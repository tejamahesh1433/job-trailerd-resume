import os
import json
import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

DATA_DIR = os.getenv("DATA_DIR", "data")
TOKENS_FILE = os.path.join(DATA_DIR, "gmail_tokens.json")
# gmail.modify is a DELIBERATE, narrower step up from readonly+compose — it's what
# actually backs the organize features (labels, archive, mark-read) below. It does NOT
# include permanent delete or send-as-anyone. Existing tokens granted before this was
# added won't have it until the user explicitly reconnects — see is_connected()'s
# "can_organize" flag, which the Inbox UI uses to gate the organize buttons rather than
# assuming every connected account has this scope.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.modify",
]

# Nested Gmail labels the "organize" actions apply — Gmail auto-creates the parent
# "Job" label the first time a child like "Job/Interview" is created.
JOB_LABELS = {
    "interview": "Job/Interview",
    "assessment": "Job/Assessment",
    "rejection": "Job/Rejection",
    "offer": "Job/Offer",
    "applied": "Job/Applied",
}

REDIRECT_URI = os.getenv("GMAIL_REDIRECT_URI", "http://localhost:8000/api/gmail/callback")

# "keywords" is just the boolean OR-clause for a category, kept separate from the full
# Gmail query (which also carries the newer_than window) so it can be recombined below
# into a single broad "job mail" net — see _build_inbox_query.
FILTER_DEFINITIONS = {
    "all": {"label": "All", "keywords": "", "positive": []},
    "verification": {"label": "Verification", "keywords": '(verify OR verification OR "confirm your email" OR "security code" OR OTP OR "one-time password" OR "authentication code")', "positive": ["verify", "verification", "confirm your email", "security code", "otp", "one-time password", "authentication code"]},
    "rejection": {"label": "Rejection", "keywords": '("not selected" OR "not moving forward" OR "unfortunately" OR "other candidates" OR "will not be proceeding" OR rejection OR rejected OR "move forward with other" OR "pursue other candidates" OR "decided not to")', "positive": ["not selected", "not moving forward", "unfortunately", "other candidates", "will not be proceeding", "rejection", "rejected", "after careful consideration"]},
    "interview": {"label": "Interview", "keywords": '(interview OR "phone screen" OR "technical screen" OR "schedule a call" OR calendly OR "meet with" OR "availability for a call")', "positive": ["interview", "phone screen", "technical screen", "schedule a call", "calendly", "meet with", "availability", "next round"]},
    "assessment": {"label": "Assessment", "keywords": '(assessment OR "coding challenge" OR hackerrank OR codility OR "take-home" OR "online test" OR "technical assessment" OR "complete the exercise")', "positive": ["assessment", "coding challenge", "hackerrank", "codility", "take-home", "online test", "technical assessment", "assignment"]},
    "reminder": {"label": "Reminder", "keywords": '(reminder OR "following up" OR "follow up" OR deadline OR "due date" OR "complete your application" OR "action required")', "positive": ["reminder", "following up", "follow up", "deadline", "due date", "complete your application", "action required"]},
    "offer": {"label": "Offer", "keywords": '("offer letter" OR "job offer" OR "employment offer" OR "we are pleased to offer" OR "congratulations" OR "pleased to offer")', "positive": ["offer letter", "job offer", "employment offer", "we are pleased to offer", "congratulations", "pleased to offer"]},
    "applied": {"label": "Applied", "keywords": '("application received" OR "thanks for applying" OR "thank you for applying" OR "we received your application" OR "application submitted")', "positive": ["application received", "thanks for applying", "thank you for applying", "we received your application", "application submitted", "your application"]},
}

# Combined "priority" bucket — interview/assessment/offer/reminder are the categories
# that usually need a timely response, unlike a plain rejection or applied-confirmation.
NEEDS_ATTENTION_CATEGORIES = ("interview", "assessment", "offer", "reminder")

# One shared "this looks like job mail" net used for ALL category filters (see
# _build_inbox_query) instead of each category's own narrow keyword query — a narrow
# per-category Gmail query can miss messages that phrase things differently (e.g. "we've
# decided to move forward with other candidates" instead of the literal word
# "rejected"), silently dropping them before AI ever gets a chance to classify them.
# Casting a wider net server-side and letting the batched AI call do the real filtering
# fixes that recall gap while still keeping the AI's input bounded to job-relevant mail.
_BROAD_JOB_MAIL_KEYWORDS = " OR ".join(
    v["keywords"] for k, v in FILTER_DEFINITIONS.items() if k != "all" and v["keywords"]
)


def _get_client_config():
    """Build OAuth client config from environment variables."""
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None
    return {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [REDIRECT_URI],
        }
    }


def get_auth_url() -> str:
    """Generate the Google OAuth consent URL."""
    client_config = _get_client_config()
    if not client_config:
        raise RuntimeError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set in .env")

    flow = Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=REDIRECT_URI)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
    )
    return auth_url


def handle_callback(auth_code: str) -> dict:
    """Exchange the authorization code for tokens and save them."""
    client_config = _get_client_config()
    if not client_config:
        raise RuntimeError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set")

    flow = Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=REDIRECT_URI)
    flow.fetch_token(code=auth_code)

    creds = flow.credentials
    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes),
    }

    os.makedirs(os.path.dirname(TOKENS_FILE), exist_ok=True)
    with open(TOKENS_FILE, "w") as f:
        json.dump(token_data, f)

    # A (re)connect may be a DIFFERENT Google account than whatever was connected
    # before — Gmail label ids are account-scoped, so any cached ids from a prior
    # account are invalid here and must not be reused.
    _label_id_cache.clear()

    return {"status": "connected", "email": _get_user_email(creds)}


def _get_user_email(creds: Credentials) -> str:
    """Get the authenticated user's email address."""
    try:
        service = build("gmail", "v1", credentials=creds)
        profile = service.users().getProfile(userId="me").execute()
        return profile.get("emailAddress", "")
    except Exception:
        return ""


def is_connected() -> dict:
    """Check if Gmail is connected and tokens are valid."""
    if not os.path.exists(TOKENS_FILE):
        return {"connected": False}

    try:
        creds = _load_credentials()
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                from google.auth.transport.requests import Request
                creds.refresh(Request())
                _save_credentials(creds)
            else:
                return {"connected": False}

        email = _get_user_email(creds)
        granted_scopes = list(creds.scopes or [])
        can_organize = any("gmail.modify" in s or "mail.google.com" in s for s in granted_scopes)
        return {"connected": True, "email": email, "can_organize": can_organize}
    except Exception:
        return {"connected": False}


def _load_credentials() -> Credentials:
    """Load stored credentials."""
    if not os.path.exists(TOKENS_FILE):
        return None

    with open(TOKENS_FILE, "r") as f:
        token_data = json.load(f)

    return Credentials(
        token=token_data["token"],
        refresh_token=token_data.get("refresh_token"),
        token_uri=token_data["token_uri"],
        client_id=token_data["client_id"],
        client_secret=token_data["client_secret"],
        scopes=token_data.get("scopes"),
    )


def _save_credentials(creds: Credentials):
    """Save refreshed credentials."""
    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes) if creds.scopes else [],
    }
    with open(TOKENS_FILE, "w") as f:
        json.dump(token_data, f)


def disconnect():
    """Remove stored Gmail tokens."""
    if os.path.exists(TOKENS_FILE):
        os.remove(TOKENS_FILE)
    _label_id_cache.clear()
    return {"status": "disconnected"}


MIME_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


def _attach_file(msg, file_path: str, display_name: str):
    """Attach any file to the email message."""
    ext = os.path.splitext(file_path)[1].lower()
    mime = MIME_TYPES.get(ext, "application/octet-stream")
    maintype, subtype = mime.split("/", 1)
    with open(file_path, "rb") as f:
        part = MIMEBase(maintype, subtype)
        part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{display_name}"')
        msg.attach(part)


def save_draft(to_emails: list, subject: str, body: str, attachment_path: str = None, attachments: list = None) -> dict:
    """Save an email as a draft in Gmail.

    attachments: list of dicts with 'path' and 'display_name' keys for explicit attachment control.
    attachment_path: legacy param — attaches resume + auto-discovers cover letter from company folder.
    """
    creds = _load_credentials()
    if not creds:
        raise RuntimeError("Gmail not connected. Please connect your Gmail account first.")

    if creds.expired and creds.refresh_token:
        from google.auth.transport.requests import Request
        creds.refresh(Request())
        _save_credentials(creds)

    service = build("gmail", "v1", credentials=creds)

    msg = MIMEMultipart()
    msg["To"] = ", ".join(to_emails) if to_emails else ""
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    attached_files = []

    if attachments:
        for att in attachments:
            path = att.get("path", "")
            name = att.get("display_name", os.path.basename(path))
            if path and os.path.exists(path):
                _attach_file(msg, path, name)
                attached_files.append(name)
    elif attachment_path and os.path.exists(attachment_path):
        _attach_file(msg, attachment_path, "Teja_Mahesh_Neerukonda_Resume.docx")
        attached_files.append(os.path.basename(attachment_path))

        company_dir = os.path.dirname(attachment_path)
        cl_files = [f for f in os.listdir(company_dir)
                     if f.endswith(".docx") and ("cover" in f.lower() or f.startswith("cover_letter_"))
                     and f != os.path.basename(attachment_path)]
        if cl_files:
            cl_path = os.path.join(company_dir, cl_files[0])
            _attach_file(msg, cl_path, "Teja_Mahesh_Neerukonda_Cover_Letter.docx")
            attached_files.append(cl_files[0])

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    draft = service.users().drafts().create(
        userId="me",
        body={"message": {"raw": raw}}
    ).execute()

    return {
        "draft_id": draft["id"],
        "message": "Draft saved to Gmail",
        "attachments": attached_files,
    }


def get_conversation_with_sender(sender_email: str, max_results: int = 20) -> list:
    """Fetch all emails exchanged with a specific sender, ordered chronologically."""
    creds = _load_credentials()
    if not creds:
        raise RuntimeError("Gmail not connected.")

    if creds.expired and creds.refresh_token:
        from google.auth.transport.requests import Request
        creds.refresh(Request())
        _save_credentials(creds)

    service = build("gmail", "v1", credentials=creds)

    queries = [
        f"from:{sender_email}",
        f"to:{sender_email}",
    ]

    all_msg_ids = set()
    for q in queries:
        resp = service.users().messages().list(
            userId="me", q=q, maxResults=max_results
        ).execute()
        for msg_stub in resp.get("messages", []):
            all_msg_ids.add(msg_stub["id"])

    conversations = []
    for msg_id in all_msg_ids:
        msg = service.users().messages().get(
            userId="me", id=msg_id, format="full"
        ).execute()
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        body_text = _extract_body(msg.get("payload", {}))
        conversations.append({
            "id": msg_id,
            "from": headers.get("From", ""),
            "to": headers.get("To", ""),
            "subject": headers.get("Subject", ""),
            "date": headers.get("Date", ""),
            "body": body_text,
            "timestamp": int(msg.get("internalDate", 0)),
        })

    conversations.sort(key=lambda m: m["timestamp"])
    return conversations


def _message_category(subject: str, snippet: str) -> dict:
    text = f"{subject or ''} {snippet or ''}".lower()
    best_key = "all"
    best_score = 0
    for key, definition in FILTER_DEFINITIONS.items():
        if key == "all":
            continue
        score = sum(1 for phrase in definition["positive"] if phrase in text)
        if score > best_score:
            best_key = key
            best_score = score
    return {
        "key": best_key,
        "label": FILTER_DEFINITIONS.get(best_key, FILTER_DEFINITIONS["all"])["label"],
        "confidence": min(0.95, 0.45 + (best_score * 0.2)) if best_score else 0.3,
        "method": "local-rules",
    }


def _build_inbox_query(query: str, category: str) -> str:
    category_key = (category or "all").lower()
    if category_key == "all":
        base = "in:anywhere newer_than:180d"
    elif category_key == "needs_attention":
        needs_attention_keywords = " OR ".join(FILTER_DEFINITIONS[k]["keywords"] for k in NEEDS_ATTENTION_CATEGORIES)
        base = f"({needs_attention_keywords}) newer_than:365d"
    else:
        # Broad job-mail net for ALL specific-category filters — the AI classification
        # pass does the real narrowing (see main.py's /api/gmail/inbox), so this query
        # only needs to rule out obviously-unrelated mail, not guess the exact category.
        base = f"({_BROAD_JOB_MAIL_KEYWORDS}) newer_than:365d"
    user_query = (query or "").strip()
    if user_query:
        return f"({base}) {user_query}"
    return base


def list_inbox_filters() -> list:
    filters = [{"key": key, "label": value["label"]} for key, value in FILTER_DEFINITIONS.items()]
    filters.insert(1, {"key": "needs_attention", "label": "Needs Attention"})
    return filters


def search_inbox(query: str, max_results: int = 15, category: str = "all", page_token: str = None) -> dict:
    """Search Gmail and return classified message summaries plus a next_page_token for
    'Load more' (None when there are no further results)."""
    creds = _load_credentials()
    if not creds:
        raise RuntimeError("Gmail not connected.")

    if creds.expired and creds.refresh_token:
        from google.auth.transport.requests import Request
        creds.refresh(Request())
        _save_credentials(creds)

    stored_scopes = list(creds.scopes or [])
    if not any("gmail.readonly" in s or "mail.google.com" in s for s in stored_scopes):
        raise RuntimeError(
            "Inbox read permission missing. Please disconnect Gmail and reconnect to grant inbox access."
        )

    service = build("gmail", "v1", credentials=creds)
    try:
        list_kwargs = {"userId": "me", "q": _build_inbox_query(query, category), "maxResults": max_results}
        if page_token:
            list_kwargs["pageToken"] = page_token
        resp = service.users().messages().list(**list_kwargs).execute()
    except Exception as e:
        err_str = str(e)
        if "insufficientPermissions" in err_str or "forbidden" in err_str.lower() or "403" in err_str:
            raise RuntimeError(
                "Inbox read permission denied by Google. Please disconnect Gmail and reconnect to grant inbox access."
            )
        raise

    messages = []
    for msg_stub in resp.get("messages", []):
        msg = service.users().messages().get(
            userId="me", id=msg_stub["id"], format="metadata",
            metadataHeaders=["From", "Subject", "Date"]
        ).execute()
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        category_info = _message_category(headers.get("Subject", ""), msg.get("snippet", ""))
        messages.append({
            "id": msg_stub["id"],
            "thread_id": msg.get("threadId", ""),
            "from": headers.get("From", ""),
            "subject": headers.get("Subject", ""),
            "date": headers.get("Date", ""),
            "snippet": msg.get("snippet", ""),
            "category": category_info["key"],
            "category_label": category_info["label"],
            "category_confidence": category_info["confidence"],
            "classified_by": category_info["method"],
        })

    return {"messages": messages, "next_page_token": resp.get("nextPageToken")}


def get_message_body(message_id: str) -> dict:
    """Get the full plain-text body of a Gmail message."""
    creds = _load_credentials()
    if not creds:
        raise RuntimeError("Gmail not connected.")

    if creds.expired and creds.refresh_token:
        from google.auth.transport.requests import Request
        creds.refresh(Request())
        _save_credentials(creds)

    service = build("gmail", "v1", credentials=creds)
    msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}

    body_text = _extract_body(msg.get("payload", {}))

    return {
        "id": message_id,
        "thread_id": msg.get("threadId", ""),
        "from": headers.get("From", ""),
        "subject": headers.get("Subject", ""),
        "date": headers.get("Date", ""),
        "body": body_text,
    }


def get_thread_messages(thread_id: str) -> list:
    """Fetch every message in a Gmail conversation thread, oldest first — used for the
    Inbox's thread view so a recruiter conversation shows as a conversation, not just
    whichever single message the user clicked."""
    creds = _load_credentials()
    if not creds:
        raise RuntimeError("Gmail not connected.")

    if creds.expired and creds.refresh_token:
        from google.auth.transport.requests import Request
        creds.refresh(Request())
        _save_credentials(creds)

    service = build("gmail", "v1", credentials=creds)
    thread = service.users().threads().get(userId="me", id=thread_id, format="full").execute()

    messages = []
    for msg in thread.get("messages", []):
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        messages.append({
            "id": msg.get("id", ""),
            "from": headers.get("From", ""),
            "subject": headers.get("Subject", ""),
            "date": headers.get("Date", ""),
            "body": _extract_body(msg.get("payload", {})),
            "timestamp": int(msg.get("internalDate", 0) or 0),
        })
    messages.sort(key=lambda m: m["timestamp"])
    return messages


def _get_organize_service():
    """Shared setup for the organize actions below — raises the same clear
    'reconnect to grant X' RuntimeErrors as search_inbox does for read access, but
    checked against gmail.modify specifically since that's a separate, later-added
    scope existing tokens may not have."""
    creds = _load_credentials()
    if not creds:
        raise RuntimeError("Gmail not connected.")
    if creds.expired and creds.refresh_token:
        from google.auth.transport.requests import Request
        creds.refresh(Request())
        _save_credentials(creds)
    stored_scopes = list(creds.scopes or [])
    if not any("gmail.modify" in s or "mail.google.com" in s for s in stored_scopes):
        raise RuntimeError(
            "Organize permission (labels/archive/mark-read) missing. Please disconnect Gmail and reconnect to grant it."
        )
    return build("gmail", "v1", credentials=creds)


_label_id_cache = {}


def _get_or_create_label_id(service, label_name: str) -> str:
    """Resolve a (possibly nested, e.g. 'Job/Interview') label name to its id, creating
    it — and any missing parent label — if it doesn't exist yet. Gmail requires parent
    labels to exist before a child can be created under them."""
    if label_name in _label_id_cache:
        return _label_id_cache[label_name]

    existing = service.users().labels().list(userId="me").execute().get("labels", [])
    by_name = {l["name"]: l["id"] for l in existing}
    if label_name in by_name:
        _label_id_cache[label_name] = by_name[label_name]
        return by_name[label_name]

    # Create any missing ancestor first (e.g. "Job" before "Job/Interview").
    if "/" in label_name:
        parent = label_name.rsplit("/", 1)[0]
        if parent not in by_name:
            _get_or_create_label_id(service, parent)

    created = service.users().labels().create(userId="me", body={
        "name": label_name, "labelListVisibility": "labelShow", "messageListVisibility": "show",
    }).execute()
    _label_id_cache[label_name] = created["id"]
    return created["id"]


def apply_job_label(message_id: str, category: str) -> dict:
    """Apply the Job/<Category> label for a classified message — e.g. category
    'interview' -> label 'Job/Interview'. Creates the label on first use."""
    label_name = JOB_LABELS.get(category)
    if not label_name:
        raise ValueError(f"No label mapped for category '{category}'")
    service = _get_organize_service()
    label_id = _get_or_create_label_id(service, label_name)
    service.users().messages().modify(userId="me", id=message_id, body={"addLabelIds": [label_id]}).execute()
    return {"status": "labeled", "label": label_name}


def archive_message(message_id: str) -> dict:
    """Remove a message from the inbox view (Gmail 'archive') without deleting it."""
    service = _get_organize_service()
    service.users().messages().modify(userId="me", id=message_id, body={"removeLabelIds": ["INBOX"]}).execute()
    return {"status": "archived"}


def mark_message_read(message_id: str) -> dict:
    service = _get_organize_service()
    service.users().messages().modify(userId="me", id=message_id, body={"removeLabelIds": ["UNREAD"]}).execute()
    return {"status": "read"}


def _find_part_by_mimetype(payload: dict, mimetype: str) -> str:
    """Recursively search a Gmail message payload for the first part matching mimetype,
    returning its decoded content, or "" if none exists anywhere in the tree."""
    if payload.get("mimeType") == mimetype and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
    for part in payload.get("parts", []):
        text = _find_part_by_mimetype(part, mimetype)
        if text:
            return text
    return ""


def _html_to_text(html: str) -> str:
    """Strip an HTML email body down to readable plain text — many recruiter/ATS/
    marketing emails have no text/plain alternative at all, only text/html, so without
    this the reader panel would show raw markup instead of the message."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    lines = [line.strip() for line in soup.get_text(separator="\n").splitlines()]
    return "\n".join(line for line in lines if line)


def _extract_body(payload: dict) -> str:
    """Extract a readable plain-text body from a Gmail message payload. Searches the
    WHOLE part tree for an actual text/plain part first (regardless of part order) —
    the old version could return raw HTML if a text/html part happened to come first or
    be the only part. Falls back to converting text/html to plain text."""
    plain = _find_part_by_mimetype(payload, "text/plain")
    if plain:
        return plain

    html = _find_part_by_mimetype(payload, "text/html")
    if html:
        return _html_to_text(html)

    if payload.get("body", {}).get("data"):
        raw = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
        return _html_to_text(raw) if payload.get("mimeType") == "text/html" else raw

    return ""


