from typing import Dict, Any, List, Optional
from src.config.logs_config import get_logger

logger = get_logger(__name__)


class TranscriptPostProcessor:
    """
    Production-grade transcript post-processor for ASR pipeline.

    Handles:
    1. Overlap-aware merge (removes duplicate words from chunk boundaries)
    2. Repetition collapse (removes decoder loops)

    Pipeline: words → overlap_merge → repetition_collapse → final_words
    """

    def __init__(
        self,
        overlap_tolerance: float = 0.05,
        max_repeat: int = 3,
        repetition_window_sec: float = 2.0,
    ):
        self.overlap_tolerance = overlap_tolerance
        self.max_repeat = max_repeat
        self.repetition_window_sec = repetition_window_sec

    def process_words(self, words: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Process words through full pipeline.

        Args:
            words: List of word dicts with 'word', 'start', 'end', 'speaker' keys

        Returns:
            Deduplicated and cleaned word list
        """
        if not words:
            return []

        logger.info(f"Processing {len(words)} words through post-processor")

        merged = self._merge_overlap_aware(words)
        logger.info(f"After overlap merge: {len(merged)} words")

        collapsed = self._collapse_repetition(merged)
        logger.info(f"After repetition collapse: {len(collapsed)} words")

        return collapsed

    def _merge_overlap_aware(self, words: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Stage 1: Overlap-aware merge for chunk boundaries.

        Removes duplicate words from overlapping audio chunks.
        Uses timestamp comparison to detect overlaps.

        Args:
            words: List of word dicts (already offset with global timestamps)

        Returns:
            Words with overlaps removed
        """
        if not words:
            return []

        words_sorted = sorted(words, key=lambda w: float(w.get("start", 0)))
        merged = [words_sorted[0]]

        for w in words_sorted[1:]:
            last_word = merged[-1]
            w_start = float(w.get("start", 0))
            last_end = float(last_word.get("end", 0))

            if w_start >= last_end - self.overlap_tolerance:
                merged.append(w)
            else:
                logger.debug(
                    f"Skipping overlapping word: '{w.get('word')}' "
                    f"(start={w_start:.3f}, last_end={last_end:.3f})"
                )

        return merged

    def _collapse_repetition(self, words: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Stage 2: Repetition collapse for decoder loops.

        Removes excessive repetition of the same word from decoder loops.
        Keeps up to max_repeat occurrences, collapses the rest.

        Args:
            words: List of word dicts

        Returns:
            Words with excessive repetitions collapsed
        """
        if not words:
            return []

        result = []
        count = 1
        prev_word: Optional[Dict[str, Any]] = None

        for w in words:
            if prev_word is not None:
                prev_word_text = prev_word.get("word", "").strip().lower()
                curr_word_text = w.get("word", "").strip().lower()

                same_speaker = prev_word.get("speaker") == w.get("speaker")
                same_word = prev_word_text == curr_word_text
                time_gap = float(w.get("start", 0)) - float(prev_word.get("end", 0))

                if same_word and same_speaker and time_gap < self.repetition_window_sec:
                    count += 1
                else:
                    count = 1
            else:
                count = 1

            if count <= self.max_repeat:
                result.append(w)
            else:
                logger.debug(
                    f"Collapsing repetition {count}: '{w.get('word')}' "
                    f"(max_repeat={self.max_repeat})"
                )

            prev_word = w

        return result

    def merge_channels(
        self, agent_words: List[Dict[str, Any]], caller_words: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Merge words from multiple channels (Agent/Caller) into single timeline.

        Args:
            agent_words: Words from left channel
            caller_words: Words from right channel

        Returns:
            Combined words sorted by timestamp
        """
        all_words = []

        for w in agent_words:
            w["speaker"] = "Agent"
            all_words.append(w)

        for w in caller_words:
            w["speaker"] = "Caller"
            all_words.append(w)

        all_words.sort(key=lambda w: float(w.get("start", 0)))

        return all_words

    def build_simple_text(self, words: List[Dict[str, Any]]) -> str:
        """
        Build simple text format from words.

        Format: [Speaker]: word1 word2 ...

        Args:
            words: List of word dicts with 'speaker' and 'word' keys

        Returns:
            Formatted transcript text
        """
        if not words:
            return ""

        lines = []
        current_speaker = None
        current_words = []

        for w in words:
            speaker = w.get("speaker", "Unknown")
            word = w.get("word", "")

            if speaker != current_speaker:
                if current_words and current_speaker:
                    lines.append(f"[{current_speaker}]: {' '.join(current_words)}")
                current_speaker = speaker
                current_words = []

            current_words.append(word)

        if current_words and current_speaker:
            lines.append(f"[{current_speaker}]: {' '.join(current_words)}")

        return "\n".join(lines)
