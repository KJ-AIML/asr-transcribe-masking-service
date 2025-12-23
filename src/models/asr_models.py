from typing import Dict, Any, Optional, List
import torch
import time
import asyncio
from transformers import pipeline
from src.config.logs_config import get_logger

logger = get_logger(__name__)

class ASRModelBase:
    """Base class for ASR models"""
    
    def __init__(self, model_name: str, device: Optional[str] = None):
        self.model_name = model_name
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.torch_dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32
        self._model = None
        
    def _load_model(self):
        """Load model - lazy loading"""
        raise NotImplementedError
        
    async def transcribe(self, audio_data: bytes) -> Dict[str, Any]:
        """Transcribe audio bytes to text"""
        raise NotImplementedError

class TyphoonASR(ASRModelBase):
    """Typhoon ASR Model"""
    
    def __init__(self):
        super().__init__("typhoon")
        self._transcribe_fn = None
        self._model_loaded = False
        
    def _load_model(self):
        """Load Typhoon model"""
        if self._model_loaded:
            return
            
        try:
            # Fix for Windows signal.SIGKILL issue
            import signal
            if not hasattr(signal, 'SIGKILL'):
                signal.SIGKILL = signal.SIGTERM
            
            from typhoon_asr import transcribe
            self._transcribe_fn = transcribe
            self._model_loaded = True
            logger.info("Typhoon ASR model loaded")
        except ImportError as e:
            logger.error(f"Failed to import typhoon_asr: {e}")
            self._transcribe_fn = None
            self._model_loaded = False
            raise
        except Exception as e:
            logger.error(f"Error loading Typhoon model: {e}")
            self._transcribe_fn = None
            self._model_loaded = False
            raise
            
    async def transcribe(self, audio_data: bytes) -> Dict[str, Any]:
        """Transcribe audio bytes using Typhoon"""
        if self._transcribe_fn is None:
            try:
                self._load_model()
            except Exception as e:
                logger.error(f"Failed to load Typhoon model: {e}")
                return {"text": "", "error": f"Typhoon model unavailable: {str(e)}"}
        
        if self._transcribe_fn is None:
            return {"text": "", "error": "Typhoon model not available"}
        
        import tempfile
        import os
        
        try:
            # Create temporary file for Typhoon ASR (it expects file path, not bytes)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                temp_file.write(audio_data)
                temp_file_path = temp_file.name
            
            try:
                # Transcribe using temp file path
                result = self._transcribe_fn(temp_file_path)
                
                # Ensure result is a string
                if isinstance(result, dict):
                    text = result.get("text", str(result))
                elif isinstance(result, str):
                    text = result
                else:
                    text = str(result)
                    
                return {"text": text, "error": None}
            finally:
                # Clean up temp file
                try:
                    os.unlink(temp_file_path)
                except Exception as cleanup_error:
                    logger.warning(f"Failed to clean up temp file {temp_file_path}: {cleanup_error}")
                    
        except Exception as e:
            logger.error(f"Typhoon transcription error: {e}")
            return {"text": "", "error": str(e)}
    
    def unload_model(self):
        """Unload Typhoon model from memory"""
        try:
            self._transcribe_fn = None
            self._model_loaded = False
            
            # Clear typhoon_asr module cache if possible
            import sys
            modules_to_remove = [mod for mod in sys.modules.keys() if 'typhoon_asr' in mod]
            for mod in modules_to_remove:
                if mod in sys.modules:
                    del sys.modules[mod]
            
            # Clear GPU cache if available
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                logger.debug("Typhoon model: CUDA cache cleared")
            
            logger.info("Typhoon ASR model unloaded from memory")
            
        except Exception as e:
            logger.warning(f"Failed to unload Typhoon model: {e}")
    
    def is_loaded(self) -> bool:
        """Check if model is loaded"""
        return self._model_loaded and self._transcribe_fn is not None

class PathummaASR(ASRModelBase):
    """Pathumma Whisper Model"""
    
    def __init__(self, model_name: str = "nectec/Pathumma-whisper-th-large-v3"):
        super().__init__(model_name)
        self.lang = "th"
        self.task = "transcribe"
        self._model_loaded = False
        
    def _load_model(self):
        """Load Pathumma Whisper model"""
        if self._model_loaded and self._model is not None:
            return
            
        try:
            self._model = pipeline(
                task="automatic-speech-recognition",
                model=self.model_name,
                return_timestamps="word",
                torch_dtype=self.torch_dtype,
                device=self.device,
            )
            
            # Configure for Thai
            self._model.model.config.forced_decoder_ids = self._model.tokenizer.get_decoder_prompt_ids(
                language=self.lang,
                task=self.task,
            )
            
            self._model_loaded = True
            logger.info(f"Pathumma ASR model loaded: {self.model_name}")
        except Exception as e:
            logger.error(f"Failed to load Pathumma model: {e}")
            self._model_loaded = False
            raise
            
    async def transcribe(self, audio_data: bytes) -> Dict[str, Any]:
        """Transcribe audio bytes using Pathumma Whisper"""
        if self._model is None:
            self._load_model()
            
        try:
            # Convert bytes to temporary file for processing
            import tempfile
            import os
            
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                temp_file.write(audio_data)
                temp_file_path = temp_file.name
            
            try:
                # Transcribe using temp file path
                out = self._model(temp_file_path)
                
                # Extract text and word-level timestamps
                if isinstance(out, dict):
                    text = out.get("text", "")
                    
                    # Extract word-level timestamps if available
                    words = []
                    chunks = out.get("chunks", [])
                    
                    for chunk in chunks:
                        if isinstance(chunk, dict):
                            chunk_text = chunk.get("text", "")
                            timestamp = chunk.get("timestamp", None)
                            
                            if timestamp and len(timestamp) == 2:
                                start_time = timestamp[0] if timestamp[0] is not None else 0.0
                                end_time = timestamp[1] if timestamp[1] is not None else start_time + 0.5
                                
                                # Split chunk text into words (simple approach)
                                words_in_chunk = chunk_text.strip().split()
                                if words_in_chunk:
                                    # Distribute timestamps across words
                                    word_duration = (end_time - start_time) / len(words_in_chunk)
                                    for i, word in enumerate(words_in_chunk):
                                        word_start = start_time + (i * word_duration)
                                        word_end = word_start + word_duration
                                        words.append({
                                            "word": word,
                                            "start": word_start,
                                            "end": word_end,
                                            "confidence": 0.95
                                        })
                    
                    return {
                        "text": text,
                        "words": words,
                        "error": None
                    }
                else:
                    # Fallback for non-dict results
                    text = str(out)
                    return {"text": text, "words": [], "error": None}
                    
            finally:
                # Clean up temp file
                try:
                    os.unlink(temp_file_path)
                except Exception as cleanup_error:
                    logger.warning(f"Failed to clean up temp file {temp_file_path}: {cleanup_error}")
                    
        except Exception as e:
            logger.error(f"Pathumma transcription error: {e}")
            return {"text": "", "words": [], "error": str(e)}
    
    def unload_model(self):
        """Unload Pathumma Whisper model from memory"""
        try:
            if self._model is not None:
                # Move model to CPU first to free VRAM
                self._model.model.cpu()
                self._model.device = "cpu"
                
                # Clear pipeline
                del self._model
                self._model = None
            
            self._model_loaded = False
            
            # Aggressive GPU memory cleanup
            import torch
            if torch.cuda.is_available():
                # Clear CUDA cache
                torch.cuda.empty_cache()
                
                # Reset memory stats
                torch.cuda.reset_peak_memory_stats()
                
                # Force garbage collection
                import gc
                gc.collect()
                
                logger.debug(f"Pathumma model: VRAM freed. Current VRAM: {torch.cuda.memory_allocated() / 1024**3:.2f}GB")
            
            logger.info("Pathumma Whisper model unloaded from memory")
            
        except Exception as e:
            logger.warning(f"Failed to unload Pathumma model: {e}")
    
    def is_loaded(self) -> bool:
        """Check if model is loaded"""
        return self._model_loaded and self._model is not None

class PathummaNoiseASR(PathummaASR):
    """Pathumma Whisper with Noise Finetuning"""
    
    def __init__(self):
        super().__init__("PogusTheWhisper/Pathumma-whisper-th-large-v3-natural-noise-finetuned")

class ASRModelManager:
    """Manager for all ASR models with memory management"""
    
    def __init__(self):
        self.models = {}
        self._load_models()
        
    def _load_models(self):
        """Load all ASR models"""
        try:
            self.models["typhoon"] = TyphoonASR()
            self.models["pathumma"] = PathummaASR()
            self.models["pathumma_noise"] = PathummaNoiseASR()
            logger.info("All ASR models loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load ASR models: {e}")
            
    async def transcribe_with_all_models(self, audio_data: bytes) -> Dict[str, Dict[str, Any]]:
        """Transcribe audio with all available models"""
        results = {}
        
        for model_name, model in self.models.items():
            try:
                result = await model.transcribe(audio_data)
                results[model_name] = result
                
                # Aggressive memory cleanup after each model transcription
                self.clear_cache()
                
                # Force garbage collection
                import gc
                gc.collect()
            except Exception as e:
                logger.error(f"Error with {model_name}: {e}")
                results[model_name] = {"text": "", "error": str(e)}
                
        return results
    
    async def transcribe_batch(self, audio_batch: List[bytes], model_names: List[str] = None, auto_unload: bool = True) -> List[Dict[str, Any]]:
        """Transcribe a batch of audio chunks with specified models"""
        if model_names is None:
            model_names = ["typhoon", "pathumma", "pathumma_noise"]
        
        batch_results = []
        
        try:
            for i, audio_data in enumerate(audio_batch):
                chunk_result = {
                    "chunk_index": i,
                    "transcriptions": {},
                    "processing_times_ms": {}
                }
                
                # Transcribe with each model
                for model_name in model_names:
                    if model_name not in self.models:
                        logger.warning(f"Model {model_name} not available")
                        continue
                    
                    start_time = time.time()
                    try:
                        result = await self.models[model_name].transcribe(audio_data)
                        processing_time = (time.time() - start_time) * 1000
                        
                        chunk_result["transcriptions"][model_name] = result
                        chunk_result["processing_times_ms"][model_name] = processing_time
                        
                        logger.debug(f"Chunk {i} - {model_name}: {processing_time:.1f}ms")
                        
                    except Exception as e:
                        processing_time = (time.time() - start_time) * 1000
                        logger.error(f"Error transcribing chunk {i} with {model_name}: {e}")
                        chunk_result["transcriptions"][model_name] = {"text": "", "error": str(e)}
                        chunk_result["processing_times_ms"][model_name] = processing_time
                
                batch_results.append(chunk_result)
                
                # Aggressive memory management - clean up every chunk for VRAM optimization
                self.clear_cache()
                
                # Optional: Unload models temporarily if memory is critical
                if auto_unload and i % 2 == 1:  # Every 2 chunks
                    self.temporarily_unload_models(model_names)
        
        finally:
            # Ensure models are reloaded after batch processing
            if auto_unload:
                self.reload_models_if_needed(model_names)
        
        return batch_results
    
    async def transcribe_chunks_parallel(self, audio_chunks: List[bytes], model_names: List[str] = None) -> List[Dict[str, Any]]:
        """Transcribe chunks in parallel for better performance"""
        if model_names is None:
            model_names = ["typhoon", "pathumma", "pathumma_noise"]
        
        # Create tasks for parallel processing
        tasks = []
        for i, audio_data in enumerate(audio_chunks):
            task = self._transcribe_single_chunk_parallel(i, audio_data, model_names)
            tasks.append(task)
        
        # Execute all tasks in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        batch_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Error processing chunk {i}: {result}")
                batch_results.append({
                    "chunk_index": i,
                    "transcriptions": {model: {"text": "", "error": str(result)} for model in model_names},
                    "processing_times_ms": {model: 0 for model in model_names}
                })
            else:
                batch_results.append(result)
        
        return batch_results
    
    async def _transcribe_single_chunk_parallel(self, chunk_index: int, audio_data: bytes, model_names: List[str]) -> Dict[str, Any]:
        """Transcribe a single chunk with all models in parallel"""
        chunk_result = {
            "chunk_index": chunk_index,
            "transcriptions": {},
            "processing_times_ms": {}
        }
        
        # Create parallel tasks for each model
        model_tasks = []
        for model_name in model_names:
            if model_name not in self.models:
                continue
            task = self._transcribe_with_model_timing(model_name, audio_data)
            model_tasks.append((model_name, task))
        
        # Execute model tasks in parallel
        model_results = await asyncio.gather(*[task for _, task in model_tasks], return_exceptions=True)
        
        # Process results
        for (model_name, _), result in zip(model_tasks, model_results):
            if isinstance(result, Exception):
                chunk_result["transcriptions"][model_name] = {"text": "", "error": str(result)}
                chunk_result["processing_times_ms"][model_name] = 0
            else:
                chunk_result["transcriptions"][model_name] = result["transcription"]
                chunk_result["processing_times_ms"][model_name] = result["processing_time_ms"]
        
        return chunk_result
    
    async def _transcribe_with_model_timing(self, model_name: str, audio_data: bytes) -> Dict[str, Any]:
        """Transcribe with timing information"""
        start_time = time.time()
        try:
            transcription = await self.models[model_name].transcribe(audio_data)
            processing_time = (time.time() - start_time) * 1000
            return {
                "transcription": transcription,
                "processing_time_ms": processing_time
            }
        except Exception as e:
            processing_time = (time.time() - start_time) * 1000
            return {
                "transcription": {"text": "", "error": str(e)},
                "processing_time_ms": processing_time
            }
        
    def get_model(self, model_name: str) -> Optional[ASRModelBase]:
        """Get specific model by name"""
        return self.models.get(model_name)
    
    def clear_cache(self, aggressive: bool = False):
        """Clear model caches and free memory
        
        Args:
            aggressive: If True, performs more aggressive cache clearing including model unloading
        """
        try:
            # Clear CUDA cache if available
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                if aggressive:
                    torch.cuda.reset_peak_memory_stats()
                    # Force synchronization
                    torch.cuda.synchronize()
                logger.debug("CUDA cache cleared" + (" (aggressive)" if aggressive else ""))
            
            # Clear model caches if they have cache clearing methods
            for model_name, model in self.models.items():
                if hasattr(model, '_model') and model._model is not None:
                    # Clear transformers model cache
                    if hasattr(model._model, 'cache'):
                        model._model.cache.clear()
                    
                    # Clear generation cache if available
                    if hasattr(model._model, 'model') and hasattr(model._model.model, 'past_key_values'):
                        model._model.model.past_key_values = None
                    
                    # For aggressive mode, temporarily unload models to free more memory
                    if aggressive and hasattr(model, 'unload_model'):
                        model.unload_model()
                        logger.debug(f"Aggressive cache clear: unloaded {model_name}")
                        
            # Force garbage collection
            import gc
            gc.collect()
            
            logger.debug(f"ASR model caches cleared" + (" (aggressive mode)" if aggressive else ""))
            
        except Exception as e:
            logger.warning(f"Failed to clear ASR model caches: {e}")
    
    def temporarily_unload_models(self, model_names: List[str] = None):
        """Temporarily unload models to free VRAM during processing"""
        if model_names is None:
            model_names = ["typhoon", "pathumma", "pathumma_noise"]
            
        try:
            for model_name in model_names:
                if model_name in self.models and hasattr(self.models[model_name], 'unload_model'):
                    self.models[model_name].unload_model()
                    logger.debug(f"Temporarily unloaded model: {model_name}")
            
            # Force garbage collection
            import gc
            gc.collect()
            
            # Clear VRAM
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                logger.debug(f"VRAM after temporary unload: {torch.cuda.memory_allocated() / 1024**3:.2f}GB")
                
        except Exception as e:
            logger.warning(f"Failed to temporarily unload models: {e}")
    
    def reload_models_if_needed(self, model_names: List[str] = None):
        """Reload models if they were temporarily unloaded"""
        if model_names is None:
            model_names = ["typhoon", "pathumma", "pathumma_noise"]
            
        try:
            for model_name in model_names:
                if model_name in self.models and hasattr(self.models[model_name], 'is_loaded'):
                    if not self.models[model_name].is_loaded():
                        self.models[model_name]._load_model()
                        logger.debug(f"Reloaded model: {model_name}")
                        
        except Exception as e:
            logger.warning(f"Failed to reload models: {e}")
    
    def unload_models(self):
        """Unload all models to free memory"""
        try:
            for model_name, model in self.models.items():
                if hasattr(model, 'unload_model'):
                    model.unload_model()
                elif hasattr(model, '_model') and model._model is not None:
                    del model._model
                    model._model = None
                    logger.debug(f"Unloaded model: {model_name}")
            
            # Clear CUDA cache if available
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.reset_peak_memory_stats()
                
            logger.info("All ASR models unloaded from memory")
            
        except Exception as e:
            logger.warning(f"Failed to unload ASR models: {e}")
    
    def reload_models(self):
        """Reload all models after unloading"""
        try:
            self.unload_models()
            self._load_models()
            logger.info("ASR models reloaded successfully")
        except Exception as e:
            logger.error(f"Failed to reload ASR models: {e}")
            raise
    
    def get_memory_usage(self) -> Dict[str, Any]:
        """Get current memory usage statistics"""
        memory_info = {
            "models_loaded": {},
            "gpu_memory": {}
        }
        
        try:
            # Check model loading status
            for model_name, model in self.models.items():
                if hasattr(model, 'is_loaded'):
                    memory_info["models_loaded"][model_name] = model.is_loaded()
                else:
                    memory_info["models_loaded"][model_name] = hasattr(model, '_model') and model._model is not None
            
            # GPU memory info
            import torch
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
            
            # System memory info
            import psutil
            memory_info["system_memory"] = {
                "used_gb": psutil.virtual_memory().used / 1024**3,
                "available_gb": psutil.virtual_memory().available / 1024**3,
                "percent_used": psutil.virtual_memory().percent
            }
            
        except Exception as e:
            logger.warning(f"Failed to get memory usage: {e}")
            memory_info["error"] = str(e)
        
        return memory_info
    
    def log_memory_usage(self, context: str = ""):
        """Log current memory usage"""
        memory_info = self.get_memory_usage()
        
        logger.info(f"Memory Usage {context}:")
        for model_name, loaded in memory_info["models_loaded"].items():
            status = "LOADED" if loaded else "UNLOADED"
            logger.info(f"  {model_name}: {status}")
        
        if "allocated_gb" in memory_info["gpu_memory"]:
            gpu_mem = memory_info["gpu_memory"]
            logger.info(f"  GPU VRAM: {gpu_mem['allocated_gb']:.2f}GB allocated, {gpu_mem['reserved_gb']:.2f}GB reserved")
            
        if "used_gb" in memory_info.get("system_memory", {}):
            sys_mem = memory_info["system_memory"]
            logger.info(f"  System RAM: {sys_mem['used_gb']:.2f}GB used ({sys_mem['percent_used']:.1f}%)")