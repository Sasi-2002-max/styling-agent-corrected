"""Part 47 tests: CriticAgent is deterministic, pure, and never shops."""

from __future__ import annotations

import copy
import socket
from pathlib import Path

import pytest
from pydantic import BaseModel

from backend.agents import critic_agent as critic_module
from backend.agents import shopping_agent as shopping_module
from backend.agents.critic_agent import (
    BUDGET_REASON,
    CriticAgent,
    CriticIssue,
    CriticResult,
    MISSING_REASON,
)


def product(pid, category, color, price, title, **extra):
    return {
        "product_id": pid,
        "store": "Demo Fashion",
        "brand": "Brand",
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


SHIRT = product("MOCK001", "shirts", "black", 1299, "Black Oxford Shirt")
PANTS = product("MOCK012", "pants", "cream", 1699, "Cream Straight Trousers")
SHOES = product("MOCK027", "shoes", "brown", 1899, "Brown Leather Loafers")

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


def evaluate(plan=PLAN, products=(SHIRT, PANTS, SHOES), **kwargs):
    kwargs.setdefault("user_request", "I need an indoor wedding outfit under 5000")
    return CriticAgent().evaluate(outfit_plan=plan, selected_products=list(products), **kwargs)


def reasons(result):
    return {(i.item, i.reason) for i in result.issues}


# 1 + 6 -----------------------------------------------------------------------


def test_approves_valid_outfit_with_empty_issues():
    result = evaluate(budget=5000)
    assert isinstance(result, CriticResult)
    assert result.status == "approve"
    assert result.issues == []
    assert result.model_dump() == {"status": "approve", "issues": []}


# 2 ---------------------------------------------------------------------------


def test_revises_when_over_budget():
    pricey = product("MOCK999", "shoes", "brown", 4000, "Brown Leather Loafers")
    result = evaluate(products=(SHIRT, PANTS, pricey), budget=5000)
    assert result.status == "revise"
    assert ("outfit", BUDGET_REASON) in reasons(result)


def test_budget_equal_to_total_is_fine():
    assert evaluate(budget=1299 + 1699 + 1899).status == "approve"


def test_plan_budget_used_when_no_explicit_budget():
    tight = {**PLAN, "budget": 1000}
    assert ("outfit", BUDGET_REASON) in reasons(evaluate(plan=tight))


def test_no_budget_supplied_is_never_invented():
    plan = {k: v for k, v in PLAN.items() if k != "budget"}
    result, notes = CriticAgent().evaluate_with_notes(
        outfit_plan=plan, selected_products=[SHIRT, PANTS, SHOES],
        user_request="indoor wedding",
    )
    assert result.status == "approve"
    assert any(n.startswith("budget:") for n in notes)


def test_partial_prices_flag_only_when_already_over_budget():
    no_price = {**SHOES, "price": None}
    assert evaluate(products=(SHIRT, PANTS, no_price), budget=5000).status == "approve"
    assert ("outfit", BUDGET_REASON) in reasons(
        evaluate(products=(SHIRT, PANTS, no_price), budget=2000)
    )


def test_mixed_currencies_skip_the_budget_check():
    usd = {**SHOES, "currency": "USD", "price": 99999}
    result, notes = CriticAgent().evaluate_with_notes(
        outfit_plan=PLAN, selected_products=[SHIRT, PANTS, usd], budget=100,
        user_request="indoor wedding",
    )
    assert ("outfit", BUDGET_REASON) not in reasons(result)
    assert any("currencies" in n for n in notes)


# 3 ---------------------------------------------------------------------------


def test_revises_when_required_item_is_missing():
    result = evaluate(products=(SHIRT, PANTS), budget=5000)
    assert result.status == "revise"
    assert reasons(result) == {("shoes", MISSING_REASON)}


def test_accessories_in_the_plan_are_required_too():
    plan = {**PLAN, "accessories": [{"category": "watch", "color": "silver"}]}
    assert ("watch", MISSING_REASON) in reasons(evaluate(plan=plan, budget=5000))


def test_nothing_selected_is_reported_as_outfit_problem():
    result = evaluate(plan={"items": [], "accessories": []}, products=())
    assert result.status == "revise"
    assert result.issues[0].item == "outfit"


def test_unmappable_plan_item_is_skipped_not_invented():
    plan = {**PLAN, "items": PLAN["items"] + [{"category": "hologram", "color": "black"}]}
    result, notes = CriticAgent().evaluate_with_notes(
        outfit_plan=plan, selected_products=[SHIRT, PANTS, SHOES], budget=5000,
        user_request="indoor wedding",
    )
    assert result.status == "approve"
    assert any("cannot map" in n for n in notes)


# 4 ---------------------------------------------------------------------------


def test_revises_when_a_product_is_unavailable():
    gone = {**SHIRT, "availability": False}
    result = evaluate(products=(gone, PANTS, SHOES), budget=5000)
    assert ("shirt", "Selected product is unavailable") in reasons(result)


def test_revises_when_dress_is_combined_with_bottoms():
    dress = product("MOCK025", "dresses", "cream", 1000, "Cream Lace A-Line Dress")
    plan = {"occasion": "dinner", "items": [{"category": "dress"}], "accessories": []}
    result = evaluate(plan=plan, products=(dress, PANTS), budget=5000, user_request="dinner")
    assert [i.item for i in result.issues] == ["pants"]
    assert "dress" in result.issues[0].reason


def test_revises_when_color_is_outside_the_planned_palette():
    navy = {**SHIRT, "color": "navy", "title": "Navy Casual Shirt"}
    result = evaluate(products=(navy, PANTS, SHOES), budget=5000)
    assert result.status == "revise"
    assert result.issues[0].item == "shirt"
    assert "palette" in result.issues[0].reason


def test_too_many_accent_colors():
    plan = {"items": [{"category": "shirt"}, {"category": "pants"}, {"category": "shoes"}],
            "accessories": []}
    products = [
        {**SHIRT, "color": "red"},
        {**PANTS, "color": "teal"},
        {**SHOES, "color": "olive"},
    ]
    result = evaluate(plan=plan, products=products, user_request="", budget=9000)
    assert ("outfit", "Too many accent colors; keep to at most two non-neutral colors") in reasons(result)


def test_formal_occasion_flags_casual_items():
    tee = product("MOCK006", "t-shirts", "black", 599, "Black Graphic Tee")
    plan = {**PLAN, "items": [{"category": "t-shirt"}, {"category": "pants"}, {"category": "shoes"}]}
    result = evaluate(plan=plan, products=(tee, PANTS, SHOES), budget=5000)
    assert [(i.item, i.reason) for i in result.issues] == [
        ("t-shirt", "Too casual for the stated formal occasion")
    ]  # style check does not repeat the occasion issue


def test_formal_style_flags_casual_item_without_occasion():
    hoodie = product("H1", "tops", "black", 900, "Black Oversized Hoodie")
    plan = {"style": "elegant", "items": [{"category": "top"}], "accessories": []}
    result = evaluate(plan=plan, products=(hoodie,), user_request="dinner", budget=5000)
    assert ("top", "Too casual for the requested style") in reasons(result)


def test_profile_style_preferences_are_used():
    hoodie = product("H1", "tops", "black", 900, "Black Oversized Hoodie")
    plan = {"items": [{"category": "top"}], "accessories": []}
    result = evaluate(
        plan=plan, products=(hoodie,), user_request="dinner",
        user_profile={"style_preferences": ["formal"]},
    )
    assert ("top", "Too casual for the requested style") in reasons(result)


# 5 ---------------------------------------------------------------------------


def test_multiple_problems_return_multiple_issues():
    tee = product("MOCK006", "t-shirts", "black", 3000, "Black Graphic Tee")
    pants = {**PANTS, "price": 2500}
    result = evaluate(products=(tee, pants), budget=4000)
    assert result.status == "revise"
    assert len(result.issues) >= 4
    items = {i.item for i in result.issues}
    assert {"t-shirt", "outfit", "shirt", "shoes"} <= items


def test_issues_are_not_duplicated():
    result = evaluate(products=(SHIRT, SHIRT, PANTS, SHOES), budget=1)
    pairs = [(i.item, i.reason) for i in result.issues]
    assert len(pairs) == len(set(pairs))


# 7 ---------------------------------------------------------------------------


def test_makes_no_shopping_or_network_calls(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("CriticAgent must not shop or use the network")

    agent_cls = shopping_module.ShoppingAgent
    for name in (
        "search", "search_outfit", "build_outfit", "find_products",
        "get_product", "get_variants", "get_alternatives",
    ):
        monkeypatch.setattr(agent_cls, name, boom)
    monkeypatch.setattr(shopping_module, "MCPShoppingClient", boom)
    monkeypatch.setattr(socket.socket, "connect", boom)

    assert evaluate(budget=5000).status == "approve"
    assert evaluate(products=(SHIRT,), budget=1).status == "revise"


def test_source_has_no_shopping_store_or_network_dependencies():
    source = Path(critic_module.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "ShoppingAgent", "MCPShoppingClient", "MockStore", "mcp_server", "mcp_client",
        "fitting_room", "httpx", "requests", "urllib", "openai", "asyncio",
    ):
        assert forbidden not in source


# 8 ---------------------------------------------------------------------------


def test_missing_optional_information_is_not_invented():
    bare = [
        {"product_id": "A", "category": "shirts"},
        {"product_id": "B", "category": "pants"},
    ]
    plan = {"items": [{"category": "shirt"}, {"category": "pants"}], "accessories": []}

    result, notes = CriticAgent().evaluate_with_notes(outfit_plan=plan, selected_products=bare)

    assert result.model_dump() == {"status": "approve", "issues": []}
    joined = " ".join(notes)
    for area in ("budget:", "color:", "style:", "occasion:"):
        assert area in joined


def test_accepts_pydantic_products_and_profile_none():
    class P(BaseModel):
        product_id: str
        category: str
        color: str
        price: float
        title: str = "Black Oxford Shirt"

    plan = {"items": [{"category": "shirt"}], "accessories": []}
    result = evaluate(
        plan=plan, products=(P(product_id="1", category="shirts", color="black", price=10),),
        user_request="", user_profile=None, budget=100,
    )
    assert result.status == "approve"


# purity / determinism --------------------------------------------------------


def test_is_deterministic_and_does_not_mutate_inputs():
    plan = copy.deepcopy(PLAN)
    products = [copy.deepcopy(SHIRT), copy.deepcopy(PANTS)]
    snapshot = (copy.deepcopy(plan), copy.deepcopy(products))

    first = CriticAgent().evaluate(outfit_plan=plan, selected_products=products, budget=100)
    second = CriticAgent().evaluate(outfit_plan=plan, selected_products=products, budget=100)

    assert first == second
    assert (plan, products) == snapshot


def test_result_models_are_strict():
    with pytest.raises(Exception):
        CriticResult(status="maybe", issues=[])
    with pytest.raises(Exception):
        CriticIssue(item="shirt", reason="x", extra="no")