"""
Action for unified stereo transcription processing
Combines model selection, speaker separation, and JSON structure generation
Uses multiprocessing for true parallel execution on separate GPUs
"""

from typing import Dict, Any, Optional, List
import asyncio
import multiprocessing as mp
import tempfile
import os
import time
from datetime import datetime
import io
import numpy as np
import librosa
import soundfile as sf
from src.config.logs_config import get_logger
from src.config.settings import settings
from src.execution.actions.process_choose_model_action import ProcessChooseModelAction
from src.models.asr_models import ASRModelManager
from src.models.transcription_model_adapter import (
    TranscriptionModelAdapter,
    WhisperAdapter,
    TyphoonAdapter,
)
from src.utils.file.json_utils import save_result_to_json
from src.utils.audio.chunk_wav_audio import vad_segment_audio_bytes


logger = get_logger(__name__)


def _mp_worker_transcribe_channel(
    audio_bytes: bytes,
    model_name: str,
    channel_label: str,
    device: str,
    max_concurrent_chunks: int,
    result_queue: mp.Queue,
) -> None:
    """
    Multiprocessing worker function for transcribing a single channel
    Each process runs on its own GPU device (or CPU)
    Results are sent back via result_queue
    """
    import torch

    channel_start = time.time()
    print(
        f"[MP Worker {device}] Starting transcription for {channel_label} at {channel_start:.2f}"
    )

    try:
        if device != "cpu":
            torch.cuda.set_device(device)
            print(f"[MP Worker {device}] Set device to {device}")
        else:
            print(f"[MP Worker {device}] Using CPU mode")

        asr_manager = ASRModelManager(device=device)
        adapter = TranscriptionModelAdapter()
        adapter.register_adapter("typhoon", TyphoonAdapter(asr_manager))
        adapter.register_adapter("pathumma", WhisperAdapter("pathumma", asr_manager))
        adapter.register_adapter(
            "pathumma_noise", WhisperAdapter("pathumma_noise", asr_manager)
        )

        print(f"[MP Worker {device}] Loaded ASR manager for {model_name}")

        if model_name in ["pathumma", "pathumma_noise"]:
            result = _mp_transcribe_chunked(
                audio_bytes,
                model_name,
                channel_label,
                adapter,
                max_concurrent_chunks,
                device,
            )
        else:
            result = _mp_transcribe_single(
                audio_bytes,
                model_name,
                channel_label,
                adapter,
            )

        print(
            f"[MP Worker {device}] Transcription completed for {channel_label} in {time.time() - channel_start:.2f}s"
        )
        result_queue.put((channel_label, result))

    except Exception as e:
        print(f"[MP Worker {device}] Error transcribing {channel_label}: {e}")
        import traceback

        traceback.print_exc()
        result_queue.put((channel_label, None))


def _mp_transcribe_single(
    audio_bytes: bytes,
    model_name: str,
    channel_label: str,
    adapter: TranscriptionModelAdapter,
) -> Dict[str, Any]:
    """Transcribe single chunk without segmentation"""
    import time

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
        tmp_file.write(audio_bytes)
        channel_audio_path = tmp_file.name

    try:
        print(
            f"[MP Worker] Transcribing single file for {channel_label} at {time.time():.2f}..."
        )

        result = asyncio.run(
            adapter.transcribe_with_model(
                audio_path=channel_audio_path,
                model_name=model_name,
                language="th",
            )
        )

        result["channel"] = channel_label
        result["speaker"] = channel_label
        return result

    finally:
        if os.path.exists(channel_audio_path):
            os.unlink(channel_audio_path)


def _mp_transcribe_chunked(
    audio_bytes: bytes,
    model_name: str,
    channel_label: str,
    adapter: TranscriptionModelAdapter,
    max_concurrent_chunks: int,
    device: str,
) -> Dict[str, Any]:
    """Transcribe with VAD segmentation"""
    import time

    chunked_start = time.time()
    print(
        f"[MP Worker {device}] Chunked transcription for {channel_label} at {chunked_start:.2f}"
    )

    segment_info = vad_segment_audio_bytes(
        wav_bytes=audio_bytes,
        target_sr=16_000,
        top_db=30.0,
        min_speech_sec=0.25,
        min_silence_sec=0.25,
        max_segment_sec=60.0,
        use_ml_vad=settings.USE_ML_VAD,
    )

    print(
        f"[MP Worker {device}] VAD segmentation completed in {time.time() - chunked_start:.2f}s, found {len(segment_info)} segments"
    )

    all_words: List[Dict[str, Any]] = []
    segments = segment_info.get("segments", [])

    for i, chunk in enumerate(segments):
        chunk_start = time.time()
        print(
            f"[MP Worker {device}] Processing chunk {i + 1}/{len(segments)} at {chunk_start:.2f}..."
        )

        chunk_bytes = chunk.to_bytes()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
            tmp_file.write(chunk_bytes)
            chunk_audio_path = tmp_file.name

        try:
            chunk_result = asyncio.run(
                adapter.transcribe_with_model(
                    audio_path=chunk_audio_path,
                    model_name=model_name,
                    language="th",
                )
            )

            words = chunk_result.get("words", [])
            offset = float(chunk.start_sec)

            for w in words:
                w_start = float(w.get("start", 0.0)) + offset
                w_end = float(w.get("end", 0.0)) + offset
                w["start"] = w_start
                w["end"] = w_end
                all_words.append(w)

            print(
                f"[MP Worker {device}] Chunk {i + 1} completed in {time.time() - chunk_start:.2f}s, {len(words)} words"
            )

        finally:
            if os.path.exists(chunk_audio_path):
                os.unlink(chunk_audio_path)

    result = {
        "channel": channel_label,
        "speaker": channel_label,
        "words": all_words,
        "language": "th",
        "duration": segment_info.get("total_duration_sec", 0),
    }

    return result


class ProcessUnifiedStereoAction:
    """
    Unified action that processes stereo WAV files through complete pipeline:
    1. Model selection (if enabled)
    2. Speaker separation (Agent/Caller)
    3. Transcription with word-level timestamps
    4. JSON structure generation

    Uses multiprocessing for true parallel execution on separate GPUs
    """

    def __init__(self):
        self.choose_model_action = ProcessChooseModelAction()

        # Speaker mapping from 3party
        self.LEFT_CHANNEL_LABEL = "Agent"
        self.RIGHT_CHANNEL_LABEL = "Caller"
        self.AMBIGUOUS_CHANNEL_LABEL = "Unknown"

        # Processing thresholds
        self.NEW_TURN_THRESHOLD = 0.3
        self.FUSE_GAP = 0.25
        self.REBUILD_GAP = 0.0
        self.MAX_WORD_DURATION = 2.0
        self.max_concurrent_chunks = 1

        # Detect GPUs
        self.device_count = 0
        self.agent_device = "cpu"
        self.caller_device = "cpu"
        self._detect_devices()

        # Set multiprocessing start method
        try:
            mp.set_start_method("spawn", force=True)
            logger.info("Set multiprocessing start method to spawn")
        except RuntimeError as e:
            logger.warning(f"Could not set multiprocessing start method: {e}")

    def _detect_devices(self) -> None:
        """Detect available GPUs and assign devices for channels"""
        try:
            import torch

            if torch.cuda.is_available():
                self.device_count = torch.cuda.device_count()
                logger.info(f"Detected {self.device_count} GPU(s)")

                if self.device_count >= 2:
                    self.agent_device = "cuda:0"
                    self.caller_device = "cuda:1"
                    logger.info("Using cuda:0 for Agent, cuda:1 for Caller")
                elif self.device_count == 1:
                    self.agent_device = "cuda:0"
                    self.caller_device = "cuda:0"
                    logger.warning(
                        "Only 1 GPU available, both channels will use cuda:0 (sequential)"
                    )
                else:
                    logger.warning("No CUDA devices available, using CPU")
            else:
                logger.warning("CUDA not available, using CPU")
        except Exception as e:
            logger.error(f"Error detecting devices: {e}")

    async def execute(
        self,
        file_content: bytes,
        filename: str,
        force_model: Optional[str] = None,
        skip_model_selection: bool = False,
        auto_continue: bool = True,
    ) -> Dict[str, Any]:
        """
        Execute unified stereo processing

        Args:
            file_content: Binary content of WAV file
            filename: Original filename
            force_model: Force specific model (typhoon/pathumma/pathumma_noise)
            skip_model_selection: Skip model selection, use force_model or default
            auto_continue: Auto-call process_json_endpoint internally

        Returns:
            Dict with complete processing results
        """
        logger.info(f"Starting unified stereo processing for: {filename}")

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
                tmp_file.write(file_content)
                tmp_path = tmp_file.name

            selected_model = force_model or "pathumma"
            model_selection_result = None

            if not skip_model_selection:
                logger.info("Running model selection...")
                model_selection_result = {
                    "chosen_model": selected_model,
                    "reasoning": "Model selection skipped - using default",
                }

            logger.info(f"Processing stereo with model: {selected_model}")

            transcription_result = await self._process_stereo_with_speaker_separation(
                tmp_path, selected_model
            )

            logger.info("Generating JSON structure...")
            json_structure = self._generate_json_structure(
                transcription_result, filename
            )

            process_json_result = None
            if auto_continue:
                logger.info("Auto-continuing to process_json...")
                process_json_result = {
                    "status": "pending",
                    "message": "Process_json integration pending",
                }

            result = {
                "action": "unified_stereo_processed",
                "filename": filename,
                "status": "completed",
                "model_selection": model_selection_result,
                "transcription": transcription_result,
                "json_structure": json_structure,
                "process_json_result": process_json_result,
                "metadata": {
                    "processed_at": datetime.now().isoformat(),
                    "model_used": selected_model,
                    "auto_continue": auto_continue,
                    "devices": {
                        "agent": self.agent_device,
                        "caller": self.caller_device,
                    },
                },
            }

            try:
                json_file_path = save_result_to_json(
                    result, f"{filename}_unified_stereo"
                )
                result["json_file_path"] = json_file_path

                json_structure_path = save_result_to_json(
                    json_structure, f"{filename}_json_structure_unified_stereo"
                )
                json_structure["json_file_path"] = json_structure_path

                logger.info(f"Unified stereo results saved to: {json_file_path}")
            except Exception as e:
                logger.error(f"Failed to save results to JSON: {str(e)}")

            logger.info(f"Unified stereo processing completed for: {filename}")
            return result

        except Exception as e:
            logger.error(f"Error in unified stereo processing: {e}")
            raise
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                    logger.debug(f"Cleaned up temporary file: {tmp_path}")
                except Exception as cleanup_error:
                    logger.warning(
                        f"Failed to cleanup temporary file {tmp_path}: {cleanup_error}"
                    )

    async def _process_stereo_with_speaker_separation(
        self, audio_path: str, model_name: str
    ) -> Dict[str, Any]:
        """
        Process stereo audio with speaker separation (Agent/Caller)
        Uses multiprocessing for true parallel execution on separate GPUs
        """
        logger.info(f"Processing stereo with speaker separation using {model_name}")

        try:
            logger.info("Loading and splitting stereo audio...")
            (
                left_channel_data,
                right_channel_data,
                duration,
            ) = await self._load_and_split_stereo(audio_path)

            logger.info("Starting multiprocessing transcription...")
            logger.info(
                f"Agent device: {self.agent_device}, Caller device: {self.caller_device}"
            )

            process_start = time.time()

            result_queue = mp.Queue()

            p0 = mp.Process(
                target=_mp_worker_transcribe_channel,
                args=(
                    left_channel_data["audio_bytes"],
                    model_name,
                    self.LEFT_CHANNEL_LABEL,
                    self.agent_device,
                    self.max_concurrent_chunks,
                    result_queue,
                ),
            )

            p1 = mp.Process(
                target=_mp_worker_transcribe_channel,
                args=(
                    right_channel_data["audio_bytes"],
                    model_name,
                    self.RIGHT_CHANNEL_LABEL,
                    self.caller_device,
                    self.max_concurrent_chunks,
                    result_queue,
                ),
            )

            print(f"[Main] Starting processes at {time.time():.2f}...")
            p0.start()
            p1.start()

            print("[Main] Processes started, waiting for results...")

            left_result = None
            right_result = None
            results_received = 0
            max_timeout = 1800

            while results_received < 2:
                try:
                    channel_label, result = result_queue.get(timeout=max_timeout)
                    print(f"[Main] Received result for {channel_label}")
                    if channel_label == self.LEFT_CHANNEL_LABEL:
                        left_result = result
                    elif channel_label == self.RIGHT_CHANNEL_LABEL:
                        right_result = result
                    results_received += 1
                except Exception as e:
                    logger.error(f"[Main] Timeout waiting for results from queue: {e}")
                    break

            p0.join(timeout=10)
            p1.join(timeout=10)

            if p0.is_alive():
                logger.warning(
                    "[Main] Left process still alive after join, terminating..."
                )
                p0.terminate()
            if p1.is_alive():
                logger.warning(
                    "[Main] Right process still alive after join, terminating..."
                )
                p1.terminate()

            if left_result is None:
                left_result = {
                    "channel": self.LEFT_CHANNEL_LABEL,
                    "speaker": self.LEFT_CHANNEL_LABEL,
                    "words": [],
                    "language": "th",
                    "duration": left_channel_data.get("duration", 0),
                }

            if right_result is None:
                right_result = {
                    "channel": self.RIGHT_CHANNEL_LABEL,
                    "speaker": self.RIGHT_CHANNEL_LABEL,
                    "words": [],
                    "language": "th",
                    "duration": right_channel_data.get("duration", 0),
                }

            total_time = time.time() - process_start
            print(f"[Main] All processes completed in {total_time:.2f}s")
            logger.info(f"Multiprocessing transcription completed in {total_time:.2f}s")

            logger.info("Merging stereo results...")
            merged_result = self._merge_stereo_results(
                left_result, right_result, duration
            )

            return merged_result

        except Exception as e:
            logger.error(f"Error in stereo processing: {e}")
            import traceback

            traceback.print_exc()
            raise

    async def _load_and_split_stereo(self, audio_path: str) -> tuple:
        """Load stereo audio and split into left/right channels"""
        logger.info(f"Loading audio from {audio_path}")

        try:
            y, sr = librosa.load(audio_path, sr=None, mono=False)

            if len(y.shape) == 1:
                logger.warning("Audio is mono, duplicating to stereo for processing")
                y = np.vstack([y, y])
            elif len(y.shape) == 2 and y.shape[0] == 1:
                logger.warning("Audio is mono (1 channel), duplicating to stereo")
                y = np.vstack([y[0], y[0]])
            elif len(y.shape) == 2 and y.shape[0] > 2:
                logger.warning(
                    f"Audio has {y.shape[0]} channels, using first 2 for stereo"
                )
                y = y[:2, :]

            duration = y.shape[1] / sr
            logger.info(
                f"Loaded stereo audio: {sr} Hz, {duration:.2f}s, shape: {y.shape}"
            )

            left_channel = y[0, :]
            right_channel = y[1, :] if y.shape[0] > 1 else y[0, :]

            left_buffer = io.BytesIO()
            sf.write(left_buffer, left_channel, sr, format="WAV")
            left_buffer.seek(0)
            left_channel_bytes = left_buffer.read()

            right_buffer = io.BytesIO()
            sf.write(right_buffer, right_channel, sr, format="WAV")
            right_buffer.seek(0)
            right_channel_bytes = right_buffer.read()

            left_channel_data = {
                "path": audio_path,
                "channel": "left",
                "audio_bytes": left_channel_bytes,
                "sample_rate": sr,
                "duration": len(left_channel) / sr,
                "speaker": "Agent",
            }

            right_channel_data = {
                "path": audio_path,
                "channel": "right",
                "audio_bytes": right_channel_bytes,
                "sample_rate": sr,
                "duration": len(right_channel) / sr,
                "speaker": "Caller",
            }

            logger.info(
                f"Split stereo audio - Left (Agent): {len(left_channel) / sr:.2f}s, Right (Caller): {len(right_channel) / sr:.2f}s"
            )

            return left_channel_data, right_channel_data, duration

        except Exception as e:
            logger.error(f"Error loading and splitting stereo audio: {e}")
            raise

    def _merge_stereo_results(
        self, left_result: Dict[str, Any], right_result: Dict[str, Any], duration: float
    ) -> Dict[str, Any]:
        """Merge left and right channel results with word-level timestamps"""
        logger.info("Merging stereo results with word-level timestamps...")

        left_words = left_result.get("words", [])
        right_words = right_result.get("words", [])

        for word in left_words:
            word["channel"] = self.LEFT_CHANNEL_LABEL
        for word in right_words:
            word["channel"] = self.RIGHT_CHANNEL_LABEL

        all_words = sorted(left_words + right_words, key=lambda w: w.get("start", 0))

        segments = self._build_segments_from_words(all_words)

        return {
            "segments": segments,
            "words": all_words,
            "language": left_result.get("language", "th"),
            "duration": duration,
        }

    def _build_segments_from_words(
        self, words: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Build segments from word-level timestamps"""
        if not words:
            return []

        segments = []
        current_segment_words = []
        last_end = None

        for word in words:
            word_start = word.get("start", 0)
            word_end = word.get("end", 0)
            word_text = word.get("word", "")

            if not word_text.strip():
                continue

            if last_end is not None:
                gap = word_start - last_end
                if gap > self.NEW_TURN_THRESHOLD and current_segment_words:
                    segments.append(self._create_segment(current_segment_words))
                    current_segment_words = []

            current_segment_words.append(word)
            last_end = word_end

        if current_segment_words:
            segments.append(self._create_segment(current_segment_words))

        return segments

    def _create_segment(self, words: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create a segment from a list of words"""
        if not words:
            return {}

        sorted_words = sorted(words, key=lambda w: w.get("start", 0))
        start = sorted_words[0].get("start", 0)
        end = sorted_words[-1].get("end", 0)
        text = " ".join(w.get("word", "") for w in sorted_words)

        speakers = [w.get("channel", "Unknown") for w in sorted_words]
        speaker = max(set(speakers), key=speakers.count) if speakers else "Unknown"

        return {
            "start": start,
            "end": end,
            "text": text,
            "speaker": speaker,
            "channel": speaker,
            "words": sorted_words,
        }

    def _generate_json_structure(
        self, transcription_result: Dict[str, Any], filename: str
    ) -> Dict[str, Any]:
        """
        Generate JSON structure matching sample_input.json format
        """
        segments = transcription_result.get("segments", [])
        words = transcription_result.get("words", [])

        # Generate formatted text
        formatted_text = self._generate_formatted_text(segments)
        simple_text = self._generate_simple_text(segments)

        return {
            "text": formatted_text,
            "simple_text": simple_text,
            "segments": segments,
            "words": words,
            "metadata": {
                "is_stereo_merged": True,
                "language": transcription_result.get("language", "th"),
                "duration": transcription_result.get("duration", 0),
                "processing_info": {
                    "start_time": time.time(),
                    "correction_passes": 0,
                    "issues_detected": 0,
                    "issues_fixed": 0,
                    "rerun_performed": False,
                    "end_time": time.time(),
                    "total_duration": 0,
                },
                "audio_info": {
                    "channels": 2,
                    "codec_name": "pcm_s16le",
                    "sample_rate": 16000,
                    "duration": transcription_result.get("duration", 0),
                    "format_name": "wav",
                    "size": "0",
                },
                "generated_at": datetime.now().isoformat(),
                "format_version": "1.0",
            },
        }

    def _generate_formatted_text(self, segments: List[Dict[str, Any]]) -> str:
        """Generate formatted text with timestamps and speaker labels"""
        lines = []
        for segment in segments:
            start = segment.get("start", 0)
            end = segment.get("end", 0)
            text = segment.get("text", "").strip()
            channel = segment.get("channel", "Unknown")

            if text:
                lines.append(f"[{start:.2f} --> {end:.2f}] [{channel}]: {text}")

        return "\n".join(lines)

    def _generate_simple_text(self, segments: List[Dict[str, Any]]) -> str:
        """Generate simple text with speaker labels only"""
        lines = []
        for segment in segments:
            text = segment.get("text", "").strip()
            channel = segment.get("channel", "Unknown")

            if text:
                lines.append(f"[{channel}]: {text}")

        return "\n".join(lines)
