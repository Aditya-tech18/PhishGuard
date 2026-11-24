# Model training, comparison and independent evaluation

## Choose the intended inference policy

The browser removes URL query and fragment before submission. The production-oriented
`train-all` command therefore defaults to `--query-policy strip`. The resulting artifact
also applies that policy in API, CLI, Kafka and Spark inference. Submitting two query values
for the same URL gives the same score with this artifact. This removes an earlier train/serve
mismatch instead of merely documenting it.

The legacy single-logistic `train` command is retained for compatibility and uses the v1
query-retaining contract. A v1 artifact remains readable, but it is not silently reinterpreted
as a query-stripped v2 artifact. Choose a new artifact when changing preprocessing policy.

## Prepare explicit source labels

The normalized class convention is 0 legitimate, 1 phishing. Raw publisher labels must be
mapped explicitly. If the source URL table uses semicolons and text labels:

```bash
python scripts/curate_dataset.py source.csv --delimiter ';' \
  --positive phishing --negative legitimate --strip-query --drop-conflicts \
  --output data/interim/query-stripped.csv
```

Query stripping can collapse URLs that previously differed and reveal additional contradictory
labels. The helper removes **all** ambiguous normalized URLs only when requested; it never
votes, flips labels or modifies source files. Keep the aggregate curation report with the run.
The curated CSV contains URLs and belongs in ignored private runtime storage.

## Compare all five families

```bash
phishguard train-all data/interim/query-stripped.csv \
  --output models/trained/run-001 --profile standard --bootstrap 200
```

The output directory must not exist. A failed experiment remains available for diagnosis;
select a fresh run name rather than overwriting it. The standard profile fits:

| Family | Implemented constraints | Portable inference |
| --- | --- | --- |
| Logistic regression | StandardScaler, balanced classes, 1,500 iteration cap | Numeric linear weights and sigmoid |
| Decision tree | Maximum depth 12, minimum leaf 5, balanced classes | Validated iterative tree traversal |
| Random forest | 100 trees, depth 12, minimum leaf 3, two fitting workers | Mean of binary leaf probabilities |
| Gradient boosting | 100 depth-3 trees, learning rate 0.08 | Initial log odds plus boosted raw trees |
| Gaussian naive Bayes | Standardized features, variance smoothing | Bounded numeric class likelihoods |

Use `--profile fast` for mechanical demos: it uses 12 ensemble trees rather than 100. Do not
compare its metrics as if it were the standard run. Both profiles share preprocessing and
split rules. No arbitrary estimator object is serialized or loaded by the API.

## Split and select without peeking at test data

The feature table is deduplicated after normalization. Bundled PSL registrable domains,
including private suffixes, are the leakage groups. GroupShuffleSplit reserves approximately
20% of **groups** for test, then one quarter of the remaining groups for validation. Row
fractions can differ substantially when domains have unequal numbers of URLs.

Every split must contain both labels. The run fails if it does not; it never falls back to a
row-random split. Train, validation and test domain sets are explicitly checked for overlap.
Reports include group-set fingerprints but not the domain names themselves.

Only training data fits the scaler and estimators. For each candidate, validation probabilities
select a threshold over a fixed grid from 0.05 through 0.95. Eligible thresholds meet the
configured validation false-positive constraint. Within a candidate, F1 and precision choose
the threshold. Candidates that meet the constraint are ranked by validation PR-AUC, then F1,
then artifact size and a deterministic name tie-break. Test labels never enter this ranking.

If no candidate meets the validation constraint, `train-all` fails and promotes no champion.
The legacy threshold helper reports its fallback explicitly; the tournament refuses to treat
that fallback as an eligible deployment candidate.

## Export and parity checks

Each candidate becomes a `phishguard-classifier-v2` JSON artifact. The format includes ordered
feature names, schema digest, scaler, fixed algorithm name, numeric parameters, threshold,
query policy and minimized provenance. A content fingerprint identifies the exact document.
The champion is copied to `url-model.json`; the complete comparison is `evaluation.json`.

Portable inference is compared with sklearn probabilities before a candidate is accepted.
Tree input comparisons reproduce sklearn's float32 tree input behavior. The artifact parser
checks dimensions, finiteness, tree topology, child indices, cycle/shared-node absence,
unreachable nodes, depth, node count and ensemble size. Arbitrary executable objects, import
paths and expressions are not part of the format.

These checks prevent format drift and unsafe object loading. They do not prove that a model
trained by an adversary is trustworthy. Artifact owners can create a different valid model;
a fingerprint provides identity/integrity, not an external authenticity signature.

## Reports and uncertainty

The selected model's held-out report includes precision, recall, F1, PR-AUC, ROC-AUC, Brier
score, false-positive rate and the labeled confusion matrix. Calibration bins compare mean
score with observed phishing frequency. Expected calibration error summarizes those bins;
it does not calibrate the model automatically.

Domain bootstrap resamples whole domain groups, preserving within-domain dependence. The
95% percentile intervals describe variability under this dataset/group sampling scheme.
They do not include label errors, collection-source bias, future drift or adversarial attack.
A perfect synthetic-demo interval is not evidence of perfect real-world performance.

Subgroup reports cover HTTP, HTTPS, punycode and long URLs when rows exist. Small subgroups
can contain one class, in which case undefined ROC/PR quantities are explicitly null. No
invented zero-value metric is substituted for an undefined evaluation.

## Evaluate new data without retraining

```bash
phishguard evaluate independent.csv --model models/trained/run-001/url-model.json \
  --output reports/local/independent-evaluation.json --bootstrap 200 \
  --reference-report models/trained/run-001/evaluation.json
```

This command reads the frozen artifact and applies its stored query policy. It never fits
or changes the model. Source labels and delimiter remain explicit CLI options. The output
must be new; an existing report is not overwritten. Passing a reference report additionally
computes descriptive feature-distribution shifts relative to the original training profile.

The tool cannot prove that a supposedly independent CSV contains no training URLs. Establish
source/time independence through data provenance before calling its output an external test.
An input hash identifies bytes, not a license or independence guarantee.

## Deploy only after reviewing error tradeoffs

An apparently high F1 can hide important false negatives or false positives. Review counts,
class distribution, site groups, collection dates and representative mistakes privately.
Do not paste victim URLs into public tickets. Consider a stricter threshold for blocking
applications; this project displays risk estimates and does not automatically block browsing.

Use the registry quality gate for explicit minimum precision/recall, maximum false-positive
rate and minimum held-out sample size. Passing those gates records a local deployment decision,
not independent certification. See `docs/model-registry.md` for activation and rollback.

## 2.2.0 coverage diagnostic

A separate sanity probe found that ordinary login/article URL forms can be scored highly by every supplied model family. High domain-held-out corpus metrics do not remove this source/URL-shape bias. `docs/validation/url-coverage.json` records training-only path counts and the limited challenge scope. The numeric URL model has not been relabeled as fixed or perfect.

URL inference now carries `review_required` and `coverage_warning` for path/login-shaped inputs, and the web/extension interface presents them as inconclusive reviews. The raw score and verdict remain model-pattern outputs; review notices take precedence in user interpretation. No trusted-domain allowlist or fabricated benign-path training labels were added to game those examples. Root URLs still have no safety guarantee. A representative current benign-path dataset and independent source/time holdout are required for a protection claim.

## Reproduce the 2.2 origin-only correction

The older full-URL experiment had no legitimate non-root paths in its training split. Do not treat its high held-out number as representative browsing accuracy. The selected release uses an explicitly curated origin view:

```sh
python scripts/curate_origins.py /absolute/curated-url-data.csv --output reports/private-origin-training.csv
python - <<'PY'
from phishguard.ml.tournament import train_tournament
train_tournament('reports/private-origin-training.csv', 'models/new-origin-tournament', input_policy='origin-only', profile='standard', bootstrap_repetitions=100)
PY
```

Keep the private derived CSV out of source control. `input_policy` is embedded in and fingerprinted with each numeric artifact; training rejects non-origin input in origin-only mode. The loader validates the policy and strips paths/queries consistently during portable inference. There is no hand-added safe-domain override. Conservative coverage notices remain separate from the raw numeric score. Model metrics across different input policies/splits are not the same benchmark.
