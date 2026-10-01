"""
Revision loop (Part 48).

    Initial outfit -> Critic -> APPROVE -> done
                          |
                        REVISE -> pick ONE actionable issue
                                     -> ShoppingAgent -> replacement product
                                     -> Critic again -> APPROVE / REVISE ...

Stops when the Critic approves, when MAX_ITERATIONS revision attempts have
been made, or when no untried actionable issue is left.

Rules:
  * Shopping data comes ONLY from an injected ShoppingAgent (its search() and
    get_alternatives()). This module never touches a store, MCP internals or
    the network, and never creates or edits a product or an image.
  * One issue per iteration, in the Critic's own order, so runs are
    deterministic. An (item, reason) pair that was already attempted is not
    attempted again.
  * Only the targeted product changes. Inputs are never mutated; the other
    selected products are the very same objects.
  * If no real replacement exists, the current product is kept and the step is
    reported as "unresolved". Nothing is invented.
  * MCP errors raised by the ShoppingAgent propagate unchanged.

Counting convention:
  iterations        = revision attempts made (an unresolved attempt counts;
                      an immediate approval is 0)
  critic_evaluations = initial evaluation + one per successful replacement
                      (an unresolved attempt changes nothing, so the Critic is
                      not called again)

Replacement source per issue (all through ShoppingAgent):
  "Required item is missing"        -> search(category, planned color, budget cap) -> ADD
  "Color is not in planned palette" -> search(category, each palette color)        -> REPLACE
  anything else about one item      -> get_alternatives(current product)           -> REPLACE
Issues about the whole outfit (item "outfit": budget, accent colors) have no
single product to replace, so they are not actionable here and stay in the
Critic's remaining issues.
"""

from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import Any, Dict, List, Literal, Optional, Sequence, Set, Tuple

from pydantic import BaseModel, ConfigDict, Field

from backend.agents.critic_agent import (
    MISSING_REASON,
    PALETTE_REASON,
    STATUS_APPROVE,
    CriticAgent,
    CriticIssue,
    CriticResult,
)
from backend.agents.shopping_agent import (
    ShoppingAgent,
    normalize_color,
    resolve_item_category,
)

MAX_ITERATIONS = 2

STOP_APPROVED = "approved"
STOP_ITERATION_LIMIT = "iteration_limit"
STOP_NO_ACTIONABLE_ISSUE = "no_actionable_issue"

ACTION_REPLACED = "replaced"
ACTION_ADDED = "added"
ACTION_UNRESOLVED = "unresolved"


class RevisionStep(BaseModel):
    """One revision attempt."""

    model_config = ConfigDict(extra="forbid")

    iteration: int
    item: str
    reason: str
    action: Literal["replaced", "added", "unresolved"]
    old_product_id: Optional[str] = None
    new_product_id: Optional[str] = None
    source: Optional[Literal["search", "alternatives"]] = None
    detail: Optional[str] = None


class RevisionLoopResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["approve", "revise"]
    stop_reason: Literal["approved", "iteration_limit", "no_actionable_issue"]
    selected_products: List[Dict[str, Any]]
    critic_result: CriticResult
    iterations: int
    critic_evaluations: int
    steps: List[RevisionStep] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        return dump()
    raise TypeError(f"Unsupported product type: {type(value).__name__}")


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _category_of_issue_item(item: str) -> Optional[str]:
    """Catalog category for a Critic issue item ("shirt" -> "shirts"); None for "outfit"."""
    return resolve_item_category(SimpleNamespace(category=item, item=item))


def _planned_color(plan: Any, category: str) -> Optional[str]:
    entries = list(_get(plan, "items") or []) + list(_get(plan, "accessories") or [])
    for entry in entries:
        resolved = resolve_item_category(
            SimpleNamespace(category=_get(entry, "category"), item=_get(entry, "item"))
        )
        if resolved == category:
            return normalize_color(_get(entry, "color"))
    return None


def _palette(plan: Any) -> List[str]:
    colors: List[str] = []
    for value in _get(plan, "color_palette") or []:
        if isinstance(value, str) and value.strip():
            colors.append(normalize_color(value) or value.strip().lower())
    return colors


def _price_cap(
    plan: Any,
    budget: Optional[float],
    products: Sequence[Any],
    exclude_index: Optional[int],
) -> Optional[float]:
    """Room left under the budget for one product, or None when there is no usable cap."""
    effective = budget if budget is not None else _get(plan, "budget")
    if not _is_number(effective) or effective <= 0:
        return None
    spent = 0.0
    for index, product in enumerate(products):
        price = _as_dict(product).get("price")
        if index != exclude_index and _is_number(price):
            spent += price
    remaining = effective - spent
    return remaining if remaining > 0 else None


def _first_usable(
    raw_candidates: Optional[Sequence[Any]],
    category: str,
    selected_ids: Set[Any],
) -> Optional[Dict[str, Any]]:
    """First candidate of the right category that is new and not known-unavailable."""
    for raw in raw_candidates or []:
        candidate = _as_dict(raw)
        if (
            candidate.get("product_id") is not None
            and candidate.get("product_id") not in selected_ids
            and candidate.get("category") == category
            and candidate.get("availability") is not False
        ):
            return candidate
    return None


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class RevisionLoop:
    def __init__(
        self,
        shopping_agent: Optional[ShoppingAgent] = None,
        critic: Optional[CriticAgent] = None,
        max_iterations: int = MAX_ITERATIONS,
    ) -> None:
        self._shopping = shopping_agent or ShoppingAgent()
        self._critic = critic or CriticAgent()
        self._max_iterations = max_iterations

    async def run(
        self,
        *,
        outfit_plan: Any,
        selected_products: Sequence[Any],
        user_request: str = "",
        user_profile: Optional[Any] = None,
        budget: Optional[float] = None,
    ) -> RevisionLoopResult:
        products: List[Any] = list(selected_products or [])  # never mutate the caller's list

        def evaluate(current: List[Any]) -> CriticResult:
            return self._critic.evaluate(
                outfit_plan=outfit_plan,
                selected_products=current,
                user_request=user_request,
                user_profile=user_profile,
                budget=budget,
            )

        result = evaluate(products)
        evaluations = 1
        iterations = 0
        steps: List[RevisionStep] = []
        attempted: Set[Tuple[str, str]] = set()

        while True:
            if result.status == STATUS_APPROVE:
                stop_reason = STOP_APPROVED
                break
            if iterations >= self._max_iterations:
                stop_reason = STOP_ITERATION_LIMIT
                break

            target = self._next_issue(result.issues, attempted)
            if target is None:
                stop_reason = STOP_NO_ACTIONABLE_ISSUE
                break

            issue, category = target
            iterations += 1
            attempted.add((issue.item, issue.reason))

            new_products, step = await self._attempt(
                iteration=iterations,
                issue=issue,
                category=category,
                products=products,
                plan=outfit_plan,
                budget=budget,
            )
            steps.append(step)

            if new_products is None:
                continue  # nothing changed, so the Critic's verdict is unchanged

            products = new_products
            result = evaluate(products)
            evaluations += 1

        return RevisionLoopResult(
            status=result.status,
            stop_reason=stop_reason,
            selected_products=[_as_dict(p) for p in products],
            critic_result=result,
            iterations=iterations,
            critic_evaluations=evaluations,
            steps=steps,
        )

    @staticmethod
    def _next_issue(
        issues: Sequence[CriticIssue], attempted: Set[Tuple[str, str]]
    ) -> Optional[Tuple[CriticIssue, str]]:
        """First issue (Critic order) not yet attempted and tied to one item."""
        for issue in issues:
            if (issue.item, issue.reason) in attempted:
                continue
            category = _category_of_issue_item(issue.item)
            if category is not None:
                return issue, category
        return None

    async def _attempt(
        self,
        *,
        iteration: int,
        issue: CriticIssue,
        category: str,
        products: List[Any],
        plan: Any,
        budget: Optional[float],
    ) -> Tuple[Optional[List[Any]], RevisionStep]:
        target_index = next(
            (i for i, p in enumerate(products) if _as_dict(p).get("category") == category),
            None,
        )
        old_id = _as_dict(products[target_index]).get("product_id") if target_index is not None else None
        selected_ids = {_as_dict(p).get("product_id") for p in products}

        def unresolved(detail: str) -> Tuple[None, RevisionStep]:
            return None, RevisionStep(
                iteration=iteration,
                item=issue.item,
                reason=issue.reason,
                action=ACTION_UNRESOLVED,
                old_product_id=old_id,
                detail=detail,
            )

        def done(
            action: str, candidate: Dict[str, Any], source: str
        ) -> Tuple[List[Any], RevisionStep]:
            new_product = copy.deepcopy(candidate)
            new_products = list(products)
            if action == ACTION_ADDED:
                new_products.append(new_product)
            else:
                new_products[target_index] = new_product  # type: ignore[index]
            return new_products, RevisionStep(
                iteration=iteration,
                item=issue.item,
                reason=issue.reason,
                action=action,  # type: ignore[arg-type]
                old_product_id=old_id,
                new_product_id=new_product.get("product_id"),
                source=source,  # type: ignore[arg-type]
            )

        # -- a required item is missing: add a real product for it ----------
        if issue.reason == MISSING_REASON:
            raw = await self._shopping.search(
                category=category,
                color=_planned_color(plan, category),
                budget=_price_cap(plan, budget, products, None),
            )
            candidate = _first_usable(raw, category, selected_ids)
            if candidate is None:
                return unresolved("ShoppingAgent returned no usable product for the missing item")
            return done(ACTION_ADDED, candidate, "search")

        # -- everything below replaces an existing product -------------------
        if target_index is None or old_id is None:
            return unresolved("No selected product to replace for this item")

        if issue.reason == PALETTE_REASON:
            palette = _palette(plan)
            if not palette:
                return unresolved("No planned palette available to search by")
            cap = _price_cap(plan, budget, products, target_index)
            for color in palette:
                raw = await self._shopping.search(category=category, color=color, budget=cap)
                candidate = _first_usable(raw, category, selected_ids)
                if candidate is not None:
                    return done(ACTION_REPLACED, candidate, "search")
            return unresolved("ShoppingAgent found no product in any planned palette color")

        raw = await self._shopping.get_alternatives(old_id)
        candidate = _first_usable(raw, category, selected_ids)
        if candidate is None:
            return unresolved("ShoppingAgent returned no usable alternative")
        return done(ACTION_REPLACED, candidate, "alternatives")