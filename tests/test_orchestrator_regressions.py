import asyncio

from backend.agents.orchestrator import (
    _normalise_product_candidates,
    _run_critic,
    _run_fitting_room,
    create_initial_state,
)
from backend.agents.product_ranker import select_products


def _product(product_id, category, item_index, price=1000, **extra):
    return {
        "product_id": product_id,
        "title": product_id,
        "category": category,
        "price": price,
        "availability": True,
        "item_index": item_index,
        **extra,
    }


def test_search_results_keep_their_outfit_item_association():
    result = _normalise_product_candidates(
        [
            {
                "index": 0,
                "source": "items",
                "item": {"category": "Top", "item": "teal kurti"},
                "products": [
                    {"product_id": "TOP-1", "category": "tops"},
                ],
            },
            {
                "index": 1,
                "source": "items",
                "item": {"category": "Footwear", "item": "block heels"},
                "products": [
                    {"product_id": "SHOE-1", "category": "shoes"},
                ],
            },
        ]
    )

    assert [(item["product_id"], item["item_index"]) for item in result] == [
        ("TOP-1", 0),
        ("SHOE-1", 1),
    ]
    assert result[0]["outfit_item"]["item"] == "teal kurti"
    assert result[1]["item_source"] == "items"


def test_ranker_never_uses_another_item_or_unavailable_product():
    plan = {
        "budget": 5000,
        "items": [
            {"category": "Top", "item": "teal kurti"},
            {"category": "Footwear", "item": "beige heels"},
            {"category": "Bottom", "item": "beige palazzo"},
        ],
    }
    candidates = [
        _product("TOP-1", "tops", 0),
        _product("WRONG-ITEM-TOP", "tops", 1),
        _product("SOLD-OUT-SHOE", "shoes", 1, availability=False),
        _product("SHOE-1", "shoes", 1),
        _product("JEANS-1", "jeans", 2),
    ]

    selected = select_products(candidates, plan)

    assert [(item["product_id"], item["item_index"]) for item in selected] == [
        ("TOP-1", 0),
        ("SHOE-1", 1),
        ("JEANS-1", 2),
    ]


def test_ranker_does_not_select_wrong_category_or_exceed_budget():
    no_wrong_category = select_products(
        [_product("TOP-1", "tops", 0)],
        {"items": [{"category": "Footwear"}]},
    )
    over_budget = select_products(
        [_product("SHOE-1", "shoes", 0, price=1200)],
        {"budget": 1000, "items": [{"category": "Footwear"}]},
    )

    assert no_wrong_category == []
    assert over_budget == []


def test_fitting_room_summary_has_real_total_and_missing_items(monkeypatch):
    from backend.fitting_room import service as fitting_room_service

    captured = {}

    class FakeFittingRoomService:
        async def prepare_fitting_room(self, **kwargs):
            captured.update(kwargs)
            return {"status": "incomplete"}

    monkeypatch.setattr(
        fitting_room_service,
        "FittingRoomService",
        FakeFittingRoomService,
    )

    state = create_initial_state({}, "wedding outfit")
    state["outfit_plan"] = {
        "items": [
            {"category": "Top", "item": "kurti"},
            {"category": "Footwear", "item": "heels"},
        ],
        "accessories": [],
    }
    state["selected_products"] = [
        _product("TOP-1", "tops", 0, price=1800),
    ]

    asyncio.run(_run_fitting_room(state))

    outfit = captured["outfit_result"]
    assert outfit["total_price"] == 1800
    assert outfit["status"] == "incomplete"
    assert outfit["missing_items"][0]["item_index"] == 1
    assert outfit["missing_items"][0]["reason"] == "no_available_product"


def test_orchestrator_invokes_the_critic_class():
    state = create_initial_state({}, "formal wedding")
    state["outfit_plan"] = {
        "occasion": "wedding",
        "items": [{"category": "shirts", "item": "formal shirt"}],
        "accessories": [],
        "color_palette": ["navy"],
        "budget": 2000,
    }
    state["selected_products"] = [
        {
            "product_id": "CASUAL-TEE",
            "category": "t-shirts",
            "title": "Graphic T-shirt",
            "color": "navy",
            "price": 500,
            "currency": "INR",
            "availability": True,
        }
    ]
    state["user_query"] = "formal wedding"

    asyncio.run(_run_critic(state))

    assert state["critic_feedback"]["source"] == "critic_agent"
    assert state["critic_feedback"]["approved"] is False
    assert state["critic_feedback"]["issues"]


def test_style_endpoint_returns_clear_configuration_status_without_groq_key(monkeypatch):
    from fastapi.testclient import TestClient

    from backend.main import app
    from backend.utils import llm

    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr(llm, "GROQ_API_KEY", None)
    monkeypatch.setattr(llm, "client", None)

    response = TestClient(app).post(
        "/api/style",
        json={"user_query": "formal wedding outfit"},
    )

    assert response.status_code == 503
    assert "GROQ_API_KEY" in response.json()["detail"]