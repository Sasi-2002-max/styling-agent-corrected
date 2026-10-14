"""
get_variants MCP tool.

Uses the configured shopping provider instead of directly querying MockStore.
"""

from __future__ import annotations

from typing import Any, Dict, List

from backend.shopping.stores.mock_store import MockStore
from mcp_server.provider import get_variants as get_from_provider

# Backward-compatible injection seam for isolated tool tests.
_store = MockStore()
_DEFAULT_STORE = _store


def get_variants_impl(product_id: str) -> List[Dict[str, Any]]:
    """Return variants from the configured provider."""
    if _store is not _DEFAULT_STORE:
        variants = _store.get_variants(product_id)
    else:
        variants = get_from_provider(product_id)

    return [variant.model_dump() for variant in variants]


def register(mcp) -> None:
    """Register the get_variants tool."""

    @mcp.tool()
    def get_variants(product_id: str) -> List[Dict[str, Any]]:
        """Retrieve variants of a product when available."""
        return get_variants_impl(product_id)