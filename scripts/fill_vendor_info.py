"""
Scan all JD texts and backfill missing vendor_contact_name, vendor_company_name,
vendor_contact_email into resumes.db.

Patterns found in JDs:
  A) From:\n  Name,\n  Company\n  email@co.com
  B) Email: email@co.com  (then search near it for name / company)
  C) Greetings from Company,
  D) First line = company name, second line = email (e.g. StellarIT Solutions\nsridhar@...)
  E) Fallback: derive name/company from email address
"""

import sys, os, sqlite3, re

BASE    = os.path.join(os.path.dirname(__file__), "..")
DB_PATH = os.path.join(BASE, "backend", "data", "resumes.db")

EMAIL_RE = re.compile(r'\b([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})\b')

# Domains/addresses to ignore (our own or noise)
IGNORE_EMAILS = {"tejamahesh33333@gmail.com", "tejamahesh23@gmail.com",
                  "ababhishek344@gmail.com"}
# Only ignore URLs/our own; allow personal gmail vendors — they exist
IGNORE_DOMAINS = {"nvoids.com", "bit.ly"}


def is_valid_vendor_email(email: str) -> bool:
    e = email.lower().strip()
    if e in IGNORE_EMAILS:
        return False
    domain = e.split("@")[1] if "@" in e else ""
    return domain not in IGNORE_DOMAINS


def find_email_in_lines(lines: list[str]) -> tuple[str, int]:
    """Return (email, line_index) for the first vendor email found."""
    # Prefer explicit "Email: x" line
    for i, line in enumerate(lines):
        m = re.match(r'^Email\s*[:\s]\s*(.+@.+\..+)', line, re.I)
        if m:
            e = m.group(1).strip()
            if is_valid_vendor_email(e):
                return e, i
    # Then bare email lines
    for i, line in enumerate(lines):
        m = EMAIL_RE.search(line)
        if m and is_valid_vendor_email(m.group(1)):
            return m.group(1), i
    return "", -1


def extract_vendor(jd_text: str) -> tuple[str, str, str]:
    """
    Returns (vendor_name, vendor_company, vendor_email).
    Empty string for any field that can't be determined.
    """
    if not jd_text:
        return "", "", ""

    lines = [l.strip() for l in jd_text.split("\n") if l.strip()]

    email, email_idx = find_email_in_lines(lines)
    name = ""
    company = ""

    # ── Pattern A: explicit "From:" block ─────────────────────────────────
    for i, line in enumerate(lines):
        if re.match(r'^From\s*:?\s*$', line, re.I):
            candidates = lines[i + 1: i + 5]
            for part in candidates:
                if re.match(r'^(http|Reply\s*to|www\.)', part, re.I):
                    break
                if EMAIL_RE.search(part):
                    break
                cleaned = part.rstrip(",").strip()
                if not cleaned:
                    continue
                if not name:
                    name = cleaned
                elif not company:
                    company = cleaned
                    break
            break

    # ── Pattern B: Greetings from Company ────────────────────────────────
    if not company:
        for line in lines:
            m = re.match(r'^Greetings\s+from\s+([^,\n]+)', line, re.I)
            if m:
                candidate = m.group(1).strip().rstrip(",")
                # Skip if it looks like a personal name (single word / 2 words no Inc/LLC)
                if re.search(r'\b(inc|llc|ltd|corp|solutions|systems|technologies|tech|group|services|consulting|staffing|global|soft)\b',
                              candidate, re.I):
                    company = candidate
                break

    # ── Pattern C: first-line = company, second-line = email ────────────
    if not company and not name and email_idx == 1:
        first = lines[0]
        # Not a job title line
        if not re.search(
            r'\b(engineer|developer|architect|devops|sre|lead|manager|analyst|'
            r'consultant|specialist|senior|junior|sr\.|jr\.|immediate|hiring|need|onsite|remote)\b',
            first, re.I
        ):
            company = first

    # ── Pattern D: "This is <Name> from <Company>" ───────────────────────
    if not name or not company:
        for line in lines:
            m = re.match(
                r'^(?:This\s+is\s+|I\s+am\s+|My\s+name\s+is\s+)'
                r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)'
                r'(?:\s*[,\s]+(?:from|at|with)\s+([^,.]+))?',
                line
            )
            if m:
                if not name:
                    name = m.group(1).strip()
                if not company and m.group(2):
                    company = m.group(2).strip()
                break

    # ── Pattern E: "Hi, I'm <Name> / recruiter at <Company>" ────────────
    if not company:
        for line in lines:
            m = re.search(
                r'(?:recruiter|talent\s+acquisition|hr|from|at|with)\s+'
                r'([A-Z][A-Za-z0-9\s&]+(?:Inc|LLC|Ltd|Corp|Solutions|Systems|Technologies|Tech|Group|Services|Consulting|Staffing|Global|Soft)\b)',
                line
            )
            if m:
                company = m.group(1).strip()
                break

    # ── Pattern F: company in job-board title "Role - COMPANY - Location | Site" ──
    if not company and lines:
        title = lines[0]
        # e.g. "DevOps Engineer - Remote - VIVA USA INC - Remote | Dice.com"
        m = re.search(
            r'-\s+([A-Z][A-Za-z0-9\s&]+(?:Inc|LLC|Ltd|Corp|Solutions|Systems|Technologies|Tech|Group|Services|Consulting|Staffing|Global)\b)',
            title
        )
        if m:
            company = m.group(1).strip()

    # ── Pattern G: bare first-line email (no "Email:" prefix) ────────────
    if not email and lines:
        m = EMAIL_RE.match(lines[0])
        if m and is_valid_vendor_email(m.group(1)):
            email = m.group(1)

    # ── Fallbacks from email ──────────────────────────────────────────────
    if email:
        local  = email.split("@")[0]
        domain = email.split("@")[1]
        domain_base = domain.split(".")[0]

        # Name from local part if still missing
        if not name:
            parts = re.split(r'[.\-_]', local)
            name = " ".join(p.capitalize() for p in parts if p and not p.isdigit())

        # Company from domain base if still missing
        if not company:
            # Clean common suffixes
            base = re.sub(r'(inc|llc|ltd|corp|tech|soft|sys|group|sol|srv|it)$', '', domain_base, flags=re.I)
            company = base.title() if base else domain_base.title()

    return name.strip(), company.strip(), email.strip()


def run():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur  = conn.cursor()

    cur.execute("""
        SELECT id, vendor_contact_name, vendor_company_name, vendor_contact_email, jd_text
        FROM resumes
        WHERE jd_text IS NOT NULL AND jd_text != ''
          AND (
              vendor_contact_name  IS NULL OR vendor_contact_name  = '' OR
              vendor_company_name  IS NULL OR vendor_company_name  = '' OR
              vendor_contact_email IS NULL OR vendor_contact_email = ''
          )
    """)
    rows = cur.fetchall()
    print(f"Records to enrich: {len(rows)}")

    updated = 0
    for row in rows:
        existing_name  = (row["vendor_contact_name"]  or "").strip()
        existing_co    = (row["vendor_company_name"]   or "").strip()
        existing_email = (row["vendor_contact_email"]  or "").strip()

        ex_name, ex_co, ex_email = extract_vendor(row["jd_text"])

        new_name  = existing_name  or ex_name
        new_co    = existing_co    or ex_co
        new_email = existing_email or ex_email

        if new_name != existing_name or new_co != existing_co or new_email != existing_email:
            cur.execute("""
                UPDATE resumes
                SET vendor_contact_name  = ?,
                    vendor_company_name  = ?,
                    vendor_contact_email = ?
                WHERE id = ?
            """, (new_name, new_co, new_email, row["id"]))
            updated += 1

    conn.commit()
    conn.close()
    print(f"Updated {updated} records.")

    # Quick verification
    conn2 = sqlite3.connect(DB_PATH)
    cur2  = conn2.cursor()
    cur2.execute("""
        SELECT
          SUM(CASE WHEN vendor_contact_name  = '' OR vendor_contact_name  IS NULL THEN 1 ELSE 0 END) as no_name,
          SUM(CASE WHEN vendor_company_name  = '' OR vendor_company_name  IS NULL THEN 1 ELSE 0 END) as no_co,
          SUM(CASE WHEN vendor_contact_email = '' OR vendor_contact_email IS NULL THEN 1 ELSE 0 END) as no_email,
          COUNT(*) as total
        FROM resumes
    """)
    r = cur2.fetchone()
    conn2.close()
    print(f"After: {r[3]} total | still missing name={r[0]} | company={r[1]} | email={r[2]}")


if __name__ == "__main__":
    run()
