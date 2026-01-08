from typing import Dict, Any, List, Generator, Tuple
import numpy as np
import io
import librosa
import soundfile as sf
from src.config.logs_config import get_logger

logger = get_logger(__name__)

_silero_vad_model = None
_silero_vad_get_speech_timestamps = None


def _load_silero_vad():
    global _silero_vad_model, _silero_vad_get_speech_timestamps
    if _silero_vad_model is not None and _silero_vad_get_speech_timestamps is not None:
        return _silero_vad_model, _silero_vad_get_speech_timestamps
    import torch

    model, utils = torch.hub.load("snakers4/silero-vad", "silero_vad", trust_repo=True)
    (get_speech_timestamps, _, _, _, _) = utils
    _silero_vad_model = model
    _silero_vad_get_speech_timestamps = get_speech_timestamps
    return _silero_vad_model, _silero_vad_get_speech_timestamps


class AudioChunk:
    """Represents a single audio chunk"""

    def __init__(
        self,
        chunk_index: int,
        audio_data: np.ndarray,
        sample_rate: int,
        start_sec: float,
        end_sec: float,
    ):
        self.chunk_index = chunk_index
        self.audio_data = audio_data
        self.sample_rate = sample_rate
        self.start_sec = start_sec
        self.end_sec = end_sec
        self.duration_sec = end_sec - start_sec

    def to_bytes(self) -> bytes:
        """Convert audio chunk to WAV bytes"""
        buffer = io.BytesIO()
        sf.write(buffer, self.audio_data, self.sample_rate, format="WAV")
        buffer.seek(0)
        return buffer.read()

    def to_dict(self) -> Dict[str, Any]:
        """Convert chunk to dictionary"""
        return {
            "chunk_index": self.chunk_index,
            "start_sec": float(self.start_sec),
            "end_sec": float(self.end_sec),
            "duration_sec": float(self.duration_sec),
            "sample_rate": self.sample_rate,
        }


def chunk_wav_audio_bytes(
    wav_bytes: bytes,
    target_sr: int = 16_000,
    chunk_duration_s: int = 30,
    overlap_s: int = 3,
    normalize: bool = True,
    batch_size: int = 3,
) -> Dict[str, Any]:
    """
    Chunk WAV audio bytes into segments for processing

    Args:
        wav_bytes: WAV file as bytes
        target_sr: Target sample rate
        chunk_duration_s: Duration of each chunk in seconds
        normalize: Whether to normalize audio
        batch_size: Number of chunks to process in batch

    Returns:
        Dict with chunk information and generator for chunks
    """
    try:
        logger.info(f"Processing WAV audio: {len(wav_bytes)} bytes")

        # Load audio from bytes
        buffer = io.BytesIO(wav_bytes)
        y, sr = librosa.load(buffer, sr=None, mono=True)
        orig_duration = len(y) / sr

        logger.info(f"Original: {sr} Hz, {orig_duration:.1f}s")

        # Resample if needed
        if sr != target_sr:
            y = librosa.resample(y, orig_sr=sr, target_sr=target_sr)
            logger.info(f"Resampled: {sr} Hz → {target_sr} Hz")
            sr = target_sr

        # Normalize if requested
        if normalize:
            peak = np.max(np.abs(y))
            if peak > 0:
                y = y / peak
                logger.info("Audio normalized")

        total_duration = len(y) / sr
        chunk_samples = int(chunk_duration_s * sr)
        overlap_samples = int(overlap_s * sr)

        # Calculate number of chunks with overlap
        if overlap_s > 0:
            step_samples = chunk_samples - overlap_samples
            num_chunks = int(np.ceil((len(y) - overlap_samples) / step_samples))
        else:
            step_samples = chunk_samples
            num_chunks = int(np.ceil(len(y) / chunk_samples))

        logger.info(
            f"Final: {total_duration:.1f}s, {num_chunks} chunks, {overlap_s}s overlap"
        )

        # Create chunk generator function
        def chunk_generator() -> Generator[AudioChunk, None, None]:
            for idx in range(num_chunks):
                if overlap_s > 0:
                    start_sample = idx * step_samples
                    end_sample = min(start_sample + chunk_samples, len(y))
                else:
                    start_sample = idx * chunk_samples
                    end_sample = min((idx + 1) * chunk_samples, len(y))

                if end_sample <= start_sample:
                    continue

                chunk_y = y[start_sample:end_sample]
                start_sec = start_sample / sr
                end_sec = end_sample / sr

                chunk = AudioChunk(
                    chunk_index=idx,
                    audio_data=chunk_y,
                    sample_rate=sr,
                    start_sec=start_sec,
                    end_sec=end_sec,
                )

                yield chunk

        # Create batch generator for memory efficiency
        def batch_generator() -> Generator[List[AudioChunk], None, None]:
            batch = []
            for chunk in chunk_generator():
                batch.append(chunk)

                if len(batch) >= batch_size:
                    yield batch
                    batch = []

            # Yield remaining chunks
            if batch:
                yield batch

        # Create metadata
        chunks_meta = []
        for idx in range(num_chunks):
            if overlap_s > 0:
                start_sample = idx * step_samples
                end_sample = min(start_sample + chunk_samples, len(y))
            else:
                start_sample = idx * chunk_samples
                end_sample = min((idx + 1) * chunk_samples, len(y))

            if end_sample <= start_sample:
                continue

            start_sec = start_sample / sr
            end_sec = end_sample / sr

            chunks_meta.append(
                {
                    "chunk_index": idx,
                    "start_sec": float(start_sec),
                    "end_sec": float(end_sec),
                    "duration_sec": float(end_sec - start_sec),
                }
            )

        return {
            "sample_rate": sr,
            "total_duration_sec": float(total_duration),
            "chunk_duration_sec": int(chunk_duration_s),
            "overlap_sec": overlap_s,
            "num_chunks": len(chunks_meta),
            "chunks": chunks_meta,
            "chunk_generator": chunk_generator,
            "batch_generator": batch_generator,
            "batch_size": batch_size,
        }

    except Exception as e:
        logger.error(f"Error chunking audio: {e}")
        raise


def process_chunks_in_batches(
    wav_bytes: bytes,
    processor_func: callable,
    target_sr: int = 16_000,
    chunk_duration_s: int = 30,
    overlap_s: int = 3,
    batch_size: int = 3,
) -> List[Dict[str, Any]]:
    """
    Process audio chunks in batches for memory efficiency

    Args:
        wav_bytes: WAV file as bytes
        processor_func: Function to process each chunk batch
        target_sr: Target sample rate
        chunk_duration_s: Duration of each chunk
        batch_size: Number of chunks per batch

    Returns:
        List of processing results
    """
    try:
        # Get chunking info
        chunk_info = chunk_wav_audio_bytes(
            wav_bytes=wav_bytes,
            target_sr=target_sr,
            chunk_duration_s=chunk_duration_s,
            overlap_s=overlap_s,
            batch_size=batch_size,
        )

        results = []

        # Process batches
        for batch_idx, chunk_batch in enumerate(chunk_info["batch_generator"]()):
            logger.info(f"Processing batch {batch_idx + 1}: {len(chunk_batch)} chunks")

            # Convert chunks to bytes for processing
            chunk_bytes_list = [chunk.to_bytes() for chunk in chunk_batch]
            chunk_meta_list = [chunk.to_dict() for chunk in chunk_batch]

            # Process batch
            batch_results = processor_func(chunk_bytes_list, chunk_meta_list)
            results.extend(batch_results)

            # Explicit cleanup
            del chunk_bytes_list
            del chunk_meta_list
            del chunk_batch

        return results

    except Exception as e:
        logger.error(f"Error processing chunks in batches: {e}")
        raise


def vad_segment_audio_bytes(
    wav_bytes: bytes,
    target_sr: int = 16_000,
    top_db: float = 30.0,
    min_speech_sec: float = 0.3,
    min_silence_sec: float = 0.3,
    max_segment_sec: float = 60.0,
    use_ml_vad: bool = False,
) -> Dict[str, Any]:
    try:
        buffer = io.BytesIO(wav_bytes)
        y, sr = librosa.load(buffer, sr=None, mono=True)
        if sr != target_sr:
            y = librosa.resample(y, orig_sr=sr, target_sr=target_sr)
            sr = target_sr
        if len(y) == 0:
            return {
                "sample_rate": sr,
                "total_duration_sec": 0.0,
                "segments": [],
            }
        total_duration = float(len(y) / sr)
        if use_ml_vad:
            try:
                import torch

                model, get_speech_timestamps = _load_silero_vad()
                audio_tensor = torch.from_numpy(y).float()
                if audio_tensor.dim() == 1:
                    audio_tensor = audio_tensor.unsqueeze(0)
                speech_ts = get_speech_timestamps(audio_tensor, model, sampling_rate=sr)
                segments_samples: List[Tuple[int, int]] = []
                for ts in speech_ts:
                    start = int(ts.get("start", 0))
                    end = int(ts.get("end", start))
                    duration_sec = (end - start) / sr
                    if duration_sec < min_speech_sec:
                        continue
                    if duration_sec <= max_segment_sec:
                        segments_samples.append((start, end))
                        continue
                    max_samples = int(max_segment_sec * sr)
                    current = start
                    while current < end:
                        seg_end = min(current + max_samples, end)
                        if seg_end > current:
                            segments_samples.append((current, seg_end))
                        current = seg_end
            except Exception as e:
                logger.error(f"Error in ML VAD, falling back to energy VAD: {e}")
                segments_samples = []
        if not segments_samples:
            intervals = librosa.effects.split(y, top_db=top_db)
            merged: List[Tuple[int, int]] = []
            for start, end in intervals:
                if not merged:
                    merged.append((start, end))
                    continue
                last_start, last_end = merged[-1]
                gap_sec = (start - last_end) / sr
                if gap_sec < min_silence_sec:
                    merged[-1] = (last_start, end)
                else:
                    merged.append((start, end))
            for start, end in merged:
                duration_sec = (end - start) / sr
                if duration_sec < min_speech_sec:
                    continue
                if duration_sec <= max_segment_sec:
                    segments_samples.append((start, end))
                    continue
                max_samples = int(max_segment_sec * sr)
                current = start
                while current < end:
                    seg_end = min(current + max_samples, end)
                    if seg_end > current:
                        segments_samples.append((current, seg_end))
                    current = seg_end
        segments: List[AudioChunk] = []
        for idx, (start, end) in enumerate(segments_samples):
            seg_y = y[start:end]
            start_sec = start / sr
            end_sec = end / sr
            segments.append(
                AudioChunk(
                    chunk_index=idx,
                    audio_data=seg_y,
                    sample_rate=sr,
                    start_sec=start_sec,
                    end_sec=end_sec,
                )
            )
        return {
            "sample_rate": sr,
            "total_duration_sec": total_duration,
            "segments": segments,
        }
    except Exception as e:
        logger.error(f"Error in VAD segmentation: {e}")
        raise
