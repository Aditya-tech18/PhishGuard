"""Real browser and HTTP app test, with no navigation to submitted websites."""

import os
from pathlib import Path
import socket
import threading
import time
import pytest
from test_serverless import load_script
from phishguard.api.serverless import create_cloud_app

pytestmark = pytest.mark.browser


def test_web_scanner_consent_minimization_key_lifecycle_and_mobile_layout(tmp_path, model_path):
    if os.getenv("PHISHGUARD_TEST_BROWSER") != "true":
        pytest.skip("Explicit isolated-browser opt-in required")
    playwright = pytest.importorskip("playwright.sync_api")
    import json
    import uvicorn
    from phishguard.ml.model_registry import URLModel

    model = URLModel.load(model_path)
    evaluation = tmp_path / "evaluation.json"
    evaluation.write_text(
        json.dumps(
            {
                "model_version": model.version,
                "test": {
                    "rows": 20,
                    "precision": 0.8,
                    "recall": 0.7,
                    "f1": 0.75,
                    "false_positive_rate": 0.1,
                },
            }
        )
    )
    root = tmp_path / "cloud"
    load_script("prepare_vercel").prepare(Path(__file__).parents[1], model_path, evaluation, root)
    app = create_cloud_app(root, {"PHISHGUARD_API_KEY": "b" * 40})
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", access_log=False)
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)
        assert server.started
        with playwright.sync_playwright() as engine:
            with engine.chromium.launch(headless=True) as browser:
                page = browser.new_page(viewport={"width": 1280, "height": 1000})
                errors = []
                sent = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on(
                    "request",
                    lambda request: (
                        sent.append(request.post_data_json) if request.method == "POST" else None
                    ),
                )
                page.goto(f"http://127.0.0.1:{port}/")
                page.get_by_text("URL service ready", exact=True).wait_for()
                assert page.locator("#scan").is_disabled()
                page.locator("#access").evaluate("(node)=>node.open=true")
                page.locator("#api-key").fill("b" * 40)
                page.locator("#save-key").click()
                assert page.locator("#api-key").input_value() == ""
                page.locator("#url").fill("https://example.com/login?token=never-send#fragment")
                page.locator("#consent").check()
                page.locator("#scan").click()
                page.locator("#prediction").wait_for(state="visible")
                assert sent == [{"url": "https://example.com/login"}]
                assert not page.locator("#consent").is_checked()
                assert page.locator("#scan").is_disabled()
                page.locator("#consent").check()
                page.locator("#url").fill("https://example.com/next")
                assert not page.locator("#consent").is_checked()
                page.locator("#clear").click()
                assert page.locator("#url").input_value() == ""
                assert page.locator("#empty").is_visible()
                page.set_viewport_size({"width": 390, "height": 844})
                assert page.evaluate("document.documentElement.scrollWidth<=window.innerWidth")
                assert page.evaluate("localStorage.length===0 && sessionStorage.length===0")
                page.reload()
                assert page.locator("#key-state").inner_text() == "Not set"
                assert page.locator("#scan").is_disabled()
                assert errors == []
    finally:
        server.should_exit = True
        thread.join(15)
        assert not thread.is_alive()
