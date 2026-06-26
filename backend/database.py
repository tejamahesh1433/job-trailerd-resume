import sqlite3
from datetime import datetime
import os

DATA_DIR = os.getenv("DATA_DIR", "data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_FILE = os.path.join(DATA_DIR, "resumes.db")

def sanitize_csv_field(field: str) -> str:
    """Prevent CSV injection attacks by prefixing dangerous characters with single quote."""
    if isinstance(field, str) and field and field[0] in '=+-@':
        return "'" + field  # Prefix with single quote to prevent formula execution
    return field

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS resumes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT,
            jd_text TEXT,
            score INTEGER,
            file_path TEXT,
            created_at TEXT
        )
    ''')
    migrations = [
        'ALTER TABLE resumes ADD COLUMN status TEXT DEFAULT "Scanned"',
        'ALTER TABLE resumes ADD COLUMN status_updated_at TEXT',
        'ALTER TABLE resumes ADD COLUMN scan_result TEXT',
        'ALTER TABLE resumes ADD COLUMN employment_type TEXT',
        'ALTER TABLE resumes ADD COLUMN job_category TEXT',
        'ALTER TABLE resumes ADD COLUMN extracted_keywords TEXT',
        'ALTER TABLE resumes ADD COLUMN warning_flags TEXT',
        'ALTER TABLE resumes ADD COLUMN match_percentage INTEGER',
        'ALTER TABLE resumes ADD COLUMN source_url TEXT',
        'ALTER TABLE resumes ADD COLUMN rejection_reason TEXT',
        'ALTER TABLE resumes ADD COLUMN source TEXT DEFAULT "dashboard"',
        'ALTER TABLE resumes ADD COLUMN user_address TEXT',
        'ALTER TABLE resumes ADD COLUMN follow_up_draft TEXT',
    ]
    for sql in migrations:
        try:
            c.execute(sql)
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()

def save_resume_record(company_name: str, jd_text: str, score: int, file_path: str, scan_result: str = None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO resumes (company_name, jd_text, score, file_path, created_at, status, scan_result)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (company_name, jd_text, score, file_path, datetime.now().isoformat(), "Scanned", scan_result))
    record_id = c.lastrowid
    conn.commit()
    conn.close()
    return record_id

def save_job_matcher_record(company_name: str, jd_text: str, match_percentage: int,
                            can_apply: bool, rejection_reason: str = None,
                            source_url: str = None, scan_result: str = None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    status = "Matched" if can_apply else "Rejected"
    c.execute('''
        INSERT INTO resumes (company_name, jd_text, score, file_path, created_at, status,
                            scan_result, source_url, rejection_reason, source, match_percentage)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (company_name, jd_text, 0, None, datetime.now().isoformat(),
          status, scan_result, source_url, rejection_reason, "job-finder", match_percentage))
    record_id = c.lastrowid
    conn.commit()
    conn.close()
    return record_id

def _parse_record(row):
    """Convert a database row to dict, parsing scan_result JSON if present."""
    if row is None:
        return None
    d = dict(row)
    if d.get('scan_result'):
        try:
            import json
            d['scan_result'] = json.loads(d['scan_result'])
        except (json.JSONDecodeError, TypeError):
            d['scan_result'] = None
    return d

def get_resume_by_id(record_id: int):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT * FROM resumes WHERE id = ?', (record_id,))
    row = c.fetchone()
    conn.close()
    return _parse_record(row)

def get_all_resumes(limit: int = 50, offset: int = 0):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT * FROM resumes ORDER BY created_at DESC LIMIT ? OFFSET ?', (limit, offset))
    rows = c.fetchall()
    conn.close()
    return [_parse_record(row) for row in rows]

def find_existing_company(company_name: str):
    """Check if a record with the same company name already exists."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT id, score, created_at FROM resumes WHERE LOWER(company_name) = LOWER(?) ORDER BY created_at DESC LIMIT 1', (company_name,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def delete_resume_record(record_id: int):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM resumes WHERE id = ?', (record_id,))
    conn.commit()
    conn.close()

def search_records(query: str, limit: int = 50):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    like = f"%{query}%"
    c.execute('''
        SELECT * FROM resumes
        WHERE company_name LIKE ? OR jd_text LIKE ? OR scan_result LIKE ?
        ORDER BY created_at DESC LIMIT ?
    ''', (like, like, like, limit))
    rows = c.fetchall()
    conn.close()
    return [_parse_record(row) for row in rows]

def update_user_address(record_id: int, address: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE resumes SET user_address = ? WHERE id = ?', (address, record_id))
    conn.commit()
    conn.close()

def save_follow_up_draft(record_id: int, subject: str, body: str):
    import json
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    payload = json.dumps({"subject": subject, "body": body, "saved_at": datetime.now().isoformat()})
    c.execute('UPDATE resumes SET follow_up_draft = ? WHERE id = ?', (payload, record_id))
    conn.commit()
    conn.close()

def get_follow_up_draft(record_id: int):
    import json
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT follow_up_draft FROM resumes WHERE id = ?', (record_id,))
    row = c.fetchone()
    conn.close()
    if row and row['follow_up_draft']:
        try:
            return json.loads(row['follow_up_draft'])
        except Exception:
            return None
    return None

def update_resume_status(record_id: int, status: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE resumes SET status = ?, status_updated_at = ? WHERE id = ?',
              (status, datetime.now().isoformat(), record_id))
    conn.commit()
    conn.close()


def get_all_addresses():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT id, company_name, user_address, created_at, scan_result, jd_text FROM resumes WHERE user_address IS NOT NULL AND user_address != \'\' ORDER BY created_at DESC')
    rows = c.fetchall()
    conn.close()
    return [_parse_record(row) for row in rows]
