#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ -n "${PHISHGUARD_PYTHON:-}" ]]; then
  task_python="$PHISHGUARD_PYTHON"
else
  task_python=""
  for candidate in python3.11 python3.12 python3.13 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then task_python="$(command -v "$candidate")"; break; fi
  done
fi
if [[ -z "$task_python" ]]; then echo 'Install Python 3.11 or newer, then run this command again.'; exit 1; fi
"$task_python" -c 'import sys; assert (3,11)<=sys.version_info[:2]<(3,14), "Use Python 3.11–3.13"'
task_env=".venv-phishguard26"
if [[ ! -f "$task_env/.phishguard-managed" ]]; then
  if [[ -e "$task_env" ]]; then echo "Existing unmanaged $task_env found. Rename it before continuing; it was not changed."; exit 1; fi
  "$task_python" -m venv "$task_env"
  touch "$task_env/.phishguard-managed"
fi
if [[ ! -f "$task_env/.installed-2.6.0" ]] || [[ pyproject.toml -nt "$task_env/.installed-2.6.0" ]]; then
  "$task_env/bin/python" -m pip install -e '.[api,ml,vision,phish360]'
  touch "$task_env/.installed-2.6.0"
fi
exec "$task_env/bin/python" scripts/run_local.py "$@"
