from typing import Any, Dict

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from src.config.logs_config import get_logger
from src.execution.actions.process_wav2file_action import ProcessWav2FileAction
from src.execution.usecases.process_wav2file_usecase import ProcessWav2FileUseCase

router = APIRouter()
logger = get_logger(__name__)


class WavFileResponse(BaseModel):
    """Response model for wav file processing"""

    message: str
    file_info: Dict[str, Any]
    processing_status: str


# Dependency injection
async def get_process_wav2file_usecase() -> ProcessWav2FileUseCase:
    action = ProcessWav2FileAction()
    return ProcessWav2FileUseCase(action)


@router.post("/process_wav2file", status_code=status.HTTP_200_OK)
async def process_wav2file_endpoint(
    file: UploadFile = File(..., description="WAV audio file to process"),
    usecase: ProcessWav2FileUseCase = Depends(get_process_wav2file_usecase),
):
    """
    Process WAV file for ASR transcription and analysis

    Args:
        file: WAV audio file to be processed

    Returns:
        WavFileResponse: Processing status and file information
    """
    try:
        # Validate file type
        if not file.filename.endswith(".wav"):
            raise ValueError("Only .wav files are supported")

        logger.info(f"Received WAV file: {file.filename}, size: {file.size}")

        # Read file content
        file_content = await file.read()

        # Process file through usecase
        result = await usecase.execute(file_content, file.filename)

        return WavFileResponse(
            message="WAV file processed successfully",
            file_info=result,
            processing_status="completed",
        )

    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error processing WAV file: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing file: {str(e)}",
        )
