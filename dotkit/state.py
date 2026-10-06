"""Persistent bookkeeping in ``~/.local/state/dotfiles/state.json``.

It records which one-time tasks ran (and with which config fingerprint) and what the
installer created, so later runs can undo exactly that when the config changes.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_VERSION = 1


class State:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._data: dict[str, Any] = {"version": _VERSION, "once": {}}
        if path.exists():
            loaded = json.loads(path.read_text())
            if loaded.get("version") != _VERSION:
                raise ValueError(f"{path}: unsupported state version {loaded.get('version')!r}")
            self._data = loaded

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def put(self, key: str, value: Any) -> None:
        self._data[key] = value

    def once_record(self, task: str) -> dict[str, str] | None:
        return self._data["once"].get(task)

    def mark_once(self, task: str, fingerprint: str) -> None:
        now = datetime.now(UTC).isoformat(timespec="seconds")
        self._data["once"][task] = {"fingerprint": fingerprint, "at": now}

    def save(self) -> None:
        """Write atomically so an interrupted run never leaves a corrupt file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".state-")
        with os.fdopen(fd, "w") as fh:
            json.dump(self._data, fh, indent=2, sort_keys=True)
            fh.write("\n")
        Path(tmp).replace(self.path)


def fingerprint(data: Any) -> str:
    """Stable short hash of any JSON-serialisable value."""
    blob = json.dumps(data, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()[:16]
