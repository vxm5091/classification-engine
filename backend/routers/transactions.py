from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, desc, asc, case, distinct
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Transaction, GLCode, Vendor, ClassificationRule
from backend.schemas import (
    TransactionOut,
    TransactionListResponse,
    TransactionApprove,
    TransactionReclassify,
    TransactionFlag,
    ConvertToRule,
    RuleOut,
)

router = APIRouter(tags=["transactions"])


def _get_latest_version(db: Session, transaction_id: str) -> Transaction:
    """Get the latest version of a transaction by transaction_id."""
    txn = (
        db.query(Transaction)
        .filter(Transaction.transaction_id == transaction_id)
        .order_by(Transaction.version.desc())
        .first()
    )
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return txn


def _create_new_version(db: Session, latest: Transaction, **overrides) -> Transaction:
    """Create a new version of a transaction, copying fields and applying overrides."""
    new_txn = Transaction(
        transaction_id=latest.transaction_id,
        version=latest.version + 1,
        date=latest.date,
        raw_description=latest.raw_description,
        amount=latest.amount,
        vendor_id=latest.vendor_id,
        service_id=latest.service_id,
        city=latest.city,
        state=latest.state,
        country=latest.country,
        is_expense=latest.is_expense,
        gl_code=latest.gl_code,
        confidence=latest.confidence,
        method=latest.method,
        rule_id=latest.rule_id,
        reasoning=latest.reasoning,
        review_status=latest.review_status,
        reviewed_by=latest.reviewed_by,
        reviewed_at=latest.reviewed_at,
        source_file=latest.source_file,
        upload_batch=latest.upload_batch,
    )
    for key, value in overrides.items():
        setattr(new_txn, key, value)
    db.add(new_txn)
    db.commit()
    db.refresh(new_txn)
    return new_txn


@router.get("/transactions/source-files")
def list_source_files(db: Session = Depends(get_db)):
    """Return distinct source_file values (legacy endpoint)."""
    rows = (
        db.query(distinct(Transaction.source_file))
        .filter(Transaction.source_file.isnot(None))
        .all()
    )
    return [r[0] for r in rows if r[0]]


@router.get("/transactions/batches")
def list_batches(db: Session = Depends(get_db)):
    """Return distinct upload_batch values for the batch filter, most recent first."""
    rows = (
        db.query(
            Transaction.upload_batch,
            func.max(Transaction.created_at).label("latest"),
        )
        .filter(Transaction.upload_batch.isnot(None))
        .group_by(Transaction.upload_batch)
        .order_by(desc(func.max(Transaction.created_at)))
        .all()
    )
    result = [r[0] for r in rows if r[0]]
    if not result:
        source_rows = (
            db.query(distinct(Transaction.source_file))
            .filter(Transaction.source_file.isnot(None))
            .all()
        )
        result = [r[0] for r in source_rows if r[0]]
    return result


# Custom ordering for confidence: Low=0, Medium=1, High=2, NULL=3
_CONFIDENCE_ORDER = case(
    (Transaction.confidence == "Low", 0),
    (Transaction.confidence == "Medium", 1),
    (Transaction.confidence == "High", 2),
    else_=3,
)

# Custom ordering for review_status: Flagged=0, Unreviewed=1, Reclassified=2, Approved=3
_STATUS_ORDER = case(
    (Transaction.review_status == "Flagged", 0),
    (Transaction.review_status == "Unreviewed", 1),
    (Transaction.review_status == "Reclassified", 2),
    (Transaction.review_status == "Approved", 3),
    else_=4,
)


@router.get("/transactions", response_model=TransactionListResponse)
def list_transactions(
    confidence: Optional[str] = Query(None),
    gl_code: Optional[int] = Query(None),
    review_status: Optional[str] = Query(None),
    vendor_id: Optional[str] = Query(None),
    vendor_search: Optional[str] = Query(None),
    source_file: Optional[str] = Query(None),
    upload_batch: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    sort_by: Optional[str] = Query("confidence"),
    sort_order: Optional[str] = Query("asc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    # Subquery to get the max version per transaction_id
    latest_version = (
        db.query(
            Transaction.transaction_id,
            func.max(Transaction.version).label("max_version"),
        )
        .group_by(Transaction.transaction_id)
        .subquery()
    )

    query = (
        db.query(
            Transaction,
            GLCode.gl_class.label("gl_class"),
            Vendor.vendor_name.label("vendor_name"),
        )
        .join(
            latest_version,
            (Transaction.transaction_id == latest_version.c.transaction_id)
            & (Transaction.version == latest_version.c.max_version),
        )
        .outerjoin(GLCode, Transaction.gl_code == GLCode.gl_code)
        .outerjoin(Vendor, Transaction.vendor_id == Vendor.vendor_id)
    )

    # Apply filters
    if confidence:
        query = query.filter(Transaction.confidence == confidence)
    if gl_code:
        query = query.filter(Transaction.gl_code == gl_code)
    if review_status:
        query = query.filter(Transaction.review_status == review_status)
    if vendor_id:
        query = query.filter(Transaction.vendor_id == vendor_id)
    if vendor_search:
        query = query.filter(Vendor.vendor_name.ilike(f"%{vendor_search}%"))
    if source_file:
        query = query.filter(Transaction.source_file == source_file)
    if upload_batch:
        query = query.filter(Transaction.upload_batch == upload_batch)
    if date_from:
        query = query.filter(Transaction.date >= date_from)
    if date_to:
        query = query.filter(Transaction.date <= date_to)

    # Count total before pagination
    total = query.count()

    # Sorting — use custom ordering for confidence and review_status
    if sort_by == "confidence":
        sort_expr = _CONFIDENCE_ORDER
    elif sort_by == "review_status":
        sort_expr = _STATUS_ORDER
    else:
        sort_expr = getattr(Transaction, sort_by, Transaction.date)

    order_func = desc if sort_order == "desc" else asc
    query = query.order_by(order_func(sort_expr))

    # Pagination
    offset = (page - 1) * page_size
    rows = query.offset(offset).limit(page_size).all()

    transactions = []
    for txn, gl_class, vendor_name in rows:
        out = TransactionOut.model_validate(txn)
        out.gl_class = gl_class
        out.vendor_name = vendor_name
        transactions.append(out)

    return TransactionListResponse(
        transactions=transactions,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/transactions/{transaction_id}", response_model=list[TransactionOut])
def get_transaction(transaction_id: str, db: Session = Depends(get_db)):
    versions = (
        db.query(
            Transaction,
            GLCode.gl_class.label("gl_class"),
            Vendor.vendor_name.label("vendor_name"),
        )
        .outerjoin(GLCode, Transaction.gl_code == GLCode.gl_code)
        .outerjoin(Vendor, Transaction.vendor_id == Vendor.vendor_id)
        .filter(Transaction.transaction_id == transaction_id)
        .order_by(Transaction.version.asc())
        .all()
    )
    if not versions:
        raise HTTPException(status_code=404, detail="Transaction not found")

    result = []
    for txn, gl_class, vendor_name in versions:
        out = TransactionOut.model_validate(txn)
        out.gl_class = gl_class
        out.vendor_name = vendor_name
        result.append(out)
    return result


@router.post("/transactions/{transaction_id}/approve", response_model=TransactionOut)
def approve_transaction(
    transaction_id: str, body: TransactionApprove, db: Session = Depends(get_db)
):
    latest = _get_latest_version(db, transaction_id)
    new_txn = _create_new_version(
        db,
        latest,
        review_status="Approved",
        reviewed_by=body.user_id,
        reviewed_at=datetime.utcnow(),
    )
    return TransactionOut.model_validate(new_txn)


@router.post("/transactions/{transaction_id}/reclassify", response_model=TransactionOut)
def reclassify_transaction(
    transaction_id: str, body: TransactionReclassify, db: Session = Depends(get_db)
):
    latest = _get_latest_version(db, transaction_id)
    new_txn = _create_new_version(
        db,
        latest,
        gl_code=body.gl_code,
        confidence="High",
        review_status="Reclassified",
        reviewed_by=body.user_id,
        reviewed_at=datetime.utcnow(),
        reasoning=body.notes,
    )
    return TransactionOut.model_validate(new_txn)


@router.post("/transactions/{transaction_id}/flag", response_model=TransactionOut)
def flag_transaction(
    transaction_id: str, body: TransactionFlag, db: Session = Depends(get_db)
):
    latest = _get_latest_version(db, transaction_id)
    new_txn = _create_new_version(
        db,
        latest,
        review_status="Flagged",
        reviewed_by=body.user_id,
        reviewed_at=datetime.utcnow(),
        reasoning=body.notes,
    )
    return TransactionOut.model_validate(new_txn)


@router.post("/transactions/{transaction_id}/convert-to-rule", response_model=RuleOut)
def convert_to_rule(
    transaction_id: str, body: ConvertToRule, db: Session = Depends(get_db)
):
    # Verify transaction exists
    _get_latest_version(db, transaction_id)

    rule = ClassificationRule(
        vendor_id=body.vendor_id,
        service_id=body.service_id,
        amount_min=body.amount_min,
        amount_max=body.amount_max,
        time_of_month_start=body.time_of_month_start,
        time_of_month_end=body.time_of_month_end,
        gl_code=body.gl_code,
        created_by=body.user_id,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)

    out = RuleOut.model_validate(rule)
    out.match_count = 0
    return out
