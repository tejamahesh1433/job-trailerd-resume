"""
Generate a multi-sheet Excel job application tracker from resumes.db,
enriched with Rate/Hr pulled from Gmail (tejamahesh33333@gmail.com).

Sheets: Applied | Submitted | Phone Screen | Shortlisted | Matched | Scanned | Rejected | Found | All Records
Columns: S.No | Day | Date | Role | Vendor Name | Vendor Company | Rate/Hr | End Client | Contact | Updates
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import sqlite3, json, re, time
from datetime import datetime
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# ── paths ──────────────────────────────────────────────────────────────────
BASE     = os.path.join(os.path.dirname(__file__), "..")
DB_PATH  = os.path.join(BASE, "backend", "data", "resumes.db")
OUT_PATH = os.path.join(BASE, "backend", "data", "job_tracker.xlsx")
RATE_CACHE_PATH = os.path.join(BASE, "backend", "data", "gmail_rate_cache.json")

DAYS = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]

SHEET_MAP = [
    ("Applied",           "Applied",       "2196F3"),
    ("Submitted Profile", "Submitted",      "9C27B0"),
    ("Phone Screen",      "Phone Screen",   "FF9800"),
    ("Shortlisted",       "Shortlisted",    "4CAF50"),
    ("Matched",           "Matched",        "00BCD4"),
    ("Scanned",           "Scanned",        "607D8B"),
    ("Rejected",          "Rejected",       "F44336"),
    ("Found",             "Found",          "9E9E9E"),
    ("ALL",               "All Records",    "212121"),
]

HEADERS    = ["S.No","Day","Date","Role","Vendor Name","Vendor Company","Rate/Hr","End Client","Company Location","My Location","Contact Number","Updates"]
COL_WIDTHS = [7, 12, 14, 42, 22, 28, 11, 32, 26, 28, 22, 38]

HDR_FILL  = PatternFill("solid", fgColor="1A237E")
HDR_FONT  = Font(bold=True, color="FFFFFF", name="Calibri", size=11)
EVEN_FILL = PatternFill("solid", fgColor="E8EAF6")
ODD_FILL  = PatternFill("solid", fgColor="FFFFFF")
BS        = Side(style="thin", color="B0BEC5")
CBORDER   = Border(left=BS, right=BS, top=BS, bottom=BS)
CFONT     = Font(name="Calibri", size=10)
CALIGN    = Alignment(wrap_text=True, vertical="top")


# ── rate extraction helpers ────────────────────────────────────────────────

RATE_RE = re.compile(
    r"(?:rate|pay|compensation|bill(?:ing)?\s*rate|salary)[\s:]*\$?\s*(\d{2,3}(?:\.\d{1,2})?)\s*/?\s*h(?:ou)?r"
    r"|\$\s*(\d{2,3}(?:\.\d{1,2})?)\s*/?\s*h(?:ou)?r"
    r"|(\d{2,3}(?:\.\d{1,2})?)\s*dollars?\s*/?\s*h(?:ou)?r",
    re.I
)

def _extract_rate_from_text(text: str) -> str:
    if not text:
        return ""
    for m in RATE_RE.finditer(text):
        val = m.group(1) or m.group(2) or m.group(3)
        if val:
            f = float(val)
            if 20 <= f <= 250:          # sanity filter
                return f"${val}/hr"
    return ""

def extract_rate_from_jd(jd_text: str, user_notes: str) -> str:
    combined = " ".join(filter(None, [jd_text or "", user_notes or ""]))
    return _extract_rate_from_text(combined)


# ── Gmail rate enrichment ──────────────────────────────────────────────────

def _get_gmail_service():
    try:
        os.environ.setdefault("DATA_DIR", os.path.join(BASE, "backend", "data"))
        from services.gmail_service import _load_credentials, _save_credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        creds = _load_credentials()
        if not creds:
            return None
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                _save_credentials(creds)
            else:
                return None
        return build("gmail", "v1", credentials=creds)
    except Exception as e:
        print(f"  [Gmail] could not connect: {e}")
        return None


def _decode_body(payload: dict) -> str:
    """Recursively decode email body to plain text."""
    mime = payload.get("mimeType", "")
    if mime == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            import base64
            return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore")
    if mime.startswith("multipart/"):
        for part in payload.get("parts", []):
            t = _decode_body(part)
            if t:
                return t
    return ""


def _api_call(fn, max_retries=5):
    """Exponential backoff on Gmail quota errors."""
    import googleapiclient.errors
    delay = 3.0
    for attempt in range(max_retries):
        try:
            return fn()
        except googleapiclient.errors.HttpError as e:
            if e.status_code in (429, 403) and attempt < max_retries - 1:
                wait = delay * (2 ** attempt)
                print(f"    [quota] sleeping {wait:.0f}s...")
                time.sleep(wait)
            else:
                raise
    return None


def _get_header(headers: list, name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def build_gmail_rate_cache(records: list[dict]) -> dict:
    """
    Strategy: ONE broad Gmail search for all emails mentioning a rate,
    then match each result back to known vendor emails.
    This is ~1 API list call + N message fetches instead of 348 separate searches.
    """
    cache: dict = {}
    if os.path.exists(RATE_CACHE_PATH):
        with open(RATE_CACHE_PATH) as f:
            cache = json.load(f)

    service = _get_gmail_service()
    if not service:
        print("  [Gmail] not connected -- skipping rate enrichment.")
        return cache

    # Build lookup set of all known vendor emails
    known_emails = set()
    for rec in records:
        e = (rec.get("vendor_contact_email") or "").strip().lower()
        if e:
            known_emails.add(e)

    # Broad single query -- hits all job emails that mention a rate/pay/$/hr
    RATE_QUERY = (
        '("per hour" OR "/hr" OR "$/hr" OR "bill rate" OR "pay rate" OR "rate/hr"'
        ' OR "hourly rate" OR "compensation") newer_than:18m'
    )

    print("  [Gmail] one broad rate search across inbox (no per-email loops)...")
    all_ids = []
    page_token = None
    while True:
        kw = dict(userId="me", q=RATE_QUERY, maxResults=500)
        if page_token:
            kw["pageToken"] = page_token
        result = _api_call(lambda k=kw: service.users().messages().list(**k).execute())
        if not result:
            break
        all_ids.extend(result.get("messages", []))
        page_token = result.get("nextPageToken")
        if not page_token or len(all_ids) >= 3000:
            break
        time.sleep(0.5)

    print(f"  [Gmail] {len(all_ids)} candidate messages -- extracting rates...")
    found_count = 0

    for i, msg_ref in enumerate(all_ids, 1):
        mid = msg_ref["id"]
        try:
            msg = _api_call(
                lambda m=mid: service.users().messages().get(
                    userId="me", id=m, format="full"
                ).execute()
            )
            if not msg:
                continue

            headers  = msg.get("payload", {}).get("headers", [])
            from_hdr = _get_header(headers, "From").lower()
            to_hdr   = _get_header(headers, "To").lower()
            addr_str = from_hdr + " " + to_hdr

            matched = next((e for e in known_emails if e in addr_str), None)
            if not matched or cache.get(matched):
                time.sleep(0.2)
                continue

            snippet = msg.get("snippet", "")
            rate = _extract_rate_from_text(snippet)
            if not rate:
                body = _decode_body(msg.get("payload", {}))
                rate = _extract_rate_from_text(body)

            if rate:
                cache[matched] = rate
                found_count += 1
                print(f"    {matched} -> {rate}")

        except Exception as e:
            print(f"    [Gmail] msg {mid} error: {e}")

        # Save progress every 30 messages; brief pause to respect quota
        if i % 30 == 0:
            with open(RATE_CACHE_PATH, "w") as f:
                json.dump(cache, f, indent=2)
        time.sleep(0.3)

    with open(RATE_CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2)

    print(f"  [Gmail] done. {found_count} rates found from {len(all_ids)} emails.")
    return cache


# ── DB load ────────────────────────────────────────────────────────────────

def load_records() -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT id, company_name, vendor_company_name, vendor_contact_name,
               vendor_contact_email, vendor_contact_phone, created_at, status,
               user_notes, jd_text, scan_result, user_address
        FROM resumes
        WHERE source != 'command-center' OR source IS NULL
        ORDER BY created_at ASC
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


LOCATION_RE = re.compile(
    r'^(?:work\s+)?loc(?:ation)?\s*[:\-]\s*(.+)'
    r'|^(?:job\s+)?loc(?:ation)?\s*[:\-]\s*(.+)'
    r'|^(?:position\s+)?loc(?:ation)?\s*[:\-]\s*(.+)',
    re.I
)
REMOTE_RE = re.compile(r'\b(100\s*%\s*remote|fully\s+remote|remote\s+only|remote)\b', re.I)
LOCAL_RE  = re.compile(
    r'(?:need|must\s+be|only|require[sd]?|looking\s+for|prefer)\s+local'
    r'|local\s+(?:to|candidates|only|required|prefer)'
    r'|locals?\s+only'
    r'|near\s*by\s+state',
    re.I
)

# State abbreviation → canonical address
STATE_ADDRESSES = {
    "CT": "68 Front Ave, West Haven, CT 06516",
    "PA": "2907 Stonecliffe Dr, Monroeville, PA 15146",
    "FL": "2925 Ybor St, Tampa, FL 33605",
    "NC": "320 S Torrence St, Charlotte, NC 28204",
    "TN": "3449 Mayflower Ave, Memphis, TN 38122",
    "MI": "4375 Alvin St, Saginaw, MI 48603",
    "CA": "465 N 3rd St, San Jose, CA 95112",
    "VA": "603 W 24th St, Richmond, VA 23225",
    "NJ": "710 Green Hollow Dr, Iselin, NJ 08830",
    "TX": "727 Lipscomb Ave, Dallas, TX 75214",
}
DEFAULT_REMOTE_ADDR = STATE_ADDRESSES["CT"]   # pure remote → West Haven CT

# Full state names → abbreviation
STATE_NAME_MAP = {
    "connecticut": "CT", "pennsylvania": "PA", "florida": "FL",
    "north carolina": "NC", "tennessee": "TN", "michigan": "MI",
    "california": "CA", "virginia": "VA", "new jersey": "NJ",
    "texas": "TX", "new york": "NY", "ohio": "OH",
    "illinois": "IL", "georgia": "GA", "maryland": "MD",
    "massachusetts": "MA", "washington": "WA", "colorado": "CO",
    "arizona": "AZ", "minnesota": "MN", "missouri": "MO",
}


def _state_abbr(text: str) -> str:
    """Extract the best state abbreviation from a location string."""
    if not text:
        return ""
    # Look for 2-letter state code
    m = re.search(r'\b([A-Z]{2})\b', text)
    if m:
        candidate = m.group(1)
        if candidate in STATE_ADDRESSES or candidate in {
            "NY","OH","IL","GA","MD","MA","WA","CO","AZ","MN","MO","SC","WI","IN","KY","OR","OK","AR","MS","AL","IA","KS","NE","NM","NV","ID","NH","ME","MT","ND","SD","WY","VT","DE","RI","AK","HI","WV","UT"}:
            return candidate
    # Full name
    lower = text.lower()
    for name, abbr in STATE_NAME_MAP.items():
        if name in lower:
            return abbr
    return ""


def extract_company_location(jd_text: str) -> str:
    """Pull location line from JD text."""
    if not jd_text:
        return ""
    for line in jd_text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = LOCATION_RE.match(line)
        if m:
            loc = (m.group(1) or m.group(2) or m.group(3) or "").strip()
            loc = re.sub(r'\s*(–|-)\s*(Hybrid|Onsite|Remote|Contract|C2C|W2).*$', '', loc, flags=re.I).strip()
            if loc and len(loc) < 80:
                return loc
    # Fallback: first line that looks like "City, ST" or contains Remote/Onsite
    for line in jd_text.splitlines():
        line = line.strip()
        if not line or len(line) > 80:
            continue
        if re.search(r'\b[A-Z]{2}\b', line) and ',' in line:
            if not re.match(r'^(http|www|email|from|reply|job|title|duration|dear|hi|hello)', line, re.I):
                return line[:80]
        if REMOTE_RE.search(line) and len(line) < 40:
            return line
    return ""


def pick_my_location(jd_text: str, company_location: str, stored_address: str) -> str:
    """
    Smart 'My Location' picker:
      - If stored address already set → keep it (user manually chose it)
      - Pure remote, no local requirement → West Haven CT
      - Remote with local-to-STATE requirement → that state's address
      - Onsite / hybrid → match state from company_location
      - No match found → blank
    """
    if stored_address:
        return stored_address

    jd = jd_text or ""
    is_remote  = bool(REMOTE_RE.search(jd)) or "remote" in (company_location or "").lower()
    needs_local = bool(LOCAL_RE.search(jd))

    if is_remote and not needs_local:
        return DEFAULT_REMOTE_ADDR

    # Determine the target state
    target_state = ""

    if needs_local:
        # Look for explicit "local to TX/CA/VA/NJ" pattern
        m = re.search(r'local\s+(?:to|in|for)\s+([A-Z]{2}(?:/[A-Z]{2})*)', jd)
        if m:
            # Could be "VA/TX" — pick first one we have an address for
            for st in m.group(1).split("/"):
                if st in STATE_ADDRESSES:
                    target_state = st
                    break
        if not target_state:
            # Extract from company_location
            target_state = _state_abbr(company_location)
        if not target_state:
            # Extract from first location-like line in JD
            target_state = _state_abbr(jd[:500])

    if not target_state and not is_remote:
        # Onsite/hybrid → use company location state
        target_state = _state_abbr(company_location)
        if not target_state:
            target_state = _state_abbr(jd[:500])

    if target_state and target_state in STATE_ADDRESSES:
        return STATE_ADDRESSES[target_state]

    # Have a state but no address → return blank (don't guess wrong address)
    return ""


def extract_role(jd_text: str) -> str:
    if not jd_text:
        return ""
    for line in jd_text.splitlines():
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"^(Contract\s*[-–—]+\s*|RE:\s*|FW:\s*)", "", line, flags=re.I)
        if re.match(r"^(http|www|email:|reply)", line, re.I):
            continue
        if len(line) > 10:
            return line[:120]
    return ""


def row_to_cols(rec: dict, sno: int, rate_cache: dict) -> list:
    ts = rec.get("created_at", "")
    try:
        dt  = datetime.fromisoformat(ts)
        day = DAYS[dt.weekday()]
        date = dt.strftime("%Y-%m-%d")
    except Exception:
        day, date = "", ts[:10]

    jd   = rec.get("jd_text") or ""
    role = extract_role(jd)

    # Rate: JD text first, then Gmail cache
    rate = extract_rate_from_jd(jd, rec.get("user_notes"))
    if not rate:
        email_key = (rec.get("vendor_contact_email") or "").strip().lower()
        rate = rate_cache.get(email_key, "")

    vendor_name    = (rec.get("vendor_contact_name")  or "").strip()
    vendor_company = (rec.get("vendor_company_name")   or "").strip()
    end_client     = (rec.get("company_name")          or "").strip()

    company_location = extract_company_location(jd)
    my_location      = pick_my_location(jd, company_location, (rec.get("user_address") or "").strip())

    phone   = (rec.get("vendor_contact_phone") or "").strip()
    email   = (rec.get("vendor_contact_email") or "").strip()
    contact = phone if phone else email

    updates = (rec.get("user_notes") or "").strip()

    return [sno, day, date, role, vendor_name, vendor_company,
            rate, end_client, company_location, my_location, contact, updates]


# ── Excel building ─────────────────────────────────────────────────────────

def add_header(ws):
    ws.row_dimensions[1].height = 28
    for ci, (h, w) in enumerate(zip(HEADERS, COL_WIDTHS), 1):
        c = ws.cell(row=1, column=ci, value=h)
        c.fill = HDR_FILL; c.font = HDR_FONT; c.border = CBORDER
        c.alignment = Alignment(horizontal="center", vertical="center")
        ws.column_dimensions[get_column_letter(ci)].width = w


def add_rows(ws, records: list[dict], rate_cache: dict):
    for ri, rec in enumerate(records, 1):
        cols = row_to_cols(rec, ri, rate_cache)
        fill = EVEN_FILL if ri % 2 == 0 else ODD_FILL
        ws.row_dimensions[ri + 1].height = 36
        for ci, val in enumerate(cols, 1):
            c = ws.cell(row=ri + 1, column=ci, value=val)
            c.fill = fill; c.font = CFONT; c.border = CBORDER; c.alignment = CALIGN


def build():
    print("Loading records from DB...")
    all_records = load_records()
    print(f"  {len(all_records)} total records")

    print("Enriching Rate/Hr from Gmail...")
    rate_cache = build_gmail_rate_cache(all_records)

    # Group by status
    groups: dict[str, list] = {}
    for rec in all_records:
        s = rec.get("status") or "Unknown"
        groups.setdefault(s, []).append(rec)

    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    for db_status, sheet_name, tab_color in SHEET_MAP:
        recs = all_records if db_status == "ALL" else groups.get(db_status, [])
        ws = wb.create_sheet(title=sheet_name)
        ws.sheet_properties.tabColor = tab_color
        add_header(ws)
        add_rows(ws, recs, rate_cache)
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        ws["M1"] = f"Total: {len(recs)}"
        ws["M1"].font  = Font(bold=True, color="FFFFFF", name="Calibri", size=10)
        ws["M1"].fill  = HDR_FILL
        ws["M1"].alignment = Alignment(horizontal="center", vertical="center")
        ws.column_dimensions["M"].width = 14

    out = OUT_PATH
    try:
        wb.save(out)
    except PermissionError:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = OUT_PATH.replace(".xlsx", f"_{ts}.xlsx")
        wb.save(out)
        print(f"  (job_tracker.xlsx was open in Excel — saved as alternate name)")
    print(f"\nSaved -> {out}")
    for db_status, sheet_name, _ in SHEET_MAP:
        cnt = len(all_records) if db_status == "ALL" else len(groups.get(db_status, []))
        print(f"  {sheet_name:<22} {cnt} records")


if __name__ == "__main__":
    build()
