#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
python scripts/generate_demo.py --output data/samples/demo.csv
phishguard train data/samples/demo.csv --output models/trained/demo-only.json --report reports/local/demo.json
phishguard predict 'https://example.com/' --model models/trained/demo-only.json
printf '%s\n' 'Synthetic demo only. These metrics do NOT measure real-world detection quality.'
