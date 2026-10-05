from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.database.connection import get_db
from backend.models.product import Product
from backend.models.profile import Profile
from backend.models.user import User
from backend.schemas.product import ProductSchema
from backend.schemas.profile import ProfileSchema


router = APIRouter(
    prefix="/api",
    tags=["Profile & Products"],
)


# ---------------------------------------------------------------------------
# PROFILE SCHEMAS
# ---------------------------------------------------------------------------

class ProfileCreateRequest(BaseModel):
    user_id: UUID
    name: str = Field(min_length=1, max_length=100)
    age: int = Field(ge=1, le=120)
    gender: str
    body_shape: str
    skin_tone: str
    height_cm: float = Field(gt=0)
    weight_kg: float = Field(gt=0)


class ProfileResponse(ProfileCreateRequest):
    profile_id: UUID


# ---------------------------------------------------------------------------
# PRODUCT ALTERNATIVE SCHEMA
# ---------------------------------------------------------------------------

class ProductAlternativesRequest(BaseModel):
    product_id: Optional[UUID] = None
    category: Optional[str] = None
    color: Optional[str] = None
    max_price: Optional[float] = Field(default=None, ge=0)
    limit: int = Field(default=5, ge=1, le=20)


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _product_to_response(product: Product) -> dict[str, Any]:
    return {
        "product_id": str(product.product_id),
        "store": product.store,
        "brand": product.brand,
        "title": product.title,
        "category": product.category,
        "color": product.color,
        "price": (
            float(product.price)
            if isinstance(product.price, Decimal)
            else product.price
        ),
        "currency": product.currency,
        "sizes": product.sizes or [],
        "image_url": product.image_url,
        "product_url": product.product_url,
        "availability": product.availability,
        "metadata": product.product_metadata or {},
    }


# ---------------------------------------------------------------------------
# PROFILE ENDPOINTS
# ---------------------------------------------------------------------------

@router.post(
    "/profile",
    response_model=ProfileResponse,
)
def create_profile(
    payload: ProfileCreateRequest,
    db: Session = Depends(get_db),
):
    """
    Create or update the profile belonging to an existing user.
    """

    user = (
        db.query(User)
        .filter(User.id == payload.user_id)
        .first()
    )

    if user is None:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    existing_profile = (
        db.query(Profile)
        .filter(Profile.user_id == payload.user_id)
        .first()
    )

    if existing_profile is not None:
        existing_profile.name = payload.name
        existing_profile.age = payload.age
        existing_profile.height_cm = payload.height_cm
        existing_profile.weight_kg = payload.weight_kg
        existing_profile.gender = payload.gender
        existing_profile.body_shape = payload.body_shape
        existing_profile.skin_tone = payload.skin_tone

        db.commit()
        db.refresh(existing_profile)

        return ProfileResponse(
            profile_id=existing_profile.id,
            user_id=existing_profile.user_id,
            name=existing_profile.name,
            age=existing_profile.age,
            gender=existing_profile.gender,
            body_shape=existing_profile.body_shape,
            skin_tone=existing_profile.skin_tone,
            height_cm=existing_profile.height_cm,
            weight_kg=existing_profile.weight_kg,
        )

    profile = Profile(
        user_id=payload.user_id,
        name=payload.name,
        age=payload.age,
        height_cm=payload.height_cm,
        weight_kg=payload.weight_kg,
        gender=payload.gender,
        body_shape=payload.body_shape,
        skin_tone=payload.skin_tone,
    )

    db.add(profile)
    db.commit()
    db.refresh(profile)

    return ProfileResponse(
        profile_id=profile.id,
        user_id=profile.user_id,
        name=profile.name,
        age=profile.age,
        gender=profile.gender,
        body_shape=profile.body_shape,
        skin_tone=profile.skin_tone,
        height_cm=profile.height_cm,
        weight_kg=profile.weight_kg,
    )


@router.get(
    "/profile/{user_id}",
    response_model=ProfileResponse,
)
def get_profile(
    user_id: UUID,
    db: Session = Depends(get_db),
):
    """
    Get the fashion profile belonging to a user.
    """

    profile = (
        db.query(Profile)
        .filter(Profile.user_id == user_id)
        .first()
    )

    if profile is None:
        raise HTTPException(
            status_code=404,
            detail="Profile not found",
        )

    return ProfileResponse(
        profile_id=profile.id,
        user_id=profile.user_id,
        name=profile.name,
        age=profile.age,
        gender=profile.gender,
        body_shape=profile.body_shape,
        skin_tone=profile.skin_tone,
        height_cm=profile.height_cm,
        weight_kg=profile.weight_kg,
    )


# ---------------------------------------------------------------------------
# PRODUCT ENDPOINTS
# ---------------------------------------------------------------------------

@router.get(
    "/products/{product_id}",
    response_model=ProductSchema,
)
def get_product(
    product_id: UUID,
    db: Session = Depends(get_db),
):
    """
    Get one product from the global product catalog.
    """

    product = (
        db.query(Product)
        .filter(Product.product_id == product_id)
        .first()
    )

    if product is None:
        raise HTTPException(
            status_code=404,
            detail="Product not found",
        )

    return _product_to_response(product)


@router.post(
    "/products/alternatives",
    response_model=list[ProductSchema],
)
def get_product_alternatives(
    payload: ProductAlternativesRequest,
    db: Session = Depends(get_db),
):
    """
    Find alternative products using the existing product catalog.

    Alternatives are filtered by category, optionally color and price.
    """

    query = db.query(Product).filter(
        Product.availability.is_(True)
    )

    if payload.product_id is not None:
        query = query.filter(
            Product.product_id != payload.product_id
        )

    if payload.category:
        query = query.filter(
            Product.category.ilike(
                f"%{payload.category.strip()}%"
            )
        )

    if payload.color:
        query = query.filter(
            or_(
                Product.color.ilike(
                    f"%{payload.color.strip()}%"
                ),
                Product.color.is_(None),
            )
        )

    if payload.max_price is not None:
        query = query.filter(
            Product.price <= payload.max_price
        )

    products = (
        query
        .order_by(Product.price.asc())
        .limit(payload.limit)
        .all()
    )

    return [
        _product_to_response(product)
        for product in products
    ]