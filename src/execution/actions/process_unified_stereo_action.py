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
from src.models.transcription_model_adapter import transcription_adapter
from src.utils.file.json_utils import save_result_to_json


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
        self.asr_manager = ASRModelManager()
        
        # Speaker mapping from 3party
        self.LEFT_CHANNEL_LABEL = "Agent"
        self.RIGHT_CHANNEL_LABEL = "Caller"
        self.AMBIGUOUS_CHANNEL_LABEL = "Unknown"
        
        # Processing thresholds
        self.NEW_TURN_THRESHOLD = 1.0  # seconds
        self.FUSE_GAP = 0.25  # seconds
        self.REBUILD_GAP = 0.0  # for Thai (non-space delimited)
        self.MAX_WORD_DURATION = 2.0  # seconds
        
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
                # Add the file path before saving
                result["json_file_path"] = (
                    f"src/data/wav2files/{filename}_unified_stereo.json"
                )
                json_file_path = save_result_to_json(
                    result, f"{filename}_unified_stereo"
                )
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
            # Step 1: Load and split stereo audio
            logger.info("Loading and splitting stereo audio...")
            left_channel_data, right_channel_data, duration = await self._load_and_split_stereo(audio_path)
            
            # Step 2: Transcribe each channel
            logger.info("Transcribing left channel (Agent)...")
            left_result = await self._transcribe_channel(left_channel_data, model_name, self.LEFT_CHANNEL_LABEL)
            
            logger.info("Transcribing right channel (Caller)...")
            right_result = await self._transcribe_channel(right_channel_data, model_name, self.RIGHT_CHANNEL_LABEL)
            
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
    
    async def _transcribe_channel(self, channel_data: Dict[str, Any], model_name: str, channel_label: str) -> Dict[str, Any]:
        """Transcribe a single channel using model adapter"""
        logger.info(f"Transcribing {channel_label} channel with {model_name}...")
        
        try:
            # Get audio bytes from channel data
            audio_bytes = channel_data.get("audio_bytes")
            if not audio_bytes:
                raise ValueError(f"No audio bytes found for {channel_label} channel")
            
            # Create temporary file for channel audio
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
                tmp_file.write(audio_bytes)
                channel_audio_path = tmp_file.name
            
            try:
                # Use transcription adapter
                result = await transcription_adapter.transcribe_with_model(
                    audio_path=channel_audio_path,
                    model_name=model_name,
                    language="th"
                )
                
                # Add channel metadata to result
                result["channel"] = channel_label
                result["speaker"] = channel_data.get("speaker", channel_label)
                result["duration"] = channel_data.get("duration", 0)
                
                logger.info(f"Channel {channel_label} transcription completed")
                return result
                
            finally:
                # Clean up temporary file
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
                    current_segment["text"] = "".join(w["word"] for w in current_segment["words"]).strip()
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
        
        # Finish last segment
        if current_segment:
            current_segment["text"] = "".join(w["word"] for w in current_segment["words"]).strip()
            segments.append(current_segment)
        
        return segments
    
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
            "transcript": {
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
