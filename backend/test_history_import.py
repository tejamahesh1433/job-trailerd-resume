import csv
import io
import sqlite3

import pytest
import database
from services.history_import import import_applications_csv


@pytest.fixture(autouse=True)
def isolated_history(tmp_path, monkeypatch):
    monkeypatch.setattr(database, 'DB_FILE', str(tmp_path / 'history.db'))
    database.init_db()


def make_csv(rows):
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode('utf-8-sig')


def test_preserves_multiline_details_and_skips_reimport():
    data = make_csv([{'Company': 'Acme', 'JD': 'Build, deploy\nMaintain systems', 'Date': '2026-09-22', 'Time': '10:50 AM EDT', 'Status': 'Applied', 'Role': 'Engineer', 'Job URL': 'https://example.com/job/1', 'LinkedIn Profile': 'https://linkedin.com/in/recruiter', 'Vendor Details': 'Recruiter: Jane Doe, contact jane@example.com'}])
    assert import_applications_csv(data)['imported'] == 1
    assert import_applications_csv(data)['skipped'] == 1
    with sqlite3.connect(database.DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute('SELECT * FROM resumes').fetchone()
        assert row['jd_text'] == 'Build, deploy\nMaintain systems'
        assert row['created_at'] == '2026-09-22T10:50:00-04:00'
        assert row['vendor_contact_email'] == 'jane@example.com'
        assert row['vendor_contact_name'] == 'Jane Doe'
        assert 'Role: Engineer' in row['user_notes']
        assert 'https://linkedin.com/in/recruiter' in row['user_notes']


def test_invalid_rows_reported_and_duplicates_within_file_skipped():
    data = make_csv([{'Company': 'Acme', 'Status': 'Applied'}, {'Company': '', 'Status': 'Applied'}, {'Company': 'Other', 'Status': 'Invalid'}, {'Company': 'Acme', 'Status': 'Applied'}])
    result = import_applications_csv(data)
    assert (result['imported'], result['skipped'], result['failed']) == (1, 1, 2)
    assert [e['row'] for e in result['errors']] == [3, 4]


@pytest.mark.parametrize('data', [b'Role\nEngineer', b'Company\n', b'Company,Company\na,b', b'Company\n"unclosed', b'Company\n\xff'])
def test_invalid_files_do_not_write(data):
    with pytest.raises(ValueError):
        import_applications_csv(data)
    with sqlite3.connect(database.DB_FILE) as conn:
        assert conn.execute('SELECT COUNT(*) FROM resumes').fetchone()[0] == 0


def test_upload_endpoint(client):
    response = client.post('/api/history/import', files={'file': ('applications.csv', b'Company,Status\nAcme,Applied', 'text/csv')})
    assert response.status_code == 200
    assert response.json()['imported'] == 1
    response = client.post('/api/history/import', files={'file': ('bad.csv', b'Role\nEngineer', 'text/csv')})
    assert response.status_code == 400
