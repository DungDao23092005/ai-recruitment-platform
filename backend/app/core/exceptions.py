from __future__ import annotations


class ServiceException(Exception):
    """Base class for all service-layer errors."""


class EntityNotFoundException(ServiceException):
    """Raised when a requested entity does not exist."""


class ConflictException(ServiceException):
    """Raised when an operation conflicts with existing state (e.g. duplicates)."""


class InvalidTransitionException(ServiceException):
    """Raised when a domain state transition is not allowed."""


class ForbiddenException(ServiceException):
    """Raised when an operation is not permitted for the caller."""


class LockedAccountException(ForbiddenException):
    """Raised when a locked account attempts to authenticate with correct credentials."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class AIError(Exception):
    """Base class for all AI module errors."""


class AIProviderQuotaExceededError(AIError):
    """Raised when AI provider quota or rate limit is exceeded."""

    def __init__(self, message: str = "AI provider quota exceeded", retry_after: int | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class AIProviderUnavailableError(AIError):
    """Raised when AI provider is temporarily unavailable."""


class EmptyDocumentError(AIError):
    """Raised when a document contains no extractable text."""


class InvalidDocumentError(AIError):
    """Raised when a document is corrupted, invalid format, or exceeds size limits."""


class ValidationError(ServiceException):
    """Raised when input validation fails (maps to HTTP 422)."""
