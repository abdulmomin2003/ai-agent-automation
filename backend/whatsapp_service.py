"""
WhatsApp service using Twilio.

Handles inbound WhatsApp messages and sends replies via the Twilio API.
Messages are processed through the agent's RAG pipeline.
"""

import logging
from typing import Optional

from twilio.rest import Client as TwilioClient

from config import settings

logger = logging.getLogger(__name__)


class WhatsAppService:
    """Handles WhatsApp messaging via Twilio."""

    def __init__(self):
        sid = getattr(settings, "TWILIO_ACCOUNT_SID", "")
        token = getattr(settings, "TWILIO_AUTH_TOKEN", "")

        if sid and token:
            self.client = TwilioClient(sid, token)
            self.enabled = True
            logger.info("WhatsApp service initialized via Twilio")
        else:
            self.client = None
            self.enabled = False
            logger.warning("Twilio credentials not configured; WhatsApp disabled")

    async def send_message(
        self,
        to_number: str,
        body: str,
        from_number: Optional[str] = None,
    ) -> Optional[str]:
        """
        Send a WhatsApp message.

        Args:
            to_number: Recipient number in E.164 format (e.g., +1234567890)
            body: Message text
            from_number: Twilio WhatsApp sender (defaults to configured number)

        Returns:
            Message SID if sent successfully, None otherwise.
        """
        if not self.enabled:
            logger.warning("WhatsApp not sent — Twilio not configured")
            return None

        from_num = from_number or getattr(settings, "TWILIO_PHONE_NUMBER", "")
        if not from_num.startswith("whatsapp:"):
            from_num = f"whatsapp:{from_num}"
        if not to_number.startswith("whatsapp:"):
            to_number = f"whatsapp:{to_number}"

        try:
            message = self.client.messages.create(
                body=body[:4096],  # WhatsApp message limit
                from_=from_num,
                to=to_number,
            )
            logger.info("WhatsApp sent to %s: SID=%s", to_number, message.sid)
            return message.sid
        except Exception as e:
            logger.error("Failed to send WhatsApp: %s", e)
            return None

    def parse_inbound(self, form_data: dict) -> dict:
        """
        Parse an inbound WhatsApp webhook from Twilio.

        Returns dict with: from_number, body, media_url, num_media
        """
        return {
            "from_number": form_data.get("From", "").replace("whatsapp:", ""),
            "to_number": form_data.get("To", "").replace("whatsapp:", ""),
            "body": form_data.get("Body", ""),
            "num_media": int(form_data.get("NumMedia", 0)),
            "media_url": form_data.get("MediaUrl0"),
            "message_sid": form_data.get("MessageSid"),
        }
