from typing import Any, Dict

from src.config.logs_config import get_logger
from src.execution.actions.process_file2choose_model_action import (
    ProcessFile2ChooseModelAction,
)
from src.utils.file.json_utils import save_result_to_json

logger = get_logger(__name__)


class ProcessFile2ChooseModelUseCase:
    def __init__(self, action: ProcessFile2ChooseModelAction):
        self.action = action

    async def execute(
        self,
        json_data: Dict[str, Any],
        filename: str,
    ) -> Dict[str, Any]:
        """
        Process JSON data containing chunk_dict for ASR model selection

        Args:
            json_data: JSON data containing chunk_dict and other information
            filename: Original filename for reference

        Returns:
            Dict with processing results including model selection
        """
        logger.info(f"Starting model selection for: {filename}")

        try:
            # Debug: Print the structure of json_data
            logger.info(f"JSON data keys: {list(json_data.keys())}")

            # Extract chunk_dict from json_data
            # The wav2file action returns chunk_dict directly
            chunk_dict = None

            # First try the most common structure - chunk_dict at the root level
            if "chunk_dict" in json_data and isinstance(json_data["chunk_dict"], dict):
                chunk_dict = json_data["chunk_dict"]
                logger.info(
                    f"Found chunk_dict at root level with {len(chunk_dict)} chunks"
                )

            # If not found, try the nested structure (older format)
            elif "chunk_processing" in json_data:
                chunk_processing = json_data["chunk_processing"]
                if (
                    isinstance(chunk_processing, dict)
                    and "chunk_dict" in chunk_processing
                ):
                    chunk_dict = chunk_processing["chunk_dict"]
                    logger.info(
                        f"Found chunk_dict in chunk_processing with {len(chunk_dict)} chunks"
                    )
                elif isinstance(chunk_processing, dict) and any(
                    k.isdigit() for k in chunk_processing.keys()
                ):
                    # chunk_processing itself is the chunk_dict
                    chunk_dict = {
                        k: v for k, v in chunk_processing.items() if k.isdigit()
                    }
                    logger.info(
                        f"Using chunk_processing as chunk_dict with {len(chunk_dict)} chunks"
                    )

            # If still not found, try to find a dict with numeric keys at any level
            if not chunk_dict:
                for key, value in json_data.items():
                    if isinstance(value, dict) and any(
                        k.isdigit() for k in value.keys()
                    ):
                        chunk_dict = {k: v for k, v in value.items() if k.isdigit()}
                        logger.info(
                            f"Found chunks in '{key}' with {len(chunk_dict)} chunks"
                        )
                        break

            if not chunk_dict:
                raise ValueError(
                    "Could not find valid chunk_dict with numeric chunk IDs. Available keys: "
                    + str(list(json_data.keys()))
                )

            # Debug: Check the structure of chunk_dict
            logger.info(f"Chunk dict type: {type(chunk_dict)}")
            logger.info(
                f"Number of chunks: {len(chunk_dict) if isinstance(chunk_dict, dict) else 0}"
            )

            if isinstance(chunk_dict, dict):
                logger.info(
                    f"Chunk dict keys sample: {list(chunk_dict.keys())[:5] if chunk_dict else 'Empty'}"
                )
                # Check the structure of first chunk
                first_key = next(iter(chunk_dict), None)
                if first_key:
                    first_chunk = chunk_dict[first_key]
                    logger.info(f"First chunk type: {type(first_chunk)}")
                    if isinstance(first_chunk, dict):
                        logger.info(f"First chunk keys: {list(first_chunk.keys())}")
                        # Verify the expected structure
                        if "chunk_info" not in first_chunk:
                            logger.warning(f"First chunk missing 'chunk_info' key")
                        if "model_transcriptions" not in first_chunk:
                            logger.warning(
                                f"First chunk missing 'model_transcriptions' key"
                            )

            if not chunk_dict:
                raise ValueError("chunk_dict cannot be empty")

            logger.info(f"Extracted chunk_dict with {len(chunk_dict)} items")

            # Process chunk_dict through action
            processing_result = await self.action.execute(chunk_dict)

            # Create result with original file info and model selection results
            result = {
                "filename": filename,
                "processing_stage": "model_selection_completed",
                "model_selection": processing_result,
            }

            try:
                # Add the file path before saving
                result["json_file_path"] = (
                    f"src/data/wav2files/{filename}_model_selection.json"
                )
                json_file_path = save_result_to_json(
                    result, f"{filename}_model_selection"
                )
                logger.info(f"Model selection results saved to: {json_file_path}")
            except Exception as e:
                logger.error(f"Failed to save results to JSON: {str(e)}")

            logger.info(f"Model selection completed for: {filename}")

            return result

        except Exception as e:
            logger.error(f"Error in model selection for {filename}: {str(e)}")
            raise
