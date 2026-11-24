"""Application factory with bounded request bodies and fail-closed model startup."""

import asyncio
import time
from collections import deque
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from phishguard.common.config import Settings
from phishguard.ml.model_registry import URLModel
from phishguard.api.prediction_store import PredictionStore
from phishguard.api.routes import router
from phishguard.api.browser_session import BrowserSession, router as browser_router


from phishguard.api.middleware import InputGuard, RuntimeMetrics, request_id

# Backward-compatible import name for existing local integrations.
BodyLimit = InputGuard


def create_app(settings=None):
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app):
        app.state.store = None
        app.state.vision = None
        task = None
        try:
            model_path = settings.model_path
            if settings.registry_path:
                from phishguard.ml.registry import LocalRegistry

                model_path = LocalRegistry(settings.registry_path).active()["model_path"]
            app.state.model = URLModel.load(model_path)
            if settings.store_events:
                app.state.store = PredictionStore(
                    settings.db_path,
                    settings.hmac_key,
                    settings.retention_days,
                    max_events=settings.max_retained_events,
                )
            if settings.vision_path:
                from phishguard.ml.vision import VisionModel

                app.state.vision = VisionModel(settings.vision_path)

            async def retention_loop():
                while True:
                    await asyncio.sleep(3600)
                    if app.state.store:
                        await asyncio.to_thread(app.state.store.purge)

            if app.state.store is not None:
                task = asyncio.create_task(retention_loop())
            yield
        finally:
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            if app.state.store is not None:
                app.state.store.close()

    app = FastAPI(
        title="PhishGuard",
        version="2.6.1",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = settings
    app.state.runtime_metrics = RuntimeMetrics()
    app.state.browser_session = BrowserSession()
    app.add_middleware(
        InputGuard,
        maximum=settings.max_request_bytes,
        receive_timeout=settings.body_timeout_seconds,
    )
    from starlette.middleware.trustedhost import TrustedHostMiddleware

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))
    # Pure ASGI controls preserve disconnects without BaseHTTPMiddleware's
    # "No response returned" exception when InputGuard receives http.disconnect.
    from phishguard.api.middleware import ResponseControls
    app.add_middleware(ResponseControls, settings=settings, metrics=app.state.runtime_metrics)

    @app.exception_handler(Exception)
    async def internal_error(request, exc):
        return JSONResponse({"detail": "Internal processing error"}, 500)

    # Validation errors normally echo the input URL. Replace them with minimized errors.
    from fastapi.exceptions import RequestValidationError

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse({"detail": "Invalid request; check field types, URL or limits"}, 422)

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "version": "2.6.1",
            "browser_bridge_enabled": True,
            "model_version": app.state.model.version,
            "vision_enabled": app.state.vision is not None,
            "vision_model_version": app.state.vision.version
            if app.state.vision is not None
            else None,
        }

    app.include_router(router)
    app.include_router(browser_router)
    from phishguard.web.router import router as web_router, STATIC
    from fastapi.staticfiles import StaticFiles

    app.include_router(web_router)
    app.mount("/assets", StaticFiles(directory=STATIC / "assets", check_dir=False), name="assets")
    return app
