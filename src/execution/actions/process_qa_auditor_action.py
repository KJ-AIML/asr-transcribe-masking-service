from typing import Dict, Any
from src.config.logs_config import get_logger
from src.agents.workflows.build import build_qa_auditor_workflow

logger = get_logger(__name__)

class ProcessQAAuditorAction:
    def __init__(self):
        self._workflow = None
    
    async def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Process single chunk through QA auditor workflow"""
        chunk_id = state.get("chunk_id", 0)
        logger.info(f"Processing chunk {chunk_id} through QA auditor workflow")
        
        # Extract values from state
        masked_transcript = state.get("masked_transcript", "")
        original_transcript = state.get("original_transcript", "")
        detections = state.get("detections", [])
        current_chunk_start = state.get("current_chunk_start", 0)
        context_direction = state.get("context_direction", "both")
        context_query = state.get("context_query", "")
        qa_auditor_results = state.get("qa_auditor_results", {})
        
        # Create qa_state with extracted values
        qa_state = {
                "masked_transcript": masked_transcript,
                "original_transcript": original_transcript,
                "detections": detections,
                "chunk_id": chunk_id,
                "current_chunk_start": current_chunk_start,
                "context_direction": context_direction,
                "context_query": context_query,
                "qa_auditor_results": qa_auditor_results
        }

        # logger.info(f"QA auditor state for chunk {chunk_id}: {qa_state}")

        try:
            # Build workflow if needed
            if self._workflow is None:
                logger.debug("Building QA auditor workflow for first time")
                self._workflow = build_qa_auditor_workflow()
            
            # Execute workflow with qa_state
            result = await self._workflow.ainvoke(qa_state)
            
            logger.debug(f"Chunk {chunk_id} QA auditor workflow completed")
            
            return {
                "chunk_id": chunk_id,
                "status": "success",
                "qa_auditor_result": result.get("qa_auditor_results", {}),
                "processing_time": result.get("processing_time"),
                "workflow_steps": result.get("workflow_steps", [])
            }
            
        except Exception as e:
            logger.error(f"QA auditor workflow failed for chunk {chunk_id}: {e}")
            return {
                "chunk_id": chunk_id,
                "status": "failed",
                "error": str(e),
                "qa_auditor_result": {},
                "processing_time": None,
                "workflow_steps": []
            }