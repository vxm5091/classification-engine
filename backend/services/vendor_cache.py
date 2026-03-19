"""
description_vendor_map CRUD operations.

Provides cache lookup and insertion for the description-to-vendor mapping table.
Pattern normalisation: uppercase, strip trailing whitespace, collapse multiple spaces.
"""

import re
from typing import Optional

from sqlalchemy.orm import Session

from backend.models import DescriptionVendorMap


def normalise_pattern(raw: str) -> str:
    """Normalise a raw transaction description into a canonical pattern."""
    pattern = raw.upper().strip()
    pattern = re.sub(r"\s+", " ", pattern)
    return pattern


def lookup(db: Session, raw_description: str) -> Optional[DescriptionVendorMap]:
    """Return the cached mapping for a description, or None if not cached."""
    pattern = normalise_pattern(raw_description)
    return (
        db.query(DescriptionVendorMap)
        .filter(DescriptionVendorMap.description_pattern == pattern)
        .first()
    )


def bulk_lookup(
    db: Session, raw_descriptions: list[str]
) -> dict[str, Optional[DescriptionVendorMap]]:
    """Look up many descriptions at once. Returns {normalised_pattern: mapping_or_None}."""
    patterns = list({normalise_pattern(d) for d in raw_descriptions})
    existing = (
        db.query(DescriptionVendorMap)
        .filter(DescriptionVendorMap.description_pattern.in_(patterns))
        .all()
    )
    by_pattern = {m.description_pattern: m for m in existing}
    return {p: by_pattern.get(p) for p in patterns}


def upsert(
    db: Session,
    raw_description: str,
    vendor_id: str,
    service_id: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    country: Optional[str] = None,
) -> DescriptionVendorMap:
    """Insert or update a description-to-vendor mapping."""
    pattern = normalise_pattern(raw_description)
    mapping = (
        db.query(DescriptionVendorMap)
        .filter(DescriptionVendorMap.description_pattern == pattern)
        .first()
    )
    if mapping:
        mapping.vendor_id = vendor_id
        mapping.service_id = service_id
        mapping.city = city
        mapping.state = state
        mapping.country = country
    else:
        mapping = DescriptionVendorMap(
            description_pattern=pattern,
            vendor_id=vendor_id,
            service_id=service_id,
            city=city,
            state=state,
            country=country,
        )
        db.add(mapping)
    db.flush()
    return mapping
