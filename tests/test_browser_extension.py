"""Run the real isolated Chromium auto-scan suite. No personal profile or live sites."""

import os
from pathlib import Path
import shutil
import subprocess

import pytest

pytestmark = pytest.mark.browser


def test_actual_automatic_navigation_warnings_and_off_cancellation():
    if os.getenv("PHISHGUARD_TEST_BROWSER") != "true":
        pytest.skip("Explicit isolated-browser opt-in required")
    if shutil.which("node") is None:
        pytest.fail("Install Node.js 22+ and run npm ci --prefix tests/browser")
    script = Path(__file__).with_name("browser_auto.cjs")
    result = subprocess.run(
        ["node", str(script)], capture_output=True, text=True, timeout=180, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
