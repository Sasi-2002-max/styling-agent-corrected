"""
Regression tests for the shopping-demo fixes (Phase A):

  * shared category / colour vocabulary (backend/shopping/taxonomy.py)
  * relaxed colour matching for stylist-planned items (shade families)
  * explicit colour searches stay strict
  * budget reserve in the Product Ranker (whole outfit stays within budget)
  * critic palette check is shade-aware
  * the expanded mock catalog can complete the stylist's wedding outfit

Everything goes through the real MCP tool implementation and MockStore; only
the MCP transport (subprocess) is replaced by a thin in-process client.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import backend.agents.shopping_agent as shopping_agent_module
from backend.agents.critic_agent import CriticAgent
from backend.agents.product_ranker import select_products
from backend.agents.shopping_agent import ShoppingAgent, resolve_item_category
from backend.schemas.outfit import OutfitItem
from backend.shopping.stores.mock_store import MockStore
from backend.shopping.taxonomy import (
    CATEGORY_ALIASES,
    MATCH_EXACT,
    MATCH_FAMILY,
    MATCH_NONE,
    color_match_level,
)
from mcp_server.tools.search_products import search_products_impl


class InProcessClient:
    """Same data path as the MCP server: search_products_impl -> MockStore."""

    async def __aenter__(self) -> "InProcessClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    async def search_products(
        self,
        query: str = "",
        budget: Optional[float] = None,
        category: Optional[str] = None,
        color: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        return search_products_impl(
            query=query, category=category, color=color, budget=budget
        )

    async def check_availability(self, product_id: str, size: Optional[str] = None):
        return {"available": MockStore().check_availability(product_id, size)}


def _use_in_process_client(monkeypatch) -> None:
    monkeypatch.setattr(shopping_agent_module, "MCPShoppingClient", InProcessClient)


def _flatten(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    flat: List[Dict[str, Any]] = []
    for entry in entries:
        for product in entry["products"]:
            candidate = dict(product)
            candidate["item_index"] = entry["index"]
            candidate["item_source"] = entry["source"]
            candidate["outfit_item"] = entry["item"]
            flat.append(candidate)
    return flat


WEDDING_PLAN: Dict[str, Any] = {
    "occasion": "Indoor friend wedding",
    "style": "Elegant",
    "color_palette": ["emerald green", "royal blue", "deep burgundy", "soft gold"],
    "items": [
        {"category": "Top", "item": "Fitted half\u2011sleeve kurti with subtle sequin detailing", "color": "emerald green"},
        {"category": "Bottom", "item": "High\u2011waisted straight\u2011cut palazzo trousers", "color": "soft gold"},
        {"category": "Footwear", "item": "Block\u2011heel sandals", "color": "gold"},
    ],
    "accessories": [
        {"category": "Jewellery", "item": "Statement jhumka earrings", "color": "gold"},
        {"category": "Bag", "item": "Clutch", "color": "deep burgundy"},
    ],
    "budget": 5000,
    "currency": "INR",
}


# --------------------------------------------------------------------------
# Taxonomy
# --------------------------------------------------------------------------


def test_indian_wear_aliases_map_to_catalog_categories():
    assert CATEGORY_ALIASES["kurti"] == "tops"
    assert CATEGORY_ALIASES["palazzo"] == "pants"
    assert CATEGORY_ALIASES["jhumka"] == "accessories"
    assert CATEGORY_ALIASES["clutch"] == "bags"
    assert CATEGORY_ALIASES["footwear"] == "shoes"


def test_color_families():
    assert color_match_level("gold", "gold") == MATCH_EXACT
    assert color_match_level("emerald green", "green") == MATCH_FAMILY
    assert color_match_level("soft gold", "gold") == MATCH_FAMILY
    assert color_match_level("deep burgundy", "maroon") == MATCH_FAMILY
    assert color_match_level("emerald green", "royal blue") == MATCH_NONE
    assert color_match_level("black", "white") == MATCH_NONE
    assert color_match_level(None, "gold") == MATCH_NONE


def test_bare_bottom_uses_item_text_to_choose_jeans_or_skirt():
    assert resolve_item_category(OutfitItem(category="Bottom", item="Blue jeans")) == "jeans"
    assert resolve_item_category(OutfitItem(category="Bottom", item="Pleated skirt")) == "skirts"
    assert resolve_item_category(OutfitItem(category="Bottom", item="Beige palazzo")) == "pants"
    assert resolve_item_category(OutfitItem(category="Bottom", item="Something nice")) == "pants"


# --------------------------------------------------------------------------
# Wedding outfit end-to-end (shopping -> ranker -> critic)
# --------------------------------------------------------------------------


def test_wedding_plan_from_swagger_is_completed_and_approved(monkeypatch):
    _use_in_process_client(monkeypatch)

    entries = asyncio.run(ShoppingAgent().search_outfit(WEDDING_PLAN))
    assert [e["status"] for e in entries] == ["ok"] * 5

    selected = select_products(_flatten(entries), WEDDING_PLAN)
    assert len(selected) == 5
    assert len({p["product_id"] for p in selected}) == 5
    assert sum(p["price"] for p in selected) <= 5000
    assert {p["category"] for p in selected} == {"tops", "pants", "shoes", "accessories", "bags"}

    verdict = CriticAgent().evaluate(
        outfit_plan=WEDDING_PLAN,
        selected_products=selected,
        user_request="indoor friend wedding outfit under 5000",
        budget=5000,
    )
    assert verdict.status == "approve", verdict.issues


def test_selected_products_keep_real_ids_and_urls(monkeypatch):
    _use_in_process_client(monkeypatch)
    entries = asyncio.run(ShoppingAgent().search_outfit(WEDDING_PLAN))
    selected = select_products(_flatten(entries), WEDDING_PLAN)
    store = MockStore()
    for product in selected:
        real = store.get_product(product["product_id"])
        assert real is not None
        assert product["product_url"] == real.product_url
        assert product["price"] == real.price


# --------------------------------------------------------------------------
# Colour relaxation only applies to stylist-planned items
# --------------------------------------------------------------------------


def test_outfit_search_relaxes_missing_color_but_explicit_search_does_not(monkeypatch):
    _use_in_process_client(monkeypatch)

    # No navy watch exists in the catalog.
    assert asyncio.run(ShoppingAgent().search(category="watches", color="navy")) == []

    plan = {
        "occasion": "office",
        "style": "Classic",
        "items": [{"category": "Watch", "item": "Navy watch", "color": "navy"}],
        "accessories": [],
        "budget": 4000,
    }
    entries = asyncio.run(ShoppingAgent().search_outfit(plan))
    assert entries[0]["status"] == "ok"
    assert entries[0]["products"]


# --------------------------------------------------------------------------
# Budget reserve
# --------------------------------------------------------------------------


def _candidate(pid: str, category: str, price: float, index: int, color: str = "black"):
    return {
        "product_id": pid,
        "category": category,
        "color": color,
        "price": price,
        "title": pid,
        "availability": True,
        "item_index": index,
    }


def test_budget_is_reserved_for_later_items():
    plan = {
        "items": [
            {"category": "Top", "item": "top", "color": "black"},
            {"category": "Shoes", "item": "shoes", "color": "black"},
        ],
        "accessories": [],
        "budget": 2000,
    }
    candidates = [
        _candidate("TOP-EXPENSIVE", "tops", 1800, 0),
        _candidate("TOP-CHEAP", "tops", 900, 0),
        _candidate("SHOE", "shoes", 1000, 1),
    ]
    selected = select_products(candidates, plan)
    assert [p["product_id"] for p in selected] == ["TOP-CHEAP", "SHOE"]
    assert sum(p["price"] for p in selected) <= 2000


# --------------------------------------------------------------------------
# Critic: shade-aware palette
# --------------------------------------------------------------------------


def test_critic_accepts_shades_of_planned_palette_colors():
    plan = {
        "occasion": "dinner",
        "style": "Elegant",
        "color_palette": ["emerald green", "soft gold"],
        "items": [
            {"category": "Top", "item": "kurti", "color": "emerald green"},
            {"category": "Shoes", "item": "sandals", "color": "gold"},
        ],
        "accessories": [],
        "budget": 5000,
    }
    products = [
        {"product_id": "A", "category": "tops", "color": "green", "price": 1000, "currency": "INR", "title": "Green Kurti"},
        {"product_id": "B", "category": "shoes", "color": "gold", "price": 900, "currency": "INR", "title": "Gold Sandals"},
    ]
    verdict = CriticAgent().evaluate(outfit_plan=plan, selected_products=products, budget=5000)
    assert verdict.status == "approve", verdict.issues


def test_critic_still_flags_a_color_outside_the_palette():
    plan = {
        "occasion": "dinner",
        "style": "Elegant",
        "color_palette": ["emerald green"],
        "items": [{"category": "Top", "item": "kurti", "color": "emerald green"}],
        "accessories": [],
        "budget": 5000,
    }
    products = [
        {"product_id": "A", "category": "tops", "color": "red", "price": 1000, "currency": "INR", "title": "Red Kurti"},
    ]
    verdict = CriticAgent().evaluate(outfit_plan=plan, selected_products=products, budget=5000)
    assert verdict.status == "revise"
    assert any("palette" in issue.reason for issue in verdict.issues)
