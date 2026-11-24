# Reproducible local demonstration

## 1. Verify before showing results

```bash
source .venv/bin/activate
make lint
make test
bash scripts/demo.sh
```

The demo creates 240 synthetic `.test` URLs, trains a domain-separated logistic model and
prints a prediction. Explain that its model metrics test pipeline mechanics, not internet
phishing detection. Never present the generated score as a production benchmark.

## 2. Start the API

```bash
export PHISHGUARD_API_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export PHISHGUARD_MODEL=models/trained/demo-only.json
make api
```

Keep the key private. Use the dashboard from another terminal with the same environment.
Run `bash scripts/run_dashboard.sh`, submit `https://example.com/` with consent and view the
probability, model version and disclaimer. Open Retained metadata: storage should be disabled.

## 3. Demonstrate Chrome controls

Load the unpacked extension. Observe OFF. Enter session key, enable scanning, navigate to a
non-sensitive HTTP(S) page, then consent and press Scan. Show that consent resets after the
request. Turn OFF and verify Scan remains disabled. Close/restart the browser session and
verify the session API key must be entered again. Uninstall with Chrome Remove.

These manual steps complement the delivered isolated Chromium toolbar test. That real runtime
test also verifies screenshot opt-in/consent and query minimization. It does not prove Chrome
Web Store compliance or every browser version.

## 4. Show the batch layer

```bash
phishguard batch data/samples/demo.csv --output data/processed/demo-run-001
```

Inspect aggregate label/reject counts and Parquet metadata. Avoid displaying raw source rows
on a shared screen. Repeat with a new output name; the original output must not be overwritten.

## 5. Show streaming, only with a local broker

```bash
phishguard topics
phishguard publish 'https://example.com/'
phishguard consume --model models/trained/demo-only.json
```

Observe acknowledged prediction output with the input event UUID. Stop with Ctrl+C. Explain
that crashes can replay events and that UUID deduplication is required. Invalid events should
produce minimized DLQ metadata, without copying the invalid raw payload.

## Exit

Stop processes cleanly. Disable/remove the extension if no longer needed. No script removes
existing data. If retaining synthetic artifacts is unnecessary, delete only the specific new
demo paths after inspecting them; never delete `data/raw` to clean up a demo.
