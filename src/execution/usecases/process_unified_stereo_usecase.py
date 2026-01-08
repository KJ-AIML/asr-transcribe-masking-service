from typing import Dict, Any, Optional
from src.config.logs_config import get_logger
from src.execution.actions.process_unified_stereo_action import (
    ProcessUnifiedStereoAction,
)

logger = get_logger(__name__)


class ProcessUnifiedStereoUseCase:
    def __init__(self, action: ProcessUnifiedStereoAction):
        self.action = action

    async def execute(
        self,
        file_content: bytes,
        filename: str,
        force_model: Optional[str] = None,
        skip_model_selection: bool = False,
        auto_continue: bool = True,
    ) -> Dict[str, Any]:
        """
        Process stereo WAV file through unified pipeline

        Args:
            file_content: Binary content of the WAV file
            filename: Original filename
            force_model: Force specific model (typhoon/pathumma/pathumma_noise)
            skip_model_selection: Skip model selection, use force_model or default
            auto_continue: Auto-call process_json_endpoint internally

        Returns:
            Dict with complete processing results
        """
        logger.info(f"Starting unified stereo processing for: {filename}")

        try:
            # Validate file
            if not file_content:
                raise ValueError("File content is empty")

            if len(file_content) < 44:  # Minimum WAV header
                raise ValueError("File too small to be a valid WAV file")

            if not file_content[:4] == b"RIFF" or not file_content[8:12] == b"WAVE":
                raise ValueError("Invalid WAV file format")

            # Process through action
            result = await self.action.execute(
                file_content=file_content,
                filename=filename,
                force_model=force_model,
                skip_model_selection=skip_model_selection,
                auto_continue=auto_continue,
            )

            logger.info(f"Unified stereo processing completed for: {filename}")
            return result

        except Exception as e:
            logger.error(f"Error in unified stereo usecase: {e}")
            raise
