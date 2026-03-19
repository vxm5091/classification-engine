"""
Deterministic rule matching engine.

Matches transactions against active ClassificationRules by vendor_id,
service_id, amount range, and time-of-month window.

Confidence logic:
- Single match                        -> High confidence
- Multiple matches, same GL code      -> High confidence
- Multiple matches, different GL codes -> Medium confidence, Flagged
- No match                            -> None (Unclassified)
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from backend.models import ClassificationRule, Transaction


@dataclass
class RuleMatchResult:
    gl_code: int
    confidence: str          # "High" or "Medium"
    rule_id: Optional[int]   # The matched rule (first one, if multiple with same GL)
    flagged: bool            # True when multiple rules disagree on GL code
    matched_rule: object = None  # The winning ClassificationRule object
    matching_rules: list = None  # Populated on conflict for the conflict advisor


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


def _specificity_score(rule: ClassificationRule) -> int:
    """Higher score = more specific rule. Used to pick the best match on conflicts."""
    score = 0
    if rule.vendor_id is not None:
        score += 1
    if rule.service_id is not None:
        score += 2
    if rule.amount_min is not None or rule.amount_max is not None:
        score += 1
    if rule.time_of_month_start is not None:
        score += 1
    return score


def _most_specific_rule(rules: list[ClassificationRule]) -> ClassificationRule:
    """Return the rule with the highest specificity score."""
    return max(rules, key=_specificity_score)


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
        most_specific = _most_specific_rule(matches)
        return RuleMatchResult(
            gl_code=most_specific.gl_code,
            confidence="High",
            rule_id=most_specific.rule_id,
            flagged=False,
            matched_rule=most_specific,
        )
    else:
        most_specific = _most_specific_rule(matches)
        return RuleMatchResult(
            gl_code=most_specific.gl_code,
            confidence="Medium",
            rule_id=most_specific.rule_id,
            flagged=True,
            matched_rule=most_specific,
            matching_rules=matches,
        )


def load_active_rules(db: Session) -> list[ClassificationRule]:
    """Load all active classification rules from the database."""
    return (
        db.query(ClassificationRule)
        .filter(ClassificationRule.is_active.is_(True))
        .all()
    )
