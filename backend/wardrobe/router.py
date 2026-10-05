from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.database.connection import DatabaseConfigurationError, get_db
from backend.wardrobe.schemas import SaveLookRequest, SaveProductRequest
from backend.wardrobe.wardrobe_service import (
    WardrobeInputError,
    get_saved_looks,
    get_saved_products,
    remove_look,
    remove_product,
    save_look,
    save_product,
)

router = APIRouter(prefix="/api/wardrobe", tags=["wardrobe"])


def _wardrobe_db():
    try:
        yield from get_db()
    except DatabaseConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/looks")
def create_saved_look(
    request: SaveLookRequest,
    db: Session = Depends(_wardrobe_db),
):
    try:
        return save_look(
            db,
            user_id=request.user_id,
            style_response=request.style_response,
            name=request.name,
        )
    except WardrobeInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/looks")
def list_saved_looks(
    user_id: UUID = Query(...),
    db: Session = Depends(_wardrobe_db),
):
    return {"looks": get_saved_looks(db, user_id=user_id)}


@router.delete("/looks/{look_id}")
def delete_saved_look(
    look_id: UUID,
    user_id: UUID = Query(...),
    db: Session = Depends(_wardrobe_db),
):
    if not remove_look(db, user_id=user_id, look_id=look_id):
        raise HTTPException(status_code=404, detail="Saved look not found.")
    return {"deleted": True, "saved_look_id": str(look_id)}


@router.post("/products")
def create_saved_product(
    request: SaveProductRequest,
    db: Session = Depends(_wardrobe_db),
):
    try:
        return save_product(
            db,
            user_id=request.user_id,
            source=request.product,
        )
    except WardrobeInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/products")
def list_saved_products(
    user_id: UUID = Query(...),
    db: Session = Depends(_wardrobe_db),
):
    return {"products": get_saved_products(db, user_id=user_id)}


@router.delete("/products/{item_id}")
def delete_saved_product(
    item_id: UUID,
    user_id: UUID = Query(...),
    db: Session = Depends(_wardrobe_db),
):
    if not remove_product(db, user_id=user_id, item_id=item_id):
        raise HTTPException(status_code=404, detail="Saved product not found.")
    return {"deleted": True, "wardrobe_item_id": str(item_id)}