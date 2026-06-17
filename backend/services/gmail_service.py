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
SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]

REDIRECT_URI = os.getenv("GMAIL_REDIRECT_URI", "http://localhost:8000/api/gmail/callback")


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
        return {"connected": True, "email": email}
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
    return {"status": "disconnected"}


def _attach_docx(msg, file_path: str, display_name: str):
    """Attach a .docx file to the email message."""
    with open(file_path, "rb") as f:
        part = MIMEBase("application", "vnd.openxmlformats-officedocument.wordprocessingml.document")
        part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{display_name}"')
        msg.attach(part)


def save_draft(to_emails: list, subject: str, body: str, attachment_path: str = None) -> dict:
    """Save an email as a draft in Gmail with resume + cover letter from the company folder."""
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

    # Attach the tailored resume from the company folder
    if attachment_path and os.path.exists(attachment_path):
        _attach_docx(msg, attachment_path, "Teja_Mahesh_Neerukonda_Resume.docx")
        attached_files.append(os.path.basename(attachment_path))

        # Also attach cover letter if it exists in the same company folder
        company_dir = os.path.dirname(attachment_path)
        cl_files = [f for f in os.listdir(company_dir)
                     if f.endswith(".docx") and ("cover" in f.lower() or f.startswith("cover_letter_"))
                     and f != os.path.basename(attachment_path)]
        if cl_files:
            cl_path = os.path.join(company_dir, cl_files[0])
            _attach_docx(msg, cl_path, "Teja_Mahesh_Neerukonda_Cover_Letter.docx")
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
