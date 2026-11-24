# Dataset contracts and provenance

## Preserve the source

Treat `~/Desktop/PhishGuard/data/raw/extracted` as immutable. The supplied release contains no
copy of your 4.4 GB dataset and does not modify it. Never run cleanup, repartition, extraction
or overwrite commands against raw. Record source URL, license, download date, publisher and
checksum in your private data catalog before training or distribution.

The existing source tree contains URL CSVs named `merged_features_final.csv` and
`dns_feature_94k.csv`. Their names do not establish the presence of raw URLs or label polarity.
The inspector exposes only headers and aggregate counts, never sample URLs. Use explicit
column names and the actual delimiter.

## Required URL schema

A source row must have a raw public HTTP(S) URL and one explicit label. The normalized training
contract is `url: str`, `label: int` where **0 = legitimate, 1 = phishing**. Map publisher labels
explicitly. A source using `-1` for phishing needs `--positive=-1`; a source using `1` for
legitimate needs `--negative 1` and the correct positive counterpart.

```bash
phishguard inspect source.csv --delimiter ';' --url-column URL --label-column status \
  --positive phishing --negative legitimate
phishguard train source.csv --delimiter ';' --url-column URL --label-column status \
  --positive phishing --negative legitimate --output models/trained/url-model.json
```

Unknown labels, malformed URLs, missing values and private/local literals are rejected and
counted. CSV files without named URL and label columns fail before training. Feature-only CSVs
must not be converted into invented URLs. Obtain the real URL source or train a different,
explicitly compatible model. Network-derived DNS features are intentionally excluded because
online URL-only inference cannot reliably reproduce historical DNS measurements.

## Duplicates and conflicts

Exact normalized duplicate URLs count once. Identical normalized URLs with contradictory
labels stop training rather than assigning a majority label. Fragments are removed. Query
values remain in offline training; the Chrome extension removes them for privacy, which creates
a documented train/serve distribution difference. Consider training a separate query-stripped
model and evaluating it for the extension use case.

Registrable domain groups are formed using a bundled public suffix list, including private
suffixes. This prevents `shop.example.co.uk` and `login.example.co.uk` falling into different
splits. It does not eliminate campaign-template, image or temporal leakage. For a credible
production result, add independently collected time-held-out and source-held-out evaluations.

## Scale and memory

CSV iteration is streaming, but sklearn training currently materializes deduplicated rows,
features and groups in memory. It is intended for URL tables that fit RAM, not arbitrary
terabyte datasets. Spark ETL processes distributed frames and writes feature Parquet; the
portable classifier training is not Spark MLlib training. Do not claim distributed model
training just because Spark is used upstream.

`inventory` can calculate file checksums without editing source files:

```bash
phishguard inventory path/to/extracted --hash > reports/local/inventory.jsonl
```

This can be slow on images. The inventory refuses symlinks. It does not extract archives or
license the dataset for redistribution. Keep inventory paths private if filenames identify users.

## Images

Optional CNN inputs are manually curated PNG/JPEG screenshots. The extension can separately capture an explicitly consented visible tab for inference;
it never adds those captures to training data.
Prepare `train/legitimate`, `train/phishing`, `val/legitimate`, `val/phishing`. Isolate sites,
brands, campaigns and capture dates before constructing folders. Identical train/val bytes
are rejected, but near-duplicate or transformed images require additional audit.

Never train on passwords, personal inboxes or authenticated account pages without an appropriate
basis and minimization. The runtime does not persist uploaded screenshots; the offline training
folders remain your responsibility. A 5 MB byte limit and 16 million pixel limit apply per image.
CNN training loads bounded batches lazily from disk. Explicit manifests can enforce site-group
and byte-identical split isolation. Full-dataset metadata ETL is implemented separately in Spark.

## Explicit conflict curation

Training fails if any normalized URL has contradictory labels. To audit and produce a new
local CSV while excluding every ambiguous URL, use the optional curation helper:

```bash
python scripts/curate_dataset.py source.csv --delimiter ';' \
  --positive phishing --negative legitimate --drop-conflicts \
  --output data/interim/curated-new.csv
```

Without `--drop-conflicts`, contradictory rows stop the helper before output is written.
An existing output is never overwritten. Curation writes raw normalized URLs with mode 0600;
keep this file out of Git. The aggregate report names no URLs. Compare metrics with and
without other provenance filters before using the dataset as a benchmark. Removing ambiguous
labels is not proof that all remaining labels are correct.
