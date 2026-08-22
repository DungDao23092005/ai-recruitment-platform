import asyncio
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging

from app.services.email_providers.base import EmailProvider

logger = logging.getLogger(__name__)

class MailpitProvider(EmailProvider):
    def __init__(self, host: str = "mailpit", port: int = 1025, from_email: str = "noreply@example.com"):
        self.host = host
        self.port = port
        self.from_email = from_email

    def _send_sync(self, to_email: str, subject: str, html: str, text: str) -> None:
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = self.from_email
        message["To"] = to_email

        part1 = MIMEText(text, "plain", "utf-8")
        part2 = MIMEText(html, "html", "utf-8")
        message.attach(part1)
        message.attach(part2)

        try:
            with smtplib.SMTP(self.host, self.port, timeout=10) as server:
                server.send_message(message)
        except Exception as e:
            logger.error("ERROR: Password reset email delivery failed via Mailpit")
            raise

    async def send_password_reset_otp(self, to_email: str, otp: str) -> None:
        subject = "Đặt lại mật khẩu — AI Recruitment Platform"
        text = f"Xin chào,\n\nBạn vừa yêu cầu đặt lại mật khẩu cho tài khoản AI Recruitment Platform.\n\nMã OTP của bạn:\n{otp}\n\nMã này có hiệu lực trong 5 phút.\nKhông chia sẻ mã OTP này với bất kỳ ai.\nNếu bạn không yêu cầu đặt lại mật khẩu, hãy bỏ qua email này.\n\nAI Recruitment Platform"
        html = f'''
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #2563eb;">Đặt lại mật khẩu</h2>
                <p>Xin chào,</p>
                <p>Bạn vừa yêu cầu đặt lại mật khẩu cho tài khoản AI Recruitment Platform.</p>
                <p>Mã OTP của bạn:</p>
                <div style="background-color: #f3f4f6; padding: 20px; text-align: center; margin: 20px 0; border-radius: 8px;">
                    <span style="font-size: 32px; font-weight: bold; letter-spacing: 8px; color: #2563eb;">{otp}</span>
                </div>
                <p><strong>Mã này có hiệu lực trong 5 phút.</strong></p>
                <p style="color: #dc2626;"><strong>Cảnh báo bảo mật:</strong> Không chia sẻ mã OTP này với bất kỳ ai.</p>
                <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 20px 0;">
                <p style="font-size: 12px; color: #6b7280;">Nếu bạn không yêu cầu đặt lại mật khẩu, hãy bỏ qua email này.</p>
                <p style="font-size: 12px; color: #6b7280;">AI Recruitment Platform</p>
            </div>
        </body>
        </html>
        '''
        await asyncio.to_thread(self._send_sync, to_email, subject, html, text)
