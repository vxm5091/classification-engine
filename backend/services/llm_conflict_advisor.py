"""
LLM Conflict Advisor.

For Medium confidence transactions (multiple rules matched with conflicting GL codes),
generates advisory text explaining which GL code is more likely correct.
Does NOT change the classification — advisory only.
"""

import json
import logging
import os
from typing import Any

import anthropic
from sqlalchemy.orm import Session

from backend.models import GLCode, Transaction, ClassificationRule

logger = logging.getLogger(__name__)

LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-20250514")

SYSTEM_PROMPT = (
    "You are an advisory engine helping accountants resolve GL code classification conflicts.\n\n"
    "For each transaction below, multiple classification rules matched with different GL codes.\n"
    "Your job is to explain which GL code is more likely correct and why, "
    "referencing historical patterns and the nature of the transaction. "
    "You are NOT making the decision — the user will decide.\n\n"
    "For each transaction, provide:\n"
    "- transaction_id\n"
    "- recommended_gl_code: Your best assessment\n"
    "- advisory: 2-3 sentence explanation. Reference the specific conflicting rules, "
    "historical patterns, and vendor context.\n\n"
    "Respond in JSON only:\n"
    "[\n"
    "  {\n"
    '    "transaction_id": "NEW-045",\n'
    '    "recommended_gl_code": 6260,\n'
    '    "advisory": "Rules R-14 (GL 6200) and R-22 (GL 6260) both match. ..."\n'
    "  }\n"
    "]"
)


def _build_historical_for_vendors(db: Session, vendor_ids: list[str], limit: int = 10) -> str:
    if not vendor_ids:
        return "(no historical comparables)"
    lines: list[str] = []
    for vid in vendor_ids:
        txns = (
            db.query(Transaction)
            .filter(
                Transaction.vendor_id == vid,
                Transaction.gl_code.isnot(None),
            )
            .order_by(Transaction.date.desc())
            .limit(limit)
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
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return json.loads(cleaned.strip())


def advise_on_conflicts(
    db: Session,
    conflict_items: list[dict[str, Any]],
) -> dict[str, dict]:
    """
    Generate advisory text for transactions with conflicting rule matches.

    conflict_items: list of dicts with keys:
        - transaction: Transaction ORM object
        - matching_rules: list of ClassificationRule objects that conflicted

    Returns a dict keyed by transaction_id with advisory info.
    """
    if not conflict_items:
        return {}

    vendor_ids = list({
        item["transaction"].vendor_id
        for item in conflict_items
        if item["transaction"].vendor_id
    })
    historical = _build_historical_for_vendors(db, vendor_ids)

    txn_blocks = []
    for item in conflict_items:
        txn = item["transaction"]
        rules = item["matching_rules"]
        rule_details = []
        for r in rules:
            gl = db.query(GLCode).filter(GLCode.gl_code == r.gl_code).first()
            gl_name = gl.gl_class if gl else str(r.gl_code)
            parts = [f"R-{r.rule_id} → GL {r.gl_code} ({gl_name})"]
            if r.service_id:
                parts.append(f"service={r.service_id}")
            if r.amount_min is not None or r.amount_max is not None:
                parts.append(f"amount={r.amount_min}-{r.amount_max}")
            rule_details.append(", ".join(parts))

        txn_blocks.append(
            f"Transaction {txn.transaction_id}:\n"
            f"  Description: {txn.raw_description}\n"
            f"  Amount: ${txn.amount}\n"
            f"  Date: {txn.date}\n"
            f"  Vendor: {txn.vendor_id}, Service: {txn.service_id}\n"
            f"  Conflicting rules:\n"
            + "\n".join(f"    - {rd}" for rd in rule_details)
        )

    user_content = (
        "Historical classified transactions by vendor:\n"
        f"{historical}\n\n"
        "Transactions with conflicting rule matches:\n"
        + "\n\n".join(txn_blocks)
    )

    logger.info("Calling LLM conflict advisor for %d transactions", len(conflict_items))

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    response = client.messages.create(
        model=LLM_MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    results = _parse_llm_json(response.content[0].text)

    advisory_map = {}
    for r in results:
        tid = str(r.get("transaction_id", ""))
        advisory_map[tid] = {
            "recommended_gl_code": r.get("recommended_gl_code"),
            "advisory": r.get("advisory", ""),
        }

    return advisory_map
