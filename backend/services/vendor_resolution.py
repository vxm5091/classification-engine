"""
Cache-first vendor resolution with LLM fallback.

Flow:
1. Normalise descriptions and check the description_vendor_map cache.
2. Batch all uncached descriptions into a single LLM call.
3. Persist new vendors / services / cache entries that the LLM discovers.
"""

import json
import logging
import os
from typing import Any

import anthropic
from sqlalchemy.orm import Session

from backend.models import Vendor, VendorService, DescriptionVendorMap
from backend.services.vendor_cache import normalise_pattern, bulk_lookup, upsert

logger = logging.getLogger(__name__)

LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-20250514")

SYSTEM_PROMPT = (
    "You are a financial transaction parser. Extract vendor information from "
    "credit card transaction descriptions.\n\n"
    "You will receive:\n"
    "1. A list of raw transaction descriptions (deduplicated)\n"
    "2. A list of known vendors and their services from our database\n\n"
    "For EACH description:\n"
    "- Match to a known vendor if possible. Use fuzzy matching \u2014 descriptions are messy and truncated.\n"
    "- If the vendor is not in the known list, suggest a new vendor_id (uppercase, max 10 chars) and vendor_name.\n"
    "- Identify the specific service if applicable (e.g., \"GOOGLE *ADS...\" \u2192 vendor: GOOGL, service: GOOGL-ADS)\n"
    "- Extract city and state from the description if present. Infer country from city/state.\n\n"
    "Respond in JSON only \u2014 an array with one entry per description, in the same order as input:\n"
    "[\n"
    "  {\n"
    '    "description_pattern": "...",\n'
    '    "vendor_id": "GOOGL",\n'
    '    "vendor_name": "Google",\n'
    '    "is_new_vendor": false,\n'
    '    "service_id": "GOOGL-ADS",\n'
    '    "service_name": "Google Ads",\n'
    '    "is_new_service": false,\n'
    '    "city": null,\n'
    '    "state": "CA",\n'
    '    "country": "US"\n'
    "  }\n"
    "]"
)


def _build_known_vendors_text(db: Session) -> str:
    """Build a text block listing all known vendors and their services."""
    vendors = db.query(Vendor).all()
    lines: list[str] = []
    for v in vendors:
        services = db.query(VendorService).filter(VendorService.vendor_id == v.vendor_id).all()
        svc_text = ", ".join(f"{s.service_id} ({s.service_name})" for s in services)
        lines.append(f"- {v.vendor_id}: {v.vendor_name}" + (f" | Services: {svc_text}" if svc_text else ""))
    return "\n".join(lines) if lines else "(none)"


def _parse_llm_json(text: str) -> list[dict]:
    """Parse JSON from LLM response, stripping markdown fences if present."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Remove opening fence (```json or ```)
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[: -3]
    return json.loads(cleaned.strip())


def _call_llm_for_vendors(
    descriptions: list[str], known_vendors_text: str
) -> list[dict]:
    """Call the Anthropic API to resolve vendor info for uncached descriptions."""
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    user_content = (
        "Known vendors and services:\n"
        f"{known_vendors_text}\n\n"
        "Transaction descriptions to resolve:\n"
        + "\n".join(f"{i+1}. {d}" for i, d in enumerate(descriptions))
    )

    response = client.messages.create(
        model=LLM_MODEL,
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    return _parse_llm_json(response.content[0].text)


def _ensure_vendor(db: Session, vendor_id: str, vendor_name: str) -> Vendor:
    """Return existing vendor or create a new one with status='pending_confirmation'."""
    vendor = db.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        vendor = Vendor(
            vendor_id=vendor_id,
            vendor_name=vendor_name,
            status="pending_confirmation",
        )
        db.add(vendor)
        db.flush()
    return vendor


def _ensure_service(
    db: Session, service_id: str, service_name: str, vendor_id: str
) -> VendorService:
    """Return existing service or create a new one."""
    svc = db.query(VendorService).filter(VendorService.service_id == service_id).first()
    if not svc:
        svc = VendorService(
            service_id=service_id,
            vendor_id=vendor_id,
            service_name=service_name,
            status="pending_confirmation",
        )
        db.add(svc)
        db.flush()
    return svc


def resolve_vendors(
    db: Session, raw_descriptions: list[str]
) -> dict[str, dict[str, Any]]:
    """
    Resolve vendor information for a list of raw transaction descriptions.

    Returns a dict keyed by normalised description pattern, each value containing:
        vendor_id, service_id, city, state, country
    """
    if not raw_descriptions:
        return {}

    # 1. Cache lookup -------------------------------------------------------
    cache_results = bulk_lookup(db, raw_descriptions)
    resolved: dict[str, dict[str, Any]] = {}
    uncached_patterns: list[str] = []

    for pattern, mapping in cache_results.items():
        if mapping:
            resolved[pattern] = {
                "vendor_id": mapping.vendor_id,
                "service_id": mapping.service_id,
                "city": mapping.city,
                "state": mapping.state,
                "country": mapping.country,
            }
        else:
            uncached_patterns.append(pattern)

    if not uncached_patterns:
        return resolved

    # 2. LLM fallback for uncached descriptions (batched) -------------------
    BATCH_SIZE = 40
    logger.info("Calling LLM to resolve %d uncached descriptions", len(uncached_patterns))
    known_vendors_text = _build_known_vendors_text(db)

    llm_results: list[dict] = []
    for batch_start in range(0, len(uncached_patterns), BATCH_SIZE):
        batch = uncached_patterns[batch_start : batch_start + BATCH_SIZE]
        batch_results = _call_llm_for_vendors(batch, known_vendors_text)
        llm_results.extend(batch_results)

    # 3. Persist new vendors, services, and cache entries -------------------
    for item in llm_results:
        vendor_id = item["vendor_id"]
        vendor_name = item.get("vendor_name", vendor_id)
        service_id = item.get("service_id")
        service_name = item.get("service_name")

        # Ensure vendor exists
        if item.get("is_new_vendor", False):
            _ensure_vendor(db, vendor_id, vendor_name)
        else:
            # Even for known vendors, ensure it exists (defensive)
            _ensure_vendor(db, vendor_id, vendor_name)

        # Ensure service exists
        if service_id:
            if item.get("is_new_service", False):
                _ensure_service(db, service_id, service_name or service_id, vendor_id)
            else:
                _ensure_service(db, service_id, service_name or service_id, vendor_id)

        # Cache the mapping
        pattern = normalise_pattern(item["description_pattern"])
        upsert(
            db,
            item["description_pattern"],
            vendor_id=vendor_id,
            service_id=service_id,
            city=item.get("city"),
            state=item.get("state"),
            country=item.get("country"),
        )

        resolved[pattern] = {
            "vendor_id": vendor_id,
            "service_id": service_id,
            "city": item.get("city"),
            "state": item.get("state"),
            "country": item.get("country"),
        }

    db.flush()
    return resolved
