"""
Failure-path tests for Gmail OAuth token handling — an expired token whose refresh
fails (revoked/expired refresh_token), and a corrupted tokens file, must both surface
as {"connected": False} rather than raising through to the caller.
"""
import json
from unittest.mock import MagicMock, patch

from google.auth.exceptions import RefreshError

from services import gmail_service


def test_status_when_no_tokens_file(client, tmp_path, monkeypatch):
    monkeypatch.setattr(gmail_service, "TOKENS_FILE", str(tmp_path / "gmail_tokens.json"))
    resp = client.get("/api/gmail/status")
    assert resp.status_code == 200
    assert resp.json() == {"connected": False}


def test_status_when_refresh_token_is_revoked(client, tmp_path, monkeypatch):
    tokens_file = tmp_path / "gmail_tokens.json"
    tokens_file.write_text(json.dumps({
        "token": "expired-access-token",
        "refresh_token": "revoked-refresh-token",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "test-client-id",
        "client_secret": "test-client-secret",
        "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
    }))
    monkeypatch.setattr(gmail_service, "TOKENS_FILE", str(tokens_file))

    fake_creds = MagicMock()
    fake_creds.valid = False
    fake_creds.expired = True
    fake_creds.refresh_token = "revoked-refresh-token"
    fake_creds.refresh.side_effect = RefreshError("invalid_grant: Token has been expired or revoked.")

    with patch.object(gmail_service, "_load_credentials", return_value=fake_creds):
        resp = client.get("/api/gmail/status")

    assert resp.status_code == 200
    assert resp.json() == {"connected": False}


def test_status_when_tokens_file_is_corrupted(client, tmp_path, monkeypatch):
    tokens_file = tmp_path / "gmail_tokens.json"
    tokens_file.write_text("{not valid json")
    monkeypatch.setattr(gmail_service, "TOKENS_FILE", str(tokens_file))

    resp = client.get("/api/gmail/status")
    assert resp.status_code == 200
    assert resp.json() == {"connected": False}


def test_auth_url_fails_cleanly_without_oauth_client_configured(client, monkeypatch):
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    resp = client.get("/api/gmail/auth")
    assert resp.status_code == 400
