from fastapi import APIRouter
from fastapi import status

from src.agents.agent_manager.agent import sample_agent
from src.config.logs_config import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.get("/sample_agent", status_code=status.HTTP_200_OK)
async def sample_agent_endpoint(query: str = ""):
    """Sample agent endpoint for v1 API"""
    logger.debug("Sample agent requested")
    result = sample_agent.invoke(
            {
                "messages": 
                [
                    {
                        "role": "user",
                        "content": query
                    }
                ]
            }
        )
    return result["messages"]
