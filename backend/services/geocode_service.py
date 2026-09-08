import os
import json
import logging
from datetime import datetime
from threading import Lock

import requests

logger = logging.getLogger("main")

DATA_DIR = os.getenv("DATA_DIR", "data")
CACHE_FILE = os.path.join(DATA_DIR, "geocode_cache.json")

POSITIONSTACK_FREE_MONTHLY_LIMIT = 100
# Stop calling well under the hard cap — the same city names recur across many job
# postings, so once resolved they're served from cache forever and never count
# against this again. Headroom also covers the check-then-call race below.
POSITIONSTACK_SAFE_MONTHLY_LIMIT = 90

_lock = Lock()


def _load_cache() -> dict:
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {"lookups": {}, "calls_by_month": {}}
    return {"lookups": {}, "calls_by_month": {}}


def _save_cache(data: dict):
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _normalize(location: str) -> str:
    return " ".join(location.split()).strip().lower()


def geocode_timezone(location: str) -> str | None:
    """Backstop for locations the static US-state table in main.py can't resolve
    (city-only postings, multi-timezone states). Calls Positionstack's forward
    geocoding API with the timezone module — but only when POSITIONSTACK_API_KEY is
    set; otherwise this is a silent no-op, same as before this existed.

    A confirmed answer (a real match, or a completed lookup with no US match) is
    cached forever by normalized location string, since the same city names recur
    constantly across job postings. A transient failure (network error, timeout,
    rate limit) is NOT cached — a location must only ever get a definitive answer
    cached, never a temporary hiccup, or a single blip would permanently blacklist
    that location. Calls are hard-capped well under the free tier's 100/month
    limit. The budget check and the network call aren't under the same lock hold
    (the call itself must not block other threads' cache reads), so under
    concurrent misses the safe cap can be overshot by a few calls — acceptable for
    this single-user tool, not worth a reservation system for.
    """
    api_key = os.getenv("POSITIONSTACK_API_KEY")
    if not api_key or not location:
        return None

    key = _normalize(location)
    month = datetime.now().strftime("%Y-%m")

    with _lock:
        data = _load_cache()
        if key in data["lookups"]:
            return data["lookups"][key]
        if data["calls_by_month"].get(month, 0) >= POSITIONSTACK_SAFE_MONTHLY_LIMIT:
            logger.warning(f"Positionstack monthly budget reached, skipping lookup for {location!r}")
            return None

    timezone = None
    lookup_completed = False
    try:
        resp = requests.get(
            "https://api.positionstack.com/v1/forward",
            params={
                "access_key": api_key,
                "query": location,
                # Requesting country=US does NOT reliably restrict results on the free
                # tier (verified live: "Jersey City" still comes back as the Channel
                # Island of Jersey, country_code JEY, even with this set) — so it's sent
                # as a hint, but the country_code check below is the real enforcement.
                "country": "US",
                "limit": 1,
                "timezone_module": 1,
            },
            timeout=4,
        )
        resp.raise_for_status()
        lookup_completed = True  # got a real response — whatever we conclude below is a
                                  # definitive answer for this location, safe to cache forever
        results = resp.json().get("data") or []
        if results:
            top = results[0]
            # the actual safety net against wrong-country matches like "Jersey" for
            # "Jersey City": reject anything not confidently in the US rather than
            # risk showing a wrong timezone
            if top.get("country_code") == "USA" and (top.get("confidence") or 0) >= 0.5:
                timezone = (top.get("timezone_module") or {}).get("name") or None
    except Exception as e:
        logger.warning(f"Positionstack geocode lookup failed for {location!r}: {e}")

    if not lookup_completed:
        return None

    with _lock:
        data = _load_cache()
        data["lookups"][key] = timezone
        data["calls_by_month"][month] = data["calls_by_month"].get(month, 0) + 1
        _save_cache(data)

    return timezone
