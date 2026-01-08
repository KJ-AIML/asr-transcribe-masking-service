from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
import uuid
import logging

logger = logging.getLogger(__name__)


@dataclass
class ChunkTranscription:
    """Transcription result for a single chunk"""

    chunk_index: int
    start_sec: float
    end_sec: float
    duration_sec: float

    # Transcription results from each model
    typhoon_transcript: Optional[str] = None
    pathumma_transcript: Optional[str] = None
    whisper_transcript: Optional[str] = None

    # Processing metadata
    processing_time_ms: Dict[str, float] = field(default_factory=dict)
    confidence_scores: Dict[str, float] = field(default_factory=dict)

    # Status tracking
    status: str = "pending"  # pending, processing, completed, error
    error_message: Optional[str] = None

    @property
    def has_all_transcriptions(self) -> bool:
        """Check if all 3 models have transcribed this chunk"""
        return all(
            [
                self.typhoon_transcript is not None,
                self.pathumma_transcript is not None,
                self.whisper_transcript is not None,
            ]
        )

    @property
    def completed_models(self) -> List[str]:
        """Get list of models that have completed transcription"""
        completed = []
        if self.typhoon_transcript:
            completed.append("typhoon")
        if self.pathumma_transcript:
            completed.append("pathumma")
        if self.whisper_transcript:
            completed.append("whisper")
        return completed

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "chunk_index": self.chunk_index,
            "start_sec": self.start_sec,
            "end_sec": self.end_sec,
            "duration_sec": self.duration_sec,
            "typhoon_transcript": self.typhoon_transcript,
            "pathumma_transcript": self.pathumma_transcript,
            "whisper_transcript": self.whisper_transcript,
            "processing_time_ms": self.processing_time_ms,
            "confidence_scores": self.confidence_scores,
            "status": self.status,
            "error_message": self.error_message,
            "has_all_transcriptions": self.has_all_transcriptions,
            "completed_models": self.completed_models,
        }


@dataclass
class TranscriptionSession:
    """Complete transcription session for a WAV file"""

    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    filename: str = ""
    file_size_bytes: int = 0
    total_duration_sec: float = 0.0
    total_chunks: int = 0
    chunk_duration_sec: int = 30
    overlap_sec: int = 3

    # Transcription results
    chunk_transcriptions: List[ChunkTranscription] = field(default_factory=list)

    # Session metadata
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Processing status
    status: str = "created"  # created, processing, completed, error
    current_model: Optional[str] = None
    current_chunk: int = 0

    # Performance metrics
    total_processing_time_ms: float = 0.0
    model_processing_times: Dict[str, float] = field(default_factory=dict)

    @property
    def progress_percentage(self) -> float:
        """Calculate transcription progress"""
        if not self.chunk_transcriptions:
            return 0.0
        completed_chunks = sum(
            1 for ct in self.chunk_transcriptions if ct.has_all_transcriptions
        )
        return (completed_chunks / len(self.chunk_transcriptions)) * 100

    @property
    def is_complete(self) -> bool:
        """Check if all chunks have all transcriptions"""
        return all(ct.has_all_transcriptions for ct in self.chunk_transcriptions)

    @property
    def summary_stats(self) -> Dict[str, Any]:
        """Get summary statistics of the session"""
        if not self.chunk_transcriptions:
            return {}

        total_models = len(self.chunk_transcriptions) * 3  # 3 models per chunk
        completed_models = sum(
            len(ct.completed_models) for ct in self.chunk_transcriptions
        )

        return {
            "total_chunks": len(self.chunk_transcriptions),
            "completed_chunks": sum(
                1 for ct in self.chunk_transcriptions if ct.has_all_transcriptions
            ),
            "total_model_transcriptions": total_models,
            "completed_model_transcriptions": completed_models,
            "progress_percentage": self.progress_percentage,
            "models_used": ["typhoon", "pathumma", "pathumma_noise"],
            "session_duration_sec": self._calculate_session_duration(),
        }

    def _calculate_session_duration(self) -> float:
        """Calculate session duration safely"""
        try:
            end_time = self.completed_at or datetime.now()
            start_time = self.started_at or self.created_at

            if isinstance(end_time, datetime) and isinstance(start_time, datetime):
                time_diff = end_time - start_time
                if hasattr(time_diff, "total_seconds"):
                    return time_diff.total_seconds()
                else:
                    return 0.0
            else:
                return 0.0
        except Exception:
            return 0.0

    def get_chunk_transcription(self, chunk_index: int) -> Optional[ChunkTranscription]:
        """Get transcription for specific chunk"""
        for ct in self.chunk_transcriptions:
            if ct.chunk_index == chunk_index:
                return ct
        return None

    def add_chunk_transcription(self, chunk_transcription: ChunkTranscription):
        """Add or update chunk transcription"""
        # Remove existing if present
        self.chunk_transcriptions = [
            ct
            for ct in self.chunk_transcriptions
            if ct.chunk_index != chunk_transcription.chunk_index
        ]
        # Add new
        self.chunk_transcriptions.append(chunk_transcription)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "session_id": self.session_id,
            "filename": self.filename,
            "file_size_bytes": self.file_size_bytes,
            "total_duration_sec": self.total_duration_sec,
            "total_chunks": self.total_chunks,
            "chunk_duration_sec": self.chunk_duration_sec,
            "overlap_sec": self.overlap_sec,
            "chunk_transcriptions": [ct.to_dict() for ct in self.chunk_transcriptions],
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "status": self.status,
            "current_model": self.current_model,
            "current_chunk": self.current_chunk,
            "total_processing_time_ms": self.total_processing_time_ms,
            "model_processing_times": self.model_processing_times,
            "progress_percentage": self.progress_percentage,
            "is_complete": self.is_complete,
            "summary_stats": self.summary_stats,
        }


class TranscriptionMemoryManager:
    """In-memory manager for transcription sessions"""

    def __init__(self, max_completed_sessions: int = 5):
        self.sessions: Dict[str, TranscriptionSession] = {}
        self.max_completed_sessions = max_completed_sessions

    def create_session(
        self,
        filename: str,
        file_size_bytes: int,
        total_duration_sec: float,
        total_chunks: int,
        chunk_duration_sec: int = 30,
        overlap_sec: int = 3,
    ) -> TranscriptionSession:
        """Create new transcription session"""
        session = TranscriptionSession(
            filename=filename,
            file_size_bytes=file_size_bytes,
            total_duration_sec=total_duration_sec,
            total_chunks=total_chunks,
            chunk_duration_sec=chunk_duration_sec,
            overlap_sec=overlap_sec,
        )

        # Initialize chunk transcriptions
        for i in range(total_chunks):
            start_sec = i * (chunk_duration_sec - overlap_sec)
            end_sec = min(start_sec + chunk_duration_sec, total_duration_sec)

            chunk_transcription = ChunkTranscription(
                chunk_index=i,
                start_sec=start_sec,
                end_sec=end_sec,
                duration_sec=end_sec - start_sec,
            )
            session.chunk_transcriptions.append(chunk_transcription)

        self.sessions[session.session_id] = session

        # Clean up old sessions if needed
        self._cleanup_old_sessions()

        return session

    def get_session(self, session_id: str) -> Optional[TranscriptionSession]:
        """Get session by ID"""
        return self.sessions.get(session_id)

    def update_session(self, session_id: str, **kwargs):
        """Update session attributes"""
        if session_id in self.sessions:
            session = self.sessions[session_id]
            for key, value in kwargs.items():
                if hasattr(session, key):
                    setattr(session, key, value)

    def delete_session(self, session_id: str) -> bool:
        """Delete session"""
        if session_id in self.sessions:
            del self.sessions[session_id]
            return True
        return False

    def list_sessions(self) -> List[Dict[str, Any]]:
        """List all sessions"""
        return [session.to_dict() for session in self.sessions.values()]

    def _cleanup_old_sessions(self):
        """Remove completed sessions if exceeding max_completed_sessions"""
        # หา sessions ที่เสร็จแล้ว (completed หรือ error)
        completed_sessions = [
            (session_id, session)
            for session_id, session in self.sessions.items()
            if session.status in ["completed", "error"]
        ]

        # ถ้าจำนวน session ที่เสร็จแล้วเกินขีดจำกัด
        if len(completed_sessions) > self.max_completed_sessions:
            # เรียงตามเวลาเสร็จ (เก่าสุดอยู่ก่อน)
            completed_sessions.sort(key=lambda x: x[1].completed_at or x[1].created_at)

            # คำนวณว่าต้องลบกี่ sessions
            sessions_to_remove = len(completed_sessions) - self.max_completed_sessions

            for i in range(sessions_to_remove):
                session_id = completed_sessions[i][0]
                logger.info(f"Cleaning up completed session: {session_id}")
                del self.sessions[session_id]


# Global instance
transcription_memory = TranscriptionMemoryManager()
