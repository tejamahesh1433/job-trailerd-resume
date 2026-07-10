import sqlite3
from datetime import datetime, timedelta
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
        'ALTER TABLE resumes ADD COLUMN user_notes TEXT',
        'ALTER TABLE resumes ADD COLUMN cover_letter_generated INTEGER DEFAULT 0',
        'ALTER TABLE resumes ADD COLUMN drafts_json TEXT',
        'ALTER TABLE resumes ADD COLUMN contact_json TEXT',
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

def update_user_notes(record_id: int, notes: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE resumes SET user_notes = ? WHERE id = ?', (notes, record_id))
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

def update_resume_status(record_id: int, status: str, rejection_reason: str = None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if rejection_reason is not None:
        c.execute('UPDATE resumes SET status = ?, status_updated_at = ?, rejection_reason = ? WHERE id = ?',
                  (status, datetime.now().isoformat(), rejection_reason, record_id))
    else:
        c.execute('UPDATE resumes SET status = ?, status_updated_at = ? WHERE id = ?',
                  (status, datetime.now().isoformat(), record_id))
    conn.commit()
    conn.close()


def update_job_description(record_id: int, description: str):
    """Patch just the description inside scan_result — used when the user pastes a
    full JD manually or the app re-fetches it from the posting URL."""
    import json
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT scan_result FROM resumes WHERE id = ?', (record_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return None
    try:
        sr = json.loads(row['scan_result']) if row['scan_result'] else {}
    except (json.JSONDecodeError, TypeError):
        sr = {}
    sr['description'] = description
    c.execute('UPDATE resumes SET scan_result = ? WHERE id = ?', (json.dumps(sr), record_id))
    conn.commit()
    conn.close()
    return get_job_detail(record_id)

def update_resume_rerun(record_id: int, company_name: str, jd_text: str, score: int, scan_result: str):
    """Overwrite an existing record's JD/score/scan_result in place for a re-run (no new row)."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE resumes SET company_name = ?, jd_text = ?, score = ?, scan_result = ? WHERE id = ?',
              (company_name, jd_text, score, scan_result, record_id))
    conn.commit()
    conn.close()

def update_resume_after_edit(record_id: int, score: int, scan_result: str):
    """Update an existing record's tailored score/scan_result in place (no new row)."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE resumes SET score = ?, scan_result = ? WHERE id = ?',
              (score, scan_result, record_id))
    conn.commit()
    conn.close()


def command_center_job_seen(company: str, title: str) -> bool:
    """True if this company+title posting was already discovered by a previous
    Command Center search — found, scored, rejected, or applied, any status — so a new
    search can skip re-scanning it (and spending an AI call on it) and spend its budget
    finding genuinely new postings instead. Same company+title dedupe key already used
    by save_found_job/save_rejected_job."""
    company = (company or '').strip()
    title = (title or '').strip()
    if not company or not title:
        return False
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''SELECT 1 FROM resumes WHERE LOWER(company_name) = LOWER(?) AND LOWER(jd_text) = LOWER(?)
                 AND source = 'command-center' LIMIT 1''', (company, title))
    row = c.fetchone()
    conn.close()
    return row is not None


def save_found_job(job: dict):
    """Persist an auto-search result so it survives a reload. Dedupes on company+title;
    refreshes the stored data only while the job is still untouched ('Found')."""
    import json
    company = (job.get('company') or 'Unknown').strip()
    title = (job.get('title') or '').strip()
    score = int(job.get('score') or 0)
    url = job.get('url') or ''
    scan_result = json.dumps(job)

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('''SELECT id, status FROM resumes
                 WHERE LOWER(company_name) = LOWER(?) AND LOWER(jd_text) = LOWER(?) AND source = 'command-center'
                 LIMIT 1''', (company, title))
    existing = c.fetchone()
    if existing:
        if existing['status'] == 'Found':
            c.execute('UPDATE resumes SET score = ?, scan_result = ?, source_url = ? WHERE id = ?',
                      (score, scan_result, url, existing['id']))
        record_id = existing['id']
    else:
        c.execute('''INSERT INTO resumes (company_name, jd_text, score, file_path, created_at, status,
                     scan_result, source, source_url)
                     VALUES (?, ?, ?, NULL, ?, 'Found', ?, 'command-center', ?)''',
                  (company, title, score, datetime.now().isoformat(), scan_result, url))
        record_id = c.lastrowid
    conn.commit()
    conn.close()
    return record_id


def get_found_jobs(limit: int = 5, offset: int = 0):
    """Auto-search results still sitting in 'Found' state, best score first, for the
    Command Center dashboard (and the full paginated "all matches" view)."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('''SELECT * FROM resumes WHERE source = 'command-center' AND status = 'Found'
                 ORDER BY score DESC, created_at DESC LIMIT ? OFFSET ?''', (limit, offset))
    rows = c.fetchall()
    conn.close()
    jobs = []
    for row in rows:
        d = _parse_record(row)
        sr = d.get('scan_result')
        job = dict(sr) if isinstance(sr, dict) else {}
        job.setdefault('title', d.get('jd_text') or '')
        job.setdefault('company', d.get('company_name') or '')
        job.setdefault('score', d.get('score') or 0)
        job.setdefault('url', d.get('source_url') or '')
        job['record_id'] = d.get('id')
        jobs.append(job)
    return jobs


def get_found_jobs_count():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM resumes WHERE source = 'command-center' AND status = 'Found'")
    count = c.fetchone()[0]
    conn.close()
    return count


ACTIVE_STATUSES_NOT_YET_APPLIED = ('Applied', 'Interviewing', 'Offered', 'Rejected')


def get_action_queue(follow_up_days: int = 7, description_min_len: int = 60, item_limit: int = 10):
    """Groups actionable jobs into work queues:
    - needing_description: found/saved postings whose scraped text was too thin to tailor against
    - ready_to_tailor: saved postings with a usable description, not yet acted on
    - cover_letters_waiting: a cover letter was generated but the job hasn't been applied to yet
    - email_drafts_waiting: a follow-up/outreach email draft is saved awaiting review
    - tailored_not_applied: a tailored resume exists but the job hasn't been applied to yet
    - follow_ups_due: applied jobs with no status change in `follow_up_days` days"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute('''SELECT id, company_name, jd_text, scan_result, status FROM resumes
                 WHERE source IN ('command-center', 'manual') AND status IN ('Found', 'Shortlisted', 'Matched')''')
    needing_description = []
    ready_to_tailor = []
    for row in c.fetchall():
        d = _parse_record(row)
        sr = d.get('scan_result') if isinstance(d.get('scan_result'), dict) else {}
        desc = (sr.get('description') or '').strip()
        item = {'id': d['id'], 'company': d.get('company_name') or '', 'title': d.get('jd_text') or ''}
        if len(desc) < description_min_len:
            needing_description.append(item)
        elif d.get('status') in ('Shortlisted', 'Matched'):
            ready_to_tailor.append(item)

    not_applied_placeholders = ','.join('?' * len(ACTIVE_STATUSES_NOT_YET_APPLIED))

    c.execute(f'''SELECT id, company_name, jd_text FROM resumes
                 WHERE cover_letter_generated = 1 AND status NOT IN ({not_applied_placeholders})''',
              ACTIVE_STATUSES_NOT_YET_APPLIED)
    cover_letters_waiting = [{'id': r['id'], 'company': r['company_name'] or '', 'title': r['jd_text'] or ''} for r in c.fetchall()]

    c.execute('''SELECT id, company_name, jd_text FROM resumes
                 WHERE follow_up_draft IS NOT NULL AND follow_up_draft != '' ''')
    email_drafts_waiting = [{'id': r['id'], 'company': r['company_name'] or '', 'title': r['jd_text'] or ''} for r in c.fetchall()]
    drafted_ids = {item['id'] for item in email_drafts_waiting}

    c.execute(f'''SELECT id, company_name, jd_text FROM resumes
                 WHERE file_path IS NOT NULL AND file_path != '' AND status NOT IN ({not_applied_placeholders})''',
              ACTIVE_STATUSES_NOT_YET_APPLIED)
    tailored_not_applied = [{'id': r['id'], 'company': r['company_name'] or '', 'title': r['jd_text'] or ''} for r in c.fetchall()]

    cutoff = (datetime.now() - timedelta(days=follow_up_days)).isoformat()
    c.execute('''SELECT id, company_name, jd_text, status_updated_at FROM resumes
                 WHERE status = 'Applied' AND status_updated_at IS NOT NULL AND status_updated_at <= ?
                 ORDER BY status_updated_at ASC''', (cutoff,))
    follow_ups_due = []
    for r in c.fetchall():
        since = r['status_updated_at']
        days_since = None
        try:
            days_since = (datetime.now() - datetime.fromisoformat(since)).days
        except (ValueError, TypeError):
            pass
        follow_ups_due.append({
            'id': r['id'], 'company': r['company_name'] or '', 'title': r['jd_text'] or '',
            'since': since, 'days_since': days_since, 'has_draft': r['id'] in drafted_ids,
        })

    conn.close()
    return {
        'needing_description': {'count': len(needing_description), 'items': needing_description[:item_limit]},
        'ready_to_tailor': {'count': len(ready_to_tailor), 'items': ready_to_tailor[:item_limit]},
        'cover_letters_waiting': {'count': len(cover_letters_waiting), 'items': cover_letters_waiting[:item_limit]},
        'email_drafts_waiting': {'count': len(email_drafts_waiting), 'items': email_drafts_waiting[:item_limit]},
        'tailored_not_applied': {'count': len(tailored_not_applied), 'items': tailored_not_applied[:item_limit]},
        'follow_ups_due': {'count': len(follow_ups_due), 'items': follow_ups_due[:item_limit]},
    }


def get_active_applications():
    """Jobs currently in the pipeline that could plausibly get an email reply from the
    company — used by services/inbox_matcher.py to match incoming Gmail messages back
    to a tracked application. Scoped to command-center/manual jobs the user has actually
    engaged with (saved or further), not raw unscored 'Found' postings."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('''SELECT id, company_name, jd_text, status FROM resumes
                 WHERE source IN ('command-center', 'manual')
                 AND status IN ('Shortlisted', 'Matched', 'Applied', 'Interviewing', 'Offered')''')
    rows = c.fetchall()
    conn.close()
    return [{'id': r['id'], 'company': r['company_name'] or '', 'title': r['jd_text'] or '', 'status': r['status']} for r in rows]


def mark_cover_letter_generated(record_id: int):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE resumes SET cover_letter_generated = 1 WHERE id = ?', (record_id,))
    conn.commit()
    conn.close()


def _infer_platform_from_url(url: str) -> str:
    if not url:
        return 'Other'
    u = url.lower()
    if 'linkedin.com' in u:
        return 'LinkedIn'
    if 'dice.com' in u:
        return 'Dice'
    if 'indeed.com' in u:
        return 'Indeed'
    if 'ziprecruiter.com' in u:
        return 'ZipRecruiter'
    if 'greenhouse.io' in u:
        return 'Greenhouse'
    if 'lever.co' in u:
        return 'Lever'
    if 'myworkdayjobs.com' in u or 'workday.com' in u:
        return 'Workday'
    return 'Other'


def get_job_source_breakdown():
    """Counts of tracked jobs by where they came from — auto-search platform
    (inferred from the posting URL) or manually added."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT source, source_url FROM resumes WHERE source IN ('command-center', 'manual')")
    rows = c.fetchall()
    conn.close()
    counts = {}
    for r in rows:
        label = 'Manual' if r['source'] == 'manual' else _infer_platform_from_url(r['source_url'])
        counts[label] = counts.get(label, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


def get_skipped_jobs(limit: int = 8):
    """Rejected jobs with the reason they were skipped, most recent first.
    Falls back to a score-based heuristic when no explicit reason was recorded."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('''SELECT id, company_name, jd_text, score, rejection_reason FROM resumes
                 WHERE status = 'Rejected' ORDER BY status_updated_at DESC, created_at DESC LIMIT ?''', (limit,))
    rows = c.fetchall()
    conn.close()
    jobs = []
    for r in rows:
        reason = (r['rejection_reason'] or '').strip()
        if not reason:
            score = r['score'] or 0
            if score and score < 40:
                reason = 'Low overall match score'
            elif score and score < 60:
                reason = 'Below target match score'
            else:
                reason = 'Marked as skip'
        jobs.append({'id': r['id'], 'company': r['company_name'] or '', 'title': r['jd_text'] or '', 'reason': reason})
    return jobs


def save_manual_job(job: dict):
    """Track a job the user is adding by hand rather than one surfaced by auto-search.
    Goes straight to 'Shortlisted' since the user has already decided to track it."""
    import json
    company = (job.get('company') or 'Unknown').strip()
    title = (job.get('title') or '').strip()
    url = job.get('url') or ''
    notes = job.get('notes') or ''
    scan_result = json.dumps({
        'title': title, 'company': company, 'url': url,
        'description': job.get('description') or '', 'score': 0, 'tags': [], 'reasons': ['Manually added'],
    })
    now = datetime.now().isoformat()

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('''SELECT id FROM resumes WHERE LOWER(company_name) = LOWER(?) AND LOWER(jd_text) = LOWER(?) LIMIT 1''',
              (company, title))
    existing = c.fetchone()
    if existing:
        record_id = existing['id']
    else:
        c.execute('''INSERT INTO resumes (company_name, jd_text, score, file_path, created_at, status,
                     status_updated_at, scan_result, source, source_url, user_notes)
                     VALUES (?, ?, 0, NULL, ?, 'Shortlisted', ?, ?, 'manual', ?, ?)''',
                  (company, title, now, now, scan_result, url, notes))
        record_id = c.lastrowid
    conn.commit()
    conn.close()
    return record_id


def clear_command_center_jobs():
    """Delete every job tracked by the Command Center (auto-search results and manually
    added jobs) so the user can start fresh. Scoped strictly to source IN
    ('command-center', 'manual') — never touches records from other pages (Resume
    Tailor's 'dashboard' scans, Job Finder's 'job-matcher' records)."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM resumes WHERE source IN ('command-center', 'manual')")
    count = c.fetchone()[0]
    c.execute("DELETE FROM resumes WHERE source IN ('command-center', 'manual')")
    conn.commit()
    conn.close()
    return count


def save_application_from_job(company_name: str, status: str = 'Shortlisted', source: str = 'command-center',
                               notes: str = '', title: str = '', url: str = ''):
    """Create or update a resume record representing a saved application. Dedupes on company+title
    so saving a job that was already surfaced by auto-search updates that same record instead of
    creating a duplicate."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT id FROM resumes WHERE LOWER(company_name) = LOWER(?) AND LOWER(jd_text) = LOWER(?) LIMIT 1',
              (company_name, title))
    existing = c.fetchone()
    now = datetime.now().isoformat()
    if existing:
        c.execute('UPDATE resumes SET status = ?, status_updated_at = ?, user_notes = ?, source_url = ? WHERE id = ?',
                  (status, now, notes, url, existing['id']))
        record_id = existing['id']
    else:
        c.execute('''INSERT INTO resumes (company_name, jd_text, score, file_path, created_at, status,
                     status_updated_at, source, source_url, user_notes)
                     VALUES (?, ?, 0, NULL, ?, ?, ?, ?, ?, ?)''',
                  (company_name, title, now, status, now, source, url, notes))
        record_id = c.lastrowid
    conn.commit()
    conn.close()
    return record_id


def save_rejected_job(job: dict):
    """Persist a job that failed a hard-reject rule (visa/W2/lead-level/language) before
    it ever reached AI scoring, so it shows up in 'Jobs to Skip' with the real reason
    instead of just silently disappearing from the search."""
    import json
    company = (job.get('company') or 'Unknown').strip()
    title = (job.get('title') or '').strip()
    reason = job.get('reason') or ''
    scan_result = json.dumps({'title': title, 'company': company, 'reasons': [reason]})
    now = datetime.now().isoformat()

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('''SELECT id FROM resumes
                 WHERE LOWER(company_name) = LOWER(?) AND LOWER(jd_text) = LOWER(?) AND source = 'command-center'
                 LIMIT 1''', (company, title))
    existing = c.fetchone()
    if existing:
        c.execute('UPDATE resumes SET status = ?, status_updated_at = ?, rejection_reason = ?, scan_result = ? WHERE id = ?',
                  ('Rejected', now, reason, scan_result, existing['id']))
        record_id = existing['id']
    else:
        c.execute('''INSERT INTO resumes (company_name, jd_text, score, file_path, created_at, status,
                     status_updated_at, scan_result, source, rejection_reason)
                     VALUES (?, ?, 0, NULL, ?, 'Rejected', ?, ?, 'command-center', ?)''',
                  (company, title, now, now, scan_result, reason))
        record_id = c.lastrowid
    conn.commit()
    conn.close()
    return record_id


def get_career_intel():
    """Real (not mocked) signal for the Command Center's Career Intel panel: average
    match score across current results, the skills showing up most often in postings,
    and which platform is producing the most jobs."""
    import json
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('''SELECT score, scan_result FROM resumes
                 WHERE source = 'command-center' AND status IN ('Found', 'Shortlisted', 'Matched')''')
    rows = c.fetchall()
    conn.close()

    scores = [r['score'] for r in rows if r['score']]
    avg_score = round(sum(scores) / len(scores)) if scores else 0

    tag_counts = {}
    for r in rows:
        if not r['scan_result']:
            continue
        try:
            d = json.loads(r['scan_result'])
        except (json.JSONDecodeError, TypeError):
            continue
        for t in (d.get('tags') or []):
            tag_counts[t] = tag_counts.get(t, 0) + 1
    top_skills = [t for t, _ in sorted(tag_counts.items(), key=lambda kv: -kv[1])[:8]]

    breakdown = get_job_source_breakdown()
    if breakdown:
        best_source, best_count = max(breakdown.items(), key=lambda kv: kv[1])
        total = sum(breakdown.values())
        source_pct = round((best_count / total) * 100) if total else 0
    else:
        best_source, source_pct = None, 0

    return {
        'avg_score': avg_score,
        'top_skills': top_skills,
        'best_source': best_source,
        'source_pct': source_pct,
    }


def get_job_detail(record_id: int):
    """Full job object for the Command Center's Job Detail Workspace — merges the
    scan_result blob (title/company/score/tags/reasons/next_action/description/url)
    with DB-side tracking fields (status, notes, drafts, contact suggestions)."""
    import json
    d = get_resume_by_id(record_id)
    if not d:
        return None
    sr = d.get('scan_result')
    job = dict(sr) if isinstance(sr, dict) else {}
    job.setdefault('title', d.get('jd_text') or '')
    job.setdefault('company', d.get('company_name') or '')
    job.setdefault('score', d.get('score') or 0)
    job.setdefault('url', d.get('source_url') or '')
    job['record_id'] = d.get('id')
    job['status'] = d.get('status')
    job['status_updated_at'] = d.get('status_updated_at')
    job['created_at'] = d.get('created_at')
    job['source'] = d.get('source')
    job['user_notes'] = d.get('user_notes')
    job['rejection_reason'] = d.get('rejection_reason')
    job['file_path'] = d.get('file_path')
    job['cover_letter_generated'] = bool(d.get('cover_letter_generated'))

    try:
        job['drafts'] = json.loads(d['drafts_json']) if d.get('drafts_json') else {}
    except (json.JSONDecodeError, TypeError):
        job['drafts'] = {}
    try:
        job['contact'] = json.loads(d['contact_json']) if d.get('contact_json') else None
    except (json.JSONDecodeError, TypeError):
        job['contact'] = None

    # If a contact wasn't explicitly searched for yet, but the scrape/scoring pass
    # already pulled a real name/email/phone straight out of the posting text, surface
    # that immediately instead of leaving the panel empty until the user clicks "Find
    # Contact" — this is actual extracted data, not a guess, so mark it verified.
    if not job['contact']:
        scraped_name = (job.get('contact_name') or '').strip()
        scraped_email = (job.get('contact_email') or '').strip()
        scraped_phone = (job.get('contact_phone') or '').strip()
        if scraped_name or scraped_email or scraped_phone:
            job['contact'] = {
                'contact_name': scraped_name or None,
                'email_guess': scraped_email or None,
                'contact_phone': scraped_phone or None,
                'linkedin_recruiter_search': None,
                'linkedin_hiring_manager_search': None,
                'linkedin_company_url': None,
                'careers_page': None,
                'outreach_strategy': f"Found directly in the job posting — reach out to {scraped_name or 'this contact'} using the details above.",
                'verified': True,
                'generated_at': d.get('created_at'),
            }

    return job


def update_job_score(record_id: int, score: int, tags: list, reasons: list, next_action: str):
    """Overwrite a job's AI score/tags/reasons/next_action after a re-score, keeping
    everything else in scan_result (description, url, location) untouched."""
    import json
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT scan_result FROM resumes WHERE id = ?', (record_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return None
    try:
        sr = json.loads(row['scan_result']) if row['scan_result'] else {}
    except (json.JSONDecodeError, TypeError):
        sr = {}
    sr['score'] = score
    sr['tags'] = tags
    sr['reasons'] = reasons
    sr['next_action'] = next_action
    c.execute('UPDATE resumes SET score = ?, scan_result = ? WHERE id = ?',
              (score, json.dumps(sr), record_id))
    conn.commit()
    conn.close()
    return get_job_detail(record_id)


def link_tailored_resume(record_id: int, file_path: str):
    """Point a Command Center job at a newly-tailored resume file (produced by the
    existing /api/scan flow, called in-place from the Job Detail Workspace) so cover
    letter generation etc. can find it immediately without a separate manual step."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE resumes SET file_path = ? WHERE id = ?', (file_path, record_id))
    conn.commit()
    conn.close()
    return get_job_detail(record_id)


def save_job_draft(record_id: int, draft_type: str, subject: str, body: str):
    """Store a generated/edited draft (recruiter_email, follow_up_email, linkedin_message)
    under its own key in drafts_json, without touching the other draft types."""
    import json
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT drafts_json FROM resumes WHERE id = ?', (record_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return None
    try:
        drafts = json.loads(row['drafts_json']) if row['drafts_json'] else {}
    except (json.JSONDecodeError, TypeError):
        drafts = {}
    drafts[draft_type] = {'subject': subject, 'body': body, 'saved_at': datetime.now().isoformat()}
    c.execute('UPDATE resumes SET drafts_json = ? WHERE id = ?', (json.dumps(drafts), record_id))
    conn.commit()
    conn.close()
    return drafts[draft_type]


def save_job_contact(record_id: int, contact: dict):
    import json
    contact = dict(contact)
    contact['generated_at'] = datetime.now().isoformat()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE resumes SET contact_json = ? WHERE id = ?', (json.dumps(contact), record_id))
    conn.commit()
    conn.close()
    return contact


def get_all_addresses():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT id, company_name, user_address, created_at, scan_result, jd_text FROM resumes WHERE user_address IS NOT NULL AND user_address != \'\' ORDER BY created_at DESC')
    rows = c.fetchall()
    conn.close()
    return [_parse_record(row) for row in rows]
