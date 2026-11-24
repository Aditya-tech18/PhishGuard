"""Authenticated, memory-only browser session snapshots and dashboard WebSocket updates."""

import asyncio
from collections import deque
import hmac
import ipaddress
import json
import os
from pathlib import Path
import time
from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field, field_validator

from phishguard.api.routes import authorized

router = APIRouter(prefix="/api/v1/browser")
Short = Annotated[str, Field(max_length=200)]


class TabState(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    tab_id: int = Field(ge=0)
    origin: str = Field(max_length=2048)
    state: Literal["queued", "checking", "complete", "unavailable"]
    scan_id: str = Field(default="", max_length=80)
    verdict: Literal["phishing", "low_risk"] | None = None
    probability: float | None = Field(default=None, ge=0, le=1)
    model_version: str = Field(default="", max_length=120)
    reasons: list[Short] = Field(default_factory=list, max_length=4)
    checked_at: float | None = Field(default=None, ge=0)
    latency_ms: float | None = Field(default=None, ge=0, le=120000)

    @field_validator("origin")
    @classmethod
    def origin_only(cls, value):
        parsed = urlsplit(value)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path not in {"", "/"}):
            raise ValueError("Only an HTTP(S) origin is accepted")
        return parsed.scheme + "://" + parsed.netloc


class BrowserReport(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    extension_id: str = Field(pattern=r"^[a-p]{32}$")
    agent_id: str = Field(min_length=16, max_length=80)
    enabled: bool
    paused_until: float = Field(default=0, ge=0)
    permission_granted: bool = False
    tabs: list[TabState] = Field(default_factory=list, max_length=200)
    total_tabs: int = Field(default=0, ge=0, le=100000)


class Feedback(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tab_id: int = Field(ge=0)
    kind: Literal["false_positive", "missed_warning"]


class BrowserSession:
    """One local operator session; no browsing state is written to disk."""

    def __init__(self):
        self.started = time.time()
        self.last_seen = 0.0
        self.enabled = False
        self.paused_until = 0.0
        self.extension_id = None
        self.agent_id = None
        self.permission_granted = False
        self.tabs = []
        self.total_tabs = 0
        self.events = deque(maxlen=200)
        self.latencies = deque(maxlen=1024)
        self.last_scans = {}
        self.checked = self.flagged = self.low_risk = self.feedback_count = 0
        self.revision = 0
        self.listeners = set()

    def snapshot(self):
        connected = bool(self.last_seen and time.time() - self.last_seen < 150)
        latencies = list(self.latencies)
        return {
            "revision": self.revision, "extension_connected": connected,
            "extension_id": self.extension_id, "enabled": self.enabled and connected,
            "reported_enabled": self.enabled, "paused_until": self.paused_until,
            "permission_granted": self.permission_granted, "last_seen": self.last_seen or None,
            "started_at": self.started, "tabs": self.tabs if connected else [],
            "total_tabs": self.total_tabs if connected else 0,
            "events": list(reversed(self.events)),
            "metrics": {"checked": self.checked, "flagged": self.flagged,
                        "low_risk": self.low_risk,
                        "average_latency_ms": sum(latencies) / len(latencies) if latencies else None,
                        "latency_samples": len(latencies), "feedback_count": self.feedback_count},
            "storage": "memory_only_current_backend_session",
        }

    def changed(self):
        self.revision += 1
        for queue in tuple(self.listeners):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(self.snapshot())

    def clear(self):
        listeners = self.listeners
        self.__init__()
        self.listeners = listeners
        self.changed()

    def update(self, report):
        now = time.time()
        if self.agent_id and self.agent_id != report.agent_id and now - self.last_seen < 150:
            raise HTTPException(409, "Another browser session is connected; disconnect it first")
        self.agent_id, self.extension_id = report.agent_id, report.extension_id
        self.last_seen, self.enabled = now, report.enabled
        self.paused_until = report.paused_until
        self.permission_granted = report.permission_granted
        self.total_tabs = report.total_tabs
        self.tabs = [tab.model_dump() for tab in report.tabs] if report.enabled else []
        for tab in report.tabs if report.enabled else []:
            if (tab.state != "complete" or not tab.scan_id or tab.verdict is None
                    or self.last_scans.get(tab.tab_id) == tab.scan_id):
                continue
            self.last_scans[tab.tab_id] = tab.scan_id
            self.checked += 1
            self.flagged += int(tab.verdict == "phishing")
            self.low_risk += int(tab.verdict == "low_risk")
            if tab.latency_ms is not None:
                self.latencies.append(tab.latency_ms)
            self.events.append({"time": now, "kind": "scan", "tab_id": tab.tab_id,
                                "origin": tab.origin, "verdict": tab.verdict,
                                "model_version": tab.model_version, "scan_id": tab.scan_id})
        current = {tab.tab_id for tab in report.tabs}
        self.last_scans = {key: value for key, value in self.last_scans.items() if key in current}
        if not report.enabled:
            # Turning OFF removes session browsing identifiers, rather than retaining history.
            self.events.clear()
            self.last_scans.clear()
        self.changed()


@router.get("/session", dependencies=[Depends(authorized)])
async def session(request: Request):
    return request.app.state.browser_session.snapshot()


@router.post("/report", dependencies=[Depends(authorized)])
async def report(payload: BrowserReport, request: Request):
    request.app.state.browser_session.update(payload)
    return {"ok": True, "revision": request.app.state.browser_session.revision}


@router.post("/feedback", dependencies=[Depends(authorized)])
async def feedback(payload: Feedback, request: Request):
    state = request.app.state.browser_session
    if not any(tab["tab_id"] == payload.tab_id for tab in state.tabs):
        raise HTTPException(404, "Tab is not in the connected session")
    state.feedback_count += 1
    state.events.append({"time": time.time(), "kind": payload.kind, "tab_id": payload.tab_id})
    state.changed()
    return {"accepted": True, "storage": "memory_only", "automatically_retrained": False}


@router.post("/disconnect", dependencies=[Depends(authorized)])
async def disconnect(request: Request):
    request.app.state.browser_session.clear()
    return {"disconnected": True}


def same_origin(origin, host):
    try:
        parsed = urlsplit(origin)
        return parsed.scheme in {"http", "https"} and parsed.netloc == host
    except ValueError:
        return False


@router.websocket("/ws")
async def browser_socket(socket: WebSocket):
    if not same_origin(socket.headers.get("origin", ""), socket.headers.get("host", "")):
        await socket.close(code=1008)
        return
    await socket.accept()
    queue = asyncio.Queue(maxsize=4)
    state = socket.app.state.browser_session
    try:
        raw = await asyncio.wait_for(socket.receive_text(), timeout=5)
        if len(raw) > 1024:
            await socket.close(code=1008)
            return
        data = json.loads(raw)
        if not isinstance(data, dict):
            await socket.close(code=1008)
            return
        key = data.get("api_key", "")
        if (data.get("type") != "authenticate" or not isinstance(key, str)
                or not hmac.compare_digest(key.encode("utf-8"), socket.app.state.settings.api_key.encode("utf-8"))):
            await socket.close(code=1008)
            return
        state.listeners.add(queue)
        await socket.send_json(state.snapshot())
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=10)
            except asyncio.TimeoutError:
                item = state.snapshot()
            await socket.send_json(item)
    except (WebSocketDisconnect, asyncio.TimeoutError, ValueError, RuntimeError):
        pass
    finally:
        state.listeners.discard(queue)


@router.post("/ui-session")
async def ui_session(request: Request):
    """Local same-origin bootstrap. Cross-site pages cannot obtain the API credential."""
    try:
        local = ipaddress.ip_address(request.client.host).is_loopback
    except (ValueError, AttributeError):
        local = False
    origin = request.headers.get("origin", "")
    if (not local or request.headers.get("sec-fetch-site") != "same-origin"
            or request.headers.get("x-phishguard-ui") != "1"
            or (origin and not same_origin(origin, request.headers.get("host", "")))):
        raise HTTPException(403, "Use the local dashboard or explicitly provide your session API key")
    return {"api_key": request.app.state.settings.api_key, "storage": "frontend_memory_only"}


def clean_report(path):
    if not path.is_file() or path.stat().st_size > 5_000_000:
        return None
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None


@router.get("/evidence", dependencies=[Depends(authorized)])
async def evidence(request: Request):
    root = Path(__file__).resolve().parents[3]
    reports = Path(os.environ.get("PHISHGUARD_REPORT_ROOT", str(root / "reports")))
    url = clean_report(reports / "evaluation.json") or {}
    vision = clean_report(request.app.state.settings.vision_path.with_suffix(".json")) if request.app.state.settings.vision_path else None
    if vision is None:
        vision = clean_report(root / "models/trained/vision-model.json") or {}
    quality = clean_report(reports / "data-quality.json") or {}
    pipeline = clean_report(reports / "pipeline.json") or {}
    from phishguard.features.feature_schema import FEATURE_NAMES
    return {
        "url": {key: url[key] for key in ("model_version", "algorithm", "threshold", "metrics", "test", "held_out_test", "split", "split_rows", "unique_rows", "input_counts", "winner", "limitations", "dataset", "feature_names", "data") if key in url},
        "vision": {key: vision[key] for key in ("architecture", "model_version", "threshold", "test_audit_after_policy_revision", "first_locked_test", "data", "new_independent_test_still_required", "training_history") if key in vision},
        "url_model_version": request.app.state.model.version,
        "url_algorithm": request.app.state.model.algorithm,
        "features": list(FEATURE_NAMES),
        "quality": quality, "pipeline": pipeline,
        "runtime": request.app.state.runtime_metrics.snapshot(),
        "capabilities": {"url": True, "vision": request.app.state.vision is not None,
                         "automatic_screenshots": False, "whois": False, "tls_inspection": False,
                         "dom_inspection": False, "onnx": False, "kafka_live_telemetry": False,
                         "spark_live_telemetry": False, "page_blocking": False},
        "scope": "Recorded model/pipeline artifacts and measured current-process metrics are separate",
    }


@router.get('/install-info', dependencies=[Depends(authorized)])
async def install_info(request: Request):
    root = Path(__file__).resolve().parents[3]
    manifest = clean_report(root / 'extension/manifest.json') or {}
    config = clean_report(root / 'src/phishguard/web/static/assets/config.json') or {}
    return {'extension_path': str(root / 'extension'),
            'extension_available': (root / 'extension/manifest.json').is_file(),
            'extension_id': config.get('extension_id'),
            'version': manifest.get('version'),
            'backend_origin': str(request.base_url).rstrip('/'),
            'requires_manual_chrome_install': True}


@router.get('/extension-download', dependencies=[Depends(authorized)])
async def extension_download():
    from io import BytesIO
    import zipfile
    from fastapi.responses import Response
    root = Path(__file__).resolve().parents[3] / 'extension'
    names = ['manifest.json','background.js','dashboard-bridge.js','scan-core.js',
             'page-warning.js','popup.html','connect.html','popup.js','popup.css','icon128.png']
    if not all((root / name).is_file() for name in names):
        raise HTTPException(503, 'Use the complete local project to install the extension')
    content = BytesIO()
    with zipfile.ZipFile(content, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            file = root / name
            if file.is_symlink():
                raise HTTPException(503, 'Extension symlink refused')
            archive.writestr(name, file.read_bytes())
    return Response(content.getvalue(), media_type='application/zip',
                    headers={'Content-Disposition':'attachment; filename="PhishGuard-extension.zip"'})
