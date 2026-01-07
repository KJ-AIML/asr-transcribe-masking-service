from fastapi import APIRouter, status, Depends
from src.config.logs_config import get_logger
from pydantic import BaseModel
from typing import Dict, Any, List
from src.execution.usecases.process_qa_auditor_usecase import ProcessQAAuditorUseCase
from src.execution.actions.process_qa_auditor_action import ProcessQAAuditorAction

router = APIRouter()
logger = get_logger(__name__)


class QAAuditorPayload(BaseModel):
    total_chunks: int
    chunks_with_credit_card: int
    processed_chunks: List[Dict[str, Any]]
    chunking_info: Dict[str, Any]
    processing_summary: Dict[str, Any]
    re_verify_results: List[Dict[str, Any]]
    re_verify_summary: Dict[str, Any]
    masker_result: Dict[str, Any]
    original_transcript: str
    masked_transcript: str
    masker_summary: Dict[str, Any]


# Dependency injection
async def get_process_qa_auditor_usecase() -> ProcessQAAuditorUseCase:
    action = ProcessQAAuditorAction()
    return ProcessQAAuditorUseCase(action)


@router.post("/process_qa_auditor", status_code=status.HTTP_200_OK)
async def process_qa_auditor_endpoint(
    payload: QAAuditorPayload,
    usecase: ProcessQAAuditorUseCase = Depends(get_process_qa_auditor_usecase),
):
    """Process QA auditor for masked transcript validation"""
    logger.info("Received QA auditor processing request")

    try:
        # Convert payload to dict for processing
        process_output = payload.dict()

        # Log payload structure for debugging
        logger.info(f"Payload keys: {process_output.keys()}")
        if "masker_result" in process_output:
            logger.info(
                f"Masker result keys in payload: {list(process_output['masker_result'].keys())}"
            )
            if "original_transcript" in process_output["masker_result"]:
                logger.info(
                    f"Original transcript found in payload masker_result, length: {len(process_output['masker_result']['original_transcript'])}"
                )
        if "original_transcript" in process_output:
            logger.info(
                f"Original transcript found at payload top level, length: {len(process_output['original_transcript'])}"
            )
            logger.info(
                f"Original transcript preview: {process_output['original_transcript'][:100]}..."
            )
        else:
            logger.warning("No original_transcript found in payload at top level")

        result = await usecase.execute(process_output)
        logger.info("QA auditor processing completed successfully")

        # Handle None values in result to prevent serialization errors
        if result is None:
            return {
                "error": "Processing failed",
                "message": "No result returned from QA auditor processing",
                "status": "failed",
            }

        # Log the result for debugging
        logger.info(f"Result type: {type(result)}")
        logger.info(
            f"Result keys: {result.keys() if isinstance(result, dict) else 'Not a dict'}"
        )

        # Recursively clean None values from nested dictionaries
        def clean_none_values(obj):
            if obj is None:
                return None
            elif isinstance(obj, dict):
                # Filter out None values from dictionaries
                try:
                    return {
                        k: clean_none_values(v) for k, v in obj.items() if v is not None
                    }
                except Exception as e:
                    logger.error(
                        f"Error cleaning dict: {e}, dict keys: {obj.keys() if obj else 'None dict'}"
                    )
                    raise
            elif isinstance(obj, list):
                # Filter out None values from lists
                try:
                    return [clean_none_values(item) for item in obj if item is not None]
                except Exception as e:
                    logger.error(
                        f"Error cleaning list: {e}, list length: {len(obj) if obj else 'None list'}"
                    )
                    raise
            else:
                return obj

        try:
            cleaned_result = clean_none_values(result)
        except Exception as e:
            logger.error(f"Error in clean_none_values: {e}")
            logger.error(f"Result that caused error: {result}")
            raise
        return cleaned_result
    except Exception as e:
        logger.error(f"QA auditor processing failed: {e}")
        return {"error": "Processing failed", "message": str(e), "status": "failed"}
