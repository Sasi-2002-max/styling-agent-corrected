"""
Shared fashion vocabulary (single source of truth).

Used by:
    backend/agents/shopping_agent.py     (stylist item -> catalog category)
    backend/agents/product_ranker.py     (category + colour scoring)
    backend/shopping/product_ranker.py   (colour scoring)
    backend/agents/critic_agent.py       (palette / accent-colour checks)

Why this file exists
--------------------
The Stylist writes natural language ("emerald green", "soft gold", "Top",
"Footwear", "kurti").  The catalog uses a small fixed vocabulary
("green", "gold", "tops", "shoes").  Matching must therefore happen in ONE
place, deterministically (no LLM), instead of being re-implemented (and
drifting apart) inside every agent.

Pure Python: no pydantic, no MCP, no network.
"""

from __future__ import annotations

import re
from typing import Dict, FrozenSet, Optional

# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------
# Canonical catalog categories (what products.json / Product.category use):
#   tops, shirts, t-shirts, pants, jeans, skirts, dresses,
#   shoes, watches, sunglasses, bags, accessories

CATEGORY_ALIASES: Dict[str, str] = {
    # t-shirts
    "t-shirt": "t-shirts",
    "tshirt": "t-shirts",
    "t-shirts": "t-shirts",
    "tee": "t-shirts",
    "tees": "t-shirts",
    # shirts
    "shirt": "shirts",
    "shirts": "shirts",
    # tops (incl. Indian wear tops)
    "top": "tops",
    "tops": "tops",
    "blouse": "tops",
    "blouses": "tops",
    "kurti": "tops",
    "kurtis": "tops",
    "kurta": "tops",
    "kurtas": "tops",
    "tunic": "tops",
    "tunics": "tops",
    "camisole": "tops",
    # bottoms
    "trouser": "pants",
    "trousers": "pants",
    "pant": "pants",
    "pants": "pants",
    "bottom": "pants",
    "bottoms": "pants",
    "chino": "pants",
    "chinos": "pants",
    "palazzo": "pants",
    "palazzos": "pants",
    "culotte": "pants",
    "culottes": "pants",
    "legging": "pants",
    "leggings": "pants",
    "salwar": "pants",
    "churidar": "pants",
    "jean": "jeans",
    "jeans": "jeans",
    "skirt": "skirts",
    "skirts": "skirts",
    # dresses
    "dress": "dresses",
    "dresses": "dresses",
    # shoes
    "shoe": "shoes",
    "shoes": "shoes",
    "footwear": "shoes",
    "heel": "shoes",
    "heels": "shoes",
    "sandal": "shoes",
    "sandals": "shoes",
    "sneaker": "shoes",
    "sneakers": "shoes",
    "loafer": "shoes",
    "loafers": "shoes",
    "boot": "shoes",
    "boots": "shoes",
    "jutti": "shoes",
    "juttis": "shoes",
    "mojari": "shoes",
    "mojaris": "shoes",
    "kolhapuri": "shoes",
    "kolhapuris": "shoes",
    "stiletto": "shoes",
    "stilettos": "shoes",
    "wedges": "shoes",
    # watches / sunglasses
    "watch": "watches",
    "watches": "watches",
    "sunglass": "sunglasses",
    "sunglasses": "sunglasses",
    # bags
    "bag": "bags",
    "bags": "bags",
    "handbag": "bags",
    "handbags": "bags",
    "clutch": "bags",
    "clutches": "bags",
    "purse": "bags",
    "purses": "bags",
    "tote": "bags",
    "potli": "bags",
    # accessories / jewellery
    "accessory": "accessories",
    "accessories": "accessories",
    "jewelry": "accessories",
    "jewellery": "accessories",
    "earring": "accessories",
    "earrings": "accessories",
    "jhumka": "accessories",
    "jhumkas": "accessories",
    "jhumki": "accessories",
    "jhumkis": "accessories",
    "chandbali": "accessories",
    "chandbalis": "accessories",
    "necklace": "accessories",
    "necklaces": "accessories",
    "pendant": "accessories",
    "choker": "accessories",
    "bracelet": "accessories",
    "bracelets": "accessories",
    "bangle": "accessories",
    "bangles": "accessories",
    "ring": "accessories",
    "rings": "accessories",
}

# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------
# Each family is a set of shade names.  Two colours are "compatible" when they
# belong to the same family (emerald green ~ green ~ forest green).

COLOR_FAMILIES: Dict[str, FrozenSet[str]] = {
    "black": frozenset({"black", "jet black"}),
    "white": frozenset({"white", "off-white", "off white", "offwhite"}),
    "cream": frozenset(
        {"cream", "ivory", "beige", "nude", "champagne", "sand", "oatmeal", "off-cream"}
    ),
    "grey": frozenset({"grey", "gray", "charcoal", "slate", "ash"}),
    "brown": frozenset(
        {"brown", "tan", "camel", "chocolate", "coffee", "mocha", "tortoise", "khaki"}
    ),
    "navy": frozenset({"navy", "navy blue", "midnight blue", "midnight"}),
    "blue": frozenset(
        {
            "blue", "royal blue", "sky blue", "light blue", "cobalt", "cobalt blue",
            "powder blue", "denim", "indigo", "mid blue", "baby blue",
        }
    ),
    "green": frozenset(
        {
            "green", "emerald", "emerald green", "forest green", "dark green",
            "bottle green", "olive", "olive green", "sage", "sage green", "mint",
            "mint green", "army green", "hunter green",
        }
    ),
    "teal": frozenset({"teal", "turquoise", "aqua", "peacock blue", "peacock green"}),
    "red": frozenset({"red", "crimson", "scarlet", "ruby", "cherry", "tomato red"}),
    "burgundy": frozenset(
        {"maroon", "burgundy", "deep burgundy", "wine", "oxblood", "claret", "merlot"}
    ),
    "pink": frozenset(
        {
            "pink", "blush", "blush pink", "baby pink", "dusty pink", "hot pink",
            "rose", "dusty rose", "fuchsia", "magenta", "rani pink",
        }
    ),
    "orange": frozenset({"orange", "coral", "peach", "rust", "terracotta", "burnt orange"}),
    "yellow": frozenset({"yellow", "mustard", "lemon", "lemon yellow"}),
    "purple": frozenset(
        {"purple", "lavender", "lilac", "violet", "mauve", "plum", "aubergine"}
    ),
    "gold": frozenset(
        {
            "gold", "golden", "soft gold", "light gold", "antique gold",
            "rose gold", "metallic gold",
        }
    ),
    "silver": frozenset({"silver", "metallic silver", "platinum", "gunmetal"}),
}

# Families that read as neutrals when judging "too many accent colours".
NEUTRAL_FAMILIES: FrozenSet[str] = frozenset(
    {"black", "white", "cream", "grey", "brown", "navy", "silver", "gold"}
)

_SHADE_TO_FAMILY: Dict[str, str] = {
    shade: family for family, shades in COLOR_FAMILIES.items() for shade in shades
}

_WS = re.compile(r"\s+")

MATCH_EXACT = "exact"
MATCH_FAMILY = "family"
MATCH_NONE = "none"


def clean_color(value: object) -> str:
    """Lower-case, trim and collapse whitespace.  Non-strings give ''."""
    if not isinstance(value, str):
        return ""
    return _WS.sub(" ", value.replace("\u2011", "-").strip().lower())


def color_family(value: object) -> Optional[str]:
    """
    Family name for a colour string, or None when it is not recognised.

        "emerald green" -> "green"      "soft gold"   -> "gold"
        "deep burgundy" -> "burgundy"   "Navy Blue"   -> "navy"
        "dark green"    -> "green"      "charcoal"    -> "grey"

    Multi-word descriptions are resolved by their longest known shade
    phrase ("light emerald green" -> "green").
    """
    cleaned = clean_color(value)
    if not cleaned:
        return None
    if cleaned in _SHADE_TO_FAMILY:
        return _SHADE_TO_FAMILY[cleaned]

    best: Optional[str] = None
    best_len = 0
    for shade, family in _SHADE_TO_FAMILY.items():
        if len(shade) > best_len and re.search(rf"\b{re.escape(shade)}\b", cleaned):
            best, best_len = family, len(shade)
    return best


def color_match_level(wanted: object, actual: object) -> str:
    """
    "exact"  same colour text            (gold == gold)
    "family" different shade, same family (emerald green ~ green, gold ~ soft gold)
    "none"   different families, or either colour unknown / missing
    """
    a, b = clean_color(wanted), clean_color(actual)
    if not a or not b:
        return MATCH_NONE
    if a == b:
        return MATCH_EXACT
    family_a, family_b = color_family(a), color_family(b)
    if family_a is not None and family_a == family_b:
        return MATCH_FAMILY
    return MATCH_NONE


def colors_compatible(wanted: object, actual: object) -> bool:
    return color_match_level(wanted, actual) != MATCH_NONE
