# Local deployment and release process

## Single host

Run one Uvicorn worker and bind loopback. Keep model read-only; only enable database writes
when choosing retention. Generate secrets outside source control. Restart the service to
load a new model. Do not overwrite artifacts while workers are reading them; promote a new
versioned path and restart. Keep the previous model/version and evaluation report for rollback.

Before promotion, verify JSON schema, provenance digest, export parity, domain-separated test
metrics, false-positive examples and threshold selection. A successful HTTP health check only
means startup and model loading worked, not that model quality is acceptable.

## Container

```bash
export PHISHGUARD_MODEL_HOST="$(pwd)/models/trained/url-model.json"
# PHISHGUARD_API_KEY must already be exported.
docker compose -f deploy/compose.yaml up --build api
```

The API runs as UID 10001 with a read-only root filesystem, no Linux capabilities and a
read-only model mount. Loopback publication avoids public exposure. The default has no DB
mount because event storage is OFF. If enabling storage, create a writable directory with
UID permissions and explicitly mount it. No secrets are baked into the image.

The optional streaming profile runs a single-node Kafka demo:

```bash
docker compose -f deploy/compose.yaml --profile streaming up -d kafka
```

The broker advertises localhost for host clients. Clients inside other containers need a
separate internal advertised listener. This Compose file does not pretend that one advertised
address works for every network topology. Its retained volume must be managed separately;
removing a container is not raw-event deletion. Do not run `down -v` unless data deletion is
intended and backed up.

## CI/CD

`ci.yml` checks lint, unit/API/model tests, a Java 17 Spark job, dependency audit, Bandit and
container build. The workflow does not exercise Kafka/vision by default because they need
optional runtime setup. `release.yml` builds wheel/sdist and uploads a private workflow
artifact after explicit workflow dispatch. It does not publish to PyPI, deploy or push images.

This is a release packaging pipeline, not an automatic cloud rollout. Add environment-specific
review gates and credentials only after choosing a hosting target. Pin Actions and images by
reviewed commit/digest for a hardened supply chain. Run platform/JVM scanners in addition to
Python auditing. A vulnerability scanner's outage should remain visible rather than being
silently ignored by CI.

## Operations

Health: poll `/health` for availability and expected model version. Do not send credentials
in query strings. Metrics endpoint shows retained prediction distribution only. Monitor broker
lag, DLQ growth, Spark query progress and output/checkpoint disk growth with platform tools.
No alerting service is configured automatically.

Retention: API runs hourly purge while active; it also purges on inserts/read. Kafka topic
retention defaults to one hour for a demo. Parquet, datasets, local journals and backups have
no automatic deletion. Model training artifacts and reports may expose provenance, so keep
storage permissions appropriate.

Incident response: stop ingestion, disable the extension, revoke/rotate API and broker secrets,
preserve minimized operational evidence, evaluate dataset/model compromise, then promote a
reviewed model and restart. Do not attach victim screenshots or raw credential-bearing URLs
to public issues.


## Optional image runtime and model permissions

The default image installs the API and portable URL inference only. Build with
`--build-arg PHISHGUARD_EXTRAS=api,vision` to include optional local CNN inference dependencies.
That larger optional image was not separately built; the default API image was built/run.
Mount a trusted local vision artifact read-only and set PHISHGUARD_VISION_MODEL to enable it.

A private (0600) artifact owned by the host user may not be readable by container UID 10001.
Create a deliberate deployment copy with read permissions for the container account or run with
an appropriate non-root UID mapping. Do not make the entire model registry world-writable.
The local container test used a separate read-only deployment copy, leaving training originals intact.

Docker CLI alone may not include the Compose plugin. Use Docker Desktop or install that plugin
before following Compose commands. The default image was exercised locally with `docker run`;
no remote GitHub Actions or public deployment is claimed.

## Optional CPU vision container (2.2.0)

`deploy/Dockerfile.vision` installs CPU Torch explicitly. Use Compose profile `vision`, with absolute `PHISHGUARD_VISION_MODEL_HOST` and `PHISHGUARD_VISION_REPORT_HOST` paths. The image model and sidecar report must match. API ports are configurable. The 2.2.0 API and CPU vision images were built and exercised with the selected origin-only URL model and spatial-v2 CNN. Health/authenticated URL/image requests passed; missing keys and untrusted hosts were rejected. Both ran as UID 10001 with read-only root filesystems and all capabilities dropped. The Compose Kafka service passed a real produce/consume probe. Use enough isolated VM disk headroom (the original small test disk filled during rebuild; a larger task-only disk resolved it). See docs/validation/container-2.2.json.

## 2.2 verification update

The former 2.1 vision-container runtime limitation is historical. The final 2.2 container results are recorded in BUILD_REPORT.md and docs/validation/container-2.2.json. Vercel uses the dedicated URL-only exported folder; see docs/vercel.md. No remote Vercel deployment was requested after the user chose deploy-ready ZIP delivery.
