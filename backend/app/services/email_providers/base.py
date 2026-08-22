from abc import ABC, abstractmethod

class EmailProvider(ABC):
    """Abstract base class for email providers."""
    
    @abstractmethod
    async def send_password_reset_otp(self, to_email: str, otp: str) -> None:
        """Send a password reset OTP email."""
        pass
