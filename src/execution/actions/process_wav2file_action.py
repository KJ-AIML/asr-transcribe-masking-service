import asyncio
import gc
import os
import time
import tempfile
import multiprocessing as mp
from datetime import datetime
from typing import Any, Dict, List

import psutil
import torch

from src.config.logs_config import get_logger
from src.execution.actions.process_choose_model_action import ProcessChooseModelAction
from src.execution.actions.process_compare_chunk_wav_files_action import (
    ProcessCompareChunkWavFilesAction,
)
from src.models.asr_models import ASRModelManager
from src.models.transcription_models import ChunkTranscription, transcription_memory
from src.models.transcription_model_adapter import (
    TranscriptionModelAdapter,
    TyphoonAdapter,
    WhisperAdapter,
) 
from src.utils.audio.chunk_wav_audio import process_chunks_in_batches

logger = get_logger(__name__)

def _mp_worker_transcribe_chunk(
    chunk_bytes: bytes,
    chunk_index: int,
    model_names: List[str],
    device: str,
    result_queue: mp.Queue,
) -> None:
    """Multiprocessing worker function for transcribing a single chunk"""
    import asyncio
    
    start_time = time.time()
    
    try:
        torch.cuda.set_device(device)
        
        asr_manager = ASRModelManager(device=device)
        adapter = TranscriptionModelAdapter()
        adapter.register_adapter("typhoon", TyphoonAdapter(asr_manager))
        adapter.register_adapter("pathumma", WhisperAdapter("pathumma", asr_manager))
        adapter.register_adapter("pathumma_noise", WhisperAdapter("pathumma_noise", asr_manager))
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp.write(chunk_bytes)
            audio_path = tmp.name
        
        try:
            transcriptions = {}
            processing_times = {}
            
            for model_name in model_names:
                model_start = time.time()
                
                result = asyncio.run(adapter.transcribe_with_model(
                    audio_path=audio_path,
                    model_name=model_name,
                    language="th",
                ))
                
                transcriptions[model_name] = {"text": result.get("text", "")}
                processing_times[model_name] = (time.time() - model_start) * 1000
            
            result_queue.put((chunk_index, transcriptions, processing_times, None))
            
        finally:
            if os.path.exists(audio_path):
                os.unlink(audio_path)
            
    except Exception as e:
        result_queue.put((chunk_index, {}, {}, str(e)))


class ProcessWav2FileAction:
    def __init__(self):
        self.max_memory_mb = 2048
        self.process = psutil.Process(os.getpid())
        self.asr_manager = ASRModelManager()
        self.compare_action = ProcessCompareChunkWavFilesAction()
        self.choose_model_action = ProcessChooseModelAction()
        self.max_concurrent_chunks = 9
        self.max_retries = 3
        
        # Set multiprocessing start method for CUDA compatibility
        try:
            mp.set_start_method("spawn", force=True)
            logger.info("Multiprocessing start method set to 'spawn'")
        except RuntimeError as e:
            logger.debug(f"Multiprocessing start method already set: {e}")


    async def _process_chunk_batch_with_transcription(
        self,
        chunk_bytes_list: List[bytes],
        chunk_meta_list: List[Dict[str, Any]],
        session_id: str,
    ) -> List[Dict[str, Any]]:
        """Process a batch of audio chunks with transcription using multiprocessing"""
        self._check_memory_usage()
        batch_results = []
        
        # Detect available GPUs
        gpu_count = torch.cuda.device_count() if torch.cuda.is_available() else 0
        if gpu_count == 0:
            logger.warning("No GPU available, falling back to CPU")
            devices = ["cpu"]
        else:
            devices = [f"cuda:{i}" for i in range(gpu_count)]
        
        logger.info(f"Using {len(devices)} devices for multiprocessing: {devices}")

        try:
            # Use multiprocessing for parallel chunk transcription
            model_names = ["typhoon", "pathumma", "pathumma_noise"]
            result_queue = mp.Queue()
            processes = []
            
            # Create processes for each chunk
            for i, chunk_bytes in enumerate(chunk_bytes_list):
                chunk_meta = chunk_meta_list[i]
                chunk_index = chunk_meta["chunk_index"]
                
                # Assign device round-robin
                device = devices[i % len(devices)]
                
                process = mp.Process(
                    target=_mp_worker_transcribe_chunk,
                    args=(chunk_bytes, chunk_index, model_names, device, result_queue)
                )
                processes.append(process)
            
            # Start all processes
            process_start = time.time()
            for process in processes:
                process.start()
            
            # Wait for all processes to complete
            for process in processes:
                process.join()
            
            total_process_time = time.time() - process_start
            logger.info(f"Multiprocessing batch completed in {total_process_time:.2f}s")
            
            # Collect results from queue
            results_dict = {}
            while not result_queue.empty():
                chunk_index, transcriptions, processing_times, error = result_queue.get()
                results_dict[chunk_index] = {
                    "transcriptions": transcriptions,
                    "processing_times_ms": processing_times,
                    "error": error,
                }

            # Update session with transcription results
            session = transcription_memory.get_session(session_id)
            if session:
                for i, chunk_meta in enumerate(chunk_meta_list):
                    chunk_index = chunk_meta["chunk_index"]
                    
                    if chunk_index not in results_dict:
                        logger.warning(f"No result for chunk {chunk_index}")
                        continue
                    
                    trans_result = results_dict[chunk_index]
                    
                    if trans_result["error"]:
                        logger.error(f"Error transcribing chunk {chunk_index}: {trans_result['error']}")
                        continue

                    # Create/update chunk transcription
                    chunk_transcription = ChunkTranscription(
                        chunk_index=chunk_index,
                        start_sec=chunk_meta["start_sec"],
                        end_sec=chunk_meta["end_sec"],
                        duration_sec=chunk_meta["duration_sec"],
                        status="completed",
                    )

                    # Add transcription results
                    transcriptions = trans_result["transcriptions"]
                    processing_times = trans_result["processing_times_ms"]

                    if "typhoon" in transcriptions:
                        chunk_transcription.typhoon_transcript = transcriptions[
                            "typhoon"
                        ].get("text", "")
                        chunk_transcription.processing_time_ms["typhoon"] = (
                            processing_times.get("typhoon", 0)
                        )

                    if "pathumma" in transcriptions:
                        chunk_transcription.pathumma_transcript = transcriptions[
                            "pathumma"
                        ].get("text", "")
                        chunk_transcription.processing_time_ms["pathumma"] = (
                            processing_times.get("pathumma", 0)
                        )

                    if "pathumma_noise" in transcriptions:
                        chunk_transcription.whisper_transcript = transcriptions[
                            "pathumma_noise"
                        ].get("text", "")
                        chunk_transcription.processing_time_ms["whisper"] = (
                            processing_times.get("pathumma_noise", 0)
                        )

                    # Update session
                    session.add_chunk_transcription(chunk_transcription)
                    session.current_chunk = chunk_index

                    # Prepare result for return
                    batch_results.append(
                        {
                            "chunk_index": chunk_index,
                            "start_sec": chunk_meta["start_sec"],
                            "end_sec": chunk_meta["end_sec"],
                            "duration_sec": chunk_meta["duration_sec"],
                            "size_bytes": len(chunk_bytes_list[i]),
                            "transcriptions": transcriptions,
                            "processing_times_ms": processing_times,
                            "has_all_transcriptions": chunk_transcription.has_all_transcriptions,
                        }
                    )

                # Update session progress
                session.current_chunk = (
                    max([r["chunk_index"] for r in batch_results]) + 1
                )
                if session.is_complete:
                    session.completed_at = datetime.now()
                    session.status = "completed"
                    logger.info(f"Session {session_id} transcription completed")

        except Exception as e:
            logger.error(f"Error in batch transcription: {e}")
            # Update session with error status
            session = transcription_memory.get_session(session_id)
            if session:
                session.status = "error"
                session.error_message = str(e)
            raise
        finally:
            self._cleanup_memory()

        return batch_results

    def _process_chunk_batch(
        self, chunk_bytes_list: List[bytes], chunk_meta_list: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Process a batch of audio chunks (just return chunk info)

        Args:
            chunk_bytes_list: List of audio chunk bytes
            chunk_meta_list: List of chunk metadata

        Returns:
            List of chunk information
        """
        # Check memory before processing batch
        self._check_memory_usage()

        batch_results = []

        try:
            # Just return chunk metadata without transcription
            for i, (chunk_bytes, chunk_meta) in enumerate(
                zip(chunk_bytes_list, chunk_meta_list)
            ):
                batch_results.append(
                    {
                        "chunk_index": chunk_meta["chunk_index"],
                        "start_sec": chunk_meta["start_sec"],
                        "end_sec": chunk_meta["end_sec"],
                        "duration_sec": chunk_meta["duration_sec"],
                        "size_bytes": len(chunk_bytes),
                    }
                )

        finally:
            # Clean up memory after batch processing
            self._cleanup_memory()

        return batch_results

    def _check_memory_usage(self):
        """Check current memory usage (disabled warning logs)"""
        try:
            memory_info = self.process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024

        except Exception as e:
            pass

    def _cleanup_memory(self):
        """Force garbage collection and memory cleanup"""
        try:
            # Force garbage collection
            gc.collect()


            # Log memory after cleanup
            memory_info = self.process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024
            logger.debug(f"Memory after cleanup: {memory_mb:.1f}MB")


        except Exception as e:
            logger.warning(f"Memory cleanup failed: {e}")

    async def _process_chunks_parallel_compare(
        self, chunk_dict: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process chunks through compare workflow in parallel with concurrency limit and retry"""
        try:
            # Create semaphore to limit concurrent processing
            semaphore = asyncio.Semaphore(self.max_concurrent_chunks)

            async def process_chunk_with_retry(
                chunk_id: str, chunk_data: Dict[str, Any]
            ) -> Dict[str, Any]:
                """Process single chunk with retry mechanism"""
                async with semaphore:
                    state = {"chunk_id": chunk_id, "chunk_data": chunk_data}

                    # Retry mechanism
                    last_exception = None
                    for attempt in range(self.max_retries + 1):
                        try:
                            if attempt > 0:
                                logger.info(
                                    f"Retrying chunk {chunk_id}, attempt {attempt + 1}/{self.max_retries + 1}"
                                )
                                await asyncio.sleep(1 * attempt)  # Exponential backoff

                            result = await self.compare_action.execute(state)

                            if result.get("status") == "success":
                                logger.debug(
                                    f"Chunk {chunk_id} processed successfully on attempt {attempt + 1}"
                                )
                                return {
                                    "chunk_id": chunk_id,
                                    "status": "success",
                                    "compare_result": result.get(
                                        "compare_chunk_wav_files_result", {}
                                    ),
                                    "processing_time": result.get("processing_time"),
                                    "workflow_steps": result.get("workflow_steps", []),
                                    "attempts": attempt + 1,
                                }
                            else:
                                # If workflow returned failed status, treat as error
                                error_msg = result.get(
                                    "error", "Unknown error in workflow"
                                )
                                last_exception = Exception(error_msg)
                                logger.warning(
                                    f"Chunk {chunk_id} workflow returned failed status on attempt {attempt + 1}: {error_msg}"
                                )

                        except Exception as e:
                            last_exception = e
                            logger.warning(
                                f"Chunk {chunk_id} failed on attempt {attempt + 1}: {e}"
                            )

                    # All retries failed
                    logger.error(
                        f"Chunk {chunk_id} failed after {self.max_retries + 1} attempts: {last_exception}"
                    )
                    return {
                        "chunk_id": chunk_id,
                        "status": "failed",
                        "error": str(last_exception),
                        "compare_result": {},
                        "attempts": self.max_retries + 1,
                    }

            # Create tasks for parallel processing with retry
            tasks = []
            for chunk_id, chunk_data in chunk_dict.items():
                task = asyncio.create_task(
                    process_chunk_with_retry(chunk_id, chunk_data)
                )
                tasks.append(task)

            # Wait for all tasks to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results and combine
            combined_results = {}
            successful_chunks = 0
            failed_chunks = 0
            total_attempts = 0

            for result in results:
                if isinstance(result, Exception):
                    # This should not happen with our retry mechanism, but handle just in case
                    logger.error(f"Unexpected error in chunk processing: {result}")
                    chunk_id = "unknown"
                    combined_results[chunk_id] = {
                        "status": "failed",
                        "error": str(result),
                        "compare_result": {},
                        "attempts": 1,
                    }
                    failed_chunks += 1
                    total_attempts += 1
                else:
                    chunk_id = result.get("chunk_id", "unknown")
                    combined_results[chunk_id] = result

                    if result.get("status") == "success":
                        successful_chunks += 1
                    else:
                        failed_chunks += 1

                    total_attempts += result.get("attempts", 1)

            logger.info(
                f"Parallel compare processing completed: {successful_chunks} successful, {failed_chunks} failed, {total_attempts} total attempts"
            )

            return {
                "total_chunks": len(chunk_dict),
                "successful_chunks": successful_chunks,
                "failed_chunks": failed_chunks,
                "total_attempts": total_attempts,
                "max_concurrent": self.max_concurrent_chunks,
                "max_retries": self.max_retries,
                "results": combined_results,
            }

        except Exception as e:
            logger.error(f"Error in parallel compare processing: {e}")
            return {
                "total_chunks": len(chunk_dict),
                "successful_chunks": 0,
                "failed_chunks": len(chunk_dict),
                "results": {},
                "error": str(e),
            }

    def execute(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        """
        Action for processing WAV file (chunking only)

        Args:
            file_content: Binary content of WAV file
            filename: Original filename

        Returns:
            Dict with chunking results
        """
        logger.info(f"Executing WAV file action for: {filename}")

        # Initial memory check
        self._check_memory_usage()

        try:
            # Process chunks in batches for memory efficiency
            chunk_results = process_chunks_in_batches(
                wav_bytes=file_content,
                processor_func=self._process_chunk_batch,
                target_sr=16_000,
                chunk_duration_s=30,
                overlap_s=3,  # 3 seconds overlap
                batch_size=3,  # Process 3 chunks at a time
            )

            # Calculate summary statistics
            total_chunks = len(chunk_results)

            # Final memory cleanup
            self._cleanup_memory()

            result = {
                "action": "wav_file_chunked",
                "filename": filename,
                "content_size": len(file_content),
                "status": "completed",
                "processing_summary": {
                    "total_chunks": total_chunks,
                    "chunk_duration_sec": 30,
                    "overlap_sec": 3,
                    "target_sample_rate": 16000,
                },
                "results": chunk_results,
            }

            logger.info(
                f"WAV file chunking completed: {filename}, {total_chunks} chunks created"
            )
            return result

        except Exception as e:
            logger.error(f"Error processing WAV file {filename}: {e}")
            # Ensure cleanup even on error
            self._cleanup_memory()
            raise

    async def execute_with_transcription(
        self, file_content: bytes, filename: str
    ) -> Dict[str, Any]:
        """Action for processing WAV file with full transcription"""
        self._check_memory_usage()

        try:
            # Create transcription session
            from src.utils.audio.chunk_wav_audio import chunk_wav_audio_bytes

            # Get chunking info first
            chunk_info = chunk_wav_audio_bytes(
                wav_bytes=file_content,
                target_sr=16_000,
                chunk_duration_s=30,
                overlap_s=3,
                batch_size=3,
            )

            # Create session in memory
            session = transcription_memory.create_session(
                filename=filename,
                file_size_bytes=len(file_content),
                total_duration_sec=chunk_info["total_duration_sec"],
                total_chunks=chunk_info["num_chunks"],
                chunk_duration_sec=30,
                overlap_sec=3,
            )

            session.started_at = datetime.now()
            session.status = "processing"

            logger.info(
                f"Created transcription session {session.session_id} for {filename}"
            )

            # Process chunks with transcription
            transcription_results = []
            batch_count = 0

            for chunk_batch in chunk_info["batch_generator"]():
                batch_count += 1
                logger.info(f"Processing transcription batch {batch_count}")

                # Convert chunks to bytes
                chunk_bytes_list = [chunk.to_bytes() for chunk in chunk_batch]
                chunk_meta_list = [chunk.to_dict() for chunk in chunk_batch]

                # Process batch with transcription
                batch_results = await self._process_chunk_batch_with_transcription(
                    chunk_bytes_list=chunk_bytes_list,
                    chunk_meta_list=chunk_meta_list,
                    session_id=session.session_id,
                )

                transcription_results.extend(batch_results)

                # Update session progress
                session.current_model = "transcribing"
                session.current_chunk = batch_count * 3  # Approximate

                # Memory cleanup
                del chunk_bytes_list
                del chunk_meta_list
                del chunk_batch

                if batch_count % 5 == 0:  # Every 5 batches
                    self._cleanup_memory()
                    self.asr_manager.clear_cache()

            # Finalize session
            session.completed_at = datetime.now()
            session.status = "completed"

            # Calculate total processing time safely
            if session.started_at:
                time_diff = session.completed_at - session.started_at
                if hasattr(time_diff, "total_seconds"):
                    session.total_processing_time_ms = time_diff.total_seconds() * 1000
                else:
                    session.total_processing_time_ms = 0
            else:
                session.total_processing_time_ms = 0

            # Calculate model processing times
            for chunk_trans in session.chunk_transcriptions:
                for model, time_ms in chunk_trans.processing_time_ms.items():
                    if model not in session.model_processing_times:
                        session.model_processing_times[model] = 0
                    session.model_processing_times[model] += time_ms

            self._cleanup_memory()

            logger.info(f"Transcription completed for session {session.session_id}")

            # Create chunk_dict with desired structure (summary: text only)
            chunk_dict = {}
            for chunk_result in transcription_results:
                chunk_id = chunk_result["chunk_index"]
                chunk_dict[chunk_id] = {
                    "chunk_info": {
                        "start_time": chunk_result["start_sec"],
                        "end_time": chunk_result["end_sec"],
                        "duration": chunk_result["duration_sec"],
                    },
                    "model_transcriptions": {
                        "typhoon": {
                            "text": chunk_result["transcriptions"]
                            .get("typhoon", {})
                            .get("text", "")
                        },
                        "pathumma": {
                            "text": chunk_result["transcriptions"]
                            .get("pathumma", {})
                            .get("text", "")
                        },
                        "pathumma_noise": {
                            "text": chunk_result["transcriptions"]
                            .get("pathumma_noise", {})
                            .get("text", "")
                        },
                    },
                }

            # Sanitize transcription_results for response: keep only text/error per model
            sanitized_results = []
            for chunk_result in transcription_results:
                transcriptions = chunk_result.get("transcriptions", {})
                sanitized_transcriptions = {}
                for model_name, result in transcriptions.items():
                    if isinstance(result, dict):
                        sanitized_transcriptions[model_name] = {
                            "text": result.get("text", ""),
                            "error": result.get("error"),
                        }
                    else:
                        sanitized_transcriptions[model_name] = {
                            "text": str(result),
                            "error": None,
                        }

                sanitized_chunk = {
                    **chunk_result,
                    "transcriptions": sanitized_transcriptions,
                }
                sanitized_results.append(sanitized_chunk)

            return {
                "action": "wav_file_transcribed",
                "filename": filename,
                "content_size": len(file_content),
                "status": "completed",
                "session_id": session.session_id,
                "processing_summary": {
                    "total_chunks": session.total_chunks,
                    "chunk_duration_sec": 30,
                    "overlap_sec": 3,
                    "target_sample_rate": 16000,
                    "total_processing_time_ms": session.total_processing_time_ms,
                    "model_processing_times": session.model_processing_times,
                },
                "results": sanitized_results,
                "chunk_dict": chunk_dict,
                "session_summary": session.summary_stats,
            }

        except Exception as e:
            logger.error(f"Error in transcription execution: {e}")
            self._cleanup_memory()
            raise
