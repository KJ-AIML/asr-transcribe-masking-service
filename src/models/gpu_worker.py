"""
GPU Worker Process for ASR Transcription
- Uses multiprocessing.Process to isolate CUDA contexts
- Each worker process has its own GPU context
- Communication via multiprocessing.Queue
"""
import multiprocessing as mp
import os
import traceback
import time
import uuid
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


def _worker_loop(
    device: str,
    in_queue: mp.Queue,
    out_queue: mp.Queue,
    model_name: str,
    max_loaded_models: int = 1
):
    """
    Worker process main loop.
    Runs in a separate process with its own CUDA context.
    """
    # Set CUDA device for this process
    if device.startswith("cuda:"):
        device_index = device.split(":")[1]
        os.environ["CUDA_VISIBLE_DEVICES"] = str(device_index)
    
    # Import torch inside the worker process
    import torch
    import asyncio
    
    # Import after setting CUDA_VISIBLE_DEVICES
    from src.models.asr_models import ASRModelManager
    from src.config.logs_config import get_logger
    
    worker_logger = get_logger(__name__)
    worker_logger.info(f"Worker process started for device={device}, model={model_name}")
    
    # Create ASR manager in this process
    manager = ASRModelManager(device=device, max_loaded_models=max_loaded_models)
    
    # Preload the model
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(manager.ensure_model_loaded(model_name))
        worker_logger.info(f"Worker preloaded model {model_name} on {device}")
    except Exception as e:
        worker_logger.error(f"Failed to preload model {model_name}: {e}")
    
    # Main worker loop
    while True:
        try:
            # Get task from input queue
            item = in_queue.get(timeout=1.0)
            
            # Check for shutdown signal
            if item is None or (isinstance(item, tuple) and item[0] == "SHUTDOWN"):
                worker_logger.info(f"Worker received shutdown signal for device={device}")
                break
            
            # Process transcription task
            task_id, audio_bytes = item
            
            try:
                # Run transcription synchronously in this process
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                # Ensure model is loaded
                loop.run_until_complete(manager.ensure_model_loaded(model_name))
                
                # Transcribe
                result = loop.run_until_complete(
                    manager.models[model_name].transcribe(audio_bytes)
                )
                
                # Send result back
                out_queue.put((task_id, {"ok": True, "result": result}))
                
            except Exception as e:
                error_msg = traceback.format_exc()
                worker_logger.error(f"Transcription error in worker: {error_msg}")
                out_queue.put((task_id, {"ok": False, "error": str(e), "traceback": error_msg}))
                
        except mp.queues.Empty:
            # No task, continue loop
            continue
        except Exception as e:
            worker_logger.error(f"Unexpected error in worker loop: {traceback.format_exc()}")
            break
    
    # Cleanup
    try:
        manager.unload_models()
        worker_logger.info(f"Worker cleaned up for device={device}")
    except Exception:
        worker_logger.error("Error during worker cleanup")


class GPUWorkerClient:
    """
    Client for communicating with a GPU worker process.
    Each instance manages a separate worker process with its own CUDA context.
    """
    
    def __init__(
        self,
        device: str,
        model_name: str,
        max_loaded_models: int = 1,
        timeout: float = 300.0
    ):
        """
        Initialize GPU worker client.
        
        Args:
            device: Device string (e.g., "cuda:0", "cuda:1")
            model_name: Model name to use (e.g., "pathumma", "pathumma_noise")
            max_loaded_models: Maximum models to load in worker
            timeout: Default timeout for transcription in seconds
        """
        self.device = device
        self.model_name = model_name
        self.timeout = timeout
        
        # Create queues for communication
        self._in_queue = mp.Queue(maxsize=10)
        self._out_queue = mp.Queue(maxsize=10)
        
        # Start worker process
        self._process = mp.Process(
            target=_worker_loop,
            args=(device, self._in_queue, self._out_queue, model_name, max_loaded_models),
            daemon=False
        )
        self._process.start()
        
        logger.info(f"GPU worker started for device={device}, model={model_name}, pid={self._process.pid}")
    
    def transcribe(self, audio_bytes: bytes, timeout: Optional[float] = None) -> Dict[str, Any]:
        """
        Transcribe audio using the worker process.
        
        Args:
            audio_bytes: Audio data as bytes
            timeout: Override default timeout
            
        Returns:
            Dict with transcription result or error
        """
        if timeout is None:
            timeout = self.timeout
        
        task_id = str(uuid.uuid4())
        
        # Send task to worker
        self._in_queue.put((task_id, audio_bytes))
        
        # Wait for result
        start_time = time.time()
        while True:
            try:
                # Check timeout
                if time.time() - start_time > timeout:
                    return {
                        "ok": False,
                        "error": f"Timeout after {timeout}s",
                        "text": "",
                        "words": []
                    }
                
                # Try to get result
                result_task_id, payload = self._out_queue.get(timeout=0.1)
                
                if result_task_id == task_id:
                    return payload
                else:
                    # Not our result, put it back
                    self._out_queue.put((result_task_id, payload))
                    
            except mp.queues.Empty:
                continue
            except Exception as e:
                return {
                    "ok": False,
                    "error": f"Queue error: {str(e)}",
                    "text": "",
                    "words": []
                }
    
    def transcribe_file(self, audio_path: str, timeout: Optional[float] = None) -> Dict[str, Any]:
        """
        Transcribe audio file using the worker process.
        
        Args:
            audio_path: Path to audio file
            timeout: Override default timeout
            
        Returns:
            Dict with transcription result or error
        """
        # Read file
        try:
            with open(audio_path, "rb") as f:
                audio_bytes = f.read()
        except Exception as e:
            return {
                "ok": False,
                "error": f"Failed to read audio file: {str(e)}",
                "text": "",
                "words": []
            }
        
        return self.transcribe(audio_bytes, timeout=timeout)
    
    def is_alive(self) -> bool:
        """Check if worker process is alive."""
        return self._process.is_alive()
    
    def shutdown(self, timeout: float = 5.0):
        """
        Shutdown worker process gracefully.
        
        Args:
            timeout: Time to wait for process to exit
        """
        try:
            # Send shutdown signal
            self._in_queue.put(("SHUTDOWN", None))
            
            # Wait for process to exit
            self._process.join(timeout=timeout)
            
            if self._process.is_alive():
                logger.warning(f"Worker for {self.device} did not shutdown gracefully, terminating...")
                self._process.terminate()
                self._process.join(timeout=1.0)
                
            logger.info(f"GPU worker shutdown for device={self.device}")
        except Exception as e:
            logger.error(f"Error shutting down worker for {self.device}: {e}")
    
    def __del__(self):
        """Cleanup on deletion."""
        try:
            self.shutdown(timeout=1.0)
        except Exception:
            pass


class GPUWorkerManager:
    """
    Manages multiple GPU workers, one per device.
    Provides a simple interface for stereo processing.
    """
    
    def __init__(
        self,
        agent_device: str,
        caller_device: str,
        model_name: str = "pathumma",
        max_loaded_models: int = 1,
        timeout: float = 300.0
    ):
        """
        Initialize GPU worker manager.
        
        Args:
            agent_device: Device for agent channel (e.g., "cuda:0")
            caller_device: Device for caller channel (e.g., "cuda:1")
            model_name: Model name to use
            max_loaded_models: Maximum models per worker
            timeout: Default timeout for transcription
        """
        self.agent_device = agent_device
        self.caller_device = caller_device
        self.model_name = model_name
        
        # Create workers
        self.agent_worker = GPUWorkerClient(
            device=agent_device,
            model_name=model_name,
            max_loaded_models=max_loaded_models,
            timeout=timeout
        )
        
        self.caller_worker = GPUWorkerClient(
            device=caller_device,
            model_name=model_name,
            max_loaded_models=max_loaded_models,
            timeout=timeout
        )
        
        logger.info(f"GPU worker manager initialized: agent={agent_device}, caller={caller_device}")
    
    async def transcribe_agent(self, audio_bytes: bytes) -> Dict[str, Any]:
        """Transcribe agent channel audio."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.agent_worker.transcribe, audio_bytes)
    
    async def transcribe_caller(self, audio_bytes: bytes) -> Dict[str, Any]:
        """Transcribe caller channel audio."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.caller_worker.transcribe, audio_bytes)
    
    async def transcribe_agent_file(self, audio_path: str) -> Dict[str, Any]:
        """Transcribe agent channel audio file."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.agent_worker.transcribe_file, audio_path)
    
    async def transcribe_caller_file(self, audio_path: str) -> Dict[str, Any]:
        """Transcribe caller channel audio file."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.caller_worker.transcribe_file, audio_path)
    
    async def transcribe_stereo(
        self,
        agent_audio: bytes,
        caller_audio: bytes
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Transcribe both stereo channels concurrently.
        
        Args:
            agent_audio: Audio bytes for agent channel
            caller_audio: Audio bytes for caller channel
            
        Returns:
            Tuple of (agent_result, caller_result)
        """
        agent_task = asyncio.create_task(self.transcribe_agent(agent_audio))
        caller_task = asyncio.create_task(self.transcribe_caller(caller_audio))
        
        return await asyncio.gather(agent_task, caller_task)
    
    def shutdown(self):
        """Shutdown all workers."""
        self.agent_worker.shutdown()
        self.caller_worker.shutdown()
        logger.info("GPU worker manager shutdown complete")
    
    def __del__(self):
        """Cleanup on deletion."""
        try:
            self.shutdown()
        except Exception:
            pass


# Ensure multiprocessing uses spawn method (required on some platforms)
if __name__ == "__main__":
    # This is for testing the worker module directly
    mp.set_start_method("spawn", force=True)
    logger.info("GPU worker module loaded with spawn start method")
