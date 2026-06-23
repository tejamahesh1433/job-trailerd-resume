import os
import logging
import asyncio
import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.telegram.org/bot{token}"


def _token():
    return os.getenv("TELEGRAM_BOT_TOKEN", "")


def is_configured() -> bool:
    return bool(_token())


def _url(method: str) -> str:
    return f"{_BASE_URL.format(token=_token())}/{method}"


async def send_message(chat_id: int, text: str):
    """Send a message via Telegram. Splits if over 4096 chars."""
    async with httpx.AsyncClient(timeout=30) as client:
        chunks = [text[i:i+4096] for i in range(0, len(text), 4096)]
        for chunk in chunks:
            resp = await client.post(_url("sendMessage"), json={
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": "HTML",
            })
            if resp.status_code != 200:
                logger.error(f"Telegram sendMessage failed: {resp.status_code} {resp.text}")


def send_message_sync(chat_id: int, text: str):
    """Sync wrapper for sending messages from background threads."""
    import httpx as _httpx
    chunks = [text[i:i+4096] for i in range(0, len(text), 4096)]
    with _httpx.Client(timeout=30) as client:
        for chunk in chunks:
            resp = client.post(_url("sendMessage"), json={
                "chat_id": chat_id,
                "text": chunk,
            })
            if resp.status_code != 200:
                logger.error(f"Telegram sendMessage failed: {resp.status_code} {resp.text}")


async def get_me() -> dict:
    """Get bot info to verify the token works."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(_url("getMe"))
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram getMe failed: {data}")
        return data["result"]


async def get_updates(offset: int = 0, timeout: int = 30) -> list:
    """Long-poll for new messages."""
    async with httpx.AsyncClient(timeout=timeout + 10) as client:
        resp = await client.get(_url("getUpdates"), params={
            "offset": offset,
            "timeout": timeout,
            "allowed_updates": '["message"]',
        })
        data = resp.json()
        if not data.get("ok"):
            logger.error(f"Telegram getUpdates failed: {data}")
            return []
        return data.get("result", [])
