"""
Critic Agent (Part 47).

Evaluates an outfit that has ALREADY been planned and selected. It does not
shop, does not replace products, and never invents product data.

Input: user profile, user request, outfit plan, selected products, budget

Output: CriticResult(status="approve" | "revise", issues=[CriticIssue, ...])

Deterministic: no LLM, no network, no shopping calls, no catalog access. The
same input always produces the same output.

Checks:
  1. occasion       formal occasion vs casual items
  2. color harmony  colors vs the planned palette; too many accent colors
  3. style          requested style vs explicit casual/formal items
  4. budget         total supplied price vs supplied budget
  5. compatibility unavailable products; a dress combined with bottoms
  6. garment type   selected product must match requested garment type
  7. completeness   every item required by the plan has a selected product

When information a check needs is missing, that check is skipped and the
reason is reported by evaluate_with_notes(); nothing is guessed.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from types import SimpleNamespace
from typing import Any, Dict, List, Literal, Optional, Sequence, Set, Tuple

from pydantic import BaseModel, ConfigDict, Field

from backend.agents.shopping_agent import (
    normalize_color,
    resolve_item_category,
)

from backend.shopping.taxonomy import (
    NEUTRAL_FAMILIES,
    color_family,
    colors_compatible,
)

from backend.agents.outfit_type_check import (
    product_matches_garment_type,
    requested_garment_type,
)


logger = logging.getLogger(__name__)

STATUS_APPROVE = "approve"
STATUS_REVISE = "revise"

OUTFIT_ITEM = "outfit"

BUDGET_REASON = "Selected outfit exceeds the provided budget"
MISSING_REASON = "Required item is missing from the selected outfit"
UNAVAILABLE_REASON = "Selected product is unavailable"

DRESS_CONFLICT_REASON = (
    "Conflicts with the selected dress; choose a dress or separates"
)

PALETTE_REASON = (
    "Color is not in the planned palette; try a different color"
)

ACCENT_REASON = (
    "Too many accent colors; keep to at most two non-neutral colors"
)

OCCASION_REASON = "Too casual for the stated formal occasion"

STYLE_CASUAL_REASON = "Too casual for the requested style"

STYLE_FORMAL_REASON = "Too formal for the requested style"


class CriticIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item: str
    reason: str


class CriticResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["approve", "revise"]
    issues: List[CriticIssue] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Vocabulary (deterministic rules)
# ---------------------------------------------------------------------------

_LABELS: Dict[str, str] = {
    "shirts": "shirt",
    "t-shirts": "t-shirt",
    "tops": "top",
    "pants": "pants",
    "jeans": "jeans",
    "skirts": "skirt",
    "dresses": "dress",
    "shoes": "shoes",
    "watches": "watch",
    "sunglasses": "sunglasses",
    "bags": "bag",
    "accessories": "accessory",
}

_NEUTRAL_COLORS = frozenset(
    {
        "black",
        "white",
        "cream",
        "beige",
        "grey",
        "brown",
        "navy",
        "silver",
        "gold",
    }
)

_MAX_ACCENT_COLORS = 2

_BOTTOM_CATEGORIES = frozenset(
    {
        "pants",
        "jeans",
        "skirts",
    }
)

_FORMAL_OCCASION = re.compile(
    r"\b("
    r"wedding|formal|interview|ceremony|reception|gala|cocktail|business"
    r")\b"
)

_FORMAL_STYLES = frozenset(
    {
        "elegant",
        "formal",
        "semi-formal",
        "classic",
        "sophisticated",
    }
)

_CASUAL_STYLES = frozenset(
    {
        "casual",
        "streetwear",
        "sporty",
        "athleisure",
        "relaxed",
    }
)

_CASUAL_TITLE_MARKERS = (
    "graphic",
    "oversized",
    "ripped",
    "distressed",
    "hoodie",
    "jogger",
    "sneaker",
)

_FORMAL_TITLE_MARKERS = (
    "formal",
    "tuxedo",
    "sequin",
    "evening",
)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _get(
    obj: Any,
    name: str,
    default: Any = None,
) -> Any:
    """Read a field from a dict or an object; missing -> default."""

    if obj is None:
        return default

    if isinstance(obj, dict):
        return obj.get(name, default)

    return getattr(obj, name, default)


def _to_dict(value: Any) -> Dict[str, Any]:
    """Convert a Pydantic model or dictionary into a dictionary."""

    if value is None:
        return {}

    if isinstance(value, dict):
        return value

    dump = getattr(value, "model_dump", None)

    if callable(dump):
        return dump()

    raise TypeError(
        f"Unsupported product type: {type(value).__name__}"
    )


def _label(category: Optional[str]) -> str:
    """Convert catalog category into a human-readable label."""

    return _LABELS.get(category, category) if category else OUTFIT_ITEM


def _canon_color(color: Any) -> Optional[str]:
    """Normalize a color into a deterministic canonical value."""

    if not isinstance(color, str) or not color.strip():
        return None

    cleaned = " ".join(color.lower().split())

    return normalize_color(cleaned) or cleaned


def _is_number(value: Any) -> bool:
    """Return True for numeric values but not booleans."""

    return isinstance(value, (int, float)) and not isinstance(
        value,
        bool,
    )


def _terms(value: Any) -> Set[str]:
    """Lower-cased terms from a string or a list of strings."""

    if isinstance(value, str):
        value = [value]

    if not isinstance(value, (list, tuple, set)):
        return set()

    return {
        v.strip().lower()
        for v in value
        if isinstance(v, str) and v.strip()
    }


def _is_casual_item(product: Dict[str, Any]) -> bool:
    """Detect clearly casual products."""

    title = str(product.get("title") or "").lower()

    return product.get("category") == "t-shirts" or any(
        marker in title
        for marker in _CASUAL_TITLE_MARKERS
    )


def _is_formal_item(product: Dict[str, Any]) -> bool:
    """Detect explicitly formal products."""

    title = str(product.get("title") or "").lower()

    return any(
        marker in title
        for marker in _FORMAL_TITLE_MARKERS
    )


# ---------------------------------------------------------------------------
# Critic Agent
# ---------------------------------------------------------------------------

class CriticAgent:
    """Deterministic outfit critic. Pure: inputs are never modified."""

    def evaluate(
        self,
        *,
        outfit_plan: Any,
        selected_products: Sequence[Any],
        user_request: str = "",
        user_profile: Optional[Any] = None,
        budget: Optional[float] = None,
    ) -> CriticResult:

        result, _ = self.evaluate_with_notes(
            outfit_plan=outfit_plan,
            selected_products=selected_products,
            user_request=user_request,
            user_profile=user_profile,
            budget=budget,
        )

        return result

    def evaluate_with_notes(
        self,
        *,
        outfit_plan: Any,
        selected_products: Sequence[Any],
        user_request: str = "",
        user_profile: Optional[Any] = None,
        budget: Optional[float] = None,
    ) -> Tuple[CriticResult, List[str]]:
        """
        Same as evaluate(), plus a list of notes naming every check (or part
        of a check) that was skipped because the input lacked the data.
        """

        products = [
            _to_dict(product)
            for product in (selected_products or [])
        ]

        notes: List[str] = []
        issues: List[CriticIssue] = []

        # 1. Occasion
        occasion_issues, flagged = self._check_occasion(
            outfit_plan,
            user_request,
            products,
            notes,
        )

        issues += occasion_issues

        # 2. Color
        issues += self._check_color(
            outfit_plan,
            products,
            notes,
        )

        # 3. Style
        issues += self._check_style(
            outfit_plan,
            user_profile,
            products,
            flagged,
            notes,
        )

        # 4. Budget
        issues += self._check_budget(
            outfit_plan,
            budget,
            products,
            notes,
        )

        # 5. Existing compatibility checks
        issues += self._check_compatibility(products)

        # 6. Garment-type validation
        issues += self._check_garment_types(
            outfit_plan,
            products,
        )

        # 7. Completeness
        issues += self._check_completeness(
            outfit_plan,
            products,
            notes,
        )

        # Remove duplicate issues while preserving order.
        unique: List[CriticIssue] = []
        seen: Set[Tuple[str, str]] = set()

        for issue in issues:
            key = (
                issue.item,
                issue.reason,
            )

            if key not in seen:
                seen.add(key)
                unique.append(issue)

        for note in notes:
            logger.debug(
                "critic skipped check: %s",
                note,
            )

        status = (
            STATUS_REVISE
            if unique
            else STATUS_APPROVE
        )

        return (
            CriticResult(
                status=status,
                issues=unique,
            ),
            notes,
        )

    # -----------------------------------------------------------------------
    # 1. Occasion
    # -----------------------------------------------------------------------

    def _check_occasion(
        self,
        plan: Any,
        user_request: str,
        products: List[Dict[str, Any]],
        notes: List[str],
    ) -> Tuple[List[CriticIssue], Set[int]]:

        text = (
            f"{_get(plan, 'occasion') or ''} "
            f"{user_request or ''}"
        ).lower()

        if not text.strip():
            notes.append(
                "occasion: no occasion or request text supplied"
            )

            return [], set()

        if not _FORMAL_OCCASION.search(text):
            notes.append(
                "occasion: no formal occasion stated; "
                "nothing to compare"
            )

            return [], set()

        issues: List[CriticIssue] = []
        flagged: Set[int] = set()

        for index, product in enumerate(products):

            if _is_casual_item(product):
                flagged.add(index)

                issues.append(
                    CriticIssue(
                        item=_label(
                            product.get("category")
                        ),
                        reason=OCCASION_REASON,
                    )
                )

        return issues, flagged

    # -----------------------------------------------------------------------
    # 2. Color harmony
    # -----------------------------------------------------------------------

    def _check_color(
        self,
        plan: Any,
        products: List[Dict[str, Any]],
        notes: List[str],
    ) -> List[CriticIssue]:

        issues: List[CriticIssue] = []

        colored = [
            (
                product,
                _canon_color(product.get("color")),
            )
            for product in products
        ]

        missing = sum(
            1
            for _, color in colored
            if color is None
        )

        if missing:
            notes.append(
                f"color: {missing} product(s) without color "
                "information were skipped"
            )

        palette = {
            color
            for color in (
                _canon_color(value)
                for value in (
                    _get(plan, "color_palette") or []
                )
            )
            if color
        }

        if palette:

            for product, color in colored:

                # A product colour is in the palette when it is
                # the same colour or a shade of the same family.

                in_palette = (
                    color is not None
                    and (
                        color in palette
                        or any(
                            colors_compatible(
                                color,
                                planned,
                            )
                            for planned in palette
                        )
                    )
                )

                if color is not None and not in_palette:
                    issues.append(
                        CriticIssue(
                            item=_label(
                                product.get("category")
                            ),
                            reason=PALETTE_REASON,
                        )
                    )

        else:
            notes.append(
                "color: no planned palette supplied; "
                "palette check skipped"
            )

        # Count accent colours by family so two shades
        # of green count once.
        accents = {
            color_family(color) or color
            for _, color in colored
            if (
                color is not None
                and color not in _NEUTRAL_COLORS
                and color_family(color)
                not in NEUTRAL_FAMILIES
            )
        }

        if len(accents) > _MAX_ACCENT_COLORS:
            issues.append(
                CriticIssue(
                    item=OUTFIT_ITEM,
                    reason=ACCENT_REASON,
                )
            )

        return issues

    # -----------------------------------------------------------------------
    # 3. Style
    # -----------------------------------------------------------------------

    def _check_style(
        self,
        plan: Any,
        profile: Any,
        products: List[Dict[str, Any]],
        already_flagged: Set[int],
        notes: List[str],
    ) -> List[CriticIssue]:

        styles = (
            _terms(
                _get(plan, "style")
            )
            | _terms(
                _get(
                    profile,
                    "style_preferences",
                )
            )
        )

        if not styles:
            notes.append(
                "style: no style or style preferences supplied"
            )

            return []

        wants_formal = bool(
            styles & _FORMAL_STYLES
        )

        wants_casual = bool(
            styles & _CASUAL_STYLES
        )

        if not (wants_formal or wants_casual):
            notes.append(
                "style: supplied style is not one "
                "the critic can compare"
            )

            return []

        issues: List[CriticIssue] = []

        for index, product in enumerate(products):

            if index in already_flagged:
                continue

            item = _label(
                product.get("category")
            )

            if (
                wants_formal
                and not wants_casual
                and _is_casual_item(product)
            ):
                issues.append(
                    CriticIssue(
                        item=item,
                        reason=STYLE_CASUAL_REASON,
                    )
                )

            elif (
                wants_casual
                and not wants_formal
                and _is_formal_item(product)
            ):
                issues.append(
                    CriticIssue(
                        item=item,
                        reason=STYLE_FORMAL_REASON,
                    )
                )

        return issues

    # -----------------------------------------------------------------------
    # 4. Budget
    # -----------------------------------------------------------------------

    def _check_budget(
        self,
        plan: Any,
        budget: Optional[float],
        products: List[Dict[str, Any]],
        notes: List[str],
    ) -> List[CriticIssue]:

        effective = (
            budget
            if budget is not None
            else _get(plan, "budget")
        )

        if not _is_number(effective) or effective <= 0:
            notes.append(
                "budget: no budget supplied"
            )

            return []

        prices = [
            product["price"]
            for product in products
            if _is_number(
                product.get("price")
            )
        ]

        unpriced = (
            len(products)
            - len(prices)
        )

        if not prices:
            notes.append(
                "budget: no product prices supplied"
            )

            return []

        currencies = {
            product.get("currency")
            for product in products
            if _is_number(
                product.get("price")
            )
        }

        if len(currencies) > 1:
            notes.append(
                "budget: products use different currencies; "
                "total not comparable"
            )

            return []

        total = sum(prices)

        if total > effective:
            return [
                CriticIssue(
                    item=OUTFIT_ITEM,
                    reason=BUDGET_REASON,
                )
            ]

        if unpriced:
            notes.append(
                f"budget: {unpriced} product(s) without a price; "
                "total is partial"
            )

        return []

    # -----------------------------------------------------------------------
    # 5. Product compatibility
    # -----------------------------------------------------------------------

    def _check_compatibility(
        self,
        products: List[Dict[str, Any]],
    ) -> List[CriticIssue]:

        issues: List[CriticIssue] = []

        # Existing availability check.
        for product in products:

            if product.get("availability") is False:
                issues.append(
                    CriticIssue(
                        item=_label(
                            product.get("category")
                        ),
                        reason=UNAVAILABLE_REASON,
                    )
                )

        # Existing dress + bottom conflict check.
        categories = {
            product.get("category")
            for product in products
        }

        if "dresses" in categories:

            for bottom in sorted(
                categories & _BOTTOM_CATEGORIES
            ):
                issues.append(
                    CriticIssue(
                        item=_label(bottom),
                        reason=DRESS_CONFLICT_REASON,
                    )
                )

        return issues

    # -----------------------------------------------------------------------
    # 6. Garment-type validation
    # -----------------------------------------------------------------------

    def _check_garment_types(
        self,
        plan: Any,
        products: List[Dict[str, Any]],
    ) -> List[CriticIssue]:
        """
        Ensure that the selected product matches the requested garment type.

        Example:
            Requested garment type = Anarkali
            Selected product = Emerald Green Satin Midi Dress

        The critic should reject that selection rather than treating every
        one-piece garment as interchangeable with an Anarkali.
        """

        plan_items = (
            list(
                _get(plan, "items") or []
            )
            + list(
                _get(plan, "accessories") or []
            )
        )

        locked_by_index: Dict[int, str] = {}

        locked_types = (
            _get(
                plan,
                "_locked_garment_types",
            )
            or []
        )

        for item in locked_types:

            if not isinstance(item, dict):
                continue

            item_index = item.get(
                "item_index"
            )

            garment_type = item.get(
                "garment_type"
            )

            if (
                item_index is None
                or not garment_type
            ):
                continue

            try:
                locked_by_index[
                    int(item_index)
                ] = str(garment_type)
            except (TypeError, ValueError):
                continue

        issues: List[CriticIssue] = []

        for item_index, planned_item in enumerate(
            plan_items
        ):

            planned = (
                planned_item
                if isinstance(
                    planned_item,
                    dict,
                )
                else _to_dict(
                    planned_item
                )
            )

            garment_type = (
                locked_by_index.get(
                    item_index
                )
                or requested_garment_type(
                    planned
                )
            )

            if not garment_type:
                continue

            # Prefer explicit item_index matching.
            selected = next(
                (
                    product
                    for product in products
                    if str(
                        product.get(
                            "item_index",
                            "",
                        )
                    )
                    == str(item_index)
                ),
                None,
            )

            # Compatibility for older ranker responses
            # without item_index.
            if (
                selected is None
                and len(products) == len(plan_items)
            ):
                selected = products[
                    item_index
                ]

            if selected is None:
                # The completeness check handles missing products.
                continue

            if not product_matches_garment_type(
                selected,
                garment_type,
            ):
                label = _label(
                    selected.get("category")
                    or planned.get("category")
                )

                issues.append(
                    CriticIssue(
                        item=label,
                        reason=(
                            "Selected product does not match the requested "
                            f"{garment_type} outfit type"
                        ),
                    )
                )

        return issues

    # -----------------------------------------------------------------------
    # 7. Completeness
    # -----------------------------------------------------------------------

    def _check_completeness(
        self,
        plan: Any,
        products: List[Dict[str, Any]],
        notes: List[str],
    ) -> List[CriticIssue]:

        plan_items = (
            list(
                _get(plan, "items") or []
            )
            + list(
                _get(plan, "accessories") or []
            )
        )

        if not plan_items:

            if not products:
                return [
                    CriticIssue(
                        item=OUTFIT_ITEM,
                        reason="No products were selected",
                    )
                ]

            notes.append(
                "completeness: plan lists no items; "
                "nothing required"
            )

            return []

        required: Counter = Counter()

        for entry in plan_items:

            category = resolve_item_category(
                SimpleNamespace(
                    category=_get(
                        entry,
                        "category",
                    ),
                    item=_get(
                        entry,
                        "item",
                    ),
                )
            )

            if category is None:
                notes.append(
                    "completeness: cannot map plan item "
                    f"{_get(entry, 'item') or _get(entry, 'category')!r} "
                    "to a known category; skipped"
                )

                continue

            required[category] += 1

        selected_categories: Counter = Counter()

        for product in products:

            category = product.get(
                "category"
            )

            if category:
                selected_categories[
                    category
                ] += 1

        issues: List[CriticIssue] = []

        for category, required_count in required.items():

            selected_count = selected_categories.get(
                category,
                0,
            )

            if selected_count < required_count:
                missing_count = (
                    required_count
                    - selected_count
                )

                label = _label(category)

                if missing_count == 1:
                    reason = MISSING_REASON
                else:
                    reason = (
                        f"{missing_count} required "
                        f"{label} items are missing "
                        "from the selected outfit"
                    )

                issues.append(
                    CriticIssue(
                        item=label,
                        reason=reason,
                    )
                )

        return issues


# ---------------------------------------------------------------------------
# Default instance
# ---------------------------------------------------------------------------

critic_agent = CriticAgent()