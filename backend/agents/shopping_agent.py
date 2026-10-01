"""
Shopping Agent

Application-level interface for fashion product discovery.

Architecture:

    Caller
        |
        v
    ShoppingAgent
        |
        v
    MCPShoppingClient
        |
        v
    MCP shopping tools
        |
        v
    Product data source

Responsibilities:
- Search products through MCPShoppingClient.
- Normalize stylist categories.
- Preserve real product metadata.
- Apply size availability checks when requested.
- Rank products using the deterministic product ranker.
- Build a complete outfit without inventing products.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Union

from backend.schemas.outfit import OutfitItem, OutfitPlan
from backend.shopping.mcp_client import MCPShoppingClient
from backend.shopping.product_normalizer import Product
from backend.shopping.product_ranker import rank_products
from backend.shopping.taxonomy import (
    CATEGORY_ALIASES,
    MATCH_NONE,
    clean_color,
    color_match_level,
)


# ---------------------------------------------------------------------------
# Category vocabulary
# ---------------------------------------------------------------------------

# Single shared vocabulary -- see backend/shopping/taxonomy.py.
# (Top/Shirt/Kurti -> tops, Bottom/Palazzo -> pants, Footwear/Heels -> shoes,
#  Jewellery/Jhumka -> accessories, Clutch -> bags, ...)
_CATEGORY_ALIASES: Dict[str, str] = CATEGORY_ALIASES


SUPPORTED_CATEGORIES = frozenset(_CATEGORY_ALIASES.values())


_GENERIC_CATEGORIES = frozenset(
    {
        "tops",
        "accessories",
    }
)

# The stylist often writes the bare word "Bottom" for jeans, a skirt or
# palazzos.  For those words the item description decides which bottom
# category to search (otherwise "Bottom: blue jeans" would only ever be
# searched as pants).
_GENERIC_BOTTOM_WORDS = frozenset({"bottom", "bottoms"})
_BOTTOM_CATEGORIES = frozenset({"pants", "jeans", "skirts"})


# ---------------------------------------------------------------------------
# Color vocabulary
# ---------------------------------------------------------------------------

_COLOR_VOCABULARY = (
    "black",
    "white",
    "navy",
    "cream",
    "brown",
    "teal",
    "maroon",
    "beige",
    "olive",
    "grey",
    "gray",
    "pink",
    "red",
    "gold",
    "silver",
    "blue",
    "nude",
)


_COLOR_ALIASES: Dict[str, str] = {
    "gray": "grey",
    "navy blue": "navy",
}


_KNOWN_COLORS = frozenset(
    _COLOR_ALIASES.get(color, color)
    for color in _COLOR_VOCABULARY
)


_WORD_PATTERN = re.compile(
    r"[a-z][a-z\-]*",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Natural-language requirement extraction
# ---------------------------------------------------------------------------

_BUDGET_PATTERN = re.compile(
    r"(?:under|below|within|less\s+than|budget\s+of|budget)\s*[₹$]?\s*(\d[\d,]*(?:\.\d+)?)"
    r"|[₹$]\s*(\d[\d,]*(?:\.\d+)?)",
    re.IGNORECASE,
)


_SIZE_PATTERN = re.compile(
    r"\bsize\s*[:\-]?\s*([a-zA-Z0-9]+)\b",
    re.IGNORECASE,
)


def _normalize_size(size: Optional[str]) -> Optional[str]:
    """
    Normalize a requested size.

    Examples:
        "m"  -> "M"
        " M " -> "M"
        "xl" -> "XL"
    """
    if not size:
        return None

    cleaned = str(size).strip()

    if not cleaned:
        return None

    return cleaned.upper()


def _normalize_budget(value: Any) -> Optional[float]:
    """
    Convert a budget value into a positive float.

    Invalid or non-positive budgets become None.
    """
    if value is None:
        return None

    try:
        budget = float(value)
    except (TypeError, ValueError):
        return None

    if budget <= 0:
        return None

    return budget


def extract_requirements(request_text: str) -> Dict[str, Any]:
    """
    Deterministically extract shopping requirements.

    Example:
        "I need a black shirt under ₹1500, size M"

    Returns:
        {
            "query": "...",
            "category": "shirts",
            "color": "black",
            "budget": 1500.0,
            "size": "M",
        }
    """

    text = (request_text or "").strip()
    lowered = text.lower()

    category = _category_from_text(lowered)

    color = None

    # Prefer multi-word color aliases first.
    for color_name in sorted(
        _COLOR_ALIASES.keys(),
        key=len,
        reverse=True,
    ):
        if re.search(
            rf"\b{re.escape(color_name)}\b",
            lowered,
        ):
            color = _COLOR_ALIASES[color_name]
            break

    # Fall back to the normal color vocabulary.
    if color is None:
        for color_name in _COLOR_VOCABULARY:
            if re.search(
                rf"\b{re.escape(color_name)}\b",
                lowered,
            ):
                color = _COLOR_ALIASES.get(
                    color_name,
                    color_name,
                )
                break

    budget: Optional[float] = None

    budget_match = _BUDGET_PATTERN.search(lowered)

    if budget_match:
        raw_amount = budget_match.group(1)

        try:
            budget = float(
                raw_amount.replace(",", "")
            )
        except ValueError:
            budget = None

    size_match = _SIZE_PATTERN.search(lowered)

    size = (
        _normalize_size(size_match.group(1))
        if size_match
        else None
    )

    return {
        "query": text,
        "category": category,
        "color": color,
        "budget": budget,
        "size": size,
    }


# ---------------------------------------------------------------------------
# Stylist item -> catalog category
# ---------------------------------------------------------------------------

def _category_from_text(
    text: Optional[str],
) -> Optional[str]:
    """
    Resolve a catalog category from natural-language text.

    The last recognized category wins.

    Examples:
        "shirt dress" -> dresses
        "black leather shoes" -> shoes
        "casual t-shirt" -> t-shirts
    """

    if not text:
        return None

    lowered = text.lower().strip()

    # Normalize common variations before token matching.
    lowered = re.sub(
        r"\bt[\s\-]*shirts?\b",
        "t-shirt",
        lowered,
    )

    # Multi-word/longer aliases should be checked first.
    aliases = sorted(
        _CATEGORY_ALIASES.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    )

    match: Optional[str] = None

    for alias, canonical in aliases:
        if re.search(
            rf"\b{re.escape(alias)}\b",
            lowered,
        ):
            match = canonical

    # Also inspect individual words so descriptions such as
    # "formal black loafers" continue to work.
    for word in _WORD_PATTERN.findall(lowered):
        canonical = _CATEGORY_ALIASES.get(
            word.strip("-").lower()
        )

        if canonical is not None:
            match = canonical

    return match


def resolve_item_category(
    item: OutfitItem,
) -> Optional[str]:
    """
    Resolve a stylist OutfitItem to a catalog category.

    Category takes priority unless it is a broad bucket such as
    tops/accessories. Then the item description is consulted.
    """

    if (
        str(item.category or "").strip().lower()
        in _GENERIC_BOTTOM_WORDS
    ):
        bottom_from_item = _category_from_text(item.item)

        if bottom_from_item in _BOTTOM_CATEGORIES:
            return bottom_from_item

    from_category = _category_from_text(
        item.category
    )

    if (
        from_category is not None
        and from_category not in _GENERIC_CATEGORIES
    ):
        return from_category

    from_item = _category_from_text(
        item.item
    )

    if from_item is not None:
        return from_item

    return from_category


def normalize_color(
    color: Optional[str],
) -> Optional[str]:
    """
    Return the catalog spelling of a known color.

    No guessing is performed.
    """

    if not color:
        return None

    cleaned = " ".join(
        str(color).lower().split()
    )

    cleaned = _COLOR_ALIASES.get(
        cleaned,
        cleaned,
    )

    if cleaned in _KNOWN_COLORS:
        return cleaned

    return None


# ---------------------------------------------------------------------------
# Search statuses
# ---------------------------------------------------------------------------

STATUS_OK = "ok"
STATUS_NO_RESULTS = "no_results"
STATUS_UNSUPPORTED = "unsupported_category"


# ---------------------------------------------------------------------------
# Outfit statuses
# ---------------------------------------------------------------------------

OUTFIT_COMPLETE = "complete"
OUTFIT_INCOMPLETE = "incomplete"


# ---------------------------------------------------------------------------
# Product helpers
# ---------------------------------------------------------------------------

def _product_to_dict(product: Product) -> Dict[str, Any]:
    """
    Convert a normalized Product into a plain dictionary.

    Supports Pydantic v2 and keeps the normalized product metadata intact.
    """

    if hasattr(product, "model_dump"):
        return product.model_dump()

    if hasattr(product, "dict"):
        return product.dict()

    return dict(product)


def _has_requested_size(
    product: Product,
    requested_size: str,
) -> bool:
    """
    Check whether the normalized product advertises the requested size.
    """

    normalized_requested = _normalize_size(
        requested_size
    )

    if not normalized_requested:
        return True

    for available_size in (
        getattr(product, "sizes", None) or []
    ):
        if (
            _normalize_size(
                str(available_size)
            )
            == normalized_requested
        ):
            return True

    return False


def _safe_price(product: Dict[str, Any]) -> Optional[float]:
    """
    Extract a valid numeric product price.

    Returns None when the product does not contain a usable price.
    """

    value = product.get("price")

    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Complete outfit selection
# ---------------------------------------------------------------------------

def select_outfit(
    candidates: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Select one unique product per outfit item.

    Important:
    - Never select the same product twice.
    - Never invent a product.
    - Preserve outfit item order.
    - Preserve the complete real product metadata.
    - Calculate total price only from real numeric product prices.
    - Missing/invalid prices do not become fake zero-price products.
    """

    selected: List[Dict[str, Any]] = []
    missing: List[Dict[str, Any]] = []

    used_product_ids: set[str] = set()

    total = 0.0
    priced_product_count = 0

    for entry in candidates:
        products = entry.get("products") or []

        if not products:
            missing.append(
                {
                    "index": entry.get("index"),
                    "item": entry.get("item"),
                    "status": entry.get("status"),
                }
            )
            continue

        best: Optional[Dict[str, Any]] = None

        # Pick the first ranked product that has not already
        # been used for another outfit item.
        for product in products:
            product_id = product.get("product_id")

            if not product_id:
                continue

            product_id = str(product_id)

            if product_id in used_product_ids:
                continue

            best = product
            break

        if best is None:
            missing.append(
                {
                    "index": entry.get("index"),
                    "item": entry.get("item"),
                    "status": "no_unique_product",
                }
            )
            continue

        product_id = str(
            best["product_id"]
        )

        used_product_ids.add(product_id)

        # Preserve all product metadata rather than reducing the
        # selected result to product_id/category only.
        selected_product = dict(best)

        selected_product["product_id"] = product_id

        selected_product["item_index"] = entry.get(
            "index"
        )

        selected_product["item_source"] = entry.get(
            "source"
        )

        selected.append(
            selected_product
        )

        price = _safe_price(best)

        if price is not None:
            total += price
            priced_product_count += 1

    is_complete = (
        bool(candidates)
        and len(selected) == len(candidates)
        and not missing
    )

    return {
        "status": (
            OUTFIT_COMPLETE
            if is_complete
            else OUTFIT_INCOMPLETE
        ),
        "selected_products": selected,
        "total_price": round(total, 2),
        "priced_product_count": priced_product_count,
        "missing_items": missing,
    }


# ---------------------------------------------------------------------------
# Shopping Agent
# ---------------------------------------------------------------------------

class ShoppingAgent:
    """
    Application-level shopping agent.

    All shopping data comes through MCPShoppingClient.
    """

    async def _search_with_client(
        self,
        client: Any,
        *,
        query: str = "",
        budget: Optional[float] = None,
        category: Optional[str] = None,
        color: Optional[str] = None,
        size: Optional[str] = None,
        outfit_item: Optional[Dict[str, Any]] = None,
        relax_color: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Search, optionally size-filter, then rank products.

        relax_color=True is used ONLY for stylist-planned outfit items, where
        the colour is a styling preference rather than a hard requirement.
        If nothing matches the exact colour, the search is repeated without
        the colour filter and similar shades of the same colour family are
        preferred (emerald green ~ green, soft gold ~ gold), then any colour
        in the right category.  Explicit user searches (colour switching)
        never relax, so "navy" never silently returns a red product.

        outfit_item is passed to the ranker so the ranker receives
        the complete stylist description rather than only
        category/color.
        """

        normalized_category = (
            _category_from_text(category)
            if category
            else None
        )

        # If a category was explicitly supplied but is unsupported,
        # do not accidentally perform a broad/unfiltered search.
        if category and normalized_category is None:
            return []

        normalized_color = normalize_color(color)

        normalized_size = _normalize_size(size)

        normalized_budget = _normalize_budget(
            budget
        )

        raw_products = await client.search_products(
            query=query or "",
            budget=normalized_budget,
            category=normalized_category,
            color=normalized_color,
        )

        requested_color_text = clean_color(
            (outfit_item or {}).get("color") or normalized_color
        )

        if not raw_products and relax_color and requested_color_text:
            # Exact colour not in stock for this category -> same colour
            # family first, then any colour in the category.  The ranker
            # still orders them by closeness to the requested colour.
            any_color = await client.search_products(
                query=query or "",
                budget=normalized_budget,
                category=normalized_category,
                color=None,
            )
            same_family = [
                raw
                for raw in (any_color or [])
                if isinstance(raw, dict)
                and color_match_level(requested_color_text, raw.get("color"))
                != MATCH_NONE
            ]
            raw_products = same_family or any_color

        if not raw_products:
            return []

        products: List[Product] = []

        for raw_product in raw_products:
            if not raw_product:
                continue

            try:
                product = Product.model_validate(
                    raw_product
                )
            except Exception:
                # MCP data that cannot be normalized is not safe
                # to expose as a real product.
                continue

            if not getattr(
                product,
                "product_id",
                None,
            ):
                continue

            products.append(product)

        if not products:
            return []

        # ---------------------------------------------------------------
        # Size-specific availability
        # ---------------------------------------------------------------

        if normalized_size:
            size_confirmed: List[Product] = []

            for product in products:
                if not _has_requested_size(
                    product,
                    normalized_size,
                ):
                    continue

                availability = (
                    await client.check_availability(
                        product.product_id,
                        size=normalized_size,
                    )
                )

                if not isinstance(
                    availability,
                    dict,
                ):
                    continue

                if (
                    availability.get("available")
                    is True
                ):
                    size_confirmed.append(product)

            products = size_confirmed

        if not products:
            return []

        # ---------------------------------------------------------------
        # Rank
        # ---------------------------------------------------------------

        if outfit_item is None:
            ranking_requirements: Dict[str, Any] = {
                "category": normalized_category,
                "color": normalized_color,
                "budget": normalized_budget,
                "size": normalized_size,
                "query": query,
            }
        else:
            # The stylist writes "Top" / "emerald green"; the ranker compares
            # against catalog values, so give it the normalized category,
            # the stylist's own colour wording (shade-aware matching) and
            # the budget cap that was actually searched.
            ranking_requirements = dict(outfit_item)
            ranking_requirements["category"] = (
                normalized_category or ranking_requirements.get("category")
            )
            ranking_requirements["color"] = (
                requested_color_text or normalized_color
            )
            ranking_requirements["budget"] = normalized_budget

        ranked = rank_products(
            products,
            ranking_requirements,
        )

        return [
            _product_to_dict(product)
            for product in (ranked or [])
        ]

    # -------------------------------------------------------------------
    # Generic search
    # -------------------------------------------------------------------

    async def search(
        self,
        query: str = "",
        budget: Optional[float] = None,
        category: Optional[str] = None,
        color: Optional[str] = None,
        size: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search products matching supplied requirements.
        """

        normalized_category = (
            _category_from_text(category)
            if category
            else None
        )

        if (
            category
            and normalized_category is None
        ):
            return []

        normalized_color = normalize_color(color)

        normalized_size = _normalize_size(size)

        normalized_budget = _normalize_budget(
            budget
        )

        async with MCPShoppingClient() as client:
            return await self._search_with_client(
                client,
                query=query or "",
                budget=normalized_budget,
                category=normalized_category,
                color=normalized_color,
                size=normalized_size,
            )

    # -------------------------------------------------------------------
    # Search complete outfit
    # -------------------------------------------------------------------

    async def search_outfit(
        self,
        outfit_plan: Union[
            OutfitPlan,
            Dict[str, Any],
        ],
        sizes: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search every OutfitPlan item independently.

        Searches:
            plan.items
            plan.accessories

        Each item gets its own MCP search.

        No unfiltered search is performed for unsupported categories.
        """

        plan = (
            outfit_plan
            if isinstance(
                outfit_plan,
                OutfitPlan,
            )
            else OutfitPlan.model_validate(
                outfit_plan
            )
        )

        plan_budget = _normalize_budget(
            plan.budget
        )

        outfit_items = (
            [
                ("items", item)
                for item in plan.items
            ]
            + [
                ("accessories", item)
                for item in plan.accessories
            ]
        )

        size_map = sizes or {}

        entries: List[
            Dict[str, Any]
        ] = []

        for index, (
            source,
            item,
        ) in enumerate(outfit_items):

            category = resolve_item_category(
                item
            )

            color = normalize_color(
                item.color
            )

            requested_size: Optional[str] = None

            if category:
                requested_size = _normalize_size(
                    size_map.get(category)
                )

            # Also support a size keyed by the original stylist
            # item name/category when provided.
            if requested_size is None:
                requested_size = _normalize_size(
                    size_map.get(
                        item.category
                    )
                )

            if requested_size is None:
                requested_size = _normalize_size(
                    size_map.get(
                        item.item
                    )
                )

            entry: Dict[str, Any] = {
                "index": index,
                "source": source,
                "item": item.model_dump(),
                "search_params": None,
                "status": STATUS_UNSUPPORTED,
                "products": [],
            }

            if category is not None:
                entry["search_params"] = {
                    "category": category,
                    "color": color,
                    "budget": plan_budget,
                    "size": requested_size,
                }

            entries.append(entry)

        searchable = [
            entry
            for entry in entries
            if entry["search_params"] is not None
        ]

        if not searchable:
            return entries

        async with MCPShoppingClient() as client:
            for entry in searchable:
                params = entry[
                    "search_params"
                ]

                products = (
                    await self._search_with_client(
                        client,
                        query="",
                        budget=params["budget"],
                        category=params["category"],
                        color=params["color"],
                        size=params["size"],
                        outfit_item=entry["item"],
                        relax_color=True,
                    )
                )

                entry["products"] = products

                entry["status"] = (
                    STATUS_OK
                    if products
                    else STATUS_NO_RESULTS
                )

        return entries

    # -------------------------------------------------------------------
    # Build complete outfit
    # -------------------------------------------------------------------

    async def build_outfit(
        self,
        outfit_plan: Union[
            OutfitPlan,
            Dict[str, Any],
        ],
        sizes: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Search once, then select one unique product per outfit item.

        No second product search is performed.
        """

        candidates = await self.search_outfit(
            outfit_plan,
            sizes=sizes,
        )

        return select_outfit(
            candidates
        )

    # -------------------------------------------------------------------
    # Natural-language search
    # -------------------------------------------------------------------

    async def find_products(
        self,
        request_text: str,
    ) -> List[Dict[str, Any]]:
        """
        Convenience entry point for natural-language shopping requests.

        Example:
            "Show me black shirts under ₹1500, size M"
        """

        requirements = extract_requirements(
            request_text
        )

        # The structured filters already carry the shopping requirements.
        # Passing the entire natural-language request as `query` would make
        # MockStore's deterministic word-match filter reject valid products
        # because words such as "under", "size", or the numeric budget are
        # not present in product metadata. Keep the free-text query only when
        # no structured shopping signal was extracted.
        structured_search = any(
            requirements[key] is not None
            for key in ("category", "color", "budget", "size")
        )
        search_query = "" if structured_search else requirements["query"]

        return await self.search(
            query=search_query,
            budget=requirements["budget"],
            category=requirements["category"],
            color=requirements["color"],
            size=requirements["size"],
        )

    # -------------------------------------------------------------------
    # Get product
    # -------------------------------------------------------------------

    async def get_product(
        self,
        product_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Look up one product through MCP.
        """

        if not product_id:
            return None

        async with MCPShoppingClient() as client:
            result = await client.get_product(
                product_id
            )

        if not result:
            return None

        if "found" in result:
            if not result.get("found"):
                return None

            return result.get("product")

        return result

    # -------------------------------------------------------------------
    # Variants
    # -------------------------------------------------------------------

    async def get_variants(
        self,
        product_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Return product variants through MCP.
        """

        if not product_id:
            return []

        async with MCPShoppingClient() as client:
            variants = await client.get_variants(
                product_id
            )

        return variants or []

    # -------------------------------------------------------------------
    # Alternatives
    # -------------------------------------------------------------------

    async def get_alternatives(
        self,
        product_id: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Return alternative products through MCP.
        """

        if not product_id:
            return []

        # Keep the public API predictable.
        try:
            safe_limit = int(limit)
        except (TypeError, ValueError):
            safe_limit = 5

        safe_limit = max(
            1,
            min(safe_limit, 50),
        )

        async with MCPShoppingClient() as client:
            alternatives = (
                await client.get_alternatives(
                    product_id,
                    limit=safe_limit,
                )
            )

        return alternatives or []