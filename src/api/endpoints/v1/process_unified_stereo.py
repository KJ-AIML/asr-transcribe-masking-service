from fastapi import APIRouter, status, Depends, UploadFile, File, HTTPException, Query
from pydantic import BaseModel
from typing import Dict, Any, Optional
from src.config.logs_config import get_logger
from src.execution.usecases.process_unified_stereo_usecase import (
    ProcessUnifiedStereoUseCase,
)
from src.execution.actions.process_unified_stereo_action import (
    ProcessUnifiedStereoAction,
)

router = APIRouter()
logger = get_logger(__name__)


class UnifiedStereoResponse(BaseModel):
    """Response model for unified stereo processing"""

    message: str
    processing_status: str
    results: Dict[str, Any]


# Dependency injection
async def get_process_unified_stereo_usecase() -> ProcessUnifiedStereoUseCase:
    action = ProcessUnifiedStereoAction()
    return ProcessUnifiedStereoUseCase(action)


@router.post("/process-unified-stereo", status_code=status.HTTP_200_OK)
async def process_unified_stereo_endpoint(
    file: UploadFile = File(..., description="Stereo WAV audio file to process"),
    force_model: Optional[str] = Query(
        None, description="Force specific model: typhoon, pathumma, or pathumma_noise"
    ),
    skip_model_selection: bool = Query(
        False, description="Skip model selection and use force_model or default"
    ),
    auto_continue: bool = Query(
        True, description="Auto-call process_json_endpoint internally"
    ),
    usecase: ProcessUnifiedStereoUseCase = Depends(get_process_unified_stereo_usecase),
):
    """
    Unified endpoint for processing stereo WAV files

    This endpoint performs complete pipeline:
    1. Model selection (if not skipped)
    2. Speaker separation (Agent/Caller)
    3. Transcription with word-level timestamps
    4. JSON structure generation
    5. Auto-continue to process_json (if enabled)

    Args:
        file: Stereo WAV audio file
        force_model: Force specific ASR model
        skip_model_selection: Skip model selection step
        auto_continue: Auto-process with process_json_endpoint

    Returns:
        UnifiedStereoResponse: Complete processing results
    """
    try:
        # Validate file type
        if not file.filename.endswith(".wav"):
            raise HTTPException(status_code=400, detail="Only .wav files are supported")

        # Validate model if provided
        if force_model and force_model not in ["typhoon", "pathumma", "pathumma_noise"]:
            raise HTTPException(
                status_code=400,
                detail="Invalid model. Must be: typhoon, pathumma, or pathumma_noise",
            )

        logger.info(
            f"Received unified stereo request: {file.filename}, "
            f"force_model: {force_model}, "
            f"skip_selection: {skip_model_selection}, "
            f"auto_continue: {auto_continue}"
        )

        # Read file content
        file_content = await file.read()

        # Process through usecase
        result = await usecase.execute(
            file_content=file_content,
            filename=file.filename,
            force_model=force_model,
            skip_model_selection=skip_model_selection,
            auto_continue=auto_continue,
        )

        return UnifiedStereoResponse(
            message=f"Successfully processed {file.filename}",
            processing_status="completed",
            results=result,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in unified stereo endpoint: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
