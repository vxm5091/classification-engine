from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import ClassificationRule, Transaction
from backend.schemas import RuleOut, RuleCreate, RuleUpdate

router = APIRouter(tags=["rules"])


@router.get("/rules", response_model=list[RuleOut])
def list_rules(db: Session = Depends(get_db)):
    # Subquery for match count: count transactions referencing each rule
    match_counts = (
        db.query(
            Transaction.rule_id,
            func.count(Transaction.id).label("match_count"),
        )
        .filter(Transaction.rule_id.isnot(None))
        .group_by(Transaction.rule_id)
        .subquery()
    )

    rows = (
        db.query(ClassificationRule, func.coalesce(match_counts.c.match_count, 0).label("match_count"))
        .outerjoin(match_counts, ClassificationRule.rule_id == match_counts.c.rule_id)
        .order_by(ClassificationRule.rule_id)
        .all()
    )

    result = []
    for rule, match_count in rows:
        out = RuleOut.model_validate(rule)
        out.match_count = match_count
        result.append(out)
    return result


@router.post("/rules", response_model=RuleOut, status_code=201)
def create_rule(body: RuleCreate, db: Session = Depends(get_db)):
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


@router.put("/rules/{rule_id}", response_model=RuleOut)
def update_rule(rule_id: int, body: RuleUpdate, db: Session = Depends(get_db)):
    rule = db.query(ClassificationRule).filter(ClassificationRule.rule_id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(rule, key, value)

    db.commit()
    db.refresh(rule)

    # Get match count
    match_count = (
        db.query(func.count(Transaction.id))
        .filter(Transaction.rule_id == rule_id)
        .scalar()
    )

    out = RuleOut.model_validate(rule)
    out.match_count = match_count
    return out


@router.post("/rules/{rule_id}/deactivate", response_model=RuleOut)
def deactivate_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.query(ClassificationRule).filter(ClassificationRule.rule_id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    rule.is_active = False
    db.commit()
    db.refresh(rule)

    match_count = (
        db.query(func.count(Transaction.id))
        .filter(Transaction.rule_id == rule_id)
        .scalar()
    )

    out = RuleOut.model_validate(rule)
    out.match_count = match_count
    return out
