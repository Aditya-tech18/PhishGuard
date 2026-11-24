# Running the complete project

## Complete bundle and source-only bundle

The complete release contains code, the selected numeric URL model, all five candidate
artifacts and aggregate evaluation/data-quality/pipeline reports. It contains no raw corpus,
private browser profile, runtime session key, database, environment or presentation.

The source-only release excludes learned artifacts and runtime reports. It is suitable for
reviewing or pushing code after your own repository review. Model/data redistribution rights
are a separate decision from the source code's MIT license.

## Installation

Extract into a new directory. Do not unzip over the Desktop data tree. With Python 3.11:

```bash
bash scripts/setup_mac.sh
source .venv/bin/activate
make doctor
make launch
```

Setup creates a managed environment. If .venv already exists without the project marker,
setup refuses to change it and suggests a new PHISHGUARD_VENV path. This preserves earlier
work. Activate whichever path you selected before running CLI commands.

The standard profile installs URL ML, API, dashboard, Kafka client and development tools.
`--full` additionally installs Spark, vision, image and browser-test Python dependencies.
Java 17 and a Kafka broker are external runtimes. Browser tests need an explicitly installed
Chromium runtime. Installing Python packages does not silently start brokers or browser apps.

## Managed local stack

`make launch` selects the bundled model and reports. It validates identity, checks that local
ports are available, generates a private session key and starts the API/dashboard in owned
process groups. It waits for HTTP readiness and performs authenticated model inference before
printing the dashboard URL. Startup failures stop children and remove the temporary key.

The API binds 127.0.0.1:8000 and dashboard 127.0.0.1:8501. If another service owns those ports,
choose explicit alternatives rather than stopping someone else's process:

```bash
phishguard launch --model models/trained/url-model.json --evaluation reports/evaluation.json \
  --api-port 18000 --dashboard-port 18501
```

The browser extension intentionally allows only 127.0.0.1:8000. A different API port requires
reviewing its fixed endpoint and manifest permission. The dashboard receives its internal API
key through the child process environment. It does not display that key in the web interface.

Ctrl+C stops only children created by this launch. The private key file is removed. Minimized
session state and service logs remain under ignored reports/local storage for diagnosis.
The source packager excludes that entire runtime tree.

## Direct API mode

For deployment configuration rather than the managed local session, export a random API key,
model/registry path and optional retention settings, then use `make api`. Doctor's --api-mode
validates those environment settings without printing secrets. See docs/configuration.md.
The local launcher deliberately forces storage and optional image inference OFF; use explicit
direct API configuration to enable those paths after reviewing their privacy implications.

## Optional features

- Spark URL/image ETL: use fresh output directories and Java 17.
- Kafka streaming: create the documented topics on an isolated broker and configure TLS/ACLs
  before remote use. Browser scans do not silently publish raw URLs to Kafka.
- Screenshot inference: train/load a trusted local image model, enable direct API configuration,
  and use separate browser opt-in plus fresh capture consent.
- Code installation into an existing tree: preview install_to_mac.sh before --apply. It skips
  all protected data/model/environment/report paths and backs up changed code.

## Local benchmark

The supplied benchmark addresses loopback only and never visits its sample URLs. It respects
server quotas and reports 429 responses instead of bypassing them. Use a dedicated local
instance with an explicitly chosen quota; do not run against someone else's service:

```bash
python scripts/benchmark_api.py --port 8000 --requests 200 --concurrency 8 \
  --output reports/local/benchmark-new.json
```

The build's 500-request result is a short local experiment. It is not a public availability
promise, penetration test or proof that thousands of concurrent users can use one worker.
