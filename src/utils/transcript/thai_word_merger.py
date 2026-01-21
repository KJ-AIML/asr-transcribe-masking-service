"""
Thai Word Merger Utility

Merges Whisper tokens (characters/subwords) into proper Thai words using PyThaiNLP.
This is needed because whisper-timestamped returns token-level timestamps,
not word-level timestamps for Thai language.
"""

from typing import List, Dict, Any
from src.config.logs_config import get_logger

logger = get_logger(__name__)


def merge_tokens_to_thai_words(tokens: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Merge Whisper tokens into proper Thai words with timestamps.

    Args:
        tokens: List of token dicts with keys: word, start, end, probability

    Returns:
        List of word dicts with merged Thai words and combined timestamps
    """
    if not tokens:
        return []

    try:
        from pythainlp import word_tokenize
    except ImportError:
        logger.warning("PyThaiNLP not installed, returning tokens as-is")
        return tokens

    # Step 1: Concatenate all token text
    # Filter out empty tokens and whitespace-only tokens
    filtered_tokens = [t for t in tokens if t.get("word", "").strip()]

    if not filtered_tokens:
        return []

    # Build full text from tokens (remove spaces between Thai characters)
    full_text = ""
    token_boundaries = []  # Track where each token starts/ends in full_text

    for token in filtered_tokens:
        word = token.get("word", "")
        # Skip whitespace tokens
        if not word.strip():
            continue
        start_pos = len(full_text)
        full_text += word
        end_pos = len(full_text)
        token_boundaries.append(
            {"start_pos": start_pos, "end_pos": end_pos, "token": token}
        )

    if not full_text.strip():
        return []

    # Step 2: Use PyThaiNLP to segment into proper Thai words
    try:
        segmented_words = word_tokenize(
            full_text, engine="newmm", keep_whitespace=False
        )
    except Exception as e:
        logger.warning(
            f"PyThaiNLP word_tokenize failed: {e}, returning concatenated result"
        )
        # Fallback: return single word with combined timestamps
        if filtered_tokens:
            return [
                {
                    "word": full_text,
                    "start": filtered_tokens[0].get("start", 0.0),
                    "end": filtered_tokens[-1].get("end", 0.0),
                    "probability": sum(t.get("probability", 0) for t in filtered_tokens)
                    / len(filtered_tokens),
                }
            ]
        return []

    # Step 3: Map segmented words back to token timestamps
    merged_words = []
    current_pos = 0

    for seg_word in segmented_words:
        if not seg_word.strip():
            continue

        word_start_pos = current_pos
        word_end_pos = current_pos + len(seg_word)

        # Find tokens that overlap with this word's position
        matching_tokens = []
        for tb in token_boundaries:
            # Check if token overlaps with word position
            if tb["end_pos"] > word_start_pos and tb["start_pos"] < word_end_pos:
                matching_tokens.append(tb["token"])

        if matching_tokens:
            # Use first token's start time and last token's end time
            start_time = matching_tokens[0].get("start", 0.0)
            end_time = matching_tokens[-1].get("end", 0.0)
            avg_prob = sum(t.get("probability", 0) for t in matching_tokens) / len(
                matching_tokens
            )

            merged_words.append(
                {
                    "word": seg_word,
                    "start": start_time,
                    "end": end_time,
                    "probability": round(avg_prob, 3),
                }
            )

        current_pos = word_end_pos

    logger.debug(
        f"Merged {len(filtered_tokens)} tokens into {len(merged_words)} Thai words"
    )
    return merged_words


def merge_segment_words(segment: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge words within a segment to proper Thai words.

    Args:
        segment: Segment dict with 'words' key

    Returns:
        Segment with merged Thai words
    """
    words = segment.get("words", [])
    if not words:
        return segment

    merged_words = merge_tokens_to_thai_words(words)

    # Build proper text from merged words
    merged_text = "".join(w.get("word", "") for w in merged_words)

    return {**segment, "words": merged_words, "text": merged_text}
