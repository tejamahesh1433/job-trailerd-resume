"""
Shared pytest setup for the backend test suite.

`main.py` validates required env vars and calls init_db() at *import* time (not inside
a FastAPI startup hook), and reads ALLOWED_HOSTS/DATA_DIR/etc. at module load too. So
everything here has to run before any test module does `import main`, which is why it
lives in conftest.py (pytest loads it before collecting test files) rather than a
fixture. Values use setdefault() so a developer's real .env is never overridden. Sets
GOOGLE_CLIENT_ID/SECRET so gmail_service can build a client config without touching the
real one, and RAPIDAPI_KEY/ANTHROPIC_API_KEY so nothing accidentally no-ops for a
different reason than the one under test.
"""
import os
import tempfile

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="trailerd_pytest_data_"))
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
os.environ.setdefault("RAPIDAPI_KEY", "test-rapidapi-key")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-client-id")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test-client-secret")

import pytest
from fastapi.testclient import TestClient

import main as main_module


@pytest.fixture(scope="session")
def app():
    return main_module.app


@pytest.fixture()
def client(app):
    # base_url host must be one of ALLOWED_HOSTS (default localhost,127.0.0.1) —
    # TestClient's default "testserver" host would otherwise get a 400 from
    # TrustedHostMiddleware before the request ever reaches a route.
    return TestClient(app, base_url="http://localhost")
