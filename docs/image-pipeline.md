# Screenshot pipeline — 2.4.0

Read [the current model card](cnn-model-card.md) and [Phish360 reproduction](phish360-training.md). The complete bundle contains local experimental ResNet18 weights and their matching report. The source ZIP excludes tensor weights. The chosen threshold emphasizes recall and increases false alarms; no automatic safe-site guarantee is made.

`make launch` enables the bundled image model for separately consented captures. API image storage stays off. Inference performs no weight downloads or page fetches. Vercel remains URL-only.
