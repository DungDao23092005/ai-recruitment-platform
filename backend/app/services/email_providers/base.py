from abc import ABC, abstractmethod

class EmailProvider(ABC):
    """Abstract base class for email providers."""

    @abstractmethod
    async def send_email(
        self, to_email: str, subject: str, html: str, text: str
    ) -> None:
        """Send an arbitrary email with an HTML body and plain-text fallback."""
        pass

    @abstractmethod
    async def send_password_reset_otp(self, to_email: str, otp: str) -> None:
        """Send a password reset OTP email."""
        pass
