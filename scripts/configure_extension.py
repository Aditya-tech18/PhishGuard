#!/usr/bin/env python3
"""Create a separate extension build restricted to one explicitly chosen HTTPS origin."""

import argparse
import json
import shutil
from pathlib import Path
from urllib.parse import urlsplit


def configure(source, origin, output):
    parsed = urlsplit(origin)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or parsed.port not in {None, 443}
        or any(c.isspace() for c in origin)
        or "\\" in origin
    ):
        raise ValueError(
            "Use one exact HTTPS deployment origin without path, credentials, query or fragment"
        )
    import ipaddress

    try:
        ipaddress.ip_address(parsed.hostname)
    except ValueError:
        from phishguard.features.url_features import normalize_url

        canonical = urlsplit(normalize_url(origin)).netloc
    else:
        raise ValueError("Use an HTTPS DNS deployment hostname")
    origin = "https://" + canonical
    source = Path(source).resolve(strict=True)
    output = Path(output).absolute()
    if output.exists() or source in output.parents:
        raise ValueError("Choose a new separate extension output folder")
    allowed = [
        "background.js",
        "dashboard-bridge.js",
        "connect.html",
        "scan-core.js",
        "page-warning.js",
        "icon128.png",
        "popup.js",
        "popup.html",
        "popup.css",
        "warning.js",
        "warning.html",
        "manifest.json",
    ]
    if any((source / name).is_symlink() for name in allowed):
        raise ValueError("Extension source symlinks are forbidden")
    manifest = json.loads((source / "manifest.json").read_text())
    manifest["host_permissions"] = [origin + "/*"]
    manifest["name"] = "PhishGuard Cloud"
    manifest["externally_connectable"] = {"matches": [origin + "/*"]}
    background = (source / "background.js").read_text()
    original = 'const API = "http://127.0.0.1:8000";'
    if background.count(original) != 1:
        raise ValueError("Unexpected extension API declaration")
    background = background.replace(original, "const API = " + json.dumps(origin) + ";")
    output.mkdir(parents=True)
    for name in allowed:
        shutil.copyfile(source / name, output / name)
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (output / "background.js").write_text(background)
    return {
        "origin": origin,
        "host_permissions": manifest["host_permissions"],
        "screenshot_model": "cloud URL profile has no image inference; disabled capability checked before capture",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, default=Path(__file__).resolve().parents[1] / "extension"
    )
    parser.add_argument("--origin", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(configure(args.source, args.origin, args.output), indent=2))
