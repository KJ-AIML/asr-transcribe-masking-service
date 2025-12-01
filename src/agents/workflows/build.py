from typing import Any
from langgraph.graph import StateGraph, START, END
from src.agents.schemas.types import State, ReVerifyState
from src.agents.workflows.nodes import (
    llm_call_context_improver,
    llm_call_self_checker,
    llm_call_sensitive_data_classify,
    pii_worker,
    synthesizer,
    route_check,
    assign_pii_workers,
    llm_call_re_verify_batch,
)
from src.config.logs_config import get_logger

# Initialize logger
logger = get_logger(__name__)


def build_workflow() -> Any:
    """
    Build and compile the ASR workflow graph.
    
    This function creates a StateGraph workflow that processes transcripts through
    multiple stages including context improvement, self-checking, PII detection,
    and synthesis.
    
    Returns:
        Compiled workflow graph ready for execution
        
    Workflow Flow:
        1. START -> llm_call_context_improver
        2. llm_call_context_improver -> llm_call_self_checker
        3. llm_call_self_checker -> (conditional) -> 
           - Accepted -> llm_call_sensitive_data_classify
           - Rejected -> llm_call_context_improver
        4. llm_call_sensitive_data_classify -> assign_pii_workers -> pii_worker
        5. pii_worker -> synthesizer
        6. synthesizer -> END
    """
    logger.info("Building ASR workflow...")
    
    # Build workflow
    builder = StateGraph(State)

    # Add the nodes
    builder.add_node("llm_call_context_improver", llm_call_context_improver)
    builder.add_node("llm_call_self_checker", llm_call_self_checker)
    builder.add_node("llm_call_sensitive_data_classify", llm_call_sensitive_data_classify)
    builder.add_node("pii_worker", pii_worker)
    builder.add_node("synthesizer", synthesizer)

    # Add edges to connect nodes
    builder.add_edge(START, "llm_call_sensitive_data_classify")
    # builder.add_edge("llm_call_context_improver", "llm_call_self_checker")
    # builder.add_conditional_edges(
    #     "llm_call_self_checker",
    #     route_check,
    #     {
    #         "Accepted": "llm_call_sensitive_data_classify",
    #         "Rejected": "llm_call_context_improver",
    #     },
    # )

    # builder.add_edge("llm_call_sensitive_data_classify", END)

    builder.add_conditional_edges(
        "llm_call_sensitive_data_classify",
        assign_pii_workers,
        ["pii_worker"]
    )
    builder.add_edge("pii_worker", "synthesizer")
    builder.add_edge("synthesizer", END)

    # Compile the workflow
    workflow = builder.compile()
    
    logger.info("Workflow compiled successfully")

    return workflow

def build_re_verify_workflow() -> Any:
    """
    Build and compile the re-verify workflow graph.
    
    This function creates a StateGraph workflow that processes transcripts through
    multiple stages including re_verify, missing detections
    
    Returns:
        Compiled workflow graph ready for execution
        
    Workflow Flow:
        1. START -> re_verify
        2. re_verify -> END
    """
    logger.info("Building re-verify workflow...")
    
    # Build workflow
    builder = StateGraph(ReVerifyState)

    # Add the nodes
    builder.add_node("re_verify", llm_call_re_verify_batch)
    
    # Add edges to connect nodes
    builder.add_edge(START, "re_verify")
    builder.add_edge("re_verify", END)
    # builder.add_edge("missing_detections", END)
    
    # Compile the workflow
    workflow = builder.compile()
    
    logger.info("Workflow compiled successfully")

    return workflow
