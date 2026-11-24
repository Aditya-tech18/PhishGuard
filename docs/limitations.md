# Limitations and acceptance boundaries

## Detection quality

The complete local bundle includes dataset-trained URL and screenshot models with held-out evaluation reports. The source-only bundle excludes weights. The demo generator produces synthetic
URLs solely to exercise the pipeline. A high score on that corpus does not measure real-world
precision or recall. Real performance requires a licensed, current, representative dataset,
verified label polarity, separate source/time holdout and an independent error review.

Five classifier families are implemented with validation-only selection and portable inference.
They share the same lexical feature limits; adding families does not establish site intent.
A URL string alone cannot establish page intent, authenticated content, brand ownership,
redirect destination or compromise status. IDN, shortener and adversarial examples can fool it.

Domain groups prevent a specific form of leakage. They do not prevent reused paths, campaigns,
registrar patterns or historical source biases. The threshold false-positive constraint is
only empirical on validation data. If no candidate satisfies it, the report says so; the
fallback threshold must not be described as guaranteed to meet the constraint.

## Optional screenshot classifier

The small CNN is experimental and uncalibrated. It has an offline train/validation procedure,
input validation and consented API inference. The complete bundle now includes real-data weights, automated filename-derived group isolation, bounded cache preparation and held-out evaluation. Its measured recall is only 34.29%; independent current-source evaluation remains necessary.
The extension can capture the visible tab only after separate opt-in and fresh consent.
URL and image results are not fused.

## Operational scale

Spark ETL is distributed; sklearn URL training is in-memory with a row cap; CNN loading is lazy and batched from disk.
The example Kafka consumer is serial and synchronous for clear delivery guarantees. SQLite is
single-host metadata persistence. These are not claims of high-throughput production scaling.
No throughput, latency SLO, availability target or disaster-recovery exercise is claimed.

CI files are supplied, but a local run does not imply GitHub Actions or cloud deployment ran.
The container recipe is supplied; it was locally built/run; exact results are listed in BUILD_REPORT.
No cloud accounts, domain, registry, certificate, web store listing or GitHub repository is
created by this package. Publishing credentials and service ownership are not fabricated.

## Privacy

Storage disabled avoids application DB retention; it does not imply perfect zero traces in
OS memory, swap, browser history, terminal history, crash reports or infrastructure logs.
Passing a sensitive URL as a CLI argument can leave it in shell history and process listings.
Use synthetic URLs for demos. HMAC metadata is pseudonymous, not anonymous. A single user key
can correlate repeated URLs within its lifetime. Deletion cannot erase backups or old disk
blocks securely.

## Safe merge

The installer preserves protected runtime trees and non-allowlisted user files. It does not
remove obsolete code, migrate an existing environment, reconcile semantic conflicts or restore
a whole project atomically. Backups and journal support manual recovery. The build does not
apply the merge to the Desktop; a reviewed preview is supplied separately when possible.

## 2.2 URL coverage correction

The old corpus contained zero legitimate non-root paths in the training split, while 11,202 phishing training rows had paths. Full-URL held-out metrics concealed this shortcut and ordinary login/article probes exposed overflagging. The selected 2.2 origin-only model ignores path/query, excludes contradictory-origin labels, and is evaluated on a different origin dataset/split. It still can overflag legitimate hosts; conservative review notices remain. No independent source/time evaluation or calibrated safety guarantee is claimed.

## 2.3 screenshot status

The new transfer CNN reached 54.30% phishing precision and 56.97% recall on the cleaned original cohort; FPR rose to 5.10%. The 85%/85% target was not achieved. Cross-source recall was only 9.00% on domain/content-nonoverlapping publisher cases. This is a generalization failure, not a protection-ready result. Read cnn-model-card.md. Older sections/report numbers are historical.
