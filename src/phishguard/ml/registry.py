"""Immutable versioned local model registry and explicit quality-gated activation.

Only JSON model artifacts are accepted. Activation writes a small atomic pointer; workers
resolve and validate the pointer at startup, never halfway through a request. Registry hashes
provide corruption detection, not signatures against a malicious registry owner.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
from phishguard.common.files import (
    atomic_bytes,
    atomic_json,
    exclusive_lock,
    read_json,
    reject_symlink_chain,
    sha256_file,
)
from phishguard.ml.model_registry import URLModel

VERSION = re.compile(r"^[a-f0-9]{16}$")


@dataclass(frozen=True)
class QualityGate:
    min_precision: float = 0.9
    min_recall: float = 0.8
    max_false_positive_rate: float = 0.05
    min_test_rows: int = 100

    def __post_init__(self):
        values = [self.min_precision, self.min_recall, self.max_false_positive_rate]
        if any(not 0 <= value <= 1 for value in values) or self.min_test_rows < 1:
            raise ValueError("Invalid deployment quality gate")

    def assess(self, report):
        metrics = report.get("test", {})
        requirements = {
            "precision": (self.min_precision, lambda actual, bound: actual >= bound),
            "recall": (self.min_recall, lambda actual, bound: actual >= bound),
            "false_positive_rate": (
                self.max_false_positive_rate,
                lambda actual, bound: actual <= bound,
            ),
            "rows": (self.min_test_rows, lambda actual, bound: actual >= bound),
        }
        failures = []
        for name, (bound, comparison) in requirements.items():
            value = metrics.get(name)
            if type(value) not in {float, int} or not comparison(value, bound):
                failures.append(name)
        return {
            "accepted": not failures,
            "failed_metrics": failures,
            "requirements": {
                "min_precision": self.min_precision,
                "min_recall": self.min_recall,
                "max_false_positive_rate": self.max_false_positive_rate,
                "min_test_rows": self.min_test_rows,
            },
        }


class LocalRegistry:
    def __init__(self, root):
        self.root = reject_symlink_chain(root)

    @staticmethod
    def checked_version(version):
        if not isinstance(version, str) or not VERSION.fullmatch(version):
            raise ValueError("Registry versions must be 16 lowercase hexadecimal characters")
        return version

    def version_dir(self, version):
        return self.root / "versions" / self.checked_version(version)

    def register(self, model_path, report_path):
        model_path = reject_symlink_chain(model_path)
        report = read_json(report_path)
        model = URLModel.load(model_path)
        version = self.checked_version(model.version)
        if report.get("model_version") != version:
            raise ValueError("Model and evaluation report versions do not match")
        model_digest = sha256_file(model_path, 64_000_000)
        destination = self.version_dir(version)
        with exclusive_lock(self.root):
            if destination.exists():
                existing = self.inspect(version)
                if existing["manifest"]["model_sha256"] == model_digest:
                    return {"version": version, "already_registered": True}
                raise ValueError("Version collision with different model bytes")
            destination.mkdir(parents=True, exist_ok=False)
            try:
                atomic_bytes(destination / "model.json", model_path.read_bytes())
                atomic_json(destination / "evaluation.json", report)
                manifest = {
                    "version": version,
                    "model_sha256": model_digest,
                    "evaluation_sha256": sha256_file(destination / "evaluation.json"),
                    "registered_at": datetime.now(timezone.utc).isoformat(),
                    "algorithm": model.algorithm,
                    "query_policy": model.query_policy,
                }
                atomic_json(destination / "manifest.json", manifest)
            except Exception:
                # Preserve a partial directory for diagnosis; it cannot activate without manifest.
                raise
        return {"version": version, "already_registered": False, "manifest": manifest}

    def inspect(self, version):
        folder = self.version_dir(version)
        manifest = read_json(folder / "manifest.json")
        if manifest.get("version") != version:
            raise ValueError("Registry manifest version mismatch")
        if sha256_file(folder / "model.json", 64_000_000) != manifest["model_sha256"]:
            raise ValueError("Registered model checksum mismatch")
        if sha256_file(folder / "evaluation.json") != manifest["evaluation_sha256"]:
            raise ValueError("Registered evaluation checksum mismatch")
        model = URLModel.load(folder / "model.json")
        report = read_json(folder / "evaluation.json")
        if model.version != version or report.get("model_version") != version:
            raise ValueError("Registry artifact identity mismatch")
        return {
            "manifest": manifest,
            "evaluation": report,
            "model_path": str(folder / "model.json"),
        }

    def activate(self, version, gate=None):
        gate = gate or QualityGate()
        with exclusive_lock(self.root):
            entry = self.inspect(version)
            assessment = gate.assess(entry["evaluation"])
            if not assessment["accepted"]:
                raise ValueError("Quality gate rejected: " + ",".join(assessment["failed_metrics"]))
            current = self.root / "active.json"
            previous = read_json(current)["version"] if current.exists() else None
            pointer = {
                "version": version,
                "previous_version": previous,
                "model_sha256": entry["manifest"]["model_sha256"],
                "activated_at": datetime.now(timezone.utc).isoformat(),
                "quality_gate": assessment,
            }
            history = self.root / "history.jsonl"
            reject_symlink_chain(history)
            with history.open("a", encoding="utf-8") as stream:
                stream.write(
                    json.dumps({"event": "activation_prepared", **pointer}, allow_nan=False) + "\n"
                )
                stream.flush()
                import os

                os.fsync(stream.fileno())
            atomic_json(current, pointer, replace=True)
            return pointer

    def active(self):
        pointer = read_json(self.root / "active.json")
        entry = self.inspect(pointer["version"])
        if entry["manifest"]["model_sha256"] != pointer["model_sha256"]:
            raise ValueError("Active pointer does not match registered model")
        return {**entry, "pointer": pointer}

    def list(self):
        directory = self.root / "versions"
        if not directory.exists():
            return []
        result = []
        for path in sorted(directory.iterdir()):
            reject_symlink_chain(path)
            if path.is_dir() and VERSION.fullmatch(path.name):
                try:
                    entry = self.inspect(path.name)
                    result.append(
                        {"version": path.name, "valid": True, "manifest": entry["manifest"]}
                    )
                except (ValueError, FileNotFoundError, KeyError):
                    result.append({"version": path.name, "valid": False})
        return result
