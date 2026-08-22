import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from app.services.email_service import EmailService
from app.services.email_providers.mailpit import MailpitProvider
from app.services.email_providers.resend import ResendProvider
from app.services.email_providers.gmail import GmailSMTPProvider

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
