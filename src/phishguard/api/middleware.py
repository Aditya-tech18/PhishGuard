"""Bounded HTTP input and minimized per-process observability.

These controls supplement a real HTTP server/proxy: they do not replace TLS, socket-level
connection limits or a distributed quota. Metrics retain numeric aggregates only.
"""

import asyncio
from collections import Counter, deque
import threading
import time
from urllib.parse import parse_qs
import uuid
import numpy as np
from starlette.responses import JSONResponse


class RuntimeMetrics:
    def __init__(self, sample_size=1024):
        self.started = time.monotonic()
        self.counts = Counter()
        self.durations = deque(maxlen=sample_size)
        self.lock = threading.Lock()

    def observe(self, status, duration):
        category = f"{int(status) // 100}xx"
        with self.lock:
            self.counts[category] += 1
            self.durations.append(max(0, float(duration)))

    def snapshot(self):
        with self.lock:
            values = list(self.durations)
            counts = dict(self.counts)
        return {
            "uptime_seconds": max(0, time.monotonic() - self.started),
            "requests": sum(counts.values()),
            "status_classes": counts,
            "sample_size": len(values),
            "latency_p50_ms": float(np.quantile(values, 0.5) * 1000) if values else None,
            "latency_p95_ms": float(np.quantile(values, 0.95) * 1000) if values else None,
            "scope": "single_process_numeric_only",
        }


class InputGuard:
    def __init__(self, app, maximum, receive_timeout=10, max_chunks=1024):
        self.app = app
        self.maximum = maximum
        self.receive_timeout = receive_timeout
        self.max_chunks = max_chunks

    @staticmethod
    def allowed_query(scope):
        raw = scope.get("query_string", b"")
        if not raw:
            return True
        if scope.get("path") != "/api/v1/predictions" or len(raw) > 32:
            return False
        try:
            values = parse_qs(raw.decode("ascii"), strict_parsing=True, max_num_fields=1)
            return (
                set(values) == {"limit"}
                and len(values["limit"]) == 1
                and values["limit"][0].isdigit()
            )
        except (ValueError, UnicodeError):
            return False

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def reject(message, status):
            response = JSONResponse(
                {"detail": message},
                status,
                headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
            )
            return await response(scope, receive, send)

        if not self.allowed_query(scope):
            return await reject("Unsupported query parameters", 400)
        incoming = scope.get("headers", [])
        lengths = [value for key, value in incoming if key.lower() == b"content-length"]
        if len(lengths) > 1:
            return await reject("Duplicate content length is forbidden", 400)
        if lengths and any(key.lower() == b"transfer-encoding" for key, _ in incoming):
            return await reject("Ambiguous HTTP framing is forbidden", 400)
        headers = {key.lower(): value for key, value in incoming}
        length = headers.get(b"content-length")
        if length is not None:
            try:
                if not length or not length.isdigit():
                    raise ValueError("Content length must contain ASCII digits")
                declared = int(length)
            except ValueError:
                return await reject("Invalid content length", 400)
            if declared < 0:
                return await reject("Invalid content length", 400)
            if declared > self.maximum:
                return await reject("Request too large", 413)
        size, messages = 0, []
        deadline = time.monotonic() + self.receive_timeout
        for _ in range(self.max_chunks):
            try:
                remaining = max(0.001, deadline - time.monotonic())
                message = await asyncio.wait_for(receive(), timeout=remaining)
            except asyncio.TimeoutError:
                return await reject("Request body timed out", 408)
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                return await reject("Invalid HTTP message", 400)
            size += len(message.get("body", b""))
            if size > self.maximum:
                return await reject("Request too large", 413)
            messages.append(message)
            if not message.get("more_body", False):
                break
            if time.monotonic() >= deadline:
                return await reject("Request body timed out", 408)
        else:
            return await reject("Too many request chunks", 413)
        if length is not None and size != int(length):
            return await reject("Content length does not match body", 400)
        index = 0

        async def replay():
            nonlocal index
            if index < len(messages):
                message = messages[index]
                index += 1
                return message
            return await receive()

        await self.app(scope, replay, send)


def request_id():
    # Never accept a caller-provided tracking identifier into application logs.
    return uuid.uuid4().hex


class ResponseControls:
    """Bounded process quotas and headers without consuming/cancelling request streams."""

    def __init__(self, app, settings, metrics):
        self.app, self.settings, self.metrics = app, settings, metrics
        self.window, self.browser_window = deque(), deque()

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        started = time.monotonic()
        path = scope.get('path', '')
        for window in (self.window, self.browser_window):
            while window and window[0] <= started - 60:
                window.popleft()
        browser = path.startswith('/api/v1/browser/')
        protected = path.startswith('/api/') and not browser
        window = self.browser_window if browser else self.window
        limit = 240 if browser else self.settings.rate_limit
        limited = (browser or protected) and len(window) >= limit
        if (browser or protected) and not limited:
            window.append(started)

        async def secured_send(message):
            if message['type'] == 'http.response.start':
                from starlette.datastructures import MutableHeaders
                message = {**message, 'headers': list(message.get('headers', []))}
                headers = MutableHeaders(scope=message)
                headers['X-Request-ID'] = request_id()
                headers['Cache-Control'] = 'no-store'
                headers['X-Content-Type-Options'] = 'nosniff'
                headers['Referrer-Policy'] = 'no-referrer'
                headers['Content-Security-Policy'] = (
                    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                    "font-src 'self'; img-src 'self' data: blob:; "
                    "connect-src 'self' ws://127.0.0.1:* ws://localhost:*; "
                    "object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
                    if path in {'/', '/live-detection', '/model-and-system'} or path.startswith('/assets/')
                    else "default-src 'none'; frame-ancestors 'none'"
                )
                self.metrics.observe(message['status'], time.monotonic() - started)
            await send(message)

        if limited:
            response = JSONResponse({'detail':'Rate limit exceeded'}, 429,
                                    headers={'Retry-After':'60'})
            return await response(scope, receive, secured_send)
        return await self.app(scope, receive, secured_send)
