"""
Part 50 tests: LangGraph orchestration.

The LLM-dependent / I/O stages are stubbed so the graph's routing can be
driven deterministically (approve / revise / revision limit / stage failure).
Everything else (routing helpers, _prepare_revision, _is_approved,
build_final_response, state handling) is the real Part 49 code.
"""

import asyncio

import pytest

from backend.agents import langgraph_workflow as lg
from backend.agents import orchestrator as orch
from backend.agents.product_ranker import ProductRankerError


PROFILE = {
    "age": 24,
    "gender": "Female",
    "body_shape": "rectangle",
    "skin_tone": "warm",
    "height": 165,
    "weight": 55,
}


class Harness:
    """Installs stub stages on the orchestrator module and records the call order."""

    def __init__(self, monkeypatch, critic_script=None):
        self.calls = []
        self.critic_script = list(critic_script or ["approve"])
        self.critic_calls = 0
        self.shopping_error = None
        self.shopping_empty = False
        self.ranker_error = False
        self.ranker_empty = False
        self.fitting_error = False
        self.critic_error = False

        def profile(state):
            self.calls.append("profile")
            state["style_context"] = {
                "profile": state["user_profile"],
                "requirements": {"occasion": "test", "budget": 5000},
            }
            return state

        def stylist(state):
            self.calls.append("stylist")
            state["outfit_plan"] = {
                "occasion": "test",
                "budget": 5000,
                "items": [{"category": "Top", "item": "top"}],
                "accessories": [],
            }
            return state

        async def shopping(state):
            self.calls.append("shopping")
            if self.shopping_error:
                raise RuntimeError(self.shopping_error)
            if self.shopping_empty:
                state["shopping_results"] = []
                state["product_candidates"] = []
                return state
            state["shopping_results"] = [{"index": 0, "products": [{"product_id": "P1"}]}]
            state["product_candidates"] = [{"product_id": "P1", "item_index": 0}]
            return state

        async def ranker(state):
            self.calls.append("ranking")
            if self.ranker_error:
                raise ProductRankerError("boom")
            state["selected_products"] = (
                [] if self.ranker_empty
                else [{"product_id": "P1", "category": "tops", "price": 999}]
            )
            return state

        async def fitting(state):
            self.calls.append("fitting")
            if self.fitting_error:
                raise RuntimeError("fitting boom")
            state["fitting_room"] = {"status": "complete", "items": []}
            return state

        async def critic(state):
            self.calls.append("critic")
            if self.critic_error:
                raise RuntimeError("critic boom")
            idx = min(self.critic_calls, len(self.critic_script) - 1)
            verdict = self.critic_script[idx]
            self.critic_calls += 1
            state["critic_feedback"] = {
                "status": verdict,
                "approved": verdict == "approve",
                "issues": [] if verdict == "approve" else [{"item": "top", "reason": "x"}],
            }
            return state

        monkeypatch.setattr(orch, "profile_agent", profile)
        monkeypatch.setattr(orch, "stylist_agent", stylist)
        monkeypatch.setattr(orch, "_run_shopping", shopping)
        monkeypatch.setattr(orch, "_run_product_ranker", ranker)
        monkeypatch.setattr(orch, "_run_fitting_room", fitting)
        monkeypatch.setattr(orch, "_run_critic", critic)

    def run(self, query="test"):
        return asyncio.run(
            lg.run_langgraph_workflow_async(PROFILE, query)
        )


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------


def test_graph_has_the_expected_nodes():
    nodes = set(lg.get_compiled_graph().get_graph().nodes)
    for name in (
        "profile_node", "stylist_node", "shopping_node", "ranking_node",
        "fitting_node", "critic_node", "wardrobe_node", "final_node",
    ):
        assert name in nodes


def test_state_has_shopping_results_field():
    from backend.agents.state import AgentState
    assert "shopping_results" in AgentState.__annotations__


# ---------------------------------------------------------------------------
# Approve path
# ---------------------------------------------------------------------------


def test_approve_path_runs_each_stage_once_and_ends(monkeypatch):
    h = Harness(monkeypatch, ["approve"])
    state = h.run()

    assert h.calls == ["profile", "stylist", "shopping", "ranking", "fitting", "critic"]
    assert state["status"] == "approved"
    assert state["iteration"] == 0
    assert state["selected_products"][0]["product_id"] == "P1"
    assert state["fitting_room"]["status"] == "complete"
    assert orch.build_final_response(state)["approved"] is True


# ---------------------------------------------------------------------------
# Revise path
# ---------------------------------------------------------------------------


def test_revise_then_approve_reruns_from_profile(monkeypatch):
    h = Harness(monkeypatch, ["revise", "approve"])
    state = h.run()

    one_pass = ["profile", "stylist", "shopping", "ranking", "fitting", "critic"]
    assert h.calls == one_pass + one_pass
    assert state["status"] == "approved"
    assert state["iteration"] == 1


# ---------------------------------------------------------------------------
# Revision limit
# ---------------------------------------------------------------------------


def test_always_revise_stops_at_the_revision_limit(monkeypatch):
    h = Harness(monkeypatch, ["revise"])
    state = h.run()

    assert state["status"] == "rejected"
    assert state["iteration"] == orch.MAX_REVISIONS
    assert h.calls.count("profile") == orch.MAX_REVISIONS + 1
    assert h.calls.count("critic") == orch.MAX_REVISIONS + 1
    assert orch.build_final_response(state)["approved"] is False


def test_limit_respects_a_changed_max_revisions(monkeypatch):
    monkeypatch.setattr(orch, "MAX_REVISIONS", 0)
    h = Harness(monkeypatch, ["revise"])
    state = h.run()

    assert state["status"] == "rejected"
    assert h.calls.count("profile") == 1


# ---------------------------------------------------------------------------
# Stage failures (Part 49: skip remaining stages -> revise or reject)
# ---------------------------------------------------------------------------


def test_shopping_exception_skips_later_stages_and_hits_limit(monkeypatch):
    h = Harness(monkeypatch)
    h.shopping_error = "mcp down"
    state = h.run()

    assert state["status"] == "rejected"
    assert state["iteration"] == orch.MAX_REVISIONS
    assert "ranking" not in h.calls
    assert "critic" not in h.calls
    assert "mcp down" in state["critic_feedback"]["issues"][0]


def test_no_candidates_is_a_stage_failure(monkeypatch):
    h = Harness(monkeypatch)
    h.shopping_empty = True
    state = h.run()

    assert state["status"] == "rejected"
    assert "ranking" not in h.calls
    assert state["critic_feedback"]["issues"] == ["No product candidates were found."]


def test_ranker_error_is_a_stage_failure(monkeypatch):
    h = Harness(monkeypatch)
    h.ranker_error = True
    state = h.run()

    assert state["status"] == "rejected"
    assert "fitting" not in h.calls
    assert state["critic_feedback"]["issues"] == ["boom"]


def test_ranker_selecting_nothing_is_a_stage_failure(monkeypatch):
    h = Harness(monkeypatch)
    h.ranker_empty = True
    state = h.run()

    assert state["status"] == "rejected"
    assert "fitting" not in h.calls
    assert state["critic_feedback"]["issues"] == ["Product Ranker selected no products."]


def test_fitting_room_exception_is_a_stage_failure(monkeypatch):
    h = Harness(monkeypatch)
    h.fitting_error = True
    state = h.run()

    assert state["status"] == "rejected"
    assert "critic" not in h.calls


def test_critic_exception_means_not_approved_then_revise(monkeypatch):
    h = Harness(monkeypatch)
    h.critic_error = True
    state = h.run()

    assert state["status"] == "rejected"
    assert h.calls.count("critic") == orch.MAX_REVISIONS + 1


def test_recovers_after_one_failed_pass(monkeypatch):
    h = Harness(monkeypatch, ["approve"])
    h.shopping_empty = True

    original = orch._run_shopping

    async def flaky(state):
        # fail the first pass only
        if h.calls.count("shopping") == 0:
            h.shopping_empty = True
        else:
            h.shopping_empty = False
        return await original(state)

    monkeypatch.setattr(orch, "_run_shopping", flaky)
    state = h.run()

    assert state["status"] == "approved"
    assert state["iteration"] == 1


# ---------------------------------------------------------------------------
# Parity with the Part 49 loop
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "script",
    [["approve"], ["revise", "approve"], ["revise"]],
)
def test_langgraph_matches_legacy_loop(monkeypatch, script):
    h = Harness(monkeypatch, script)
    legacy = asyncio.run(orch.run_orchestrator_legacy_async(PROFILE, "test"))
    legacy_calls = list(h.calls)

    h2 = Harness(monkeypatch, script)
    graph_state = asyncio.run(orch.run_orchestrator_async(PROFILE, "test"))

    assert h2.calls == legacy_calls
    assert orch.build_final_response(graph_state) == orch.build_final_response(legacy)


def test_orchestrator_entry_points_delegate_to_langgraph(monkeypatch):
    h = Harness(monkeypatch, ["approve"])
    state = orch.run_orchestrator(PROFILE, "test")  # sync wrapper
    assert state["status"] == "approved"
    assert h.calls[0] == "profile"