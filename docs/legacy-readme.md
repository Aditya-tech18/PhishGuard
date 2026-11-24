> **Release 2.5.0:** opt-in automatic domain checks for current/new tabs, phishing-only friendly page warnings, optional browser notifications, and OFF/stale-result cancellation. URL/CNN weights are unchanged. [Setup and limits](docs/automatic-extension.md).

# PhishGuard 2.0

Privacy-first phishing classification with a shared lexical feature contract, domain-isolated
five-family URL model comparison, Spark CSV-to-Parquet ETL, Kafka inference, an authenticated FastAPI service,
Streamlit interface and an OFF-by-default Chrome Manifest V3 extension.

**Read [BUILD_REPORT.md](BUILD_REPORT.md) for actual validation results and limitations.**
The complete bundle includes the selected numeric model and dataset-specific held-out results.
Production certification, internet-wide accuracy and browser-store approval are not claimed.


## Run the complete project

The complete release ZIP includes the selected numeric URL model and matching aggregate reports.
Extract into a new folder, then:

```bash
bash scripts/setup_mac.sh
source .venv/bin/activate
make doctor
make launch
```

The launcher checks the model/report pair, binds API and dashboard to loopback, creates a
private temporary session key and stops its own services when you press Ctrl+C. Raw datasets
and environments are not bundled. Event retention and image inference default OFF.

Use `bash scripts/setup_mac.sh --full` for Spark/vision/browser test dependencies. Java 17,
a Kafka broker and Chromium test runtime are separate prerequisites documented below.
An existing unmarked virtual environment is preserved; select PHISHGUARD_VENV for a new one.

![Actual local dashboard](docs/assets/dashboard-result.png)

## A–J map

| Section | Responsibility | Paths |
| --- | --- | --- |
| A | Configuration and runtime contracts | `config/`, `src/phishguard/common/` |
| B | Read-only dataset inspection and ingestion | `src/phishguard/ingestion/` |
| C | Spark cleaning, feature engineering, Parquet | `src/phishguard/processing/` |
| D | Deterministic URL features and schema | `src/phishguard/features/` |
| E | Training, evaluation, portable registry, optional CNN | `src/phishguard/ml/` |
| F | Kafka producer, consumer, DLQ, Spark streaming | `src/phishguard/streaming/` |
| G | Authentication, bounded requests, optional metadata | `src/phishguard/api/` |
| H | User interface and minimized analytics | `src/phishguard/dashboard/`, `analytics/` |
| I | Opt-in automatic Chrome extension | `extension/` |
| J | Safe merge, tests, CI, deployment and runbooks | `scripts/`, `tests/`, `deploy/`, `docs/` |

The earlier Desktop tree had empty Python placeholders. This repository retains those module
paths and adds integration, security and operational files. File and line counts are measured
in the build report; there is no line padding to meet a nominal 12,000-line target.

## Quick start on Mac

Use Python 3.11. Java 17 is needed only for Spark. From the extracted repository:

```bash
bash scripts/setup_mac.sh
source .venv/bin/activate
bash scripts/demo.sh
export PHISHGUARD_API_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export PHISHGUARD_MODEL=models/trained/demo-only.json
make api
```

The demo creates synthetic `.test` URLs and a **demo-only** model. Do not use it for protection.
In another terminal using the same environment and API key:

```bash
bash scripts/run_dashboard.sh
```

The dashboard listens at `http://127.0.0.1:8501`. The API listens at `http://127.0.0.1:8000`.
For real training, inspect the real dataset schema and label meaning first:

```bash
phishguard inspect path/to/data.csv --url-column url --label-column label
phishguard train-all path/to/curated-query-stripped.csv --output models/trained/run-001
```

Use `--delimiter ';'`, `--positive phishing`, `--negative legitimate` and explicit column names
when required. PhishGuard never guesses label polarity or substitutes a feature-only table
for raw URL data. [Dataset guide](docs/dataset.md).

## Merge into the existing Desktop folder safely

First review a preview (this does not write to the Desktop):

```bash
bash install_to_mac.sh --target "$HOME/Desktop/PhishGuard"
```

Nonempty conflicts stop the default apply. To inspect planned code replacements:

```bash
bash install_to_mac.sh --target "$HOME/Desktop/PhishGuard" --replace-code
```

After reviewing that preview, apply the same plan with `--apply`:

```bash
bash install_to_mac.sh --target "$HOME/Desktop/PhishGuard" --replace-code --apply
```

The script never copies or deletes `data/`, `models/`, `.env`, `.git`, `.venv`, `reports/` or
`logs/`. It backs up replaced code to a timestamped sibling directory and writes a merge
journal. It leaves obsolete files alone. Existing dependencies and v1 settings are not
silently migrated. Run setup and checks after merging. [Detailed merge/rollback guide](docs/setup.md).

## Chrome extension — automatic checks

1. Start the backend: `bash scripts/setup_mac.sh`, activate the printed environment, then `make launch`.
2. Open `chrome://extensions`, enable Developer mode, choose **Load unpacked**, select this release's `extension/` folder. When upgrading, remove the old unpacked extension or reload it from the new directory; do not keep two versions enabled.
3. Open the toolbar popup, expand **Connect your local server**, paste/save the local session API key. The managed launcher prints the private session-key file location.
4. Turn **Automatic URL checks** ON and approve Chrome's website-access prompt. Existing supported tabs are checked; new tabs/navigation are checked automatically. Active tabs are also rechecked approximately once per minute.
5. Suspicious URL-model results show **“Yeh website scam ho sakti hai”**, verification advice and a reasons button. Normal results produce no page popup. Optional browser notifications need their own permission and may depend on OS settings.
6. Turn OFF to cancel queued/in-flight checks and remove warnings. New browser sessions need a new saved session key.

Only origins/domains are submitted automatically; no paths, query tokens, fragments, page titles, browsing history, form contents or screenshots. Warning DOM is inserted only for a suspicious result, rather than reading page content. Website access is optional until ON. Screenshot/CNN checks remain separately enabled and require consent for every capture.

The local API must be running. An unavailable check shows `?` in the toolbar and is not treated as safe. Restricted Chrome pages cannot receive injected warnings. Navigation is not blocked. Large bursts of tabs can encounter backend rate limits; unavailable checks are shown honestly and active tabs retry. The domain model cannot inspect phishing content on an otherwise legitimate domain. Read [automatic-mode details](docs/automatic-extension.md).

## Tests and deployment

```bash
pip install -e '.[api,ml,streaming,dev]'
make lint
make test
pip install -e '.[spark]'
JAVA_HOME=/path/to/jdk17 SPARK_LOCAL_IP=127.0.0.1 pytest -m spark -v
```

Run Kafka integration only against an isolated broker, not a production cluster:

```bash
PHISHGUARD_TEST_KAFKA=true pytest -m kafka -v
```

[Architecture](docs/architecture.md) · [Setup](docs/setup.md) · [Pipeline](docs/pipeline.md) ·
[API](docs/api.md) · [Security](SECURITY.md) · [Limitations](docs/limitations.md) ·
[Deployment](docs/deployment.md) · [Live demo](docs/live_demo.md).


## Complete training and deployment flow

```bash
python scripts/curate_dataset.py source.csv --delimiter ';' --positive phishing \
  --negative legitimate --strip-query --drop-conflicts --output data/interim/curated.csv
phishguard train-all data/interim/curated.csv --output models/trained/run-001 --bootstrap 200
phishguard registry-register --root models/registry --model models/trained/run-001/url-model.json \
  --report models/trained/run-001/evaluation.json
phishguard registry-activate --root models/registry --version VERSION_FROM_TRAINING
export PHISHGUARD_REGISTRY=models/registry
make api
```

The tournament compares logistic regression, decision tree, random forest, gradient boosting
and Gaussian naive Bayes. Validation chooses the algorithm/threshold; the held-out test is
reported only for the winner. All five export to validated numeric JSON without pickle.

The dashboard includes URL checks, optional image submission, runtime overview, model results,
data-quality summaries and metadata deletion. Set PHISHGUARD_EVALUATION_REPORT,
PHISHGUARD_DATA_QUALITY_REPORT and PHISHGUARD_PIPELINE_REPORT to explicit minimized local reports.

For image metadata at scale:

```bash
phishguard images-etl --legitimate-root path/to/legitimate --phishing-root path/to/phishing \
  --output data/processed/image-run-001
```

This produces structural validation, dimensions, content checksums and duplicate groups,
without copying pixels or paths into output. CNN training is separate and supports lazy disk
loading and explicit site-isolated manifests.

[Training guide](docs/model-training.md) · [Model registry](docs/model-registry.md) ·
[Image pipeline](docs/image-pipeline.md) · [Testing](docs/testing.md).
