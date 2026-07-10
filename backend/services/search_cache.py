"""Small cache for Command Center searches that found nothing usable.

This deliberately caches only empty outcomes, so a successful search can still refresh
normally while repeated strict-filter misses do not spend another external search call.
"""

import hashlib
import json
import os
import time
from typing import Any


DATA_DIR = os.getenv("DATA_DIR", "data")
CACHE_FILE = os.path.join(DATA_DIR, "command_center_empty_search_cache.json")
TTL_SECONDS = int(os.getenv("COMMAND_CENTER_EMPTY_SEARCH_CACHE_SECONDS", str(6 * 60 * 60)))
SEARCH_STRATEGY_VERSION = "jsearch-targeted-contract-v2"


def make_key(query: str, platforms: list[str], work_types: list[str], contract_types: list[str]) -> str:
    payload = {
        "strategy_version": SEARCH_STRATEGY_VERSION,
        "query": (query or "").strip().lower(),
        "platforms": sorted((p or "").strip().lower() for p in (platforms or []) if p),
        "work_types": sorted((w or "").strip().lower() for w in (work_types or []) if w),
        "contract_types": sorted((c or "").strip().lower() for c in (contract_types or []) if c),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _load() -> dict[str, Any]:
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save(cache: dict[str, Any]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp_file = f"{CACHE_FILE}.tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)
    os.replace(tmp_file, CACHE_FILE)


def get_recent(key: str) -> dict[str, Any] | None:
    cache = _load()
    entry = cache.get(key)
    if not isinstance(entry, dict):
        return None

    created_at = float(entry.get("created_at") or 0)
    age = int(time.time() - created_at)
    if age < 0 or age > TTL_SECONDS:
        cache.pop(key, None)
        try:
            _save(cache)
        except Exception:
            pass
        return None

    result = dict(entry.get("result") or {})
    result["cached"] = True
    result["api_spent"] = False
    result["cache_age_seconds"] = age
    base_message = result.get("message") or "No usable postings found for this search."
    result["message"] = f"{base_message} Same filters were checked recently, so no new external search was spent."
    return result


def store_empty(key: str, result: dict[str, Any]) -> None:
    if int(result.get("count") or 0) != 0:
        return

    cache = _load()
    stored = dict(result)
    stored["cached"] = False
    stored["api_spent"] = True
    cache[key] = {
        "created_at": time.time(),
        "result": stored,
    }
    _save(cache)
