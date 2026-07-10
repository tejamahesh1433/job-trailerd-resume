import os
import json
import logging
import asyncio
import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.telegram.org/bot{token}"

DATA_DIR = os.getenv("DATA_DIR", "data")
KNOWN_CHATS_FILE = os.path.join(DATA_DIR, "telegram_chats.json")


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


def _token():
    return os.getenv("TELEGRAM_BOT_TOKEN", "")


def is_configured() -> bool:
    return bool(_token())


def _url(method: str) -> str:
    return f"{_BASE_URL.format(token=_token())}/{method}"


async def send_message(chat_id: int, text: str, reply_markup: dict = None):
    """Send a message via Telegram. Splits if over 4096 chars."""
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


def send_message_sync(chat_id: int, text: str, reply_markup: dict = None):
    """Sync wrapper for sending messages from background threads."""
    import httpx as _httpx
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
