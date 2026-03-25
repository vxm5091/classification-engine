"""
Classification pipeline orchestration.

Steps:
1. Detect non-expense transactions
2. Run vendor resolution (cache-first, LLM fallback)
3. Run deterministic rule matching
4. For Medium confidence (rule conflicts), call LLM conflict advisor
5. Unmatched transactions → Unclassified (gl_code=NULL, confidence=Low)
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from backend.models import Transaction
from backend.services.vendor_cache import normalise_pattern
from backend.services.vendor_resolution import resolve_vendors
from backend.services.rule_engine import classify_deterministic, load_active_rules
from backend.services.llm_conflict_advisor import advise_on_conflicts

logger = logging.getLogger(__name__)

NON_EXPENSE_KEYWORDS = [
    "AUTOPAY PAYMENT",
    "PAYMENT - THANK YOU",
]


@dataclass
class ClassificationSummary:
    total: int = 0
    non_expense: int = 0
    pre_classified: int = 0
    rule_matched: int = 0
    medium_confidence: int = 0
    unclassified: int = 0
    errors: list[str] = field(default_factory=list)


def is_non_expense(description: str, amount: float) -> bool:
    """Check if a transaction is a non-expense (e.g. credit card payment)."""
    upper = description.upper()
    return any(kw in upper for kw in NON_EXPENSE_KEYWORDS)


def _apply_non_expense(txn: Transaction) -> None:
    """Mark a transaction as non-expense."""
    txn.is_expense = False
    txn.gl_code = None
    txn.method = "Unclassifiable"
    txn.confidence = None
    txn.reasoning = "Non-expense transaction: credit card payment"
    txn.review_status = "Approved"


def _format_rule_reasoning(rule) -> str:
    """Build a human-readable summary of the rule that matched."""
    parts = [f"Rule R-{rule.rule_id}"]
    if rule.vendor_id:
        parts.append(f"vendor={rule.vendor_id}")
    if rule.service_id:
        parts.append(f"service={rule.service_id}")
    if rule.amount_min is not None or rule.amount_max is not None:
        lo = f"${rule.amount_min}" if rule.amount_min is not None else "any"
        hi = f"${rule.amount_max}" if rule.amount_max is not None else "any"
        parts.append(f"amount={lo}–{hi}")
    if rule.time_of_month_start is not None:
        parts.append(f"day={rule.time_of_month_start}–{rule.time_of_month_end}")
    parts.append(f"→ GL {rule.gl_code}")
    return " | ".join(parts)


def _apply_rule_result(txn: Transaction, result) -> None:
    """Apply a deterministic rule match result to a transaction."""
    txn.gl_code = result.gl_code
    txn.confidence = result.confidence
    txn.method = "Rule Match"
    txn.rule_id = result.rule_id
    if result.flagged:
        conflict_detail = "; ".join(
            _format_rule_reasoning(r) for r in (result.matching_rules or [])
        )
        txn.reasoning = f"RULE CONFLICT — multiple rules matched with different GL codes. {conflict_detail}. Most specific rule selected. Review recommended."
        txn.review_status = "Flagged"
    else:
        rule_desc = _format_rule_reasoning(result.matched_rule) if result.matched_rule else f"Rule R-{result.rule_id}"
        parts = [f"Deterministic match: {rule_desc}"]
        if result.matched_rule and getattr(result.matched_rule, "reasoning", None):
            parts.append(f"\n\nRule Justification: {result.matched_rule.reasoning}")
        txn.reasoning = "".join(parts)
        txn.review_status = "Unreviewed"


def _apply_unclassified(txn: Transaction) -> None:
    """Mark a transaction as unclassified (no rule matched)."""
    txn.gl_code = None
    txn.confidence = "Low"
    txn.method = "Unclassified"
    txn.rule_id = None
    txn.reasoning = "No classification rule matched this transaction."
    txn.review_status = "Flagged"


def classify_transactions(
    db: Session, transactions: list[Transaction]
) -> ClassificationSummary:
    """
    Run the full classification pipeline on a list of transactions.

    Transactions are modified in-place and flushed to the session.
    The caller is responsible for committing.
    """
    summary = ClassificationSummary(total=len(transactions))

    if not transactions:
        return summary

    # ------------------------------------------------------------------
    # Step 1: Detect non-expense transactions
    # ------------------------------------------------------------------
    expense_txns: list[Transaction] = []
    for txn in transactions:
        if is_non_expense(txn.raw_description, float(txn.amount)):
            _apply_non_expense(txn)
            summary.non_expense += 1
        else:
            expense_txns.append(txn)

    if not expense_txns:
        db.flush()
        return summary

    # ------------------------------------------------------------------
    # Step 2: Vendor resolution (cache-first, LLM fallback)
    # ------------------------------------------------------------------
    raw_descriptions = [t.raw_description for t in expense_txns]
    try:
        vendor_map = resolve_vendors(db, raw_descriptions)
    except Exception as e:
        logger.error("Vendor resolution failed: %s", str(e)[:200])
        summary.errors.append(f"Vendor resolution error: {e}")
        vendor_map = {}

    for txn in expense_txns:
        pattern = normalise_pattern(txn.raw_description)
        info = vendor_map.get(pattern)
        if info:
            txn.vendor_id = info["vendor_id"]
            txn.service_id = info.get("service_id")
            txn.city = info.get("city")
            txn.state = info.get("state")
            txn.country = info.get("country")

    # ------------------------------------------------------------------
    # Step 3: Deterministic rule matching
    # ------------------------------------------------------------------
    rules = load_active_rules(db)
    conflict_items: list[dict] = []

    for txn in expense_txns:
        is_preclassified = txn.method == "Pre-classified" and txn.gl_code is not None
        result = classify_deterministic(txn, rules)

        if is_preclassified:
            summary.pre_classified += 1
            if result is not None:
                if result.gl_code == txn.gl_code:
                    txn.method = "Pre-classified"
                    txn.rule_id = result.rule_id
                    txn.confidence = "High"
                    rule_desc = _format_rule_reasoning(result.matched_rule) if result.matched_rule else f"Rule R-{result.rule_id}"
                    parts = [f"Pre-classified GL {txn.gl_code} confirmed by rule match: {rule_desc}"]
                    if result.matched_rule and getattr(result.matched_rule, "reasoning", None):
                        parts.append(f"\n\nRule Justification: {result.matched_rule.reasoning}")
                    txn.reasoning = "".join(parts)
                else:
                    txn.confidence = "Medium"
                    txn.review_status = "Flagged"
                    rule_desc = _format_rule_reasoning(result.matched_rule) if result.matched_rule else f"Rule R-{result.rule_id}"
                    txn.reasoning = (
                        f"Pre-classified as GL {txn.gl_code}, but rule match suggests GL {result.gl_code}. "
                        f"{rule_desc}. Review recommended."
                    )
                    summary.medium_confidence += 1
            continue

        if result is not None:
            _apply_rule_result(txn, result)
            summary.rule_matched += 1
            if result.flagged:
                summary.medium_confidence += 1
                conflict_items.append({
                    "transaction": txn,
                    "matching_rules": result.matching_rules or [],
                })
        else:
            _apply_unclassified(txn)
            summary.unclassified += 1

    # ------------------------------------------------------------------
    # Step 4: Conflict advisory (Medium confidence transactions)
    # ------------------------------------------------------------------
    if conflict_items:
        try:
            advisory_map = advise_on_conflicts(db, conflict_items)
            for item in conflict_items:
                txn = item["transaction"]
                advisory = advisory_map.get(txn.transaction_id)
                if advisory:
                    txn.reasoning = (
                        txn.reasoning + f"\n\nLLM Advisory: {advisory['advisory']}"
                    )
        except Exception as e:
            logger.error("Conflict advisor failed: %s", e)
            summary.errors.append(f"Conflict advisor error: {e}")

    db.flush()
    return summary
