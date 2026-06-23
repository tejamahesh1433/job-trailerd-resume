import os
import logging
import hmac
import hashlib
from urllib.parse import quote
from twilio.rest import Client
from twilio.request_validator import RequestValidator

logger = logging.getLogger(__name__)

_client = None
_validator = None


def _get_client():
    global _client
    if _client is None:
        sid = os.getenv("TWILIO_ACCOUNT_SID")
        token = os.getenv("TWILIO_AUTH_TOKEN")
        if not sid or not token:
            raise RuntimeError("TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN are required")
        _client = Client(sid, token)
    return _client


def _get_validator():
    global _validator
    if _validator is None:
        token = os.getenv("TWILIO_AUTH_TOKEN")
        if not token:
            raise RuntimeError("TWILIO_AUTH_TOKEN is required")
        _validator = RequestValidator(token)
    return _validator


def is_configured() -> bool:
    return bool(
        os.getenv("TWILIO_ACCOUNT_SID")
        and os.getenv("TWILIO_AUTH_TOKEN")
        and os.getenv("TWILIO_WHATSAPP_NUMBER")
    )


def validate_request(url: str, params: dict, signature: str) -> bool:
    try:
        return _get_validator().validate(url, params, signature)
    except Exception as e:
        logger.warning(f"Twilio signature validation failed: {e}")
        return False


def send_message(to: str, body: str):
    client = _get_client()
    from_number = os.getenv("TWILIO_WHATSAPP_NUMBER", "")
    if not from_number.startswith("whatsapp:"):
        from_number = f"whatsapp:{from_number}"
    if not to.startswith("whatsapp:"):
        to = f"whatsapp:{to}"

    # WhatsApp has a 1600 char limit per message
    if len(body) > 1600:
        body = body[:1597] + "..."

    msg = client.messages.create(from_=from_number, to=to, body=body)
    logger.info(f"WhatsApp message sent to {to}: SID={msg.sid}")
    return msg.sid
