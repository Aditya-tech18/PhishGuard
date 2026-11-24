import asyncio
import pytest
from fastapi.testclient import TestClient
from phishguard.api.middleware import InputGuard, RuntimeMetrics
from phishguard.api.main import create_app
from phishguard.common.config import Settings


def direct_guard(messages, *, headers=None, timeout=0.05, chunks=1024, delayed=False):
    sent, accepted = [], []
    iterator = iter(messages)

    async def receive():
        if delayed:
            await asyncio.sleep(0.1)
        return next(iterator)

    async def downstream(scope, receive, send):
        accepted.append(await receive())
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def send(message):
        sent.append(message)

    guard = InputGuard(downstream, maximum=1024, receive_timeout=timeout, max_chunks=chunks)
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": headers or [],
        "query_string": b"",
    }
    asyncio.run(guard(scope, receive, send))
    return sent[0]["status"] if sent else None, accepted


@pytest.mark.parametrize(
    "length,status",
    [(b"", 400), (b"-1", 400), (b"garbage", 400), (b"2048", 413), (b"0", 400), (b"3", 204)],
)
def test_content_length_is_validated(length, status):
    actual, _ = direct_guard(
        [{"type": "http.request", "body": b"abc"}], headers=[(b"content-length", length)]
    )
    assert actual == status


def test_slow_body_and_empty_chunk_limits():
    status, accepted = direct_guard([{"type": "http.request", "body": b""}], delayed=True)
    assert status == 408 and accepted == []
    status, accepted = direct_guard(
        [{"type": "http.request", "body": b"", "more_body": True}] * 4, chunks=3
    )
    assert status == 413 and accepted == []


def test_disconnect_and_unexpected_messages():
    assert direct_guard([{"type": "http.disconnect"}]) == (None, [])
    assert direct_guard([{"type": "invalid"}])[0] == 400


def test_host_and_pagination_contract(model_path, tmp_path):
    settings = Settings("k" * 32, model_path, tmp_path / "data.db")
    with TestClient(create_app(settings)) as client:
        headers = {"X-API-Key": "k" * 32}
        assert client.get("/health", headers={"Host": "attacker.example"}).status_code == 400
        assert client.get("/api/v1/predictions?limit=10", headers=headers).status_code == 200
        assert client.get("/api/v1/predictions?limit=1001", headers=headers).status_code == 422
        assert client.get("/api/v1/predictions?limit=1&limit=2", headers=headers).status_code == 400
        response = client.get("/api/v1/metrics", headers=headers)
        assert response.status_code == 200
        assert response.json()["runtime"]["scope"] == "single_process_numeric_only"
        assert len(response.headers["X-Request-ID"]) == 32


def test_metrics_are_bounded_and_minimized():
    metrics = RuntimeMetrics(sample_size=3)
    for _ in range(10):
        metrics.observe(200, 0.1)
    result = metrics.snapshot()
    assert result["requests"] == 10
    assert result["sample_size"] == 3
    assert result["status_classes"] == {"2xx": 10}
    assert result["latency_p95_ms"] == pytest.approx(100)


@pytest.mark.parametrize(
    "headers",
    [
        [(b"content-length", b"3"), (b"content-length", b"3")],
        [(b"content-length", b"3"), (b"transfer-encoding", b"chunked")],
        [(b"content-length", b"+3")],
        [(b"content-length", b" 3")],
    ],
)
def test_ambiguous_http_framing_rejected(headers):
    status, accepted = direct_guard([{"type": "http.request", "body": b"abc"}], headers=headers)
    assert status == 400 and not accepted


def test_full_controls_accept_early_browser_disconnect():
    """A browser aborting before body completion must not become a middleware exception."""
    import asyncio
    from types import SimpleNamespace
    from phishguard.api.middleware import InputGuard, ResponseControls, RuntimeMetrics
    reached = []
    async def endpoint(scope, receive, send):
        reached.append(True)
    async def disconnected():
        return {'type':'http.disconnect'}
    async def send(message):
        raise AssertionError('Disconnected clients need no HTTP response')
    app = ResponseControls(InputGuard(endpoint, maximum=1024),
                           SimpleNamespace(rate_limit=60), RuntimeMetrics())
    asyncio.run(app({'type':'http','path':'/api/v1/predict/url','headers':[]}, disconnected, send))
    assert not reached
