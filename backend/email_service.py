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

_SENDGRID_URL = "https://api.sendgrid.com/v3/mail/send"


class EmailService:
    """Sends emails via SendGrid API."""

    def __init__(self, api_key: Optional[str] = None, from_email: Optional[str] = None, from_name: str = "AI Agent"):
        self.api_key = api_key or getattr(settings, "SENDGRID_API_KEY", "") or ""
        self.from_email = from_email or getattr(settings, "SENDGRID_FROM_EMAIL", "ai-agent@yourdomain.com")
        self.from_name = from_name

        if not self.api_key or not self.api_key.startswith("SG."):
            logger.warning("SendGrid API key not configured or invalid; emails will not be sent.")
            self.enabled = False
        else:
            self.enabled = True
            logger.info("SendGrid email service initialized (from=%s)", self.from_email)

    def _build_payload(self, to_email: str, subject: str, body_html: str, from_email: str = None, from_name: str = None) -> dict:
        return {
            "personalizations": [{"to": [{"email": to_email}]}],
            "from": {"email": from_email or self.from_email, "name": from_name or self.from_name},
            "subject": subject,
            "content": [{"type": "text/html", "value": body_html}],
        }

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    # ── Synchronous sending (used by LangGraph tools) ─────────────
    def send_email_sync(
        self,
        to_email: str,
        subject: str,
        body_html: str,
        from_email: str = None,
        from_name: str = None,
    ) -> bool:
        """
        Send an email via SendGrid synchronously.
        Use this from LangGraph tools (sync context).
        Returns True if sent successfully, False otherwise.
        """
        if not self.enabled:
            logger.warning("Email not sent — SendGrid not configured")
            return False

        payload = self._build_payload(to_email, subject, body_html, from_email, from_name)
        try:
            with httpx.Client(timeout=15) as client:
                response = client.post(_SENDGRID_URL, json=payload, headers=self._headers())
            if response.status_code in (200, 201, 202):
                logger.info("Email sent to %s: %s", to_email, subject)
                return True
            logger.error("SendGrid error %d: %s", response.status_code, response.text)
            return False
        except Exception as e:
            logger.error("Failed to send email: %s", e)
            return False

    # ── Async sending (used by agent_manager background tasks) ────
    async def send_email(
        self,
        to_email: str,
        subject: str,
        body_html: str,
        from_email: str = None,
        from_name: str = None,
    ) -> bool:
        """
        Send an email via SendGrid asynchronously.
        Returns True if sent successfully, False otherwise.
        """
        if not self.enabled:
            logger.warning("Email not sent — SendGrid not configured")
            return False

        payload = self._build_payload(to_email, subject, body_html, from_email, from_name)
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(_SENDGRID_URL, json=payload, headers=self._headers())
            if response.status_code in (200, 201, 202):
                logger.info("Email sent to %s: %s", to_email, subject)
                return True
            logger.error("SendGrid error %d: %s", response.status_code, response.text)
            return False
        except Exception as e:
            logger.error("Failed to send email: %s", e)
            return False

    # ── Email Templates ────────────────────────────────────────────

    def send_follow_up_sync(self, to_email: str, agent_name: str, summary: str) -> bool:
        """Send a follow-up email after a conversation (sync)."""
        subject = f"Follow-up from {agent_name}"
        body = _follow_up_html(agent_name, summary)
        return self.send_email_sync(to_email, subject, body, from_name=agent_name)

    async def send_follow_up(self, to_email: str, agent_name: str, summary: str) -> bool:
        """Send a follow-up email after a conversation (async)."""
        subject = f"Follow-up from {agent_name}"
        body = _follow_up_html(agent_name, summary)
        return await self.send_email(to_email, subject, body, from_name=agent_name)

    def send_booking_confirmation_sync(
        self,
        to_email: str,
        agent_name: str,
        customer_name: str,
        booking_date: str,
        booking_time: str,
        notes: str = "",
    ) -> bool:
        """Send a booking confirmation email (sync)."""
        subject = f"Appointment Confirmed — {agent_name}"
        body = _booking_confirmation_html(agent_name, customer_name, booking_date, booking_time, notes)
        return self.send_email_sync(to_email, subject, body, from_name=agent_name)

    async def send_booking_confirmation(
        self,
        to_email: str,
        agent_name: str,
        customer_name: str,
        booking_date: str,
        booking_time: str,
        notes: str = "",
    ) -> bool:
        """Send a booking confirmation email (async)."""
        subject = f"Appointment Confirmed — {agent_name}"
        body = _booking_confirmation_html(agent_name, customer_name, booking_date, booking_time, notes)
        return await self.send_email(to_email, subject, body, from_name=agent_name)

    def send_cancellation_sync(
        self,
        to_email: str,
        agent_name: str,
        customer_name: str,
        booking_date: str,
        booking_time: str,
    ) -> bool:
        """Send a booking cancellation email (sync)."""
        subject = f"Appointment Cancelled — {agent_name}"
        body = _cancellation_html(agent_name, customer_name, booking_date, booking_time)
        return self.send_email_sync(to_email, subject, body, from_name=agent_name)


# ── HTML Templates ─────────────────────────────────────────────────

def _base_html(agent_name: str, content: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f6f9fc;font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f6f9fc;padding:40px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">
        <!-- Header -->
        <tr><td style="background:linear-gradient(135deg,#667eea,#764ba2);padding:32px 40px;">
          <h1 style="margin:0;color:#fff;font-size:22px;font-weight:700;">{agent_name}</h1>
          <p style="margin:4px 0 0;color:rgba(255,255,255,0.75);font-size:13px;">AI-Powered Customer Service</p>
        </td></tr>
        <!-- Content -->
        <tr><td style="padding:32px 40px;">
          {content}
        </td></tr>
        <!-- Footer -->
        <tr><td style="background:#f6f9fc;padding:20px 40px;border-top:1px solid #e8ecef;">
          <p style="margin:0;color:#9ca3af;font-size:12px;text-align:center;">
            This message was sent by {agent_name} — an AI-powered assistant.<br>
            If you have questions, please contact us directly.
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _follow_up_html(agent_name: str, summary: str) -> str:
    content = f"""
    <h2 style="margin:0 0 16px;color:#1a1a2e;font-size:20px;">Thank you for reaching out!</h2>
    <p style="color:#4b5563;line-height:1.6;margin:0 0 20px;">
      Here's a summary of our conversation:
    </p>
    <div style="background:#f8f9ff;border-left:4px solid #667eea;border-radius:0 8px 8px 0;padding:16px 20px;margin:0 0 24px;">
      <p style="margin:0;color:#374151;line-height:1.7;white-space:pre-line;">{summary}</p>
    </div>
    <p style="color:#4b5563;line-height:1.6;margin:0;">
      If you have any further questions, feel free to reach out anytime. We're here to help!
    </p>"""
    return _base_html(agent_name, content)


def _booking_confirmation_html(agent_name: str, customer_name: str, booking_date: str, booking_time: str, notes: str = "") -> str:
    notes_block = f"""
    <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:14px 18px;margin:16px 0 0;">
      <p style="margin:0;color:#166534;font-size:14px;"><strong>Notes:</strong> {notes}</p>
    </div>""" if notes else ""

    content = f"""
    <h2 style="margin:0 0 8px;color:#1a1a2e;font-size:20px;">✅ Appointment Confirmed!</h2>
    <p style="color:#4b5563;margin:0 0 24px;">Hi {customer_name}, your appointment has been booked successfully.</p>
    <div style="background:#f8f9ff;border-radius:10px;padding:20px 24px;margin:0 0 20px;">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td style="padding:8px 0;color:#6b7280;font-size:14px;width:40%;">📅 Date</td>
          <td style="padding:8px 0;color:#111827;font-weight:600;font-size:14px;">{booking_date}</td>
        </tr>
        <tr>
          <td style="padding:8px 0;color:#6b7280;font-size:14px;">🕐 Time</td>
          <td style="padding:8px 0;color:#111827;font-weight:600;font-size:14px;">{booking_time}</td>
        </tr>
        <tr>
          <td style="padding:8px 0;color:#6b7280;font-size:14px;">🏢 With</td>
          <td style="padding:8px 0;color:#111827;font-weight:600;font-size:14px;">{agent_name}</td>
        </tr>
      </table>
    </div>
    {notes_block}
    <p style="color:#4b5563;line-height:1.6;margin:20px 0 0;font-size:14px;">
      Please arrive a few minutes early. If you need to reschedule, reply to this email or contact us directly.
    </p>"""
    return _base_html(agent_name, content)


def _cancellation_html(agent_name: str, customer_name: str, booking_date: str, booking_time: str) -> str:
    content = f"""
    <h2 style="margin:0 0 8px;color:#1a1a2e;font-size:20px;">❌ Appointment Cancelled</h2>
    <p style="color:#4b5563;margin:0 0 24px;">Hi {customer_name}, your appointment has been cancelled.</p>
    <div style="background:#fff7ed;border:1px solid #fed7aa;border-radius:10px;padding:20px 24px;margin:0 0 20px;">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td style="padding:8px 0;color:#6b7280;font-size:14px;width:40%;">📅 Date</td>
          <td style="padding:8px 0;color:#111827;font-weight:600;font-size:14px;">{booking_date}</td>
        </tr>
        <tr>
          <td style="padding:8px 0;color:#6b7280;font-size:14px;">🕐 Time</td>
          <td style="padding:8px 0;color:#111827;font-weight:600;font-size:14px;">{booking_time}</td>
        </tr>
      </table>
    </div>
    <p style="color:#4b5563;line-height:1.6;margin:0;font-size:14px;">
      Would you like to reschedule? Feel free to contact us and we'll find a time that works for you.
    </p>"""
    return _base_html(agent_name, content)
