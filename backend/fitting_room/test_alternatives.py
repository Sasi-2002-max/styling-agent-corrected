"""Part 45 tests: POST /api/fitting-room/alternatives. TEST FIXTURE DATA ONLY."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.fitting_room.service import FittingRoomService, InvalidCategoryError
from backend.main import app
from backend.shopping.mcp_client import MCPConnectionError, MCPToolError

ALT_SHIRT_1 = {
    "product_id": "AMZ124", "store": "Demo Fashion", "brand": "Urban Weave",
    "title": "Black Linen Shirt", "category": "shirts", "color": "black",
    "price": 1399.0, "currency": "INR", "sizes": ["M", "L"],
    "image_url": "https://example.test/amz124.jpg",
    "product_url": "https://example.test/amz124", "availability": True,
}
ALT_SHIRT_2 = {
    "product_id": "AMZ125", "store": "Demo Style", "brand": "InkPrint",
    "title": "Blue Shirt", "category": "shirts", "color": "blue",
    "price": 1199.0, "currency": "INR", "sizes": ["S"],
    "image_url": None,  # real product with no image: must stay None
    "product_url": "https://example.test/amz125", "availability": True,
}
ALT_PANTS = {
    "product_id": "MYN457", "store": "Demo Trends", "brand": "Chino Co",
    "title": "Beige Chinos", "category": "pants", "color": "beige",
    "price": 1499.0, "currency": "INR", "sizes": ["32"],
    "image_url": "https://example.test/myn457.jpg",
    "product_url": "https://example.test/myn457", "availability": True,
}


class FakeShoppingAgent:
    """Only get_alternatives is legitimate; any search or product lookup fails the test."""

    def __init__(
        self,
        alternatives: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        error: Optional[Exception] = None,
    ) -> None:
        self._alternatives = alternatives or {}
        self._error = error
        self.get_alternatives_calls: List[str] = []
        self.forbidden_calls: List[str] = []

    async def get_alternatives(self, product_id: str) -> List[Dict[str, Any]]:
        self.get_alternatives_calls.append(product_id)
        if self._error:
            raise self._error
        return self._alternatives.get(product_id, [])

    async def search(self, *a, **k):
        self.forbidden_calls.append("search")
        raise AssertionError("must not search")

    async def search_outfit(self, *a, **k):
        self.forbidden_calls.append("search_outfit")
        raise AssertionError("must not search")

    async def find_products(self, *a, **k):
        self.forbidden_calls.append("find_products")
        raise AssertionError("must not search")


def _service(agent: FakeShoppingAgent) -> FittingRoomService:
    return FittingRoomService(shopping_agent=agent)


def _client(agent: FakeShoppingAgent):
    patcher = patch(
        "backend.main.FittingRoomService",
        side_effect=lambda: FittingRoomService(shopping_agent=agent),
    )
    return patcher, TestClient(app)


# 1. endpoint returns real products
def test_endpoint_returns_real_products():
    agent = FakeShoppingAgent({"AMZ123": [ALT_SHIRT_1, ALT_SHIRT_2]})
    patcher, client = _client(agent)
    with patcher:
        res = client.post(
            "/api/fitting-room/alternatives",
            json={"product_id": "AMZ123", "category": "shirts"},
        )
    assert res.status_code == 200
    body = res.json()
    assert body["category"] == "shirts"
    assert body["products"] == [ALT_SHIRT_1, ALT_SHIRT_2]


# 2. selected product id is passed to the existing ShoppingAgent
def test_product_id_is_passed_to_shopping_agent():
    agent = FakeShoppingAgent({"AMZ123": [ALT_SHIRT_1]})
    asyncio.run(_service(agent).get_alternatives("AMZ123", "shirts"))
    assert agent.get_alternatives_calls == ["AMZ123"]


# 3. no fake product is created, no search happens
def test_no_fake_products_and_no_search():
    agent = FakeShoppingAgent({"AMZ123": [ALT_SHIRT_1, ALT_SHIRT_2]})
    result = asyncio.run(_service(agent).get_alternatives("AMZ123", "shirts"))
    assert [p.product_id for p in result.products] == ["AMZ124", "AMZ125"]
    assert result.products[1].image_url is None
    assert result.products[0].product_url == ALT_SHIRT_1["product_url"]
    assert agent.forbidden_calls == []


def test_works_for_other_categories():
    agent = FakeShoppingAgent({"MYN456": [ALT_PANTS]})
    result = asyncio.run(_service(agent).get_alternatives("MYN456", "pants"))
    assert result.category == "pants"
    assert result.products[0].product_id == "MYN457"


# 4. MCP / shopping errors propagate
def test_mcp_connection_error_propagates():
    agent = FakeShoppingAgent(error=MCPConnectionError("down"))
    with pytest.raises(MCPConnectionError):
        asyncio.run(_service(agent).get_alternatives("AMZ123", "shirts"))


def test_mcp_tool_error_propagates():
    agent = FakeShoppingAgent(error=MCPToolError("get_alternatives", "boom"))
    with pytest.raises(MCPToolError):
        asyncio.run(_service(agent).get_alternatives("AMZ123", "shirts"))


def test_mcp_error_propagates_through_endpoint():
    agent = FakeShoppingAgent(error=MCPToolError("get_alternatives", "boom"))
    patcher, client = _client(agent)
    with patcher, pytest.raises(MCPToolError):
        client.post(
            "/api/fitting-room/alternatives",
            json={"product_id": "AMZ123", "category": "shirts"},
        )


# 5. empty alternatives remain empty
def test_empty_alternatives_remain_empty():
    agent = FakeShoppingAgent({})
    patcher, client = _client(agent)
    with patcher:
        res = client.post(
            "/api/fitting-room/alternatives",
            json={"product_id": "AMZ123", "category": "shirts"},
        )
    assert res.status_code == 200
    assert res.json() == {"category": "shirts", "products": []}


# invalid input
def test_invalid_category_rejected_before_any_shopping_call():
    agent = FakeShoppingAgent({"AMZ123": [ALT_SHIRT_1]})
    with pytest.raises(InvalidCategoryError):
        asyncio.run(_service(agent).get_alternatives("AMZ123", "hats"))
    assert agent.get_alternatives_calls == []


def test_invalid_category_returns_422():
    agent = FakeShoppingAgent()
    patcher, client = _client(agent)
    with patcher:
        res = client.post(
            "/api/fitting-room/alternatives",
            json={"product_id": "AMZ123", "category": "hats"},
        )
    assert res.status_code == 422
    assert agent.get_alternatives_calls == []


def test_blank_product_id_returns_422():
    agent = FakeShoppingAgent()
    patcher, client = _client(agent)
    with patcher:
        res = client.post(
            "/api/fitting-room/alternatives",
            json={"product_id": "  ", "category": "shirts"},
        )
    assert res.status_code == 422
    assert agent.get_alternatives_calls == []