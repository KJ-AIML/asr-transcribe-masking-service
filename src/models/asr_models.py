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
        
    def _load_model(self):
        """Load Typhoon model"""
        try:
            # Fix for Windows signal.SIGKILL issue
            import signal
            if not hasattr(signal, 'SIGKILL'):
                signal.SIGKILL = signal.SIGTERM
            
            from typhoon_asr import transcribe
            self._transcribe_fn = transcribe
            logger.info("Typhoon ASR model loaded")
        except ImportError as e:
            logger.error(f"Failed to import typhoon_asr: {e}")
            self._transcribe_fn = None
            raise
        except Exception as e:
            logger.error(f"Error loading Typhoon model: {e}")
            self._transcribe_fn = None
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

class PathummaASR(ASRModelBase):
    """Pathumma Whisper Model"""
    
    def __init__(self, model_name: str = "nectec/Pathumma-whisper-th-large-v3"):
        super().__init__(model_name)
        self.lang = "th"
        self.task = "transcribe"
        
    def _load_model(self):
        """Load Pathumma Whisper model"""
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
            
            logger.info(f"Pathumma ASR model loaded: {self.model_name}")
        except Exception as e:
            logger.error(f"Failed to load Pathumma model: {e}")
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
            except Exception as e:
                logger.error(f"Error with {model_name}: {e}")
                results[model_name] = {"text": "", "error": str(e)}
                
        return results
    
    async def transcribe_batch(self, audio_batch: List[bytes], model_names: List[str] = None) -> List[Dict[str, Any]]:
        """Transcribe a batch of audio chunks with specified models"""
        if model_names is None:
            model_names = ["typhoon", "pathumma", "pathumma_noise"]
        
        batch_results = []
        
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
            
            # Clear cache between chunks to manage memory
            if i % 3 == 0:  # Every 3 chunks
                self.clear_cache()
        
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
    
    def clear_cache(self):
        """Clear model caches and free memory"""
        try:
            # Clear CUDA cache if available
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                logger.debug("CUDA cache cleared")
            
            # Clear model caches if they have cache clearing methods
            for model_name, model in self.models.items():
                if hasattr(model, '_model') and model._model is not None:
                    # Some transformers models have cache
                    if hasattr(model._model, 'cache'):
                        model._model.cache.clear()
                        
            logger.debug("ASR model caches cleared")
            
        except Exception as e:
            logger.warning(f"Failed to clear ASR model caches: {e}")
    
    def unload_models(self):
        """Unload all models to free memory"""
        try:
            for model_name, model in self.models.items():
                if hasattr(model, '_model') and model._model is not None:
                    del model._model
                    model._model = None
                    logger.debug(f"Unloaded model: {model_name}")
            
            # Clear CUDA cache if available
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                
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