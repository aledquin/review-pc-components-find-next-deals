"""Tiny in-memory + SQLite-backed HTTP cache with per-source TTL.

For MVP we keep the cache interface small: ``get(key)`` and
``set(key, value, ttl_seconds)``. The file-backed tier is a single JSON
document inside the cache directory; SQLite will replace it in Wave 3 when
concurrent access becomes an issue.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from pca.core.config import get_settings


class Cache:
    def __init__(self, namespace: str) -> None:
        self._namespace = namespace
        self._mem: dict[str, tuple[float, Any]] = {}
        self._file: Path | None = None

    def _ensure_file(self) -> Path:
        if self._file is None:
            cache_dir = get_settings().resolved_cache_dir()
            cache_dir.mkdir(parents=True, exist_ok=True)
            self._file = cache_dir / f"{self._namespace}.json"
            if not self._file.exists():
                self._file.write_text("{}", encoding="utf-8")
        return self._file

    def get(self, key: str) -> Any | None:
        now = time.time()
        if key in self._mem:
            expires, value = self._mem[key]
            if expires > now:
                return value
            del self._mem[key]

        path = self._ensure_file()
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            blob = {}
        entry = blob.get(key)
        if entry and entry["expires"] > now:
            self._mem[key] = (entry["expires"], entry["value"])
            return entry["value"]
        return None

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        expires = time.time() + max(0, ttl_seconds)
        self._mem[key] = (expires, value)

        path = self._ensure_file()
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            blob = {}
        blob[key] = {"expires": expires, "value": value}
        path.write_text(json.dumps(blob), encoding="utf-8")

    def clear(self) -> None:
        self._mem.clear()
        if self._file and self._file.exists():
            self._file.write_text("{}", encoding="utf-8")
