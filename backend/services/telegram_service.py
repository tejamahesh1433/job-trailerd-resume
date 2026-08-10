import os
import json
import logging
import asyncio
import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.telegram.org/bot{token}"

DATA_DIR = os.getenv("DATA_DIR", "data")
KNOWN_CHATS_FILE = os.path.join(DATA_DIR, "telegram_chats.json")
RESUME_SELECTION_FILE = os.path.join(DATA_DIR, "telegram_resume_selection.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "telegram_settings.json")

DEFAULT_SETTINGS = {
    "max_years_experience": 10,
    "hard_reject_visa": True,
    "hard_reject_language": True,
    "hard_reject_lead_role": True,
}


def get_known_chat_ids() -> list:
    """Chat IDs that have messaged the bot at least once — proactive pushes (new
    matches, daily digest) can only reach chats that exist, and Telegram's API has no
    'send to whoever set up the bot' concept, so we remember who's said hello."""
    if os.path.exists(KNOWN_CHATS_FILE):
        try:
            with open(KNOWN_CHATS_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return []
    return []


def add_known_chat_id(chat_id: int):
    chat_ids = set(get_known_chat_ids())
    if chat_id in chat_ids:
        return
    chat_ids.add(chat_id)
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(KNOWN_CHATS_FILE, "w") as f:
        json.dump(sorted(chat_ids), f)


def get_selected_resume(chat_id: int) -> str:
    """Which resume filename (in 'original/') this chat has chosen via /resumes — empty
    string means 'fall back to the most recently modified resume', the old default behavior."""
    if os.path.exists(RESUME_SELECTION_FILE):
        try:
            with open(RESUME_SELECTION_FILE, "r") as f:
                data = json.load(f)
            return data.get(str(chat_id), "")
        except (json.JSONDecodeError, OSError):
            return ""
    return ""


def set_selected_resume(chat_id: int, filename: str):
    data = {}
    if os.path.exists(RESUME_SELECTION_FILE):
        try:
            with open(RESUME_SELECTION_FILE, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            data = {}
    data[str(chat_id)] = filename
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(RESUME_SELECTION_FILE, "w") as f:
        json.dump(data, f)


def get_settings() -> dict:
    """Global bot behavior knobs (hard-reject toggles, experience cap) — single-user
    bot, so one shared settings file rather than per-chat, edited via /settings."""
    merged = dict(DEFAULT_SETTINGS)
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                merged.update(json.load(f))
        except (json.JSONDecodeError, OSError):
            pass
    return merged


def save_settings(settings: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f)


def _token():
    return os.getenv("TELEGRAM_BOT_TOKEN", "")


def is_configured() -> bool:
    return bool(_token())


def _url(method: str) -> str:
    return f"{_BASE_URL.format(token=_token())}/{method}"


async def send_message(chat_id: int, text: str, reply_markup: dict = None):
    """Send a message via Telegram. Splits if over 4096 chars.
    Returns the last chunk's Telegram message (with 'message_id') for callers that
    need to edit it later, or None if the send failed."""
    last_result = None
    async with httpx.AsyncClient(timeout=30) as client:
        chunks = [text[i:i+4096] for i in range(0, len(text), 4096)]
        for i, chunk in enumerate(chunks):
            payload = {
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": "HTML",
            }
            if reply_markup and i == len(chunks) - 1:
                payload["reply_markup"] = reply_markup
            resp = await client.post(_url("sendMessage"), json=payload)
            if resp.status_code != 200:
                logger.error(f"Telegram sendMessage failed: {resp.status_code} {resp.text}")
            else:
                last_result = resp.json().get("result")
    return last_result


def send_message_sync(chat_id: int, text: str, reply_markup: dict = None):
    """Sync wrapper for sending messages from background threads.
    Returns the last chunk's Telegram message (with 'message_id') for callers that
    need to edit it later, or None if the send failed."""
    import httpx as _httpx
    last_result = None
    chunks = [text[i:i+4096] for i in range(0, len(text), 4096)]
    with _httpx.Client(timeout=30) as client:
        for i, chunk in enumerate(chunks):
            payload = {
                "chat_id": chat_id,
                "text": chunk,
            }
            if reply_markup and i == len(chunks) - 1:
                payload["reply_markup"] = reply_markup
            resp = client.post(_url("sendMessage"), json=payload)
            if resp.status_code != 200:
                logger.error(f"Telegram sendMessage failed: {resp.status_code} {resp.text}")
            else:
                last_result = resp.json().get("result")
    return last_result


async def edit_message_text(chat_id: int, message_id: int, text: str, reply_markup: dict = None):
    """Edit an already-sent message in place — used for staged status updates
    ([1/3] -> [2/3] -> [3/3]) instead of spamming a new message per stage."""
    async with httpx.AsyncClient(timeout=30) as client:
        payload = {"chat_id": chat_id, "message_id": message_id, "text": text[:4096]}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        resp = await client.post(_url("editMessageText"), json=payload)
        if resp.status_code != 200:
            logger.error(f"Telegram editMessageText failed: {resp.status_code} {resp.text}")


def edit_message_text_sync(chat_id: int, message_id: int, text: str, reply_markup: dict = None):
    """Sync wrapper for editing a message from background threads."""
    import httpx as _httpx
    with _httpx.Client(timeout=30) as client:
        payload = {"chat_id": chat_id, "message_id": message_id, "text": text[:4096]}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        resp = client.post(_url("editMessageText"), json=payload)
        if resp.status_code != 200:
            logger.error(f"Telegram editMessageText failed: {resp.status_code} {resp.text}")


async def send_chat_action(chat_id: int, action: str = "typing"):
    """Show the '<bot> is typing...' indicator while a long-running task (AI analysis,
    tailoring) runs — best-effort, a failure here should never break the real action."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(_url("sendChatAction"), json={"chat_id": chat_id, "action": action})
            if resp.status_code != 200:
                logger.warning(f"Telegram sendChatAction failed: {resp.status_code} {resp.text}")
    except Exception as e:
        logger.warning(f"Telegram sendChatAction error: {e}")


def _send_document_multipart(client, chat_id: int, file_path: str, caption: str = ""):
    filename = os.path.basename(file_path)
    with open(file_path, "rb") as f:
        data = {"chat_id": str(chat_id)}
        if caption:
            data["caption"] = caption[:1024]
        files = {"document": (filename, f)}
        resp = client.post(_url("sendDocument"), data=data, files=files)
    if resp.status_code != 200:
        logger.error(f"Telegram sendDocument failed: {resp.status_code} {resp.text}")
    return resp.status_code == 200


async def send_document(chat_id: int, file_path: str, caption: str = "") -> bool:
    """Upload and send a file (resume/cover letter .docx, mail draft .txt) directly
    into the chat via Telegram's sendDocument API."""
    async with httpx.AsyncClient(timeout=60) as client:
        return await asyncio.get_event_loop().run_in_executor(
            None, _send_document_multipart, client, chat_id, file_path, caption
        )


def send_document_sync(chat_id: int, file_path: str, caption: str = "") -> bool:
    """Sync wrapper for sending a document from background threads."""
    import httpx as _httpx
    with _httpx.Client(timeout=60) as client:
        return _send_document_multipart(client, chat_id, file_path, caption)


async def answer_callback_query(callback_query_id: str, text: str = ""):
    """Acknowledge a callback query (removes the loading spinner on the button)."""
    async with httpx.AsyncClient(timeout=10) as client:
        payload = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        resp = await client.post(_url("answerCallbackQuery"), json=payload)
        if resp.status_code != 200:
            logger.error(f"Telegram answerCallbackQuery failed: {resp.status_code} {resp.text}")


async def get_me() -> dict:
    """Get bot info to verify the token works."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(_url("getMe"))
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram getMe failed: {data}")
        return data["result"]


async def get_updates(offset: int = 0, timeout: int = 30) -> list:
    """Long-poll for new messages and callback queries."""
    async with httpx.AsyncClient(timeout=timeout + 10) as client:
        resp = await client.get(_url("getUpdates"), params={
            "offset": offset,
            "timeout": timeout,
            "allowed_updates": '["message","callback_query"]',
        })
        data = resp.json()
        if not data.get("ok"):
            logger.error(f"Telegram getUpdates failed: {data}")
            return []
        return data.get("result", [])
