#!/usr/bin/env python3
"""Prepare private transfer folds or train an offline CNN; never part of API startup."""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("root", type=Path)
    prepare.add_argument("--manifest", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--workers", type=int, default=4)
    train = sub.add_parser("train")
    train.add_argument("--records", type=Path, required=True)
    train.add_argument("--pretrained", type=Path, required=True)
    train.add_argument("--output", type=Path, required=True)
    train.add_argument("--device", choices=["cpu", "mps", "cuda"], default="cpu")
    train.add_argument("--epochs", type=int, default=16)
    train.add_argument("--batch-size", type=int, default=32)
    train.add_argument("--workers", type=int, default=0)
    train.add_argument("--freeze-batchnorm", action="store_true")
    args = parser.parse_args()
    if args.command == "prepare":
        from phishguard.ml.transfer_data import prepare_transfer

        _, report = prepare_transfer(args.root, args.manifest, args.output, workers=args.workers)
    else:
        from phishguard.ml.transfer_training import train_transfer

        report = train_transfer(
            args.records,
            args.pretrained,
            args.output,
            epochs=args.epochs,
            batch_size=args.batch_size,
            device=args.device,
            workers=args.workers,
            freeze_batchnorm=args.freeze_batchnorm,
            progress=lambda item: print(json.dumps(item), flush=True),
        )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
