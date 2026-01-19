from typing import Any
from langgraph.graph import StateGraph, START, END
from langgraph.types import RetryPolicy
from src.agents.schemas.types import (
    State,
    ReVerifyState,
    MaskerBatchState,
    QAAuditorState,
    CompareChunkWavFilesState,
    ChooseModelToTranscribeState,
)
from src.agents.workflows.nodes import (
    llm_call_sensitive_data_classify,
    pii_worker,
    synthesizer,
    assign_pii_workers,
    llm_call_re_verify_batch,
    llm_call_masker_batch,
    llm_call_qa_auditor,
    llm_call_compare_chunk_wav_files,
    llm_call_choose_model_to_transcribe,
)
from src.config.logs_config import get_logger

# Initialize logger
logger = get_logger(__name__)


def build_workflow() -> Any:
    """
    Build and compile the ASR workflow graph.

    This function creates a StateGraph workflow that processes transcripts through
    multiple stages including PII detection, and synthesis.

    Returns:
        Compiled workflow graph ready for execution

    Workflow Flow:
        1. START -> llm_call_sensitive_data_classify
        2. llm_call_sensitive_data_classify -> assign_pii_workers -> pii_worker
        3. pii_worker -> synthesizer
        4. synthesizer -> END
    """
    logger.info("Building ASR workflow...")

    # Build workflow
    builder = StateGraph(State)

    # Add the nodes
    builder.add_node(
        "llm_call_sensitive_data_classify", llm_call_sensitive_data_classify,
        retry_policy=RetryPolicy(max_attempts=1),
    )
    builder.add_node("pii_worker", pii_worker,
        retry_policy=RetryPolicy(max_attempts=1),
    )
    builder.add_node("synthesizer", synthesizer,
        retry_policy=RetryPolicy(max_attempts=1),
    )

    builder.add_edge(START, "llm_call_sensitive_data_classify")

    builder.add_conditional_edges(
        "llm_call_sensitive_data_classify", assign_pii_workers, ["pii_worker"]
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
    builder.add_node("re_verify", llm_call_re_verify_batch,
        retry_policy=RetryPolicy(max_attempts=1),
    )

    # Add edges to connect nodes
    builder.add_edge(START, "re_verify")
    builder.add_edge("re_verify", END)
    # builder.add_edge("missing_detections", END)

    # Compile the workflow
    workflow = builder.compile()

    logger.info("Workflow compiled successfully")

    return workflow


def build_masker_workflow() -> Any:
    """
    Build and compile the masker workflow graph.

    This function creates a StateGraph workflow that processes transcripts through
    multiple stages including masker batch

    Returns:
        Compiled workflow graph ready for execution

    Workflow Flow:
        1. START -> masker_batch
        2. masker_batch -> END
    """
    logger.info("Building masker workflow...")

    # Build workflow
    builder = StateGraph(MaskerBatchState)

    # Add the nodes
    builder.add_node("masker_batch", llm_call_masker_batch,
        retry_policy=RetryPolicy(max_attempts=1),
    )

    # Add edges to connect nodes
    builder.add_edge(START, "masker_batch")
    builder.add_edge("masker_batch", END)

    # Compile the workflow
    workflow = builder.compile()

    logger.info("Workflow compiled successfully")

    return workflow


def build_qa_auditor_workflow() -> Any:
    """
    Build and compile the qa auditor workflow graph.

    This function creates a StateGraph workflow that processes transcripts through
    multiple stages including qa auditor

    Returns:
        Compiled workflow graph ready for execution

    Workflow Flow:
        1. START -> qa_auditor
        2. qa_auditor -> END
    """
    logger.info("Building qa auditor workflow...")

    # Build workflow
    builder = StateGraph(QAAuditorState)

    # Add the nodes
    builder.add_node("qa_auditor", llm_call_qa_auditor,
        retry_policy=RetryPolicy(max_attempts=1),
    )

    # Add edges to connect nodes
    builder.add_edge(START, "qa_auditor")
    builder.add_edge("qa_auditor", END)

    # Compile the workflow
    workflow = builder.compile()

    logger.info("Workflow compiled successfully")

    return workflow


def build_compare_chunk_wav_files_workflow() -> Any:
    """
    Build and compile the compare chunk wav files workflow graph.

    This function creates a StateGraph workflow that processes transcripts through
    multiple stages including compare chunk wav files

    Returns:
        Compiled workflow graph ready for execution

    Workflow Flow:
        1. START -> compare_chunk_wav_files
        2. compare_chunk_wav_files -> END
    """
    logger.info("Building compare chunk wav files workflow...")

    # Build workflow
    builder = StateGraph(CompareChunkWavFilesState)

    # Add the nodes
    builder.add_node("compare_chunk_wav_files", llm_call_compare_chunk_wav_files,
        retry_policy=RetryPolicy(max_attempts=1),
    )

    # Add edges to connect nodes
    builder.add_edge(START, "compare_chunk_wav_files")
    builder.add_edge("compare_chunk_wav_files", END)

    # Compile the workflow
    workflow = builder.compile()

    logger.info("Workflow compiled successfully")

    return workflow


def build_choose_model_to_transcribe_workflow() -> Any:
    """
    Build and compile the choose model to transcribe workflow graph.

    This function creates a StateGraph workflow that processes transcripts through
    multiple stages including choose model to transcribe

    Returns:
        Compiled workflow graph ready for execution

    Workflow Flow:
        1. START -> choose_model_to_transcribe
        2. choose_model_to_transcribe -> END
    """
    logger.info("Building choose model to transcribe workflow...")

    # Build workflow
    builder = StateGraph(ChooseModelToTranscribeState)

    # Add the nodes
    builder.add_node("choose_model_to_transcribe", llm_call_choose_model_to_transcribe,
        retry_policy=RetryPolicy(max_attempts=1),
    )

    # Add edges to connect nodes
    builder.add_edge(START, "choose_model_to_transcribe")
    builder.add_edge("choose_model_to_transcribe", END)

    # Compile the workflow
    workflow = builder.compile()

    logger.info("Workflow compiled successfully")

    return workflow
