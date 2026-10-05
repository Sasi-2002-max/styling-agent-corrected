"""
LangGraph workflow (Part 50).

LangGraph is now the orchestration layer. It does NOT contain business
logic: every node calls the existing, already-tested implementation in
backend/agents/orchestrator.py (which in turn calls the Profile Agent,
Stylist Agent, ShoppingAgent + MCP, Product Ranker, FittingRoomService
and CriticAgent).

    FastAPI  ->  LangGraph  ->  existing agents/services  ->  MCP / RAG / ...

Graph (mirrors the real Part 49 behaviour):

    START
      |
      v
    profile_node
      |
      v
    stylist_node            (also runs the RAG stage, as in Part 49)
      |
      v
    shopping_node ----- stage failed? ----+
      |                                   |
      v                                   |
    ranking_node ------ stage failed? ----+
      |                                   |
      v                                   |
    fitting_node ------ stage failed? ----+
      |                                   |
      v                                   |
    critic_node                           |
      |                                   |
      +-- approved ---------> wardrobe_node --> final_node --> END
      |                                   |
      +-- not approved / failed stage ----+
              |
              +-- iteration >= MAX_REVISIONS --> final_node (rejected) --> END
              |
              +-- otherwise --> revision_node --> profile_node (full re-run)

Part 49 behaviour that is preserved:

* A revision is a FULL re-run from the Profile Agent. `_prepare_revision()`
  bumps `iteration` and clears outfit_plan / shopping_results /
  product_candidates / selected_products / fitting_room, but keeps
  `style_context` and `critic_feedback`.
* A failure in Shopping / Ranker / Fitting Room (exception, no candidates,
  nothing selected) skips the remaining stages and goes straight to the
  revise-or-reject decision. A Critic failure is treated as "not approved".
* Revision limit is `orchestrator.MAX_REVISIONS` (2): the workflow runs at
  most MAX_REVISIONS + 1 passes, then ends with status "rejected".

wardrobe_node is a deliberate no-op placeholder. The real wardrobe feature is
Part 51.
"""

from __future__ import annotations

import asyncio
import logging
from functools import lru_cache
from typing import Any, Dict, Literal, Optional, cast

from langgraph.graph import END, START, StateGraph

from backend.agents import orchestrator as orch
from backend.agents.product_ranker import ProductRankerError
from backend.agents.state import AgentState


logger = logging.getLogger(__name__)

# Marker written to state["status"] when Shopping / Ranker / Fitting Room
# could not produce a usable result. Routers read it; final_node overwrites it.
STAGE_FAILED = "stage_failed"

# Nodes executed in one full pass:
# profile, stylist, shopping, ranking, fitting, critic, revision.
_NODES_PER_PASS = 7
_RECURSION_BUFFER = 10


# ============================================================================
# Helpers
# ============================================================================


def _copy(state: AgentState) -> AgentState:
    """
    Shallow copy so the existing agents (which mutate and return the state)
    never modify LangGraph's input object.
    """
    return cast(AgentState, dict(state))


def _failure_feedback(message: str) -> Dict[str, Any]:
    """Same shape the Part 49 orchestrator used for stage failures."""
    return {
        "approved": False,
        "issues": [message],
        "source": "orchestrator",
    }


def _recursion_limit() -> int:
    """
    LangGraph's default limit (25 steps) is too small for 3 passes of 7
    nodes plus wardrobe/final, so set an explicit limit derived from
    MAX_REVISIONS. This is only a safety net; the router is what stops
    the loop.
    """
    passes = int(orch.MAX_REVISIONS) + 1
    return passes * _NODES_PER_PASS + 2 + _RECURSION_BUFFER


# ============================================================================
# Nodes
# ============================================================================


async def profile_node(state: AgentState) -> AgentState:
    iteration = int(state.get("iteration", 0))
    logger.info("LANGGRAPH: profile_node (iteration=%d)", iteration)

    working = _copy(state)

    # profile_agent is synchronous: keep it off the event loop.
    working = await asyncio.to_thread(orch.profile_agent, working)
    working = await orch._maybe_await(working)

    return cast(AgentState, working)


async def stylist_node(state: AgentState) -> AgentState:
    logger.info("LANGGRAPH: stylist_node")

    working = _copy(state)

    # stylist_agent is synchronous (blocking LLM calls): keep it off the loop.
    working = await asyncio.to_thread(orch.stylist_agent, working)
    working = await orch._maybe_await(working)

    # Part 49 ran a (pass-through) RAG stage right after the Stylist.
    working = orch._run_rag(working)

    return cast(AgentState, working)


async def shopping_node(state: AgentState) -> AgentState:
    logger.info("LANGGRAPH: shopping_node")

    working = _copy(state)

    try:
        working = await orch._run_shopping(working)
    except Exception as exc:
        logger.exception("Shopping stage failed.")
        working["product_candidates"] = []
        working["critic_feedback"] = _failure_feedback(
            f"Shopping failed: {exc}"
        )
        working["status"] = STAGE_FAILED
        return cast(AgentState, working)

    if not working.get("product_candidates"):
        logger.warning(
            "No product candidates were returned by Shopping Agent."
        )
        working["critic_feedback"] = _failure_feedback(
            "No product candidates were found."
        )
        working["status"] = STAGE_FAILED

    return cast(AgentState, working)


async def ranking_node(state: AgentState) -> AgentState:
    logger.info("LANGGRAPH: ranking_node")

    working = _copy(state)

    try:
        working = await orch._run_product_ranker(working)
    except ProductRankerError as exc:
        logger.exception("Product ranking failed.")
        working["selected_products"] = []
        working["critic_feedback"] = _failure_feedback(str(exc))
        working["status"] = STAGE_FAILED
        return cast(AgentState, working)

    if not working.get("selected_products"):
        logger.warning("Product Ranker did not select any products.")
        working["critic_feedback"] = _failure_feedback(
            "Product Ranker selected no products."
        )
        working["status"] = STAGE_FAILED

    return cast(AgentState, working)


async def fitting_node(state: AgentState) -> AgentState:
    logger.info("LANGGRAPH: fitting_node")

    working = _copy(state)

    try:
        working = await orch._run_fitting_room(working)
    except Exception as exc:
        logger.exception("Fitting Room failed.")
        working["fitting_room"] = {}
        working["critic_feedback"] = _failure_feedback(
            f"Fitting Room failed: {exc}"
        )
        working["status"] = STAGE_FAILED

    return cast(AgentState, working)


async def critic_node(state: AgentState) -> AgentState:
    logger.info("LANGGRAPH: critic_node")

    working = _copy(state)

    try:
        working = await orch._run_critic(working)
    except Exception as exc:
        # Part 49: a Critic failure is "not approved", NOT a skipped stage.
        logger.exception("Critic failed.")
        working["critic_feedback"] = _failure_feedback(
            f"Critic failed: {exc}"
        )

    return cast(AgentState, working)


async def revision_node(state: AgentState) -> AgentState:
    """
    Prepare another full pass (iteration += 1, clear plan/products,
    keep style_context + critic_feedback). Reuses Part 49's helper.
    """
    working = orch._prepare_revision(_copy(state))

    logger.info(
        "LANGGRAPH: revision_node -> starting revision %d",
        int(working.get("iteration", 0)),
    )

    return cast(AgentState, working)


async def wardrobe_node(state: AgentState) -> Dict[str, Any]:
    """
    PLACEHOLDER (no-op). Real wardrobe persistence is Part 51.

    Only reached for approved looks. It changes nothing so the workflow
    result is identical to Part 49.
    """
    logger.info("LANGGRAPH: wardrobe_node (placeholder, Part 51)")
    return {}


async def final_node(state: AgentState) -> AgentState:
    working = _copy(state)

    if orch._is_approved(working):
        working["status"] = "approved"
        logger.info(
            "LANGGRAPH: final_node status=approved iteration=%d",
            int(working.get("iteration", 0)),
        )
    else:
        working["status"] = "rejected"
        logger.warning(
            "LANGGRAPH: final_node status=rejected after %d revision(s)",
            int(working.get("iteration", 0)),
        )

    return cast(AgentState, working)


# ============================================================================
# Routing
# ============================================================================

Route = Literal["revision", "final"]


def _revise_or_stop(state: AgentState) -> Route:
    """
    Part 49 rule: if iteration >= MAX_REVISIONS stop (rejected),
    otherwise revise. This is what guarantees termination.
    """
    iteration = int(state.get("iteration", 0))

    if iteration >= int(orch.MAX_REVISIONS):
        logger.warning(
            "LANGGRAPH: route=final (revision limit %d reached)",
            int(orch.MAX_REVISIONS),
        )
        return "final"

    logger.info("LANGGRAPH: route=revise (iteration=%d)", iteration)
    return "revision"


def route_after_shopping(state: AgentState) -> Literal["ranking", "revision", "final"]:
    if state.get("status") == STAGE_FAILED:
        return _revise_or_stop(state)
    return "ranking"


def route_after_ranking(state: AgentState) -> Literal["fitting", "revision", "final"]:
    if state.get("status") == STAGE_FAILED:
        return _revise_or_stop(state)
    return "fitting"


def route_after_fitting(state: AgentState) -> Literal["critic", "revision", "final"]:
    if state.get("status") == STAGE_FAILED:
        return _revise_or_stop(state)
    return "critic"


def route_after_critic(state: AgentState) -> Literal["wardrobe", "revision", "final"]:
    if orch._is_approved(state):
        logger.info("LANGGRAPH: route=approve")
        return "wardrobe"
    return _revise_or_stop(state)


# ============================================================================
# Graph
# ============================================================================


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("profile_node", profile_node)
    graph.add_node("stylist_node", stylist_node)
    graph.add_node("shopping_node", shopping_node)
    graph.add_node("ranking_node", ranking_node)
    graph.add_node("fitting_node", fitting_node)
    graph.add_node("critic_node", critic_node)
    graph.add_node("revision_node", revision_node)
    graph.add_node("wardrobe_node", wardrobe_node)
    graph.add_node("final_node", final_node)

    graph.add_edge(START, "profile_node")
    graph.add_edge("profile_node", "stylist_node")
    graph.add_edge("stylist_node", "shopping_node")

    graph.add_conditional_edges(
        "shopping_node",
        route_after_shopping,
        {
            "ranking": "ranking_node",
            "revision": "revision_node",
            "final": "final_node",
        },
    )
    graph.add_conditional_edges(
        "ranking_node",
        route_after_ranking,
        {
            "fitting": "fitting_node",
            "revision": "revision_node",
            "final": "final_node",
        },
    )
    graph.add_conditional_edges(
        "fitting_node",
        route_after_fitting,
        {
            "critic": "critic_node",
            "revision": "revision_node",
            "final": "final_node",
        },
    )
    graph.add_conditional_edges(
        "critic_node",
        route_after_critic,
        {
            "wardrobe": "wardrobe_node",
            "revision": "revision_node",
            "final": "final_node",
        },
    )

    # Revision = full re-run from the Profile Agent (Part 49 behaviour).
    graph.add_edge("revision_node", "profile_node")

    graph.add_edge("wardrobe_node", "final_node")
    graph.add_edge("final_node", END)

    return graph


@lru_cache(maxsize=1)
def get_compiled_graph():
    """Compile once; node functions look up orchestrator helpers at call time."""
    return build_graph().compile()


# ============================================================================
# Entry point
# ============================================================================


async def run_langgraph_workflow_async(
    user_profile: Optional[Dict[str, Any]],
    user_query: str,
) -> AgentState:
    """
    Run the full styling workflow through LangGraph and return the final
    AgentState (same shape the Part 49 orchestrator returned, so
    build_final_response() keeps working unchanged).
    """
    initial_state = orch.create_initial_state(
        user_profile=user_profile,
        user_query=user_query,
    )

    logger.info("LANGGRAPH: start")

    result = await get_compiled_graph().ainvoke(
        initial_state,
        config={"recursion_limit": _recursion_limit()},
    )

    return cast(AgentState, result)