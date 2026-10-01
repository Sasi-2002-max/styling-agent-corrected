"""
Pydantic schemas for the Fitting Room backend (Parts 42-43).

These describe the frontend-facing data contract only. They never appear
inside ShoppingAgent or MCPShoppingClient; this module is purely the shape
the fitting-room service produces from Part 41's already-selected outfit.

No field here is invented by this module -- every value either comes
straight from Part 41's build_outfit() output or from a real product
resolved through ShoppingAgent (backed by MCPShoppingClient). Missing data
(e.g. a product with no image) stays None; it is never filled in with a
guess or placeholder.

Part 43 principle: THE SELECTED RETAILER PRODUCT IS THE SOURCE OF TRUTH.
`FittingRoomItem.product.product_id` and `.image_url` refer to the exact
real product Part 41 selected. There is no separate visual catalog.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class MannequinGender(str, Enum):
    """The two supported mannequin types. No other value is accepted."""

    FEMALE = "female"
    MALE = "male"


class FittingRoomMannequin(BaseModel):
    """A resolved mannequin reference: which one, and its static asset path."""

    gender: MannequinGender
    asset: str


class FittingRoomProduct(BaseModel):
    """
    Real product data as resolved through ShoppingAgent for the fitting room.

    Every field is preserved exactly as returned by MCP; none is fabricated.
    image_url is None when the source has no image -- never a placeholder.
    product_url is always the real retailer/product URL.
    """

    product_id: str
    store: str
    brand: str
    title: str
    category: str
    color: Optional[str] = None
    price: float
    currency: str = "INR"
    sizes: List[str] = Field(default_factory=list)
    image_url: Optional[str] = None
    product_url: str
    availability: bool = True


class ColorVariation(BaseModel):
    """
    One real color variant of a selected product, from get_variants().

    image_url is None when the real source has no variation image -- it is
    never invented.
    """

    product_id: str
    color: Optional[str] = None
    image_url: Optional[str] = None
    product_url: str
    price: float
    currency: str = "INR"


class SelectedProductRef(BaseModel):
    """One entry from Part 41's build_outfit() selected_products list."""

    product_id: str
    category: str
    item_index: int


class OutfitSummary(BaseModel):
    """
    Part 41's build_outfit() output, carried through unchanged.

    This is the exact shape ShoppingAgent.build_outfit() already returns:
    status ("complete"/"incomplete"), the selected product refs, the real
    total price, and any missing_items. Nothing here is recomputed.
    """

    status: str
    selected_products: List[SelectedProductRef] = Field(default_factory=list)
    total_price: float = 0.0
    missing_items: List[Dict[str, Any]] = Field(default_factory=list)


class FittingRoomItem(BaseModel):
    """
    One outfit slot's fitting-room data.

    `product` is None and `error` is set (e.g. "product_not_found") when
    MCP could not resolve the selected product_id -- it is never invented.

    `visual_source` (Part 43) tells the frontend where the visual for this
    item comes from:
      - "product_image": render `product.image_url` (the real retailer
        image of the exact selected product).
      - None: there is no real image to render (product not found, or the
        product's image_url is None). Nothing is fabricated.
    """

    item_index: int
    category: str
    product: Optional[FittingRoomProduct] = None
    visual_source: Optional[Literal["product_image"]] = None
    color_variations: List[ColorVariation] = Field(default_factory=list)
    alternatives: List[FittingRoomProduct] = Field(default_factory=list)
    error: Optional[str] = None


class FittingRoomRequest(BaseModel):
    """Request body for POST /api/fitting-room."""

    outfit: OutfitSummary
    mannequin_gender: MannequinGender
    include_variants: bool = True
    include_alternatives: bool = True


class FittingRoomResponse(BaseModel):
    """
    Full fitting-room response for the (future) Next.js frontend.

    `status` mirrors the outfit's own completeness: "ready" only when the
    underlying outfit is "complete"; "incomplete" otherwise. An incomplete
    outfit is never reported as ready.
    """

    status: str
    mannequin: FittingRoomMannequin
    outfit: OutfitSummary
    items: List[FittingRoomItem] = Field(default_factory=list)


class AlternativesRequest(BaseModel):
    """Request body for POST /api/fitting-room/alternatives."""

    model_config = ConfigDict(str_strip_whitespace=True)

    product_id: str = Field(min_length=1)
    category: str = Field(min_length=1)


class AlternativesResponse(BaseModel):
    """
    Real alternatives for one outfit slot, exactly as returned through
    ShoppingAgent.get_alternatives(). An empty list stays empty.
    """

    category: str
    products: List[FittingRoomProduct] = Field(default_factory=list)


class ColorSwitchRequest(BaseModel):
    """Request body for POST /api/fitting-room/switch-color."""

    model_config = ConfigDict(str_strip_whitespace=True)

    product_id: str = Field(min_length=1)  # the product currently in the slot
    category: str = Field(min_length=1)    # backend catalog category, e.g. "shirts"
    color: str = Field(min_length=1)       # requested color, e.g. "navy"


class ColorSwitchResponse(BaseModel):
    """
    Result of resolving a requested color to a REAL retailer product.

    status "found": `product` is the real product exactly as the shopping
    layer returned it, and `source` says how it was resolved:
      - "variant": from get_variants() of the current product
      - "search":  from the existing ShoppingAgent.search()
    status "not_found": `product` is None and `reason` says why. Nothing is
    invented and the caller must keep its current product.
    """

    status: Literal["found", "not_found"]
    requested_color: str
    category: str
    source: Optional[Literal["variant", "search"]] = None
    product: Optional[FittingRoomProduct] = None
    reason: Optional[str] = None