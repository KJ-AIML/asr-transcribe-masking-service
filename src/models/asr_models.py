"""
Patched asr.py
- Lazy-load models (no eager loading on ASRModelManager init)
- Controlled loading with LRU eviction (max_loaded_models)
- PathummaASR: use WhisperProcessor + WhisperForConditionalGeneration from_pretrained
  (avoid HF pipeline which is eager and harder to control memory)
- Ensure input dtypes match model dtype (float16 vs float32)
- Safe chunking (<= 25-30s per chunk) and attention_mask handling
- Async load locks to avoid concurrent loads racing to GPU
- Utilities: clear_cache, unload_models, memory logging

Replace your existing asr.py with this file. Adjust `max_loaded_models` in
ASRModelManager() to suit your GPU VRAM (default=1 for a single large model on one GPU).
"""

from typing import Dict, Any, Optional, List
from pathlib import Path
import torch
import time
import asyncio
import gc
import os
from collections import OrderedDict
import tempfile

from transformers import WhisperProcessor, WhisperForConditionalGeneration
from huggingface_hub import snapshot_download

from src.config.logs_config import get_logger

logger = get_logger(__name__)

BASE_DIR = Path(__file__).resolve().parents[2]
ASR_MODELS_CACHE_DIR = BASE_DIR / "asr_models_cache"
ASR_MODELS_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Safe-mode: per-device async locks to ensure 1 job per GPU at a time
_DEVICE_LOCKS: Dict[str, asyncio.Lock] = {}


class ASRModelBase:
    """Base class for ASR model wrappers."""

    def __init__(self, model_name: str, device: Optional[str] = None):
        self.model_name = model_name
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32
        self._model = None

    def _load_model(self):
        raise NotImplementedError

    async def transcribe(self, audio_data: bytes) -> Dict[str, Any]:
        raise NotImplementedError

    def unload_model(self):
        """Optional: free model resources."""
        pass

    def is_loaded(self) -> bool:
        return False


class TyphoonASR(ASRModelBase):
    """Typhoon ASR (example). Keep lazy-load behaviour as in your original code."""

    def __init__(self, device: Optional[str] = None):
        super().__init__("typhoon", device=device)
        self._transcribe_fn = None
        self._model_loaded = False
        self._load_lock = asyncio.Lock()

    def _load_model(self):
        if self._model_loaded:
            return

        # synchronous import and load
        import signal
        if not hasattr(signal, "SIGKILL"):
            signal.SIGKILL = signal.SIGTERM

        from typhoon_asr import transcribe  # may raise ImportError
        self._transcribe_fn = transcribe
        self._model_loaded = True
        logger.info("Typhoon ASR model loaded")

    async def ensure_loaded(self):
        async with self._load_lock:
            if not self._model_loaded:
                # consider running in executor if import is slow
                self._load_model()

    async def transcribe(self, audio_data: bytes) -> Dict[str, Any]:
        if self._transcribe_fn is None:
            try:
                await self.ensure_loaded()
            except Exception as e:
                logger.error(f"Failed to load Typhoon model: {e}")
                return {"text": "", "error": f"Typhoon model unavailable: {str(e)}"}

        if self._transcribe_fn is None:
            return {"text": "", "error": "Typhoon model not available"}

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                temp_file.write(audio_data)
                tmp_path = temp_file.name

            result = self._transcribe_fn(tmp_path)

            if isinstance(result, dict):
                text = result.get("text", str(result))
            elif isinstance(result, str):
                text = result
            else:
                text = str(result)

            return {"text": text, "error": None}

        except Exception as e:
            logger.exception(f"Typhoon transcription error: {e}")
            return {"text": "", "error": str(e)}

        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    logger.debug(f"Failed to cleanup temp file: {tmp_path}")

    def unload_model(self):
        try:
            self._transcribe_fn = None
            self._model_loaded = False
            # clear module cache
            import sys
            modules_to_remove = [m for m in list(sys.modules.keys()) if "typhoon_asr" in m]
            for m in modules_to_remove:
                sys.modules.pop(m, None)

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            logger.info("Typhoon ASR model unloaded")
        except Exception:
            logger.exception("Failed unloading Typhoon model")

    def is_loaded(self) -> bool:
        return self._model_loaded and (self._transcribe_fn is not None)


class PathummaASR(ASRModelBase):
    """Pathumma Whisper wrapper using transformers (processor + model).

    This class lazy-loads with an asyncio.Lock and attempts to control memory by
    moving models to device only when requested. Chunking and dtype casting are handled.
    """

    def __init__(self, model_name: str = "nectec/Pathumma-whisper-th-large-v3", chunk_sec: int = 25, device: Optional[str] = None):
        super().__init__(model_name, device=device)
        self.lang = "th"
        self.task = "transcribe"
        self._model_loaded = False
        self._processor: Optional[WhisperProcessor] = None
        self._wf_model: Optional[WhisperForConditionalGeneration] = None
        self._forced_decoder_ids = None
        self._load_lock = asyncio.Lock()
        self.num_beams = 1
        self.max_new_tokens = 256
        # safe chunk <= 30 sec (use 25 by default)
        self.chunk_sec = min(25, chunk_sec)

    def _download_local_model(self) -> str:
        """Ensure model cached locally and return local path. Uses huggingface_hub snapshot_download.
        If snapshot_download fails (e.g., offline), it will re-raise the exception.
        """
        cache_dir = ASR_MODELS_CACHE_DIR
        try:
            local_model_path = snapshot_download(
                repo_id=self.model_name,
                cache_dir=str(cache_dir),
                local_files_only=True,
            )
            logger.info(f"Using cached Pathumma model from {local_model_path}")
            return local_model_path
        except Exception:
            logger.info("Pathumma model not found in cache, attempting to download")
            local_model_path = snapshot_download(
                repo_id=self.model_name,
                cache_dir=str(cache_dir),
                local_files_only=False,
            )
            logger.info(f"Downloaded Pathumma model to {local_model_path}")
            return local_model_path

    def _load_model(self):
        if self._model_loaded and self._wf_model is not None:
            return

        logger.info(f"Loading Pathumma model {self.model_name} dtype={self.torch_dtype} device={self.device}")

        local_model_path = None
        try:
            local_model_path = self._download_local_model()
        except Exception as e:
            logger.warning(f"snapshot_download failed: {e} - will try to load from hub directly")
            local_model_path = self.model_name

        self._processor = WhisperProcessor.from_pretrained(local_model_path)

        try:
            self._forced_decoder_ids = self._processor.get_decoder_prompt_ids(language=self.lang, task=self.task)
        except Exception:
            logger.exception("Failed to compute forced_decoder_ids; will use default decoding")
            self._forced_decoder_ids = None

        self._wf_model = WhisperForConditionalGeneration.from_pretrained(
            local_model_path,
            torch_dtype=self.torch_dtype,
            low_cpu_mem_usage=True,
        )

        # move to device (GPU if available and requested)
        if torch.cuda.is_available() and "cuda" in self.device:
            try:
                self._wf_model = self._wf_model.to(self.device)
            except Exception:
                logger.exception("Failed to move Pathumma model to device; continuing with CPU (may be slow)")

        self._wf_model.eval()

        try:
            self._wf_model.generation_config.use_cache = False
            self._wf_model.generation_config.task = self.task
            self._wf_model.generation_config.num_beams = self.num_beams
            if self._forced_decoder_ids is not None:
                try:
                    self._wf_model.generation_config.forced_decoder_ids = self._forced_decoder_ids
                except Exception:
                    logger.exception("Failed to set forced_decoder_ids on generation_config")
        except Exception:
            logger.debug("Failed to set generation_config - fine.")

        self._model_loaded = True
        logger.info("Pathumma model loaded (transformers style)")

    async def ensure_loaded(self):
        async with self._load_lock:
            if not self._model_loaded:
                # heavy IO/load - consider run_in_executor if needed
                self._load_model()

    def _load_audio_tensor(self, tmp_path: str) -> torch.Tensor:
        import torchaudio
        wav, sr = torchaudio.load(tmp_path)
        if sr != 16000:
            wav = torchaudio.functional.resample(wav, sr, 16000)
        # ensure mono
        if wav.dim() > 1:
            wav = wav.mean(dim=0, keepdim=True)
        wav = wav.squeeze(0)
        return wav

    def _chunk_audio(self, wav: torch.Tensor):
        chunk_size = int(self.chunk_sec * 16000)
        for i in range(0, len(wav), chunk_size):
            yield wav[i:i + chunk_size]

    def _transcribe_chunks_sync(self, wav: torch.Tensor) -> str:
        results: List[str] = []

        # Ensure correct CUDA device is set for this thread when using GPU
        if torch.cuda.is_available() and isinstance(self.device, str) and self.device.startswith("cuda"):
            try:
                device_index = int(self.device.split(":")[1]) if ":" in self.device else 0
                torch.cuda.set_device(device_index)
            except Exception:
                logger.exception(f"Failed to set CUDA device {self.device} in _transcribe_chunks_sync")

        with torch.no_grad():
            for chunk in self._chunk_audio(wav):
                if chunk.numel() == 0:
                    continue

                inputs = self._processor(
                    chunk,
                    sampling_rate=16000,
                    return_tensors="pt",
                    return_attention_mask=True,
                    padding="max_length",
                    truncation=True,
                )

                input_features = inputs.input_features.to(device=self.device, dtype=self._wf_model.dtype)

                attention_mask = inputs.attention_mask.to(self.device) if "attention_mask" in inputs else None

                generate_kwargs = {
                    "attention_mask": attention_mask,
                    "max_new_tokens": self.max_new_tokens,
                    "num_beams": self.num_beams,
                }

                generated = self._wf_model.generate(
                    input_features,
                    **generate_kwargs,
                )

                text = self._processor.batch_decode(generated, skip_special_tokens=True)[0]
                results.append(text)

                del inputs, input_features, attention_mask, generated
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

        return " ".join(results)

    async def transcribe(self, audio_data: bytes) -> Dict[str, Any]:
        await self.ensure_loaded()

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(audio_data)
                tmp_path = tmp.name

            wav = self._load_audio_tensor(tmp_path)

            # Safe mode: ensure only one Pathumma job per device at a time
            device_key = str(self.device)
            lock = _DEVICE_LOCKS.get(device_key)
            if lock is None:
                lock = asyncio.Lock()
                _DEVICE_LOCKS[device_key] = lock

            async with lock:
                loop = asyncio.get_running_loop()
                text = await loop.run_in_executor(None, self._transcribe_chunks_sync, wav)

            return {"text": text, "words": [], "error": None}

        except Exception as e:
            logger.exception(f"Pathumma transcription error: {e}")
            return {"text": "", "words": [], "error": str(e)}

        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    logger.debug("failed to unlink tmp file")

    def unload_model(self):
        try:
            if self._wf_model is not None:
                try:
                    # try move to CPU first
                    self._wf_model.to("cpu")
                except Exception:
                    pass

            self._wf_model = None
            self._processor = None
            self._model_loaded = False

            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                try:
                    torch.cuda.reset_peak_memory_stats()
                except Exception:
                    pass

            logger.info(f"Pathumma model {self.model_name} unloaded")
        except Exception:
            logger.exception("Failed unloading Pathumma model")

    def is_loaded(self) -> bool:
        return self._model_loaded and (self._wf_model is not None)


class PathummaNoiseASR(PathummaASR):
    def __init__(self, device: Optional[str] = None):
        super().__init__("PogusTheWhisper/Pathumma-whisper-th-large-v3-natural-noise-finetuned", device=device)

class ASRModelManager:
    def __init__(self, max_loaded_models: int = 1, device: Optional[str] = None):
        self.models: Dict[str, ASRModelBase] = {}
        self.max_loaded_models = max_loaded_models
        self._loaded_order: OrderedDict = OrderedDict()
        self.device = device
        self._register_models()

    def _register_models(self):
        # Create model wrappers but do NOT load heavy weights here
        self.models["typhoon"] = TyphoonASR(device=self.device)
        self.models["pathumma"] = PathummaASR(device=self.device)
        self.models["pathumma_noise"] = PathummaNoiseASR(device=self.device)
        logger.info("ASR models registered (lazy load).")

    async def ensure_model_loaded(self, model_name: str):
        if model_name not in self.models:
            raise KeyError(model_name)

        model = self.models[model_name]

        # Already loaded
        if model.is_loaded():
            # refresh LRU
            self._loaded_order.pop(model_name, None)
            self._loaded_order[model_name] = True
            return

        # Evict until we can load within max_loaded_models
        while len(self._loaded_order) >= self.max_loaded_models:
            oldest_model_name, _ = self._loaded_order.popitem(last=False)
            try:
                if oldest_model_name in self.models:
                    self.models[oldest_model_name].unload_model()
                    logger.debug(f"Evicted model {oldest_model_name} to free memory")
            except Exception:
                logger.exception(f"Failed to evict model {oldest_model_name}")
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        # load the requested model
        if hasattr(model, "ensure_loaded"):
            await model.ensure_loaded()
        else:
            model._load_model()

        # register as most recently used
        self._loaded_order[model_name] = True

    async def transcribe_with_all_models(self, audio_data: bytes) -> Dict[str, Dict[str, Any]]:
        results: Dict[str, Dict[str, Any]] = {}

        # sequential to avoid concurrent loads; if you have enough VRAM, you can parallelize
        for model_name in list(self.models.keys()):
            try:
                await self.ensure_model_loaded(model_name)
                result = await self.models[model_name].transcribe(audio_data)
                results[model_name] = result
            except Exception as e:
                logger.exception(f"Error with {model_name}: {e}")
                results[model_name] = {"text": "", "error": str(e)}
            finally:
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

        return results

    async def transcribe_batch(self, audio_batch: List[bytes], model_names: List[str] = None, auto_unload: bool = True) -> List[Dict[str, Any]]:
        if model_names is None:
            model_names = list(self.models.keys())

        batch_results = []
        try:
            for i, audio_data in enumerate(audio_batch):
                chunk_result = {"chunk_index": i, "transcriptions": {}, "processing_times_ms": {}}
                for model_name in model_names:
                    if model_name not in self.models:
                        logger.warning(f"Model {model_name} not available")
                        continue

                    start_time = time.time()
                    try:
                        await self.ensure_model_loaded(model_name)
                        result = await self.models[model_name].transcribe(audio_data)
                        processing_time = (time.time() - start_time) * 1000
                        chunk_result["transcriptions"][model_name] = result
                        chunk_result["processing_times_ms"][model_name] = processing_time
                    except Exception as e:
                        processing_time = (time.time() - start_time) * 1000
                        logger.exception(f"Error transcribing chunk {i} with {model_name}: {e}")
                        chunk_result["transcriptions"][model_name] = {"text": "", "error": str(e)}
                        chunk_result["processing_times_ms"][model_name] = processing_time

                batch_results.append(chunk_result)

                # memory management between chunks
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

                if auto_unload and i % 2 == 1:
                    self.temporarily_unload_models(model_names)

        finally:
            if auto_unload:
                self.reload_models_if_needed(model_names)

        return batch_results

    async def transcribe_chunks_parallel(self, audio_chunks: List[bytes], model_names: List[str] = None) -> List[Dict[str, Any]]:
        if model_names is None:
            model_names = list(self.models.keys())

        tasks = []
        for i, audio_data in enumerate(audio_chunks):
            task = self._transcribe_single_chunk_parallel(i, audio_data, model_names)
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        batch_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.exception(f"Error processing chunk {i}: {result}")
                batch_results.append({
                    "chunk_index": i,
                    "transcriptions": {model: {"text": "", "error": str(result)} for model in model_names},
                    "processing_times_ms": {model: 0 for model in model_names}
                })
            else:
                batch_results.append(result)

        return batch_results

    async def _transcribe_single_chunk_parallel(self, chunk_index: int, audio_data: bytes, model_names: List[str]) -> Dict[str, Any]:
        chunk_result = {"chunk_index": chunk_index, "transcriptions": {}, "processing_times_ms": {}}

        model_tasks = []
        for model_name in model_names:
            if model_name not in self.models:
                continue
            task = self._transcribe_with_model_timing(model_name, audio_data)
            model_tasks.append((model_name, task))

        model_results = await asyncio.gather(*[task for _, task in model_tasks], return_exceptions=True)

        for (model_name, _), result in zip(model_tasks, model_results):
            if isinstance(result, Exception):
                chunk_result["transcriptions"][model_name] = {"text": "", "error": str(result)}
                chunk_result["processing_times_ms"][model_name] = 0
            else:
                chunk_result["transcriptions"][model_name] = result["transcription"]
                chunk_result["processing_times_ms"][model_name] = result["processing_time_ms"]

        return chunk_result

    async def _transcribe_with_model_timing(self, model_name: str, audio_data: bytes) -> Dict[str, Any]:
        start_time = time.time()
        try:
            await self.ensure_model_loaded(model_name)
            transcription = await self.models[model_name].transcribe(audio_data)
            processing_time = (time.time() - start_time) * 1000
            return {"transcription": transcription, "processing_time_ms": processing_time}
        except Exception as e:
            processing_time = (time.time() - start_time) * 1000
            logger.exception(f"Error transcribing with timing {model_name}: {e}")
            return {"transcription": {"text": "", "error": str(e)}, "processing_time_ms": processing_time}

    def get_model(self, model_name: str) -> Optional[ASRModelBase]:
        return self.models.get(model_name)

    def clear_cache(self, aggressive: bool = False):
        try:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                if aggressive:
                    try:
                        torch.cuda.reset_peak_memory_stats()
                        torch.cuda.synchronize()
                    except Exception:
                        pass
                logger.debug("CUDA cache cleared" + (" (aggressive)" if aggressive else ""))

            for model_name, model in self.models.items():
                # try to clear pipeline caches if present
                if hasattr(model, '_model') and model._model is not None:
                    if hasattr(model._model, 'cache'):
                        try:
                            model._model.cache.clear()
                        except Exception:
                            pass

                # clear internal attributes for our transformers wrapper
                if hasattr(model, '_wf_model') and getattr(model, '_wf_model') is not None:
                    # detach past_key_values if present
                    try:
                        if hasattr(model._wf_model, 'past_key_values'):
                            model._wf_model.past_key_values = None
                    except Exception:
                        pass

                if aggressive and hasattr(model, 'unload_model'):
                    try:
                        model.unload_model()
                        logger.debug(f"Aggressive cache clear: unloaded {model_name}")
                    except Exception:
                        logger.exception(f"Failed aggressive unload for {model_name}")

            gc.collect()
            logger.debug("ASR model caches cleared" + (" (aggressive)" if aggressive else ""))
        except Exception:
            logger.exception("Failed to clear caches")

    def temporarily_unload_models(self, model_names: List[str] = None):
        if model_names is None:
            model_names = list(self.models.keys())

        for model_name in model_names:
            if model_name in self.models and hasattr(self.models[model_name], 'unload_model'):
                try:
                    self.models[model_name].unload_model()
                    logger.debug(f"Temporarily unloaded model: {model_name}")
                except Exception:
                    logger.exception(f"Failed to temporarily unload {model_name}")

        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            logger.debug(f"VRAM after temporary unload: {torch.cuda.memory_allocated() / 1024**3:.2f}GB")

    def reload_models_if_needed(self, model_names: List[str] = None):
        if model_names is None:
            model_names = list(self.models.keys())

        for model_name in model_names:
            if model_name in self.models and hasattr(self.models[model_name], 'is_loaded'):
                try:
                    if not self.models[model_name].is_loaded():
                        # synchronous reload; could schedule async if desired
                        if hasattr(self.models[model_name], 'ensure_loaded'):
                            # ensure_loaded may be async; run it in event loop if available
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                loop.create_task(self.models[model_name].ensure_loaded())
                            else:
                                loop.run_until_complete(self.models[model_name].ensure_loaded())
                        else:
                            self.models[model_name]._load_model()
                        logger.debug(f"Reloaded model: {model_name}")
                except Exception:
                    logger.exception(f"Failed to reload model {model_name}")

    def unload_models(self):
        for model_name, model in self.models.items():
            try:
                if hasattr(model, 'unload_model'):
                    model.unload_model()
                elif hasattr(model, '_model') and model._model is not None:
                    del model._model
                    model._model = None
                    logger.debug(f"Unloaded model: {model_name}")
            except Exception:
                logger.exception(f"Failed to unload model {model_name}")

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            try:
                torch.cuda.reset_peak_memory_stats()
            except Exception:
                pass

        logger.info("All ASR models unloaded from memory")

    def reload_models(self):
        try:
            self.unload_models()
            self._register_models()
            logger.info("ASR models reloaded successfully")
        except Exception:
            logger.exception("Failed to reload ASR models")
            raise

    def get_memory_usage(self) -> Dict[str, Any]:
        memory_info = {"models_loaded": {}, "gpu_memory": {}, "system_memory": {}}
        try:
            for model_name, model in self.models.items():
                memory_info["models_loaded"][model_name] = model.is_loaded() if hasattr(model, 'is_loaded') else (hasattr(model, '_model') and model._model is not None)

            if torch.cuda.is_available():
                memory_info["gpu_memory"] = {
                    "allocated_gb": torch.cuda.memory_allocated() / 1024**3,
                    "reserved_gb": torch.cuda.memory_reserved() / 1024**3,
                    "max_allocated_gb": torch.cuda.max_memory_allocated() / 1024**3,
                    "device_count": torch.cuda.device_count(),
                    "device_name": torch.cuda.get_device_name(0) if torch.cuda.device_count() > 0 else "No GPU"
                }
            else:
                memory_info["gpu_memory"] = {"message": "CUDA not available"}

            import psutil
            memory_info["system_memory"] = {
                "used_gb": psutil.virtual_memory().used / 1024**3,
                "available_gb": psutil.virtual_memory().available / 1024**3,
                "percent_used": psutil.virtual_memory().percent
            }
        except Exception:
            logger.exception("Failed to gather memory usage")
        return memory_info

    def log_memory_usage(self, context: str = ""):
        memory_info = self.get_memory_usage()
        logger.info(f"Memory Usage {context}:")
        for model_name, loaded in memory_info.get("models_loaded", {}).items():
            status = "LOADED" if loaded else "UNLOADED"
            logger.info(f"  {model_name}: {status}")
        gpu = memory_info.get("gpu_memory", {})
        if "allocated_gb" in gpu:
            logger.info(f"  GPU VRAM: {gpu['allocated_gb']:.2f}GB allocated, {gpu['reserved_gb']:.2f}GB reserved")
        sys_mem = memory_info.get("system_memory", {})
        if "used_gb" in sys_mem:
            logger.info(f"  System RAM: {sys_mem['used_gb']:.2f}GB used ({sys_mem['percent_used']:.1f}%)")

