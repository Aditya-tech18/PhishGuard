from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter()
STATIC = Path(__file__).with_name("static")


@router.get("/", include_in_schema=False)
async def home():
    return FileResponse(STATIC / "index.html", media_type="text/html")


@router.get("/live-detection", include_in_schema=False)
async def live():
    return FileResponse(STATIC / "live-detection.html", media_type="text/html")


@router.get("/model-and-system", include_in_schema=False)
async def models():
    return FileResponse(STATIC / "model-and-system.html", media_type="text/html")
