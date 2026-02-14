import os
from unittest.mock import patch

import pytest

from app.services.transcription_service import TranscriptionService


class TestRunPodBaseUrlResolution:
    def test_prefers_iudex_runpod_public_base_url(self):
        service = TranscriptionService()
        with patch.dict(
            os.environ,
            {
                "IUDEX_RUNPOD_PUBLIC_BASE_URL": "https://public.example.com/",
                "IUDEX_PUBLIC_BASE_URL": "https://legacy.example.com",
                "IUDEX_BASE_URL": "http://localhost:8000",
            },
            clear=False,
        ):
            base_url, source = service._resolve_runpod_base_url()
            assert base_url == "https://public.example.com"
            assert source == "IUDEX_RUNPOD_PUBLIC_BASE_URL"

    def test_rejects_localhost_without_override(self):
        service = TranscriptionService()
        with patch.dict(
            os.environ,
            {
                "IUDEX_ALLOW_PRIVATE_BASE_URL_FOR_RUNPOD": "false",
            },
            clear=False,
        ):
            with pytest.raises(RuntimeError, match="URL pública"):
                service._validate_runpod_base_url("http://localhost:8000")

    def test_allows_private_with_override(self):
        service = TranscriptionService()
        with patch.dict(
            os.environ,
            {
                "IUDEX_ALLOW_PRIVATE_BASE_URL_FOR_RUNPOD": "true",
            },
            clear=False,
        ):
            service._validate_runpod_base_url("http://127.0.0.1:8000")

    def test_rejects_invalid_absolute_url(self):
        service = TranscriptionService()
        with pytest.raises(RuntimeError, match="URL absoluta"):
            service._validate_runpod_base_url("localhost:8000")

    def test_extracts_job_id_from_transcription_jobs_path(self):
        service = TranscriptionService()
        path = "/tmp/storage/transcription_jobs/1615d69a-b64c-4284-81db-ee50e17faa00/input/audio.mp3"
        job_id = service._extract_transcription_job_id_from_audio_path(path)
        assert job_id == "1615d69a-b64c-4284-81db-ee50e17faa00"

    def test_extracts_job_id_from_legacy_jobs_path(self):
        service = TranscriptionService()
        path = "/tmp/storage/jobs/abc123/input/audio.wav"
        job_id = service._extract_transcription_job_id_from_audio_path(path)
        assert job_id == "abc123"

    def test_extracts_job_id_from_windows_style_path(self):
        service = TranscriptionService()
        path = r"C:\iudex\storage\transcription_jobs\job-xyz\input\audio.mp3"
        job_id = service._extract_transcription_job_id_from_audio_path(path)
        assert job_id == "job-xyz"
