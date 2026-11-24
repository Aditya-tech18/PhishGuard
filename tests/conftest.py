import importlib.util
import json
from pathlib import Path
import pytest
from phishguard.features.feature_schema import FEATURE_NAMES, SCHEMA_HASH


@pytest.fixture
def model_path(tmp_path):
    path = tmp_path / "model.json"
    n = len(FEATURE_NAMES)
    path.write_text(
        json.dumps(
            {
                "format": "phishguard-logistic-v1",
                "schema_hash": SCHEMA_HASH,
                "features": list(FEATURE_NAMES),
                "version": "test-only-zero-model",
                "threshold": 0.5,
                "mean": [0] * n,
                "scale": [1] * n,
                "weights": [0] * n,
                "bias": 0,
            }
        )
    )
    return path


@pytest.fixture
def demo_csv(tmp_path):
    script = Path(__file__).parents[1] / "scripts/generate_demo.py"
    spec = importlib.util.spec_from_file_location("demo", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.generate(tmp_path / "demo.csv")
