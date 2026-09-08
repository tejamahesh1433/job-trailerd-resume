"""
Positionstack geocoding backstop (services/geocode_service.py) — must stay a true
no-op without an API key, must never re-call the API for a location it has already
definitively resolved (or definitively failed to resolve), must stop calling once
the free tier's monthly budget is used up, and — per a real bug caught live-testing
this feature ("Jersey City" resolving to the Channel Island of Jersey instead of
Jersey City, NJ, because Positionstack's free-tier `country` filter doesn't reliably
restrict results) — must reject any match that isn't confidently in the US rather
than ever hand back a wrong timezone.
"""
import json
import os
from unittest.mock import patch, MagicMock

import pytest

from services import geocode_service


@pytest.fixture()
def cache_file(tmp_path, monkeypatch):
    path = str(tmp_path / "geocode_cache.json")
    monkeypatch.setattr(geocode_service, "CACHE_FILE", path)
    return path


def _fake_response(timezone_name="America/New_York", has_results=True, country_code="USA", confidence=1):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {
        "data": [{
            "country_code": country_code,
            "confidence": confidence,
            "timezone_module": {"name": timezone_name},
        }] if has_results else []
    }
    return resp


def test_returns_none_without_api_key_and_makes_no_network_call(cache_file, monkeypatch):
    monkeypatch.delenv("POSITIONSTACK_API_KEY", raising=False)
    with patch("services.geocode_service.requests.get") as mock_get:
        result = geocode_service.geocode_timezone("Jersey City")
    assert result is None
    mock_get.assert_not_called()


def test_successful_lookup_is_cached_and_not_called_twice(cache_file, monkeypatch):
    monkeypatch.setenv("POSITIONSTACK_API_KEY", "test-key")
    with patch("services.geocode_service.requests.get", return_value=_fake_response("America/Chicago")) as mock_get:
        first = geocode_service.geocode_timezone("Jersey City")
        second = geocode_service.geocode_timezone("  jersey city  ")  # same place, different casing/whitespace

    assert first == "America/Chicago"
    assert second == "America/Chicago"
    mock_get.assert_called_once()


def test_failed_lookup_is_cached_as_none_and_not_retried(cache_file, monkeypatch):
    monkeypatch.setenv("POSITIONSTACK_API_KEY", "test-key")
    with patch("services.geocode_service.requests.get", return_value=_fake_response(has_results=False)) as mock_get:
        first = geocode_service.geocode_timezone("Nowhereville")
        second = geocode_service.geocode_timezone("Nowhereville")

    assert first is None
    assert second is None
    mock_get.assert_called_once()


def test_stops_calling_once_monthly_budget_is_reached(cache_file, monkeypatch):
    from datetime import datetime
    monkeypatch.setenv("POSITIONSTACK_API_KEY", "test-key")

    month = datetime.now().strftime("%Y-%m")
    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
    with open(cache_file, "w") as f:
        json.dump({"lookups": {}, "calls_by_month": {month: geocode_service.POSITIONSTACK_SAFE_MONTHLY_LIMIT}}, f)

    with patch("services.geocode_service.requests.get") as mock_get:
        result = geocode_service.geocode_timezone("Some New City")

    assert result is None
    mock_get.assert_not_called()


def test_network_error_returns_none_without_raising(cache_file, monkeypatch):
    monkeypatch.setenv("POSITIONSTACK_API_KEY", "test-key")
    with patch("services.geocode_service.requests.get", side_effect=Exception("timeout")):
        result = geocode_service.geocode_timezone("Somewhere")
    assert result is None


def test_transient_failure_is_not_cached_and_is_retried_next_time(cache_file, monkeypatch):
    """A network error / timeout / rate limit (429) must NOT permanently blacklist
    a location — only a completed lookup is a definitive, cacheable answer."""
    monkeypatch.setenv("POSITIONSTACK_API_KEY", "test-key")
    with patch("services.geocode_service.requests.get", side_effect=Exception("429 rate limited")) as mock_get:
        geocode_service.geocode_timezone("Chicago")
        geocode_service.geocode_timezone("Chicago")
    assert mock_get.call_count == 2  # not short-circuited by a cached failure


def test_rejects_wrong_country_match_even_with_high_confidence(cache_file, monkeypatch):
    """Regression test for the live-caught bug: 'Jersey City' matched the Channel
    Island of Jersey (country_code JEY) at confidence 1.0. A non-US match must
    never be surfaced as a timezone, no matter how confident Positionstack is."""
    monkeypatch.setenv("POSITIONSTACK_API_KEY", "test-key")
    bad_match = _fake_response(timezone_name="Europe/Jersey", country_code="JEY", confidence=1)
    with patch("services.geocode_service.requests.get", return_value=bad_match) as mock_get:
        first = geocode_service.geocode_timezone("Jersey City")
        second = geocode_service.geocode_timezone("Jersey City")

    assert first is None
    assert second is None
    # this IS a definitive (if negative) answer, so it should be cached — not retried
    mock_get.assert_called_once()


def test_rejects_low_confidence_us_match(cache_file, monkeypatch):
    monkeypatch.setenv("POSITIONSTACK_API_KEY", "test-key")
    weak_match = _fake_response(timezone_name="America/Denver", country_code="USA", confidence=0.2)
    with patch("services.geocode_service.requests.get", return_value=weak_match):
        result = geocode_service.geocode_timezone("Some Ambiguous Place")
    assert result is None
