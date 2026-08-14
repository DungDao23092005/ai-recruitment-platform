from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_admin
from app.models import User
from app.schemas.admin import AdminStatsResponse
from app.services.admin_service import AdminService

router = APIRouter()


def _get_admin_service(db: AsyncSession = Depends(get_db)) -> AdminService:
    return AdminService(db)


@router.get("/stats", response_model=AdminStatsResponse)
async def get_admin_stats(
    current_user: User = Depends(require_admin),
    service: AdminService = Depends(_get_admin_service),
) -> AdminStatsResponse:
    return await service.get_stats()