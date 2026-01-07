from typing import Dict, Any, List
import re
from src.config.logs_config import get_logger

logger = get_logger(__name__)


def chunk_original_transcript(
    original_transcript: str,
    chunk_duration: float = 100.0,
    overlap_duration: float = 10.0,
) -> Dict[str, Any]:
    """
    Chunk an original transcript string into overlapping time windows.
    This function is specifically designed for QA auditor to process original transcripts
    without requiring segment information.

    Args:
        original_transcript: The original transcript string with timestamp format [start --> end] [channel]: text
        chunk_duration: Duration of each chunk in seconds (default: 100.0)
        overlap_duration: Overlap between consecutive chunks in seconds (default: 10.0)

    Returns:
        A dictionary containing chunked data and processing metadata

    Raises:
        ValueError: If chunk_duration <= overlap_duration
    """
    # Validate parameters
    if chunk_duration <= overlap_duration:
        raise ValueError("chunk_duration must be greater than overlap_duration")

    # Parse the original transcript to extract segments with timestamps
    segments = _parse_original_transcript(original_transcript)

    if not segments:
        logger.warning("No segments found in original transcript")
        return {
            "chunks": [],
            "chunking_config": {
                "chunk_duration": chunk_duration,
                "overlap_duration": overlap_duration,
                "step_size": chunk_duration - overlap_duration,
                "total_chunks": 0,
                "total_duration": 0,
            },
        }

    # Calculate total duration
    total_duration = max(seg["end"] for seg in segments)
    logger.info(f"Total transcript duration: {total_duration}s")

    # Calculate chunk parameters
    step_size = chunk_duration - overlap_duration
    total_chunks = max(1, int((total_duration - overlap_duration) / step_size) + 1)

    logger.info(
        f"Creating {total_chunks} chunks with {chunk_duration}s duration and {overlap_duration}s overlap"
    )

    # Create chunks
    chunks = []
    for i in range(total_chunks):
        start_time = i * step_size
        end_time = min(start_time + chunk_duration, total_duration)

        # Get segments for this chunk
        chunk_segments = [
            seg
            for seg in segments
            if seg["start"] < end_time and seg["end"] > start_time
        ]

        # Create chunk text
        chunk_text = "\n".join(
            [
                f"[{seg['start']:.2f} --> {seg['end']:.2f}] [{seg['channel']}]: {seg['text']}"
                for seg in chunk_segments
            ]
        )

        # Create chunk metadata
        metadata = {
            "chunk_index": i,
            "start_time": start_time,
            "end_time": end_time,
            "duration": end_time - start_time,
            "segment_count": len(chunk_segments),
        }

        # Create chunk object
        chunk = {"segments": chunk_segments, "text": chunk_text, "metadata": metadata}

        chunks.append(chunk)
        logger.debug(
            f"Created chunk {i}: {start_time:.2f}s to {end_time:.2f}s with {len(chunk_segments)} segments"
        )

    # Return chunked result
    chunking_config = {
        "chunk_duration": chunk_duration,
        "overlap_duration": overlap_duration,
        "step_size": step_size,
        "total_chunks": total_chunks,
        "total_duration": total_duration,
    }

    logger.info(f"Successfully created {total_chunks} chunks from original transcript")

    return {"chunks": chunks, "chunking_config": chunking_config}


def _parse_original_transcript(original_transcript: str) -> List[Dict[str, Any]]:
    """
    Parse original transcript string to extract segments with timestamps.

    Args:
        original_transcript: The original transcript string with timestamp format [start --> end] [channel]: text

    Returns:
        List of segment dictionaries with start, end, channel, and text
    """
    segments = []

    # Log the original transcript for debugging
    logger.info(f"Original transcript type: {type(original_transcript)}")
    logger.info(f"Original transcript length: {len(original_transcript)}")
    logger.info(f"Original transcript is empty: {not original_transcript}")
    logger.info(
        f"Original transcript (first 500 chars): {original_transcript[:500]}..."
    )

    # Pattern to match transcript lines: [start --> end] [channel]: text
    pattern = r"\[(\d+\.?\d*)\s*-->\s*(\d+\.?\d*)\]\s*\[([^\]]+)\]:\s*(.+)"

    lines = original_transcript.split("\n")
    logger.debug(f"Split transcript into {len(lines)} lines")

    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue

        logger.debug(f"Processing line {i}: {line}")

        match = re.match(pattern, line)
        if match:
            start_time = float(match.group(1))
            end_time = float(match.group(2))
            channel = match.group(3)
            text = match.group(4)

            segments.append(
                {"start": start_time, "end": end_time, "channel": channel, "text": text}
            )
            logger.debug(
                f"Successfully parsed segment: start={start_time}, end={end_time}, channel={channel}"
            )
        else:
            logger.debug(f"Failed to match pattern for line: {line}")

    logger.info(f"Parsed {len(segments)} segments from original transcript")
    return segments
