import csv
import io
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, UploadFile, File, Form
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Transaction, ClassificationRule
from backend.schemas import (
    ClassifyRequest,
    ClassifyResponse,
    UploadResponse,
    SuggestRulesResponse,
    RuleSuggestion,
    AcceptSuggestionsRequest,
    ReclassifyResponse,
)
from backend.services.classification import classify_transactions
from backend.services.llm_rule_suggester import suggest_rules

router = APIRouter(tags=["classify"])


# ---------------------------------------------------------------------------
# CSV parsing helpers
# ---------------------------------------------------------------------------

def _parse_amount(raw: str) -> Decimal | None:
    if not raw:
        return None
    s = raw.strip()
    negative = False
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
    s = raw.strip()
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _latest_version_subquery(db: Session):
    return (
        db.query(
            Transaction.transaction_id,
            func.max(Transaction.version).label("max_version"),
        )
        .group_by(Transaction.transaction_id)
        .subquery()
    )


# ---------------------------------------------------------------------------
# Upload endpoint
# ---------------------------------------------------------------------------

@router.post("/upload-csv", response_model=UploadResponse)
async def upload_csv(
    file: UploadFile = File(...),
    batch_label: str = Form(None),
    db: Session = Depends(get_db),
):
    """
    Upload a CSV file of transactions to ingest (but not yet classify).
    """
    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("utf-8")

    reader = csv.reader(io.StringIO(text))

    header = next(reader, None)
    if not header:
        return UploadResponse(
            filename=file.filename,
            transactions_ingested=0,
            transactions_skipped=0,
            source_file=file.filename,
            upload_batch=file.filename,
        )

    clean_header = [h.strip().lower() for h in header]

    date_idx = next((i for i, h in enumerate(clean_header) if "date" in h), 0)
    desc_idx = next((i for i, h in enumerate(clean_header) if "desc" in h), 1)
    amount_idx = next((i for i, h in enumerate(clean_header) if "amount" in h), 2)

    gl_idx = next(
        (i for i, h in enumerate(clean_header) if "gl" in h or "assigned" in h),
        None,
    )
    has_gl_column = gl_idx is not None

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

    if batch_label:
        batch_label = batch_label
    else:
        batch_label = f"{file.filename} ({datetime.now().strftime('%b %d, %Y %I:%M %p')})"

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
            upload_batch=batch_label,
            review_status="Unreviewed",
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
        upload_batch=batch_label,
    )


# ---------------------------------------------------------------------------
# Classification endpoint
# ---------------------------------------------------------------------------

@router.post("/classify", response_model=ClassifyResponse)
def run_classification(body: ClassifyRequest, db: Session = Depends(get_db)):
    """
    Trigger classification pipeline on transactions that need processing.
    Includes transactions missing vendor info OR missing GL codes.
    Pre-classified transactions (with GL codes from CSV) get vendor resolution
    but keep their existing GL code.
    """
    latest_version = _latest_version_subquery(db)

    from sqlalchemy import or_

    query = (
        db.query(Transaction)
        .join(
            latest_version,
            (Transaction.transaction_id == latest_version.c.transaction_id)
            & (Transaction.version == latest_version.c.max_version),
        )
        .filter(Transaction.is_expense.isnot(False))
        .filter(
            or_(
                Transaction.vendor_id.is_(None),
                Transaction.gl_code.is_(None),
                Transaction.method.is_(None),
                Transaction.method == "Pre-classified",
            )
        )
    )

    if body.source_file:
        query = query.filter(Transaction.source_file == body.source_file)

    transactions = query.all()

    summary = classify_transactions(db, transactions)
    db.commit()

    return ClassifyResponse(
        total=summary.total,
        pre_classified=summary.pre_classified,
        classified_by_rule=summary.rule_matched,
        medium_confidence=summary.medium_confidence,
        unclassified=summary.unclassified,
        non_expense=summary.non_expense,
    )


# ---------------------------------------------------------------------------
# Rule Suggestion endpoints
# ---------------------------------------------------------------------------

@router.post("/suggest-rules", response_model=SuggestRulesResponse)
def suggest_rules_endpoint(db: Session = Depends(get_db)):
    """
    Triggers the rule suggestion engine for all currently unclassified
    (Low confidence, Unclassified method) transactions.
    Returns suggested rules — does NOT create them.
    """
    latest_version = _latest_version_subquery(db)

    unclassified = (
        db.query(Transaction)
        .join(
            latest_version,
            (Transaction.transaction_id == latest_version.c.transaction_id)
            & (Transaction.version == latest_version.c.max_version),
        )
        .filter(Transaction.is_expense.is_(True))
        .filter(
            (Transaction.gl_code.is_(None))
            | (Transaction.method == "Unclassified")
        )
        .all()
    )

    if not unclassified:
        return SuggestRulesResponse(suggestions=[], total_unclassified=0)

    raw_suggestions = suggest_rules(db, unclassified)

    suggestions = []
    for s in raw_suggestions:
        if s.get("gl_code") is None or s.get("vendor_id") is None:
            continue
        try:
            suggestions.append(RuleSuggestion(**s))
        except Exception:
            continue

    return SuggestRulesResponse(
        suggestions=suggestions,
        total_unclassified=len(unclassified),
    )


@router.post("/suggest-rules/accept")
def accept_suggestions(body: AcceptSuggestionsRequest, db: Session = Depends(get_db)):
    """
    Creates classification rules from accepted suggestions.
    """
    created_ids = []
    for s in body.suggestions:
        rule = ClassificationRule(
            vendor_id=s.get("vendor_id"),
            service_id=s.get("service_id"),
            amount_min=s.get("amount_min"),
            amount_max=s.get("amount_max"),
            gl_code=s["gl_code"],
            reasoning=s.get("reasoning"),
            is_active=True,
            created_by=body.user_id,
        )
        db.add(rule)
        db.flush()
        created_ids.append(rule.rule_id)

    db.commit()
    return {"created_rule_ids": created_ids}


# ---------------------------------------------------------------------------
# Reclassify endpoint
# ---------------------------------------------------------------------------

@router.post("/reclassify", response_model=ReclassifyResponse)
def reclassify_transactions(db: Session = Depends(get_db)):
    """
    Re-runs the rule engine on all unclassified (Low confidence) and
    Flagged transactions using the current rules table.
    """
    latest_version = _latest_version_subquery(db)

    candidates = (
        db.query(Transaction)
        .join(
            latest_version,
            (Transaction.transaction_id == latest_version.c.transaction_id)
            & (Transaction.version == latest_version.c.max_version),
        )
        .filter(Transaction.is_expense.is_(True))
        .filter(
            (Transaction.method == "Unclassified")
            | (Transaction.gl_code.is_(None))
        )
        .all()
    )

    if not candidates:
        return ReclassifyResponse(
            total_reclassified=0, newly_classified=0, still_unclassified=0
        )

    summary = classify_transactions(db, candidates)
    db.commit()

    return ReclassifyResponse(
        total_reclassified=len(candidates),
        newly_classified=summary.rule_matched,
        still_unclassified=summary.unclassified,
    )


@router.post("/reclassify/{transaction_id}")
def reclassify_single_transaction(transaction_id: str, db: Session = Depends(get_db)):
    """Re-run the classification pipeline on a single transaction."""
    from fastapi import HTTPException

    txn = (
        db.query(Transaction)
        .filter(Transaction.transaction_id == transaction_id)
        .order_by(Transaction.version.desc())
        .first()
    )
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    txn.gl_code = None
    txn.confidence = None
    txn.method = None
    txn.rule_id = None
    txn.reasoning = None
    txn.review_status = "Unreviewed"

    summary = classify_transactions(db, [txn])
    db.commit()

    return {
        "transaction_id": transaction_id,
        "classified": summary.rule_matched > 0,
        "gl_code": txn.gl_code,
        "confidence": txn.confidence,
        "method": txn.method,
    }
