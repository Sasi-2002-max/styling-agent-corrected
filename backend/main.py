from typing import Any, Dict, Optional

import logging

from fastapi import FastAPI, HTTPException

from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel, Field

from sqlalchemy import text

from backend.agents.orchestrator import (
    build_final_response,
    run_orchestrator_async,
)

from backend.database.connection import (
    DatabaseConfigurationError,
    get_engine,
)

from backend.utils.llm import LLMConfigurationError

from backend.fitting_room.schemas import (
    AlternativesRequest,
    AlternativesResponse,
    ColorSwitchRequest,
    ColorSwitchResponse,
    FittingRoomRequest,
    FittingRoomResponse,
)

from backend.fitting_room.service import (
    FittingRoomService,
    InvalidCategoryError,
    InvalidColorError,
    InvalidMannequinGenderError,
)

# ---------------------------------------------------------------------------
# Part 57 - Profile & Product Router
# ---------------------------------------------------------------------------

from backend.api.profile_product_router import (
    router as profile_product_router,
)

# ---------------------------------------------------------------------------
# Wardrobe Router
# ---------------------------------------------------------------------------

from backend.wardrobe.router import router as wardrobe_router


app = FastAPI(title="AI Fashion Stylist API")

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Part 57 - Profile & Product API
# ---------------------------------------------------------------------------

app.include_router(profile_product_router)


# ---------------------------------------------------------------------------
# Wardrobe API
# ---------------------------------------------------------------------------

app.include_router(wardrobe_router)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
def health_check() -> Dict[str, str]:
    """
    Basic API health check.
    """
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Database test
# ---------------------------------------------------------------------------

@app.get("/db-test")
def database_test() -> Dict[str, Any]:
    """
    Test whether the configured database connection is working.
    """
    try:
        engine = get_engine()
    except DatabaseConfigurationError as exc:
        return {
            "status": "error",
            "database": "configuration_error",
            "message": str(exc),
        }

    if engine is None:
        return {
            "status": "not_configured",
            "database": "unavailable",
            "message": "DATABASE_URL is not set.",
        }

    try:
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))

            return {
                "status": "success",
                "database": "connected",
                "result": result.scalar(),
            }

    except Exception as exc:
        return {
            "status": "error",
            "database": "connection_failed",
            "error": str(exc),
        }


# ---------------------------------------------------------------------------
# Fitting Room
# ---------------------------------------------------------------------------

@app.post(
    "/api/fitting-room",
    response_model=FittingRoomResponse,
)
async def fitting_room(
    request: FittingRoomRequest,
) -> FittingRoomResponse:
    """
    Part 42:

    Resolve an already-selected outfit into fitting-room data:

        selected products
        + mannequin
        + real product images
        + color variations
        + alternatives
    """

    service = FittingRoomService()

    try:
        return await service.prepare_fitting_room(
            outfit_result=request.outfit,
            mannequin_gender=request.mannequin_gender,
            include_variants=request.include_variants,
            include_alternatives=request.include_alternatives,
        )

    except InvalidMannequinGenderError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc


# ---------------------------------------------------------------------------
# Fitting Room Alternatives
# ---------------------------------------------------------------------------

@app.post(
    "/api/fitting-room/alternatives",
    response_model=AlternativesResponse,
)
async def fitting_room_alternatives(
    request: AlternativesRequest,
) -> AlternativesResponse:
    """
    Part 45:

    Return real alternatives for one selected product.

    Flow:

        API
          ↓
        FittingRoomService
          ↓
        ShoppingAgent
          ↓
        MCP
    """

    service = FittingRoomService()

    try:
        return await service.get_alternatives(
            product_id=request.product_id,
            category=request.category,
        )

    except InvalidCategoryError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc


# ---------------------------------------------------------------------------
# Fitting Room Color Switching
# ---------------------------------------------------------------------------

@app.post(
    "/api/fitting-room/switch-color",
    response_model=ColorSwitchResponse,
)
async def fitting_room_switch_color(
    request: ColorSwitchRequest,
) -> ColorSwitchResponse:
    """
    Part 46:

    Resolve a requested color to a REAL retailer product.

    Resolution:

        Existing variant
             ↓
        Shopping search
             ↓
        Real matching product
             ↓
        not_found if unavailable
    """

    service = FittingRoomService()

    try:
        return await service.switch_color(
            product_id=request.product_id,
            category=request.category,
            color=request.color,
        )

    except (
        InvalidCategoryError,
        InvalidColorError,
    ) as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc


# ---------------------------------------------------------------------------
# Styling / Orchestrator
# ---------------------------------------------------------------------------

class StylingRequest(BaseModel):
    user_profile: Optional[Dict[str, Any]] = None
    user_query: str = Field(min_length=1)


@app.post("/api/style")
async def create_style(request: StylingRequest):
    """
    Run the complete fashion-styling workflow.
    """

    if not request.user_query.strip():
        raise HTTPException(
            status_code=422,
            detail="user_query must not be blank.",
        )

    try:
        state = await run_orchestrator_async(
            user_profile=request.user_profile,
            user_query=request.user_query,
        )

        return build_final_response(state)

    except LLMConfigurationError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        logger.exception("Styling request failed.")

        raise HTTPException(
            status_code=500,
            detail=(
                "Styling request failed. "
                "Check the API server logs for details."
            ),
        ) from exc
