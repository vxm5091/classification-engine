import csv
import io
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Transaction
from backend.schemas import ClassifyRequest, ClassifyResponse, UploadResponse
from backend.services.classification import classify_transactions

router = APIRouter(tags=["classify"])


# ---------------------------------------------------------------------------
# CSV parsing helpers (same logic as seed.py)
# ---------------------------------------------------------------------------

def _parse_amount(raw: str) -> Decimal | None:
    if not raw:
        return None
    s = raw.strip()
    negative = False
    # Handle parenthetical negatives: ($X.XX) or $(X.XX)
    if ("(" in s) and s.endswith(")"):
        negative = True
        s = s.replace("(", "").replace(")", "")
    s = s.replace("$", "").replace(",", "").strip()
    if not s:
        return None
    try:
        val = Decimal(s)
    except InvalidOperation:
        return None
    return -val if negative else val


def _parse_date(raw: str) -> datetime | None:
    if not raw or not raw.strip():
        return None
    try:
        return datetime.strptime(raw.strip(), "%m/%d/%Y").date()
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Upload endpoint
# ---------------------------------------------------------------------------

@router.post("/upload-csv", response_model=UploadResponse)
async def upload_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Upload a CSV file of transactions to ingest (but not yet classify).

    Expected CSV columns: Date, Description, Amount
    (Same format as classify.csv — no GL code column.)
    """
    content = await file.read()
    # Try utf-8-sig first (handles BOM), then utf-8
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("utf-8")

    reader = csv.reader(io.StringIO(text))

    # Read header row
    header = next(reader, None)
    if not header:
        return UploadResponse(
            filename=file.filename,
            transactions_ingested=0,
            transactions_skipped=0,
            source_file=file.filename,
        )

    # Normalise header names
    clean_header = [h.strip().lower() for h in header]

    # Determine column indices
    date_idx = next((i for i, h in enumerate(clean_header) if "date" in h), 0)
    desc_idx = next((i for i, h in enumerate(clean_header) if "desc" in h), 1)
    amount_idx = next((i for i, h in enumerate(clean_header) if "amount" in h), 2)

    # Check for GL code column (pre-classified CSV like classified.csv)
    gl_idx = next(
        (i for i, h in enumerate(clean_header) if "gl" in h or "assigned" in h),
        None,
    )
    has_gl_column = gl_idx is not None

    # Figure out the next available UPL-xxx ID
    max_upl = (
        db.query(func.max(Transaction.transaction_id))
        .filter(Transaction.transaction_id.like("UPL-%"))
        .scalar()
    )
    start_num = 1
    if max_upl:
        m = re.search(r"UPL-(\d+)", max_upl)
        if m:
            start_num = int(m.group(1)) + 1

    ingested = 0
    skipped = 0

    for row_num, row in enumerate(reader, start=1):
        if not row or len(row) <= max(date_idx, desc_idx, amount_idx):
            skipped += 1
            continue

        raw_date = row[date_idx].strip()
        raw_desc = row[desc_idx].strip()
        raw_amount = row[amount_idx].strip()

        dt = _parse_date(raw_date)
        amount = _parse_amount(raw_amount)
        if not dt or not raw_desc or amount is None:
            skipped += 1
            continue

        # Parse GL code if present
        gl_code = None
        if has_gl_column and gl_idx < len(row):
            gl_str = row[gl_idx].strip()
            if gl_str:
                try:
                    gl_code = int(gl_str)
                except (ValueError, TypeError):
                    pass

        txn_id = f"UPL-{start_num + ingested:03d}"
        txn = Transaction(
            transaction_id=txn_id,
            version=1,
            date=dt,
            raw_description=raw_desc,
            amount=amount,
            source_file=file.filename,
            review_status="Approved" if gl_code else "Unreviewed",
            gl_code=gl_code,
            confidence="High" if gl_code else None,
            method="Pre-classified" if gl_code else None,
        )
        db.add(txn)
        ingested += 1

    db.commit()

    return UploadResponse(
        filename=file.filename,
        transactions_ingested=ingested,
        transactions_skipped=skipped,
        source_file=file.filename,
    )


# ---------------------------------------------------------------------------
# Classification endpoint
# ---------------------------------------------------------------------------

@router.post("/classify", response_model=ClassifyResponse)
def run_classification(body: ClassifyRequest, db: Session = Depends(get_db)):
    """Trigger classification pipeline on unclassified transactions."""
    latest_version = (
        db.query(
            Transaction.transaction_id,
            func.max(Transaction.version).label("max_version"),
        )
        .group_by(Transaction.transaction_id)
        .subquery()
    )

    query = (
        db.query(Transaction)
        .join(
            latest_version,
            (Transaction.transaction_id == latest_version.c.transaction_id)
            & (Transaction.version == latest_version.c.max_version),
        )
        .filter(Transaction.gl_code.is_(None))
        .filter(Transaction.is_expense.is_(True))
    )

    if body.source_file:
        query = query.filter(Transaction.source_file == body.source_file)

    transactions = query.all()

    summary = classify_transactions(db, transactions)
    db.commit()

    return ClassifyResponse(
        total=summary.total,
        classified_by_rule=summary.rule_matched,
        classified_by_llm=summary.llm_classified,
        unclassifiable=summary.unclassified,
        non_expense=summary.non_expense,
    )
