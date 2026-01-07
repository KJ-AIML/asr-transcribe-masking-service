import time
import torch
import multiprocessing as mp


def gpu_worker(device_id: int, seconds: int = 10):
    """
    งานหนักบน GPU แบบง่ายสุด:
    - matrix multiply loop
    - รันตามเวลาที่กำหนด
    """
    torch.cuda.set_device(device_id)
    device = torch.device(f"cuda:{device_id}")

    print(f"[GPU {device_id}] starting work on {device}")

    # tensor ใหญ่พอให้ GPU ทำงานจริง
    a = torch.randn(4096, 4096, device=device)
    b = torch.randn(4096, 4096, device=device)

    start = time.time()
    iters = 0

    while time.time() - start < seconds:
        a @ b
        # sync เพื่อให้แน่ใจว่า kernel รันจริง
        torch.cuda.synchronize(device)
        iters += 1

    print(f"[GPU {device_id}] done, iterations = {iters}")


if __name__ == "__main__":
    mp.set_start_method("spawn", force=True)

    if not torch.cuda.is_available():
        print("❌ CUDA not available")
        exit(1)

    gpu_count = torch.cuda.device_count()
    print(f"✅ Detected {gpu_count} GPU(s)")

    if gpu_count < 2:
        print("❌ Need at least 2 GPUs")
        exit(1)

    # สร้าง process แยกต่อ GPU
    p0 = mp.Process(target=gpu_worker, args=(0, 10))
    p1 = mp.Process(target=gpu_worker, args=(1, 10))

    print("🚀 Starting GPU workers...")
    p0.start()
    p1.start()

    p0.join()
    p1.join()

    print("✅ Test finished")
