import asyncio

import httpx
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from app.core.config import settings
from app.core.exceptions import EmailTransportError
from app.services.email_service import EmailService
from app.services.email_providers.mailpit import MailpitProvider
from app.services.email_providers.resend import ResendProvider
from app.services.email_providers.gmail import GmailSMTPProvider

# Capture the real methods before the suite-wide ``_no_outbound_email`` fixture
# replaces them with AsyncMocks for the duration of each test.
_ORIGINAL_SEND_EMAIL = EmailService.send_email
_ORIGINAL_SEND_PASSWORD_RESET_OTP = EmailService.send_password_reset_otp

def test_email_service_initializes_mailpit_by_default(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.EMAIL_PROVIDER", "mailpit")
    service = EmailService()
    assert isinstance(service.provider, MailpitProvider)

def test_email_service_initializes_resend(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.EMAIL_PROVIDER", "resend")
    monkeypatch.setattr("app.core.config.settings.RESEND_API_KEY", "test-key")
    service = EmailService()
    assert isinstance(service.provider, ResendProvider)

def test_email_service_initializes_gmail(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.EMAIL_PROVIDER", "gmail")
    monkeypatch.setattr("app.core.config.settings.GMAIL_USERNAME", "test@gmail.com")
    monkeypatch.setattr("app.core.config.settings.GMAIL_APP_PASSWORD", "test-app-password")
    service = EmailService()
    assert isinstance(service.provider, GmailSMTPProvider)
    assert service.provider.username == "test@gmail.com"
    assert service.provider.app_password == "test-app-password"
    assert service.provider.host == "smtp.gmail.com"
    assert service.provider.port == 587

def test_email_service_initializes_gmail_with_custom_host_port(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.EMAIL_PROVIDER", "gmail")
    monkeypatch.setattr("app.core.config.settings.GMAIL_USERNAME", "test@gmail.com")
    monkeypatch.setattr("app.core.config.settings.GMAIL_APP_PASSWORD", "test-app-password")
    monkeypatch.setattr("app.core.config.settings.GMAIL_HOST", "smtp.custom.com")
    monkeypatch.setattr("app.core.config.settings.GMAIL_PORT", 465)
    service = EmailService()
    assert isinstance(service.provider, GmailSMTPProvider)
    assert service.provider.host == "smtp.custom.com"
    assert service.provider.port == 465

@pytest.mark.asyncio
async def test_mailpit_sends_email():
    provider = MailpitProvider(host="localhost", port=1025)
    with patch("app.services.email_providers.mailpit.smtplib.SMTP") as mock_smtp:
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server
        await provider.send_password_reset_otp("test@example.com", "123456")
        mock_server.send_message.assert_called_once()
        message = mock_server.send_message.call_args[0][0]
        assert message["To"] == "test@example.com"
        assert message["Subject"] == "Đặt lại mật khẩu — AI Recruitment Platform"

@pytest.mark.asyncio
async def test_resend_sends_email():
    provider = ResendProvider(api_key="test-key", from_email="test@example.com")
    with patch("app.services.email_providers.resend.httpx.AsyncClient") as mock_client:
        mock_post = AsyncMock()
        mock_client.return_value.__aenter__.return_value.post = mock_post
        await provider.send_password_reset_otp("test@example.com", "123456")
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "https://api.resend.com/emails"
        assert kwargs["json"]["to"] == ["test@example.com"]
        assert "123456" in kwargs["json"]["text"]

@pytest.mark.asyncio
async def test_gmail_sends_email():
    provider = GmailSMTPProvider(
        username="test@gmail.com",
        app_password="test-app-password",
        from_email="test@example.com",
        host="smtp.gmail.com",
        port=587,
    )
    with patch("app.services.email_providers.gmail.smtplib.SMTP") as mock_smtp:
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server
        await provider.send_password_reset_otp("test@example.com", "123456")
        mock_server.send_message.assert_called_once()
        mock_server.ehlo.assert_called()
        mock_server.starttls.assert_called()
        mock_server.login.assert_called_once_with("test@gmail.com", "test-app-password")
        message = mock_server.send_message.call_args[0][0]
        assert message["To"] == "test@example.com"
        assert message["Subject"] == "Đặt lại mật khẩu — AI Recruitment Platform"
        assert message["From"] == "test@example.com"

@pytest.mark.asyncio
async def test_gmail_handles_smtp_error():
    provider = GmailSMTPProvider(
        username="test@gmail.com",
        app_password="test-app-password",
        from_email="test@example.com",
    )
    with patch("app.services.email_providers.gmail.smtplib.SMTP") as mock_smtp:
        mock_smtp.return_value.__enter__.side_effect = Exception("SMTP connection failed")
        with pytest.raises(Exception, match="SMTP connection failed"):
            await provider.send_password_reset_otp("test@example.com", "123456")


def test_mailpit_transport_error_maps_to_email_transport_error(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "mailpit")
    service = EmailService()

    with patch.object(
        EmailService,
        "send_password_reset_otp",
        new=_ORIGINAL_SEND_PASSWORD_RESET_OTP,
    ), patch(
        "app.services.email_providers.mailpit.smtplib.SMTP",
        side_effect=OSError("smtp connection refused"),
    ):
        with pytest.raises(EmailTransportError) as exc_info:
            asyncio.run(
                service.send_password_reset_otp("test@example.com", "123456")
            )

    error = exc_info.value
    assert error.provider == "mailpit"
    assert error.cause_type == "OSError"
    # No raw provider text (or OTP) leaks through the typed exception.
    assert "smtp connection refused" not in str(error)
    assert "123456" not in str(error)


def test_gmail_transport_error_maps_to_email_transport_error(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "gmail")
    monkeypatch.setattr(settings, "GMAIL_USERNAME", "test@gmail.com")
    monkeypatch.setattr(settings, "GMAIL_APP_PASSWORD", "app-password")
    service = EmailService()

    with patch.object(
        EmailService,
        "send_password_reset_otp",
        new=_ORIGINAL_SEND_PASSWORD_RESET_OTP,
    ), patch(
        "app.services.email_providers.gmail.smtplib.SMTP",
        side_effect=OSError("gmail unreachable"),
    ):
        with pytest.raises(EmailTransportError) as exc_info:
            asyncio.run(
                service.send_password_reset_otp("test@example.com", "123456")
            )

    assert exc_info.value.provider == "gmail"
    assert exc_info.value.cause_type == "OSError"


def test_resend_transport_error_maps_to_email_transport_error(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "resend")
    monkeypatch.setattr(settings, "RESEND_API_KEY", "test-key")
    service = EmailService()

    with patch.object(
        EmailService, "send_email", new=_ORIGINAL_SEND_EMAIL
    ), patch(
        "app.services.email_providers.resend.httpx.AsyncClient",
        side_effect=httpx.ConnectError("resend unreachable"),
    ):
        with pytest.raises(EmailTransportError) as exc_info:
            asyncio.run(
                service.send_email(
                    "test@example.com", "Subject", "<p>x</p>", "x"
                )
            )

    error = exc_info.value
    assert error.provider == "resend"
    assert error.cause_type == "ConnectError"
    assert "resend unreachable" not in str(error)


def test_unexpected_provider_error_is_not_converted(monkeypatch):
    """Programming/configuration errors must not look like transport failures."""
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "mailpit")
    service = EmailService()
    service.provider.send_email = AsyncMock(
        side_effect=ValueError("bad configuration")
    )

    with patch.object(EmailService, "send_email", new=_ORIGINAL_SEND_EMAIL):
        with pytest.raises(ValueError, match="bad configuration"):
            asyncio.run(
                service.send_email("test@example.com", "Subject", "h", "t")
            )
