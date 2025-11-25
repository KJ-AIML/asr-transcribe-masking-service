"""
Utility functions for extracting timestamp information from detections
This module provides functions to extract, group, and analyze detections with timestamps
for the Re-Verify workflow implementation.
"""

from typing import Dict, List, Any, Tuple
import logging

logger = logging.getLogger(__name__)

def extract_detections_with_timestamps(processed_chunks: List[Dict[str, Any]], before_seconds: float = 60.0, after_seconds: float = 20.0) -> List[Dict[str, Any]]:
    """
    Extract all detections with timestamps from processed chunks (individual detections)
    
    Args:
        processed_chunks: List of processed chunks from the main workflow
        before_seconds: Seconds to include before the detection for context
        after_seconds: Seconds to include after the detection for context
        
    Returns:
        List of individual detections with timestamp information and context windows
    """
    detections = []
    logger.info(f"Extracting detections from {len(processed_chunks)} processed chunks")
    
    for chunk in processed_chunks:
        logger.debug(f"Processing chunk {chunk.get('chunk_id', 'unknown')}, has_credit_card: {chunk.get('has_credit_card', False)}")
        
        # Extract from masked_credit_cards (existing logic)
        if chunk.get("has_credit_card") and "masked_credit_cards" in chunk:
            logger.debug(f"Found {len(chunk['masked_credit_cards'])} masked credit cards in chunk {chunk.get('chunk_id', 'unknown')}")
            for detection in chunk["masked_credit_cards"]:
                detection_data = {
                    "chunk_id": chunk["chunk_id"],
                    "detection": detection,
                    "context_window": {
                        "start_time": max(0, detection["start_time"] - before_seconds),
                        "end_time": detection["end_time"] + after_seconds,
                        "original_start": detection["start_time"],
                        "original_end": detection["end_time"],
                        "before_seconds": before_seconds,
                        "after_seconds": after_seconds
                    }
                }
                detections.append(detection_data)
                logger.debug(f"Added masked credit card detection: {detection.get('type', 'unknown')} at {detection.get('start_time', 0)}")
        
        # NEW: Extract from Payment Agent results
        if "workflow_result" in chunk:
            logger.debug(f"Checking workflow_result in chunk {chunk.get('chunk_id', 'unknown')}")
            if "completed_results" in chunk["workflow_result"]:
                logger.debug(f"Found {len(chunk['workflow_result']['completed_results'])} completed results")
                for result in chunk["workflow_result"]["completed_results"]:
                    if result.get("agent") == "Agent_Payment":
                        logger.debug("Found Agent_Payment result")
                        payment_result = result.get("result", {})
                        if "detections" in payment_result and payment_result["detections"]:
                            logger.debug(f"Found {len(payment_result['detections'])} Payment Agent detections")
                            for detection in payment_result["detections"]:
                                if detection.get("pii_type") == "PAYMENT":
                                    logger.debug(f"Processing PAYMENT detection: {detection.get('raw_value', 'N/A')}")
                                    # Convert Payment Agent detection to expected format
                                    detection_data = {
                                        "chunk_id": chunk["chunk_id"],
                                        "detection": {
                                            "id": detection.get("id", f"payment_{len(detections)}"),
                                            "type": "card_number",  # Map PAYMENT to card_number for Re-Verify
                                            "original_text": detection.get("raw_value", ""),
                                            "start_time": detection.get("start_time", 0),
                                            "end_time": detection.get("end_time", 0),
                                            "confidence": detection.get("confidence", 0),
                                            "source": "payment_agent"  # Track source for debugging
                                        },
                                        "context_window": {
                                            "start_time": max(0, detection.get("start_time", 0) - before_seconds),
                                            "end_time": detection.get("end_time", 0) + after_seconds,
                                            "original_start": detection.get("start_time", 0),
                                            "original_end": detection.get("end_time", 0),
                                            "before_seconds": before_seconds,
                                            "after_seconds": after_seconds
                                        }
                                    }
                                    detections.append(detection_data)
                                    logger.debug(f"Added Payment Agent detection: {detection.get('raw_value', 'N/A')} at {detection.get('start_time', 0)}")
                                else:
                                    logger.debug(f"Skipping non-PAYMENT detection: {detection.get('pii_type', 'unknown')}")
                        else:
                            logger.debug("No detections found in Payment Agent result")
                    else:
                        logger.debug(f"Skipping non-Payment Agent result: {result.get('agent', 'unknown')}")
            else:
                logger.debug("No completed_results found in workflow_result")
        else:
            logger.debug("No workflow_result found in chunk")
    
    logger.info(f"Extracted {len(detections)} total detections from {len(processed_chunks)} chunks")
    return detections

def calculate_context_windows(detections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Calculate context windows for each individual detection
    
    Args:
        detections: List of detections with basic timestamp information
        
    Returns:
        List of detections with calculated context window details
    """
    for detection in detections:
        context = detection["context_window"]
        detection["context_window"]["duration"] = context["end_time"] - context["start_time"]
        detection["context_window"]["actual_before_seconds"] = context["original_start"] - context["start_time"]
        detection["context_window"]["actual_after_seconds"] = context["end_time"] - context["original_end"]
    
    return detections

def group_detections_by_proximity(detections: List[Dict[str, Any]], proximity_threshold: float = 30.0) -> List[List[Dict[str, Any]]]:
    """
    Group detections that are close to each other (within proximity_threshold seconds)
    This can help optimize Re-Verify processing by batching nearby detections
    
    Args:
        detections: List of detections with timestamp information
        proximity_threshold: Maximum time gap between detections to be in the same group
        
    Returns:
        List of detection groups
    """
    if not detections:
        return []
    
    # Sort by start time
    sorted_detections = sorted(detections, key=lambda x: x["detection"]["start_time"])
    
    groups = []
    current_group = [sorted_detections[0]]
    
    for detection in sorted_detections[1:]:
        last_detection = current_group[-1]
        
        # Check if this detection is close to the last one in the current group
        if detection["detection"]["start_time"] - last_detection["detection"]["end_time"] <= proximity_threshold:
            current_group.append(detection)
        else:
            groups.append(current_group)
            current_group = [detection]
    
    groups.append(current_group)
    return groups

def analyze_detection_patterns(detections: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze patterns in detections to understand the data better
    
    Args:
        detections: List of detections with timestamp information
        
    Returns:
        Dictionary containing analysis results
    """
    if not detections:
        return {}
    
    # Detection types
    types = {}
    for detection in detections:
        det_type = detection["detection"]["type"]
        types[det_type] = types.get(det_type, 0) + 1
    
    # Time distribution
    start_times = [d["detection"]["start_time"] for d in detections]
    time_range = {
        "earliest": min(start_times),
        "latest": max(start_times),
        "span": max(start_times) - min(start_times)
    }
    
    # Confidence scores
    confidences = [d["detection"]["confidence"] for d in detections]
    confidence_stats = {
        "min": min(confidences),
        "max": max(confidences),
        "avg": sum(confidences) / len(confidences)
    }
    
    # Context window sizes
    context_durations = [d["context_window"]["duration"] for d in detections]
    context_stats = {
        "min": min(context_durations),
        "max": max(context_durations),
        "avg": sum(context_durations) / len(context_durations)
    }
    
    return {
        "total_detections": len(detections),
        "detection_types": types,
        "time_distribution": time_range,
        "confidence_stats": confidence_stats,
        "context_window_stats": context_stats
    }

def get_group_time_range(detection_group: List[Dict[str, Any]]) -> Tuple[float, float]:
    """
    Get the time range for a group of detections
    
    Args:
        detection_group: List of detections in the same group
        
    Returns:
        Tuple of (start_time, end_time) for the entire group
    """
    if not detection_group:
        return (0.0, 0.0)
    
    start_times = [d["detection"]["start_time"] for d in detection_group]
    end_times = [d["detection"]["end_time"] for d in detection_group]
    
    return (min(start_times), max(end_times))