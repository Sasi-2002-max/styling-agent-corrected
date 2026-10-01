"""
Part 46 backend tests: color switching selects a REAL product, never a recolor.

Fixtures come from the real data/products/products.json catalog.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Dict, List

import pytest

from backend.agents import shopping_agent as shopping_agent_module
from backend.fitting_room import service as service_module
from backend.fitting_room.service import (
    FittingRoomService,
    InvalidCategoryError,
    InvalidColorError,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CATALOG: List[Dict[str, Any]] = json.loads(
    (PROJECT_ROOT / "data" / "products" / "products.json").read_text(encoding="utf-8")
)
BY_ID = {p["product_id"]: p for p in CATALOG}


def run(coro):
    return asyncio.run(coro)


class FakeAgent:
    """Stands in for ShoppingAgent and records every call."""

    def __init__(self, variants=None, search_results=None, products=None):
        self.variants = variants or []
        self.search_results = search_results or []
        self.products = products or {}
        self.calls: List[tuple] = []

    async def get_variants(self, product_id):
        self.calls.append(("get_variants", product_id))
        return self.variants

    async def search(self, **kwargs):
        self.calls.append(("search", kwargs))
        return self.search_results

    async def get_product(self, product_id):
        self.calls.append(("get_product", product_id))
        return self.products.get(product_id)

    async def get_alternatives(self, *args, **kwargs):  # must never be used
        raise AssertionError("switch_color must not call get_alternatives")


def names(agent: FakeAgent) -> List[str]:
    return [c[0] for c in agent.calls]


# ---------------------------------------------------------------- variants


@pytest.mark.parametrize("target_id,color", [("MOCK003", "navy"), ("MOCK002", "white")])
def test_variant_color_resolves_to_real_product_without_search(target_id, color):
    agent = FakeAgent(variants=[dict(BY_ID[target_id])])

    result = run(FittingRoomService(agent).switch_color("MOCK001", "shirts", color))

    real = BY_ID[target_id]
    assert result.status == "found"
    assert result.source == "variant"
    assert result.product is not None
    assert result.product.product_id == target_id
    assert result.product.color == real["color"]
    assert result.product.image_url == real["image_url"]      # real URL (or real null)
    assert result.product.product_url == real["product_url"]
    assert result.product.model_dump() == real                  # nothing added or altered
    assert "search" not in names(agent)


def test_missing_image_stays_none_never_fabricated():
    agent = FakeAgent(variants=[dict(BY_ID["MOCK003"])])  # catalog has image_url null
    result = run(FittingRoomService(agent).switch_color("MOCK001", "shirts", "navy"))
    assert result.product is not None and result.product.image_url is None


def test_partial_variant_is_resolved_through_get_product():
    agent = FakeAgent(
        variants=[{"product_id": "MOCK003", "color": "navy"}],
        products={"MOCK003": dict(BY_ID["MOCK003"])},
    )
    result = run(FittingRoomService(agent).switch_color("MOCK001", "shirts", "navy"))
    assert result.status == "found" and result.source == "variant"
    assert result.product is not None and result.product.product_id == "MOCK003"
    assert ("get_product", "MOCK003") in agent.calls
    assert "search" not in names(agent)


def test_variant_of_wrong_color_is_ignored_and_search_is_used():
    agent = FakeAgent(
        variants=[dict(BY_ID["MOCK002"])],  # white
        search_results=[dict(BY_ID["MOCK003"])],
    )
    result = run(FittingRoomService(agent).switch_color("MOCK001", "shirts", "navy"))
    assert result.source == "search"
    assert result.product is not None and result.product.product_id == "MOCK003"


# ------------------------------------------------------------------ search


def test_search_fallback_uses_existing_search_with_category_and_color():
    agent = FakeAgent(variants=[], search_results=[dict(BY_ID["MOCK003"])])

    result = run(FittingRoomService(agent).switch_color("MOCK001", "shirts", "Navy"))

    assert names(agent) == ["get_variants", "search"]
    assert agent.calls[1][1] == {"category": "shirts", "color": "navy"}
    assert result.status == "found" and result.source == "search"
    assert result.product is not None
    assert result.product.product_id == "MOCK003"
    assert result.product.model_dump() == BY_ID["MOCK003"]


def test_current_product_is_never_returned_as_the_new_color():
    agent = FakeAgent(search_results=[dict(BY_ID["MOCK003"])])
    result = run(FittingRoomService(agent).switch_color("MOCK003", "shirts", "navy"))
    assert result.status == "not_found" and result.product is None


def test_search_results_of_wrong_color_or_category_are_rejected():
    agent = FakeAgent(search_results=[dict(BY_ID["MOCK001"]), dict(BY_ID["MOCK026"])])
    # MOCK001 is black, MOCK026 is a navy *dress*.
    result = run(FittingRoomService(agent).switch_color("MOCK002", "shirts", "navy"))
    assert result.status == "not_found" and result.product is None


def test_color_spelling_is_normalised_to_catalog_spelling():
    agent = FakeAgent(search_results=[dict(BY_ID["MOCK007"])])
    result = run(FittingRoomService(agent).switch_color("MOCK005", "t-shirts", "Gray"))
    assert agent.calls[1][1]["color"] == "grey"
    assert result.product is not None and result.product.product_id == "MOCK007"


# --------------------------------------------------------------- not found


def test_unavailable_color_returns_structured_not_found():
    agent = FakeAgent()
    result = run(FittingRoomService(agent).switch_color("MOCK001", "shirts", "teal"))

    assert result.status == "not_found"
    assert result.product is None
    assert result.source is None
    assert result.reason == "no_product_in_requested_color"
    assert result.requested_color == "teal"
    assert result.category == "shirts"


def test_invalid_category_and_empty_color_make_no_shopping_calls():
    agent = FakeAgent()
    service = FittingRoomService(agent)
    with pytest.raises(InvalidCategoryError):
        run(service.switch_color("MOCK001", "spaceships", "navy"))
    with pytest.raises(InvalidColorError):
        run(service.switch_color("MOCK001", "shirts", "   "))
    assert agent.calls == []


# ------------------------------------ real ShoppingAgent + (faked) MCP client


class FakeMCPClient:
    """Replaces MCPShoppingClient inside the REAL ShoppingAgent."""

    instances: List["FakeMCPClient"] = []

    def __init__(self):
        self.calls: List[tuple] = []
        FakeMCPClient.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def get_variants(self, product_id):
        self.calls.append(("get_variants", product_id))
        return []

    async def search_products(self, query="", budget=None, category=None, color=None):
        self.calls.append(("search_products", {"category": category, "color": color}))
        return [
            dict(p)
            for p in CATALOG
            if (category is None or p["category"] == category)
            and (color is None or p["color"] == color)
        ]

    async def check_availability(self, product_id, size=None):
        self.calls.append(("check_availability", product_id))
        return {"product_id": product_id, "available": True}


@pytest.fixture
def real_agent_service(monkeypatch):
    FakeMCPClient.instances.clear()
    monkeypatch.setattr(shopping_agent_module, "MCPShoppingClient", FakeMCPClient)
    return FittingRoomService()  # default = the real ShoppingAgent


def test_real_shopping_agent_mcp_path_returns_actual_catalog_product(real_agent_service):
    result = run(real_agent_service.switch_color("MOCK001", "shirts", "navy"))

    assert result.status == "found"
    assert result.product is not None
    assert result.product.product_id == "MOCK003"             # real id, not invented
    assert result.product.color == "navy"
    assert result.product.product_url == BY_ID["MOCK003"]["product_url"]
    assert result.product.image_url == BY_ID["MOCK003"]["image_url"]
    assert result.product.model_dump() == BY_ID["MOCK003"]

    # It went through ShoppingAgent -> MCP client, and only about this product.
    calls = [c for client in FakeMCPClient.instances for c in client.calls]
    assert ("get_variants", "MOCK001") in calls
    assert any(c[0] == "search_products" for c in calls)
    for name, arg in calls:
        if name in ("get_variants", "check_availability"):
            assert arg == "MOCK001"


def test_real_shopping_agent_unavailable_color_is_not_found(real_agent_service):
    result = run(real_agent_service.switch_color("MOCK001", "shirts", "teal"))
    assert result.status == "not_found" and result.product is None


def test_returned_id_always_exists_in_the_catalog(real_agent_service):
    result = run(real_agent_service.switch_color("MOCK012", "pants", "black"))
    assert result.product is not None
    assert result.product.product_id in BY_ID
    assert result.product.product_id == "MOCK013"


# ----------------------------------------------- architecture / no-recolor scan


def test_service_has_no_direct_store_access_and_no_image_manipulation():
    source = Path(service_module.__file__).read_text(encoding="utf-8")

    for forbidden in ("MockStore", "mcp_server", "mcp_client", "backend.shopping.stores"):
        assert forbidden not in source

    for forbidden in ("PIL", "cv2", "numpy", "hue_rotate", "colorsys", "ImageEnhance"):
        assert forbidden not in source

    # image_url is only ever read, never assigned.
    assert not re.search(r"\bimage_url\s*=[^=]", source)


# ------------------------------------------------------------ API endpoint


def _client():
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    import backend.main as main_module

    return main_module, TestClient(main_module.app)


def test_endpoint_found_returns_the_real_product(monkeypatch):
    main_module, client = _client()
    from backend.fitting_room.schemas import ColorSwitchResponse, FittingRoomProduct

    class FakeService:
        async def switch_color(self, product_id, category, color):
            return ColorSwitchResponse(
                status="found",
                requested_color=color,
                category=category,
                source="variant",
                product=FittingRoomProduct.model_validate(BY_ID["MOCK003"]),
            )

    monkeypatch.setattr(main_module, "FittingRoomService", FakeService)

    response = client.post(
        "/api/fitting-room/switch-color",
        json={"product_id": "MOCK001", "category": "shirts", "color": "navy"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "found"
    assert body["product"]["product_id"] == "MOCK003"
    assert body["product"]["image_url"] is None
    assert body["product"]["product_url"] == BY_ID["MOCK003"]["product_url"]


def test_endpoint_not_found_is_200_with_no_product(monkeypatch):
    main_module, client = _client()
    from backend.fitting_room.schemas import ColorSwitchResponse

    class FakeService:
        async def switch_color(self, product_id, category, color):
            return ColorSwitchResponse(
                status="not_found",
                requested_color=color,
                category=category,
                reason="no_product_in_requested_color",
            )

    monkeypatch.setattr(main_module, "FittingRoomService", FakeService)

    response = client.post(
        "/api/fitting-room/switch-color",
        json={"product_id": "MOCK001", "category": "shirts", "color": "teal"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "not_found"
    assert response.json()["product"] is None


def test_endpoint_rejects_bad_input_with_422(monkeypatch):
    main_module, client = _client()

    class FakeService:
        async def switch_color(self, product_id, category, color):
            raise InvalidCategoryError("Invalid category")

    monkeypatch.setattr(main_module, "FittingRoomService", FakeService)

    assert client.post(
        "/api/fitting-room/switch-color",
        json={"product_id": "MOCK001", "category": "nope", "color": "navy"},
    ).status_code == 422
    assert client.post(
        "/api/fitting-room/switch-color",
        json={"product_id": "MOCK001", "category": "shirts"},  # color missing
    ).status_code == 422