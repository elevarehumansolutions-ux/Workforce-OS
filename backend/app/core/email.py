"""Email service abstraction for Elevare Workforce OS.

Provides an abstract EmailService interface with two implementations:
- ResendEmailService: sends real emails via the Resend API
- StubEmailService: logs to stdout, used in dev/tests

Wire into FastAPI via get_email_service().
"""

import logging
from abc import ABC, abstractmethod

from .config import settings

logger = logging.getLogger(__name__)


class EmailService(ABC):
    """Abstract interface for email delivery."""

    @abstractmethod
    async def send_verification_email(
        self, email: str, verification_token: str, next_url: str | None = None
    ) -> None:
        """Send email address verification link to a newly registered user."""
        ...

    @abstractmethod
    async def send_invite_email(
        self,
        email: str,
        invite_link: str,
        company_name: str | None = None,
    ) -> None:
        """Send an invite link to a prospective teammate joining an organization."""
        ...

    @abstractmethod
    async def send_password_reset_email(
        self, email: str, reset_token: str
    ) -> None:
        """Send a password reset link to a user who requested one."""
        ...


def _render_email_layout(
    title: str,
    preheader: str,
    body_content_html: str,
    footer_note: str,
) -> str:
    """Wraps email content in a simple, responsive layout."""
    from datetime import datetime

    current_year = datetime.now().year

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <meta name="supported-color-schemes" content="light">
  <title>{title}</title>
  <style>
    :root {{ color-scheme: light; supported-color-schemes: light; }}
    body {{
      width: 100% !important; height: 100% !important; margin: 0 !important;
      padding: 0 !important; -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%;
      background-color: #F8FAFC;
    }}
    table {{ border-collapse: collapse; border-spacing: 0; mso-table-lspace: 0pt; mso-table-rspace: 0pt; }}
    img {{ border: 0; height: auto; line-height: 100%; outline: none; text-decoration: none; }}
    .email-container {{
      max-width: 600px; margin: 40px auto; background-color: #ffffff;
      border: 1px solid #E2E8F0; border-radius: 12px; overflow: hidden;
      box-shadow: 0 4px 6px -1px rgba(15, 23, 42, 0.03), 0 2px 4px -1px rgba(15, 23, 42, 0.02);
    }}
    @media only screen and (max-width: 600px) {{
      .email-container {{ margin: 0 !important; width: 100% !important; border-radius: 0 !important; border-left: none !important; border-right: none !important; }}
      .email-padding {{ padding: 24px 20px !important; }}
    }}
  </style>
</head>
<body style="background-color: #F8FAFC; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; -webkit-font-smoothing: antialiased; margin: 0; padding: 0;">
  <div style="display: none; max-height: 0px; max-width: 0px; opacity: 0; overflow: hidden; mso-hide: all; font-size: 1px; color: #F8FAFC; line-height: 1px;">
    {preheader}
  </div>
  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color: #F8FAFC; min-width: 100%;">
    <tr>
      <td align="center" style="padding: 12px 12px 40px 12px;">
        <table class="email-container" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color: #ffffff; max-width: 600px; width: 100%;">
          <tr>
            <td style="padding: 32px 32px 0 32px;" class="email-padding">
              <table width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td align="left">
                    <a href="{settings.app_url}" target="_blank" style="text-decoration: none;">
                      <span style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 22px; font-weight: 800; color: #1A4D8F; letter-spacing: -0.5px;">elevare</span>
                    </a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding: 24px 32px 40px 32px;" class="email-padding">
              {body_content_html}
            </td>
          </tr>
        </table>
        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width: 600px; width: 100%;">
          <tr>
            <td align="center" style="padding: 24px 20px 0 20px; text-align: center;">
              <p style="margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 12px; line-height: 1.5; color: #64748B; font-weight: 400;">
                © {current_year} Elevare. All rights reserved.
              </p>
              <p style="margin: 4px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 12px; line-height: 1.5; color: #94A3B8; font-weight: 400;">
                {footer_note}
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _render_button(text: str, link: str, is_primary: bool = True) -> str:
    """Helper to render a styled, client-safe HTML button."""
    if is_primary:
        bg_color, border_color, text_color = "#1A4D8F", "#1A4D8F", "#FFFFFF"
    else:
        bg_color, border_color, text_color = "#FFFFFF", "#E2E8F0", "#1A4D8F"

    return f"""
    <table cellpadding="0" cellspacing="0" border="0" style="margin: 24px 0;">
      <tr>
        <td align="center" style="border-radius: 8px; background-color: {bg_color};">
          <a href="{link}" target="_blank" style="display: inline-block; padding: 12px 28px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 14px; font-weight: 600; line-height: 1.5; text-decoration: none; color: {text_color}; background-color: {bg_color}; border: 1px solid {border_color}; border-radius: 8px; text-align: center;">{text}</a>
        </td>
      </tr>
    </table>
    """


class ResendEmailService(EmailService):
    """Concrete implementation that delivers email via the Resend API."""

    def __init__(self) -> None:
        """Initialise the service and configure the Resend SDK with the API key."""
        import resend as resend_sdk

        resend_sdk.api_key = settings.resend_api_key
        self._resend = resend_sdk

    async def _send_html(
        self,
        subject: str,
        recipients: list[str],
        html_body: str,
    ) -> None:
        """Run the blocking Resend SDK call in a thread pool to avoid blocking the event loop."""
        import asyncio

        loop = asyncio.get_event_loop()
        payload = {
            "from": settings.mail_from,
            "to": recipients,
            "subject": subject,
            "html": html_body,
        }
        try:
            await loop.run_in_executor(None, lambda: self._resend.Emails.send(payload))
            logger.info("Email sent to %s — subject: %s", recipients, subject)
        except Exception as exc:
            logger.error("Resend delivery failed to %s: %s", recipients, exc)
            raise

    async def send_verification_email(
        self, email: str, verification_token: str, next_url: str | None = None
    ) -> None:
        """Send an email address verification link to the newly registered user."""
        verification_link = f"{settings.app_url}/verify-email?token={verification_token}"
        if next_url:
            from urllib.parse import quote

            verification_link += f"&next={quote(next_url, safe='')}"

        body_content_html = f"""
        <h2 style="margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 20px; font-weight: 600; line-height: 1.4; color: #0F172A;">Verify Your Email Address</h2>
        <p style="margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 15px; line-height: 1.6; color: #334155;">Welcome to Elevare Workforce OS! Click the button below to verify your email address and activate your account. This link will expire in {settings.email_verification_token_expiry} hours.</p>
        {_render_button("Verify Email", verification_link)}
        """

        html_body = _render_email_layout(
            title="Verify Your Email Address",
            preheader="Verify your email address to activate your Elevare Workforce OS account.",
            body_content_html=body_content_html,
            footer_note="If you didn't create an account, you can safely ignore this email.",
        )

        await self._send_html(
            subject="Verify Your Email Address — Elevare Workforce OS",
            recipients=[email],
            html_body=html_body,
        )

    async def send_invite_email(
        self,
        email: str,
        invite_link: str,
        company_name: str | None = None,
    ) -> None:
        """Send an invite link to a prospective teammate joining an organization."""
        if company_name:
            subject = f"You've been invited to join {company_name} on Elevare Workforce OS"
            heading = "You're invited to join a team"
            copy = f"You've been invited to join <strong>{company_name}</strong> on Elevare Workforce OS. Click below to accept and set up your account."
        else:
            subject = "You've been invited to Elevare Workforce OS"
            heading = "You're invited to Elevare Workforce OS"
            copy = "Click below to accept your invite and get started."

        body_content_html = f"""
        <h2 style="margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 20px; font-weight: 600; line-height: 1.4; color: #0F172A;">{heading}</h2>
        <p style="margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 15px; line-height: 1.6; color: #334155;">{copy}</p>
        <p style="margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 15px; line-height: 1.6; color: #334155;">This link expires in {settings.invite_expiry} day{"s" if settings.invite_expiry != 1 else ""}.</p>
        {_render_button("Accept Invite", invite_link)}
        """

        html_body = _render_email_layout(
            title=subject,
            preheader=copy,
            body_content_html=body_content_html,
            footer_note="If you weren't expecting this invite, you can safely ignore this email.",
        )

        await self._send_html(subject=subject, recipients=[email], html_body=html_body)

    async def send_password_reset_email(self, email: str, reset_token: str) -> None:
        """Send a password reset link to a user who requested one."""
        reset_link = f"{settings.app_url}/reset-password?token={reset_token}"

        body_content_html = f"""
        <h2 style="margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 20px; font-weight: 600; line-height: 1.4; color: #0F172A;">Reset Your Password</h2>
        <p style="margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 15px; line-height: 1.6; color: #334155;">Click the button below to choose a new password. This link will expire in {settings.password_reset_token_expiry} hour{"s" if settings.password_reset_token_expiry != 1 else ""}.</p>
        {_render_button("Reset Password", reset_link)}
        """

        html_body = _render_email_layout(
            title="Reset Your Password",
            preheader="Reset your Elevare Workforce OS password.",
            body_content_html=body_content_html,
            footer_note="If you didn't request this, you can safely ignore this email — your password won't change.",
        )

        await self._send_html(
            subject="Reset Your Password — Elevare Workforce OS",
            recipients=[email],
            html_body=html_body,
        )


class StubEmailService(EmailService):
    """Concrete implementation that logs to stdout — used in dev/tests."""

    async def send_verification_email(
        self, email: str, verification_token: str, next_url: str | None = None
    ) -> None:
        """Log a stub verification email with a full clickable link."""
        from urllib.parse import quote

        link = f"{settings.app_url}/verify-email?token={verification_token}"
        if next_url:
            link += f"&next={quote(next_url, safe='')}"
        logger.info("STUB VERIFICATION EMAIL to %s — click to verify:\n%s", email, link)

    async def send_invite_email(
        self,
        email: str,
        invite_link: str,
        company_name: str | None = None,
    ) -> None:
        """Log a stub invite email with a full clickable link."""
        logger.info(
            "STUB INVITE EMAIL to %s — company=%s\n  Accept: %s",
            email,
            company_name,
            invite_link,
        )

    async def send_password_reset_email(self, email: str, reset_token: str) -> None:
        """Log a stub password reset email with a full clickable link."""
        link = f"{settings.app_url}/reset-password?token={reset_token}"
        logger.info("STUB PASSWORD RESET EMAIL to %s — click to reset:\n%s", email, link)


def get_email_service() -> EmailService:
    """FastAPI dependency — returns ResendEmailService in production, StubEmailService in dev/CI."""
    if settings.email_stub_mode or not settings.resend_api_key:
        return StubEmailService()
    return ResendEmailService()
