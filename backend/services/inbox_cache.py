import os
import json
import hashlib

DATA_DIR = os.getenv("DATA_DIR", "data")
CACHE_FILE = os.path.join(DATA_DIR, "inbox_classify_cache.json")
MAX_CACHE_ENTRIES = 3000


def _content_hash(subject: str, snippet: str) -> str:
    return hashlib.md5(f"{subject}|{snippet}".encode("utf-8", errors="ignore")).hexdigest()


def _load() -> dict:
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save(cache: dict):
    if len(cache) > MAX_CACHE_ENTRIES:
        # dicts preserve insertion order in py3.7+ — keep the most-recently-written tail
        cache = dict(list(cache.items())[-MAX_CACHE_ENTRIES:])
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f)


def split_cached(messages: list):
    """Split a message list into (cached_categories, uncached_messages). cached_categories
    is {message_id: category_key} for anything already classified with unchanged
    subject/snippet content (a re-labeled/edited thread invalidates its own cache entry
    via the content hash). uncached_messages still needs an AI call."""
    cache = _load()
    cached_categories = {}
    uncached = []
    for m in messages:
        h = _content_hash(m.get("subject", ""), m.get("snippet", ""))
        entry = cache.get(m["id"])
        if entry and entry.get("hash") == h:
            cached_categories[m["id"]] = entry["category"]
        else:
            uncached.append(m)
    return cached_categories, uncached


def store(messages: list, categories: dict):
    """Persist freshly-classified results. messages: the list that was just sent to AI;
    categories: {message_id: category_key} returned for (a subset of) them."""
    if not categories:
        return
    cache = _load()
    for m in messages:
        cat = categories.get(m["id"])
        if not cat:
            continue
        cache[m["id"]] = {"hash": _content_hash(m.get("subject", ""), m.get("snippet", "")), "category": cat}
    _save(cache)
