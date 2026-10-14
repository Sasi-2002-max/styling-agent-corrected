"""Multi-garment virtual try-on via Runware P-Image-Try-On.

The existing mannequin flow remains the fallback. This service only generates
an image when the user explicitly clicks AI Try On; it never calls SerpApi.
"""
from __future__ import annotations

import base64
import mimetypes
import os
from pathlib import Path
from typing import Optional
from uuid import uuid4

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, Field, HttpUrl, field_validator

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env", override=False)

RUNWARE_ENDPOINT = "https://api.runware.ai/v1"
TRYON_MODEL = "prunaai:p-image@try-on"
MAX_MODEL_IMAGE_BYTES = 12 * 1024 * 1024


class TryOnGarment(BaseModel):
    image_url: HttpUrl
    title: str = Field(default="garment", max_length=240)
    category: str = Field(default="clothing", max_length=60)

    @field_validator("image_url")
    @classmethod
    def image_url_must_use_https(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme != "https":
            raise ValueError("Garment image URLs must use HTTPS.")
        return value


class VirtualTryOnRequest(BaseModel):
    # MVP sends the top, bottom/dress, and optionally shoes. Accessories are
    # intentionally omitted because handbags and small items are unreliable.
    garments: list[TryOnGarment] = Field(min_length=1, max_length=4)


class VirtualTryOnConfigurationError(RuntimeError):
    """Local key or default model image is not configured."""


class VirtualTryOnProviderError(RuntimeError):
    """Runware rejected the request or failed to return an image."""


def _model_image_data_uri() -> str:
    configured_path = os.getenv(
        "VIRTUAL_TRYON_MODEL_IMAGE_PATH",
        "backend/assets/virtual_tryon/default_model.jpg",
    ).strip()
    image_path = Path(configured_path)
    if not image_path.is_absolute():
        image_path = PROJECT_ROOT / image_path

    if not image_path.is_file():
        raise VirtualTryOnConfigurationError(
            "Default try-on model image is missing. Add a licensed full-body "
            "model photo at backend/assets/virtual_tryon/default_model.jpg, "
            "or configure VIRTUAL_TRYON_MODEL_IMAGE_PATH in .env."
        )

    image_bytes = image_path.read_bytes()
    if not image_bytes:
        raise VirtualTryOnConfigurationError("Default model image is empty.")
    if len(image_bytes) > MAX_MODEL_IMAGE_BYTES:
        raise VirtualTryOnConfigurationError(
            "Default model image must be 12 MB or smaller."
        )

    mime_type, _ = mimetypes.guess_type(image_path.name)
    if mime_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise VirtualTryOnConfigurationError(
            "Default model image must be a JPG, PNG, or WEBP file."
        )

    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _provider_error_message(payload: object) -> str:
    if not isinstance(payload, dict):
        return "Runware returned an unexpected response."
    errors = payload.get("errors")
    if isinstance(errors, list) and errors:
        first = errors[0]
        if isinstance(first, dict) and isinstance(first.get("message"), str):
            return first["message"][:500]
    error = payload.get("error")
    if isinstance(error, str):
        return error[:500]
    return "Runware did not return a usable try-on image."


async def generate_virtual_try_on(request: VirtualTryOnRequest) -> dict:
    """Generate a single composite try-on image from product image URLs."""
    api_key = (os.getenv("RUNWARE_API_KEY") or "").strip()
    if not api_key:
        raise VirtualTryOnConfigurationError(
            "RUNWARE_API_KEY is missing from the backend .env file."
        )

    person_image = _model_image_data_uri()
    reference_images = [{"image": person_image, "role": "person"}]
    for garment in request.garments:
        reference_images.append({
            "image": str(garment.image_url),
            "role": "garment",
        })

    descriptions = [
        f"{index}. {garment.category}: {garment.title}"
        for index, garment in enumerate(request.garments, start=1)
    ]
    prompt = (
        "Create a natural, believable virtual try-on fashion photo using the "
        "person image as the person to dress and every garment image as a "
        "selected product. Garments in order: " + "; ".join(descriptions) + ". "
        "Preserve the person's face, hair, identity, body shape, body proportions, "
        "pose, hands, and background. Match the selected products' colors and "
        "visible design details; fit them naturally with realistic fabric folds, "
        "correct layering, and soft contact shadows. Keep a clean, simple fashion "
        "catalog look, full body visible, natural lighting, no text, no logos, "
        "no extra garments or accessories. This is a visual preview, not a size fit guarantee."
    )

    task = {
        "taskType": "imageInference",
        "taskUUID": str(uuid4()),
        "model": TRYON_MODEL,
        "positivePrompt": prompt,
        "inputs": {"referenceImages": reference_images},
        "settings": {"turbo": True, "preserveInputSize": True},
        "deliveryMethod": "sync",
        "includeCost": True,
    }

    timeout = httpx.Timeout(100.0, connect=10.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                RUNWARE_ENDPOINT,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=[task],
            )
    except httpx.TimeoutException as exc:
        raise VirtualTryOnProviderError(
            "The try-on image took too long. Please try again later; no automatic retry was made."
        ) from exc
    except httpx.HTTPError as exc:
        raise VirtualTryOnProviderError(
            "Could not connect to the virtual try-on provider."
        ) from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise VirtualTryOnProviderError(
            f"Runware returned a non-JSON response (HTTP {response.status_code})."
        ) from exc

    if response.status_code >= 400:
        raise VirtualTryOnProviderError(_provider_error_message(payload))

    data = payload.get("data") if isinstance(payload, dict) else None
    item = data[0] if isinstance(data, list) and data else None
    image_url = item.get("imageURL") if isinstance(item, dict) else None
    if not isinstance(image_url, str) or not image_url.startswith("https://"):
        raise VirtualTryOnProviderError(_provider_error_message(payload))

    cost = item.get("cost") if isinstance(item, dict) else None
    return {"image_url": image_url, "cost_usd": cost, "model": TRYON_MODEL}
