from fastapi import APIRouter

# Import v1 endpoints
from src.api.endpoints.v1 import (
    health,
    process_file2choose_model,
    process_json_transcript,
    process_qa_auditor,
    process_wav2file,
    process_unified_stereo,
)

# Create v1 router
v1_router = APIRouter()

# Include v1 endpoints
v1_router.include_router(health.router, prefix="/health", tags=["Health"])
v1_router.include_router(
    process_json_transcript.router,
    prefix="/process_json_transcript",
    tags=["Transcription"],
)
v1_router.include_router(
    process_qa_auditor.router, prefix="/process_qa_auditor", tags=["QA"]
)
# v1_router.include_router(process_wav_file.router, prefix="/process_wav_file")
v1_router.include_router(
    process_wav2file.router, prefix="/process_wav2file", tags=["wavfiles"]
)
v1_router.include_router(
    process_file2choose_model.router,
    prefix="/process_file2choose_model",
    tags=["wavfiles"],
)
v1_router.include_router(
    process_unified_stereo.router,
    prefix="/process_unified_stereo",
    tags=["Full Pipeline"],
)
