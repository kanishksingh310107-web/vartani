"""Small persistent store for reusable benchmark suites."""
from __future__ import annotations
import json
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from .config import DATA_DIR

STORE = DATA_DIR / "user" / "suites.json"
_LOCK = threading.RLock()


def _read() -> list:
    if not STORE.exists():
        return []
    try:
        value = json.loads(STORE.read_text(encoding="utf-8"))
        return value if isinstance(value, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _write(suites: list) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STORE.with_suffix(".tmp")
    tmp.write_text(json.dumps(suites, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(STORE)


def list_suites() -> list:
    with _LOCK:
        return [{k: s[k] for k in ("id", "name", "created", "n_items", "langs")} for s in _read()]


def save_suite(name: str, items: list, config: Optional[dict] = None) -> dict:
    if not isinstance(items, list) or not items:
        raise ValueError("A benchmark suite needs at least one valid question.")
    if len(items) > 5000:
        raise ValueError("A suite can contain up to 5,000 questions.")
    if any(not isinstance(row, dict) for row in items):
        raise ValueError("Every question must be a valid dataset row.")
    with _LOCK:
        suites = _read()
        clean_name = (name or "").strip()[:100] or "Saved benchmark"
        suite = {"id": uuid.uuid4().hex[:10], "name": clean_name,
             "created": time.time(), "n_items": len(items),
             "langs": sorted({str(i.get("lang", "?")) for i in items}),
             "items": items, "config": config or {}}
        suites.insert(0, suite)
        _write(suites[:100])
        return {k: suite[k] for k in ("id", "name", "created", "n_items", "langs")}


def get_suite(sid: str) -> Optional[dict]:
    with _LOCK:
        return next((s for s in _read() if s.get("id") == sid), None)


def delete_suite(sid: str) -> bool:
    with _LOCK:
        suites = _read()
        updated = [s for s in suites if s.get("id") != sid]
        if len(updated) == len(suites):
            return False
        _write(updated)
        return True
