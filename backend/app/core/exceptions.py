from __future__ import annotations


class ServiceException(Exception):
    """Base class for all service-layer errors."""


class EntityNotFoundException(ServiceException):
    """Raised when a requested entity does not exist."""


class ConflictException(ServiceException):
    """Raised when an operation conflicts with existing state (e.g. duplicates)."""


class InvalidTransitionException(ServiceException):
    """Raised when a domain state transition is not allowed."""
