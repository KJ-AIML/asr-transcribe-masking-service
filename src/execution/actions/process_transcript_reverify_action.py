from typing import Dict, Any
from src.config.logs_config import get_logger
from src.agents.workflows.build import build_re_verify_workflow


logger = get_logger(__name__)

class ProcessTranscriptReVerifyAction:
    def __init__(self):
        self._workflow = None
    
    async def execute(self, batch_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process a batch of detections (chunk) through re-verify workflow"""
        logger.info(f"Processing batch of {len(batch_data.get('detections', []))} detections through re-verify workflow")
        
        try:
            # Build workflow if needed
            if self._workflow is None:
                logger.debug("Building re-verify workflow for first time")
                self._workflow = build_re_verify_workflow()
        
            context_text = batch_data.get("context_text", "")
            detections = batch_data.get("detections", [])
            metadata = batch_data.get("metadata", {})
            
            # Execute workflow with re-verify format
            # We pass the whole batch_data structure
            result = await self._workflow.ainvoke({
                "detection_data": {
                    "context_text": context_text,
                    "detections": detections,
                    "metadata": metadata
                }
            })
            
            logger.debug("Re-verify workflow completed for batch")
            
            # Extract re-verify results
            re_verify_results = result.get("re_verify_results", [])
            
            # If the result is a dict with 'results' key (from JSON parsing), extract it
            if isinstance(re_verify_results, dict) and "results" in re_verify_results:
                re_verify_results = re_verify_results["results"]
            
            # logger.info(f"Extracted re-verify results: {re_verify_results}")

            return {
                "status": "success",
                "re_verify_results": re_verify_results,
                "metadata": metadata
            }
            
        except Exception as e:
            logger.error(f"Re-verify workflow failed: {e}")
            return {
                "status": "failed",
                "error": str(e),
                "re_verify_results": [],
                "metadata": batch_data.get("metadata", {})
            }
