# Phishguard ai — main project · 2.6.1

Open this folder in VS Code. Stop the old project server with Ctrl+C in its terminal first.

```bash
bash start_local.sh
```

Open http://127.0.0.1:8000 in Google Chrome. Click Connect extension and follow the guided setup. In chrome://extensions, remove or disable older PhishGuard copies, choose Load unpacked and select this folder's extension subfolder. Reload the dashboard after installation. Pair and approve website access in the extension setup page, then turn protection ON.

The dashboard cannot silently install a browser extension. A missing extension now opens guided setup instead of leaving you at an unexplained error. The setup screen displays this project's actual folder path and offers a ZIP download.

Code, old dataset, both trained model families, reports and the supplied Phish360 archive are in this main folder. Existing data is copied, not linked back to the old folder. The old project is preserved. The new environment is created independently; old Python environments and Git history were not copied.

Screenshot CNN checks require explicit consent. URL risk predictions can be wrong; no universal accuracy guarantee. Spark/Kafka services remain separately started components.

## Local dataset layout

- `data/raw/extracted/Phishing dataset/`: original image corpus and URL CSV files, restored locally and checked against original ZIP CRCs.
- `data/raw/dataset_archive/Phishing dataset V2.0.zip`: original archive.
- `data/raw/phish360/phish360.zip`: the supplied CNN dataset archive.
- `data/raw/phish360/extracted/Phish360/`: full extracted Phish360 publisher tree with screenshots, labels, URL metadata and inert raw HTML.
- `models/releases/2.6.0/`: actual trained URL model, candidate model artifacts and CNN weights.
- `reports/releases/2.6.0/`: recorded benchmark and pipeline reports. These weights and benchmark results were not retrained by the connection fix.

See COPY_REPORT.json and DATA_VERIFICATION.json for actual copy and integrity outcomes. Dataset archives and extracted raw content are private local data, not dashboard assets. No raw HTML is served or executed by the local dashboard.

## Connection fix verification

73 selected Python checks and 20 extension behavior checks passed. Isolated Chrome verified missing-extension setup, exact new-folder path, ZIP download, authenticated pairing, ON, actual URL result in new tabs, WebSocket updates and OFF cleanup. Native Chrome permission approval remains a manual browser action. Both actual model inference smoke checks passed from this folder's independent environment.

The old folder and its running server were left intact. Stop the old server before starting this main project on port 8000. The launcher now gives a plain explanation if that port is already occupied.
