"""
Pull all RTR confirmation emails from Gmail, extract submission details,
match to existing DB records (or create new ones), and mark them as
'Submitted Profile'.

Extracted fields per RTR email:
  vendor_email, vendor_name, vendor_company, role, end_client, rate, date
"""

import sys, os, re, base64, json, sqlite3, time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.environ.setdefault("DATA_DIR",
    os.path.join(os.path.dirname(__file__), "..", "backend", "data"))

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "backend", "data", "resumes.db")

EMAIL_RE = re.compile(r'[\w._%+\-]+@[\w.\-]+\.[a-zA-Z]{2,}')
RATE_RE  = re.compile(
    r'\$\s*(\d{2,3}(?:\.\d{1,2})?)\s*/?\s*h(?:ou)?r'
    r'|(\d{2,3}(?:\.\d{1,2})?)\s*(?:dollars?\s*/?\s*h(?:ou)?r|per\s+hour)',
    re.I
)

OWN_EMAILS = {"tejamahesh33333@gmail.com", "tejamahesh23@gmail.com"}
IGNORE_DOMAINS = {"nvoids.com", "bit.ly", "linkedin.com", "dice.com"}

VALID_STATUSES_ORDER = [
    "Scanned", "Found", "Matched", "Applied",
    "Submitted Profile", "Phone Screen", "Shortlisted",
    "Interview", "Offer", "Rejected"
]


# ── Gmail helpers ───────────────────────────────────────────────────────────

def get_service():
    from services.gmail_service import _load_credentials, _save_credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    creds = _load_credentials()
    if not creds:
        raise RuntimeError("Gmail not connected")
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_credentials(creds)
    return build("gmail", "v1", credentials=creds)


def api_call(fn, retries=5):
    import googleapiclient.errors
    delay = 3.0
    for i in range(retries):
        try:
            return fn()
        except googleapiclient.errors.HttpError as e:
            if e.status_code in (429, 403) and i < retries - 1:
                print(f"  [quota] sleeping {delay:.0f}s...")
                time.sleep(delay); delay *= 2
            else:
                raise
    return None


def decode_body(payload):
    mime = payload.get("mimeType", "")
    if mime == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore")
    if mime.startswith("multipart/"):
        for part in payload.get("parts", []):
            t = decode_body(part)
            if t:
                return t
    return ""


def get_header(headers, name):
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def strip_email_addr(raw: str) -> str:
    """'John Doe <john@co.com>' → 'john@co.com'"""
    m = EMAIL_RE.search(raw)
    return m.group(0).lower() if m else ""


def strip_display_name(raw: str) -> str:
    """'John Doe <john@co.com>' → 'John Doe'"""
    m = re.match(r'^"?([^"<]+)"?\s*<', raw.strip())
    return m.group(1).strip() if m else ""


# ── RTR field extraction ────────────────────────────────────────────────────

def extract_rate(text: str) -> str:
    for m in RATE_RE.finditer(text):
        val = m.group(1) or m.group(2)
        if val and 20 <= float(val) <= 250:
            return f"${val}/hr"
    return ""


def extract_role(subject: str, body: str) -> str:
    # From subject: "RTR Confirmation for X || ROLE || CLIENT || LOCATION"
    m = re.search(r'\|\|\s*([^|]+?)\s*(?:C2[CH]|Contract|Fulltime)?\s*\|\|', subject, re.I)
    if m:
        return m.group(1).strip()
    # "for the ROLE position"
    m = re.search(r'for\s+(?:the\s+)?([A-Z][^\n.]{5,60}?)\s+position', body, re.I)
    if m:
        role = m.group(1).strip()
        if len(role) < 80:
            return role
    # From subject directly
    subj_clean = re.sub(r'^(Re:|Fw:|RTR[:\s-]*|Rate Confirmation[:\s-]*)', '', subject, flags=re.I).strip()
    subj_clean = re.sub(r'\s*[-|]\s*(Remote|Onsite|Hybrid|C2C|W2).*$', '', subj_clean, flags=re.I)
    if 10 < len(subj_clean) < 100:
        return subj_clean
    return ""


def extract_client(subject: str, body: str) -> str:
    # Subject pattern: "|| CLIENT || LOCATION"
    parts = re.split(r'\s*\|\|\s*', subject)
    for p in parts[2:]:
        p = p.strip()
        if p and not re.match(r'^(Remote|Onsite|Hybrid|C2C|W2|Contract|\d)', p, re.I):
            return p.split()[0:4]  # first 4 words
    # Body: "Client: COMPANY"
    m = re.search(r'Client\s*[:\-]\s*([^\n,]{3,60})', body, re.I)
    if m:
        return m.group(1).strip()
    return ""


def extract_vendor_company(from_email: str, body: str) -> str:
    # "from 'COMPANY'" or "Account Manager at COMPANY"
    m = re.search(r"(?:from|at|with)\s+['\"]?([A-Z][A-Za-z0-9\s&]+(?:Inc|LLC|Ltd|Corp|Solutions|Systems|Technologies|Tech|Group|Services|Consulting|Staffing|Global)\b)",
                  body)
    if m:
        return m.group(1).strip()
    # Derive from email domain
    domain = from_email.split("@")[1] if "@" in from_email else ""
    base = re.sub(r'\.(com|net|org|io|us)$', '', domain)
    base = re.sub(r'(inc|llc|ltd|corp|tech|soft|sys|group|sol|srv|it)$', '', base, flags=re.I)
    return base.title() if base else ""


def parse_rtr_email(msg: dict) -> dict | None:
    """Extract all fields from an RTR email. Returns None if not a real RTR."""
    headers  = msg.get("payload", {}).get("headers", [])
    subject  = get_header(headers, "Subject")
    from_raw = get_header(headers, "From")
    date_str = get_header(headers, "Date")
    body     = decode_body(msg.get("payload", {}))
    snippet  = msg.get("snippet", "")

    from_email = strip_email_addr(from_raw)
    from_name  = strip_display_name(from_raw)

    # Skip our own outgoing emails
    if from_email in OWN_EMAILS:
        return None

    domain = from_email.split("@")[1] if "@" in from_email else ""
    if domain in IGNORE_DOMAINS:
        return None

    # Must actually be an RTR/rate confirmation (not just a JD with "RTR" somewhere)
    is_rtr = bool(re.search(
        r'\b(RTR|right\s+to\s+represent|rate\s+confirm|rtr\s+confirm|I\s+confirm\s+the\s+(?:C2C|rate))',
        subject + " " + snippet, re.I
    ))
    if not is_rtr:
        return None

    rate   = extract_rate(body) or extract_rate(snippet)
    role   = extract_role(subject, body)
    client_parts = extract_client(subject, body)
    client = " ".join(client_parts) if isinstance(client_parts, list) else client_parts
    company = extract_vendor_company(from_email, body)

    # Parse date
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(date_str)
        date_iso = dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:
        date_iso = datetime.utcnow().isoformat()

    return {
        "vendor_email":   from_email,
        "vendor_name":    from_name,
        "vendor_company": company,
        "role":           role,
        "end_client":     client,
        "rate":           rate,
        "date":           date_iso,
        "subject":        subject,
    }


# ── DB matching & update ────────────────────────────────────────────────────

def load_db_records():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT id, company_name, vendor_contact_email, vendor_contact_name,
               vendor_company_name, vendor_contact_phone, created_at, status, user_notes
        FROM resumes ORDER BY created_at DESC
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def find_match(rtr: dict, db_rows: list[dict]) -> dict | None:
    """Find the best matching DB record for this RTR by vendor email + date proximity."""
    vendor_email = rtr["vendor_email"].lower()
    rtr_dt = datetime.fromisoformat(rtr["date"])

    candidates = []
    for row in db_rows:
        db_email = (row.get("vendor_contact_email") or "").lower().strip()
        if db_email != vendor_email:
            continue
        try:
            row_dt = datetime.fromisoformat(row["created_at"])
            # Allow RTR up to 30 days after the record was created
            delta = (rtr_dt - row_dt).days
            if -5 <= delta <= 45:
                candidates.append((abs(delta), row))
        except Exception:
            pass

    if candidates:
        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]
    return None


def update_record(record_id: int, rtr: dict, conn):
    cur = conn.cursor()
    cur.execute("SELECT status, vendor_contact_name, vendor_company_name, user_notes FROM resumes WHERE id=?", (record_id,))
    row = cur.fetchone()
    if not row:
        return

    current_status = row[0] or ""
    # Don't downgrade status
    current_idx = VALID_STATUSES_ORDER.index(current_status) if current_status in VALID_STATUSES_ORDER else 0
    new_idx     = VALID_STATUSES_ORDER.index("Submitted Profile")
    new_status  = "Submitted Profile" if new_idx >= current_idx else current_status

    # Append rate to notes if not already there
    notes = row[3] or ""
    if rtr["rate"] and rtr["rate"] not in notes:
        notes = (notes + f"\nRate: {rtr['rate']}").strip()
    if rtr["end_client"] and rtr["end_client"] not in notes:
        notes = (notes + f"\nClient: {rtr['end_client']}").strip()

    cur.execute("""
        UPDATE resumes SET
            status               = ?,
            vendor_contact_name  = COALESCE(NULLIF(vendor_contact_name,''), ?),
            vendor_company_name  = COALESCE(NULLIF(vendor_company_name,''), ?),
            user_notes           = ?
        WHERE id = ?
    """, (new_status,
          rtr["vendor_name"],
          rtr["vendor_company"],
          notes,
          record_id))


def insert_new_record(rtr: dict, conn):
    cur = conn.cursor()
    notes = []
    if rtr["rate"]:        notes.append(f"Rate: {rtr['rate']}")
    if rtr["end_client"]:  notes.append(f"Client: {rtr['end_client']}")
    notes_str = "\n".join(notes)
    cur.execute("""
        INSERT INTO resumes
            (company_name, jd_text, score, file_path, created_at, status,
             vendor_contact_name, vendor_company_name, vendor_contact_email,
             source, user_notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        rtr["end_client"] or rtr["vendor_company"],
        f"RTR via Gmail — {rtr['subject']}",
        0,
        "",
        rtr["date"],
        "Submitted Profile",
        rtr["vendor_name"],
        rtr["vendor_company"],
        rtr["vendor_email"],
        "gmail-rtr",
        notes_str,
    ))
    return cur.lastrowid


# ── Main ────────────────────────────────────────────────────────────────────

def run():
    print("Connecting to Gmail...")
    service = get_service()

    RTR_QUERY = (
        '(subject:RTR OR subject:"right to represent" OR subject:"rtr confirmation" '
        'OR subject:"rate confirmation") newer_than:18m'
    )

    print("Fetching RTR emails...")
    all_ids = []
    page_token = None
    while True:
        kw = dict(userId="me", q=RTR_QUERY, maxResults=500)
        if page_token:
            kw["pageToken"] = page_token
        result = api_call(lambda k=kw: service.users().messages().list(**k).execute())
        if not result:
            break
        all_ids.extend(result.get("messages", []))
        page_token = result.get("nextPageToken")
        if not page_token:
            break
        time.sleep(0.5)

    print(f"Found {len(all_ids)} RTR candidate emails")

    db_rows = load_db_records()
    conn    = sqlite3.connect(DB_PATH)

    updated = 0
    inserted = 0
    skipped  = 0

    seen_keys = set()   # deduplicate by (vendor_email, role_hash)

    for i, msg_ref in enumerate(all_ids, 1):
        try:
            msg = api_call(
                lambda m=msg_ref["id"]: service.users().messages().get(
                    userId="me", id=m, format="full"
                ).execute()
            )
            if not msg:
                continue

            rtr = parse_rtr_email(msg)
            if not rtr:
                skipped += 1
                time.sleep(0.2)
                continue

            key = (rtr["vendor_email"], rtr["role"][:30])
            if key in seen_keys:
                time.sleep(0.2)
                continue
            seen_keys.add(key)

            match = find_match(rtr, db_rows)
            if match:
                update_record(match["id"], rtr, conn)
                print(f"  Updated  #{match['id']} | {rtr['vendor_email']} | {rtr['role'][:50]} | {rtr['rate']}")
                updated += 1
            else:
                new_id = insert_new_record(rtr, conn)
                print(f"  Inserted #{new_id} | {rtr['vendor_email']} | {rtr['role'][:50]} | {rtr['rate']}")
                inserted += 1

        except Exception as e:
            print(f"  Error on {msg_ref['id']}: {e}")

        if i % 20 == 0:
            conn.commit()
        time.sleep(0.3)

    conn.commit()
    conn.close()

    print(f"\nDone. Updated={updated} | Inserted={inserted} | Skipped(not RTR)={skipped}")
    print("Run generate_tracker.py to refresh the Excel.")


if __name__ == "__main__":
    run()
