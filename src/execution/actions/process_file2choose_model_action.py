import asyncio
import gc
import os
from typing import Any, Dict

import psutil

from src.config.logs_config import get_logger
from src.execution.actions.process_choose_model_action import ProcessChooseModelAction
from src.execution.actions.process_compare_chunk_wav_files_action import (
    ProcessCompareChunkWavFilesAction,
)
from src.models.asr_models import ASRModelManager

logger = get_logger(__name__)


class ProcessFile2ChooseModelAction:
    def __init__(self):
        self.max_memory_mb = 2048
        self.process = psutil.Process(os.getpid())
        self.asr_manager = ASRModelManager()
        self.compare_action = ProcessCompareChunkWavFilesAction()
        self.choose_model_action = ProcessChooseModelAction()
        self.max_concurrent_chunks = 9
        self.max_retries = 3


    def _check_memory_usage(self):
        """Check current memory usage and log warnings if approaching limits"""
        try:
            # Check RAM usage
            memory_info = self.process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024

            if memory_mb > self.max_memory_mb * 0.8:
                logger.warning(
                    f"High RAM usage detected: {memory_mb:.1f}MB / {self.max_memory_mb}MB"
                )
            elif memory_mb > self.max_memory_mb * 0.9:
                logger.error(
                    f"Critical RAM usage: {memory_mb:.1f}MB / {self.max_memory_mb}MB"
                )


        except Exception as e:
            logger.warning(f"Could not check memory usage: {e}")

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

    async def execute(
        self,
        chunk_dict: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Action for processing WAV file with full transcription"""

        try:
            logger.info(
                f"Processing {len(chunk_dict)} chunks through compare workflow in parallel"
            )
            compare_results = await self._process_chunks_parallel_compare(chunk_dict)

            # Choose best model based on comparison results
            logger.info("Choosing best ASR model based on comparison results")

            model_selection_state = {"compare_results": compare_results}
            model_selection_result = await self.choose_model_action.execute(
                model_selection_state
            )

            return {
                "model_selection": model_selection_result,
            }

        except Exception as e:
            logger.error(f"Error in transcription execution: {e}")
            self._cleanup_memory()
            raise
