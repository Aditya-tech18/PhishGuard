"""Validated runtime settings. Secrets are only obtained from the environment."""

import os
from dataclasses import dataclass
from pathlib import Path
import yaml


def read_yaml(path):
    with Path(path).open(encoding="utf-8") as stream:
        value = yaml.safe_load(stream)
    if not isinstance(value, dict) or value.get("version") != 2:
        raise ValueError("Expected a version: 2 YAML mapping; migrate older settings first")
    return value


def env_bool(name, default=False):
    value = os.getenv(name, str(default)).lower()
    if value not in {"true", "false"}:
        raise ValueError(f"{name} must be true or false")
    return value == "true"


@dataclass(frozen=True)
class Settings:
    api_key: str
    model_path: Path
    db_path: Path
    hmac_key: str = ""
    store_events: bool = False
    retention_days: int = 7
    rate_limit: int = 60
    max_request_bytes: int = 65536
    vision_path: Path | None = None
    max_retained_events: int = 10000
    registry_path: Path | None = None
    body_timeout_seconds: float = 10
    allowed_hosts: tuple[str, ...] = ("127.0.0.1", "localhost", "::1", "testserver")

    def __post_init__(self):
        if not 0.05 <= self.body_timeout_seconds <= 120:
            raise ValueError("Body timeout must be .05..120 seconds")
        if not self.allowed_hosts or any(
            host == "*" or "/" in host or not host for host in self.allowed_hosts
        ):
            raise ValueError("Explicit trusted hostnames are required")
        if len(self.api_key) < 32 or self.api_key.startswith("replace-"):
            raise ValueError("Set PHISHGUARD_API_KEY to at least 32 random characters")
        if self.store_events and (len(self.hmac_key) < 32 or self.hmac_key == self.api_key):
            raise ValueError("Event storage requires a separate 32-character HMAC key")
        if not 1 <= self.max_retained_events <= 1000000:
            raise ValueError("Invalid retained event limit")
        if not 1 <= self.retention_days <= 30:
            raise ValueError("Retention must be between 1 and 30 days")
        if not 1 <= self.rate_limit <= 10000:
            raise ValueError("Invalid rate limit")
        if not 1024 <= self.max_request_bytes <= 8000000:
            raise ValueError("Invalid request limit")

    @classmethod
    def from_env(cls):
        vision = os.getenv("PHISHGUARD_VISION_MODEL")
        return cls(
            api_key=os.getenv("PHISHGUARD_API_KEY", ""),
            model_path=Path(os.getenv("PHISHGUARD_MODEL", "models/trained/url-model.json")),
            db_path=Path(os.getenv("PHISHGUARD_DB", "data/predictions.db")),
            hmac_key=os.getenv("PHISHGUARD_HMAC_KEY", ""),
            store_events=env_bool("PHISHGUARD_STORE_EVENTS"),
            retention_days=int(os.getenv("PHISHGUARD_RETENTION_DAYS", "7")),
            max_retained_events=int(os.getenv("PHISHGUARD_MAX_RETAINED_EVENTS", "10000")),
            rate_limit=int(os.getenv("PHISHGUARD_RATE_LIMIT", "60")),
            max_request_bytes=int(
                os.getenv("PHISHGUARD_MAX_REQUEST_BYTES", "8000000" if vision else "65536")
            ),
            vision_path=Path(vision) if vision else None,
            registry_path=Path(os.environ["PHISHGUARD_REGISTRY"])
            if os.getenv("PHISHGUARD_REGISTRY")
            else None,
            body_timeout_seconds=float(os.getenv("PHISHGUARD_BODY_TIMEOUT_SECONDS", "10")),
            allowed_hosts=tuple(
                host.strip()
                for host in os.getenv("PHISHGUARD_ALLOWED_HOSTS", "127.0.0.1,localhost,::1").split(
                    ","
                )
            ),
        )
