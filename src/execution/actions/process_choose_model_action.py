"""
Action for choosing the best ASR model based on comparison results
"""
from typing import Dict, Any, Optional
import logging
from src.config.logs_config import get_logger
from src.agents.workflows.build import build_choose_model_to_transcribe_workflow
from src.utils.transcript.model_selection_stats import prepare_choose_model_input

logger = get_logger(__name__)


class ProcessChooseModelAction:
    """
    Action for choosing the best ASR model based on comparison analysis
    """
    
    def __init__(self):
        self._workflow = None
    
    async def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute model selection based on compare_results
        
        Args:
            state: Dict containing compare_results from ProcessWavFileAction
            
        Returns:
            Dict with chosen model and reasoning
        """
        try:
            # Get compare_results from state
            compare_results = state.get("compare_results", {})
            
            if not compare_results:
                logger.warning("No compare_results found in state")
                return {
                    "chosen_model": "typhoon",
                    "reasoning": "No comparison results available, defaulting to typhoon model",
                    "confidence": 0.5,
                    "model_selection_results": {}
                }
            
            logger.info(f"Processing model selection from {len(compare_results)} chunks")
            
            # Build workflow if needed
            if self._workflow is None:
                logger.debug("Building choose model to transcribe workflow for first time")
                self._workflow = build_choose_model_to_transcribe_workflow()
            
            # Prepare input for choose_model workflow
            choose_model_input = prepare_choose_model_input(compare_results)

            workflow_state = {
                "metrics": choose_model_input["metrics"],
                "missing_examples": choose_model_input["missing_examples"],
                "row_summaries": choose_model_input["row_summaries"],
                "analysis_timestamp": choose_model_input["analysis_timestamp"],
                "total_chunks_processed": choose_model_input["total_chunks_processed"],
                "summary_stats_text": choose_model_input.get("summary_stats_text", "")
            }
            
            # Execute workflow
            workflow_result = await self._workflow.ainvoke(workflow_state)
            
            # Extract results
            model_to_process = workflow_result.get("model_to_process", 0)
            reasoning = workflow_result.get("reasoning", "No reasoning provided")
            
            # Convert model number to name
            model_map = {0: "typhoon", 1: "pathumma", 2: "pathumma_noise"}
            chosen_model = model_map.get(model_to_process, "typhoon")
            
            # Calculate confidence based on analysis completeness
            total_chunks = choose_model_input["metrics"]["total_chunks"]
            confidence = min(0.9, 0.5 + (total_chunks / 100))
            
            logger.info(f"Model selection completed: chosen_model={chosen_model}, confidence={confidence}")
            
            return {
                "chosen_model": chosen_model,
                "reasoning": reasoning,
                "confidence": confidence,
                "model_selection_results": workflow_result,
                "analysis_summary": choose_model_input.get("summary_stats_text", ""),
                "total_chunks_analyzed": len(compare_results)
            }
            
        except Exception as e:
            logger.error(f"Error in ProcessChooseModelAction: {str(e)}")
            return {
                "chosen_model": "typhoon",
                "reasoning": f"Error during model selection: {str(e)}, defaulting to typhoon",
                "confidence": 0.3,
                "model_selection_results": {},
                "error": str(e)
            }