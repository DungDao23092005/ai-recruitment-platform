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


class AIError(Exception):
    """Base class for all AI module errors."""


class EmptyDocumentError(AIError):
    """Raised when a document contains no extractable text."""


class InvalidDocumentError(AIError):
    """Raised when a document is corrupted, invalid format, or exceeds size limits."""
