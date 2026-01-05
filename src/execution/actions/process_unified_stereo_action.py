"""
Action for unified stereo transcription processing
Combines model selection, speaker separation, and JSON structure generation
"""
from typing import Dict, Any, Optional, List
import asyncio
import tempfile
import os
import json
import time
from datetime import datetime
import logging
import io
import numpy as np
import librosa
import soundfile as sf
from src.config.logs_config import get_logger
from src.execution.actions.process_choose_model_action import ProcessChooseModelAction
from src.models.asr_models import ASRModelManager
from src.models.transcription_model_adapter import TranscriptionModelAdapter
from src.utils.file.json_utils import save_result_to_json
from src.utils.audio.chunk_wav_audio import vad_segment_audio_bytes


logger = get_logger(__name__)


class ProcessUnifiedStereoAction:
    """
    Unified action that processes stereo WAV files through complete pipeline:
    1. Model selection (if enabled)
    2. Speaker separation (Agent/Caller)
    3. Transcription with word-level timestamps
    4. JSON structure generation
    """
    
    def __init__(self):
        self.choose_model_action = ProcessChooseModelAction()
        self.asr_manager_agent = None
        self.asr_manager_caller = None
        self.adapter_agent = None
        self.adapter_caller = None
        
        # Speaker mapping from 3party
        self.LEFT_CHANNEL_LABEL = "Agent"
        self.RIGHT_CHANNEL_LABEL = "Caller"
        self.AMBIGUOUS_CHANNEL_LABEL = "Unknown"
        
        # Processing thresholds
        self.NEW_TURN_THRESHOLD = 0.3  # seconds
        self.FUSE_GAP = 0.25  # seconds
        self.REBUILD_GAP = 0.0  # for Thai (non-space delimited)
        self.MAX_WORD_DURATION = 2.0  # seconds
        # Limit concurrent Pathumma chunks to reduce VRAM spikes on smaller GPUs
        self.max_concurrent_chunks = 1

        self._init_per_channel_managers()

    def _init_per_channel_managers(self) -> None:
        device_count = 0
        try:
            import torch

            if torch.cuda.is_available():
                device_count = torch.cuda.device_count()
        except Exception:
            device_count = 0

        if device_count >= 2:
            agent_device = "cuda:0"
            caller_device = "cuda:1"
        elif device_count == 1:
            agent_device = "cuda:0"
            caller_device = "cuda:0"
        else:
            agent_device = "cpu"
            caller_device = "cpu"

        self.asr_manager_agent = ASRModelManager(device=agent_device)
        self.asr_manager_caller = ASRModelManager(device=caller_device)

        self.adapter_agent = TranscriptionModelAdapter()
        self.adapter_caller = TranscriptionModelAdapter()

        from src.models.transcription_model_adapter import TyphoonAdapter, WhisperAdapter

        self.adapter_agent.register_adapter("typhoon", TyphoonAdapter(self.asr_manager_agent))
        self.adapter_agent.register_adapter("pathumma", WhisperAdapter("pathumma", self.asr_manager_agent))
        self.adapter_agent.register_adapter("pathumma_noise", WhisperAdapter("pathumma_noise", self.asr_manager_agent))

        self.adapter_caller.register_adapter("typhoon", TyphoonAdapter(self.asr_manager_caller))
        self.adapter_caller.register_adapter("pathumma", WhisperAdapter("pathumma", self.asr_manager_caller))
        self.adapter_caller.register_adapter("pathumma_noise", WhisperAdapter("pathumma_noise", self.asr_manager_caller))
        
    async def execute(
        self,
        file_content: bytes,
        filename: str,
        force_model: Optional[str] = None,
        skip_model_selection: bool = False,
        auto_continue: bool = True
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
            # Save temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
                tmp_file.write(file_content)
                tmp_path = tmp_file.name
            
            # Step 1: Model Selection (if not skipped)
            selected_model = force_model or "pathumma"
            model_selection_result = None
            
            if not skip_model_selection:
                logger.info("Running model selection...")
                # TODO: Implement model selection logic
                # For now, use default
                model_selection_result = {
                    "chosen_model": selected_model,
                    "reasoning": "Model selection skipped - using default",
                }
            
            # Step 2: Stereo Processing and Transcription
            logger.info(f"Processing stereo with model: {selected_model}")
            
            # Process stereo with speaker separation
            transcription_result = await self._process_stereo_with_speaker_separation(
                tmp_path, selected_model
            )
            
            # Step 3: Generate JSON Structure
            logger.info("Generating JSON structure...")
            json_structure = self._generate_json_structure(
                transcription_result, filename
            )
            
            # Step 4: Auto-continue to process_json if enabled
            process_json_result = None
            if auto_continue:
                logger.info("Auto-continuing to process_json...")
                # TODO: Call process_json_endpoint internally
                process_json_result = {
                    "status": "pending",
                    "message": "Process_json integration pending"
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
                    "auto_continue": auto_continue
                }
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
            # Cleanup temporary file in all cases
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                    logger.debug(f"Cleaned up temporary file: {tmp_path}")
                except Exception as cleanup_error:
                    logger.warning(f"Failed to cleanup temporary file {tmp_path}: {cleanup_error}")
    
    async def _process_stereo_with_speaker_separation(self, audio_path: str, model_name: str) -> Dict[str, Any]:
        """
        Process stereo audio with speaker separation (Agent/Caller)
        Step 1: Load stereo audio and split channels
        Step 2: Transcribe each channel separately
        Step 3: Merge results with word-level timestamps
        """
        logger.info(f"Processing stereo with speaker separation using {model_name}")
        
        try:
            logger.info("Loading and splitting stereo audio...")
            left_channel_data, right_channel_data, duration = await self._load_and_split_stereo(audio_path)

            semaphore = asyncio.Semaphore(self.max_concurrent_chunks)

            logger.info("Transcribing left and right channels concurrently...")
            left_task = asyncio.create_task(
                self._transcribe_channel(
                    left_channel_data,
                    model_name,
                    self.LEFT_CHANNEL_LABEL,
                    semaphore,
                )
            )
            right_task = asyncio.create_task(
                self._transcribe_channel(
                    right_channel_data,
                    model_name,
                    self.RIGHT_CHANNEL_LABEL,
                    semaphore,
                )
            )

            left_result, right_result = await asyncio.gather(left_task, right_task)
            
            # Step 3: Merge results with word-level timestamps
            logger.info("Merging stereo results...")
            merged_result = self._merge_stereo_results(left_result, right_result, duration)
            
            return merged_result
            
        except Exception as e:
            logger.error(f"Error in stereo processing: {e}")
            raise
    
    async def _load_and_split_stereo(self, audio_path: str) -> tuple:
        """Load stereo audio and split into left/right channels"""
        logger.info(f"Loading audio from {audio_path}")
        
        try:
            # Load stereo audio
            y, sr = librosa.load(audio_path, sr=None, mono=False)
            
            # Check if audio is actually stereo
            if len(y.shape) == 1:
                logger.warning("Audio is mono, duplicating to stereo for processing")
                # Convert mono to stereo by duplicating
                y = np.vstack([y, y])
            elif len(y.shape) == 2 and y.shape[0] == 1:
                logger.warning("Audio is mono (1 channel), duplicating to stereo")
                # Convert single channel to stereo
                y = np.vstack([y[0], y[0]])
            elif len(y.shape) == 2 and y.shape[0] > 2:
                logger.warning(f"Audio has {y.shape[0]} channels, using first 2 for stereo")
                # Use only first 2 channels
                y = y[:2, :]
            
            # Calculate duration
            duration = y.shape[1] / sr
            logger.info(f"Loaded stereo audio: {sr} Hz, {duration:.2f}s, shape: {y.shape}")
            
            # Split into left and right channels
            # Channel 0 (left) = Agent, Channel 1 (right) = Caller
            left_channel = y[0, :]  # Agent
            right_channel = y[1, :] if y.shape[0] > 1 else y[0, :]  # Caller
            
            # Convert to bytes for processing
            left_buffer = io.BytesIO()
            sf.write(left_buffer, left_channel, sr, format='WAV')
            left_buffer.seek(0)
            left_channel_bytes = left_buffer.read()
            
            right_buffer = io.BytesIO()
            sf.write(right_buffer, right_channel, sr, format='WAV')
            right_buffer.seek(0)
            right_channel_bytes = right_buffer.read()
            
            # Create channel data with metadata
            left_channel_data = {
                "path": audio_path,
                "channel": "left",
                "audio_bytes": left_channel_bytes,
                "sample_rate": sr,
                "duration": len(left_channel) / sr,
                "speaker": "Agent"
            }
            
            right_channel_data = {
                "path": audio_path,
                "channel": "right",
                "audio_bytes": right_channel_bytes,
                "sample_rate": sr,
                "duration": len(right_channel) / sr,
                "speaker": "Caller"
            }
            
            logger.info(f"Split stereo audio - Left (Agent): {len(left_channel)/sr:.2f}s, Right (Caller): {len(right_channel)/sr:.2f}s")
            
            return left_channel_data, right_channel_data, duration
            
        except Exception as e:
            logger.error(f"Error loading and splitting stereo audio: {e}")
            raise
    
    def _get_adapter_for_channel(self, channel_label: str) -> TranscriptionModelAdapter:
        if channel_label == self.LEFT_CHANNEL_LABEL:
            return self.adapter_agent
        if channel_label == self.RIGHT_CHANNEL_LABEL:
            return self.adapter_caller
        return self.adapter_agent

    async def _transcribe_channel(self, channel_data: Dict[str, Any], model_name: str, channel_label: str, semaphore: Optional[asyncio.Semaphore] = None) -> Dict[str, Any]:
        """Transcribe a single channel using model adapter"""
        logger.info(f"Transcribing {channel_label} channel with {model_name}...")

        try:
            audio_bytes = channel_data.get("audio_bytes")
            if not audio_bytes:
                raise ValueError(f"No audio bytes found for {channel_label} channel")
            adapter = self._get_adapter_for_channel(channel_label)

            if model_name in ["pathumma", "pathumma_noise"]:
                return await self._transcribe_channel_chunked(
                    audio_bytes,
                    channel_data,
                    model_name,
                    channel_label,
                    semaphore,
                )

            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
                tmp_file.write(audio_bytes)
                channel_audio_path = tmp_file.name
            try:
                result = await adapter.transcribe_with_model(
                    audio_path=channel_audio_path,
                    model_name=model_name,
                    language="th",
                )
                result["channel"] = channel_label
                result["speaker"] = channel_data.get("speaker", channel_label)
                result["duration"] = channel_data.get("duration", 0)
                logger.info(f"Channel {channel_label} transcription completed")
                return result
            finally:
                if os.path.exists(channel_audio_path):
                    os.unlink(channel_audio_path)
            
        except Exception as e:
            logger.error(f"Error transcribing {channel_label} channel: {e}")
            raise
    
    def _merge_stereo_results(self, left_result: Dict[str, Any], right_result: Dict[str, Any], duration: float) -> Dict[str, Any]:
        """Merge left and right channel results with word-level timestamps"""
        logger.info("Merging stereo results with word-level timestamps...")
        
        # Get words from both channels
        left_words = left_result.get("words", [])
        right_words = right_result.get("words", [])
        
        # Add channel labels
        for word in left_words:
            word["channel"] = self.LEFT_CHANNEL_LABEL
        for word in right_words:
            word["channel"] = self.RIGHT_CHANNEL_LABEL
        
        # Combine and sort by start time
        all_words = sorted(left_words + right_words, key=lambda w: w.get("start", 0))
        
        # Build segments from words
        segments = self._build_segments_from_words(all_words)
        
        return {
            "segments": segments,
            "words": all_words,
            "language": left_result.get("language", "th"),
            "duration": duration
        }

    async def _transcribe_channel_chunked(self, audio_bytes: bytes, channel_data: Dict[str, Any], model_name: str, channel_label: str, semaphore: Optional[asyncio.Semaphore] = None) -> Dict[str, Any]:
        logger.info(f"Chunked transcription for {channel_label} with {model_name}")
        if semaphore is None:
            semaphore = asyncio.Semaphore(self.max_concurrent_chunks)

        segment_info = vad_segment_audio_bytes(
            wav_bytes=audio_bytes,
            target_sr=16_000,
            top_db=25.0,
            min_speech_sec=0.2,
            min_silence_sec=0.2,
            max_segment_sec=60.0,
        )

        adapter = self._get_adapter_for_channel(channel_label)

        async def process_single_chunk(chunk) -> List[Dict[str, Any]]:
            async with semaphore:
                chunk_bytes = chunk.to_bytes()
                with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
                    tmp_file.write(chunk_bytes)
                    chunk_audio_path = tmp_file.name
                try:
                    chunk_result = await adapter.transcribe_with_model(
                        audio_path=chunk_audio_path,
                        model_name=model_name,
                        language="th",
                    )
                finally:
                    if os.path.exists(chunk_audio_path):
                        os.unlink(chunk_audio_path)

                words = chunk_result.get("words", [])
                if not words:
                    return []

                offset = float(chunk.start_sec)
                shifted_words: List[Dict[str, Any]] = []
                for w in words:
                    w_start = float(w.get("start", 0.0)) + offset
                    w_end = float(w.get("end", 0.0)) + offset
                    w["start"] = w_start
                    w["end"] = w_end
                    shifted_words.append(w)
                return shifted_words

        tasks: List[asyncio.Task] = []
        for chunk in segment_info["segments"]:
            tasks.append(asyncio.create_task(process_single_chunk(chunk)))

        all_words: List[Dict[str, Any]] = []
        if tasks:
            results = await asyncio.gather(*tasks)
            for words in results:
                all_words.extend(words)

        all_words.sort(key=lambda w: w.get("start", 0.0))
        all_words = self._sanitize_words(all_words)

        result: Dict[str, Any] = {
            "words": all_words,
            "segments": self._build_segments_from_words(all_words),
            "language": "th",
            "duration": channel_data.get("duration", 0),
        }
        result["channel"] = channel_label
        result["speaker"] = channel_data.get("speaker", channel_label)
        logger.info(f"Channel {channel_label} chunked transcription completed with {len(all_words)} words")
        return result
    
    def _build_segments_from_words(self, words: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Build segments from words based on speaker turns and pauses"""
        if not words:
            return []
        
        segments = []
        current_segment = None
        
        for i, word in enumerate(words):
            # Check if we need to start a new segment
            should_start_new = False
            
            if current_segment is None:
                should_start_new = True
            else:
                # Check for speaker change
                if word.get("channel") != current_segment.get("channel"):
                    should_start_new = True
                else:
                    # Check for long pause (NEW_TURN_THRESHOLD)
                    last_word_end = current_segment["words"][-1]["end"]
                    gap = word["start"] - last_word_end
                    if gap > self.NEW_TURN_THRESHOLD:
                        should_start_new = True
            
            if should_start_new:
                # Finish current segment
                if current_segment:
                    self._sanitize_segment(current_segment)
                    segments.append(current_segment)
                
                # Start new segment
                current_segment = {
                    "id": len(segments),
                    "seek": 0,
                    "start": word["start"],
                    "end": word["end"],
                    "text": "",
                    "channel": word.get("channel", "Unknown"),
                    "words": [word]
                }
            else:
                # Add to current segment
                current_segment["words"].append(word)
                current_segment["end"] = word["end"]
        
        if current_segment:
            self._sanitize_segment(current_segment)
            segments.append(current_segment)

        # Sort segments by start time
        segments.sort(key=lambda s: s.get("start", 0))

        # Ensure segments do not overlap in time
        for i in range(len(segments) - 1):
            current = segments[i]
            nxt = segments[i + 1]

            # Only adjust when next segment clearly starts after current
            if nxt["start"] > current["start"] and current["end"] > nxt["start"]:
                current["end"] = nxt["start"]

        return segments

    def _sanitize_segment(self, segment: Dict[str, Any]) -> None:
        words = segment.get("words", [])
        if not words:
            segment["text"] = ""
            return
        start = float(segment.get("start", 0.0))
        end = float(segment.get("end", start))
        duration = max(end - start, 0.01)
        max_tokens_per_sec = 8.0
        max_tokens = int(max_tokens_per_sec * duration) + 4
        if len(words) > max_tokens:
            words = words[:max_tokens]
            segment["words"] = words
            if words:
                segment["end"] = float(words[-1].get("end", end))
        segment["text"] = " ".join(w["word"] for w in words).strip()
    
    def _sanitize_words(self, words: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not words:
            return []

        cleaned: List[Dict[str, Any]] = []
        zero_length_run = 0
        eps = 1e-3

        for w in words:
            start = float(w.get("start", 0.0))
            end = float(w.get("end", start))
            duration = end - start

            if duration < 0:
                continue

            if duration <= eps:
                if cleaned:
                    prev_end = float(cleaned[-1].get("end", 0.0))
                    if abs(start - prev_end) <= 0.05:
                        zero_length_run += 1
                        if zero_length_run > 2:
                            continue
                    else:
                        zero_length_run = 0
                else:
                    zero_length_run = 0
            else:
                zero_length_run = 0

            cleaned.append(w)

        return cleaned
    
    def _generate_json_structure(self, transcription_result: Dict[str, Any], filename: str) -> Dict[str, Any]:
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
                        "total_duration": 0
                    },
                    "audio_info": {
                        "channels": 2,
                        "codec_name": "pcm_s16le",
                        "sample_rate": 16000,
                        "duration": transcription_result.get("duration", 0),
                        "format_name": "wav",
                        "size": "0"
                    },
                    "generated_at": datetime.now().isoformat(),
                    "format_version": "1.0"
                }
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
