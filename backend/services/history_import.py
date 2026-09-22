"""Import application CSVs without replacing existing history records."""
import csv
import io
import re
import sqlite3
from datetime import datetime, timedelta, timezone

import database

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 1000
STATUSES = ('Scanned', 'Matched', 'Submitted Profile', 'Applied', 'Phone Screen', 'Interview', 'Offer', 'Rejected')


def _created_at(row):
    date = row.get('Date', '')
    time = row.get('Time', '')
    if not date:
        if time:
            raise ValueError('Time requires a Date')
        return datetime.now().astimezone().isoformat()
    if not time:
        return datetime.fromisoformat(date).isoformat()
    match = re.fullmatch(r'(\d{1,2}:\d{2} [AP]M)(?: (EDT|EST|UTC))?', time, re.I)
    if not match:
        raise ValueError('Time must use HH:MM AM/PM, optionally followed by EDT, EST, or UTC')
    value = datetime.strptime(date + ' ' + match[1].upper(), '%Y-%m-%d %I:%M %p')
    if match[2]:
        value = value.replace(tzinfo=timezone(timedelta(hours={'EDT': -4, 'EST': -5, 'UTC': 0}[match[2].upper()])))
    return value.isoformat()


def import_applications_csv(content):
    if len(content) > MAX_BYTES:
        raise ValueError('CSV must be 5 MB or smaller')
    try:
        reader = csv.DictReader(io.StringIO(content.decode('utf-8-sig'), newline=''), strict=True)
        headers = reader.fieldnames
        if not headers or 'Company' not in headers:
            raise ValueError('CSV must have a Company column')
        if len(set(headers)) != len(headers):
            raise ValueError('CSV contains duplicate column names')
        records, errors = [], []
        count = 0
        for number, raw in enumerate(reader, start=2):
            if not any(raw.values()):
                continue
            count += 1
            if count > MAX_ROWS:
                raise ValueError('CSV must contain no more than 1,000 applications')
            try:
                if None in raw or any(value is None for value in raw.values()):
                    raise ValueError('Column count does not match the header')
                row = {key: value.strip() for key, value in raw.items()}
                company = row['Company']
                if not company or len(company) > 200:
                    raise ValueError('Company is required and must be at most 200 characters')
                status = row.get('Status') or 'Scanned'
                if status not in STATUSES:
                    raise ValueError('Unknown status: ' + status)
                created = _created_at(row)
                vendor = row.get('Vendor Details', '')
                contact = re.search(r'(?:Recruiter:|Job poster:|job poster card:)\s*([^,]+)', vendor, re.I)
                email = re.search(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', vendor)
                notes = '\n'.join(f'{key}: {value}' for key, value in row.items() if value and key not in ('Company', 'JD'))
                if len(row.get('JD', '')) > 20000 or len(notes) > 20000:
                    raise ValueError('Job description or notes exceed 20,000 characters')
                records.append(dict(
                    company_name=company, jd_text=row.get('JD', ''), score=0,
                    created_at=created, status=status, status_updated_at=created,
                    employment_type=row.get('Job Type', ''), source_url=row.get('Job URL', ''),
                    source='csv-import', user_notes=notes,
                    vendor_company_name=company if vendor else '',
                    vendor_contact_name=contact[1].replace(' (Verified)', '').strip() if contact else '',
                    vendor_contact_email=email[0].rstrip('.') if email else '',
                    vendor_contact_phone='',
                ))
            except ValueError as exc:
                errors.append({'row': number, 'message': str(exc)})
        if not count:
            raise ValueError('CSV contains no applications')
    except UnicodeDecodeError as exc:
        raise ValueError('Save your CSV using UTF-8 encoding') from exc
    except csv.Error as exc:
        raise ValueError('Malformed CSV: ' + str(exc)) from exc

    # Serialize duplicate checks with insertion, including concurrent uploads.
    conn = sqlite3.connect(database.DB_FILE, timeout=30)
    imported = skipped = 0
    try:
        with conn:
            conn.execute('BEGIN IMMEDIATE')
            existing = conn.execute('SELECT source_url, company_name, jd_text, user_notes FROM resumes').fetchall()
            urls = {r[0].strip().rstrip('/') for r in existing if r[0]}
            identities = {(r[1] or '', r[2] or '', r[3] or '') for r in existing}
            for record in records:
                url = record['source_url'].rstrip('/')
                identity = (record['company_name'], record['jd_text'], record['user_notes'])
                if (url and url in urls) or identity in identities:
                    skipped += 1
                    continue
                conn.execute('INSERT INTO resumes (' + ','.join(record) + ') VALUES (' + ','.join('?' for _ in record) + ')', tuple(record.values()))
                imported += 1
                if url:
                    urls.add(url)
                identities.add(identity)
    finally:
        conn.close()
    return {'imported': imported, 'skipped': skipped, 'failed': len(errors), 'errors': errors}
