"""
Failure-path tests for POST /api/job-matcher/fetch-url (the JD-from-URL scraper) and
POST /api/job-matcher/analyze — network/HTTP failures must surface as a clean 400 with
a readable message, never a raw traceback, and never a real outbound request in CI.
"""
from unittest.mock import patch, MagicMock

import requests


def _fake_response(status_code):
    resp = MagicMock()
    resp.status_code = status_code
    resp.raise_for_status.side_effect = requests.exceptions.HTTPError(
        f"{status_code} Client Error", response=resp
    )
    return resp


def test_fetch_url_rejects_non_http_scheme(client):
    resp = client.post("/api/job-matcher/fetch-url", data={"url": "not-a-url"})
    assert resp.status_code == 400
    assert "Invalid URL" in resp.json()["detail"]


def test_fetch_url_handles_404(client):
    with patch("requests.get", return_value=_fake_response(404)):
        resp = client.post(
            "/api/job-matcher/fetch-url",
            data={"url": "https://example.com/jobs/expired-posting"},
        )
    assert resp.status_code == 400
    assert "404" in resp.json()["detail"] or "expired" in resp.json()["detail"].lower()


def test_fetch_url_handles_403_bot_block(client):
    with patch("requests.get", return_value=_fake_response(403)):
        resp = client.post(
            "/api/job-matcher/fetch-url",
            data={"url": "https://example.com/jobs/blocked"},
        )
    assert resp.status_code == 400
    assert "blocked" in resp.json()["detail"].lower()


def test_fetch_url_handles_timeout(client):
    with patch("requests.get", side_effect=requests.exceptions.Timeout("timed out")):
        resp = client.post(
            "/api/job-matcher/fetch-url",
            data={"url": "https://example.com/jobs/slow"},
        )
    assert resp.status_code == 400
    assert "timed out" in resp.json()["detail"].lower() or "timeout" in resp.json()["detail"].lower()


def test_fetch_url_handles_connection_error(client):
    with patch("requests.get", side_effect=requests.exceptions.ConnectionError("refused")):
        resp = client.post(
            "/api/job-matcher/fetch-url",
            data={"url": "https://nonexistent.example.invalid/jobs/1"},
        )
    assert resp.status_code == 400


def test_analyze_rejects_too_short_jd(client):
    resp = client.post("/api/job-matcher/analyze", data={"jd_text": "too short"})
    assert resp.status_code == 400
    assert "too short" in resp.json()["detail"].lower()
