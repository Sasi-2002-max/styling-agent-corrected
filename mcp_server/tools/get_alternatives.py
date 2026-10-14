"""
get_alternatives MCP tool.

Uses the configured shopping provider instead of directly querying MockStore.
"""

from __future__ import annotations

from typing import Any, Dict, List

from backend.shopping.stores.mock_store import MockStore
from mcp_server.provider import get_alternatives as get_from_provider

# Backward-compatible injection seam for isolated tool tests.
_store = MockStore()
_DEFAULT_STORE = _store


def get_alternatives_impl(
    product_id: str,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """Return alternatives from the configured provider."""
    if _store is not _DEFAULT_STORE:
        alternatives = _store.get_alternatives(product_id, limit=limit)
    else:
        alternatives = get_from_provider(product_id, limit=limit)

    return [alternative.model_dump() for alternative in alternatives]


def register(mcp) -> None:
    """Register the get_alternatives tool."""

    @mcp.tool()
    def get_alternatives(
        product_id: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Suggest alternatives for a product."""
        return get_alternatives_impl(product_id, limit=limit)
