#!/usr/bin/env python3
"""Read-only project readiness checks. No installation, data mutation or secret printing."""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from phishguard.ml.model_registry import URLModel


def check(model, full=False, api_mode=False, vision_model=None):
    checks = []

    def add(name, status, detail):
        checks.append({"name": name, "status": status, "detail": detail})

    supported = (3, 11) <= sys.version_info[:2] < (3, 14)
    add("python", "pass" if supported else "fail", ".".join(map(str, sys.version_info[:3])))
    for module in ["numpy", "pydantic", "yaml", "fastapi", "uvicorn", "httpx", "streamlit"]:
        present = importlib.util.find_spec(module) is not None
        add(
            module,
            "pass" if present else "fail",
            "installed" if present else "install API/dashboard extras",
        )
    try:
        artifact = URLModel.load(model)
        result = artifact.predict("https://example.com/")
        add("url_model", "pass", f"{artifact.algorithm}, version {result['model_version']}")
    except (OSError, ValueError, TypeError, KeyError):
        add("url_model", "fail", "missing, malformed or incompatible numeric artifact")
    if vision_model is not None:
        try:
            from phishguard.ml.vision import VisionModel

            vision = VisionModel(vision_model)
            add("vision_model", "pass", vision.version)
        except (OSError, ValueError, RuntimeError, ImportError):
            add("vision_model", "fail", "missing or incompatible screenshot model")
    if api_mode:
        from phishguard.common.config import Settings

        try:
            Settings.from_env()
            add(
                "api_configuration",
                "pass",
                "environment settings validated without exposing values",
            )
        except (ValueError, TypeError):
            add(
                "api_configuration", "fail", "check required key, retention, host and size settings"
            )
    else:
        add("session_key", "pass", "launch command creates a fresh private session key")
    if full:
        for module in ["pyspark", "confluent_kafka", "torch", "PIL"]:
            present = importlib.util.find_spec(module) is not None
            add(
                module,
                "pass" if present else "fail",
                "installed" if present else "install optional full-stack extras",
            )
        home = os.getenv("JAVA_HOME")
        java = str(Path(home) / "bin/java") if home else shutil.which("java")
        if java:
            try:
                version = subprocess.run(
                    [java, "-version"], capture_output=True, text=True, timeout=10
                )
                match = re.search(r'version "(\d+)', version.stderr + version.stdout)
                major = int(match.group(1)) if match else None
                add(
                    "java",
                    "pass" if major == 17 else "warn",
                    "Java 17 selected"
                    if major == 17
                    else "select Java 17 for Spark with JAVA_HOME",
                )
            except (OSError, subprocess.TimeoutExpired):
                add("java", "fail", "Java executable could not be inspected")
        else:
            add("java", "fail", "Java 17 is required for Spark tests")
    return {
        "ready": not any(item["status"] == "fail" for item in checks),
        "checks": checks,
        "scope": "local prerequisites; broker/cloud availability not probed",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=Path("models/trained/url-model.json"))
    parser.add_argument("--vision-model", type=Path)
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--api-mode", action="store_true")
    args = parser.parse_args()
    report = check(args.model, args.full, args.api_mode, args.vision_model)
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["ready"] else 1)
