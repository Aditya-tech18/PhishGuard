"""Managed local API and dashboard stack with isolated secrets, readiness checks and owned cleanup.

This launcher prepares a foreground local development session. It never trains a model, touches
raw data, opens a target website, modifies a browser profile or binds a public interface.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import importlib.util
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
from phishguard.common.files import atomic_bytes, atomic_json, read_json, reject_symlink_chain
from phishguard.ml.model_registry import URLModel


@dataclass(frozen=True)
class ShowcaseConfig:
    model: Path
    evaluation: Path | None = None
    vision_model: Path | None = None
    quality: Path | None = None
    pipeline: Path | None = None
    runtime_root: Path = Path("reports/local/showcase")
    api_port: int = 8000
    dashboard_port: int = 8501
    startup_timeout: float = 40
    run_seconds: float = 0

    def __post_init__(self):
        if not all(
            type(port) is int and 1024 <= port <= 65535
            for port in [self.api_port, self.dashboard_port]
        ):
            raise ValueError("Showcase requires nonprivileged local ports")
        if self.api_port == self.dashboard_port:
            raise ValueError("API and dashboard ports must be different")
        if not 1 <= self.startup_timeout <= 120 or not 0 <= self.run_seconds <= 7200:
            raise ValueError("Invalid showcase timing bounds")


def check_port(port):
    with socket.socket() as connection:
        connection.bind(("127.0.0.1", port))


def preflight(config, check_ports=True):
    required = ["uvicorn", "streamlit", "httpx"]
    missing = [name for name in required if importlib.util.find_spec(name) is None]
    if missing:
        raise ValueError("Install API/dashboard extras before showcasing: " + ", ".join(missing))
    model = URLModel.load(config.model)
    if config.evaluation:
        report = read_json(config.evaluation)
        if report.get("model_version") != model.version:
            raise ValueError("Evaluation report does not match the model")
    for path in [config.quality, config.pipeline]:
        if path:
            read_json(path)
    vision_version = None
    if config.vision_model:
        from phishguard.ml.vision import VisionModel

        vision_version = VisionModel(config.vision_model).version
    if check_ports:
        check_port(config.api_port)
        check_port(config.dashboard_port)
    # The smoke input is a reserved public example and triggers no outbound page fetch.
    prediction = model.predict("https://example.com/")
    if not 0 <= prediction["probability"] <= 1:
        raise ValueError("Model failed local inference preflight")
    return {
        "model_version": model.version,
        "algorithm": model.algorithm,
        "query_policy": model.query_policy,
        "required_imports": required,
        "local_inference": "passed",
        "bind_address": "127.0.0.1",
        "storage_enabled": False,
        "vision_enabled": config.vision_model is not None,
        "vision_model_version": vision_version,
    }


def wait_http(url, process, deadline, expected_version=None):
    import httpx

    with httpx.Client(timeout=2, trust_env=False, follow_redirects=False) as client:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("Showcase child exited during startup; inspect its local log")
            try:
                response = client.get(url)
                if response.status_code == 200:
                    if (
                        expected_version
                        and response.json().get("model_version") != expected_version
                    ):
                        raise RuntimeError("Unexpected model answered on the showcase port")
                    return
            except (httpx.HTTPError, ValueError):
                pass
            time.sleep(0.1)
    raise TimeoutError("Showcase service did not become ready before the deadline")


def stop_owned(process):
    if process.poll() is not None:
        return
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
    else:
        process.terminate()
    try:
        process.wait(10)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            process.kill()
        process.wait(5)


def run(config, stop=None, announce=True):
    import httpx

    summary = preflight(config)
    session_name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + secrets.token_hex(4)
    runtime = reject_symlink_chain(config.runtime_root) / session_name
    runtime.mkdir(parents=True, exist_ok=False, mode=0o700)
    key = secrets.token_urlsafe(32)
    key_path = atomic_bytes(runtime / "session-api-key.txt", (key + "\n").encode())
    stop = stop or threading.Event()
    env = dict(os.environ)
    for name in ["PHISHGUARD_REGISTRY", "PHISHGUARD_VISION_MODEL", "PHISHGUARD_HMAC_KEY"]:
        env.pop(name, None)
    env.update(
        PHISHGUARD_API_KEY=key,
        PHISHGUARD_MODEL=str(config.model.resolve()),
        PHISHGUARD_STORE_EVENTS="false",
        PHISHGUARD_ALLOWED_HOSTS="127.0.0.1,localhost,::1",
        PHISHGUARD_API_URL=f"http://127.0.0.1:{config.api_port}",
        PHISHGUARD_DB=str(runtime / "unused-events.db"),
    )
    if config.vision_model:
        env["PHISHGUARD_VISION_MODEL"] = str(config.vision_model.resolve())
        env["PHISHGUARD_MAX_REQUEST_BYTES"] = "8000000"
    for name, value in [
        ("PHISHGUARD_EVALUATION_REPORT", config.evaluation),
        ("PHISHGUARD_DATA_QUALITY_REPORT", config.quality),
        ("PHISHGUARD_PIPELINE_REPORT", config.pipeline),
    ]:
        if value:
            env[name] = str(value.resolve())
        else:
            env.pop(name, None)
    app = Path(__file__).parent / "dashboard/app.py"
    commands = [
        [
            sys.executable,
            "-m",
            "uvicorn",
            "phishguard.api.main:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(config.api_port),
            "--no-access-log",
        ],
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(app),
            "--server.address",
            "127.0.0.1",
            "--server.port",
            str(config.dashboard_port),
            "--server.headless",
            "true",
            "--browser.gatherUsageStats",
            "false",
            "--client.toolbarMode",
            "viewer",
            "--theme.base",
            "dark",
            "--theme.primaryColor",
            "#2dd4bf",
            "--theme.backgroundColor",
            "#08111f",
            "--theme.secondaryBackgroundColor",
            "#122139",
            "--theme.textColor",
            "#edf4fb",
        ],
    ]
    processes, logs = [], []
    state = {
        **summary,
        "status": "starting",
        "session": str(runtime),
        "api_url": env["PHISHGUARD_API_URL"],
        "dashboard_url": f"http://127.0.0.1:{config.dashboard_port}",
    }
    state_path = runtime / "session.json"
    started = time.monotonic()
    try:
        atomic_json(state_path, state)
        for name, command in zip(["api", "dashboard"], commands):
            stream = (runtime / (name + ".log")).open("w")
            logs.append(stream)
            processes.append(
                subprocess.Popen(
                    command,
                    cwd=runtime,
                    env=env,
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            )
        deadline = time.monotonic() + config.startup_timeout
        wait_http(state["api_url"] + "/health", processes[0], deadline, summary["model_version"])
        wait_http(state["dashboard_url"] + "/_stcore/health", processes[1], deadline)
        with httpx.Client(timeout=5, trust_env=False) as client:
            result = client.post(
                state["api_url"] + "/api/v1/predict/url",
                headers={"X-API-Key": key},
                json={"url": "https://example.com/"},
            )
            if (
                result.status_code != 200
                or result.json()["model_version"] != summary["model_version"]
            ):
                raise RuntimeError("Authenticated showcase inference failed")
        if config.vision_model:
            import base64
            import io
            from PIL import Image

            buffer = io.BytesIO()
            Image.new("RGB", (16, 16), "white").save(buffer, format="PNG")
            with httpx.Client(timeout=10, trust_env=False) as client:
                image_result = client.post(
                    state["api_url"] + "/api/v1/predict/image",
                    headers={"X-API-Key": key},
                    json={
                        "consent": True,
                        "image_base64": base64.b64encode(buffer.getvalue()).decode(),
                    },
                )
                if (
                    image_result.status_code != 200
                    or image_result.json()["model_version"] != summary["vision_model_version"]
                ):
                    raise RuntimeError("Authenticated image inference readiness failed")
            state["image_smoke"] = "passed"
        state.update(
            status="ready",
            owned_pids=[process.pid for process in processes],
            startup_seconds=time.monotonic() - started,
            authenticated_smoke="passed",
        )
        atomic_json(state_path, state, replace=True)
        if announce:
            print("PhishGuard local stack ready: " + state["dashboard_url"], flush=True)
            print("Extension session key is in a private local file: " + str(key_path), flush=True)
            print("Keep the key file private. Ctrl+C stops this session only.", flush=True)
        ready_at = time.monotonic()
        while not stop.wait(0.2):
            if any(process.poll() is not None for process in processes):
                raise RuntimeError("A showcase service stopped unexpectedly")
            if config.run_seconds and time.monotonic() - ready_at >= config.run_seconds:
                break
        return {**state, "status": "stopped"}
    finally:
        for process in reversed(processes):
            stop_owned(process)
        for stream in logs:
            stream.close()
        state["status"] = "stopped"
        state["elapsed_seconds"] = time.monotonic() - started
        # Delete credentials before best-effort diagnostic writes, even on a full disk.
        key_path.unlink(missing_ok=True)
        try:
            atomic_json(state_path, state, replace=True)
        except OSError:
            pass
