#!/usr/bin/env bash
set -euo pipefail
java -version
python -c 'import pyspark; print("PySpark", pyspark.__version__)'
python -m pytest -m spark -v
# Explicit opt-in: tests talk to your configured broker and create PhishGuard topics.
if [[ "${PHISHGUARD_TEST_KAFKA:-false}" == true ]]; then
  python -m pytest -m kafka -v
fi
