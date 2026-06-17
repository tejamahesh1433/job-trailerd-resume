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

def update_resume_status(record_id: int, status: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE resumes SET status = ?, status_updated_at = ? WHERE id = ?',
              (status, datetime.now().isoformat(), record_id))
    conn.commit()
    conn.close()
