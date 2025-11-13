from fastapi import APIRouter

# Import versioned routers
from src.api.endpoints.v1.routers import v1_router

# Create main API router
api_router = APIRouter()

# Include versioned routers with their prefixes
api_router.include_router(v1_router, prefix="/v1", tags=["v1"])
