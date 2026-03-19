from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Vendor, VendorService, Transaction
from backend.schemas import VendorOut, VendorCreate, VendorServiceOut, VendorServiceCreate, VendorConfirm

router = APIRouter(tags=["vendors"])


@router.get("/vendors", response_model=list[VendorOut])
def list_vendors(
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    # Subquery for service count
    service_counts = (
        db.query(
            VendorService.vendor_id,
            func.count(VendorService.service_id).label("service_count"),
        )
        .group_by(VendorService.vendor_id)
        .subquery()
    )

    # Subquery for transaction count (latest version only)
    latest_version = (
        db.query(
            Transaction.transaction_id,
            func.max(Transaction.version).label("max_version"),
        )
        .group_by(Transaction.transaction_id)
        .subquery()
    )

    txn_counts = (
        db.query(
            Transaction.vendor_id,
            func.count(Transaction.id).label("txn_count"),
        )
        .join(
            latest_version,
            (Transaction.transaction_id == latest_version.c.transaction_id)
            & (Transaction.version == latest_version.c.max_version),
        )
        .filter(Transaction.vendor_id.isnot(None))
        .group_by(Transaction.vendor_id)
        .subquery()
    )

    query = (
        db.query(
            Vendor,
            func.coalesce(service_counts.c.service_count, 0).label("service_count"),
            func.coalesce(txn_counts.c.txn_count, 0).label("transaction_count"),
        )
        .outerjoin(service_counts, Vendor.vendor_id == service_counts.c.vendor_id)
        .outerjoin(txn_counts, Vendor.vendor_id == txn_counts.c.vendor_id)
    )

    if search:
        query = query.filter(
            Vendor.vendor_name.ilike(f"%{search}%")
            | Vendor.vendor_id.ilike(f"%{search}%")
        )

    query = query.order_by(Vendor.vendor_name)
    rows = query.all()

    result = []
    for vendor, service_count, transaction_count in rows:
        out = VendorOut.model_validate(vendor)
        out.transaction_count = transaction_count
        result.append(out)
    return result


@router.post("/vendors", response_model=VendorOut, status_code=201)
def create_vendor(body: VendorCreate, db: Session = Depends(get_db)):
    existing = db.query(Vendor).filter(Vendor.vendor_id == body.vendor_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="Vendor already exists")

    vendor = Vendor(
        vendor_id=body.vendor_id,
        vendor_name=body.vendor_name,
        created_by=body.user_id,
    )
    db.add(vendor)
    db.commit()
    db.refresh(vendor)

    out = VendorOut.model_validate(vendor)
    out.transaction_count = 0
    return out


@router.put("/vendors/{vendor_id}", response_model=VendorOut)
def update_vendor(vendor_id: str, body: VendorCreate, db: Session = Depends(get_db)):
    vendor = db.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    vendor.vendor_name = body.vendor_name
    db.commit()
    db.refresh(vendor)

    txn_count = (
        db.query(func.count(Transaction.id))
        .filter(Transaction.vendor_id == vendor_id)
        .scalar()
    )

    out = VendorOut.model_validate(vendor)
    out.transaction_count = txn_count
    return out


@router.post("/vendors/{vendor_id}/confirm", response_model=VendorOut)
def confirm_vendor(vendor_id: str, body: VendorConfirm, db: Session = Depends(get_db)):
    vendor = db.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    vendor.status = "active"
    vendor.confirmed_by = body.user_id
    vendor.confirmed_at = datetime.utcnow()
    db.commit()
    db.refresh(vendor)

    txn_count = (
        db.query(func.count(Transaction.id))
        .filter(Transaction.vendor_id == vendor_id)
        .scalar()
    )

    out = VendorOut.model_validate(vendor)
    out.transaction_count = txn_count
    return out


@router.get("/vendors/{vendor_id}/services", response_model=list[VendorServiceOut])
def list_vendor_services(vendor_id: str, db: Session = Depends(get_db)):
    vendor = db.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    services = (
        db.query(VendorService)
        .filter(VendorService.vendor_id == vendor_id)
        .order_by(VendorService.service_name)
        .all()
    )
    return [VendorServiceOut.model_validate(s) for s in services]


@router.post("/vendors/{vendor_id}/services", response_model=VendorServiceOut, status_code=201)
def create_vendor_service(
    vendor_id: str, body: VendorServiceCreate, db: Session = Depends(get_db)
):
    vendor = db.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    service = VendorService(
        service_id=body.service_id,
        vendor_id=vendor_id,
        service_name=body.service_name,
        created_by=body.user_id,
    )
    db.add(service)
    db.commit()
    db.refresh(service)
    return VendorServiceOut.model_validate(service)
