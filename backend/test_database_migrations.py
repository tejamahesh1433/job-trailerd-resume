"""
Regression tests for the versioned schema migration system in database.py —
a fresh database must end up fully migrated, and an already-migrated database
must be a no-op re-run (idempotent), since init_db() runs on every startup.
"""
import sqlite3

import database


def test_init_db_creates_schema_version_and_applies_all_migrations(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_FILE", str(tmp_path / "resumes.db"))

    database.init_db()

    conn = sqlite3.connect(database.DB_FILE)
    c = conn.cursor()
    c.execute("SELECT version FROM schema_version")
    version = c.fetchone()[0]
    expected_version = len(database._pending_migrations(0))
    assert version == expected_version

    c.execute("PRAGMA table_info(resumes)")
    columns = {row[1] for row in c.fetchall()}
    assert "vendor_contact_phone" in columns
    conn.close()


def test_init_db_is_idempotent_on_an_already_migrated_database(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_FILE", str(tmp_path / "resumes.db"))

    database.init_db()
    database.init_db()  # simulates a second app startup against the same DB

    conn = sqlite3.connect(database.DB_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM schema_version")
    assert c.fetchone()[0] == 1  # never grows extra rows on repeat startups
    conn.close()
