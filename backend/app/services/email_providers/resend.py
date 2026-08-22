import logging
import httpx

from app.services.email_providers.base import EmailProvider

logger = logging.getLogger(__name__)

class ResendProvider(EmailProvider):
    def __init__(self, api_key: str, from_email: str):
        self.api_key = api_key
        self.from_email = from_email
        self.api_url = "https://api.resend.com/emails"

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

        if not self.api_key:
            logger.error("ERROR: Password reset email delivery failed (missing Resend API key)")
            raise ValueError("Missing API key")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "from": self.from_email,
            "to": [to_email],
            "subject": subject,
            "html": html,
            "text": text
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(self.api_url, headers=headers, json=payload)
                response.raise_for_status()
        except Exception as e:
            logger.error("ERROR: Password reset email delivery failed via Resend")
            raise

