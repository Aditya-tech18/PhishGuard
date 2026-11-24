#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
PYTHON="${PHISHGUARD_PYTHON:-python3.11}"
VENV="${PHISHGUARD_VENV:-.venv}"
EXTRAS='api,ml,streaming,dashboard,dev,vision,images'
if [[ "${1:-}" == --full ]]; then
  EXTRAS='api,ml,streaming,dashboard,dev,spark,vision,images,browser'
elif [[ -n "${1:-}" ]]; then
  printf '%s\n' 'Usage: bash scripts/setup_mac.sh [--full]' >&2
  exit 2
fi
if [[ -e "$VENV" && ! -f "$VENV/.phishguard-managed" ]]; then
  printf '%s\n' 'Existing environment preserved. Choose a new path, for example:' >&2
  printf '%s\n' 'PHISHGUARD_VENV=.venv-phishguard2 bash scripts/setup_mac.sh' >&2
  exit 1
fi
if [[ ! -d "$VENV" ]]; then
  "$PYTHON" -m venv "$VENV"
  touch "$VENV/.phishguard-managed"
fi
"$VENV/bin/python" -c 'import sys; assert (3,11) <= sys.version_info[:2] < (3,14), "Use Python 3.11, 3.12 or 3.13"'
if [[ -f requirements-tested.txt ]]; then
  "$VENV/bin/python" -m pip install -c requirements-tested.txt -e ".[${EXTRAS}]"
else
  "$VENV/bin/python" -m pip install -e ".[${EXTRAS}]"
fi
printf '%s\n' "Installed. Activate with: source $VENV/bin/activate"
printf '%s\n' 'Complete bundle: make doctor, then make launch.'
printf '%s\n' 'Spark needs Java 17. Kafka needs a broker. Browser tests need: python -m playwright install chromium'
