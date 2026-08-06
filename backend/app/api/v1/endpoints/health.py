from typing import Dict
from fastapi import APIRouter

router = APIRouter()


@router.get("/health", response_model=Dict[str, str])
async def health_check() -> Dict[str, str]:
    """
    Health check endpoint to verify system status.
    """
    return {
        "status": "healthy",
        "service": "AI Recruitment Platform API",
        "version": "1.0.0"
    }
