"""
check_availability MCP tool.

    MCP Server
         v
    check_availability()          <-- this file
         v
    provider registry -> cached SerpApi listing or MockStore catalog
         v
    {"product_id": ..., "available": bool}
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from backend.shopping.stores.mock_store import MockStore
from mcp_server.provider import check_availability as check_from_provider

# Backward-compatible injection seam for isolated tool tests.
_store = MockStore()
_DEFAULT_STORE = _store


def check_availability_impl(
    product_id: str,
    size: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Check whether a product is currently available.

    Args:
        product_id: The product identifier.
        size: Optional requested size.

    Returns:
        {
            "product_id": "...",
            "available": True/False
        }

    Availability is read from the store and never guessed.
    """
    if _store is not _DEFAULT_STORE:
        available = _store.check_availability(product_id, size=size)
    else:
        available = check_from_provider(product_id, size=size)

    return {
        "product_id": product_id,
        "available": available,
    }


def register(mcp) -> None:
    """Register the check_availability tool on the MCP server."""

    @mcp.tool()
    def check_availability(
        product_id: str,
        size: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Check whether a product is available, optionally for a
        specific size.
        """
        return check_availability_impl(
            product_id,
            size=size,
        )