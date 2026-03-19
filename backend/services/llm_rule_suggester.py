"""
LLM Rule Suggestion Engine.

Takes batches of unclassified transactions and suggests new classification rules
for the user to review/approve. Does NOT classify individual transactions.
"""

import json
import logging
import os
from typing import Any

import anthropic
from sqlalchemy.orm import Session

from backend.models import GLCode, Transaction, ClassificationRule, Vendor, VendorService

logger = logging.getLogger(__name__)

LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-20250514")

SYSTEM_PROMPT = (
    "You are a rule suggestion engine for a GL code classification system at a small insurance agency.\n\n"
    "You will receive:\n"
    "1. A batch of unclassified transactions (no existing rule matched)\n"
    "2. The current rules table (so you don't suggest duplicates)\n"
    "3. Historical classified transactions for context\n"
    "4. The GL code hierarchy\n\n"
    "Your job is to suggest NEW classification rules that would correctly classify these transactions.\n"
    "Do NOT classify individual transactions. Instead, suggest rules that cover patterns.\n\n"
    "For each suggested rule, provide:\n"
    "- vendor_id: The vendor ticker to match (must reference an existing vendor)\n"
    "- service_id: Optional service ticker for more specific matching (null if not needed)\n"
    "- amount_min / amount_max: Optional amount range if relevant (null if not needed)\n"
    "- gl_code: The target GL code (integer)\n"
    "- reasoning: Why this rule makes sense — reference historical patterns, vendor business type, GL code descriptions\n"
    "- affected_transactions: List of transaction_ids this rule would classify\n\n"
    "Group transactions by vendor. One rule per vendor pattern. "
    "If a vendor needs multiple rules (different services or amount ranges), suggest each separately.\n\n"
    "Be conservative. If you're unsure about a GL code, say so in the reasoning and let the user decide.\n\n"
    "Respond in JSON only — an array of suggested rules:\n"
    "[\n"
    "  {\n"
    '    "vendor_id": "COMCST",\n'
    '    "service_id": null,\n'
    '    "amount_min": null,\n'
    '    "amount_max": null,\n'
    '    "gl_code": 6260,\n'
    '    "reasoning": "Comcast transactions without a service-level match appear to be cable/utility charges...",\n'
    '    "affected_transactions": ["NEW-045", "NEW-089"]\n'
    "  }\n"
    "]"
)


def _build_gl_hierarchy(db: Session) -> str:
    codes = (
        db.query(GLCode)
        .filter(GLCode.gl_level == 3)
        .order_by(GLCode.gl_code)
        .all()
    )
    lines = [f"- {c.gl_code}: {c.description} ({c.gl_class})" for c in codes]
    return "\n".join(lines) if lines else "(no GL codes found)"


def _build_existing_rules(db: Session) -> str:
    rules = (
        db.query(ClassificationRule)
        .filter(ClassificationRule.is_active.is_(True))
        .all()
    )
    if not rules:
        return "(no existing rules)"
    lines = []
    for r in rules:
        parts = [f"R-{r.rule_id}: vendor={r.vendor_id}"]
        if r.service_id:
            parts.append(f"service={r.service_id}")
        if r.amount_min is not None:
            parts.append(f"amount_min={r.amount_min}")
        if r.amount_max is not None:
            parts.append(f"amount_max={r.amount_max}")
        parts.append(f"→ GL {r.gl_code}")
        lines.append(" ".join(parts))
    return "\n".join(lines)


def _build_historical(db: Session, vendor_ids: list[str], limit: int = 10) -> str:
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


def suggest_rules(
    db: Session,
    unclassified_transactions: list[Transaction],
) -> list[dict[str, Any]]:
    """
    Send unclassified transactions to LLM and get suggested rules back.
    Returns a list of rule suggestion dicts.
    """
    if not unclassified_transactions:
        return []

    gl_hierarchy = _build_gl_hierarchy(db)
    existing_rules = _build_existing_rules(db)
    vendor_ids = list({t.vendor_id for t in unclassified_transactions if t.vendor_id})
    historical = _build_historical(db, vendor_ids)

    txn_lines = []
    for t in unclassified_transactions:
        vendor = db.query(Vendor).filter(Vendor.vendor_id == t.vendor_id).first() if t.vendor_id else None
        vendor_name = vendor.vendor_name if vendor else "Unknown"
        txn_lines.append(
            f"- transaction_id: {t.transaction_id}, description: {t.raw_description}, "
            f"amount: {t.amount}, date: {t.date}, vendor_id: {t.vendor_id}, "
            f"vendor_name: {vendor_name}, service_id: {t.service_id}"
        )

    user_content = (
        "GL Code Hierarchy (level 3 only):\n"
        f"{gl_hierarchy}\n\n"
        "Existing Rules (do not duplicate):\n"
        f"{existing_rules}\n\n"
        "Historical classified transactions by vendor:\n"
        f"{historical}\n\n"
        "Unclassified transactions (no rule matched):\n"
        + "\n".join(txn_lines)
    )

    logger.info("Calling LLM to suggest rules for %d transactions", len(unclassified_transactions))

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    response = client.messages.create(
        model=LLM_MODEL,
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    suggestions = _parse_llm_json(response.content[0].text)

    enriched = []
    for s in suggestions:
        vendor = db.query(Vendor).filter(Vendor.vendor_id == s.get("vendor_id")).first()
        gl = db.query(GLCode).filter(GLCode.gl_code == s.get("gl_code")).first()
        service = None
        if s.get("service_id"):
            service = db.query(VendorService).filter(VendorService.service_id == s["service_id"]).first()

        enriched.append({
            "vendor_id": s.get("vendor_id"),
            "vendor_name": vendor.vendor_name if vendor else s.get("vendor_id", "Unknown"),
            "service_id": s.get("service_id"),
            "service_name": service.service_name if service else None,
            "amount_min": s.get("amount_min"),
            "amount_max": s.get("amount_max"),
            "gl_code": s.get("gl_code"),
            "gl_class": gl.gl_class if gl else None,
            "reasoning": s.get("reasoning", ""),
            "affected_transaction_ids": s.get("affected_transactions", []),
            "affected_count": len(s.get("affected_transactions", [])),
        })

    return enriched
