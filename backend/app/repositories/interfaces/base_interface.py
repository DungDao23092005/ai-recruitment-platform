from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base_class import Base

T = TypeVar("T", bound=Base)


class BaseRepositoryInterface(ABC, Generic[T]):
    """Contract every repository must implement.

    The transaction lifecycle is owned by the caller (e.g. a service
    layer); repository methods never commit.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @abstractmethod
    async def get_by_id(self, entity_id: Any) -> T | None:
        """Retrieve an entity by primary key, excluding soft-deleted rows."""

    @abstractmethod
    async def list_all(self) -> list[T]:
        """Retrieve all non-deleted entities."""

    @abstractmethod
    async def create(self, entity: T) -> T:
        """Persist a new entity and return its refreshed state."""

    @abstractmethod
    async def update(self, entity: T) -> T:
        """Persist changes to an entity and return its refreshed state."""

    @abstractmethod
    async def soft_delete(self, entity: T) -> None:
        """Mark an entity as soft-deleted."""
