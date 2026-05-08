"""
Email service using SendGrid.

Sends templated emails triggered by the AI agent during conversations:
- Follow-up emails after calls
- Appointment confirmations
- Problem summaries and resolutions
"""

import logging
from typing import Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)


class EmailService:
    """Sends emails via SendGrid API."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or getattr(settings, "SENDGRID_API_KEY", "")
        if not self.api_key or self.api_key.startswith("SG.") is False:
            logger.warning("SendGrid API key not configured; emails will not be sent.")
            self.enabled = False
        else:
            self.enabled = True
            logger.info("SendGrid email service initialized")

    async def send_email(
        self,
        to_email: str,
        subject: str,
        body_html: str,
        from_email: str = None,
        from_name: str = "AI Sales Agent",
    ) -> bool:
        """
        Send an email via SendGrid.

        Returns True if sent successfully, False otherwise.
        """
        from_email = from_email or settings.SENDGRID_FROM_EMAIL
        if not self.enabled:
            logger.warning("Email not sent — SendGrid not configured")
            return False

        payload = {
            "personalizations": [
                {"to": [{"email": to_email}]}
            ],
            "from": {"email": from_email, "name": from_name},
            "subject": subject,
            "content": [
                {"type": "text/html", "value": body_html}
            ],
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(
                    "https://api.sendgrid.com/v3/mail/send",
                    json=payload,
                    headers=headers,
                )
            if response.status_code in (200, 201, 202):
                logger.info("Email sent to %s: %s", to_email, subject)
                return True
            else:
                logger.error(
                    "SendGrid error %d: %s",
                    response.status_code,
                    response.text,
                )
                return False
        except Exception as e:
            logger.error("Failed to send email: %s", e)
            return False

    async def send_follow_up(
        self,
        to_email: str,
        agent_name: str,
        summary: str,
    ) -> bool:
        """Send a follow-up email after a conversation."""
        subject = f"Follow-up from {agent_name}"
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; color: #333;">
            <h2>Thank you for your conversation with {agent_name}</h2>
            <p>Here's a summary of our discussion:</p>
            <div style="background: #f5f5f5; padding: 16px; border-radius: 8px; margin: 16px 0;">
                {summary}
            </div>
            <p>If you have any further questions, feel free to reach out!</p>
            <hr style="border: none; border-top: 1px solid #eee; margin: 24px 0;" />
            <p style="font-size: 12px; color: #999;">
                This email was sent by {agent_name} — an AI-powered assistant.
            </p>
        </body>
        </html>
        """
        return await self.send_email(to_email, subject, body, from_name=agent_name)
