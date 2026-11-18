from __future__ import annotations
import logging
import smtplib

import httpx

from app.core.config import settings
from app.core.exceptions import EmailTransportError
from app.services.email_providers.base import EmailProvider
from app.services.email_providers.mailpit import MailpitProvider
from app.services.email_providers.resend import ResendProvider
from app.services.email_providers.gmail import GmailSMTPProvider

logger = logging.getLogger(__name__)

# Expected provider/transport failures. These are the error families the SMTP
# providers (Mailpit/Gmail) and the Resend HTTP provider raise when delivery
# cannot be attempted or accepted. Configuration/programming errors (for
# example Resend's missing-key ``ValueError``) are deliberately excluded so they
# are never reported as a generic delivery failure.
_EMAIL_TRANSPORT_EXCEPTIONS: tuple[type[BaseException], ...] = (
    smtplib.SMTPException,
    OSError,
    httpx.HTTPError,
)


class EmailService:
    def __init__(self) -> None:
        self.provider_name = getattr(settings, 'EMAIL_PROVIDER', 'mailpit').lower()
        self.from_email = getattr(settings, 'EMAIL_FROM', 'AI Recruitment Platform <noreply@example.com>')
        
        if self.provider_name == 'resend':
            api_key = getattr(settings, 'RESEND_API_KEY', '')
            self.provider: EmailProvider = ResendProvider(api_key=api_key, from_email=self.from_email)
        elif self.provider_name == 'gmail':
            username = getattr(settings, 'GMAIL_USERNAME', '')
            app_password = getattr(settings, 'GMAIL_APP_PASSWORD', '')
            host = getattr(settings, 'GMAIL_HOST', 'smtp.gmail.com')
            port = getattr(settings, 'GMAIL_PORT', 587)
            self.provider = GmailSMTPProvider(
                username=username,
                app_password=app_password,
                from_email=self.from_email,
                host=host,
                port=port,
            )
        else:
            host = getattr(settings, 'MAILPIT_HOST', 'mailpit')
            port = getattr(settings, 'MAILPIT_PORT', 1025)
            self.provider = MailpitProvider(host=host, port=port, from_email=self.from_email)

    def _raise_transport_error(self, exc: BaseException) -> None:
        """Normalize an expected provider failure without leaking its details."""
        cause_type = type(exc).__name__
        logger.error(
            "Email delivery failed via %s (%s)",
            self.provider_name,
            cause_type,
        )
        raise EmailTransportError(
            provider=self.provider_name,
            cause_type=cause_type,
        ) from None

    async def send_email(
        self, to_email: str, subject: str, html: str, text: str
    ) -> None:
        """Send an email with an HTML body and plain-text fallback."""
        try:
            await self.provider.send_email(to_email, subject, html, text)
        except _EMAIL_TRANSPORT_EXCEPTIONS as exc:
            self._raise_transport_error(exc)

    async def send_password_reset_otp(self, to_email: str, otp: str) -> None:
        """Send a password reset OTP email using the configured provider."""
        try:
            await self.provider.send_password_reset_otp(to_email, otp)
        except _EMAIL_TRANSPORT_EXCEPTIONS as exc:
            self._raise_transport_error(exc)
