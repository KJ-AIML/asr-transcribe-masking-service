from fastapi import APIRouter

# Import v1 endpoints
from src.api.endpoints.v1 import (
    health,
    sample_agent,
    process_json_transcript
)

# Create v1 router
v1_router = APIRouter()

# Include v1 endpoints
v1_router.include_router(health.router, prefix="/health")
# v1_router.include_router(sample_agent.router, prefix="/sample_agent")
# v1_router.include_router(sample_workflow.router, prefix="/sample_workflow")
v1_router.include_router(process_json_transcript.router, prefix="/process_json_transcript")
