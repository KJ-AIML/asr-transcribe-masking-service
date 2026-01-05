from typing import Dict, Any, Optional
from src.config.logs_config import get_logger
from src.execution.actions.process_wav2json_action import ProcessWav2JsonAction

logger = get_logger(__name__)


class ProcessWav2JsonUseCase:
    def __init__(self, action: ProcessWav2JsonAction):
        self.action = action
    
    async def execute(
        self,
        file_content: bytes,
        filename: str,
        force_model: Optional[str] = None,
        skip_model_selection: bool = False,
        auto_continue: bool = True
    ) -> Dict[str, Any]:
        """
        Process WAV file through wav2json pipeline
        
        Args:
            file_content: Binary content of the WAV file
            filename: Original filename
            force_model: Force specific model (typhoon/pathumma/pathumma_noise)
            skip_model_selection: Skip model selection, use force_model or default
            auto_continue: Auto-call process_json_endpoint internally
            
        Returns:
            Dict with complete processing results
        """
        logger.info(f"Starting wav2json processing for: {filename}")
        
        try:
            # Validate file
            if not file_content:
                raise ValueError("File content is empty")
            
            if len(file_content) < 44:
                raise ValueError("File too small to be a valid WAV file")
            
            if not file_content[:4] == b'RIFF' or not file_content[8:12] == b'WAVE':
                raise ValueError("Invalid WAV file format")
            
            # Process through action
            result = await self.action.execute(
                file_content=file_content,
                filename=filename,
                force_model=force_model,
                skip_model_selection=skip_model_selection,
                auto_continue=auto_continue
            )
            
            # Log success
            logger.info(f"Wav2Json processing completed for: {filename}")   
            return result
            
        except Exception as e:
            logger.error(f"Error in wav2json usecase: {e}")
            raise
