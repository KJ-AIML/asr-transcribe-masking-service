from typing import Any, Dict

from src.config.logs_config import get_logger
from src.execution.actions.process_wav2file_action import ProcessWav2FileAction
from src.utils.file.json_utils import save_result_to_json

logger = get_logger(__name__)


class ProcessWav2FileUseCase:
    def __init__(self, action: ProcessWav2FileAction):
        self.action = action

    async def execute(
        self,
        file_content: bytes,
        filename: str,
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
        logger.info(f"Starting WAV file processing for: {filename})")

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

            processing_result = await self.action.execute_with_transcription(
                file_content, filename
            )

            # Combine file info with processing results
            result = {
                **file_info,
                "processing_stage": "completed",
                "chunk_processing": processing_result,
            }

            try:
                # Add the file path before saving
                result["json_file_path"] = f"src/data/wav2files/{filename}.json"
                json_file_path = save_result_to_json(result, filename)
                logger.info(f"Results saved to: {json_file_path}")
            except Exception as e:
                logger.error(f"Failed to save results to JSON: {str(e)}")

            logger.info(f"WAV file processing completed: {filename}")

            return result

        except Exception as e:
            logger.error(f"Error processing WAV file {filename}: {str(e)}")
            raise
