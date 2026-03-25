"""
LLM-based GL code classification.

Batches all rule-unmatched transactions into a single Anthropic API call,
providing GL code hierarchy and historical comparables as context.
"""

import json
import logging
import os
from typing import Any, Optional

import anthropic
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models import GLCode, Transaction

logger = logging.getLogger(__name__)

LLM_MODEL = os.getenv("LLM_MODEL", "claude-opus-4-6")

SYSTEM_PROMPT = (
    "You are a GL code classifier for a small insurance agency.\n"
    "You will receive a batch of transactions that could not be classified "
    "by deterministic rules, along with context.\n\n"
    "Rules:\n"
    "- Assign exactly one GL code from the provided hierarchy for each transaction.\n"
    '- Assess your confidence: "Medium" if reasonable evidence, "Low" if uncertain.\n'
    "- If you truly cannot classify, return gl_code as null and confidence as \"Low\".\n"
    "- Be conservative. When uncertain between two codes, choose \"Low\" confidence.\n"
    "- Negative amounts may be refunds/credits. Classify based on the nature of the expense.\n\n"
    "Respond in JSON only:\n"
    "[\n"
    "  {\n"
    '    "transaction_id": "NEW-042",\n'
    '    "gl_code": 6160,\n'
    '    "confidence": "Medium",\n'
    '    "reasoning": "..."\n'
    "  }\n"
    "]"
)


def _build_gl_hierarchy(db: Session) -> str:
    """Build a text listing of level-3 GL codes for the LLM prompt."""
    codes = (
        db.query(GLCode)
        .filter(GLCode.gl_level == 3)
        .order_by(GLCode.gl_code)
        .all()
    )
    lines = [f"- {c.gl_code}: {c.description} ({c.gl_class})" for c in codes]
    return "\n".join(lines) if lines else "(no GL codes found)"


def _build_historical_comparables(
    db: Session, vendor_ids: list[str], limit_per_vendor: int = 10
) -> str:
    """
    Fetch recent approved transactions for the given vendors, grouped by vendor.
    Returns a text block the LLM can reference.
    """
    if not vendor_ids:
        return "(no historical comparables)"

    lines: list[str] = []
    for vid in vendor_ids:
        txns = (
            db.query(Transaction)
            .filter(
                Transaction.vendor_id == vid,
                Transaction.review_status == "Approved",
                Transaction.gl_code.isnot(None),
            )
            .order_by(Transaction.date.desc())
            .limit(limit_per_vendor)
            .all()
        )
        if txns:
            lines.append(f"Vendor {vid}:")
            for t in txns:
                lines.append(
                    f"  {t.transaction_id} | {t.raw_description} | "
                    f"${t.amount} | GL {t.gl_code} | {t.date}"
                )
    return "\n".join(lines) if lines else "(no historical comparables)"


def _parse_llm_json(text: str) -> list[dict]:
    """Parse JSON from LLM response, stripping markdown fences if present."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[: -3]
    return json.loads(cleaned.strip())


def classify_with_llm(
    db: Session, transactions: list[Transaction]
) -> list[dict[str, Any]]:
    """
    Classify a batch of transactions using the Anthropic LLM.

    Each transaction should already have vendor_id populated (from vendor resolution).
    Returns a list of dicts with keys: transaction_id, gl_code, confidence, reasoning.
    """
    if not transactions:
        return []

    # Gather context
    gl_hierarchy = _build_gl_hierarchy(db)
    vendor_ids = list({t.vendor_id for t in transactions if t.vendor_id})
    comparables = _build_historical_comparables(db, vendor_ids)

    # Build transaction list for the prompt
    txn_lines: list[str] = []
    for t in transactions:
        txn_lines.append(
            f"- transaction_id: {t.transaction_id}, description: {t.raw_description}, "
            f"amount: {t.amount}, date: {t.date}, vendor_id: {t.vendor_id}, "
            f"service_id: {t.service_id}"
        )

    user_content = (
        "GL Code Hierarchy (level 3 only):\n"
        f"{gl_hierarchy}\n\n"
        "Historical comparables (recent approved transactions by vendor):\n"
        f"{comparables}\n\n"
        "Transactions to classify:\n"
        + "\n".join(txn_lines)
    )

    logger.info("Calling LLM to classify %d transactions", len(transactions))

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    response = client.messages.create(
        model=LLM_MODEL,
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    results = _parse_llm_json(response.content[0].text)
    return results
