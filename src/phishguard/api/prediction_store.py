"""Optional minimized SQLite event store. Never stores raw URL, query, image or API key."""

import hashlib
import hmac
import sqlite3
import threading
from pathlib import Path
from datetime import datetime, timezone, timedelta


class PredictionStore:
    def __init__(self, path, secret, retention_days=7, max_events=10000):
        if len(secret) < 32:
            raise ValueError("A 32-character HMAC secret is required")
        import os
        from phishguard.common.files import reject_symlink_chain

        path = reject_symlink_chain(Path(path))
        if not 1 <= max_events <= 1000000:
            raise ValueError("Invalid retained event limit")
        self.max_events = max_events
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(descriptor)
        os.chmod(path, 0o600)
        self.secret = secret.encode()
        self.retention_days = retention_days
        self.lock = threading.Lock()
        self.connection = sqlite3.connect(str(path), check_same_thread=False)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA secure_delete=ON")
        self.connection.execute("PRAGMA busy_timeout=5000")
        self.connection.execute("""CREATE TABLE IF NOT EXISTS events (
            event_id TEXT PRIMARY KEY, timestamp TEXT NOT NULL, url_hash TEXT NOT NULL,
            probability REAL NOT NULL, verdict TEXT NOT NULL, model_version TEXT NOT NULL)""")
        self.connection.execute("CREATE INDEX IF NOT EXISTS event_time ON events(timestamp)")
        self.connection.commit()
        self.purge()

    def add(self, url, prediction):
        digest = hmac.new(self.secret, url.encode(), hashlib.sha256).hexdigest()
        with self.lock, self.connection:
            self.connection.execute(
                "INSERT OR IGNORE INTO events VALUES (?, ?, ?, ?, ?, ?)",
                (
                    str(prediction.event_id),
                    prediction.timestamp.isoformat(),
                    digest,
                    prediction.probability,
                    prediction.verdict,
                    prediction.model_version,
                ),
            )
        self.purge()

    def purge(self):
        cutoff = (datetime.now(timezone.utc) - timedelta(days=self.retention_days)).isoformat()
        with self.lock, self.connection:
            self.connection.execute("DELETE FROM events WHERE timestamp < ?", (cutoff,))
            self.connection.execute(
                "DELETE FROM events WHERE event_id IN (SELECT event_id FROM events "
                "ORDER BY timestamp DESC LIMIT -1 OFFSET ?)",
                (self.max_events,),
            )

    def list(self, limit=100):
        if not 1 <= limit <= 1000:
            raise ValueError("Invalid limit")
        self.purge()
        with self.lock:
            cursor = self.connection.execute(
                "SELECT event_id, timestamp, probability, verdict, "
                "model_version FROM events ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]

    def metrics(self):
        self.purge()
        with self.lock:
            total, high = self.connection.execute(
                "SELECT count(*), coalesce(sum(verdict = 'phishing'), 0) FROM events"
            ).fetchone()
        return {"retained_predictions": total, "phishing_predictions": high}

    def clear(self):
        with self.lock, self.connection:
            self.connection.execute("DELETE FROM events")
        # SQLite WAL may retain deleted pages until checkpoint; disk is not secure erasure.
        with self.lock:
            self.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def close(self):
        with self.lock:
            self.connection.close()
