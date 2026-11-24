# Reproduce the Phish360 experiment

Obtain the raw Phish360 archive through the publisher academic access process:
https://web.cs.hacettepe.edu.tr/~selman/phish360-dataset/
The archive and its extraction password are not distributed in this repository.
Follow the publisher license, citation, and use restrictions; repository code licensing
is separate from the data license. No archived HTML is executed or extracted by these scripts.

Use Python 3.11 and install the project with its `vision`, `phish360`, and `ml` extras.
For the recorded experiment, Torch 2.15.0, Torchvision 0.29.2, NumPy 2.4.6,
scikit-learn 1.9.1, Pillow 13.0.0, tldextract 5.4.0, and pyzipper 0.3.6 were used.
An Apple MPS GPU was used. CPU and CUDA devices can be selected explicitly.

```sh
python -m pip install -e '.[vision,phish360,ml]'
export PHISH360_ARCHIVE=/absolute/path/phish360.zip
export PHISH360_WORK_DIR=/absolute/path/private-phish360-run
mkdir -p "$PHISH360_WORK_DIR"
# Enter the DATASET extraction password privately when prompted.
read -s PHISH360_DATASET_PASSWORD
export PHISH360_DATASET_PASSWORD
python scripts/prepare_phish360.py
unset PHISH360_DATASET_PASSWORD
```

Preparation reads the publisher label files. Test positives use `phish`; training
positives use brand names. The explicit allowlisted brand mapping requires a matching
publisher P-prefixed folder. Missing/unknown labels and folder-label mismatches are
recorded and excluded, without guessing their intent. All image names, domains, URLs and label text remain outside the model input.
Derivatives and row manifests are private and must not be added to a public repository.
Exact contradictory pixels are excluded; pixel duplicates are deduplicated. The publisher
test set is reserved. Trainval domain/content connected components intersecting test
are excluded from development. Remaining trainval groups are split into training,
selection and calibration with fixed seeds 4201 and 4202.

Get the official ImageNet initialization separately:

```sh
mkdir -p models/private-initialization
curl -fL https://download.pytorch.org/models/resnet18-f37072fd.pth \
  -o models/private-initialization/resnet18-f37072fd.pth
export PHISH360_PRETRAINED="$PWD/models/private-initialization/resnet18-f37072fd.pth"
export PHISH360_DEVICE=mps  # cpu or cuda also supported
python scripts/train_phish360.py
```

The script verifies the full official pretrained SHA-256. It trains the upper two
ResNet18 stages and a new classifier for at most 20 epochs, with early stopping.
The best checkpoint is selected by selection PR AUC. Only then is a threshold selected
by maximizing the minimum phishing-class precision/recall on calibration. Calibration and final test run on CPU, matching the deployed vision model. The model
and threshold are saved to separate locks before the official test is scored once.
A later experiment informed by this test must call it a development benchmark and
reserve a genuinely new holdout; do not repeatedly tune against its score.

The final aggregate report includes class counts, confusion matrix, precision, recall,
F1, false-positive rate, and individual-example Wilson 95% intervals. These intervals
do not account for all within-domain/template correlations. Raw screenshots, individual
prediction records and the original archive are deliberately excluded from release ZIPs.

A screenshot-only model cannot prove website ownership or detect every visually exact
clone. This benchmark does not establish universal live-web accuracy. Vercel remains
URL-only; the screenshot model runs in the local/vision service profile.

## Recorded sensitivity revision

The first `train_phish360.py` result is preserved unchanged. After its recall missed 85%,
the recorded run used `python scripts/recalibrate_phish360.py` with the same
`PHISH360_WORK_DIR`. That script freezes weights, recalculates calibration predictions,
locks a recall-oriented threshold using calibration only, and then audits the already
observed test predictions. It explicitly marks the policy revision and does not label
the result a new independent test. No repeated alternate threshold policies were tried.

To load a reproduced sensitivity candidate without overwriting the supplied model:

```sh
mkdir -p models/private-candidate
cp "$PHISH360_WORK_DIR/best.pt" models/private-candidate/vision-model.pt
cp "$PHISH360_WORK_DIR/sensitivity-evaluation.json" models/private-candidate/vision-model.json
export PHISHGUARD_VISION_MODEL="$PWD/models/private-candidate/vision-model.pt"
make launch
```

The recorded final run used batch size 16 and no parallel loader workers because of
the available Mac memory. The local temporary runtime was created from exact-version
hash-verified official PyPI wheels after cloud-offloaded development files stalled.
These environment repairs did not change the dataset split or use test results to fit weights.
