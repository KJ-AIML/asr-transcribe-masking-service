from fastapi import APIRouter
from fastapi import status

from src.agents.workflows.build import build_workflow
from src.config.logs_config import get_logger

router = APIRouter()
logger = get_logger(__name__)

workflow = build_workflow()


@router.post("/sample_workflow", status_code=status.HTTP_200_OK)
async def sample_workflow_endpoint(query: str = ""):
    """Sample workflow endpoint for v1 API"""
    logger.debug("Sample workflow requested")
    result = workflow.invoke({"original_transcript": query})

    return result
