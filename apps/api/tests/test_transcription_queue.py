"""
Testes para a fila inteligente de transcrição (semáforo por provider).

Whisper: sequencial (semáforo=1)
AssemblyAI: concorrência configurável (default conservador)
RunPod: configurável (padrão=5)
Providers diferentes NÃO bloqueiam uns aos outros.
"""

import asyncio
import pytest
from unittest.mock import patch

from app.services.transcription_providers import (
    ProviderConfig,
    get_provider_config,
    list_enabled_providers,
)


# ---------- Provider Config ----------

class TestProviderConfig:
    def test_whisper_is_sequential(self):
        cfg = get_provider_config("whisper")
        assert cfg.max_concurrency == 1
        assert cfg.is_local is True
        assert cfg.is_enabled is True

    def test_assemblyai_default_concurrency_when_key_present(self):
        with patch.dict("os.environ", {"ASSEMBLYAI_API_KEY": "test-key"}):
            from app.services.transcription_providers import _build_configs
            configs = _build_configs()
            assert configs["assemblyai"].max_concurrency == 2
            assert configs["assemblyai"].is_enabled is True

    def test_assemblyai_allows_unlimited_via_env_zero(self):
        with patch.dict("os.environ", {
            "ASSEMBLYAI_API_KEY": "test-key",
            "ASSEMBLYAI_MAX_CONCURRENCY": "0",
        }):
            from app.services.transcription_providers import _build_configs
            configs = _build_configs()
            assert configs["assemblyai"].max_concurrency == 0

    def test_assemblyai_disabled_without_key(self):
        with patch.dict("os.environ", {"ASSEMBLYAI_API_KEY": ""}, clear=False):
            from app.services.transcription_providers import _build_configs
            configs = _build_configs()
            assert configs["assemblyai"].is_enabled is False

    def test_runpod_concurrency_from_env(self):
        with patch.dict("os.environ", {
            "RUNPOD_API_KEY": "rpa_test",
            "RUNPOD_ENDPOINT_ID": "abc123",
            "RUNPOD_MAX_CONCURRENCY": "3",
        }):
            from app.services.transcription_providers import _build_configs
            configs = _build_configs()
            assert configs["runpod"].max_concurrency == 3
            assert configs["runpod"].is_enabled is True

    def test_runpod_disabled_without_keys(self):
        with patch.dict("os.environ", {"RUNPOD_API_KEY": "", "RUNPOD_ENDPOINT_ID": ""}, clear=False):
            from app.services.transcription_providers import _build_configs
            configs = _build_configs()
            assert configs["runpod"].is_enabled is False

    def test_unknown_engine_falls_back_to_whisper(self):
        cfg = get_provider_config("unknown_engine")
        assert cfg.name == "whisper"
        assert cfg.max_concurrency == 1

    def test_list_enabled_always_includes_whisper(self):
        enabled = list_enabled_providers()
        assert "whisper" in enabled


# ---------- Semáforo per-provider ----------

class TestProviderSemaphore:
    """Testa que a fila inteligente funciona: Whisper sequencial, cloud paralelo."""

    @pytest.mark.asyncio
    async def test_whisper_sequential(self):
        """Whisper com semáforo=1: segundo job espera o primeiro terminar."""
        from app.api.endpoints.transcription import (
            _get_provider_semaphore,
            _acquire_provider_slot,
            _provider_semaphores,
        )
        # Limpar cache
        _provider_semaphores.clear()

        order = []

        async def job(name: str, delay: float):
            async with _acquire_provider_slot("whisper"):
                order.append(f"{name}_start")
                await asyncio.sleep(delay)
                order.append(f"{name}_end")

        await asyncio.gather(job("A", 0.1), job("B", 0.05))
        # Whisper é sequencial: A deve começar e terminar antes de B
        assert order == ["A_start", "A_end", "B_start", "B_end"]

    @pytest.mark.asyncio
    async def test_assemblyai_obeys_configured_limit(self):
        """AssemblyAI respeita concorrência configurada."""
        from app.api.endpoints.transcription import (
            _acquire_provider_slot,
            _provider_semaphores,
        )
        _provider_semaphores.clear()

        with patch(
            "app.api.endpoints.transcription.get_provider_config",
            return_value=ProviderConfig(name="assemblyai", max_concurrency=2, is_local=False, is_enabled=True),
        ):
            concurrent = []
            max_concurrent = 0

            async def job(name: str, delay: float):
                nonlocal max_concurrent
                async with _acquire_provider_slot("assemblyai"):
                    concurrent.append(name)
                    max_concurrent = max(max_concurrent, len(concurrent))
                    await asyncio.sleep(delay)
                    concurrent.remove(name)

            await asyncio.gather(job("A", 0.1), job("B", 0.05), job("C", 0.05))
            assert max_concurrent <= 2

    @pytest.mark.asyncio
    async def test_different_providers_dont_block(self):
        """Whisper e AssemblyAI rodando simultaneamente não se bloqueiam."""
        from app.api.endpoints.transcription import (
            _acquire_provider_slot,
            _provider_semaphores,
        )
        _provider_semaphores.clear()

        order = []

        async def whisper_job():
            async with _acquire_provider_slot("whisper"):
                order.append("whisper_start")
                await asyncio.sleep(0.1)
                order.append("whisper_end")

        async def aai_job():
            async with _acquire_provider_slot("assemblyai"):
                order.append("aai_start")
                await asyncio.sleep(0.05)
                order.append("aai_end")

        await asyncio.gather(whisper_job(), aai_job())
        # Ambos devem iniciar antes que qualquer um termine
        starts = [e for e in order if "_start" in e]
        assert len(starts) == 2
        assert order.index("aai_start") < order.index("whisper_end")

    @pytest.mark.asyncio
    async def test_runpod_concurrency_limit(self):
        """RunPod com semáforo=2: no máximo 2 jobs simultâneos."""
        from app.api.endpoints.transcription import (
            _acquire_provider_slot,
            _provider_semaphores,
        )
        _provider_semaphores.clear()

        # Mock RunPod com concurrency=2
        with patch(
            "app.api.endpoints.transcription.get_provider_config",
            return_value=ProviderConfig(name="runpod", max_concurrency=2, is_local=False, is_enabled=True),
        ):
            concurrent = []
            max_concurrent = 0

            async def job(idx: int):
                nonlocal max_concurrent
                async with _acquire_provider_slot("runpod"):
                    concurrent.append(idx)
                    if len(concurrent) > max_concurrent:
                        max_concurrent = len(concurrent)
                    await asyncio.sleep(0.05)
                    concurrent.remove(idx)

            await asyncio.gather(*[job(i) for i in range(5)])
            assert max_concurrent <= 2
