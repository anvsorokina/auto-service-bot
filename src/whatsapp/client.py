"""Twilio WhatsApp client — sends messages via Twilio API."""

from __future__ import annotations

import asyncio
from typing import Optional

import structlog

from src.config import settings

logger = structlog.get_logger()

# Lazy singleton
_client: Optional["WhatsAppClient"] = None


class WhatsAppClient:
    """Async wrapper around Twilio's synchronous SDK for WhatsApp messaging."""

    def __init__(self, account_sid: str, auth_token: str, from_number: str):
        from twilio.rest import Client as TwilioClient

        self.twilio = TwilioClient(account_sid, auth_token)
        self.from_number = from_number  # e.g. "+14155238886" (sandbox)

    async def send_message(self, to_phone: str, text: str) -> str:
        """Send a WhatsApp message.

        Args:
            to_phone: Recipient phone number (e.g. "+79123456789")
            text: Message body

        Returns:
            Twilio message SID
        """
        # Twilio SDK is synchronous — run in thread pool
        msg = await asyncio.to_thread(
            self.twilio.messages.create,
            body=text,
            from_=f"whatsapp:{self.from_number}",
            to=f"whatsapp:{to_phone}",
        )

        logger.info(
            "whatsapp_message_sent",
            to=to_phone,
            sid=msg.sid,
            text_len=len(text),
        )
        return msg.sid


def get_whatsapp_client() -> Optional[WhatsAppClient]:
    """Get or create the singleton WhatsApp client.

    Returns None if Twilio credentials are not configured.
    """
    global _client

    if _client is not None:
        return _client

    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        logger.debug("whatsapp_client_not_configured")
        return None

    _client = WhatsAppClient(
        account_sid=settings.twilio_account_sid,
        auth_token=settings.twilio_auth_token,
        from_number=settings.twilio_whatsapp_number,
    )

    logger.info(
        "whatsapp_client_initialized",
        from_number=settings.twilio_whatsapp_number,
    )
    return _client
