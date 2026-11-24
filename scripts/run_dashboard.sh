#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
exec streamlit run src/phishguard/dashboard/app.py --server.address 127.0.0.1 --browser.gatherUsageStats false
