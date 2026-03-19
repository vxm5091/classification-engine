"""
Deterministic rule matching engine.

Matches transactions against active ClassificationRules by vendor_id,
service_id, amount range, and time-of-month window.

Confidence logic:
- Single match                        -> High confidence
- Multiple matches, same GL code      -> High confidence
- Multiple matches, different GL codes -> Low confidence, Flagged
- No match                            -> None (route to LLM)
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from backend.models import ClassificationRule, Transaction


@dataclass
class RuleMatchResult:
    gl_code: int
    confidence: str          # "High" or "Low"
    rule_id: Optional[int]   # The matched rule (first one, if multiple with same GL)
    flagged: bool            # True when multiple rules disagree on GL code


def _rule_matches(rule: ClassificationRule, vendor_id: Optional[str],
                  service_id: Optional[str], amount: Decimal,
                  day_of_month: int) -> bool:
    """Check whether a single rule matches the given transaction attributes."""
    # vendor_id: rule.vendor_id must match if specified
    if rule.vendor_id is not None and rule.vendor_id != vendor_id:
        return False

    # service_id: rule.service_id must match if specified
    if rule.service_id is not None and rule.service_id != service_id:
        return False

    # amount range
    if rule.amount_min is not None and amount < rule.amount_min:
        return False
    if rule.amount_max is not None and amount > rule.amount_max:
        return False

    # time-of-month window
    if rule.time_of_month_start is not None and day_of_month < rule.time_of_month_start:
        return False
    if rule.time_of_month_end is not None and day_of_month > rule.time_of_month_end:
        return False

    return True


def classify_deterministic(
    transaction: Transaction,
    rules: list[ClassificationRule],
) -> Optional[RuleMatchResult]:
    """
    Attempt to classify a transaction using deterministic rules.

    Returns a RuleMatchResult on match, or None if no rule applies (route to LLM).
    """
    vendor_id = transaction.vendor_id
    service_id = transaction.service_id
    amount = Decimal(str(transaction.amount))
    day_of_month = transaction.date.day

    matches = [r for r in rules if _rule_matches(r, vendor_id, service_id, amount, day_of_month)]

    if not matches:
        return None

    gl_codes = {r.gl_code for r in matches}

    if len(gl_codes) == 1:
        # Single GL code (one or many rules agree) -> High confidence
        return RuleMatchResult(
            gl_code=matches[0].gl_code,
            confidence="High",
            rule_id=matches[0].rule_id,
            flagged=False,
        )
    else:
        # Multiple rules disagree on GL code -> Low confidence, flagged
        # Pick the GL code from the first matching rule (arbitrary but deterministic)
        return RuleMatchResult(
            gl_code=matches[0].gl_code,
            confidence="Low",
            rule_id=matches[0].rule_id,
            flagged=True,
        )


def load_active_rules(db: Session) -> list[ClassificationRule]:
    """Load all active classification rules from the database."""
    return (
        db.query(ClassificationRule)
        .filter(ClassificationRule.is_active.is_(True))
        .all()
    )
