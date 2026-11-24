# Setup, safe merge and rollback

## Prerequisites

Use Python 3.11 and a virtual environment dedicated to this repository. Spark 3.5.8 is pinned
and should use Java 17, not the system's newer JDK by accident. Kafka can run separately or
through the optional Compose profile. Network access is needed to download dependencies;
the runtime URL model itself requires no internet access.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e '.[api,ml,streaming,dashboard,dev]'
```

Add extras only when using them:

```bash
pip install -e '.[spark]'
pip install -e '.[vision]'
```

On a Mac with Homebrew Java 17 already installed:

```bash
export JAVA_HOME="$(brew --prefix openjdk@17)/libexec/openjdk.jdk/Contents/Home"
export SPARK_LOCAL_IP=127.0.0.1
export PYSPARK_PYTHON="$(command -v python)"
```

## Secrets and runtime

The app reads environment variables; it intentionally does not automatically source `.env`.
If creating `.env`, keep it local, restrict permissions and do not commit it. Generate distinct
API and HMAC secrets:

```bash
export PHISHGUARD_API_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export PHISHGUARD_HMAC_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export PHISHGUARD_MODEL=models/trained/url-model.json
```

Do not paste these values into a public issue. Event storage is OFF unless explicitly enabled:

```bash
export PHISHGUARD_STORE_EVENTS=true
export PHISHGUARD_DB=data/predictions.db
export PHISHGUARD_RETENTION_DAYS=7
```

Enable only after deciding that keyed URL linkage and metadata retention are appropriate.
The key should be different from the API key. Rotate it to break future linkage with previous
digests. Rotation does not delete prior backups or historical rows.

## Existing Desktop project

The source release is created separately. Your extracted dataset is not packaged and no
existing Desktop files are edited by the build. Run the merge preview from the release root:

```bash
bash install_to_mac.sh --target "$HOME/Desktop/PhishGuard"
```

The preview lists added files, backed-up replacements and unresolved conflicts. By default,
empty placeholder files can be replaced; nonempty conflicts block the whole apply. To preserve
existing nonempty edits, reconcile them manually in a separate copy. To intentionally install
the new code over old code, review:

```bash
bash install_to_mac.sh --target "$HOME/Desktop/PhishGuard" --replace-code
```

Then apply:

```bash
bash install_to_mac.sh --target "$HOME/Desktop/PhishGuard" --replace-code --apply
```

The backup is beside the target, named `PhishGuard.code-backup-<UTC timestamp>`. It contains
`original/` for replaced files and `merge-journal.json` with the plan and completed operations.
The script writes files atomically one at a time; a whole-directory transaction is not claimed.
Do not edit the destination concurrently. A malicious concurrent writer is outside the script's
threat model. Symlinks in path chains are refused. It never follows symlinks into dataset paths.

Only code/documentation/config allowlists are merged. `data`, `models`, `.env`, `.git`, `.venv`,
`reports`, `logs` and unknown top-level user files are skipped. Existing Git history remains.
The source `data/samples` is also not copied: the demo generator regenerates synthetic samples.
No archives are extracted by this script. Unzip the delivered archive into a separate folder.

## Rollback

1. Stop services using the target code.
2. Read the journal and compare the current hashes with the release before reverting anything.
3. Copy saved files from `original/` back to their corresponding target paths.
4. Added files are listed in the journal; remove them only after checking they contain no new work.
5. Reinstall the previous dependency set if the environment was changed after the merge.

A preview-first guarded rollback helper is available:

```bash
python scripts/rollback_merge.py /path/to/merge-journal.json
python scripts/rollback_merge.py /path/to/merge-journal.json --apply
```

It refuses rollback if installed files have later user edits, snapshots the current code,
restores only verified backups and removes only unchanged files added by that merge. Dataset rollback is unnecessary because
the merge never changes dataset paths. Backups themselves may contain secrets if old code did;
keep them private and remove them only after a retention decision.

## Post-merge verification

```bash
python -m pip install -e '.[api,ml,streaming,dev]'
make lint
make test
phishguard inspect path/to/dataset.csv --url-column URL --label-column label --delimiter ';'
```

Older v1 settings are not accepted as v2 runtime settings. The YAML files are documented
reference defaults; production secrets and paths are environment-driven. Training CLI arguments
control ingestion; do not expect changing a YAML parameter to change hard-coded model behavior.
See `config/model.yaml` for the implemented logistic baseline. The separate train-all command implements the five-family comparison.
See docs/model-training.md for its concrete profile and selection rules.
