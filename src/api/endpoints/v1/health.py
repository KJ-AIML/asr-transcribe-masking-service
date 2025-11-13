from fastapi import APIRouter
from fastapi import status

from src.config.logs_config import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.get("", status_code=status.HTTP_200_OK)
async def health_check():
    """Health check endpoint for v1 API"""
    logger.debug("Health check requested")
    return {
        "status": "healthy",
        "version": "v1",
        "service": "AI Structure Microservice",
    }
