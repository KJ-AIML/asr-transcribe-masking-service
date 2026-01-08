from typing import Dict, Any
from src.config.logs_config import get_logger
from src.execution.actions.process_wav_file_action import ProcessWavFileAction

logger = get_logger(__name__)


class ProcessWavFileUseCase:
    def __init__(self, action: ProcessWavFileAction):
        self.action = action

    async def execute(
        self, file_content: bytes, filename: str, with_transcription: bool = False
    ) -> Dict[str, Any]:
        """
        Process WAV file for ASR transcription pipeline

        Args:
            file_content: Binary content of the WAV file
            filename: Original filename
            with_transcription: Whether to perform transcription or just chunking

        Returns:
            Dict with processing results including chunk transcriptions
        """
        logger.info(
            f"Starting WAV file processing for: {filename} (transcription: {with_transcription})"
        )

        try:
            # Basic file validation
            if not file_content:
                raise ValueError("File content is empty")

            # Check WAV file header (simple validation)
            if len(file_content) < 44:  # Minimum WAV header size
                raise ValueError("File too small to be a valid WAV file")

            # Check RIFF header
            if not file_content[:4] == b"RIFF" or not file_content[8:12] == b"WAVE":
                raise ValueError("Invalid WAV file format")

            # Extract file information
            file_info = {
                "filename": filename,
                "size_bytes": len(file_content),
                "size_mb": round(len(file_content) / (1024 * 1024), 2),
                "file_type": "WAV",
                "validation": "passed",
            }

            logger.info(f"WAV file validation passed: {file_info}")

            # Process WAV file through action
            if with_transcription:
                # Full transcription with all ASR models
                processing_result = await self.action.execute_with_transcription(
                    file_content, filename
                )
                next_steps = ["transcription_completed", "comparison_ready"]
            else:
                # Chunking only
                processing_result = self.action.execute(file_content, filename)
                next_steps = ["transcription_ready"]

            # Combine file info with processing results
            result = {
                **file_info,
                "processing_stage": "completed",
                "with_transcription": with_transcription,
                "chunk_processing": processing_result,
                "next_steps": next_steps,
            }

            logger.info(f"WAV file processing completed: {filename}")
            return result

        except Exception as e:
            logger.error(f"Error processing WAV file {filename}: {str(e)}")
            raise
