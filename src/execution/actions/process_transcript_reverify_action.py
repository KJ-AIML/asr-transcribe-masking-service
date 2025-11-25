from typing import Dict, Any, List
from src.config.logs_config import get_logger
from src.agents.workflows.build import build_re_verify_workflow

logger = get_logger(__name__)

class ProcessTranscriptReVerifyAction:
    def __init__(self):
        self._workflow = None
    
    async def execute(self, detection_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process individual detection through re-verify workflow"""
        logger.info(f"Processing individual detection through re-verify workflow")
        
        try:
            # Build workflow if needed
            if self._workflow is None:
                logger.debug("Building re-verify workflow for first time")
                self._workflow = build_re_verify_workflow()
            
            # Prepare input for re-verify workflow
            # detection_data should contain:
            # - context_text: text with extended context (60s before, 20s after)
            # - detection: single detection to verify
            # - segments: segments from context
            # - context_window: context window information
            
            context_text = detection_data.get("context_text", "")
            detection = detection_data.get("detection", {})
            segments = detection_data.get("segments", [])
            context_window = detection_data.get("context_window", {})
            
            # Execute workflow with re-verify format
            result = await self._workflow.ainvoke({
                "detection_data": {
                    "context_text": context_text,
                    "detection": detection,
                    "segments": segments,
                    "context_window": context_window
                },
                "text_and_segment": {
                    "text": context_text,
                    "segments": segments,
                },
                "segments": segments,
            })
            
            logger.debug(f"Re-verify workflow completed for detection: {detection.get('type', 'unknown')}")
            
            # Extract re-verify results
            re_verify_results = result.get("re_verify_results", [])
            
            return {
                "status": "success",
                "re_verify_results": re_verify_results,
                "original_detection": detection,
                "verified_detection": self._extract_verified_detection(re_verify_results, detection),
                "context_window": context_window
            }
            
        except Exception as e:
            logger.error(f"Re-verify workflow failed: {e}")
            return {
                "status": "failed",
                "error": str(e),
                "re_verify_results": [],
                "original_detection": detection_data.get("detection", {}),
                "verified_detection": None,
                "context_window": detection_data.get("context_window", {})
            }
    
    def _extract_verified_detection(self, re_verify_results: List[Dict], original_detection: Dict) -> Dict:
        """Extract verified detection from re-verify results"""
        for result in re_verify_results:
            # Check if re-verify passed
            if result.get("status") == "PASS":
                # Return original detection that passed verification
                return original_detection
        
        # If no PASS result, return None
        return None