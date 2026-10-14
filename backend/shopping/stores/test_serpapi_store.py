"""Offline tests for SerpApi Google Shopping integration (no API credits used)."""
from __future__ import annotations

import httpx
import pytest

from backend.shopping.stores.serpapi import SerpApiStore
from mcp_server import provider


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("fake HTTP error", request=None, response=None)

    def json(self):
        return self._payload


def _row(**overrides):
    row = {
        "product_id": "google-shopping-123",
        "title": "Casual Cotton Shirt",
        "source": "Example Retailer",
        "product_link": "https://retailer.example/products/cotton-shirt",
        "thumbnail": "https://retailer.example/images/shirt.jpg",
        "price": "₹1,299.00",
        "extracted_price": 1299,
    }
    row.update(overrides)
    return row


def test_search_uses_google_shopping_and_preserves_product_fields(monkeypatch):
    monkeypatch.setenv("SERPAPI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("DEFAULT_COUNTRY", "India")
    captured = {}

    def fake_get(url, *, params, timeout):
        captured.update(url=url, params=params, timeout=timeout)
        return FakeResponse({"shopping_results": [_row()]})

    monkeypatch.setattr("backend.shopping.stores.serpapi.httpx.get", fake_get)
    products = SerpApiStore().search_products(
        query="button down", category="shirts", color="blue", budget=2500,
        occasion="weekend", style="casual",
    )

    assert len(products) == 1
    product = products[0]
    assert captured["params"]["engine"] == "google_shopping"
    assert "button down" in captured["params"]["q"]
    assert "weekend" in captured["params"]["q"]
    assert "casual" in captured["params"]["q"]
    assert "shirts" in captured["params"]["q"]
    assert "blue" in captured["params"]["q"]
    assert "2500" in captured["params"]["q"]
    assert captured["params"]["gl"] == "in"
    assert captured["timeout"] <= 10
    assert product.product_id.startswith("serp_")
    assert product.store == "SerpApi / Example Retailer"
    assert product.title == "Casual Cotton Shirt"
    assert product.product_url == "https://retailer.example/products/cotton-shirt"
    assert product.image_url == "https://retailer.example/images/shirt.jpg"
    assert product.price == 1299
    assert product.currency == "INR"


def test_search_skips_missing_or_ambiguous_or_non_inr_prices(monkeypatch):
    monkeypatch.setenv("SERPAPI_API_KEY", "test-key-not-real")
    rows = [
        _row(product_id="missing", price=None, extracted_price=None),
        _row(product_id="usd", price="$19.99", extracted_price=19.99),
        _row(product_id="range", price="₹499 - ₹999", extracted_price=None),
        _row(product_id="valid", price="₹899", extracted_price=899),
    ]
    monkeypatch.setattr(
        "backend.shopping.stores.serpapi.httpx.get",
        lambda *a, **k: FakeResponse({"shopping_results": rows}),
    )
    products = SerpApiStore().search_products("shirt", budget=2000)
    assert [p.price for p in products] == [899]


def test_search_filters_results_over_budget(monkeypatch):
    monkeypatch.setenv("SERPAPI_API_KEY", "test-key-not-real")
    monkeypatch.setattr(
        "backend.shopping.stores.serpapi.httpx.get",
        lambda *a, **k: FakeResponse({"shopping_results": [
            _row(product_id="cheap", price="₹999", extracted_price=999),
            _row(product_id="costly", price="₹2,999", extracted_price=2999),
        ]}),
    )
    products = SerpApiStore().search_products("shirt", budget=2500)
    assert len(products) == 1
    assert products[0].price == 999


def test_provider_falls_back_to_mock_on_serpapi_exception(monkeypatch):
    monkeypatch.setenv("SERPAPI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("SHOPPING_PROVIDER", "serpapi")
    monkeypatch.setenv("SERPAPI_FALLBACK_TO_MOCK", "true")
    monkeypatch.setattr(provider._serpapi_store, "search_products", lambda **kwargs: (_ for _ in ()).throw(TimeoutError()))
    products = provider.search_products(query="", category="shirts", max_price=5000, limit=3)
    assert products
    assert all(not p.product_id.startswith("serp_") for p in products)


def test_provider_falls_back_to_mock_on_empty_serpapi_results(monkeypatch):
    monkeypatch.setenv("SERPAPI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("SHOPPING_PROVIDER", "serpapi")
    monkeypatch.setenv("SERPAPI_FALLBACK_TO_MOCK", "true")
    monkeypatch.setattr(provider._serpapi_store, "search_products", lambda **kwargs: [])
    products = provider.search_products(query="", category="shirts", max_price=5000, limit=3)
    assert products
    assert all(not p.product_id.startswith("serp_") for p in products)


def test_provider_can_select_mock_explicitly(monkeypatch):
    monkeypatch.setenv("SHOPPING_PROVIDER", "mock")
    monkeypatch.setattr(provider._serpapi_store, "search_products", lambda **kwargs: pytest.fail("SerpApi should not be called"))
    products = provider.search_products(query="", category="shirts", max_price=5000, limit=2)
    assert products
    assert all(not p.product_id.startswith("serp_") for p in products)


def test_provider_returns_empty_if_fallback_disabled(monkeypatch):
    monkeypatch.setenv("SERPAPI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("SHOPPING_PROVIDER", "serpapi")
    monkeypatch.setenv("SERPAPI_FALLBACK_TO_MOCK", "false")
    monkeypatch.setattr(provider._serpapi_store, "search_products", lambda **kwargs: [])
    assert provider.search_products(query="shirt", category="shirts", max_price=5000) == []


def test_product_id_is_stable_and_cached_for_followup_lookup(monkeypatch):
    monkeypatch.setenv("SERPAPI_API_KEY", "test-key-not-real")
    monkeypatch.setattr(
        "backend.shopping.stores.serpapi.httpx.get",
        lambda *a, **k: FakeResponse({"shopping_results": [_row()]}),
    )
    store = SerpApiStore()
    first = store.search_products("shirt", budget=2000)[0]
    second = store.search_products("shirt", budget=2000)[0]
    assert first.product_id == second.product_id
    assert store.get_product(first.product_id).product_url == first.product_url


def test_timeout_is_a_provider_error_without_exposing_credentials(monkeypatch):
    monkeypatch.setenv("SERPAPI_API_KEY", "never-log-this-key")
    def timeout(*args, **kwargs):
        raise httpx.ReadTimeout("request timed out")
    monkeypatch.setattr("backend.shopping.stores.serpapi.httpx.get", timeout)
    with pytest.raises(RuntimeError, match="timed out") as exc:
        SerpApiStore().search_products("shirt")
    assert "never-log-this-key" not in str(exc.value)


def test_rejects_conflicting_currency_and_displayed_price_range(monkeypatch):
    monkeypatch.setenv("SERPAPI_API_KEY", "test-key-not-real")
    rows = [
        _row(product_id="conflict", price="$1,299", extracted_price=1299, currency="INR"),
        _row(product_id="range", price="₹999 - ₹1,499", extracted_price=999),
        _row(product_id="valid", price="₹799", extracted_price="799"),
    ]
    monkeypatch.setattr(
        "backend.shopping.stores.serpapi.httpx.get",
        lambda *a, **k: FakeResponse({"shopping_results": rows}),
    )
    products = SerpApiStore().search_products("shirt", budget=2000)
    assert len(products) == 1
    assert products[0].price == 799


def test_provider_passes_occasion_and_style_to_serpapi(monkeypatch):
    monkeypatch.setenv("SERPAPI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("SHOPPING_PROVIDER", "serpapi")
    captured = {}
    def fake_search(**kwargs):
        captured.update(kwargs)
        return [object()]
    monkeypatch.setattr(provider._serpapi_store, "search_products", fake_search)
    results = provider.search_products(
        query="shirt", category="shirts", occasion="weekend", style="casual"
    )
    assert len(results) == 1
    assert captured["occasion"] == "weekend"
    assert captured["style"] == "casual"


def test_missing_serpapi_key_uses_mock_fallback(monkeypatch):
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    monkeypatch.setenv("SHOPPING_PROVIDER", "serpapi")
    monkeypatch.setenv("SERPAPI_FALLBACK_TO_MOCK", "true")
    products = provider.search_products(query="", category="shirts", max_price=5000, limit=2)
    assert products
    assert all(not p.product_id.startswith("serp_") for p in products)
