"""
Registry de providers de transcrição com configuração de concorrência.

Whisper local: sequencial (MLX não suporta inferência concorrente)
AssemblyAI/ElevenLabs: concorrência configurável (default conservador)
RunPod: paralelo com limite configurável (N workers = N GPUs)
"""
import os
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class ProviderConfig:
    name: str
    max_concurrency: int  # 0 = sem limite
    is_local: bool
    is_enabled: bool


def _read_max_concurrency(env_key: str, default: int) -> int:
    raw = os.getenv(env_key, str(default)).strip()
    try:
        value = int(raw)
    except Exception:
        value = default
    return max(0, value)


def _build_configs() -> Dict[str, ProviderConfig]:
    runpod_key = os.getenv("RUNPOD_API_KEY", "")
    runpod_endpoint = os.getenv("RUNPOD_ENDPOINT_ID", "")
    aai_key = os.getenv("ASSEMBLYAI_API_KEY", "")

    return {
        "whisper": ProviderConfig(
            name="whisper",
            max_concurrency=1,
            is_local=True,
            is_enabled=True,
        ),
        "assemblyai": ProviderConfig(
            name="assemblyai",
            max_concurrency=_read_max_concurrency("ASSEMBLYAI_MAX_CONCURRENCY", 2),
            is_local=False,
            is_enabled=bool(aai_key),
        ),
        "elevenlabs": ProviderConfig(
            name="elevenlabs",
            max_concurrency=_read_max_concurrency("ELEVENLABS_MAX_CONCURRENCY", 2),
            is_local=False,
            is_enabled=bool(os.getenv("ELEVENLABS_API_KEY", "")),
        ),
        "runpod": ProviderConfig(
            name="runpod",
            max_concurrency=_read_max_concurrency("RUNPOD_MAX_CONCURRENCY", 5),
            is_local=False,
            is_enabled=bool(runpod_key and runpod_endpoint),
        ),
    }


PROVIDER_CONFIGS = _build_configs()


def get_provider_config(engine: str) -> ProviderConfig:
    return PROVIDER_CONFIGS.get(engine, PROVIDER_CONFIGS["whisper"])


def list_enabled_providers() -> list[str]:
    return [k for k, v in PROVIDER_CONFIGS.items() if v.is_enabled]
