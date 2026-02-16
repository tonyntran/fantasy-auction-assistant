"""
Append-only event log for crash recovery and draft replay.

Each line in the log file is a JSON object:
  {"seq": int, "ts": float, "type": "draft_update"|"manual", "payload": {...}}

On server restart, events are replayed to reconstruct draft state.
"""

import json
import time
from pathlib import Path
from typing import Optional


class EventStore:
    """Singleton append-only event log."""

    _instance: Optional["EventStore"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._path: Optional[Path] = None
        self._seq: int = 0
        self._file = None

    def open(self, path: str):
        """Open (or create) the event log file. Resumes sequence numbering."""
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if self._path.exists():
            with open(self._path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        self._seq += 1
        self._file = open(self._path, "a", encoding="utf-8")

    def append(self, event_type: str, payload: dict):
        """Append an event to the log. Flushes immediately for durability."""
        if not self._file:
            return
        self._seq += 1
        record = {
            "seq": self._seq,
            "ts": time.time(),
            "type": event_type,
            "payload": payload,
        }
        self._file.write(json.dumps(record, default=str) + "\n")
        self._file.flush()

    def replay(self) -> list[dict]:
        """Read all events from disk, sorted by sequence number."""
        if not self._path or not self._path.exists():
            return []
        events = []
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return sorted(events, key=lambda e: e.get("seq", 0))

    def clear(self):
        """Clear the event log (for testing or fresh draft)."""
        if self._file:
            self._file.close()
        if self._path and self._path.exists():
            self._path.unlink()
        self._seq = 0
        if self._path:
            self._file = open(self._path, "a", encoding="utf-8")

    def close(self):
        """Close the file handle."""
        if self._file:
            self._file.close()
            self._file = None
