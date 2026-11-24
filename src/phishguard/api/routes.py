"""Authenticated prediction and data controls; no URL-fetching endpoints."""

import base64
import binascii
import hmac
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.security import APIKeyHeader
from phishguard.common.schemas import URLRequest, URLBatch, ImageRequest, Prediction

router = APIRouter(prefix="/api/v1")
key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def authorized(request: Request, key: str | None = Depends(key_header)):
    if not key or not hmac.compare_digest(
        key.encode("utf-8"), request.app.state.settings.api_key.encode("utf-8")
    ):
        raise HTTPException(401, "Invalid API key")
    return True


def predict_one(request, url):
    result = Prediction(**request.app.state.model.predict(url))
    if request.app.state.store:
        request.app.state.store.add(url, result)
    return result


@router.post("/predict/url", response_model=Prediction, dependencies=[Depends(authorized)])
def predict_url(payload: URLRequest, request: Request):
    return predict_one(request, payload.url)


@router.post("/predict/batch", response_model=list[Prediction], dependencies=[Depends(authorized)])
def predict_batch(payload: URLBatch, request: Request):
    return [predict_one(request, item.url) for item in payload.items]


@router.post("/predict/image", response_model=Prediction, dependencies=[Depends(authorized)])
def predict_image(payload: ImageRequest, request: Request):
    if request.app.state.vision is None:
        raise HTTPException(503, "Screenshot model is disabled or not trained")
    try:
        data = base64.b64decode(payload.image_base64, validate=True)
        return Prediction(**request.app.state.vision.predict(data))
    except (ValueError, binascii.Error):
        raise HTTPException(422, "Invalid or oversized PNG/JPEG") from None


@router.get("/predictions", dependencies=[Depends(authorized)])
def predictions(request: Request, limit: int = Query(100, ge=1, le=1000)):
    store = request.app.state.store
    return {"storage_enabled": store is not None, "items": store.list(limit) if store else []}


@router.delete("/predictions", dependencies=[Depends(authorized)])
def clear(request: Request):
    if request.app.state.store:
        request.app.state.store.clear()
    return {"cleared": True, "note": "Logical deletion; not guaranteed physical disk erasure"}


@router.get("/metrics", dependencies=[Depends(authorized)])
def metrics(request: Request):
    store = request.app.state.store
    return {
        "storage_enabled": store is not None,
        "runtime": request.app.state.runtime_metrics.snapshot(),
        **(store.metrics() if store else {"retained_predictions": 0, "phishing_predictions": 0}),
    }
