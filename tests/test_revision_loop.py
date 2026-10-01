"""
Part 48 tests: revision loop reuses CriticAgent and ShoppingAgent, nothing else.
"""

from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest

from backend.agents import revision_loop as loop_module
from backend.agents import shopping_agent as shopping_module
from backend.agents.critic_agent import (
    MISSING_REASON,
    PALETTE_REASON,
    UNAVAILABLE_REASON,
    CriticAgent,
    CriticIssue,
    CriticResult,
)
from backend.agents.revision_loop import MAX_ITERATIONS, RevisionLoop


PROJECT_ROOT = Path(__file__).resolve().parents[1]

CATALOG: List[Dict[str, Any]] = json.loads(
    (PROJECT_ROOT / "data" / "products" / "products.json").read_text(
        encoding="utf-8"
    )
)

BY_ID = {p["product_id"]: p for p in CATALOG}


def run(coro):
    return asyncio.run(coro)


def product(
    pid,
    category,
    color,
    price,
    title,
    **extra,
):
    return {
        "product_id": pid,
        "store": "Demo",
        "brand": "B",
        "title": title,
        "category": category,
        "color": color,
        "price": price,
        "currency": "INR",
        "sizes": ["M"],
        "image_url": None,
        "product_url": f"https://www.example.test/product/{pid}",
        "availability": True,
        **extra,
    }


NAVY_SHIRT = product(
    "S-NAVY",
    "shirts",
    "navy",
    1000,
    "Navy Shirt",
)

BLACK_SHIRT = product(
    "S-BLACK",
    "shirts",
    "black",
    1100,
    "Black Shirt",
)

PANTS = product(
    "P-CREAM",
    "pants",
    "cream",
    1500,
    "Cream Trousers",
)

SHOES = product(
    "SH-BROWN",
    "shoes",
    "brown",
    1800,
    "Brown Loafers",
)

GOOD_SHOES = product(
    "SH-BROWN2",
    "shoes",
    "brown",
    1700,
    "Brown Derby Shoes",
)


PLAN = {
    "occasion": "indoor wedding",
    "style": "elegant",
    "color_palette": ["black", "cream", "brown"],
    "items": [
        {"category": "shirt", "color": "black"},
        {"category": "pants", "color": "cream"},
        {"category": "shoes", "color": "brown"},
    ],
    "accessories": [],
    "budget": 5000,
}


def revise(*pairs):
    return CriticResult(
        status="revise",
        issues=[
            CriticIssue(item=item, reason=reason)
            for item, reason in pairs
        ],
    )


APPROVE = CriticResult(
    status="approve",
    issues=[],
)


class FakeCritic:
    """Returns scripted results and records each call."""

    def __init__(self, *results):
        self.results = list(results)
        self.calls: List[Dict[str, Any]] = []

    def evaluate(self, **kwargs):
        self.calls.append(
            {
                **kwargs,
                "selected_products": list(
                    kwargs["selected_products"]
                ),
            }
        )

        return self.results[
            min(
                len(self.calls) - 1,
                len(self.results) - 1,
            )
        ]


class FakeShopping:
    """Stands in for ShoppingAgent and records every call."""

    def __init__(
        self,
        *,
        search=None,
        alternatives=None,
    ):
        self.search_map: Dict[Tuple[str, Any], list] = (
            search or {}
        )

        self.alt_map: Dict[str, list] = alternatives or {}

        self.search_calls: List[Dict[str, Any]] = []
        self.alt_calls: List[str] = []

    async def search(
        self,
        query="",
        budget=None,
        category=None,
        color=None,
        size=None,
    ):
        self.search_calls.append(
            {
                "category": category,
                "color": color,
                "budget": budget,
            }
        )

        return copy.deepcopy(
            self.search_map.get(
                (category, color),
                [],
            )
        )

    async def get_alternatives(
        self,
        product_id,
        limit=5,
    ):
        self.alt_calls.append(product_id)

        return copy.deepcopy(
            self.alt_map.get(
                product_id,
                [],
            )
        )


def make_loop(
    critic,
    shopping,
    **kwargs,
):
    return RevisionLoop(
        shopping_agent=shopping,
        critic=critic,
        **kwargs,
    )


def go(
    loop,
    products,
    **kwargs,
):
    kwargs.setdefault(
        "outfit_plan",
        PLAN,
    )

    kwargs.setdefault(
        "user_request",
        "indoor wedding outfit",
    )

    return run(
        loop.run(
            selected_products=products,
            **kwargs,
        )
    )


def ids(products):
    return [
        p["product_id"]
        for p in products
    ]


# ---------------------------------------------------------------------------
# 1. Maximum iterations
# ---------------------------------------------------------------------------


def test_max_iterations_is_two():
    assert MAX_ITERATIONS == 2


# ---------------------------------------------------------------------------
# 2 + 3. Immediate approval / revision
# ---------------------------------------------------------------------------


def test_critic_approves_immediately():
    critic = FakeCritic(APPROVE)
    shopping = FakeShopping()

    result = go(
        make_loop(critic, shopping),
        [BLACK_SHIRT, PANTS, SHOES],
    )

    assert result.status == "approve"
    assert result.stop_reason == "approved"
    assert result.iterations == 0
    assert result.critic_evaluations == 1

    assert len(critic.calls) == 1
    assert result.steps == []

    assert shopping.search_calls == []
    assert shopping.alt_calls == []

    assert ids(result.selected_products) == [
        "S-BLACK",
        "P-CREAM",
        "SH-BROWN",
    ]


def test_revision_replaces_only_the_requested_item_then_critic_runs_again():
    critic = FakeCritic(
        revise(("shirt", PALETTE_REASON)),
        APPROVE,
    )

    shopping = FakeShopping(
        search={
            ("shirts", "black"): [
                BLACK_SHIRT,
            ]
        }
    )

    original = [
        NAVY_SHIRT,
        PANTS,
        SHOES,
    ]

    result = go(
        make_loop(critic, shopping),
        original,
    )

    assert len(critic.calls) == 2

    assert shopping.search_calls[0]["category"] == "shirts"
    assert shopping.search_calls[0]["color"] == "black"

    revised_seen_by_critic = (
        critic.calls[1]["selected_products"]
    )

    assert revised_seen_by_critic[0] == BLACK_SHIRT

    # Untouched objects remain the same objects.
    assert revised_seen_by_critic[1] is PANTS
    assert revised_seen_by_critic[2] is SHOES

    assert ids(result.selected_products) == [
        "S-BLACK",
        "P-CREAM",
        "SH-BROWN",
    ]


def test_approves_after_one_revision():
    critic = FakeCritic(
        revise(("shirt", PALETTE_REASON)),
        APPROVE,
    )

    shopping = FakeShopping(
        search={
            ("shirts", "black"): [
                BLACK_SHIRT,
            ]
        }
    )

    result = go(
        make_loop(critic, shopping),
        [NAVY_SHIRT, PANTS, SHOES],
    )

    assert result.status == "approve"
    assert result.stop_reason == "approved"
    assert result.iterations == 1
    assert result.critic_evaluations == 2

    assert result.critic_result.issues == []

    step = result.steps[0]

    assert (
        step.action,
        step.old_product_id,
        step.new_product_id,
        step.source,
    ) == (
        "replaced",
        "S-NAVY",
        "S-BLACK",
        "search",
    )


def test_unavailable_item_is_replaced_from_alternatives():
    gone = {
        **NAVY_SHIRT,
        "availability": False,
    }

    bad_alt = {
        **BLACK_SHIRT,
        "product_id": "S-GONE",
        "availability": False,
    }

    critic = FakeCritic(
        revise(("shirt", UNAVAILABLE_REASON)),
        APPROVE,
    )

    shopping = FakeShopping(
        alternatives={
            "S-NAVY": [
                bad_alt,
                BLACK_SHIRT,
            ]
        }
    )

    result = go(
        make_loop(critic, shopping),
        [gone, PANTS, SHOES],
    )

    assert shopping.alt_calls == ["S-NAVY"]
    assert shopping.search_calls == []

    assert ids(result.selected_products)[0] == "S-BLACK"
    assert result.steps[0].source == "alternatives"


def test_missing_item_is_added_with_a_budget_cap():
    critic = FakeCritic(
        revise(("shoes", MISSING_REASON)),
        APPROVE,
    )

    shopping = FakeShopping(
        search={
            ("shoes", "brown"): [
                SHOES,
            ]
        }
    )

    result = go(
        make_loop(critic, shopping),
        [BLACK_SHIRT, PANTS],
    )

    assert shopping.search_calls == [
        {
            "category": "shoes",
            "color": "brown",
            "budget": 5000 - 1100 - 1500,
        }
    ]

    assert ids(result.selected_products) == [
        "S-BLACK",
        "P-CREAM",
        "SH-BROWN",
    ]

    assert result.steps[0].action == "added"


# ---------------------------------------------------------------------------
# 4. Iteration limits
# ---------------------------------------------------------------------------


def test_stops_at_max_iterations_and_keeps_remaining_issues():
    still = revise(
        ("shirt", PALETTE_REASON),
        ("shoes", UNAVAILABLE_REASON),
    )

    critic = FakeCritic(still)

    shopping = FakeShopping(
        search={
            ("shirts", "black"): [
                BLACK_SHIRT,
            ]
        },
        alternatives={
            "SH-BROWN": [
                GOOD_SHOES,
            ]
        },
    )

    result = go(
        make_loop(critic, shopping),
        [NAVY_SHIRT, PANTS, SHOES],
    )

    assert result.status == "revise"
    assert result.stop_reason == "iteration_limit"

    assert result.iterations == MAX_ITERATIONS
    assert result.critic_evaluations == MAX_ITERATIONS + 1

    assert len(critic.calls) == 3

    assert result.critic_result.issues == still.issues

    assert (
        len(shopping.search_calls)
        + len(shopping.alt_calls)
        == 2
    )


def test_same_issue_forever_does_not_loop():
    critic = FakeCritic(
        revise(("shirt", PALETTE_REASON))
    )

    shopping = FakeShopping(
        search={
            ("shirts", "black"): [
                BLACK_SHIRT,
            ]
        }
    )

    result = go(
        make_loop(critic, shopping),
        [NAVY_SHIRT, PANTS, SHOES],
    )

    assert result.iterations == 1
    assert result.stop_reason == "no_actionable_issue"
    assert result.status == "revise"

    assert len(shopping.search_calls) == 1


def test_max_iterations_is_configurable():
    critic = FakeCritic(
        revise(
            ("shirt", PALETTE_REASON),
            ("shoes", UNAVAILABLE_REASON),
        )
    )

    shopping = FakeShopping(
        search={
            ("shirts", "black"): [
                BLACK_SHIRT,
            ]
        },
        alternatives={
            "SH-BROWN": [
                GOOD_SHOES,
            ]
        },
    )

    result = go(
        make_loop(
            critic,
            shopping,
            max_iterations=1,
        ),
        [NAVY_SHIRT, PANTS, SHOES],
    )

    assert result.iterations == 1
    assert result.stop_reason == "iteration_limit"


# ---------------------------------------------------------------------------
# 5. Issue ordering
# ---------------------------------------------------------------------------


def test_one_issue_per_iteration_in_critic_order():
    issues = revise(
        ("shirt", PALETTE_REASON),
        ("shoes", UNAVAILABLE_REASON),
    )

    shopping = FakeShopping(
        search={
            ("shirts", "black"): [
                BLACK_SHIRT,
            ]
        },
        alternatives={
            "SH-BROWN": [
                GOOD_SHOES,
            ]
        },
    )

    critic = FakeCritic(issues)

    result = go(
        make_loop(critic, shopping),
        [NAVY_SHIRT, PANTS, SHOES],
    )

    assert [s.item for s in result.steps] == [
        "shirt",
        "shoes",
    ]

    assert [s.iteration for s in result.steps] == [
        1,
        2,
    ]

    assert ids(
        critic.calls[1]["selected_products"]
    ) == [
        "S-BLACK",
        "P-CREAM",
        "SH-BROWN",
    ]

    assert ids(
        critic.calls[2]["selected_products"]
    ) == [
        "S-BLACK",
        "P-CREAM",
        "SH-BROWN2",
    ]


def test_outfit_level_issues_are_skipped_not_guessed():
    critic = FakeCritic(
        revise(
            (
                "outfit",
                "Selected outfit exceeds the provided budget",
            ),
            ("shirt", PALETTE_REASON),
        ),
        APPROVE,
    )

    shopping = FakeShopping(
        search={
            ("shirts", "black"): [
                BLACK_SHIRT,
            ]
        }
    )

    result = go(
        make_loop(critic, shopping),
        [NAVY_SHIRT, PANTS, SHOES],
    )

    assert [s.item for s in result.steps] == [
        "shirt"
    ]


def test_outfit_level_issue_alone_is_left_for_the_caller():
    issue = revise(
        (
            "outfit",
            "Selected outfit exceeds the provided budget",
        )
    )

    shopping = FakeShopping()

    result = go(
        make_loop(
            FakeCritic(issue),
            shopping,
        ),
        [NAVY_SHIRT, PANTS, SHOES],
    )

    assert result.iterations == 0
    assert result.stop_reason == "no_actionable_issue"
    assert result.critic_result.issues == issue.issues

    assert shopping.search_calls == []
    assert shopping.alt_calls == []


def test_runs_are_deterministic():
    def once():
        critic = FakeCritic(
            revise(
                ("shirt", PALETTE_REASON),
                ("shoes", UNAVAILABLE_REASON),
            )
        )

        shopping = FakeShopping(
            search={
                ("shirts", "black"): [
                    BLACK_SHIRT,
                ]
            },
            alternatives={
                "SH-BROWN": [
                    GOOD_SHOES,
                ]
            },
        )

        return go(
            make_loop(critic, shopping),
            [NAVY_SHIRT, PANTS, SHOES],
        ).model_dump()

    assert once() == once()


# ---------------------------------------------------------------------------
# 6. Unresolved revisions
# ---------------------------------------------------------------------------


def test_no_replacement_keeps_the_existing_product_and_reports_unresolved():
    original = [
        NAVY_SHIRT,
        PANTS,
        SHOES,
    ]

    critic = FakeCritic(
        revise(("shirt", PALETTE_REASON))
    )

    shopping = FakeShopping()

    result = go(
        make_loop(critic, shopping),
        original,
    )

    assert result.selected_products == original
    assert result.status == "revise"
    assert result.stop_reason == "no_actionable_issue"

    step = result.steps[0]

    assert step.action == "unresolved"
    assert step.new_product_id is None
    assert step.old_product_id == "S-NAVY"
    assert step.detail

    assert len(critic.calls) == 1

    assert result.critic_result.issues == (
        critic.results[0].issues
    )


def test_unusable_candidates_are_rejected_not_fabricated():
    same = copy.deepcopy(NAVY_SHIRT)

    wrong_category = product(
        "X1",
        "pants",
        "black",
        100,
        "Black Pants",
    )

    unavailable = {
        **BLACK_SHIRT,
        "availability": False,
    }

    shopping = FakeShopping(
        search={
            ("shirts", "black"): [
                same,
                wrong_category,
                unavailable,
            ]
        }
    )

    result = go(
        make_loop(
            FakeCritic(
                revise(("shirt", PALETTE_REASON))
            ),
            shopping,
        ),
        [NAVY_SHIRT, PANTS, SHOES],
    )

    assert result.steps[0].action == "unresolved"

    assert ids(result.selected_products) == [
        "S-NAVY",
        "P-CREAM",
        "SH-BROWN",
    ]


def test_unresolved_first_issue_moves_on_to_the_next_one():
    critic = FakeCritic(
        revise(
            ("shirt", PALETTE_REASON),
            ("shoes", UNAVAILABLE_REASON),
        ),
        APPROVE,
    )

    shopping = FakeShopping(
        alternatives={
            "SH-BROWN": [
                GOOD_SHOES,
            ]
        }
    )

    result = go(
        make_loop(critic, shopping),
        [NAVY_SHIRT, PANTS, SHOES],
    )

    assert [
        (s.item, s.action)
        for s in result.steps
    ] == [
        ("shirt", "unresolved"),
        ("shoes", "replaced"),
    ]

    assert ids(result.selected_products) == [
        "S-NAVY",
        "P-CREAM",
        "SH-BROWN2",
    ]

    assert result.iterations == 2
    assert result.status == "approve"


# ---------------------------------------------------------------------------
# 7. Input immutability
# ---------------------------------------------------------------------------


def test_inputs_are_not_mutated():
    products = [
        copy.deepcopy(NAVY_SHIRT),
        copy.deepcopy(PANTS),
        copy.deepcopy(SHOES),
    ]

    plan = copy.deepcopy(PLAN)

    snapshot = (
        copy.deepcopy(products),
        copy.deepcopy(plan),
        list(products),
    )

    critic = FakeCritic(
        revise(("shirt", PALETTE_REASON)),
        APPROVE,
    )

    shopping = FakeShopping(
        search={
            ("shirts", "black"): [
                BLACK_SHIRT,
            ]
        }
    )

    result = go(
        make_loop(critic, shopping),
        products,
        outfit_plan=plan,
    )

    assert products == snapshot[0]
    assert plan == snapshot[1]

    assert all(
        a is b
        for a, b in zip(
            products,
            snapshot[2],
        )
    )

    assert ids(result.selected_products)[0] == "S-BLACK"

    # The new product is detached from the shopping result.
    assert result.selected_products[0] is not BLACK_SHIRT


# ---------------------------------------------------------------------------
# 8. No forbidden dependencies
# ---------------------------------------------------------------------------


def test_orchestrator_has_no_store_mcp_network_or_image_code():
    source = Path(
        loop_module.__file__
    ).read_text(
        encoding="utf-8"
    )

    for forbidden in (
        "MockStore",
        "mcp_server",
        "MCPShoppingClient",
        "mcp_client",
        "fitting_room",
        "httpx",
        "requests",
        "urllib",
        "socket",
        "openai",
        "PIL",
        "image_url",
    ):
        assert forbidden not in source


# ---------------------------------------------------------------------------
# 9. Real ShoppingAgent + fake MCP
# ---------------------------------------------------------------------------


class FakeMCPClient:
    """
    Replaces MCPShoppingClient inside the real ShoppingAgent.

    This allows the end-to-end test to exercise:

        RevisionLoop
            -> ShoppingAgent
                -> MCPShoppingClient

    without making network calls.
    """

    instances: List["FakeMCPClient"] = []

    def __init__(self):
        self.calls: List[tuple] = []
        FakeMCPClient.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def search_products(
        self,
        query="",
        budget=None,
        category=None,
        color=None,
    ):
        self.calls.append(
            (
                "search_products",
                category,
                color,
                budget,
            )
        )

        return [
            dict(p)
            for p in CATALOG
            if (
                category is None
                or p["category"] == category
            )
            and (
                color is None
                or p["color"] == color
            )
            and (
                budget is None
                or p["price"] <= budget
            )
        ]

    async def check_availability(
        self,
        product_id,
        size=None,
    ):
        return {
            "product_id": product_id,
            "available": True,
        }


def test_end_to_end_with_real_critic_and_real_shopping_agent(
    monkeypatch,
):
    """
    End-to-end Part 48 test.

    IMPORTANT:
    Do not monkeypatch socket.socket.connect here.

    On Windows asyncio itself uses socketpair() when creating
    the event loop. Patching socket.connect breaks asyncio before
    RevisionLoop.run() even starts.
    """

    FakeMCPClient.instances.clear()

    # Replace the MCP layer used by the real ShoppingAgent.
    monkeypatch.setattr(
        shopping_module,
        "MCPShoppingClient",
        FakeMCPClient,
    )

    selected = [
        dict(BY_ID["MOCK003"]),
        dict(BY_ID["MOCK012"]),
        dict(BY_ID["MOCK027"]),
    ]

    originals = copy.deepcopy(selected)

    result = run(
        RevisionLoop().run(
            outfit_plan=PLAN,
            selected_products=selected,
            user_request="indoor wedding outfit",
            budget=5000,
        )
    )

    assert result.status == "approve"
    assert result.stop_reason == "approved"
    assert result.iterations == 1

    assert ids(result.selected_products) == [
        "MOCK001",
        "MOCK012",
        "MOCK027",
    ]

    assert result.selected_products[0] == (
        BY_ID["MOCK001"]
    )

    # Caller-owned data must remain untouched.
    assert selected == originals

    # Every shopping call went through:
    #
    # RevisionLoop
    #      ↓
    # ShoppingAgent
    #      ↓
    # FakeMCPClient
    #
    calls = [
        call
        for client in FakeMCPClient.instances
        for call in client.calls
    ]

    assert calls
    assert all(
        call[0] == "search_products"
        for call in calls
    )

    assert calls[0][1:3] == (
        "shirts",
        "black",
    )