from typing import Dict, Any
from src.config.logs_config import get_logger
from src.agents.workflows.build import build_compare_chunk_wav_files_workflow

logger = get_logger(__name__)


class ProcessCompareChunkWavFilesAction:
    def __init__(self):
        self._workflow = None

    async def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Process single chunk through compare chunk wav files workflow"""
        chunk_id = state.get("chunk_id", 0)
        chunk_data = state.get("chunk_data", {})
        logger.info(
            f"Processing chunk {chunk_id} through compare chunk wav files workflow"
        )

        # Pass the complete chunk data to the workflow
        compare_chunk_wav_files_state = {
            "chunk_id": chunk_id,
            "chunk_info": chunk_data.get("chunk_info", {}),
            "model_transcriptions": chunk_data.get("model_transcriptions", {}),
        }

        try:
            # Build workflow if needed
            if self._workflow is None:
                logger.debug("Building compare chunk wav files workflow for first time")
                self._workflow = build_compare_chunk_wav_files_workflow()

            # Execute workflow with compare_chunk_wav_files_state
            result = await self._workflow.ainvoke(compare_chunk_wav_files_state)

            logger.debug(f"Chunk {chunk_id} compare chunk wav files workflow completed")

            return {
                "chunk_id": chunk_id,
                "status": "success",
                "compare_chunk_wav_files_result": result.get(
                    "compare_chunk_wav_files_results", {}
                ),
                "processing_time": result.get("processing_time"),
                "workflow_steps": result.get("workflow_steps", []),
            }

        except Exception as e:
            logger.error(
                f"Compare chunk wav files workflow failed for chunk {chunk_id}: {e}"
            )
            return {
                "chunk_id": chunk_id,
                "status": "failed",
                "error": str(e),
                "compare_chunk_wav_files_result": {},
                "processing_time": None,
                "workflow_steps": [],
            }
