"""
Product Ranker Agent.

Ranks already-returned shopping candidates against the stylist's OutfitPlan.

Responsibilities:
- Does NOT search for products.
- Does NOT call MCP.
- Does NOT call an LLM.
- Does NOT modify the catalog.
- Ranks only products that already exist in product_candidates.
- Selects at most one product for each outfit item.
- Prevents the same product from being selected for multiple outfit items.
- Understands common category aliases such as:
    Top -> tops
    Bottom -> pants
    Shoes -> shoes
    Bag -> bags
    Jewelry -> accessories
- Includes both OutfitPlan.items and OutfitPlan.accessories.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from backend.agents.state import AgentState
from backend.shopping.taxonomy import (
    CATEGORY_ALIASES,
    MATCH_EXACT,
    MATCH_FAMILY,
    color_match_level,
)

logger = logging.getLogger(__name__)


class ProductRankerError(Exception):
    """Raised when product ranking cannot be completed."""


# ---------------------------------------------------------------------------
# Category normalization
# ---------------------------------------------------------------------------

# Single shared vocabulary -- see backend/shopping/taxonomy.py.
_CATEGORY_ALIASES: Dict[str, str] = CATEGORY_ALIASES


def _normalize_text(value: Any) -> str:
    """Convert a value to normalized lowercase text."""
    if value is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value).strip().lower(),
    )


def _normalize_category(value: Any) -> str:
    """
    Normalize product/outfit categories.

    Examples:
        Top -> tops
        Bottom -> pants
        Shoes -> shoes
        Clutch -> bags
    """
    text = _normalize_text(value)

    if not text:
        return ""

    if text in _CATEGORY_ALIASES:
        return _CATEGORY_ALIASES[text]

    # Handle phrases such as:
    # "embroidered top"
    # "high waisted pants"
    # "gold clutch"
    words = re.findall(r"[a-z0-9-]+", text)

    resolved: Optional[str] = None

    for word in words:
        if word in _CATEGORY_ALIASES:
            resolved = _CATEGORY_ALIASES[word]

    return resolved or text


def _normalize_color(value: Any) -> str:
    """Normalize common color spellings."""
    value = _normalize_text(value)

    aliases = {
        "gray": "grey",
        "grey": "grey",
        "off white": "off-white",
        "offwhite": "off-white",
        "navy blue": "navy",
        "navy": "navy",
    }

    return aliases.get(value, value)


# ---------------------------------------------------------------------------
# Basic candidate helpers
# ---------------------------------------------------------------------------

def _number(
    value: Any,
    default: float = 0.0,
) -> float:
    """Safely convert a value to float."""
    if value is None:
        return default

    if isinstance(value, bool):
        return default

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _candidate_category(candidate: Dict[str, Any]) -> str:
    return _normalize_category(
        candidate.get("category")
        or candidate.get("product_type")
        or candidate.get("type")
    )


def _categories_compatible(required: str, candidate: str) -> bool:
    """Return whether two normalized categories describe the same item class."""
    if not required or not candidate:
        return False
    if required == candidate:
        return True

    compatible_groups = (
        {"tops", "shirts", "t-shirts"},
        {"pants", "jeans", "skirts"},
    )
    if any(required in group and candidate in group for group in compatible_groups):
        return True

    accessory_categories = {"accessories", "bags", "watches", "sunglasses"}
    return (
        required == "accessories" and candidate in accessory_categories
    ) or (
        candidate == "accessories" and required in accessory_categories
    )


def _is_available(candidate: Dict[str, Any]) -> bool:
    """Treat explicit out-of-stock values as unavailable; absent status is unknown/usable."""
    value = candidate.get("availability", candidate.get("in_stock", True))
    if value is False or value == 0:
        return False
    if isinstance(value, str):
        return value.strip().lower() not in {
            "false",
            "0",
            "no",
            "unavailable",
            "out of stock",
            "sold out",
        }
    return True


def _candidate_color(candidate: Dict[str, Any]) -> str:
    return _normalize_color(
        candidate.get("color")
        or candidate.get("colour")
    )


def _candidate_price(candidate: Dict[str, Any]) -> float:
    """
    Get product price.

    Supports common product schemas.
    """
    for key in (
        "price",
        "sale_price",
        "amount",
    ):
        value = candidate.get(key)

        if value is not None:
            return _number(value)

    return 0.0


def _candidate_rating(candidate: Dict[str, Any]) -> float:
    return _number(
        candidate.get("rating")
        or candidate.get("review_rating")
    )


def _candidate_text(candidate: Dict[str, Any]) -> str:
    """
    Build searchable product text.
    """
    fields = [
        candidate.get("name"),
        candidate.get("title"),
        candidate.get("description"),
        candidate.get("brand"),
        candidate.get("category"),
        candidate.get("color"),
    ]

    return _normalize_text(
        " ".join(
            str(value)
            for value in fields
            if value
        )
    )


# ---------------------------------------------------------------------------
# Outfit helpers
# ---------------------------------------------------------------------------

def _get_budget(
    outfit_plan: Dict[str, Any],
) -> Optional[float]:
    """
    Read budget from OutfitPlan.

    Supports:
        {"budget": 5000}

    and:
        {"requirements": {"budget": 5000}}
    """
    direct_budget = outfit_plan.get("budget")

    if direct_budget is not None:
        budget = _number(direct_budget)

        if budget > 0:
            return budget

    requirements = outfit_plan.get("requirements")

    if isinstance(requirements, dict):
        budget = requirements.get("budget")

        if budget is not None:
            value = _number(budget)

            if value > 0:
                return value

    return None


def _get_required_items(
    outfit_plan: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Return both regular outfit items and accessories.

    Accessories are appended after normal items while preserving
    their original order inside each list.
    """
    result: List[Dict[str, Any]] = []

    items = outfit_plan.get("items")

    if isinstance(items, list):
        result.extend(
            item
            for item in items
            if isinstance(item, dict)
        )

    accessories = outfit_plan.get("accessories")

    if isinstance(accessories, list):
        result.extend(
            item
            for item in accessories
            if isinstance(item, dict)
        )

    return result


def _required_category(
    item: Dict[str, Any],
) -> str:
    """
    Resolve stylist category.

    Uses category first, then item/type/item_type.
    """
    category = (
        item.get("category")
        or item.get("type")
        or item.get("item_type")
    )

    resolved = _normalize_category(category)

    if resolved:
        return resolved

    # Fallback to the actual item description.
    return _normalize_category(
        item.get("item")
        or item.get("name")
    )


def _required_color(
    item: Dict[str, Any],
) -> str:
    return _normalize_color(
        item.get("color")
        or item.get("colour")
    )


def _required_keywords(
    item: Dict[str, Any],
) -> List[str]:
    """
    Extract useful words from the stylist item.

    Example:
        "Embroidered teal kurti with subtle gold threadwork"

    returns useful searchable terms such as:
        embroidered, teal, kurti, gold, threadwork
    """
    text = _normalize_text(
        " ".join(
            str(item.get(key, ""))
            for key in (
                "name",
                "item",
                "description",
                "style",
                "silhouette",
                "color",
                "category",
                "notes",
            )
        )
    )

    if not text:
        return []

    stop_words = {
        "the",
        "a",
        "an",
        "for",
        "with",
        "and",
        "or",
        "of",
        "to",
        "in",
        "on",
        "is",
        "item",
        "piece",
        "adds",
        "add",
        "wear",
        "worn",
        "style",
        "styles",
    }

    words = re.findall(
        r"[a-z0-9-]+",
        text,
    )

    return [
        word
        for word in words
        if word not in stop_words
        and len(word) > 2
    ]


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_product(
    candidate: Dict[str, Any],
    outfit_item: Dict[str, Any],
    budget_remaining: Optional[float] = None,
) -> float:
    """
    Calculate deterministic product compatibility.

    Scoring:
        Category      : strongest
        Color         : strong
        Keywords      : medium
        Rating        : small
        Budget        : strong
    """
    score = 0.0

    candidate_category = _candidate_category(candidate)
    required_category = _required_category(outfit_item)

    # -----------------------------------------------------------------------
    # Category
    # -----------------------------------------------------------------------

    if required_category:
        if candidate_category == required_category:
            score += 50

        elif _categories_compatible(required_category, candidate_category):
            score += 40

        else:
            # Strong penalty for wrong category.
            score -= 45

    # -----------------------------------------------------------------------
    # Color
    # -----------------------------------------------------------------------

    candidate_color = _candidate_color(candidate)
    required_color = _required_color(outfit_item)

    if required_color:
        color_level = color_match_level(required_color, candidate_color)

        if candidate_color == required_color or color_level == MATCH_EXACT:
            score += 25

        elif color_level == MATCH_FAMILY:
            # Same colour family, different shade
            # (emerald green ~ green, soft gold ~ gold).
            score += 15

        elif (
            required_color in candidate_color
            or candidate_color in required_color
        ):
            score += 10

        else:
            score -= 8

    # -----------------------------------------------------------------------
    # Keywords
    # -----------------------------------------------------------------------

    candidate_text = _candidate_text(candidate)
    keywords = _required_keywords(outfit_item)

    if keywords:
        matched = sum(
            1
            for keyword in keywords
            if keyword in candidate_text
        )

        score += min(
            matched * 3,
            18,
        )

    # -----------------------------------------------------------------------
    # Rating
    # -----------------------------------------------------------------------

    rating = _candidate_rating(candidate)

    if rating > 0:
        score += min(
            rating,
            5.0,
        ) * 2

    # -----------------------------------------------------------------------
    # Budget
    # -----------------------------------------------------------------------

    price = _candidate_price(candidate)

    if budget_remaining is not None and price > 0:
        if price <= budget_remaining:
            score += 12

            if price <= budget_remaining * 0.75:
                score += 3
        else:
            score -= 40

    return round(score, 4)


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------

def rank_products(
    candidates: List[Dict[str, Any]],
    outfit_item: Dict[str, Any],
    budget_remaining: Optional[float] = None,
    exclude_product_ids: Optional[set[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Rank existing candidates for one outfit item.

    No products are created.

    Products already selected for another outfit item can be excluded.
    """
    excluded = exclude_product_ids or set()

    scored: List[Dict[str, Any]] = []

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue

        product_id = candidate.get("product_id")

        if not product_id:
            continue

        if product_id in excluded:
            continue

        result = dict(candidate)

        result["rank_score"] = score_product(
            candidate,
            outfit_item,
            budget_remaining,
        )

        scored.append(result)

    scored.sort(
        key=lambda product: (
            _number(
                product.get("rank_score")
            ),
            _candidate_rating(product),
            -_candidate_price(product),
        ),
        reverse=True,
    )

    return scored


# ---------------------------------------------------------------------------
# Main selector
# ---------------------------------------------------------------------------

def select_products(
    product_candidates: List[Dict[str, Any]],
    outfit_plan: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Select at most one real product for every outfit item.

    Important protections:
    - category matching is normalized
    - accessories are included
    - same product cannot be selected twice
    - global budget is respected as much as possible
    - only real candidates are selected
    """
    if not isinstance(product_candidates, list):
        raise ProductRankerError(
            "product_candidates must be a list."
        )

    if not isinstance(outfit_plan, dict):
        raise ProductRankerError(
            "outfit_plan must be a dictionary."
        )

    outfit_items = _get_required_items(
        outfit_plan
    )

    if not outfit_items:
        logger.warning(
            "OutfitPlan contains no items."
        )
        return []

    budget = _get_budget(outfit_plan)
    remaining_budget = budget

    selected: List[Dict[str, Any]] = []
    selected_product_ids: set[str] = set()

    # -----------------------------------------------------------------------
    # -----------------------------------------------------------------------
    # Process every outfit item.
    # -----------------------------------------------------------------------

    # Per-item candidate pools (category-compatible, available, priced),
    # built up-front so each item can see what the LATER items will cost.
    has_item_scopes = any(
        isinstance(candidate, dict) and "item_index" in candidate
        for candidate in product_candidates
    )

    def _pool(index: int, outfit_item: Dict[str, Any]) -> List[Dict[str, Any]]:
        required_category = _required_category(outfit_item)

        if has_item_scopes:
            # Per-item search results retain their source outfit index.
            # Never borrow a result from another item.
            pool = [
                candidate
                for candidate in product_candidates
                if isinstance(candidate, dict)
                and str(candidate.get("item_index")) == str(index)
            ]
        else:
            # Legacy flat candidate lists are safe only when the category is
            # explicitly compatible.
            pool = [
                candidate
                for candidate in product_candidates
                if isinstance(candidate, dict)
            ]

        return [
            candidate
            for candidate in pool
            if candidate.get("product_id")
            and _is_available(candidate)
            and _categories_compatible(
                required_category,
                _candidate_category(candidate),
            )
        ]

    pools = [_pool(i, item) for i, item in enumerate(outfit_items)]

    def _cheapest(pool: List[Dict[str, Any]]) -> Optional[float]:
        prices = [
            _candidate_price(candidate)
            for candidate in pool
            if _candidate_price(candidate) > 0
        ]
        return min(prices) if prices else None

    for index, outfit_item in enumerate(outfit_items):
        candidates = pools[index]

        # Budget: an item may only spend what is left AFTER reserving the
        # cheapest real product for every later item.  Without this, the
        # first items could use the whole budget (every search is capped at
        # the full outfit budget) and the outfit would end up over budget
        # or incomplete.  If even that reserve cannot be honoured, fall back
        # to the plain remaining budget (best effort).
        item_budget = remaining_budget

        if remaining_budget is not None:
            reserve = sum(
                price
                for price in (_cheapest(pool) for pool in pools[index + 1:])
                if price is not None
            )
            cheapest_here = _cheapest(candidates)

            if cheapest_here is not None and remaining_budget - reserve >= cheapest_here:
                item_budget = remaining_budget - reserve

            candidates = [
                candidate
                for candidate in candidates
                if 0 < _candidate_price(candidate) <= item_budget
            ]

        ranked = rank_products(
            candidates,
            outfit_item,
            item_budget,
            exclude_product_ids=selected_product_ids,
        )

        if not ranked:
            logger.warning(
                "No valid product found for outfit item %d: %s",
                index,
                outfit_item,
            )
            continue

        selected_product = dict(
            ranked[0]
        )

        product_id = selected_product.get(
            "product_id"
        )

        if not product_id:
            continue

        # Extra duplicate protection.
        if product_id in selected_product_ids:
            continue

        selected_product_ids.add(
            product_id
        )

        selected_product["item_index"] = index

        # Preserve stylist category if candidate has no category.
        if not selected_product.get("category"):
            selected_product["category"] = (
                outfit_item.get("category")
                or outfit_item.get("type")
                or outfit_item.get("item_type")
            )

        selected.append(
            selected_product
        )

        # Update remaining budget.
        price = _candidate_price(
            selected_product
        )

        if (
            remaining_budget is not None
            and price > 0
        ):
            remaining_budget -= price

    return selected


# ---------------------------------------------------------------------------
# Workflow entry point
# ---------------------------------------------------------------------------

def product_ranker_agent(
    state: AgentState,
) -> AgentState:
    """
    Workflow-facing Product Ranker.

    Reads:
        state["product_candidates"]
        state["outfit_plan"]

    Writes:
        state["selected_products"]
    """
    product_candidates = (
        state.get("product_candidates")
        or []
    )

    outfit_plan = (
        state.get("outfit_plan")
        or {}
    )

    try:
        selected = select_products(
            product_candidates,
            outfit_plan,
        )

    except ProductRankerError:
        raise

    except Exception as exc:
        logger.exception(
            "Product Ranker failed."
        )

        raise ProductRankerError(
            f"Product Ranker failed: {exc}"
        ) from exc

    state["selected_products"] = selected

    logger.info(
        "Product Ranker selected %d product(s) from %d candidate(s).",
        len(selected),
        len(product_candidates),
    )

    return state


# Alias used by some workflow code.
ranker_agent = product_ranker_agent


# ---------------------------------------------------------------------------
# Local test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    sample_state: AgentState = {
        "user_profile": {},
        "user_query": (
            "Indoor wedding under ₹5,000"
        ),
        "style_context": {},
        "rag_context": [],
        "outfit_plan": {
            "occasion": "indoor wedding",
            "formality": "semi-formal",
            "budget": 5000,
            "items": [
                {
                    "category": "Top",
                    "item": (
                        "Embroidered teal kurti "
                        "with subtle gold threadwork"
                    ),
                    "color": "teal",
                },
                {
                    "category": "Bottom",
                    "item": (
                        "High-waisted beige "
                        "palazzo pants"
                    ),
                    "color": "beige",
                },
                {
                    "category": "Footwear",
                    "item": (
                        "Nude block-heel juttis"
                    ),
                    "color": "nude",
                },
            ],
            "accessories": [
                {
                    "category": "Jewelry",
                    "item": (
                        "Gold statement hoop earrings"
                    ),
                    "color": "gold",
                },
                {
                    "category": "Bag",
                    "item": (
                        "Compact gold clutch"
                    ),
                    "color": "gold",
                },
            ],
        },
        "product_candidates": [
            {
                "product_id": "top-001",
                "category": "tops",
                "title": "Teal Embroidered Kurti",
                "color": "teal",
                "price": 1999,
                "rating": 4.5,
            },
            {
                "product_id": "pants-001",
                "category": "pants",
                "title": "Beige Wide Leg Pants",
                "color": "beige",
                "price": 1399,
                "rating": 4.4,
            },
            {
                "product_id": "shoe-001",
                "category": "shoes",
                "title": "Nude Block Heel Juttis",
                "color": "nude",
                "price": 899,
                "rating": 4.3,
            },
            {
                "product_id": "earring-001",
                "category": "accessories",
                "title": "Gold Statement Hoop Earrings",
                "color": "gold",
                "price": 499,
                "rating": 4.5,
            },
            {
                "product_id": "bag-001",
                "category": "bags",
                "title": "Gold Sequin Clutch",
                "color": "gold",
                "price": 799,
                "rating": 4.4,
            },
        ],
        "selected_products": [],
        "fitting_room": {},
        "critic_feedback": {},
        "iteration": 0,
        "status": "running",
    }

    updated = product_ranker_agent(
        sample_state
    )

    print(
        json.dumps(
            updated["selected_products"],
            indent=4,
            ensure_ascii=False,
        )
    )