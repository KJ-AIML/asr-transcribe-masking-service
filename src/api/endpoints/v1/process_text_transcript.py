from fastapi import APIRouter, status, Depends
from src.config.logs_config import get_logger
from pydantic import BaseModel
from src.execution.usecases.process_transcript_usecase import ProcessTranscriptUseCase
from src.execution.actions.process_transcript_action import ProcessTranscriptAction
from src.execution.actions.process_transcript_reverify_action import ProcessTranscriptReVerifyAction

router = APIRouter()
logger = get_logger(__name__)

class TextTranscriptRequest(BaseModel):
    text: str  

# Dependency injection
async def get_process_transcript_usecase() -> ProcessTranscriptUseCase:
    action = ProcessTranscriptAction()
    re_verify_action = ProcessTranscriptReVerifyAction()
    return ProcessTranscriptUseCase(action, re_verify_action)

@router.post("/process_text_transcript", status_code=status.HTTP_200_OK)
async def process_text_transcript_endpoint(
    request: TextTranscriptRequest,
    usecase: ProcessTranscriptUseCase = Depends(get_process_transcript_usecase)
):
    """Process text transcript with timestamps for credit card detection"""
    text_length = len(request.text)
    line_count = request.text.count('\n') + 1
    logger.info(f"Received text transcript: {text_length} chars, {line_count} lines")
    
    # Log first and last lines for debugging
    lines = request.text.split('\n')
    if lines:
        logger.info(f"First line: {lines[0][:100]}...")
        logger.info(f"Last line: {lines[-1][:100]}...")
    
    try:
        # UseCase จะจัดการ parse text ให้เป็น JSON อัตโนมัติ
        result = await usecase.execute(request.text)
        logger.info("Text transcript processing completed successfully")
        return result
    except Exception as e:
        logger.error(f"Text transcript processing failed: {e}")
        return {
            "error": "Processing failed", 
            "message": str(e),
            "status": "failed"
        }

@router.post("/process_plain_text", status_code=status.HTTP_200_OK)
async def process_plain_text_endpoint(
    text: str,
    usecase: ProcessTranscriptUseCase = Depends(get_process_transcript_usecase)
):
    """Process plain text directly (no JSON wrapper) for credit card detection"""
    text_length = len(text)
    line_count = text.count('\n') + 1
    logger.info(f"Received plain text: {text_length} chars, {line_count} lines")
    
    # Log first and last lines for debugging
    lines = text.split('\n')
    if lines:
        logger.info(f"First line: {lines[0][:100]}...")
        logger.info(f"Last line: {lines[-1][:100]}...")
    
    try:
        # UseCase จะจัดการ parse text ให้เป็น JSON อัตโนมัติ
        result = await usecase.execute(text)
        logger.info("Plain text processing completed successfully")
        return result
    except Exception as e:
        logger.error(f"Plain text processing failed: {e}")
        return {
            "error": "Processing failed", 
            "message": str(e),
            "status": "failed"
        }