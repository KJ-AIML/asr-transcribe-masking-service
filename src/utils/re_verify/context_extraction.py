"""
Utility functions for extracting context data from transcript segments
This module provides functions to extract text context for Re-Verify workflow
with different context window sizes and analysis capabilities.
"""

from typing import Dict, List, Any, Tuple
from src.config.logs_config import get_logger

def extract_context_with_segments(
    transcript: Dict[str, Any], 
    start_time: float, 
    end_time: float
) -> Dict[str, Any]:
    """
    Extract context and segments within the specified time range
    
    Args:
        transcript: Original transcript with segments
        start_time: Start time of the context window
        end_time: End time of the context window
        
    Returns:
        Dictionary containing context text, segments, and metadata
    """
    # Filter segments within the time range
    context_segments = [
        seg for seg in transcript.get("segments", [])
        if seg["start"] < end_time and seg["end"] > start_time
    ]
    
    # Create context text with timestamps
    context_text = "\n".join([
        f"[{seg['start']:.2f} --> {seg['end']:.2f}] [{seg['channel']}]: {seg['text']}"
        for seg in context_segments
    ])
    
    # Create simple text without timestamps
    simple_text = "\n".join([
        f"[{seg['channel']}]: {seg['text']}"
        for seg in context_segments
    ])
    
    return {
        "text": context_text,
        "simple_text": simple_text,
        "segments": context_segments,
        "start_time": start_time,
        "end_time": end_time,
        "duration": end_time - start_time
    }

def prepare_re_verify_input(
    detection: Dict[str, Any], 
    original_transcript: Dict[str, Any],
    before_seconds: float = 30.0,
    after_seconds: float = 10.0
) -> Dict[str, Any]:
    """
    Prepare input for re-verify workflow with extended context for individual detection
    
    Args:
        detection: Single detection with timestamp information
        original_transcript: Original transcript with segments
        before_seconds: Seconds to include before the detection
        after_seconds: Seconds to include after the detection
        
    Returns:
        Dictionary containing all necessary data for re-verify workflow
    """
    # Get detection time range
    start_time = detection["detection"]["start_time"]
    end_time = detection["detection"]["end_time"]
    
    # Extend context window
    context_start = max(0, start_time - before_seconds)
    context_end = end_time + after_seconds
    
    # Handle different transcript structures
    # Try to get segments from different possible locations
    segments = []
    
    # Debug: Log transcript structure
    logger = get_logger(__name__)
    logger.debug(f"Transcript keys: {list(original_transcript.keys())}")
    
    # Option 1: Direct segments in transcript
    if "segments" in original_transcript:
        segments = original_transcript["segments"]
        logger.debug(f"Found {len(segments)} segments directly in transcript")
    
    # Option 2: Nested in transcript.transcript.segments
    elif "transcript" in original_transcript and isinstance(original_transcript["transcript"], dict):
        if "segments" in original_transcript["transcript"]:
            segments = original_transcript["transcript"]["segments"]
            logger.debug(f"Found {len(segments)} segments in transcript.transcript")
    
    # Fallback: If no segments found, try to extract from text if available
    if not segments:
        logger.warning(f"No segments found in transcript. Available keys: {list(original_transcript.keys())}")
        
        # Try to use simple_text if available
        if "simple_text" in original_transcript:
            simple_text = original_transcript["simple_text"]
            # Create a dummy segment with the full text
            segments = [{
                "start": 0,
                "end": context_end - context_start,
                "text": simple_text,
                "channel": "unknown"
            }]
            logger.debug("Created fallback segment from simple_text")
        
        # Or use text if available
        elif "text" in original_transcript:
            text = original_transcript["text"]
            # Create a dummy segment with the full text
            segments = [{
                "start": 0,
                "end": context_end - context_start,
                "text": text,
                "channel": "unknown"
            }]
            logger.debug("Created fallback segment from text")
    
    # Extract segments within the context window
    context_segments = [
        seg for seg in segments
        if seg["start"] < context_end and seg["end"] > context_start
    ]
    
    logger.debug(f"Extracted {len(context_segments)} segments within context window [{context_start:.2f} - {context_end:.2f}]")
    
    # Create context text
    context_text = "\n".join([
        f"[{seg['start']:.2f} --> {seg['end']:.2f}] [{seg['channel']}]: {seg['text']}"
        for seg in context_segments
    ])
    
    return {
        "context_text": context_text,
        "detection": detection["detection"],
        "segments": context_segments,
        "context_window": {
            "start": context_start,
            "end": context_end,
            "original_start": start_time,
            "original_end": end_time,
            "before_seconds": before_seconds,
            "after_seconds": after_seconds
        }
    }

def analyze_context_for_false_positive(
    context_text: str,
    detection_type: str = "card_number"
) -> Dict[str, Any]:
    """
    Analyze context to determine if detection is likely a false positive
    
    Args:
        context_text: Text context around the detection
        detection_type: Type of detection (card_number, expiration_date, cvv)
        
    Returns:
        Dictionary containing analysis results
    """
    text_lower = context_text.lower()
    
    # Keywords for credit card context
    credit_keywords = [
        "บัตรเครดิต", "จ่าย", "ชำระ", "visa", "mastercard", "เครดิต",
        "payment", "credit card", "card number", "expir", "cvv"
    ]
    
    # Keywords for ID card context (false positives)
    id_keywords = [
        "บัตรประชาชน", "ประชาชน", "สิบสามหลัก", "id card",
        "บัตร", "id", "identification", "citizen"
    ]
    
    # Keywords for insurance context (false positives)
    insurance_keywords = [
        "กรมธรรม์", "ประกัน", "police", "insurance", "policy",
        "เลขกรมธรรม์", "กรมธรรม์ประกัน"
    ]
    
    # Count keyword occurrences
    credit_score = sum(1 for kw in credit_keywords if kw in text_lower)
    id_score = sum(1 for kw in id_keywords if kw in text_lower)
    insurance_score = sum(1 for kw in insurance_keywords if kw in text_lower)
    
    # Determine likely category
    total_score = credit_score + id_score + insurance_score
    
    if total_score == 0:
        # No keywords found, default to credit_card with low confidence
        likely_category = "credit_card"
        confidence = 0.1
    elif credit_score > id_score and credit_score > insurance_score:
        likely_category = "credit_card"
        confidence = min(credit_score / total_score, 1.0)
    elif id_score > insurance_score:
        likely_category = "id_card"
        confidence = min(id_score / total_score, 1.0)
    else:
        likely_category = "insurance"
        confidence = min(insurance_score / total_score, 1.0)
    
    return {
        "likely_category": likely_category,
        "confidence": confidence,
        "keyword_scores": {
            "credit": credit_score,
            "id": id_score,
            "insurance": insurance_score
        },
        "recommendation": "PASS" if likely_category == "credit_card" else "FAIL"
    }

def extract_context_for_missing_detection(
    transcript: Dict[str, Any],
    start_time: float,
    end_time: float,
    search_window: float = 120.0
) -> Dict[str, Any]:
    """
    Extract extended context for missing detection analysis
    
    Args:
        transcript: Original transcript with segments
        start_time: Start time of the area to search
        end_time: End time of the area to search
        search_window: Additional time to extend the search area
        
    Returns:
        Dictionary containing extended context for missing detection analysis
    """
    # Extend search window
    context_start = max(0, start_time - search_window)
    context_end = end_time + search_window
    
    # Extract segments within the extended context window
    context_segments = [
        seg for seg in transcript.get("segments", [])
        if seg["start"] < context_end and seg["end"] > context_start
    ]
    
    # Create context text
    context_text = "\n".join([
        f"[{seg['start']:.2f} --> {seg['end']:.2f}] [{seg['channel']}]: {seg['text']}"
        for seg in context_segments
    ])
    
    return {
        "context_text": context_text,
        "segments": context_segments,
        "search_window": {
            "start": context_start,
            "end": context_end,
            "original_start": start_time,
            "original_end": end_time,
            "extended_seconds": search_window
        }
    }