"""Stateless URL-only cloud profile. No SQLite, image runtime or worker processes."""

import os
import re
from pathlib import Path
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from phishguard.api.main import create_app
from phishguard.common.config import Settings
from phishguard.common.files import read_json


def cloud_hosts(environment):
    hosts = {"localhost", "127.0.0.1", "testserver"}
    for name in ["VERCEL_URL", "VERCEL_PROJECT_PRODUCTION_URL", "PHISHGUARD_ALLOWED_HOSTS"]:
        for value in environment.get(name, "").split(","):
            value = value.strip().lower()
            if not value:
                continue
            if (
                len(value) > 253
                or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", value)
                or ".." in value
            ):
                raise ValueError(
                    "Cloud hosts must be explicit DNS names, without scheme, wildcard or path"
                )
            hosts.add(value)
    return tuple(sorted(hosts))


def create_cloud_app(bundle_root, environment=None):
    environment = dict(os.environ if environment is None else environment)
    if environment.get("PHISHGUARD_STORE_EVENTS", "false").lower() != "false":
        raise ValueError("Persistent event storage is unsupported in this stateless cloud profile")
    if environment.get("PHISHGUARD_VISION_MODEL") or environment.get("PHISHGUARD_REGISTRY"):
        raise ValueError(
            "Cloud profile uses only its bundled URL model; vision/registry run separately"
        )
    root = Path(bundle_root).resolve(strict=True)
    settings = Settings(
        api_key=environment.get("PHISHGUARD_API_KEY", ""),
        model_path=root / "models/url-model.json",
        db_path=root / "disabled-event-store.sqlite",
        allowed_hosts=cloud_hosts(environment),
        store_events=False,
        rate_limit=int(environment.get("PHISHGUARD_RATE_LIMIT", "60")),
        max_request_bytes=65536,
    )
    # Validate at construction so a deployment with missing/mismatched artifacts fails closed.
    from phishguard.ml.model_registry import URLModel

    model = URLModel.load(settings.model_path)
    card = read_json(root / "models/model-card.json")
    if card.get("model_version") != model.version:
        raise ValueError("Bundled model card identity mismatch")
    app = create_app(settings)
    assets = root / "public/assets"
    app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/", include_in_schema=False)
    def home():
        return FileResponse(root / "public/index.html")

    @app.get("/api/v1/model-card")
    def model_card():
        return {
            **card,
            "deployment_profile": "stateless-url-only",
            "image_inference": False,
            "retained_predictions": False,
            "rate_limit_scope": "per-warm-instance",
        }

    @app.middleware("http")
    async def web_headers(request, call_next):
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith("/assets/"):
            response.headers["Content-Security-Policy"] = (
                "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "
                "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
            )
        return response

    return app
