# Screenshot model card — PhishGuard 2.4.0

The current image-only ResNet18 operating point measured **precision 88.16% and recall 88.36%** on 2,684 Phish360 cases. **This is an audit of a previously observed test set after changing the operating-point policy. A genuinely new independent test is still required.** It is not universal live-web accuracy or production certification.

## First lock and the subsequent policy revision

The initial model and max-min calibration threshold were locked before the first test. That first test produced precision 92.85%, recall 80.66%; recall missed 85%. The original report is preserved in `docs/validation/phish360-first-locked-evaluation.json`.

After seeing that result, the model weights remained frozen. A new rule was applied using **calibration predictions only**: maximize recall among thresholds whose descriptive Wilson precision lower bound is at least 85%. The threshold was written to a new lock before re-reading the original test predictions. No test score sweep or new test-based training was performed. Nevertheless, changing the rule after observing a test result makes the following numbers an adaptive benchmark audit, not independent confirmation.

| Same 2,684 cases | First locked operating point | Current sensitivity operating point |
| --- | ---: | ---: |
| Threshold | 0.912861884 | 0.279168636 |
| Phishing precision | 92.85% | 88.16% |
| Phishing recall | 80.66% | 88.36% |
| F1 | 86.33% | 88.26% |
| False-positive rate | 5.59% | 10.69% |
| True phishing detections / 1,272 | 1026 | 1124 |
| Missed phishing cases | 246 | 148 |
| False alarms / 1,412 legitimate | 79 | 151 |

The revised threshold catches 98 additional phishing cases and adds 72 false alarms. Current calibration precision is 88.77%, recall 94.71%. Example-level intervals are descriptive, assume more independence than related webpage templates may have, and do not provide a post-selection guarantee. Precision also depends on class prevalence; these cases contain 47.4% phishing and do not represent the live-web base rate.

## Data and training

- Source: the user-authorized raw [Phish360 archive](https://web.cs.hacettepe.edu.tr/~selman/phish360-dataset/), SHA-256 `64f573e6e52a9deb486f9d07d87c56e245065545fa161e8db6f080732d5ddd5f`. Raw data is subject to publisher academic-use terms and is not redistributed here.
- 10,748 screenshot entries; 10,533 decoded/accepted records. Rejections: 86 missing labels, 120 missing metadata files, eight unknown/inconsistent labels, one oversized image. Exclusions are fixed input-quality rules, not model-error filtering.
- Training labels contain brand strings while test positives say `phish`. The parser requires an allowlisted training brand and matching publisher P-folder encoding, checks legitimate L-folder consistency, and excludes missing/unknown labels. Brand, folder and URL text never enter the model.
- 51 exact-pixel duplicates removed. 521 trainval cases whose domain/content components intersect official test were excluded from development. All four resulting folds have disjoint registrable-domain/content components. Near-duplicate templates are not comprehensively eliminated.
- Train: 5,102 (1,749 phishing); selection: 1,093 (375 phishing); calibration: 1,082 (359 phishing); test: 2,684 (1,272 phishing). The retained test covers 96.86% of the publisher's 2,771 test entries, so results do not cover every raw entry.
- No exact raw/resized-pixel overlap with the previous local corpus was found. Only this source was used to fit this model. The previous PhishGuard weights were not reused.
- Official ImageNet ResNet18 initialization; layers 3/4 and a new dropout/128-unit classifier fine-tuned with AdamW and mild color/affine augmentation. Full-frame RGB224 bilinear preprocessing and ImageNet normalization match runtime. No flips or URL visits.
- Eleven epochs completed; epoch six restored by maximum selection PR AUC (0.9755). Batch 16, no parallel workers, seed 42, Apple MPS training. Calibration and test inference run on CPU, matching the default deployed model. GPU runs are not guaranteed bit-for-bit reproducible across hardware/library versions.

## Scope and runtime

This is a single-publisher, domain-isolated benchmark. It does not establish unseen-source, unseen-brand, time-held-out, or live-browser accuracy. Publisher labels have not been independently re-verified. The previous release's poor external-source results concern a different model; this new model has not received a fresh external-source certification. A screenshot alone cannot prove site ownership for visually exact clones.

Inference uses local tensor weights with bounded decoding, weights-only loading, finite-state checks and report/weight identity validation. Image inference requires authentication and explicit capture consent; the API does not retain images or fetch submitted URLs. Image scores remain experimental and are not calibrated safety probabilities. Vercel is still URL-only; Torch/CNN runs locally or in the vision service profile.

The origin-only URL model is unchanged, and its results must not be presented as CNN metrics. The earlier 54.30%/56.97% CNN results used a different corpus and class distribution; they are not a same-cohort comparison with this release.

See [Phish360 reproduction](phish360-training.md). Raw images, row manifests, passwords and prediction-level records stay private. The complete ZIP includes the trained tensor weights and aggregate reports; the source ZIP omits learned tensor weights.
