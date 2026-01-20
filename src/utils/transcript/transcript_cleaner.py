"""
Transcript Cleaner Utility

Post-processing filters to improve transcription quality:
- Filter repetitive patterns (ringtones, hold music)
- Deduplicate consecutive repeated words
- Merge very short segments
"""

from typing import List, Dict, Any
from collections import Counter
from src.config.logs_config import get_logger

logger = get_logger(__name__)


def is_repetitive_segment(words: List[Dict[str, Any]], threshold: float = 0.5) -> bool:
    """
    Check if a segment has repetitive patterns (likely ringtone/hold music).

    Args:
        words: List of word dicts
        threshold: If ratio of most common word > threshold, it's repetitive

    Returns:
        True if segment appears to be repetitive pattern
    """
    if not words or len(words) < 3:
        return False

    # Extract word text
    word_texts = [w.get("word", "").strip() for w in words if w.get("word", "").strip()]

    if len(word_texts) < 3:
        return False

    # Count word frequencies
    word_counts = Counter(word_texts)
    most_common_word, most_common_count = word_counts.most_common(1)[0]

    # Calculate ratio: if one word appears > threshold of all words
    ratio = most_common_count / len(word_texts)

    # Also check for very short repeated words (like "ติ้ง", "ตี")
    is_short_word = len(most_common_word) <= 6  # Thai chars are 3 bytes each

    if ratio > threshold and is_short_word:
        logger.debug(
            f"Detected repetitive pattern: '{most_common_word}' appears {ratio:.1%}"
        )
        return True

    # Check for alternating patterns like "โทร ติ้ง โทร ติ้ง"
    if len(word_counts) <= 3 and len(word_texts) > 6:
        # Only 2-3 unique words but many total words
        total_coverage = sum(c for _, c in word_counts.most_common(3)) / len(word_texts)
        if total_coverage > 0.9:
            logger.debug(
                f"Detected alternating pattern with {len(word_counts)} unique words"
            )
            return True

    return False


def filter_repetitive_segments(segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Filter out segments that appear to be ringtones or repetitive patterns.

    Args:
        segments: List of segment dicts with 'words' key

    Returns:
        Filtered list of segments
    """
    filtered = []
    removed_count = 0

    for segment in segments:
        words = segment.get("words", [])

        if is_repetitive_segment(words):
            removed_count += 1
            logger.info(
                f"Filtered repetitive segment: {segment.get('text', '')[:50]}..."
            )
            continue

        filtered.append(segment)

    if removed_count > 0:
        logger.info(
            f"Removed {removed_count} repetitive segments (ringtone/hold music)"
        )

    return filtered


def deduplicate_consecutive_words(
    words: List[Dict[str, Any]], max_repeats: int = 2
) -> List[Dict[str, Any]]:
    """
    Remove consecutive duplicate words, keeping at most max_repeats.

    Args:
        words: List of word dicts
        max_repeats: Maximum allowed consecutive repeats (default 2)

    Returns:
        Deduplicated word list
    """
    if not words:
        return words

    result = []
    prev_word = None
    repeat_count = 0

    for word_dict in words:
        word_text = word_dict.get("word", "").strip()

        if word_text == prev_word:
            repeat_count += 1
            if repeat_count < max_repeats:
                result.append(word_dict)
        else:
            repeat_count = 0
            prev_word = word_text
            result.append(word_dict)

    removed = len(words) - len(result)
    if removed > 0:
        logger.debug(f"Deduplicated {removed} consecutive repeated words")

    return result


def merge_short_segments(
    segments: List[Dict[str, Any]], min_words: int = 2, max_gap: float = 1.0
) -> List[Dict[str, Any]]:
    """
    Merge very short segments with nearby ones.

    Args:
        segments: List of segment dicts
        min_words: Minimum words for a standalone segment
        max_gap: Maximum time gap (seconds) to merge segments

    Returns:
        Merged segment list
    """
    if not segments or len(segments) < 2:
        return segments

    merged = []
    current = None

    for segment in segments:
        words = segment.get("words", [])

        if current is None:
            current = segment.copy()
            current["words"] = list(words)
            continue

        # Check if should merge with current
        current_words = current.get("words", [])
        gap = segment.get("start", 0) - current.get("end", 0)
        same_speaker = current.get("speaker") == segment.get("speaker")

        # Merge if: short segment + small gap + same speaker
        should_merge = len(current_words) < min_words and gap < max_gap and same_speaker

        if should_merge:
            # Merge into current
            current["words"].extend(words)
            current["end"] = segment.get("end", current["end"])
            current["text"] = " ".join(w.get("word", "") for w in current["words"])
        else:
            # Save current and start new
            merged.append(current)
            current = segment.copy()
            current["words"] = list(words)

    # Don't forget the last segment
    if current:
        merged.append(current)

    if len(merged) < len(segments):
        logger.debug(f"Merged segments: {len(segments)} → {len(merged)}")

    return merged


def clean_transcription(
    segments: List[Dict[str, Any]],
    filter_repetitive: bool = True,
    deduplicate: bool = True,
    merge_short: bool = True,
) -> Dict[str, Any]:
    """
    Main entry point for transcription cleaning.

    Args:
        segments: List of segment dicts
        filter_repetitive: Remove repetitive patterns (ringtones)
        deduplicate: Remove consecutive word duplicates
        merge_short: Merge very short segments

    Returns:
        Dict with cleaned segments and all words
    """
    cleaned_segments = segments

    # Step 1: Filter repetitive patterns (ringtones)
    if filter_repetitive:
        cleaned_segments = filter_repetitive_segments(cleaned_segments)

    # Step 2: Deduplicate consecutive words in each segment
    if deduplicate:
        for segment in cleaned_segments:
            words = segment.get("words", [])
            segment["words"] = deduplicate_consecutive_words(words)
            # Rebuild text from words
            segment["text"] = "".join(w.get("word", "") for w in segment["words"])

    # Step 3: Merge short segments
    if merge_short:
        cleaned_segments = merge_short_segments(cleaned_segments)

    # Extract all words
    all_words = []
    for segment in cleaned_segments:
        all_words.extend(segment.get("words", []))

    # Build full text
    full_text = " ".join(w.get("word", "") for w in all_words)

    logger.info(
        f"Cleaned transcription: {len(segments)} → {len(cleaned_segments)} segments"
    )

    return {"segments": cleaned_segments, "words": all_words, "text": full_text}
