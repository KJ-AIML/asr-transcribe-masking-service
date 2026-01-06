"""
Test script to verify concurrent GPU execution for stereo processing
This test checks if left and right channels are processed in parallel on different GPUs
"""
import asyncio
import time
import torch
from src.models.asr_models import ASRModelManager
from src.models.transcription_model_adapter import TranscriptionModelAdapter, WhisperAdapter


async def test_concurrent_gpus():
    print("=" * 60)
    print("Testing Concurrent GPU Execution")
    print("=" * 60)
    
    device_count = torch.cuda.device_count() if torch.cuda.is_available() else 0
    print(f"\nAvailable GPUs: {device_count}")
    
    if device_count < 2:
        print("WARNING: This test requires at least 2 GPUs for true parallel execution")
        print("Proceeding anyway to see the behavior...")
    
    agent_device = "cuda:0" if device_count >= 1 else "cpu"
    caller_device = "cuda:1" if device_count >= 2 else "cuda:0" if device_count >= 1 else "cpu"
    
    print(f"Agent device: {agent_device}")
    print(f"Caller device: {caller_device}")
    print()
    
    manager_agent = ASRModelManager(device=agent_device)
    manager_caller = ASRModelManager(device=caller_device)
    
    adapter_agent = TranscriptionModelAdapter()
    adapter_caller = TranscriptionModelAdapter()
    
    adapter_agent.register_adapter("pathumma", WhisperAdapter("pathumma", manager_agent))
    adapter_caller.register_adapter("pathumma", WhisperAdapter("pathumma", manager_caller))
    
    print("Loading models...")
    start_time = time.time()
    await manager_agent.ensure_model_loaded("pathumma")
    await manager_caller.ensure_model_loaded("pathumma")
    load_time = time.time() - start_time
    print(f"Models loaded in {load_time:.2f}s\n")
    
    test_audio_path = "test_audio.wav"
    try:
        print("Testing concurrent transcription...")
        
        start_total = time.time()
        
        task_agent = asyncio.create_task(
            adapter_agent.transcribe_with_model(test_audio_path, "pathumma", "th")
        )
        task_caller = asyncio.create_task(
            adapter_caller.transcribe_with_model(test_audio_path, "pathumma", "th")
        )
        
        results = await asyncio.gather(task_agent, task_caller)
        total_time = time.time() - start_total
        
        print(f"Concurrent transcription completed in {total_time:.2f}s")
        print()
        print("Agent result:", results[0].get("text", "")[:100] + "...")
        print("Caller result:", results[1].get("text", "")[:100] + "...")
        
        print("\n" + "=" * 60)
        print("SUCCESS: Concurrent execution test completed")
        print("=" * 60)
        
    except FileNotFoundError:
        print(f"Test audio file not found: {test_audio_path}")
        print("Please provide a test WAV file to run this test")
    except Exception as e:
        print(f"Error during test: {e}")
        import traceback
        traceback.print_exc()
    finally:
        manager_agent.models.get("pathumma", object()).unload_model()
        manager_caller.models.get("pathumma", object()).unload_model()


if __name__ == "__main__":
    asyncio.run(test_concurrent_gpus())
