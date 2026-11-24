# API contract

Start a single local worker using `make api`. Configure a trusted URL model and a random
`PHISHGUARD_API_KEY` of at least 32 characters. Startup fails if model validation fails.
All prediction/data routes require `X-API-Key`. `/health` is unauthenticated and exposes only
status and model/application versions. Interactive OpenAPI pages are disabled.

| Method | Path | Input / output |
| --- | --- | --- |
| GET | `/health` | Health and loaded model version |
| POST | `/api/v1/predict/url` | `{ "url": "https://example.com/" }` → prediction |
| POST | `/api/v1/predict/batch` | `{ "items": [{ "url": "..." }] }`, 1–32 entries |
| POST | `/api/v1/predict/image` | Explicit true consent and base64 PNG/JPEG |
| GET | `/api/v1/predictions` | Up to 100 retained metadata events |
| DELETE | `/api/v1/predictions` | Logical deletion of retained metadata |
| GET | `/api/v1/metrics` | Retained counts, not measured model accuracy |

The service rejects URL/key query submission; use POST JSON for URL data. The metadata list
accepts only `?limit=1..1000`, default 100. Unknown/duplicate query parameters are rejected.

## Prediction response

```json
{
  "event_id": "00000000-0000-0000-0000-000000000000",
  "timestamp": "2026-01-01T00:00:00Z",
  "probability": 0.75,
  "verdict": "phishing",
  "model_version": "example-version",
  "reasons": ["url_length", "suspicious_tokens"],
  "disclaimer": "Model estimate only; low risk does not guarantee safety."
}
```

This is an illustrative schema, not a measured prediction. A `low_risk` result is not a safety
certificate. Reasons are positive contributions in the linear model, not causal explanations.
Probabilities are not independently calibrated for every deployment population.

## Errors and limits

- 401: missing/incorrect API key.
- 413: request exceeds configured byte limit, including chunked bodies.
- 422: malformed input, unsupported/private literal URL, extra fields or batch size violation.
- 429: process-wide rate budget exhausted; `Retry-After: 60`.
- 503: optional image model is disabled.
- 500: unexpected internal processing error; response does not expose exception internals.

Default request size is 65,536 bytes. URL length is bounded at 2,048 characters. Rate budget is
60 requests per minute across a process; a batch can contain up to 32 predictions. This is a
request budget, not a model-inference-count budget. Health bypasses the rate budget. No IP list
is retained and reverse-proxy forwarding headers are not trusted for identity.

## Screenshot API

The complete bundle launcher loads the included experimental CNN. For manual API startup, set `PHISHGUARD_VISION_MODEL` to the trusted local weights, then restart. To accept larger base64
requests, raise `PHISHGUARD_MAX_REQUEST_BYTES` up to 8,000,000. The decoded image remains bounded
at 5,000,000 bytes and 16 million pixels. JSON must include `consent: true` and `image_base64`.
The endpoint never stores or forwards image bytes and returns the separate experimental score.
The extension implements a separate opt-in screenshot button with fresh per-capture consent.
It checks `/health` for `vision_enabled` before capture. With a vision model configured through
the environment, the default body cap becomes 8,000,000 bytes; an explicit environment cap overrides it.

## Privacy and service logs

Use `--no-access-log`. Do not enable debug traceback middleware, body logging or request capture
in a proxy. Framework/host diagnostics may contain context in unexpected failures, so protect
service logs. Responses use `Cache-Control: no-store`, a restrictive CSP, no-referrer and
nosniff headers. These do not prevent a caller from copying results or a compromised host from
reading memory. Request content remains in transient process memory until released.

FastAPI's API key header dependency is based on the official implementation:
[FastAPI APIKeyHeader](https://github.com/fastapi/fastapi/blob/master/fastapi/security/api_key.py).


HTTP reception has a configurable body deadline (default 10 seconds), a maximum chunk count
and declared-length consistency checks. Host headers must match configured trusted names.
`X-Request-ID` is generated server-side. `/api/v1/metrics` includes bounded per-process
request/status/latency aggregates; it never stores paths, URLs, client IPs or payloads.

### Coverage review (2.2.0)

URL predictions include `review_required` and nullable `coverage_warning`. A true review flag marks an inconclusive URL shape because the corpus underrepresents legitimate login/article paths. The raw numeric score and `verdict` remain available for audit; neither is a verified-threat label. Clients should surface the notice and request independent verification. No live destination is fetched.

## 2.2 input policy and review notices

The bundled URL model declares `input_policy: origin-only`. Full input is validated first; path and query are excluded from the feature vector. `review_required` and `coverage_warning` accompany non-root/login-like inputs. These are conservative notices, not score overrides. A raw `phishing` verdict is a model pattern signal, not verified maliciousness. Cloud `/api/v1/model-card` exposes the actual input policy and measured scope.
