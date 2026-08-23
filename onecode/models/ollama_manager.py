from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable, Optional

import httpx
import psutil


@dataclass
class HardwareProfile:
    total_memory_gb: float
    has_nvidia_gpu: bool
    gpu_memory_gb: Optional[float] = None


@dataclass
class ModelStatus:
    model_id: str
    installed: bool = False
    size_gb: Optional[float] = None
    downloading: bool = False
    download_progress: Optional[float] = None
    error: Optional[str] = None


class OllamaManager:
    ENDPOINT = "http://localhost:11434"

    MODEL_SPECS: dict[str, dict] = {
        "qwen3.5-2b": {
            "ollama_name": "qwen3.5:2b",
            "min_memory_gb": 6,
            "recommended_memory_gb": 8,
            "description": "Qwen3.5 2B - 轻量推荐",
        },
        "qwen3.5-4b": {
            "ollama_name": "qwen3.5:4b",
            "min_memory_gb": 12,
            "recommended_memory_gb": 16,
            "description": "Qwen3.5 4B - 高质量",
        },
        "llama2": {
            "ollama_name": "llama2",
            "min_memory_gb": 4,
            "recommended_memory_gb": 8,
            "description": "Llama 2",
        },
        "codellama": {
            "ollama_name": "codellama",
            "min_memory_gb": 8,
            "recommended_memory_gb": 16,
            "description": "CodeLlama",
        },
    }

    def __init__(self, endpoint: str = "http://localhost:11434"):
        self.endpoint = endpoint.rstrip("/")

    async def check_running(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self.endpoint}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False

    async def list_installed(self) -> dict[str, ModelStatus]:
        result: dict[str, ModelStatus] = {}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{self.endpoint}/api/tags")
                if resp.status_code != 200:
                    return result
                models = resp.json().get("models", [])
                for m in models:
                    name = m.get("name", "")
                    size = m.get("size", 0)
                    for mid, spec in self.MODEL_SPECS.items():
                        if spec["ollama_name"] == name:
                            result[mid] = ModelStatus(
                                model_id=mid,
                                installed=True,
                                size_gb=round(size / (1024**3), 2),
                            )
        except Exception:
            pass
        return result

    def detect_hardware(self) -> HardwareProfile:
        memory = psutil.virtual_memory()
        total_gb = round(memory.total / (1024**3), 1)

        has_nvidia = False
        gpu_mem: Optional[float] = None
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                has_nvidia = True
                gpu_mem = float(result.stdout.strip().split("\n")[0]) / 1024
        except Exception:
            pass

        return HardwareProfile(
            total_memory_gb=total_gb,
            has_nvidia_gpu=has_nvidia,
            gpu_memory_gb=gpu_mem,
        )

    def recommend(self, hardware: HardwareProfile) -> Optional[str]:
        if hardware.total_memory_gb >= 15:
            return "qwen3.5-4b"
        elif hardware.total_memory_gb >= 7:
            return "qwen3.5-2b"
        return None

    def get_hardware_info(self, hardware: HardwareProfile) -> str:
        info = f"内存: {hardware.total_memory_gb}GB"
        if hardware.has_nvidia_gpu:
            info += f" | GPU: {hardware.gpu_memory_gb}GB"
        return info

    def get_recommended_model_info(self, hardware: HardwareProfile) -> str:
        model = self.recommend(hardware)
        if not model:
            return "内存不足，无法运行 Qwen3.5（至少需要 8GB）"
        spec = self.MODEL_SPECS.get(model, {})
        return f"推荐: {model} ({spec.get('description', '')})"

    async def pull_model(
        self,
        model_id: str,
        progress_callback: Optional[Callable[[dict], None]] = None,
    ) -> bool:
        spec = self.MODEL_SPECS.get(model_id)
        if not spec:
            raise ValueError(f"Unknown model: {model_id}")

        ollama_name = spec["ollama_name"]

        async with httpx.AsyncClient(timeout=600) as client:
            async with client.stream(
                "POST",
                f"{self.endpoint}/api/pull",
                json={"name": ollama_name},
            ) as resp:
                if resp.status_code != 200:
                    error_body = await resp.aread()
                    raise RuntimeError(f"Pull failed: {error_body.decode()}")
                async for line in resp.aiter_lines():
                    if line:
                        data = json.loads(line)
                        if progress_callback:
                            progress_callback(data)
                        if data.get("error"):
                            raise RuntimeError(data["error"])
                        if data.get("success"):
                            return True
        return False

    def get_spec(self, model_id: str) -> Optional[dict]:
        return self.MODEL_SPECS.get(model_id)
