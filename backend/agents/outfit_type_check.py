"""Small, deterministic checks for culturally specific garment types.

The shopping catalog uses broad categories such as ``dresses``.  The
stylist's item description still carries the more specific request (for
example, Anarkali), so the critic compares that description with the selected
product title instead of treating every dress as interchangeable.
"""

from __future__ import annotations

import re
from typing import Any, Optional


_REQUESTED_TYPES = (
    ("anarkali", re.compile(r"\banarkali\b", re.IGNORECASE)),
    ("saree", re.compile(r"\b(saree|sari)\b", re.IGNORECASE)),
    ("lehenga", re.compile(r"\b(lehenga|lehnga)\b", re.IGNORECASE)),
    (
        "salwar suit",
        re.compile(r"\b(salwar\s+(suit|kameez)|suit\s+set)\b", re.IGNORECASE),
    ),
    ("sharara", re.compile(r"\bsharara\b", re.IGNORECASE)),
    ("jumpsuit", re.compile(r"\bjumpsuit\b", re.IGNORECASE)),
    (
        "western dress",
        re.compile(
            r"\b(western\s+dress|midi\s+dress|fit[- ]and[- ]flare\s+dress)\b",
            re.IGNORECASE,
        ),
    ),
)

_ETHNIC_MARKERS = re.compile(
    r"\b(anarkali|saree|sari|lehenga|lehnga|salwar|kameez|sharara)\b",
    re.IGNORECASE,
)

_PRODUCT_MARKERS = {
    "anarkali": re.compile(r"\banarkali\b", re.IGNORECASE),
    "saree": re.compile(r"\b(saree|sari)\b", re.IGNORECASE),
    "lehenga": re.compile(r"\b(lehenga|lehnga)\b", re.IGNORECASE),
    "salwar suit": re.compile(
        r"\b(salwar\s+(suit|kameez)|suit\s+set)\b", re.IGNORECASE
    ),
    "sharara": re.compile(r"\bsharara\b", re.IGNORECASE),
    "jumpsuit": re.compile(r"\bjumpsuit\b", re.IGNORECASE),
    "western dress": re.compile(r"\b(dress|gown)\b", re.IGNORECASE),
}


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return " ".join(
            str(value.get(key) or "")
            for key in ("category", "item", "style", "notes", "name")
        ).strip()
    return ""


def requested_garment_type(item: Any) -> Optional[str]:
    """Return a specific one-piece garment type explicitly named by the stylist."""
    description = _text(item)
    for garment_type, pattern in _REQUESTED_TYPES:
        if pattern.search(description):
            return garment_type
    return None


def product_matches_garment_type(product: Any, garment_type: str) -> bool:
    """Require the selected product itself to identify the requested garment."""
    if not isinstance(product, dict):
        return False
    product_text = " ".join(
        str(product.get(key) or "")
        for key in ("title", "category", "product_type", "type")
    )
    matcher = _PRODUCT_MARKERS.get(garment_type)
    if matcher is None:
        return False
    if not matcher.search(product_text):
        return False
    if garment_type == "western dress":
        return not product_is_ethnic_wear(product)
    return True


def product_is_ethnic_wear(product: Any) -> bool:
    if not isinstance(product, dict):
        return False
    title = str(product.get("title") or "")
    return bool(_ETHNIC_MARKERS.search(title))