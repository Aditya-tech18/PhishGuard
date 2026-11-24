# Versioned local model registry

## Why activation is separate from training

An experiment finishing successfully should not silently replace a model serving requests.
PhishGuard's local registry stores immutable version directories and a small atomic active
pointer. It validates model/report identity and hashes before activation. An API process
resolves that pointer at startup; it does not reload weights halfway through an in-flight scan.

The registry is local artifact management, not a multi-tenant model platform or signed remote
model marketplace. Keep its directory private and writable only by the deployment owner.

## Register a completed experiment

```bash
phishguard registry-register --root models/registry \
  --model models/trained/run-001/url-model.json \
  --report models/trained/run-001/evaluation.json
phishguard registry-list --root models/registry
```

Model and evaluation `model_version` must match. Registry version IDs are restricted to 16
lowercase hexadecimal characters. Registered model and report hashes are saved in a manifest.
No pickle or joblib object is accepted. A duplicate registration with the identical model is
idempotent; a version collision with different bytes fails.

Partial directories from an interrupted registration are left for review. Without a complete,
valid manifest they cannot be activated. Inspect a failed version before manually removing
anything; registry code does not guess that partial user work is disposable.

## Apply explicit acceptance gates

```bash
phishguard registry-activate --root models/registry --version VERSION_FROM_TRAINING \
  --min-precision 0.95 --min-recall 0.90 --max-fpr 0.03 --min-test-rows 1000
```

Defaults are precision at least 0.90, recall at least 0.80, false-positive rate at most 0.05
and at least 100 held-out rows. These are development defaults, not a universal security policy.
Choose gates for the deployment's false-positive and false-negative costs. Missing, null or
invalid metrics fail closed. The activation command does not optimize gates on the test set.

Activation takes an exclusive local lock. It appends an activation-prepared audit record, then
atomically publishes `active.json`. The pointer is authoritative if a crash happens between
those steps. The history is not claimed to be a transactional database or tamper-proof ledger.
Stale locks require explicit operator review; they are not deleted on an arbitrary age timeout.

## Start the API from the registry

```bash
export PHISHGUARD_REGISTRY=models/registry
export PHISHGUARD_API_KEY='your-random-private-key'
make api
```

When this variable is set, startup resolves the registry's active model rather than the
standalone PHISHGUARD_MODEL path. Model bytes, report bytes, manifest identity and pointer
hash are verified before the API accepts requests. Missing/corrupt activation stops startup.

A running worker keeps its already loaded artifact. After activating another version, restart
the service deliberately and confirm `/health` reports the intended model version. Multiple
workers should roll in a controlled order; this repository does not claim a distributed
zero-downtime deployment coordinator.

## Roll back model activation

List versions, identify the previous known-good version, inspect its held-out report and
activate that version using the appropriate explicit quality gates. Then restart the service.
Old version directories are not overwritten by a new registration. The active pointer records
the preceding version to help review, but rollback is an explicit choice rather than a blind
"latest previous" command that might select a rejected experiment.

Code rollback and model rollback are different operations. The safe code merge protects the
entire `models/` tree. `scripts/rollback_merge.py` restores code files only; it does not change
registry contents or remove trained artifacts.

## Permissions and trust

Registry JSON files are created privately. A non-root Docker user needs read access to whichever
artifact you explicitly mount; create a separate reviewed read-only deployment copy rather
than making the entire registry world-writable. Numeric model weights do not contain raw URL
rows, but learned patterns and provenance still deserve an appropriate distribution decision.

Hashes detect unexpected changes relative to trusted metadata. A malicious owner able to edit
both the artifact and its manifest can replace both. Use filesystem controls, authenticated
artifact distribution and external signing if stronger supply-chain trust is required.
