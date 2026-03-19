from fastapi import APIRouter, Depends
from sqlalchemy import String, func, cast
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Transaction
from backend.schemas import StatsResponse

router = APIRouter(tags=["stats"])


@router.get("/stats", response_model=StatsResponse)
def get_stats(db: Session = Depends(get_db)):
    # Subquery for latest version per transaction
    latest_version = (
        db.query(
            Transaction.transaction_id,
            func.max(Transaction.version).label("max_version"),
        )
        .group_by(Transaction.transaction_id)
        .subquery()
    )

    base = (
        db.query(Transaction)
        .join(
            latest_version,
            (Transaction.transaction_id == latest_version.c.transaction_id)
            & (Transaction.version == latest_version.c.max_version),
        )
    )

    total = base.count()

    # By review_status
    by_review_status = {}
    rows = (
        base.with_entities(Transaction.review_status, func.count(Transaction.id))
        .group_by(Transaction.review_status)
        .all()
    )
    for status, count in rows:
        if status:
            by_review_status[status] = count

    # By confidence
    by_confidence = {}
    rows = (
        base.with_entities(Transaction.confidence, func.count(Transaction.id))
        .group_by(Transaction.confidence)
        .all()
    )
    for conf, count in rows:
        if conf:
            by_confidence[conf] = count

    # By method
    by_method = {}
    rows = (
        base.with_entities(Transaction.method, func.count(Transaction.id))
        .group_by(Transaction.method)
        .all()
    )
    for method, count in rows:
        if method:
            by_method[method] = count

    # By gl_code
    by_gl_code = {}
    rows = (
        base.with_entities(Transaction.gl_code, func.count(Transaction.id))
        .filter(Transaction.gl_code.isnot(None))
        .group_by(Transaction.gl_code)
        .all()
    )
    for gl_code, count in rows:
        by_gl_code[str(gl_code)] = count

    return StatsResponse(
        total_transactions=total,
        by_review_status=by_review_status,
        by_confidence=by_confidence,
        by_method=by_method,
        by_gl_code=by_gl_code,
    )
