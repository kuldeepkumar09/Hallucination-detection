"""VRAM monitor for RTX 3050 Laptop GPU (4 GB). Pauses generation when VRAM > safe limit."""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

GPU_VRAM_TOTAL_MB = 4096   # RTX 3050 Laptop GPU
GPU_VRAM_LIMIT_MB = 3500   # Leave 596 MB headroom for OS + driver


def get_vram_usage_mb() -> Optional[float]:
    try:
        import pynvml
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        return info.used / 1024 / 1024
    except Exception:
        return None


def is_vram_safe() -> bool:
    usage = get_vram_usage_mb()
    if usage is None:
        return True
    return usage < GPU_VRAM_LIMIT_MB


def vram_status() -> dict:
    usage = get_vram_usage_mb()
    if usage is None:
        return {
            "available": False,
            "used_mb": 0,
            "total_mb": GPU_VRAM_TOTAL_MB,
            "free_mb": GPU_VRAM_TOTAL_MB,
            "safe": True,
            "utilization_pct": 0.0,
            "gpu": "RTX 3050 Laptop GPU",
        }
    return {
        "available": True,
        "used_mb": round(usage, 1),
        "total_mb": GPU_VRAM_TOTAL_MB,
        "free_mb": round(GPU_VRAM_TOTAL_MB - usage, 1),
        "safe": usage < GPU_VRAM_LIMIT_MB,
        "utilization_pct": round(usage / GPU_VRAM_TOTAL_MB * 100, 1),
        "gpu": "RTX 3050 Laptop GPU",
    }
