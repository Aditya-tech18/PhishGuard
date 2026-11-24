from datetime import datetime, timezone, timedelta
from uuid import uuid4
import json
from pathlib import Path
from phishguard.api.prediction_store import PredictionStore
from phishguard.common.schemas import Prediction


def test_retention_and_no_raw_storage(tmp_path):
    path = tmp_path / "db.sqlite"
    store = PredictionStore(path, "s" * 32, 1)
    old = Prediction(
        event_id=uuid4(),
        timestamp=datetime.now(timezone.utc) - timedelta(days=2),
        probability=0.8,
        verdict="phishing",
        model_version="test",
        reasons=[],
    )
    store.add("https://example.com/?password=do-not-store", old)
    assert store.list() == []
    assert "do-not-store" not in path.read_bytes().decode(errors="ignore")
    store.close()


def test_extension_privacy_contract():
    root = Path(__file__).parents[1] / "extension"
    manifest = json.loads((root / "manifest.json").read_text())
    assert manifest["manifest_version"] == 3
    assert set(manifest["permissions"]) == {"activeTab", "storage", "scripting", "alarms"}
    assert "content_scripts" not in manifest
    assert manifest["host_permissions"] == ["http://127.0.0.1:8000/*"]
    assert set(manifest["optional_host_permissions"]) == {"http://*/*", "https://*/*"}
    assert manifest["optional_permissions"] == ["notifications"]
    # Behavioral opt-in, cancellation and screenshot rules are exercised by
    # test_extension_auto.cjs and the real Chromium browser test, not string matching.


def test_storage_is_private_bounded_and_symlink_safe(tmp_path):
    import stat
    import pytest
    from phishguard.common.schemas import Prediction

    path = tmp_path / "bounded.db"
    store = PredictionStore(path, "s" * 32, max_events=2)
    for _ in range(5):
        store.add(
            "https://example.com/",
            Prediction(probability=0.1, verdict="low_risk", model_version="test", reasons=[]),
        )
    assert len(store.list()) == 2
    store.close()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    link = tmp_path / "symlink.db"
    link.symlink_to(path)
    with pytest.raises(ValueError, match="Symlink"):
        PredictionStore(link, "s" * 32)
