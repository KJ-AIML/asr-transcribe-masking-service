from typing import Dict, Any
from src.config.logs_config import get_logger
from src.agents.workflows.build import build_workflow

logger = get_logger(__name__)


class ProcessTranscriptAction:
    def __init__(self):
        self._workflow = None

    async def execute(self, chunk_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process single chunk through credit card detection workflow"""
        chunk_id = chunk_data["metadata"]["chunk_index"]
        logger.info(f"Processing chunk {chunk_id} through workflow")

        try:
            # Build workflow if needed
            if self._workflow is None:
                logger.debug("Building workflow for first time")
                self._workflow = build_workflow()

            # Execute workflow with expected format
            # result = await self._workflow.ainvoke({
            #     "original_transcript": {
            #         "segments": chunk_data.get("segments", []),
            #         "chunk_id": chunk_id,
            #         "metadata": chunk_data.get("metadata", {}),
            #         "simple_text": chunk_data.get("simple_text", ""),
            #         "text": chunk_data.get("text", ""),
            #         "words": chunk_data.get("words", [])
            #     }
            # })

            # Renumber segment IDs to 0,1,2,3... for this chunk
            # This ensures LLM-generated segment_ids match actual segment IDs
            segments_with_words = []
            for i, segment in enumerate(chunk_data.get("segments", [])):
                segment_copy = segment.copy()
                segment_copy["id"] = i
                segments_with_words.append(segment_copy)

            result = await self._workflow.ainvoke(
                {
                    "chunk_data": chunk_data,
                    "text_and_segment": {
                        "text": chunk_data.get("text", ""),
                        "segments": segments_with_words,
                    },
                    "segments": segments_with_words,
                }
            )

            logger.debug(f"Chunk {chunk_id} workflow completed")

            # Extract detections from subagent_response
            subagent_response = result.get("subagent_response", {})
            subagent_response.get("all_detections", [])

            return {
                "chunk_id": chunk_id,
                "status": "success",
                "subagent_response": result.get("subagent_response", {}),
                "processing_time": result.get("processing_time"),
                "workflow_steps": result.get("workflow_steps", []),
            }

        except Exception as e:
            logger.error(f"Workflow failed for chunk {chunk_id}: {e}")
            return {
                "chunk_id": chunk_id,
                "status": "failed",
                "error": str(e),
                "subagent_response": {"masking_results": [], "summary": {}},
                "processing_time": None,
                "workflow_steps": [],
            }
