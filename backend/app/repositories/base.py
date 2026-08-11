from __future__ import annotations

from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base_class import Base
from app.repositories.interfaces.base_interface import BaseRepositoryInterface

T = TypeVar("T", bound=Base)


class BaseRepository(BaseRepositoryInterface[T], Generic[T]):
    """Generic async repository implementing soft-delete-aware CRUD.

    Soft-delete filtering is applied conditionally: models without an
    ``is_deleted`` column (e.g. junction tables) are queried unfiltered.
    """

    def __init__(self, session: AsyncSession, model: type[T]) -> None:
        super().__init__(session)
        self.model = model

    @staticmethod
    def _is_soft_deletable(model: type[Base]) -> bool:
        return "is_deleted" in model.__table__.columns

    async def get_by_id(self, entity_id: Any) -> T | None:
        stmt = select(self.model).where(self.model.id == entity_id)
        if self._is_soft_deletable(self.model):
            stmt = stmt.where(self.model.is_deleted.is_(False))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self) -> list[T]:
        stmt = select(self.model)
        if self._is_soft_deletable(self.model):
            stmt = stmt.where(self.model.is_deleted.is_(False))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, entity: T) -> T:
        self.session.add(entity)
        await self.session.flush()
        await self.session.refresh(entity)
        return entity

    async def update(self, entity: T) -> T:
        await self.session.flush()
        await self.session.refresh(entity)
        return entity

    async def soft_delete(self, entity: T) -> None:
        if not self._is_soft_deletable(self.model):
            raise ValueError(
                f"{self.model.__name__} has no 'is_deleted' column "
                "and cannot be soft-deleted"
            )
        entity.is_deleted = True
        await self.session.flush()
