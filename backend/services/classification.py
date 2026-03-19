"""
Classification pipeline orchestration.

Steps:
1. Detect non-expense transactions
2. Run vendor resolution (cache-first, LLM fallback)
3. Run deterministic rule matching
4. Run LLM inference for unmatched transactions
5. Return summary stats
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from backend.models import Transaction
from backend.services.vendor_cache import normalise_pattern
from backend.services.vendor_resolution import resolve_vendors
from backend.services.rule_engine import classify_deterministic, load_active_rules
from backend.services.llm_classifier import classify_with_llm

logger = logging.getLogger(__name__)

NON_EXPENSE_KEYWORDS = [
    "AUTOPAY PAYMENT",
    "PAYMENT - THANK YOU",
]


@dataclass
class ClassificationSummary:
    total: int = 0
    non_expense: int = 0
    rule_matched: int = 0
    llm_classified: int = 0
    flagged: int = 0
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


def _apply_rule_result(txn: Transaction, result) -> None:
    """Apply a deterministic rule match result to a transaction."""
    txn.gl_code = result.gl_code
    txn.confidence = result.confidence
    txn.method = "Rule Match"
    txn.rule_id = result.rule_id
    txn.reasoning = f"Matched rule {result.rule_id}"
    if result.flagged:
        txn.review_status = "Flagged"
        txn.reasoning += " (multiple rules with conflicting GL codes)"


def _apply_llm_result(txn: Transaction, llm_item: dict) -> None:
    """Apply an LLM classification result to a transaction."""
    txn.gl_code = llm_item.get("gl_code")
    txn.confidence = llm_item.get("confidence", "Low")
    txn.method = "LLM Inference"
    txn.reasoning = llm_item.get("reasoning", "")


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
        # Continue — transactions will still attempt rule/LLM matching without vendor info

    # Apply vendor info to transactions
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
    needs_llm: list[Transaction] = []

    for txn in expense_txns:
        result = classify_deterministic(txn, rules)
        if result is not None:
            _apply_rule_result(txn, result)
            summary.rule_matched += 1
            if result.flagged:
                summary.flagged += 1
        else:
            needs_llm.append(txn)

    # ------------------------------------------------------------------
    # Step 4: LLM inference for unmatched transactions (batched)
    # ------------------------------------------------------------------
    BATCH_SIZE = 30  # Keep batches small enough for reliable JSON output

    if needs_llm:
        for batch_start in range(0, len(needs_llm), BATCH_SIZE):
            batch = needs_llm[batch_start : batch_start + BATCH_SIZE]
            try:
                llm_results = classify_with_llm(db, batch)
                # Build lookup by transaction_id
                llm_by_id = {str(r["transaction_id"]): r for r in llm_results}

                for txn in batch:
                    llm_item = llm_by_id.get(txn.transaction_id)
                    if llm_item and llm_item.get("gl_code") is not None:
                        _apply_llm_result(txn, llm_item)
                        summary.llm_classified += 1
                    elif llm_item:
                        # LLM returned null gl_code
                        _apply_llm_result(txn, llm_item)
                        txn.review_status = "Flagged"
                        summary.unclassified += 1
                    else:
                        # LLM did not return a result for this transaction
                        txn.method = "LLM Inference"
                        txn.confidence = "Low"
                        txn.reasoning = "LLM did not return a classification"
                        txn.review_status = "Flagged"
                        summary.unclassified += 1
            except Exception as e:
                logger.error("LLM classification failed for batch: %s", e)
                summary.errors.append(f"LLM classification error: {e}")
                # Mark all transactions in this failed batch
                for txn in batch:
                    txn.method = "LLM Inference"
                    txn.confidence = "Low"
                    txn.reasoning = f"Classification failed: {e}"
                    txn.review_status = "Flagged"
                summary.unclassified += len(batch)

    db.flush()
    return summary
