from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy.orm import Session

from backend.models.product import Product
from backend.models.saved_look import SavedLook
from backend.models.user import User
from backend.models.wardrobe_item import WardrobeItem


class WardrobeInputError(ValueError):
    """Raised when a save request does not contain a usable product or look."""


def _public_http_url(value: Any, field_name: str, required: bool = False) -> Optional[str]:
    if value is None or value == "":
        if required:
            raise WardrobeInputError(f"{field_name} is required.")
        return None
    if not isinstance(value, str):
        raise WardrobeInputError(f"{field_name} must be a URL.")
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise WardrobeInputError(f"{field_name} must start with http:// or https://.")
    return value.strip()


def _ensure_user(db: Session, user_id: UUID) -> User:
    """Create a local demo identity on first use; this is not authentication."""
    user = db.get(User, user_id)
    if user is None:
        user = User(id=user_id, email=f"guest-{user_id.hex}@styleai.local")
        db.add(user)
        db.flush()
    return user


def _price(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise WardrobeInputError("Product price must be a number.") from exc
    if not amount.is_finite() or amount < 0:
        raise WardrobeInputError("Product price must be zero or greater.")
    return amount


def _product_from_source(db: Session, source: Dict[str, Any]) -> Product:
    source_id = source.get("product_id") or source.get("id")
    title = source.get("title") or source.get("product_name") or source.get("name")
    product_url = _public_http_url(source.get("product_url"), "product_url", True)
    if not source_id:
        raise WardrobeInputError("Product is missing product_id.")
    if not isinstance(title, str) or not title.strip():
        raise WardrobeInputError("Product is missing a title.")

    # The shopping catalog uses IDs such as MOCK066, while the existing
    # products table intentionally has a UUID primary key.  Match/upsert on
    # retailer URL and retain the original catalog ID in JSON metadata.
    product = db.query(Product).filter(Product.product_url == product_url).first()
    if product is None:
        raw_sizes = source.get("sizes")
        sizes = raw_sizes if isinstance(raw_sizes, list) else []
        raw_metadata = {
            "source_product_id": str(source_id),
            "source_product": source,
        }
        product = Product(
            store=source.get("store"),
            brand=source.get("brand"),
            title=title.strip(),
            category=source.get("category"),
            color=source.get("color"),
            price=_price(source.get("price")),
            currency=str(source.get("currency") or "INR")[:3].upper(),
            sizes=sizes,
            image_url=_public_http_url(source.get("image_url"), "image_url"),
            product_url=product_url,
            availability=source.get("availability") is not False,
            product_metadata=raw_metadata,
        )
        db.add(product)
        db.flush()
    return product


def _attach_product(
    db: Session,
    *,
    user_id: UUID,
    product: Product,
    category: Optional[str],
    saved_from_look_id: Optional[UUID] = None,
) -> WardrobeItem:
    existing = (
        db.query(WardrobeItem)
        .filter(
            WardrobeItem.user_id == user_id,
            WardrobeItem.product_id == product.product_id,
            WardrobeItem.saved_from_look_id == saved_from_look_id,
        )
        .first()
    )
    if existing is not None:
        return existing
    item = WardrobeItem(
        user_id=user_id,
        product_id=product.product_id,
        category=category or product.category,
        saved_from_look_id=saved_from_look_id,
    )
    db.add(item)
    db.flush()
    return item


def _product_json(product: Product) -> Dict[str, Any]:
    metadata = product.product_metadata or {}
    return {
        "product_id": metadata.get("source_product_id") or str(product.product_id),
        "store": product.store,
        "brand": product.brand,
        "title": product.title,
        "category": product.category,
        "color": product.color,
        "price": float(product.price) if product.price is not None else None,
        "currency": product.currency or "INR",
        "sizes": product.sizes or [],
        "image_url": product.image_url,
        "product_url": product.product_url,
        "availability": product.availability,
    }


def _wardrobe_item_json(item: WardrobeItem) -> Dict[str, Any]:
    return {
        "wardrobe_item_id": str(item.wardrobe_item_id),
        "category": item.category,
        "saved_from_look_id": (
            str(item.saved_from_look_id) if item.saved_from_look_id else None
        ),
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "product": _product_json(item.product),
    }


def _look_json(look: SavedLook) -> Dict[str, Any]:
    return {
        "saved_look_id": str(look.saved_look_id),
        "name": look.name,
        "occasion": look.occasion,
        "total_price": float(look.total_price) if look.total_price is not None else None,
        "fitting_room_image_url": look.fitting_room_image_url,
        "created_at": look.created_at.isoformat() if look.created_at else None,
        "products": [_wardrobe_item_json(item) for item in look.wardrobe_items],
    }


def save_look(
    db: Session,
    *,
    user_id: UUID,
    style_response: Dict[str, Any],
    name: Optional[str] = None,
) -> Dict[str, Any]:
    if not isinstance(style_response, dict):
        raise WardrobeInputError("style_response must be an object.")
    approved = style_response.get("approved") is True or (
        str(style_response.get("status") or "").lower() == "approved"
    )
    if not approved:
        raise WardrobeInputError("Only an approved look can be saved.")

    selected = style_response.get("selected_products") or []
    if not isinstance(selected, list) or not selected:
        raise WardrobeInputError("The approved look contains no selected products.")

    plan = style_response.get("outfit_plan") or {}
    fitting_room = style_response.get("fitting_room") or {}
    fitting_outfit = fitting_room.get("outfit") or {}
    occasion = str(plan.get("occasion") or "")[:100] or None
    look_name = (name or occasion or "Saved outfit").strip()[:150]
    total_price = fitting_outfit.get("total_price")
    if total_price is None:
        total_price = sum(
            float(item.get("price") or 0)
            for item in selected
            if isinstance(item, dict)
        )

    try:
        _ensure_user(db, user_id)
        look = SavedLook(
            user_id=user_id,
            name=look_name,
            occasion=occasion,
            total_price=_price(total_price),
            fitting_room_image_url=_public_http_url(
                fitting_room.get("image_url"), "fitting_room.image_url"
            ),
        )
        db.add(look)
        db.flush()

        seen_source_ids = set()
        for source in selected:
            if not isinstance(source, dict):
                continue
            source_id = str(source.get("product_id") or source.get("id") or "")
            if source_id and source_id in seen_source_ids:
                continue
            if source_id:
                seen_source_ids.add(source_id)
            product = _product_from_source(db, source)
            _attach_product(
                db,
                user_id=user_id,
                product=product,
                category=source.get("category"),
                saved_from_look_id=look.saved_look_id,
            )

        db.commit()
        db.refresh(look)
        return _look_json(look)
    except Exception:
        db.rollback()
        raise


def save_product(
    db: Session,
    *,
    user_id: UUID,
    source: Dict[str, Any],
) -> Dict[str, Any]:
    try:
        _ensure_user(db, user_id)
        product = _product_from_source(db, source)
        item = _attach_product(
            db,
            user_id=user_id,
            product=product,
            category=source.get("category"),
        )
        db.commit()
        db.refresh(item)
        return _wardrobe_item_json(item)
    except Exception:
        db.rollback()
        raise


def get_saved_looks(db: Session, *, user_id: UUID) -> list[Dict[str, Any]]:
    _ensure_user(db, user_id)
    db.commit()
    looks = (
        db.query(SavedLook)
        .filter(SavedLook.user_id == user_id)
        .order_by(SavedLook.created_at.desc())
        .all()
    )
    return [_look_json(look) for look in looks]


def get_saved_products(db: Session, *, user_id: UUID) -> list[Dict[str, Any]]:
    _ensure_user(db, user_id)
    db.commit()
    items = (
        db.query(WardrobeItem)
        .filter(
            WardrobeItem.user_id == user_id,
            WardrobeItem.saved_from_look_id.is_(None),
        )
        .order_by(WardrobeItem.created_at.desc())
        .all()
    )
    return [_wardrobe_item_json(item) for item in items]


def remove_look(db: Session, *, user_id: UUID, look_id: UUID) -> bool:
    look = (
        db.query(SavedLook)
        .filter(
            SavedLook.saved_look_id == look_id,
            SavedLook.user_id == user_id,
        )
        .first()
    )
    if look is None:
        return False
    db.delete(look)
    db.commit()
    return True


def remove_product(db: Session, *, user_id: UUID, item_id: UUID) -> bool:
    item = (
        db.query(WardrobeItem)
        .filter(
            WardrobeItem.wardrobe_item_id == item_id,
            WardrobeItem.user_id == user_id,
            WardrobeItem.saved_from_look_id.is_(None),
        )
        .first()
    )
    if item is None:
        return False
    db.delete(item)
    db.commit()
    return True