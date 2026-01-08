from fastapi import APIRouter, status, Depends
from src.config.logs_config import get_logger
from pydantic import BaseModel
from src.execution.usecases.process_transcript_usecase import ProcessTranscriptUseCase
from src.execution.actions.process_transcript_action import ProcessTranscriptAction
from src.execution.actions.process_transcript_reverify_action import (
    ProcessTranscriptReVerifyAction,
)
from src.execution.actions.process_transcript_masker_action import (
    ProcessTranscriptMaskerAction,
)

router = APIRouter()
logger = get_logger(__name__)


class TranscriptPayload(BaseModel):
    transcript: dict


# Dependency injection
async def get_process_transcript_usecase() -> ProcessTranscriptUseCase:
    action = ProcessTranscriptAction()
    re_verify_action = ProcessTranscriptReVerifyAction()
    masker_action = ProcessTranscriptMaskerAction()
    return ProcessTranscriptUseCase(action, re_verify_action, masker_action)


@router.post("/process_json_transcript", status_code=status.HTTP_200_OK)
async def process_json_transcript_endpoint(
    payload: TranscriptPayload,
    usecase: ProcessTranscriptUseCase = Depends(get_process_transcript_usecase),
):
    """Process JSON transcript for credit card detection"""
    logger.info("Received JSON transcript processing request")

    try:
        result = await usecase.execute(payload.transcript)
        logger.info("Transcript processing completed successfully")

        # Handle None values in result to prevent serialization errors
        if result is None:
            return {
                "error": "Processing failed",
                "message": "No result returned from processing",
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
        logger.error(f"Transcript processing failed: {e}")
        return {"error": "Processing failed", "message": str(e), "status": "failed"}
