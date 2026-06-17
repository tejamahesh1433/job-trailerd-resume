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
    try:
        c.execute('ALTER TABLE resumes ADD COLUMN status TEXT DEFAULT "Scanned"')
    except sqlite3.OperationalError:
        pass # Column already exists
    conn.commit()
    conn.close()

def save_resume_record(company_name: str, jd_text: str, score: int, file_path: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO resumes (company_name, jd_text, score, file_path, created_at, status)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (company_name, jd_text, score, file_path, datetime.now().isoformat(), "Scanned"))
    record_id = c.lastrowid
    conn.commit()
    conn.close()
    return record_id

def get_resume_by_id(record_id: int):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT * FROM resumes WHERE id = ?', (record_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def get_all_resumes(limit: int = 50, offset: int = 0):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT * FROM resumes ORDER BY created_at DESC LIMIT ? OFFSET ?', (limit, offset))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def delete_resume_record(record_id: int):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM resumes WHERE id = ?', (record_id,))
    conn.commit()
    conn.close()

def update_resume_status(record_id: int, status: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE resumes SET status = ? WHERE id = ?', (status, record_id))
    conn.commit()
    conn.close()
