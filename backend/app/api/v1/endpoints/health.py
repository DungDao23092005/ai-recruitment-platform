from typing import Dict
from fastapi import APIRouter

from app.core.config import settings

router = APIRouter()


@router.get("/health", response_model=Dict[str, str])
async def health_check() -> Dict[str, str]:
    """
    Health check endpoint to verify system status.
    """
    return {
        "status": "healthy",
        "service": "AI Recruitment Platform API",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT
    }
