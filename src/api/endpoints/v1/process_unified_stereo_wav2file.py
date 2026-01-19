from fastapi import APIRouter, status, Depends, UploadFile, File, HTTPException, Query
from pydantic import BaseModel
from typing import Dict, Any, Optional
from src.config.logs_config import get_logger
from src.execution.usecases.process_unified_stereo_usecase import (
    ProcessUnifiedStereoWav2FileUseCase,
)
from src.execution.actions.process_unified_stereo_action import (
    ProcessUnifiedStereoWav2FileAction,
)


router = APIRouter()
logger = get_logger(__name__)


class UnifiedStereoWav2FileResponse(BaseModel):
    message: str
    processing_status: str
    results: Dict[str, Any]


async def get_process_unified_stereo_wav2file_usecase() -> ProcessUnifiedStereoWav2FileUseCase:
    action = ProcessUnifiedStereoWav2FileAction()
    return ProcessUnifiedStereoWav2FileUseCase(action)


@router.post("/process-unified-stereo-wav2file", status_code=status.HTTP_200_OK)
async def process_unified_stereo_wav2file_endpoint(
    file: UploadFile = File(
        ..., description="Stereo WAV audio file to process with fixed-chunk pipeline"
    ),
    force_model: Optional[str] = Query(
        None,
        description="Force specific model: typhoon, pathumma, or pathumma_noise (pathumma recommended)",
    ),
    skip_model_selection: bool = Query(
        False, description="Skip model selection and use force_model or default pathumma",
    ),
    auto_continue: bool = Query(
        True, description="Auto-call process_json_endpoint internally (placeholder)",
    ),
    usecase: ProcessUnifiedStereoWav2FileUseCase = Depends(
        get_process_unified_stereo_wav2file_usecase
    ),
):
    try:
        if not file.filename.endswith(".wav"):
            raise HTTPException(status_code=400, detail="Only .wav files are supported")

        if force_model and force_model not in ["typhoon", "pathumma", "pathumma_noise"]:
            raise HTTPException(
                status_code=400,
                detail="Invalid model. Must be: typhoon, pathumma, or pathumma_noise",
            )

        logger.info(
            f"Received unified stereo WAV2FILE-style request: {file.filename}, "
            f"force_model: {force_model}, "
            f"skip_selection: {skip_model_selection}, "
            f"auto_continue: {auto_continue}"
        )

        file_content = await file.read()

        result = await usecase.execute(
            file_content=file_content,
            filename=file.filename,
            force_model=force_model,
            skip_model_selection=skip_model_selection,
            auto_continue=auto_continue,
        )

        return UnifiedStereoWav2FileResponse(
            message=f"Successfully processed {file.filename} with WAV2FILE-style pipeline",
            processing_status="completed",
            results=result,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in unified stereo WAV2FILE-style endpoint: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

