"""
Fitting Room Service (Parts 42-46).

Resolves Part 41's already-selected outfit into frontend-friendly fitting-
room data: a mannequin reference plus each selected item's real product,
color variations, and alternatives.

Architecture:

    ShoppingAgent.build_outfit()   (Part 41 -- already run elsewhere)
              v
    FittingRoomService.prepare_fitting_room()
              v
    ShoppingAgent.get_product() / get_variants() / get_alternatives()
              v
    FittingRoomResponse

Part 43 -- product visual source:

    THE SELECTED RETAILER PRODUCT IS THE SOURCE OF TRUTH.

    The visual for each item is the real product's own image_url, exactly
    as returned by ShoppingAgent.get_product(). If the product has no
    image, image_url stays None -- no image is fabricated.

Part 45 -- product switching:

    get_alternatives() returns the real alternatives for one product via
    the existing ShoppingAgent.get_alternatives(). No search, no extra
    ranking, no filtering: whatever the shopping system returns is
    returned, and an empty result stays empty.

Part 46 -- color switching:

    switch_color() resolves a requested color to a REAL retailer product.

    Existing variants are checked first. If no matching real variant exists,
    the existing ShoppingAgent.search() is used with the requested category
    and color. Only a real product returned by the shopping layer is
    accepted.

This service performs NO independent product catalog access. It uses only
ShoppingAgent for shopping data.

Infrastructure errors from the shopping layer are allowed to propagate to
the caller. A genuinely unavailable product/color is represented by the
appropriate structured response rather than fabricated data.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from pydantic import ValidationError

from backend.agents.shopping_agent import (
    SUPPORTED_CATEGORIES,
    ShoppingAgent,
    normalize_color,
)
from backend.fitting_room.schemas import (
    AlternativesResponse,
    ColorSwitchResponse,
    ColorVariation,
    FittingRoomItem,
    FittingRoomMannequin,
    FittingRoomProduct,
    FittingRoomResponse,
    MannequinGender,
    OutfitSummary,
)


FITTING_ROOM_READY = "ready"
FITTING_ROOM_INCOMPLETE = "incomplete"

PRODUCT_NOT_FOUND_ERROR = "product_not_found"

VISUAL_SOURCE_PRODUCT_IMAGE = "product_image"

COLOR_SWITCH_FOUND = "found"
COLOR_SWITCH_NOT_FOUND = "not_found"

NO_PRODUCT_IN_COLOR_REASON = "no_product_in_requested_color"

COLOR_SOURCE_VARIANT = "variant"
COLOR_SOURCE_SEARCH = "search"


_MANNEQUIN_ASSETS: Dict[MannequinGender, str] = {
    MannequinGender.FEMALE: "assets/fitting-room/female-mannequin.png",
    MannequinGender.MALE: "assets/fitting-room/male-mannequin.png",
}


class FittingRoomError(Exception):
    """Base class for Fitting Room service errors."""


class InvalidMannequinGenderError(FittingRoomError):
    """Raised when an unsupported mannequin gender is requested."""


class InvalidCategoryError(FittingRoomError):
    """Raised when an alternatives or color request uses an unsupported category."""


class InvalidColorError(FittingRoomError):
    """Raised when a color-switch request has an empty color."""


def resolve_mannequin(
    mannequin_gender: Union[str, MannequinGender],
) -> FittingRoomMannequin:
    """
    Validate a mannequin gender and resolve it to its static asset path.

    Args:
        mannequin_gender: "female" or "male", or the corresponding enum.

    Returns:
        The resolved mannequin reference.

    Raises:
        InvalidMannequinGenderError:
            If the supplied mannequin gender is unsupported.
    """
    try:
        gender = MannequinGender(mannequin_gender)
    except ValueError as exc:
        valid = ", ".join(g.value for g in MannequinGender)
        raise InvalidMannequinGenderError(
            f"Invalid mannequin_gender: {mannequin_gender!r}. "
            f"Must be one of: {valid}."
        ) from exc

    return FittingRoomMannequin(
        gender=gender,
        asset=_MANNEQUIN_ASSETS[gender],
    )


def _canonical_color(color: Optional[str]) -> Optional[str]:
    """
    Convert a requested color to the catalog spelling.

    Example:
        "Gray" -> "grey"

    Unknown colors are only normalized to lowercase/whitespace form.
    """
    if not color or not color.strip():
        return None

    cleaned = " ".join(color.lower().split())

    return normalize_color(cleaned) or cleaned


def _is_color_match(
    candidate: Dict[str, Any],
    *,
    category: str,
    wanted: str,
    current_product_id: str,
) -> bool:
    """
    Check whether a candidate is a valid real product for the requested color.

    A candidate must:

    - have a product_id
    - be different from the current product
    - belong to the requested category when it states a category
    - have the requested real color
    """
    candidate_id = candidate.get("product_id")

    if candidate_id is None:
        return False

    if candidate_id == current_product_id:
        return False

    if candidate.get("category") not in (None, category):
        return False

    return _canonical_color(candidate.get("color")) == wanted


class FittingRoomService:
    """
    Resolves an already-selected outfit into fitting-room data.

    All shopping data comes through the injected ShoppingAgent.
    """

    def __init__(
        self,
        shopping_agent: Optional[ShoppingAgent] = None,
    ) -> None:
        self._shopping_agent = shopping_agent or ShoppingAgent()

    async def prepare_fitting_room(
        self,
        outfit_result: Union[Dict[str, Any], OutfitSummary],
        mannequin_gender: Union[str, MannequinGender],
        include_variants: bool = True,
        include_alternatives: bool = True,
    ) -> FittingRoomResponse:
        """
        Build the fitting-room response for an already-selected outfit.

        No new outfit search is performed here. Only the product IDs already
        selected by Part 41 are resolved.

        Args:
            outfit_result:
                Part 41's build_outfit() output.

            mannequin_gender:
                "female" or "male".

            include_variants:
                Whether real color variants should be loaded.

            include_alternatives:
                Whether real alternative products should be loaded.

        Returns:
            FittingRoomResponse.
        """
        mannequin = resolve_mannequin(mannequin_gender)

        outfit = (
            outfit_result
            if isinstance(outfit_result, OutfitSummary)
            else OutfitSummary.model_validate(outfit_result)
        )

        items: List[FittingRoomItem] = [
            await self._resolve_item(
                selected.product_id,
                selected.category,
                selected.item_index,
                include_variants=include_variants,
                include_alternatives=include_alternatives,
            )
            for selected in outfit.selected_products
        ]

        overall_status = (
            FITTING_ROOM_READY
            if outfit.status == "complete"
            else FITTING_ROOM_INCOMPLETE
        )

        return FittingRoomResponse(
            status=overall_status,
            mannequin=mannequin,
            outfit=outfit,
            items=items,
        )

    async def get_alternatives(
        self,
        product_id: str,
        category: str,
    ) -> AlternativesResponse:
        """
        Return real alternatives for one selected product.

        The existing ShoppingAgent method is used directly. No independent
        search, ranking, or filtering is performed here.
        """
        if category not in SUPPORTED_CATEGORIES:
            valid = ", ".join(sorted(SUPPORTED_CATEGORIES))
            raise InvalidCategoryError(
                f"Invalid category: {category!r}. "
                f"Must be one of: {valid}."
            )

        raw_alternatives = await self._shopping_agent.get_alternatives(
            product_id
        )

        return AlternativesResponse(
            category=category,
            products=[
                FittingRoomProduct.model_validate(alt)
                for alt in (raw_alternatives or [])
            ],
        )

    async def switch_color(
        self,
        product_id: str,
        category: str,
        color: str,
    ) -> ColorSwitchResponse:
        """
        Resolve a requested color to a REAL retailer product.

        Resolution order:

        1. Check the selected product's existing real variants.
        2. If a matching real variant exists, use it without searching.
        3. Otherwise use the existing ShoppingAgent.search() with category
           and color.
        4. Accept only a real product matching the requested category/color
           and having a different product_id.
        5. If no real product exists, return a structured not_found response.

        No image recoloring, product generation, or fake product creation
        occurs.
        """
        if category not in SUPPORTED_CATEGORIES:
            valid = ", ".join(sorted(SUPPORTED_CATEGORIES))
            raise InvalidCategoryError(
                f"Invalid category: {category!r}. "
                f"Must be one of: {valid}."
            )

        wanted = _canonical_color(color)

        if wanted is None:
            raise InvalidColorError("color must not be empty.")

        requested = color.strip()

        # 1. Existing variant data first.
        raw_variants = await self._shopping_agent.get_variants(product_id)

        for variant in raw_variants or []:
            if not _is_color_match(
                variant,
                category=category,
                wanted=wanted,
                current_product_id=product_id,
            ):
                continue

            product = await self._variant_as_product(variant)

            if product is not None:
                return ColorSwitchResponse(
                    status=COLOR_SWITCH_FOUND,
                    requested_color=requested,
                    category=category,
                    source=COLOR_SOURCE_VARIANT,
                    product=product,
                )

        # 2. No matching variant: use the existing shopping search.
        raw_results = await self._shopping_agent.search(
            category=category,
            color=wanted,
        )

        for candidate in raw_results or []:
            if not _is_color_match(
                candidate,
                category=category,
                wanted=wanted,
                current_product_id=product_id,
            ):
                continue

            return ColorSwitchResponse(
                status=COLOR_SWITCH_FOUND,
                requested_color=requested,
                category=category,
                source=COLOR_SOURCE_SEARCH,
                product=FittingRoomProduct.model_validate(candidate),
            )

        # 3. No real product in requested color.
        return ColorSwitchResponse(
            status=COLOR_SWITCH_NOT_FOUND,
            requested_color=requested,
            category=category,
            reason=NO_PRODUCT_IN_COLOR_REASON,
        )

    async def _variant_as_product(
        self,
        variant: Dict[str, Any],
    ) -> Optional[FittingRoomProduct]:
        """
        Convert a real variant into a FittingRoomProduct.

        If the variant already contains the complete product fields, it is
        used directly. If it only contains a product_id, the actual product
        is resolved through ShoppingAgent.get_product().
        """
        try:
            return FittingRoomProduct.model_validate(variant)
        except ValidationError:
            raw_product = await self._shopping_agent.get_product(
                variant["product_id"]
            )

            if raw_product is None:
                return None

            return FittingRoomProduct.model_validate(raw_product)

    async def _resolve_item(
        self,
        product_id: str,
        category: str,
        item_index: int,
        *,
        include_variants: bool,
        include_alternatives: bool,
    ) -> FittingRoomItem:
        """
        Resolve one already-selected product_id.

        Only product resolution, variant resolution, and alternative
        resolution are performed. No new outfit search occurs.
        """
        raw_product = await self._shopping_agent.get_product(product_id)

        if raw_product is None:
            return FittingRoomItem(
                item_index=item_index,
                category=category,
                product=None,
                visual_source=None,
                color_variations=[],
                alternatives=[],
                error=PRODUCT_NOT_FOUND_ERROR,
            )

        product = FittingRoomProduct.model_validate(raw_product)

        color_variations: List[ColorVariation] = []

        if include_variants:
            raw_variants = await self._shopping_agent.get_variants(
                product_id
            )

            color_variations = [
                ColorVariation.model_validate(variant)
                for variant in (raw_variants or [])
            ]

        alternatives: List[FittingRoomProduct] = []

        if include_alternatives:
            raw_alternatives = await self._shopping_agent.get_alternatives(
                product_id
            )

            alternatives = [
                FittingRoomProduct.model_validate(alt)
                for alt in (raw_alternatives or [])
            ]

        return FittingRoomItem(
            item_index=item_index,
            category=category,
            product=product,
            visual_source=(
                VISUAL_SOURCE_PRODUCT_IMAGE
                if product.image_url
                else None
            ),
            color_variations=color_variations,
            alternatives=alternatives,
            error=None,
        )