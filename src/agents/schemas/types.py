import operator
from typing import Annotated
from pydantic import BaseModel, Field
from typing_extensions import TypedDict, Literal, Optional, List

# Stage 
class State(TypedDict):
    original_transcript: dict
    improved_transcript: dict
    issue_found: list[dict] | None
    feedback: dict | None
    self_checker_feedback_status: str
    sensitive_data_detected: dict
    subagent_response: dict
    completed_results: Annotated[list, operator.add]

class WorkerState(TypedDict):
    agent_name: str
    pii_info: list
    transcript: dict
    completed_results: Annotated[list, operator.add]

class TranscriptLine(BaseModel):
    timestamp_start: float = Field(..., description="Start time in seconds")
    timestamp_end: float = Field(..., description="End time in seconds")
    speaker: str = Field(..., description="Speaker label")
    text: str = Field(..., description="Corrected transcript text")

class TranscriptChunk(BaseModel):
    chunk_id: int = Field(..., description="Chunk identifier")
    lines: List[TranscriptLine] = Field(..., description="List of transcript lines in this chunk")
    context_before: Optional[List[TranscriptLine]] = Field(default_factory=list, description="Optional preceding context")
    context_after: Optional[List[TranscriptLine]] = Field(default_factory=list, description="Optional following context")

class Agent1Output(BaseModel):
    chunks: List[TranscriptChunk]

class LineRef(BaseModel):
    timestamp_start: float
    timestamp_end: float
    speaker: str

class Issue(BaseModel):
    issue_type: str
    severity: Literal["critical", "major", "minor"]
    line_index: int
    line_ref: LineRef
    problem: str
    expected: str
    context: str

class FeedbackForAgent1(BaseModel):
    priority_fixes: List[str] = Field(
        description="Most critical issues for Agent 1 to fix, ordered by priority."
    )
    detailed_instructions: str = Field(
        description="Specific, actionable notes to guide Agent 1 fixing this transcript."
    )

class Statistics(BaseModel):
    total_lines: int
    total_issues: int
    critical_issues: int
    major_issues: int
    minor_issues: int

class SelfCheckerResult(BaseModel):
    status: Literal["PASS", "FAIL"]
    decision_reason: str = Field(..., description="Brief explanation for the pass/fail decision.")
    issues_found: Optional[List[Issue]] = Field(
        default=None,
        description="Detailed list of identified issues if status is FAIL."
    )
    feedback_for_agent_1: Optional[FeedbackForAgent1] = Field(
        default=None,
        description="Priority fixes + detailed instructions (None if PASS)."
    )
    statistics: Statistics

# Sensitive Data State

AgentName = Literal[
    "Agent_Name",
    "Agent_ID_Card",
    "Agent_DOB",
    "Agent_Phone",
    "Agent_Address",
    "Agent_Email",
    "Agent_Coverage",
    "Agent_Premium",
    "Agent_Payment",
    "Agent_License",
    "Agent_Health",
    "Agent_Spelling",
    "Agent_Beneficiary",
    "Agent_Other",
]

PriorityLevel = Literal["CRITICAL", "MEDIUM", "LOW"]

PIICategory = Literal[
    "CUSTOMER_NAME",
    "ID_CARD",
    "DOB",
    "PHONE",
    "ADDRESS",
    "EMAIL",
    "COVERAGE",
    "PREMIUM",
    "PAYMENT",
    "LICENSE",
    "HEALTH",
    "BENEFICIARY",
    "OTHER",
]

class TimestampRange(BaseModel):
    start: float = Field(..., description="Start time in seconds")
    end: float = Field(..., description="End time in seconds")

class EstimatedLocation(BaseModel):
    line_index: int = Field(..., description="Index of the line in the chunk (0-based or the format you use)")
    timestamp_range: TimestampRange

class RoutingDecision(BaseModel):
    has_sensitive_data: bool = Field(..., description="Whether sensitive data was found")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score 0-1")
    reasoning: str = Field(..., description="Brief explanation of the decision")

class DetectedPIICategory(BaseModel):
    category: PIICategory
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence: List[str] = Field(..., description="Evidence/text supporting the detection")
    required_agent: AgentName = Field(..., description="Agent required to handle this PII category")
    priority: PriorityLevel
    estimated_locations: List[EstimatedLocation] = Field(
        default_factory=list,
        description="Locations where PII is expected to appear"
    )

class RoutingPlan(BaseModel):
    parallel_agents: List[AgentName] = Field(default_factory=list, description="Agents that can run in parallel")
    sequential_agents: List[AgentName] = Field(default_factory=list, description="Agents that must run sequentially")
    skip_agents: List[AgentName] = Field(default_factory=list, description="Agents that are not needed")

class PIIScanStatistics(BaseModel):
    total_categories_detected: int
    critical_priority: int
    medium_priority: int
    low_priority: int
    estimated_pii_count: int

class ChunkPIIResult(BaseModel):
    """Result for one chunk (chunk_id as string to support both 'chunk_001' or numeric)"""
    chunk_id: str
    routing_decision: RoutingDecision
    pii_categories_detected: List[DetectedPIICategory] = Field(default_factory=list)
    routing_plan: RoutingPlan
    statistics: PIIScanStatistics

class SensitiveDataDetectorOutput(BaseModel):
    """Combined output for the PII detection and routing stage"""
    results: List[ChunkPIIResult] = Field(..., description="List of results per chunk")
    # Overall summary for the job (if needed)
    overall_has_sensitive_data: bool = Field(
        ...,
        description="true if at least one chunk contains PII"
    )
    overall_priority: PriorityLevel = Field(
        ...,
        description="Highest priority level found in this job"
    )

#PII State

class PIIDetection(BaseModel):
    """Single PII detection instance"""
    pii_type: PIICategory = Field(..., description="Type of PII detected")
    value: str = Field(..., description="Detected PII value (masked if sensitive)")
    raw_value: Optional[str] = Field(None, description="Full unmasked value (for internal use only)")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Detection confidence 0-1")
    
    start_time: float = Field(..., description="Start timestamp in seconds")
    end_time: float = Field(..., description="End timestamp in seconds")
    
    line_indices: List[int] = Field(..., description="Line indices where PII appears (0-based)")
    speaker: Literal["Agent", "Caller"] = Field(..., description="Who provided the PII")
    
    context: str = Field(..., description="Surrounding context explaining the detection")
    detection_method: str = Field(..., description="How it was detected: pattern/keyword/context")
    
    should_censor: bool = Field(..., description="Whether this should be censored in audio")
    censor_method: Literal["beep", "silence", "replacement"] = Field(
        default="beep",
        description="Method to use for censoring"
    )
    
    validation_notes: Optional[str] = Field(None, description="Additional validation notes or warnings")

class PIIWorkerStatistics(BaseModel):
    """Statistics for PII worker processing"""
    agent_name: AgentName
    category_processed: PIICategory
    total_detections: int
    high_confidence: int = Field(..., description="Detections with confidence >= 0.8")
    medium_confidence: int = Field(..., description="Detections with 0.5 <= confidence < 0.8")
    low_confidence: int = Field(..., description="Detections with confidence < 0.5")
    censoring_required: int = Field(..., description="Number of detections marked for censoring")
    processing_time_ms: Optional[float] = Field(None, description="Processing time in milliseconds")

class PIIWorkerOutput(BaseModel):
    """Output from a single PII worker agent"""
    agent_name: AgentName = Field(..., description="Name of the agent that processed this")
    category: PIICategory = Field(..., description="PII category this agent specializes in")
    
    detections: List[PIIDetection] = Field(
        default_factory=list,
        description="List of all PII instances detected"
    )
    
    statistics: PIIWorkerStatistics
    
    flags: List[str] = Field(
        default_factory=list,
        description="Any warnings or special notes about the detection"
    )
    
    status: Literal["success", "partial", "error"] = Field(
        default="success",
        description="Processing status"
    )
    
    error_message: Optional[str] = Field(None, description="Error details if status is error")

# For the final synthesized output
class SynthesizedPIIResult(BaseModel):
    """Final aggregated result from all PII workers"""
    chunk_id: str
    
    all_detections: List[PIIDetection] = Field(
        default_factory=list,
        description="All PII detections from all agents"
    )
    
    worker_results: List[PIIWorkerOutput] = Field(
        default_factory=list,
        description="Individual results from each worker"
    )
    
    total_pii_found: int
    total_censor_segments: int
    
    conflicts: List[dict] = Field(
        default_factory=list,
        description="Any conflicts or overlaps between detections"
    )
    
    overall_status: Literal["complete", "partial", "failed"]