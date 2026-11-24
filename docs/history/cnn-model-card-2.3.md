# Screenshot model card — 2.3.0 experimental candidate

**The requested phishing-class precision and recall of 85% each were not achieved.** The strongest validation-selected image-only candidate is included with its real measurements. It is not a production protection model. URL inference remains a separate origin-only classifier; its metrics must not be reported as CNN metrics.

## Fixed comparison on the same cleaned test cohort

Both models were scored on the same 2,540 original-cohort images, after one cross-split duplicate was excluded. Positive means phishing. Neither this comparison nor the external test was used to select the new model or threshold.

| Measure | Previous spatial CNN | New ResNet18 transfer CNN |
| --- | ---: | ---: |
| Phishing precision | 52.20% | 54.30% |
| Phishing recall | 34.02% | 56.97% |
| F1 | 41.19% | 55.60% |
| False-positive rate | 3.31% | 5.10% |
| True phishing detections | 83 / 244 | 139 / 244 |
| False alarms | 76 / 2,296 | 117 / 2,296 |

The recall improvement comes with more false alarms. No score, sensitivity or safety guarantee is implied by these dataset numbers.

## Training and selection

- Official ImageNet ResNet18 initialization, then supervised upper-layer fine-tuning on the local corpus. No filenames, URLs, domain strings or source class directories are model features.
- Clean cohort: 13,848 images. Train: 8,725 (1,860 phishing); selection: 1,813 (205 phishing); calibration: 770 (98 phishing); test: 2,540 (244 phishing).
- Pixel duplicate audit excluded 56 within-split repeats and 2 cross-split records symmetrically. No row was removed or relabeled because a model predicted it incorrectly.
- Original registrable-domain/content grouping is retained. The original filename-host provenance and publisher labels are not independently verified. Validation is subdivided by group with seed 2718.
- Three pretrained CNN backbones were compared: ResNet18, ConvNeXt Tiny and CLIP ResNet50. Each frozen feature probe compared three regularized linear and three RBF heads. Two ResNet18 fine-tuning recipes were examined. An interrupted first recipe completed seven epochs and retained its selected checkpoint. The final recipe completed fourteen epochs, restoring epoch ten using selection-fold PR AUC (0.6754).
- A separate group-disjoint calibration fold selected threshold 0.477633 by maximizing the smaller of precision/recall. Calibration precision and recall were both 63.27%. No threshold on that fold met both 85% targets.
- The model and threshold were locked before the final test. The test cohort was previously observed in earlier releases and is not a fresh external certification cohort. The JSON report includes individual-example Wilson 95% intervals; these do not replace a domain/source bootstrap or live evaluation.

## Additional source-held-out stress test

A separate publisher-described manually curated archive was reserved for evaluation only. It was not used for gradients, hyperparameters, checkpoint choice or threshold calibration. Only bounded PNG pixels/label metadata were read; archived HTML was not executed and submitted URLs were not visited.

After input validation, 977 publisher-labeled cases remained. Excluding domains/content observed in training/selection/calibration left 756 cases: 633 phishing and 123 legitimate by the publisher's labels. At the already frozen threshold, **precision was 100%, but recall was only 9.00%**. The small number of flagged positives and phishing-heavy class distribution make the precision number unsuitable as a headline claim. Poor cross-source recall is a material generalization failure. Publisher labels and site intent were not independently re-verified.

Source: [seirin16/Dataset_Phising](https://huggingface.co/datasets/seirin16/Dataset_Phising), revision and archive SHA-256 in the JSON report. License is CC BY-NC 4.0. This dataset was used only for evaluation; raw examples are not redistributed. The source card's manual-verification claim is attributed to its publisher.

## Data quality findings and next requirements

A training-only nearest-neighbor review surfaced nearly identical blocked/error screens under opposite labels. A visual descriptor found 137 phishing training cases with cosine similarity >=0.99 to some legitimate training case; this is a similarity proxy, not proof that all such pairs have identical intent. The review did not trigger any post-hoc test filtering. Screenshot pixels alone cannot reliably establish the destination/ownership of visually cloned pages.

More training on this same cohort has not delivered the requested target. The next meaningful round needs independently verified captures with site intent at capture time, representative legitimate login pages, explicit quality labels for blocked/empty/offline captures, and a genuinely new domain/source/time holdout. An additional image+domain experiment reached roughly 75% balanced precision/recall on selection and was not integrated or represented as image-only performance.

Phish360 was investigated as a better source: its public Parquet listing exposes image paths, while raw screenshots require the publisher's academic access flow. No form or personal information was submitted. An authorized raw-image link is required to use that source. [Publisher dataset page](https://web.cs.hacettepe.edu.tr/~selman/phish360-dataset/).

## Runtime and reproduction

Inference uses local trusted tensor weights, CPU by default, bounded image decoding and `torch.load(weights_only=True)`. It never downloads weights or follows submitted URLs. The experimental image route requires authentication and fresh capture consent. Images are not retained by the API. Vercel remains a URL-only profile and does not include Torch/CNN workers.

```sh
# Use an explicit site-group-isolated manifest; derivatives and path records stay private.
python scripts/train_transfer.py prepare /absolute/image-root --manifest /absolute/manifest.csv --output reports/private-transfer
# Official initialization is downloaded separately, never by HTTP inference.
python - <<'PY'
import torch
state = torch.hub.load_state_dict_from_url(
    'https://download.pytorch.org/models/resnet18-f37072fd.pth',
    model_dir='models/private-initialization', check_hash=True, weights_only=True)
PY
python scripts/train_transfer.py train --records reports/private-transfer/records-private.json --pretrained models/private-initialization/resnet18-f37072fd.pth --output models/new-transfer-run --epochs 16 --batch-size 32 --device mps --workers 2
```

Use CPU if MPS is unavailable. GPU execution is seeded but not guaranteed bit-for-bit identical across library/hardware versions. The stored epoch history, calibration policy, model digest and split counts are evidence for the delivered candidate. Do not mix the external stress-test dataset into training and continue to call it an untouched test.

Backbone references: [Torchvision ResNet18](https://docs.pytorch.org/vision/stable/models/generated/torchvision.models.resnet18), [ConvNeXt Tiny](https://docs.pytorch.org/vision/main/models/generated/torchvision.models.convnext_tiny.html), [CLIP ResNet50 weights](https://huggingface.co/timm/resnet50_clip.openai). Their pretraining benchmarks are not phishing-detection metrics.
