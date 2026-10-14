"""Backend-only shopping provider selection and mock fallback."""
from __future__ import annotations

import logging
import os
from typing import Optional

from dotenv import load_dotenv

from backend.shopping.product_normalizer import Product
from backend.shopping.stores.mock_store import MockStore
from backend.shopping.stores.serpapi import SerpApiStore

load_dotenv()
logger = logging.getLogger(__name__)
_mock_store = MockStore()
_serpapi_store = SerpApiStore()


def _configured_provider() -> str:
    configured = (os.getenv("SHOPPING_PROVIDER") or "").strip().lower()
    if configured in {"mock", "serpapi"}:
        return configured
    return "serpapi" if (os.getenv("SERPAPI_API_KEY") or "").strip() else "mock"


def search_products(
    *, query: str = "", category: Optional[str] = None, color: Optional[str] = None,
    max_price: Optional[float] = None, limit: int = 20, budget: Optional[float] = None,
    occasion: Optional[str] = None, style: Optional[str] = None,
) -> list[Product]:
    """Search configured provider; use MockStore on SerpApi failure/empty result."""
    budget = max_price if max_price is not None else budget
    provider = _configured_provider()
    if provider == "serpapi":
        try:
            results = _serpapi_store.search_products(
                query=query, budget=budget, category=category, color=color,
                occasion=occasion, style=style,
            )
            if results:
                logger.info("shopping_provider=serpapi result_count=%d", len(results))
                return results[:max(1, limit)]
            logger.warning("SerpApi returned no usable INR-priced results; trying MockStore fallback")
        except Exception as exc:
            logger.warning("SerpApi search unavailable (%s); trying MockStore fallback", type(exc).__name__)
        if (os.getenv("SERPAPI_FALLBACK_TO_MOCK") or "true").strip().lower() not in {"1", "true", "yes", "on"}:
            return []
    else:
        logger.info("shopping_provider=mock")

    try:
        products = _mock_store.search_products(query=query, budget=budget, category=category, color=color, limit=limit)
    except Exception as exc:
        logger.error("MockStore search failed (%s)", type(exc).__name__)
        return []
    logger.info("shopping_provider=mock result_count=%d", len(products))
    return products[:max(1, limit)]


def get_product(product_id: str) -> Optional[Product]:
    product = _serpapi_store.get_product(product_id)
    return product if product is not None else _mock_store.get_product(product_id)


def get_variants(product_id: str) -> list[Product]:
    if product_id.startswith("serp_"):
        return _serpapi_store.get_variants(product_id)
    return _mock_store.get_variants(product_id)


def check_availability(product_id: str, size: Optional[str] = None) -> bool:
    if product_id.startswith("serp_"):
        # No size-level inventory API is exposed by this search adapter.
        return _serpapi_store.check_availability(product_id)
    return _mock_store.check_availability(product_id, size=size)


def get_alternatives(product_id: str, limit: int = 5) -> list[Product]:
    if product_id.startswith("serp_"):
        return _serpapi_store.get_alternatives(product_id, limit=limit)
    return _mock_store.get_alternatives(product_id, limit=limit)
