"""
Model Adapter for handling different ASR models (Typhoon, Pathumma, Pathumma_noise)
Handles the differences between NeMo (Typhoon) and Whisper (Pathumma) models
"""
from typing import Dict, Any, List
from abc import ABC, abstractmethod
from src.config.logs_config import get_logger

logger = get_logger(__name__)


class BaseTranscriptionAdapter(ABC):
    """Base class for transcription adapters"""
    
    @abstractmethod
    async def transcribe(self, audio_path: str, language: str = "th") -> Dict[str, Any]:
        """Transcribe audio and return word-level results"""
        pass


class TyphoonAdapter(BaseTranscriptionAdapter):
    """
    Adapter for Typhoon model (NeMo-based)
    Note: Typhoon doesn't provide word-level timestamps natively
    """
    
    def __init__(self, asr_manager: Any):
        self.model_name = "typhoon"
        self.asr_manager = asr_manager
        
    async def transcribe(self, audio_path: str, language: str = "th") -> Dict[str, Any]:
        """
        Transcribe with Typhoon model using ASRModelManager
        Returns segment-level results (no word timestamps)
        """
        logger.info(f"Transcribing with Typhoon model: {audio_path}")
        
        try:
            # Read audio file
            with open(audio_path, 'rb') as f:
                audio_data = f.read()
            
            # Get model from ASRManager
            model = self.asr_manager.get_model(self.model_name)
            if not model:
                raise ValueError(f"Model {self.model_name} not available")
            
            # Transcribe using ASRModelManager
            result = await model.transcribe(audio_data)
            
            if result.get("error"):
                raise Exception(f"Transcription error: {result['error']}")
            
            # Typhoon doesn't provide word-level timestamps
            # Calculate actual duration and create a single segment
            duration = self._calculate_audio_duration(audio_data)
            
            return {
                "words": [],
                "segments": [
                    {
                        "start": 0.0,
                        "end": duration,
                        "text": result["text"],
                        "confidence": 0.85
                    }
                ],
                "language": language,
                "duration": duration,
                "model": self.model_name,
                "text": result["text"],
                "note": "Word-level timestamps not available for Typhoon model"
            }
            
        except Exception as e:
            logger.error(f"Error in Typhoon transcription: {e}")
            raise
    
    def _calculate_audio_duration(self, audio_data: bytes) -> float:
        """Calculate audio duration from bytes"""
        try:
            import io
            import soundfile as sf
            
            buffer = io.BytesIO(audio_data)
            info = sf.info(buffer)
            return info.duration
        except Exception as e:
            logger.warning(f"Failed to calculate audio duration: {e}")
            return 0.0


class WhisperAdapter(BaseTranscriptionAdapter):
    """
    Adapter for Whisper-based models (Pathumma, Pathumma_noise)
    Provides word-level timestamps using ASRModelManager
    """
    
    def __init__(self, model_name: str, asr_manager: Any):
        self.model_name = model_name
        self.asr_manager = asr_manager
        
    async def transcribe(self, audio_path: str, language: str = "th") -> Dict[str, Any]:
        """
        Transcribe with Whisper model (Pathumma/Pathumma_noise)
        Returns word-level timestamps
        """
        logger.info(f"Transcribing with {self.model_name} model: {audio_path}")
        
        try:
            # Read audio file
            with open(audio_path, 'rb') as f:
                audio_data = f.read()
            
            # Get model from ASRManager
            model = self.asr_manager.get_model(self.model_name)
            if not model:
                raise ValueError(f"Model {self.model_name} not available")
            
            result = await model.transcribe(audio_data)

            if result.get("error"):
                raise Exception(f"Transcription error: {result['error']}")

            duration = self._calculate_audio_duration(audio_data)

            words = result.get("words", [])

            if not words:
                words = self._create_word_timestamps(result["text"], duration)
            
            return {
                "words": words,
                "segments": self._build_segments_from_words(words),
                "language": language,
                "duration": duration,
                "model": self.model_name,
                "text": result.get("text", "")
            }
            
        except Exception as e:
            logger.error(f"Error in {self.model_name} transcription: {e}")
            raise
    
    def _create_word_timestamps(self, text: str, duration: float) -> List[Dict[str, Any]]:
        """
        Fallback method to create word-level timestamps from text
        Only used when model doesn't provide word-level timestamps
        """
        # This is a fallback - in production, word timestamps should come from model
        words = []
        
        # Simple word splitting and timestamp distribution
        # This is a basic fallback and should be improved with actual ASR word timestamps
        word_list = text.strip().split()
        if not word_list:
            return words
            
        total_duration = duration if duration and duration > 0 else 1.0
        word_duration = total_duration / len(word_list)
        
        for i, word in enumerate(word_list):
            start_time = i * word_duration
            end_time = (i + 1) * word_duration
            words.append({
                "word": word,
                "start": start_time,
                "end": end_time,
                "probability": 0.85  # Default confidence for fallback
            })
        
        return words
    
    def _calculate_audio_duration(self, audio_data: bytes) -> float:
        """Calculate audio duration from bytes"""
        try:
            import io
            import soundfile as sf
            
            buffer = io.BytesIO(audio_data)
            info = sf.info(buffer)
            return info.duration
        except Exception as e:
            logger.warning(f"Failed to calculate audio duration: {e}")
            return 0.0
    
    def _build_segments_from_words(self, words: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Build segments from word-level timestamps"""
        if not words:
            return []
        
        segments = []
        current_segment = None
        
        for word in words:
            word_start = word.get("start", 0)
            word_end = word.get("end", word_start + 0.5)
            word_text = word.get("word", "")
            
            # Start new segment if needed (gap > 1 second or first word)
            if (current_segment is None or 
                word_start - current_segment["end"] > 1.0):
                
                # Save previous segment
                if current_segment:
                    segments.append(current_segment)
                
                # Start new segment
                current_segment = {
                    "start": word_start,
                    "end": word_end,
                    "text": word_text
                }
            else:
                # Continue current segment
                current_segment["end"] = word_end
                current_segment["text"] += " " + word_text
        
        # Add final segment
        if current_segment:
            segments.append(current_segment)
        
        return segments


class TranscriptionModelAdapter:
    """
    Factory class for creating appropriate transcription adapters
    """
    
    def __init__(self, model_manager=None):
        self.adapters = {}
        self.model_manager = model_manager
        
    def register_adapter(self, model_name: str, adapter: BaseTranscriptionAdapter):
        """Register a model adapter"""
        self.adapters[model_name] = adapter
        logger.info(f"Registered adapter for model: {model_name}")
        
    def get_adapter(self, model_name: str) -> BaseTranscriptionAdapter:
        """Get adapter for a model name"""
        if model_name not in self.adapters:
            raise ValueError(f"No adapter registered for model: {model_name}")
        return self.adapters[model_name]
    
    async def transcribe_with_model(self, audio_path: str, model_name: str, language: str = "th") -> Dict[str, Any]:
        """
        Transcribe audio with specified model
        
        Args:
            audio_path: Path to audio file
            model_name: Model name (typhoon, pathumma, pathumma_noise)
            language: Language code
            
        Returns:
            Dict with transcription results
        """
        logger.info(f"Transcribing with model: {model_name}")
        
        adapter = self.get_adapter(model_name)
        result = await adapter.transcribe(audio_path, language)
        
        logger.info(f"Transcription completed with {model_name}")
        return result


# Global adapter instance
transcription_adapter = TranscriptionModelAdapter()

# Global ASR manager instance (will be set during initialization)
asr_manager = None

def initialize_adapters(asr_model_manager: Any):
    """Initialize and register all model adapters with ASRModelManager"""
    global asr_manager
    asr_manager = asr_model_manager
    
    # Register Typhoon adapter
    transcription_adapter.register_adapter("typhoon", TyphoonAdapter(asr_manager))
    
    # Register Pathumma adapters
    transcription_adapter.register_adapter("pathumma", WhisperAdapter("pathumma", asr_manager))
    transcription_adapter.register_adapter("pathumma_noise", WhisperAdapter("pathumma_noise", asr_manager))
    
    logger.info("All transcription adapters initialized with ASRModelManager")
