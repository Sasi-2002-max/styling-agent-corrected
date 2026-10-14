"""
search_products MCP tool.

    MCP Server
         v
    search_products()             <-- this file
         v
    provider registry -> SerpApi Google Shopping or MockStore fallback
         v
    Product objects -> serialized dicts
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.shopping.stores.mock_store import DEFAULT_LIMIT, MockStore
from mcp_server.provider import search_products as search_from_provider

# Kept as a test seam for existing MockStore-specific tool tests. Production
# requests use the provider registry below.
_store = MockStore()
_DEFAULT_STORE = _store


def search_products_impl(
    query: str = "",
    category: Optional[str] = None,
    color: Optional[str] = None,
    max_price: Optional[float] = None,
    limit: int = DEFAULT_LIMIT,
    budget: Optional[float] = None,  # backward-compatible alias for max_price
    occasion: Optional[str] = None,
    style: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Search for products matching the given filters. Uses the configured
    SerpApi Google Shopping provider, with MockStore fallback by default.

    Price and category filtering is deterministic after retrieval (no LLM).

    Returns:
        A list of serialized Product dicts (via Product.model_dump()).
        Never a custom/second schema. May be empty.
    """
    if max_price is None:
        max_price = budget

    if _store is not _DEFAULT_STORE:
        # Backward-compatible seam used by tests that inject a temporary catalog.
        products = _store.search_products(
            query=query or "", budget=max_price, category=category, color=color, limit=limit
        )
    else:
        products = search_from_provider(
            query=query or "",
            max_price=max_price,
            budget=budget,
            category=category,
            color=color,
            limit=limit,
            occasion=occasion,
            style=style,
        )
    return [product.model_dump() for product in products]


def register(mcp) -> None:
    """Register the search_products tool on the given MCPServer."""

    @mcp.tool()
    def search_products(
        query: str = "",
        category: Optional[str] = None,
        color: Optional[str] = None,
        max_price: Optional[float] = None,
        limit: int = DEFAULT_LIMIT,
        budget: Optional[float] = None,
        occasion: Optional[str] = None,
        style: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search the configured shopping product source for fashion products.
        SerpApi Google Shopping is used when configured; MockStore is the
        selectable provider and the default fallback when SerpApi fails.

        Args:
            query: Free-text search terms, e.g. "black shirt".
            category: Optional exact category filter, e.g. "shirt".
            color: Optional exact color filter, e.g. "black".
            max_price: Optional maximum price (inclusive).
            limit: Maximum number of products to return.
            budget: Alias for max_price. MCPShoppingClient sends "budget";
                without this parameter the MCP layer silently dropped it
                and the price filter was never applied.

        Returns:
            A list of product objects, each with: product_id, store, brand,
            title, category, color, price, currency, sizes, image_url,
            product_url, availability. image_url is null when the source
            has no image for that product; it is never fabricated.
        """
        return search_products_impl(
            query=query,
            category=category,
            color=color,
            max_price=max_price,
            limit=limit,
            budget=budget,
            occasion=occasion,
            style=style,
        )