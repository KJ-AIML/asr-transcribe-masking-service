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
    text_and_segment: dict
    chunk_data: dict
    segments: list

class WorkerState(TypedDict):
    agent_name: str
    pii_info: list
    transcript: dict
    text_and_segment: dict
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
    segment_index: int
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
    "Agent_Payment",
]

PriorityLevel = Literal["CRITICAL", "MEDIUM", "LOW"]

PIICategory = Literal[
    "PAYMENT",
]

class DigitGroup(BaseModel):
    segment_id: int = Field(..., description="Segment ID where this digit group appears")
    text: str = Field(..., description="Original Thai text from transcript")
    arabic: str = Field(..., description="Converted to Arabic numerals")

class TimestampRange(BaseModel):
    start: float = Field(..., description="Start time in seconds")
    end: float = Field(..., description="End time in seconds")

class CreditCardSection(BaseModel):
    section_type: Literal[
        "SEQUENTIAL_SPELLING", "FULL_MENTION", "AGENT_CONFIRMATION",
        "EXPIRY_DATE", "CVV"
    ] = Field(..., description="Type of credit card PII detected")
    detection_method: str = Field(..., description="How the PII was detected")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Detection confidence 0-1")
    evidence: list[str] = Field(..., description="Specific evidence supporting the detection")
    segment_ids: list[int] = Field(..., description="Which segments contain this PII")
    line_indices: list[int] = Field(..., description="Line numbers for reference")
    start_segment_id: int = Field(..., description="First segment ID where PII appears")
    end_segment_id: int = Field(..., description="Last segment ID where PII appears")
    timestamp_range: TimestampRange = Field(..., description="Time range of the PII section")
    total_digits_detected: int | None = Field(None, description="Total number of digits in the detected sequence")
    digit_groups: list[DigitGroup] | None = Field(None, description="Each digit group with Thai text and Arabic conversion")
    acknowledgment_segments: list[int] | None = Field(None, description="Agent acknowledgment segments between digit groups")

class RoutingDecision(BaseModel):
    has_credit_card_data: bool = Field(..., description="True if ANY credit card PII detected")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Overall confidence in routing decision")
    reasoning: str = Field(..., description="Detailed explanation of ALL detected evidence")

class RoutingPlan(BaseModel):
    route_to_payment_agent: bool = Field(..., description="True if credit card data found")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in routing plan")
    skip_other_agents: list[str] = Field(default_factory=list, description="List of agents to skip (PCI-DSS compliance)")

class Statistics(BaseModel):
    total_sections_detected: int = Field(..., description="Total PII sections found")
    sequential_spelling_sections: int = Field(..., description="Count of sequential spelling sections")
    full_mention_sections: int = Field(default=0, description="Count of full number mentions")
    confirmation_sections: int = Field(default=0, description="Count of agent confirmations")
    expiry_date_sections: int = Field(default=0, description="Count of expiry date discussions")
    total_segments_with_pii: int = Field(..., description="Unique segments containing PII")
    estimated_pii_items: int = Field(..., description="Estimated total PII items (for prioritization)")

class ChunkAnalysis(BaseModel):
    chunk_id: str = Field(..., description="Must match exactly the chunk_id from input JSON")
    routing_decision: RoutingDecision = Field(..., description="Overall routing decision for this chunk")
    credit_card_sections: list[CreditCardSection] = Field(..., description="All detected credit card PII sections")
    routing_plan: RoutingPlan = Field(..., description="Which agents should process this chunk")
    statistics: Statistics = Field(..., description="Summary statistics for this chunk")

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

class MaskingResult(BaseModel):
    """Single masking result from Agent_Payment"""
    type: Literal["card_number", "expiration_date", "cvv"] = Field(..., description="Type of PII masked")
    original_text: str = Field(..., description="Original text before masking")
    masked_text: str = Field(..., description="Text after masking")
    start_time: float = Field(..., description="Start timestamp in seconds")
    end_time: float = Field(..., description="End timestamp in seconds")
    segment_ids: List[int] = Field(..., description="Segment IDs where masking was applied")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Masking confidence 0-1")
    category: Literal["Success Mask", "Success Partial", "Success Overmask", "Fail Overmask", "Missing Mask", "Wrong Mask", "No Card"] = Field(..., description="Masking quality category")

class MaskingSummary(BaseModel):
    """Summary statistics for masking operations"""
    total_masked: int = Field(..., description="Total masking operations performed")
    success_mask: int = Field(..., description="Count of complete masking operations")
    success_partial: int = Field(..., description="Count of PCI DSS compliant partial masking")
    overmask_issues: int = Field(..., description="Count of overmasking problems")
    missing_mask: int = Field(..., description="Count of security failures")
    wrong_mask: int = Field(..., description="Count of false positive maskings")

class AgentPaymentOutput(BaseModel):
    """Output from Agent_Payment worker with split utterance handling"""
    chunk_id: str = Field(..., description="Chunk identifier")
    masking_results: List[MaskingResult] = Field(..., description="List of masking operations performed")
    summary: MaskingSummary = Field(..., description="Summary statistics for masking operations")

class PIIWorkerOutput(BaseModel):
    """Output from a single PII worker agent"""
    agent_name: AgentName = Field(..., description="Name of the agent that processed this")
    category: PIICategory = Field(..., description="PII category this agent specializes in")
    
    # Legacy field for backward compatibility
    detections: List[PIIDetection] = Field(
        default_factory=list,
        description="List of all PII instances detected"
    )
    
    # New field for Agent_Payment split utterance handling
    masking_results: Optional[AgentPaymentOutput] = Field(
        default=None,
        description="Masking results from Agent_Payment with split utterance handling"
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