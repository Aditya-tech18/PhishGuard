# PhishGuard 2.3.0 — CNN experiment and actual release status

**The user-requested 85% precision AND recall target was not achieved.** This delivery includes the strongest selection-fold image-only candidate, its actual results, reproducible preparation/training code and tested local integration. It must not be described as production-ready protection.

## Same-cohort measurement

Both models were evaluated on exactly 2,540 cleaned original-cohort screenshots. Previous spatial CNN: phishing precision 52.20%, recall 34.02%, F1 41.19%, FPR 3.31%. New ResNet18 transfer CNN: precision 54.30%, recall 56.97%, F1 55.60%, FPR 5.10%. More phishing images are detected, with more false alarms.

The independent-source, training-domain/content-nonoverlapping publisher cohort contained 756 cases (633 phishing, 123 legitimate). Precision was 100%, but recall was only 9.00%. This is poor cross-source generalization, not an achievement of the requested operating target. Its phishing-heavy class balance and inherited publisher labels are explicitly documented. The external data was used only for frozen-model evaluation, never fitting or threshold adjustment.

## Method

Original data remained untouched. A pixel audit removed 56 within-split repeats and 2 cross-split records symmetrically. Clean folds: 8,725 training, 1,813 selection, 770 calibration, 2,540 test. Selection/calibration are separated by domain group. Three official pretrained CNN backbones and six frozen-head settings per backbone were compared; two ResNet18 fine-tuning recipes were tested. The first recipe was interrupted after seven completed epochs; its selected checkpoint was retained. The final recipe completed fourteen epochs and restored epoch ten by selection PR AUC (0.6754). A separate calibration fold chose threshold 0.477633029 by maximizing the smaller of precision/recall; calibration precision/recall were both 63.27%.

The model/threshold were locked before test/source-held-out scoring. The original test cohort was seen in prior releases, so it is not a new external certification set. Full reports include confusion counts and Wilson 95% example-level intervals. No post-hoc test filtering, label changes or favorable-class averaging was used to claim 85%.

Training-only visual review exposed blocked/error-page screenshots in both classes. Similarity diagnostics are proxies and did not remove or relabel difficult examples. Further progress needs better verified capture/intent labels and a new independent holdout, not an accuracy promise from additional epochs. Phish360 raw screenshots require authorized academic access; no personal-information form was submitted. The user was asked for an authorized data link.

## Implemented and executed

- Local trusted ResNet18 transfer inference, CPU default, no runtime downloads; old global/spatial CNN artifacts remain loadable.
- Exact training/runtime normalization regression; bounded weights-only Torch loading, finite state checks and model/report digest validation.
- Private deterministic derivative generation, duplicate-leakage exclusion and separate selection/calibration folds.
- Offline transfer-training CLI with bounded parameters, class balance, early stopping and atomic private checkpoints. Its one-epoch training-only/validation-only smoke, reload and prediction passed; this is a pipeline check, not an accuracy claim.
- **172 pytest tests passed**, 8 warnings, 64.31 seconds, **74% statement coverage**. Real Spark, Kafka, vision and Chromium markers enabled.
- Managed native API/dashboard with final URL/CNN weights: authenticated URL/image readiness, shutdown and key cleanup passed.
- Actual Chromium extension with final weights: ON/OFF, URL scan, separately consented screenshot inference and key-clear passed.
- Ruff, JS/shell syntax, dependency consistency and medium/high Bandit checks passed.
- Latest 2.3 Docker runtime was **not verified**: a fresh isolated daemon connection was unavailable. Do not relabel the older successful 2.2 container evidence as current. CPU inference itself was exercised natively. No cloud publication was performed.

## Delivery

Complete ZIP contains full source, unchanged selected origin-only URL model `3a4516d9641014ee`, all five URL candidates, new experimental CNN/sidecar and minimized aggregate reports. The source ZIP excludes learned weights. No original screenshots, external archive, private feature matrix, CSV, environment, session key, database or presentation is included. ZIP CRC, archived-byte comparison and SHA-256 manifests/checksums are verified by the packagers.

The existing Desktop/PhishGuard tree was read only and no merge was applied. Extract to a new folder, run setup_mac.sh, activate the managed environment, then make doctor/make launch. Chrome Load unpacked remains a manual step. The Vercel profile remains URL-only and does not host Torch, Spark/Kafka or Streamlit workers. See docs/cnn-model-card.md for honest model scope and reproduction.

Inventory before final report regeneration: 174 maintained code/config/test/doc files; 11,343 text lines including 8,759 Python lines. No filler or generated evidence is counted toward the approximate original LOC target. Third-party dataset/model rights require review before redistribution. Code licensing does not establish rights in every learned artifact.
