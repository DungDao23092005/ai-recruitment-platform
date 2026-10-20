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
    """Raised when AI provider is temporarily unavailable (e.g., 503)."""

    def __init__(self, message: str = "AI provider temporarily unavailable", retry_after: int | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class MatchExplanationRefreshInputError(ServiceException):
    """Missing/invalid trusted input for the match-explanation refresh.

    Raised before any quota reservation or provider call. The future API
    boundary maps this to HTTP 400.
    """

    http_status = 400


class MatchExplanationRefreshError(AIError):
    """Controlled failure for the quota-controlled match-explanation refresh.

    The internal refresh operation raises this after releasing its quota
    reservation when a valid, validated AI narrative was not produced. The
    fixed message is safe to expose; callers may map ``http_status`` (502 by
    default, 503/429 for provider availability/quota failures) without leaking
    provider errors, prompts or credentials.
    """

    def __init__(
        self,
        reason: str,
        *,
        http_status: int = 502,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(
            "The AI match explanation refresh could not be completed."
        )
        self.reason = reason
        self.http_status = http_status
        self.retry_after = retry_after


class EmptyDocumentError(AIError):
    """Raised when a document contains no extractable text."""


class InvalidDocumentError(AIError):
    """Raised when a document is corrupted, invalid format, or exceeds size limits."""


class ValidationError(ServiceException):
    """Raised when input validation fails (maps to HTTP 422)."""
