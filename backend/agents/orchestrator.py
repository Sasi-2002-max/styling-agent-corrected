"""
Main Fashion Stylist Orchestrator.

Workflow:

    START
      |
      v
    Profile Agent
      |
      v
    Stylist Agent
      |
      v
    RAG
      |
      v
    Shopping Agent
      |
      v
    MCP
      |
      v
    Product Ranker
      |
      v
    Fitting Room
      |
      v
    Critic
      |
      v
    Approval?
      |
      +---------------- YES ----------------> FINAL
      |
      NO
      |
      v
    Revision
      |
      +--------------------> Profile Agent

Responsibilities:

- Profile Agent owns profile/request parsing.
- Stylist Agent owns outfit planning.
- RAG provides fashion knowledge/context.
- Shopping Agent owns product retrieval.
- MCP remains behind Shopping Agent.
- Product Ranker ranks/selects EXISTING candidates.
- Fitting Room resolves selected products.
- Critic decides whether the result needs revision.

IMPORTANT:

The Shopping Agent MUST NOT use build_outfit() in this
orchestrator because build_outfit() already performs product
selection.

The orchestrator therefore uses:

    ShoppingAgent.search_outfit()
        -> retrieves real products
        -> product_candidates
        -> Product Ranker
        -> selected_products
        -> Fitting Room

This keeps retrieval and selection as separate responsibilities.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any, Dict, List, Optional

from backend.agents.profile_agent import profile_agent
from backend.agents.stylist_agent import stylist_agent
from backend.agents.product_ranker import (
    ProductRankerError,
    product_ranker_agent,
)
from backend.agents.state import AgentState


logger = logging.getLogger(__name__)

MAX_REVISIONS = 2


class OrchestratorError(Exception):
    """Raised when the fashion workflow cannot complete."""


# ============================================================================
# Helpers
# ============================================================================


async def _maybe_await(value: Any) -> Any:
    """
    Await a value when necessary.

    Supports both synchronous and asynchronous agents/functions.
    """
    if inspect.isawaitable(value):
        return await value

    return value


def _normalise_product_candidates(result: Any) -> List[Dict[str, Any]]:
    """
    Convert ShoppingAgent.search_outfit() output into a flat list
    of actual product dictionaries.

    Expected search_outfit() output:

        [
            {
                "index": 0,
                "source": "items",
                "item": {...},
                "search_params": {...},
                "status": "ok",
                "products": [
                    {...real product...},
                    {...real product...}
                ]
            }
        ]

    Product Ranker must receive the actual products, not the wrapper
    entries.

    Also supports simpler list/dict response shapes for compatibility.
    """

    if result is None:
        return []

    # ------------------------------------------------------------------
    # Direct list response
    # ------------------------------------------------------------------

    if isinstance(result, list):
        flattened: List[Dict[str, Any]] = []

        for fallback_index, entry in enumerate(result):
            if not isinstance(entry, dict):
                continue

            # search_outfit wrapper
            products = entry.get("products")

            if isinstance(products, list):
                item_index = entry.get("index", fallback_index)
                outfit_item = entry.get("item")
                source = entry.get("source")

                for product in products:
                    if isinstance(product, dict):
                        candidate = dict(product)
                        candidate.setdefault("item_index", item_index)
                        if source is not None:
                            candidate.setdefault("item_source", source)
                        if isinstance(outfit_item, dict):
                            candidate.setdefault("outfit_item", dict(outfit_item))
                            if not (
                                candidate.get("category")
                                or candidate.get("product_type")
                                or candidate.get("type")
                            ):
                                candidate["category"] = (
                                    outfit_item.get("category")
                                    or outfit_item.get("type")
                                    or outfit_item.get("item_type")
                                )
                        flattened.append(candidate)

                continue

            # Already a product
            if entry.get("product_id") or entry.get("id"):
                flattened.append(dict(entry))

        return flattened

    # ------------------------------------------------------------------
    # Dictionary response
    # ------------------------------------------------------------------

    if isinstance(result, dict):

        # Explicit product_candidates
        candidates = result.get("product_candidates")

        if isinstance(candidates, list):
            return _normalise_product_candidates(candidates)

        # products
        products = result.get("products")

        if isinstance(products, list):
            return _normalise_product_candidates(products)

        # entries
        entries = result.get("entries")

        if isinstance(entries, list):
            return _normalise_product_candidates(entries)

    return []


def _extract_selected_products(result: Any) -> List[Dict[str, Any]]:
    """
    Extract selected products from Product Ranker output.

    Supports:

        {
            "selected_products": [...]
        }

    or:

        {
            "products": [...]
        }

    or:

        {
            "product_candidates": [...]
        }

    or a direct list.
    """

    if result is None:
        return []

    if isinstance(result, list):
        return [
            item
            for item in result
            if isinstance(item, dict)
        ]

    if isinstance(result, dict):

        selected = result.get("selected_products")

        if isinstance(selected, list):
            return selected

        products = result.get("products")

        if isinstance(products, list):
            return products

        candidates = result.get("product_candidates")

        if isinstance(candidates, list):
            return candidates

    return []


def _extract_critic_feedback(result: Any) -> Dict[str, Any]:
    """
    Normalize Critic output into a dictionary.
    """

    if result is None:
        return {
            "approved": False,
            "issues": [
                "Critic returned no result."
            ],
        }

    if isinstance(result, bool):
        return {
            "approved": result,
            "issues": [],
        }

    if isinstance(result, dict):

        feedback = result.get("critic_feedback")

        if isinstance(feedback, dict):
            return feedback

        return result

    return {
        "approved": False,
        "issues": [
            "Critic returned an unsupported response."
        ],
    }


# ============================================================================
# Initial State
# ============================================================================


def create_initial_state(
    user_profile: Optional[Dict[str, Any]],
    user_query: str,
) -> AgentState:
    """
    Create the shared AgentState.
    """

    return {
        "user_profile": user_profile or {},
        "user_query": user_query or "",

        "style_context": {},
        "rag_context": [],

        "outfit_plan": {},

        # Shopping retrieval output
        "shopping_results": [],
        "product_candidates": [],

        # Product Ranker output
        "selected_products": [],

        # Fitting Room output
        "fitting_room": {},

        # Critic output
        "critic_feedback": {},

        "iteration": 0,
        "status": "running",
    }


# ============================================================================
# RAG
# ============================================================================


def _run_rag(state: AgentState) -> AgentState:
    """
    RAG stage.

    The Stylist Agent may already perform RAG internally.

    We therefore preserve whatever rag_context already exists.
    """

    logger.info("3. RAG stage")

    if state.get("rag_context") is None:
        state["rag_context"] = []

    return state


# ============================================================================
# Shopping Agent
# ============================================================================


async def _run_shopping(state: AgentState) -> AgentState:
    """
    Run ShoppingAgent.search_outfit().

    IMPORTANT:

    DO NOT call ShoppingAgent.build_outfit() here.

    build_outfit() performs:

        search
        -> rank
        -> select

    That would duplicate the Product Ranker's responsibility.

    The orchestrator needs:

        search_outfit()
        -> raw/real products
        -> Product Ranker

    """

    logger.info("4. Shopping Agent")

    try:
        from backend.agents.shopping_agent import ShoppingAgent
    except ImportError as exc:
        raise OrchestratorError(
            "Could not import "
            "backend.agents.shopping_agent.ShoppingAgent"
        ) from exc

    shopping_agent = ShoppingAgent()

    outfit_plan = state.get("outfit_plan") or {}

    # ------------------------------------------------------------------
    # Preferred API: search_outfit()
    # ------------------------------------------------------------------

    search_outfit = getattr(
        shopping_agent,
        "search_outfit",
        None,
    )

    if callable(search_outfit):

        logger.info(
            "Calling ShoppingAgent.search_outfit()"
        )

        result = search_outfit(
            outfit_plan=outfit_plan
        )

        result = await _maybe_await(result)

        # Preserve original per-item shopping results.
        if isinstance(result, list):
            state["shopping_results"] = result
        else:
            state["shopping_results"] = []

        # Flatten actual products for Product Ranker.
        candidates = _normalise_product_candidates(result)

        state["product_candidates"] = candidates

        logger.info(
            "ShoppingAgent.search_outfit() returned "
            "%d real product candidates",
            len(candidates),
        )

        return state

    # ------------------------------------------------------------------
    # Compatibility fallback: search()
    # ------------------------------------------------------------------

    search = getattr(
        shopping_agent,
        "search",
        None,
    )

    if not callable(search):
        raise OrchestratorError(
            "ShoppingAgent has neither "
            "search_outfit() nor search()."
        )

    logger.warning(
        "ShoppingAgent.search_outfit() unavailable. "
        "Using generic search() fallback."
    )

    items = outfit_plan.get("items") or []
    accessories = outfit_plan.get("accessories") or []

    all_items = items + accessories

    candidates: List[Dict[str, Any]] = []

    budget = outfit_plan.get("budget")

    for item_index, item in enumerate(all_items):

        if not isinstance(item, dict):
            continue

        category = (
            item.get("category")
            or item.get("type")
            or item.get("item_type")
        )

        color = (
            item.get("color")
            or item.get("colour")
        )

        query = item.get("item") or ""

        if not category:
            logger.warning(
                "Skipping outfit item without category: %s",
                item,
            )
            continue

        logger.info(
            "Searching category=%s color=%s query=%s",
            category,
            color,
            query,
        )

        try:
            result = search(
                query=query,
                budget=budget,
                category=category,
                color=color,
            )

        except TypeError:

            try:
                result = search(
                    category=category,
                    color=color,
                )

            except TypeError:

                result = search(
                    category=category,
                )

        result = await _maybe_await(result)

        if isinstance(result, list):
            item_candidates = [
                product
                for product in result
                if isinstance(product, dict)
            ]
        elif isinstance(result, dict):
            item_candidates = _normalise_product_candidates(result)
        else:
            item_candidates = []

        item_source = (
            "items" if item_index < len(items) else "accessories"
        )
        for product in item_candidates:
            candidate = dict(product)
            candidate.setdefault("item_index", item_index)
            candidate.setdefault("item_source", item_source)
            candidate.setdefault("outfit_item", dict(item))
            if not (
                candidate.get("category")
                or candidate.get("product_type")
                or candidate.get("type")
            ):
                candidate["category"] = category
            candidates.append(candidate)

    state["product_candidates"] = candidates

    logger.info(
        "Fallback shopping returned %d product candidates",
        len(candidates),
    )

    return state


# ============================================================================
# Product Ranker
# ============================================================================


async def _run_product_ranker(
    state: AgentState,
) -> AgentState:
    """
    Run Product Ranker.

    The Product Ranker receives EXISTING products from Shopping Agent.

    It must NOT search MCP again.

    Input:

        state["product_candidates"]

    Output:

        state["selected_products"]
    """

    logger.info("6. Product Ranker")

    candidates = (
        state.get("product_candidates")
        or []
    )

    if not candidates:

        logger.warning(
            "Product Ranker received zero product candidates."
        )

        state["selected_products"] = []

        state["critic_feedback"] = {
            "approved": False,
            "issues": [
                "Shopping Agent returned no product candidates."
            ],
            "source": "orchestrator",
        }

        return state

    try:

        result = product_ranker_agent(state)

        result = await _maybe_await(result)

        # --------------------------------------------------------------
        # IMPORTANT FIX:
        #
        # Do NOT blindly do:
        #
        #     state = result
        #
        # because a ranker may return only a partial dictionary.
        #
        # Merge returned state into the existing state instead.
        # --------------------------------------------------------------

        if isinstance(result, dict):

            returned_selected = result.get(
                "selected_products"
            )

            returned_candidates = result.get(
                "product_candidates"
            )

            returned_feedback = result.get(
                "critic_feedback"
            )

            # If the ranker returned selected products,
            # use them explicitly.
            if isinstance(returned_selected, list):

                state["selected_products"] = [
                    product
                    for product in returned_selected
                    if isinstance(product, dict)
                ]

            # Preserve candidates if the ranker returned them.
            if isinstance(returned_candidates, list):

                state["product_candidates"] = [
                    product
                    for product in returned_candidates
                    if isinstance(product, dict)
                ]

            # Preserve critic feedback if present.
            if isinstance(returned_feedback, dict):

                state["critic_feedback"] = (
                    returned_feedback
                )

            # Some ranker implementations may return
            # {"products": [...]} instead.
            if (
                not state.get("selected_products")
                and isinstance(
                    result.get("products"),
                    list,
                )
            ):

                state["selected_products"] = [
                    product
                    for product in result["products"]
                    if isinstance(product, dict)
                ]

            # Some implementations return only
            # {"product_candidates": [...]}
            # where those are already ranked/selected.
            if (
                not state.get("selected_products")
                and isinstance(returned_candidates, list)
                and returned_candidates
            ):

                state["selected_products"] = [
                    product
                    for product in returned_candidates
                    if isinstance(product, dict)
                ]

        # Direct list response
        elif isinstance(result, list):

            state["selected_products"] = [
                item
                for item in result
                if isinstance(item, dict)
            ]

    except ProductRankerError:
        raise

    except Exception as exc:

        logger.exception(
            "Product Ranker failed."
        )

        raise ProductRankerError(
            f"Product ranking failed: {exc}"
        ) from exc

    selected = (
        state.get("selected_products")
        or []
    )

    logger.info(
        "Product Ranker selected %d products",
        len(selected),
    )

    return state


# ============================================================================
# Fitting Room
# ============================================================================


async def _run_fitting_room(
    state: AgentState,
) -> AgentState:
    """
    Resolve selected products through FittingRoomService.

    Fitting Room receives ONLY selected_products.

    It must not perform product search or product ranking.
    """

    logger.info("7. Fitting Room")

    from backend.fitting_room.service import (
        FittingRoomService,
    )

    selected_products = (
        state.get("selected_products")
        or []
    )

    outfit_plan = state.get("outfit_plan") or {}
    planned_items = [
        item
        for key in ("items", "accessories")
        for item in (outfit_plan.get(key) or [])
        if isinstance(item, dict)
    ]

    outfit = {
        "status": "complete",
        "selected_products": [],
        "total_price": 0.0,
        "missing_items": [],
    }
    selected_by_index: Dict[int, Dict[str, Any]] = {}
    total_price = 0.0

    for index, product in enumerate(
        selected_products
    ):

        if not isinstance(product, dict):
            continue

        product_id = (
            product.get("product_id")
            or product.get("id")
        )

        if not product_id:

            logger.warning(
                "Selected product at index %d "
                "has no product_id",
                index,
            )

            continue

        category = (
            product.get("category")
            or product.get("product_type")
            or product.get("type")
            or "unknown"
        )

        outfit["selected_products"].append(
            {
                "product_id": product_id,
                "category": category,
                "item_index": product.get(
                    "item_index",
                    index,
                ),
            }
        )
        try:
            item_index = int(product.get("item_index", index))
        except (TypeError, ValueError):
            item_index = index
        selected_by_index[item_index] = product

        price = product.get("price")
        try:
            numeric_price = float(price)
        except (TypeError, ValueError):
            numeric_price = 0.0
        if numeric_price > 0:
            total_price += numeric_price

    for item_index, planned_item in enumerate(planned_items):
        selected = selected_by_index.get(item_index)
        if selected is None:
            outfit["missing_items"].append(
                {
                    "item_index": item_index,
                    "category": (
                        planned_item.get("category")
                        or planned_item.get("type")
                        or planned_item.get("item_type")
                        or "unknown"
                    ),
                    "item": (
                        planned_item.get("item")
                        or planned_item.get("name")
                        or ""
                    ),
                    "reason": "no_available_product",
                }
            )
            continue

        try:
            has_price = float(selected.get("price")) > 0
        except (TypeError, ValueError):
            has_price = False
        if not has_price:
            outfit["missing_items"].append(
                {
                    "item_index": item_index,
                    "category": (
                        planned_item.get("category")
                        or planned_item.get("type")
                        or "unknown"
                    ),
                    "item": (
                        planned_item.get("item")
                        or planned_item.get("name")
                        or ""
                    ),
                    "reason": "price_unavailable",
                }
            )

    outfit["total_price"] = round(total_price, 2)
    outfit["status"] = (
        "complete" if not outfit["missing_items"] else "incomplete"
    )

    # ------------------------------------------------------------------
    # Determine mannequin gender
    # ------------------------------------------------------------------

    style_context = (
        state.get("style_context")
        or {}
    )

    user_profile = (
        style_context.get("profile")
        or state.get("user_profile")
        or {}
    )

    mannequin_gender = (
        user_profile.get("gender")
        or "female"
    )

    mannequin_gender = str(
        mannequin_gender
    ).lower()

    if mannequin_gender not in {
        "female",
        "male",
    }:
        mannequin_gender = "female"

    # ------------------------------------------------------------------
    # No selected products
    # ------------------------------------------------------------------

    if not outfit["selected_products"]:

        logger.warning(
            "Fitting Room received no selected products."
        )

        state["fitting_room"] = {
            "status": "incomplete",
            "mannequin": {
                "gender": mannequin_gender,
                "asset": (
                    f"assets/fitting-room/"
                    f"{mannequin_gender}-mannequin.png"
                ),
            },
            "outfit": {
                "status": "incomplete",
                "selected_products": [],
                "total_price": 0,
                "missing_items": outfit["missing_items"] or [
                    {
                        "item_index": None,
                        "category": "outfit",
                        "item": "",
                        "reason": "no_products_selected",
                    }
                ],
            },
            "items": [],
        }

        return state

    # ------------------------------------------------------------------
    # Call FittingRoomService
    # ------------------------------------------------------------------

    service = FittingRoomService()

    response = await service.prepare_fitting_room(
        outfit_result=outfit,
        mannequin_gender=mannequin_gender,
        include_variants=True,
        include_alternatives=True,
    )

    if hasattr(response, "model_dump"):
        state["fitting_room"] = (
            response.model_dump()
        )
    else:
        state["fitting_room"] = response

    return state


# ============================================================================
# Critic
# ============================================================================


async def _run_critic(
    state: AgentState,
) -> AgentState:
    """
    Run the existing Critic Agent when available.

    Supports:

        backend.agents.critic_agent
        backend.agents.critic

    And:

        critic_agent()
        run_critic()
        critique()
    """

    logger.info("8. Critic")

    critic_function = None

    possible_modules = (
        "backend.agents.critic_agent",
        "backend.agents.critic",
    )

    possible_functions = (
        "critic_agent",
        "run_critic",
        "critique",
    )

    for module_name in possible_modules:

        try:
            module = __import__(
                module_name,
                fromlist=["*"],
            )

        except ImportError:
            continue

        critic_class = getattr(module, "CriticAgent", None)
        if callable(critic_class):
            critic = critic_class()
            style_context = state.get("style_context") or {}
            profile = style_context.get("profile") or state.get("user_profile") or {}
            plan = state.get("outfit_plan") or {}
            result, notes = critic.evaluate_with_notes(
                outfit_plan=plan,
                selected_products=state.get("selected_products") or [],
                user_request=state.get("user_query") or "",
                user_profile=profile,
                budget=plan.get("budget"),
            )
            state["critic_feedback"] = {
                "status": result.status,
                "approved": result.status == "approve",
                "issues": [
                    issue.model_dump()
                    for issue in result.issues
                ],
                "notes": notes,
                "source": "critic_agent",
            }
            return state

        for function_name in possible_functions:

            candidate = getattr(
                module,
                function_name,
                None,
            )

            if callable(candidate):

                critic_function = candidate
                break

        if critic_function:
            break

    # ------------------------------------------------------------------
    # No Critic Agent
    # ------------------------------------------------------------------

    if critic_function is None:

        logger.warning(
            "No Critic Agent was found. "
            "Using deterministic approval checks."
        )

        selected = (
            state.get("selected_products")
            or []
        )

        fitting_room = (
            state.get("fitting_room")
            or {}
        )

        if selected and fitting_room:

            state["critic_feedback"] = {
                "approved": True,
                "issues": [],
                "source": "fallback",
            }

        elif not selected:

            state["critic_feedback"] = {
                "approved": False,
                "issues": [
                    "No products were selected."
                ],
                "source": "fallback",
            }

        else:

            state["critic_feedback"] = {
                "approved": False,
                "issues": [
                    "Fitting Room did not produce a result."
                ],
                "source": "fallback",
            }

        return state

    # ------------------------------------------------------------------
    # Run Critic
    # ------------------------------------------------------------------

    result = critic_function(state)

    result = await _maybe_await(result)

    if isinstance(result, dict):

        if isinstance(
            result.get("critic_feedback"),
            dict,
        ):

            state["critic_feedback"] = (
                result["critic_feedback"]
            )

        else:

            state["critic_feedback"] = (
                _extract_critic_feedback(result)
            )

    else:

        state["critic_feedback"] = (
            _extract_critic_feedback(result)
        )

    return state


# ============================================================================
# Approval
# ============================================================================


def _is_approved(
    state: AgentState,
) -> bool:
    """
    Determine whether Critic approved the current result.
    """

    feedback = (
        state.get("critic_feedback")
        or {}
    )

    if isinstance(feedback, bool):
        return feedback

    if not isinstance(feedback, dict):
        return False

    approved = feedback.get("approved")

    if approved is True:
        return True

    status = str(
        feedback.get(
            "status",
            "",
        )
    ).lower()

    if status in {
        "approved",
        "approve",
        "accepted",
        "complete",
    }:
        return True

    return False


# ============================================================================
# Revision
# ============================================================================


def _prepare_revision(
    state: AgentState,
) -> AgentState:
    """
    Prepare shared state for another workflow pass.

    The stylist/profile context is preserved so the next iteration
    can improve the existing request instead of losing all context.
    """

    state["iteration"] = (
        int(
            state.get(
                "iteration",
                0,
            )
        )
        + 1
    )

    # These are rebuilt during the next iteration.
    state["outfit_plan"] = {}
    state["shopping_results"] = []
    state["product_candidates"] = []
    state["selected_products"] = []
    state["fitting_room"] = {}

    # Keep critic feedback available to the next
    # Profile/Stylist stages so they can understand
    # why the previous result was rejected.
    state["status"] = "revision"

    return state


# ============================================================================
# Asynchronous Workflow
# ============================================================================


async def run_orchestrator_async(
    user_profile: Optional[Dict[str, Any]],
    user_query: str,
) -> AgentState:
    """
    Run the complete fashion workflow asynchronously.

    Recommended entry point for FastAPI.

    Part 50: this now executes the LangGraph workflow defined in
    backend/agents/langgraph_workflow.py. The signature and return
    value (the final AgentState) are unchanged, so FastAPI and existing
    callers keep working.

    The import is local on purpose: langgraph_workflow imports the
    stage helpers from this module, so a top-level import here would be
    circular.
    """

    from backend.agents.langgraph_workflow import (
        run_langgraph_workflow_async,
    )

    return await run_langgraph_workflow_async(
        user_profile=user_profile,
        user_query=user_query,
    )


async def run_orchestrator_legacy_async(
    user_profile: Optional[Dict[str, Any]],
    user_query: str,
) -> AgentState:
    """
    Part 49 hand-written loop, kept for reference / rollback / parity tests.

    Not used by the API after Part 50.
    """

    state = create_initial_state(
        user_profile=user_profile,
        user_query=user_query,
    )

    for _ in range(MAX_REVISIONS + 1):

        iteration = int(
            state.get(
                "iteration",
                0,
            )
        )

        logger.info(
            "=================================================="
        )

        logger.info(
            "Starting workflow iteration %d",
            iteration,
        )

        logger.info(
            "=================================================="
        )

        # ==============================================================
        # 1. Profile Agent
        # ==============================================================

        logger.info("1. Profile Agent")

        state = profile_agent(state)

        state = await _maybe_await(state)

        # ==============================================================
        # 2. Stylist Agent
        # ==============================================================

        logger.info("2. Stylist Agent")

        state = stylist_agent(state)

        state = await _maybe_await(state)

        # ==============================================================
        # 3. RAG
        # ==============================================================

        logger.info("3. RAG")

        state = _run_rag(state)

        # ==============================================================
        # 4. Shopping Agent
        # 5. MCP is encapsulated inside ShoppingAgent
        # ==============================================================

        logger.info("4. Shopping Agent")
        logger.info("5. MCP")

        try:

            state = await _run_shopping(state)

        except Exception as exc:

            logger.exception(
                "Shopping stage failed."
            )

            state["critic_feedback"] = {
                "approved": False,
                "issues": [
                    f"Shopping failed: {exc}"
                ],
                "source": "orchestrator",
            }

            if iteration >= MAX_REVISIONS:

                state["status"] = "rejected"

                return state

            state = _prepare_revision(state)

            continue

        # ==============================================================
        # Safety check: Shopping must return real products
        # ==============================================================

        if not state.get("product_candidates"):

            logger.warning(
                "No product candidates were returned "
                "by Shopping Agent."
            )

            state["critic_feedback"] = {
                "approved": False,
                "issues": [
                    "No product candidates were found."
                ],
                "source": "orchestrator",
            }

            if iteration >= MAX_REVISIONS:

                state["status"] = "rejected"

                return state

            state = _prepare_revision(state)

            continue

        # ==============================================================
        # 6. Product Ranker
        # ==============================================================

        logger.info("6. Product Ranker")

        try:

            state = await _run_product_ranker(state)

        except ProductRankerError as exc:

            logger.exception(
                "Product ranking failed."
            )

            state["critic_feedback"] = {
                "approved": False,
                "issues": [
                    str(exc)
                ],
                "source": "orchestrator",
            }

            if iteration >= MAX_REVISIONS:

                state["status"] = "rejected"

                return state

            state = _prepare_revision(state)

            continue

        # ==============================================================
        # Safety check: Product Ranker must select products
        # ==============================================================

        if not state.get("selected_products"):

            logger.warning(
                "Product Ranker did not select "
                "any products."
            )

            state["critic_feedback"] = {
                "approved": False,
                "issues": [
                    "Product Ranker selected no products."
                ],
                "source": "orchestrator",
            }

            if iteration >= MAX_REVISIONS:

                state["status"] = "rejected"

                return state

            state = _prepare_revision(state)

            continue

        # ==============================================================
        # 7. Fitting Room
        # ==============================================================

        logger.info("7. Fitting Room")

        try:

            state = await _run_fitting_room(state)

        except Exception as exc:

            logger.exception(
                "Fitting Room failed."
            )

            state["critic_feedback"] = {
                "approved": False,
                "issues": [
                    f"Fitting Room failed: {exc}"
                ],
                "source": "orchestrator",
            }

            if iteration >= MAX_REVISIONS:

                state["status"] = "rejected"

                return state

            state = _prepare_revision(state)

            continue

        # ==============================================================
        # 8. Critic
        # ==============================================================

        logger.info("8. Critic")

        try:

            state = await _run_critic(state)

        except Exception as exc:

            logger.exception(
                "Critic failed."
            )

            state["critic_feedback"] = {
                "approved": False,
                "issues": [
                    f"Critic failed: {exc}"
                ],
                "source": "orchestrator",
            }

        # ==============================================================
        # 9. Approval?
        # ==============================================================

        logger.info(
            "9. Approval check"
        )

        if _is_approved(state):

            state["status"] = "approved"

            logger.info(
                "Workflow APPROVED on iteration %d",
                iteration,
            )

            return state

        # ==============================================================
        # 10. Revision
        # ==============================================================

        if iteration >= MAX_REVISIONS:

            state["status"] = "rejected"

            logger.warning(
                "Workflow REJECTED after %d revision(s).",
                MAX_REVISIONS,
            )

            return state

        logger.info(
            "Critic rejected result. "
            "Starting revision %d.",
            iteration + 1,
        )

        state = _prepare_revision(state)

    state["status"] = "rejected"

    return state


# ============================================================================
# Synchronous compatibility wrapper
# ============================================================================


def run_orchestrator(
    user_profile: Optional[Dict[str, Any]],
    user_query: str,
) -> AgentState:
    """
    Compatibility wrapper for synchronous callers.

    FastAPI should use run_orchestrator_async().
    """

    return asyncio.run(
        run_orchestrator_async(
            user_profile=user_profile,
            user_query=user_query,
        )
    )


# ============================================================================
# Final API Response
# ============================================================================


def build_final_response(
    state: AgentState,
) -> Dict[str, Any]:
    """
    Convert final AgentState into a clean API response.
    """

    return {
        "status": state.get("status"),

        "approved": _is_approved(state),

        "iteration": state.get(
            "iteration",
            0,
        ),

        "style_context": (
            state.get(
                "style_context"
            )
            or {}
        ),

        "outfit_plan": (
            state.get(
                "outfit_plan"
            )
            or {}
        ),

        # Preserve the raw per-item shopping results.
        "shopping_results": (
            state.get(
                "shopping_results"
            )
            or []
        ),

        # All actual products retrieved by Shopping Agent.
        "product_candidates": (
            state.get(
                "product_candidates"
            )
            or []
        ),

        # Products selected by Product Ranker.
        "selected_products": (
            state.get(
                "selected_products"
            )
            or []
        ),

        # Fitting Room output.
        "fitting_room": (
            state.get(
                "fitting_room"
            )
            or {}
        ),

        # Critic decision.
        "critic_feedback": (
            state.get(
                "critic_feedback"
            )
            or {}
        ),
    }


# ============================================================================
# Direct Test
# ============================================================================


if __name__ == "__main__":

    import json

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    async def main() -> None:

        state = await run_orchestrator_async(
            user_profile={
                "age": 24,
                "gender": "Female",
                "body_shape": "rectangle",
                "skin_tone": "warm",
                "height": 165,
                "weight": 55,
            },
            user_query=(
                "I need a semi-formal outfit "
                "for an indoor wedding "
                "under ₹5,000"
            ),
        )

        print(
            json.dumps(
                build_final_response(state),
                indent=4,
                ensure_ascii=False,
                default=str,
            )
        )

    asyncio.run(main())