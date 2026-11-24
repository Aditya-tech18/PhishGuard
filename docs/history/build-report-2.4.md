# PhishGuard 2.4.0 — actual build and validation report

## Delivered model and measured scope

The complete ZIP contains full source, the unchanged origin-only URL model, and the newly trained experimental Phish360 screenshot CNN. At the current threshold, the **previously observed benchmark audit** measured precision **88.16%**, recall **88.36%**, F1 **88.26%**, false-positive rate **10.69%**, over 2,684 cases.

This is not independent confirmation: the first locked test measured precision 92.85% and recall 80.66%, missing the recall target. Afterwards a fixed calibration-only recall-oriented rule changed the threshold while keeping weights frozen. The revised threshold was locked before auditing stored test predictions. Both results and the adaptive policy change are included. A new independent holdout is still needed; no universal live-web or 100% accuracy claim is made.

At the current threshold: TP 1,124, FP 151, FN 148, TN 1,261. Compared with the first operating point, this catches 98 more phishing cases and adds 72 false alarms. The test contains 47.4% phishing; precision on other base rates may be substantially different.

## Training actually executed

- Supplied Phish360 archive read using its authorized extraction password; no archived HTML executed, no dataset URLs visited.
- Explicit publisher label audit handled brand-valued train labels and binary test labels. 215 invalid/incomplete cases excluded by input rules, 51 exact-pixel duplicates removed, 521 development cases excluded for test-group overlap.
- Group-isolated folds: 5,102 training; 1,093 selection; 1,082 calibration; 2,684 test. Zero exact overlap with the old local corpus was found; no old tuned weights used.
- ImageNet-initialized ResNet18 trained for eleven completed epochs on Apple MPS. Epoch six selected by selection PR AUC 0.9755. Batch 16, no parallel workers. Calibration/test inference used CPU.
- Model SHA-256: `5eb84248519052f38b5372637075d17fa309b5a421adca07dc3820b9c4c83d0a`. Current threshold: `0.27916863560676575`. Selection/threshold locks, histories, aggregate evaluation and source hashes are preserved.
- Missing labels, metadata and oversized images mean the retained test covers 96.86% of the publisher test entries. Labels remain publisher-provided; near-duplicate templates and unseen-source/time/brand performance are limitations.

## Verification actually executed for 2.4

- **20 targeted pytest tests passed:** ten transfer/data-isolation tests and ten image/API tests. The API tests emitted one existing Starlette/httpx deprecation warning. No coverage percentage was measured in this round.
- Loaded the actual final CNN weights/report through the project CPU runtime. Raw archive screenshots from both classes matched the recorded derivative scores.
- Actual FastAPI application check passed: health/version, authenticated image predictions, URL prediction, missing-key rejection, missing-consent rejection, invalid-image rejection, and no event database created.
- Ruff passed for the complete staged source. Reproduction scripts compile. ZIP CRC, member hashes, source/weight agreement, excluded-private-data checks and SHA-256 manifests are verified during packaging.
- Spark, Kafka, Chromium/Chrome extension, Streamlit and Docker were **not rerun in this round**. The earlier 2.3 validation is archived under `docs/history` and is not presented as a new pass for this model. The application interfaces remain unchanged apart from version metadata and the supplied model.
- No Vercel/cloud deployment, browser-store publication, automatic Chrome installation, or merge into Desktop was performed. Vercel remains URL-only; the local/vision profile runs CNN inference.

## Data preservation and delivery

The original Desktop/PhishGuard data and the supplied Downloads/phish360.zip remain untouched. Environment repairs and new derivatives stayed in task-owned work/temporary directories. Only task-downloaded temporary research archives and recomputable feature matrices from completed experiments were removed to recover space; their source/audit reports and trained models were retained.

The ZIP includes safe merge/setup scripts, code, model weights and aggregate evidence. It excludes raw images, the dataset ZIP, private manifests, per-image predictions, feature matrices, extraction password, API keys, environments and databases. The source ZIP omits learned tensor weights. Extract the complete ZIP into a new folder and follow README.md; installing the Chrome extension remains a manual Load unpacked step.

Read `docs/cnn-model-card.md` for exact limitations and `docs/phish360-training.md` for reproduction. Publisher academic-use restrictions apply separately from the repository code license; bundling a local project does not grant unrestricted dataset/model redistribution rights.
