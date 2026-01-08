from typing import Any, Dict

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel

from src.config.logs_config import get_logger
from src.execution.actions.process_wav_file_action import ProcessWavFileAction
from src.execution.usecases.process_wav_file_usecase import ProcessWavFileUseCase

router = APIRouter()
logger = get_logger(__name__)


class WavFileResponse(BaseModel):
    """Response model for wav file processing"""

    message: str
    file_info: Dict[str, Any]
    processing_status: str


# Dependency injection
async def get_process_wav_file_usecase() -> ProcessWavFileUseCase:
    action = ProcessWavFileAction()
    return ProcessWavFileUseCase(action)


@router.post("/process_wav_file", status_code=status.HTTP_200_OK)
async def process_wav_file_endpoint(
    file: UploadFile = File(..., description="WAV audio file to process"),
    with_transcription: bool = Query(
        False, description="Whether to perform full transcription with all ASR models"
    ),
    usecase: ProcessWavFileUseCase = Depends(get_process_wav_file_usecase),
):
    """
    Process WAV file for ASR transcription and analysis

    Args:
        file: WAV audio file to be processed
        with_transcription: If True, performs full transcription with all ASR models. If False, only chunks the file.

    Returns:
        WavFileResponse: Processing status and file information
    """
    try:
        # Validate file type
        if not file.filename.endswith(".wav"):
            raise ValueError("Only .wav files are supported")

        logger.info(
            f"Received WAV file: {file.filename}, size: {file.size}, transcription: {with_transcription}"
        )

        # Read file content
        file_content = await file.read()

        # Process file through usecase
        result = await usecase.execute(file_content, file.filename, with_transcription)

        return WavFileResponse(
            message=f"WAV file processed successfully (transcription: {with_transcription})",
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


# @router.get("/transcription_sessions", status_code=status.HTTP_200_OK)
# async def get_transcription_sessions():
#     """
#     Get all transcription sessions from memory

#     Returns:
#         List of transcription sessions with their status and results
#     """
#     try:
#         sessions = transcription_memory.list_sessions()
#         return {
#             "message": "Transcription sessions retrieved successfully",
#             "sessions": sessions,
#             "total_sessions": len(sessions)
#         }
#     except Exception as e:
#         logger.error(f"Error retrieving transcription sessions: {str(e)}")
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail=f"Error retrieving sessions: {str(e)}"
#         )

# @router.get("/transcription_sessions/{session_id}", status_code=status.HTTP_200_OK)
# async def get_transcription_session(session_id: str):
#     """
#     Get specific transcription session by ID

#     Args:
#         session_id: ID of the transcription session

#     Returns:
#         Transcription session details with all chunk transcriptions
#     """
#     try:
#         session = transcription_memory.get_session(session_id)
#         if not session:
#             raise HTTPException(
#                 status_code=status.HTTP_404_NOT_FOUND,
#                 detail=f"Session {session_id} not found"
#             )

#         return {
#             "message": "Transcription session retrieved successfully",
#             "session": session.to_dict()
#         }
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Error retrieving transcription session {session_id}: {str(e)}")
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail=f"Error retrieving session: {str(e)}"
#         )

# @router.delete("/transcription_sessions/{session_id}", status_code=status.HTTP_200_OK)
# async def delete_transcription_session(session_id: str):
#     """
#     Delete transcription session from memory

#     Args:
#         session_id: ID of the transcription session to delete

#     Returns:
#         Deletion status
#     """
#     try:
#         success = transcription_memory.delete_session(session_id)
#         if not success:
#             raise HTTPException(
#                 status_code=status.HTTP_404_NOT_FOUND,
#                 detail=f"Session {session_id} not found"
#             )

#         return {
#             "message": f"Transcription session {session_id} deleted successfully",
#             "session_id": session_id
#         }
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Error deleting transcription session {session_id}: {str(e)}")
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail=f"Error deleting session: {str(e)}"
#         )
