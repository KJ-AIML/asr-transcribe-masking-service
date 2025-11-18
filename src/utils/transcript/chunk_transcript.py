import json
from typing import Dict, List, Any, Optional

from src.config.logs_config import get_logger

logger = get_logger(__name__)

def chunk_transcript(
    json_data: Dict[str, Any],
    chunk_duration: float = 45.0,
    overlap_duration: float = 5.0,
    include_original_text: bool = False
) -> Dict[str, Any]:
    """
    Chunk a transcript JSON into overlapping time windows.

    Args:
        json_data: The input transcript JSON object containing segments, words, and metadata
        chunk_duration: Duration of each chunk in seconds (default: 45.0)
        overlap_duration: Overlap between consecutive chunks in seconds (default: 5.0)
        include_original_text: Whether to include original full text fields in output (default: False)

    Returns:
        A dictionary containing chunked data and processing metadata

    Raises:
        ValueError: If chunk_duration <= overlap_duration or if required fields are missing
    """
    # Validate parameters
    if chunk_duration <= overlap_duration:
        raise ValueError("chunk_duration must be greater than overlap_duration")

    # Validate input structure
    required_fields = ["segments", "words", "metadata"]
    for field in required_fields:
        if field not in json_data:
            raise ValueError(f"Input JSON must contain '{field}' field")

    # Determine total duration (use maximum of metadata and actual segment ends)
    total_duration = json_data["metadata"].get("duration", 0.0)
    segment_count = len(json_data["segments"])
    logger.info(f"Chunking transcript with {segment_count} segments")
    
    if json_data["segments"]:
        max_segment_end = max(seg["end"] for seg in json_data["segments"])
        total_duration = max(total_duration, max_segment_end)
        first_seg = json_data["segments"][0]
        last_seg = json_data["segments"][-1]
        logger.info(f"Segment time range: {first_seg['start']}s to {last_seg['end']}s")
        logger.info(f"Calculated total duration: {total_duration}s")

    if total_duration <= 0:
        raise ValueError("Could not determine valid total duration")

    # Initialize chunking parameters
    chunks = []
    step_size = chunk_duration - overlap_duration
    chunk_start = 0.0
    chunk_index = 0
    
    logger.info(f"Creating chunks with duration={chunk_duration}s, overlap={overlap_duration}s, step={step_size}s")

    # Process chunks
    while chunk_start < total_duration:
        chunk_end = min(chunk_start + chunk_duration, total_duration)
        
        # Find segments that overlap with this chunk's time window
        chunk_segments = [
            segment for segment in json_data["segments"]
            if segment["start"] < chunk_end and segment["end"] > chunk_start
        ]
        
        # Find words that overlap with this chunk's time window
        chunk_words = [
            word for word in json_data["words"]
            if word["start"] < chunk_end and word["end"] > chunk_start
        ]
        
        # CRITICAL FIX: Skip creating chunks with no segments
        if not chunk_segments:
            logger.warning(f"Skipping chunk {chunk_index}: no segments found in time window {chunk_start:.2f}s - {chunk_end:.2f}s")
            chunk_start += step_size
            chunk_index += 1
            continue
        
        # Build text representations from segments
        chunk_text = ""
        chunk_simple_text = ""
        if chunk_segments:
            chunk_text = "\n".join([
                f"[{seg['start']:.2f} --> {seg['end']:.2f}] [{seg['channel']}]: {seg['text']}"
                for seg in chunk_segments
            ])
            chunk_simple_text = "\n".join([
                f"[{seg['channel']}]: {seg['text']}"
                for seg in chunk_segments
            ])

        # Create chunk metadata
        chunk_metadata = {
            "chunk_index": chunk_index,
            "chunk_start": round(chunk_start, 2),
            "chunk_end": round(chunk_end, 2),
            "duration": round(chunk_end - chunk_start, 2),
            "segment_count": len(chunk_segments),
            "word_count": len(chunk_words),
            "is_last_chunk": chunk_end >= total_duration - 0.01
        }

        # Build chunk object
        chunk = {
            "text": chunk_text,
            "simple_text": chunk_simple_text,
            "segments": chunk_segments,
            "words": chunk_words,
            "metadata": chunk_metadata
        }

        chunks.append(chunk)
        logger.info(f"Created chunk {chunk_index}: {chunk_start:.2f}s to {chunk_end:.2f}s with {len(chunk_segments)} segments")

        # If this was the last chunk, exit loop
        if chunk_end >= total_duration:
            break

        # Move to next chunk position
        chunk_start += step_size
        chunk_index += 1

    logger.info(f"Created {len(chunks)} chunks total")

    # Prepare final result
    result = {
        "chunks": chunks,
        "chunking_config": {
            "chunk_duration": chunk_duration,
            "overlap_duration": overlap_duration,
            "step_size": step_size,
            "total_chunks": len(chunks),
            "total_duration": round(total_duration, 2)
        },
        "original_metadata": json_data["metadata"]
    }

    # Optionally include original text fields
    if include_original_text:
        result["original_text"] = json_data.get("text", "")
        result["original_simple_text"] = json_data.get("simple_text", "")

    return result


def log_chunk_summary(chunked_result: Dict[str, Any]) -> None:
    """
    Log a formatted summary of the chunked transcript.

    Args:
        chunked_result: The result from chunk_transcript function
    """
    config = chunked_result["chunking_config"]
    logger.info(f"Chunking Summary:")
    logger.info(f"  Total Duration: {config['total_duration']}s")
    logger.info(f"  Chunk Duration: {config['chunk_duration']}s")
    logger.info(f"  Overlap Duration: {config['overlap_duration']}s")
    logger.info(f"  Step Size: {config['step_size']}s")
    logger.info(f"  Total Chunks: {config['total_chunks']}")
    logger.info("\nChunk Details:")

    for chunk in chunked_result["chunks"]:
        meta = chunk["metadata"]
        logger.info(f"  Chunk {meta['chunk_index']}: "
              f"{meta['chunk_start']:.2f}s - {meta['chunk_end']:.2f}s "
              f"({meta['duration']:.2f}s, {meta['segment_count']} segments, "
              f"{meta['word_count']} words)" +
              (" [LAST]" if meta['is_last_chunk'] else ""))