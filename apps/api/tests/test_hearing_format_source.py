import pytest

from app.services.transcription_service import TranscriptionService


class FakeVomo:
    def __init__(self) -> None:
        self.calls = []

    def optimize_audio(self, file_path: str) -> str:
        return file_path

    def transcribe(self, audio_path: str) -> str:
        return "RAW"

    def _segment_raw_transcription(self, text: str):
        return [
            {"speaker": "SPEAKER 1", "content": "[00:01] Bom dia."},
            {"speaker": "SPEAKER 2", "content": "[00:02] Ok."},
        ]

    async def format_transcription_async(
        self,
        transcription: str,
        video_name: str,
        output_folder: str,
        mode: str = "APOSTILA",
        custom_prompt=None,
        dry_run: bool = False,
        progress_callback=None,
        skip_audit: bool = False,
        skip_fidelity_audit: bool = False,
        skip_sources_audit: bool = False,
        include_timestamps: bool = True,
        allow_indirect: bool = False,
        allow_summary: bool = False,
    ) -> str:
        self.calls.append({
            "transcription": transcription,
            "video_name": video_name,
            "mode": mode,
            "include_timestamps": include_timestamps,
            "allow_indirect": allow_indirect,
            "allow_summary": allow_summary,
            "skip_audit": skip_audit,
            "skip_fidelity_audit": skip_fidelity_audit,
            "skip_sources_audit": skip_sources_audit,
        })
        return "FORMATTED"

    def save_as_word(self, *args, **kwargs):
        return None


@pytest.mark.asyncio
async def test_hearing_format_uses_transcript_markdown(monkeypatch, tmp_path):
    service = TranscriptionService()
    fake_vomo = FakeVomo()

    async def fake_classify(*args, **kwargs):
        return {}, []

    async def fake_extract(evidence, *args, **kwargs):
        return evidence

    hearings_dir = tmp_path / "hearings"
    hearings_dir.mkdir(parents=True, exist_ok=True)

    def _case_dir(case_id: str):
        case_dir = hearings_dir / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        return case_dir

    monkeypatch.setattr(service, "_get_vomo", lambda *args, **kwargs: fake_vomo)
    monkeypatch.setattr(service, "_classify_segments_act_with_llm", fake_classify)
    monkeypatch.setattr(service, "_extract_claims_with_llm", fake_extract)
    async def fake_infer_roles(*a, **kw):
        return {}
    monkeypatch.setattr(service, "_infer_speaker_roles_with_llm", fake_infer_roles)
    monkeypatch.setattr(service, "_detect_contradictions", lambda claims: [])
    monkeypatch.setattr(service, "_build_timeline", lambda claims, segments: [])
    monkeypatch.setattr(service, "_get_hearing_case_dir", _case_dir)

    audio_file = tmp_path / "audio.wav"
    audio_file.write_text("dummy", encoding="utf-8")

    result = await service.process_hearing_with_progress(
        file_path=str(audio_file),
        case_id="case123",
        format_mode="REUNIAO",
        format_enabled=True,
        goal="alegacoes_finais",
        thinking_level="low",
        model_selection="gemini-3-flash-preview",
        high_accuracy=False,
        use_cache=False,
    )

    assert fake_vomo.calls, "format_transcription_async was not called"
    call = fake_vomo.calls[0]
    assert call["mode"] == "REUNIAO"
    assert call["allow_indirect"] is False
    assert call["allow_summary"] is False
    assert "SPEAKER 1" in call["transcription"]
    assert "[00:01]" in call["transcription"]
    assert result["hearing"]["formatted_mode"] == "REUNIAO"
    assert result["hearing"]["formatted_text"] == "FORMATTED"
    assert call["include_timestamps"] is True


@pytest.mark.asyncio
async def test_hearing_can_disable_timestamps(monkeypatch, tmp_path):
    service = TranscriptionService()
    fake_vomo = FakeVomo()

    async def fake_classify(*args, **kwargs):
        return {}, []

    async def fake_extract(evidence, *args, **kwargs):
        return evidence

    hearings_dir = tmp_path / "hearings"
    hearings_dir.mkdir(parents=True, exist_ok=True)

    def _case_dir(case_id: str):
        case_dir = hearings_dir / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        return case_dir

    monkeypatch.setattr(service, "_get_vomo", lambda *args, **kwargs: fake_vomo)
    monkeypatch.setattr(service, "_classify_segments_act_with_llm", fake_classify)
    monkeypatch.setattr(service, "_extract_claims_with_llm", fake_extract)
    async def fake_infer_roles(*a, **kw):
        return {}
    monkeypatch.setattr(service, "_infer_speaker_roles_with_llm", fake_infer_roles)
    monkeypatch.setattr(service, "_detect_contradictions", lambda claims: [])
    monkeypatch.setattr(service, "_build_timeline", lambda claims, segments: [])
    monkeypatch.setattr(service, "_get_hearing_case_dir", _case_dir)

    audio_file = tmp_path / "audio.wav"
    audio_file.write_text("dummy", encoding="utf-8")

    result = await service.process_hearing_with_progress(
        file_path=str(audio_file),
        case_id="case123",
        format_mode="AUDIENCIA",
        format_enabled=True,
        include_timestamps=False,
        goal="alegacoes_finais",
        thinking_level="low",
        model_selection="gemini-3-flash-preview",
        high_accuracy=False,
        use_cache=False,
    )

    assert fake_vomo.calls, "format_transcription_async was not called"
    call = fake_vomo.calls[0]
    assert call["include_timestamps"] is False
    assert "SPEAKER 1" in call["transcription"]
    assert "[00:01]" not in call["transcription"]
    assert result["hearing"]["transcript_markdown"]
    assert "[00:01]" in result["hearing"]["transcript_markdown"]
    assert result["hearing"]["blocks"], "blocks should be present"
    assert "[00:01]" in (result["hearing"]["blocks"][0].get("text") or "")


@pytest.mark.asyncio
async def test_hearing_allows_indirect_and_summary_for_audiencia(monkeypatch, tmp_path):
    service = TranscriptionService()
    fake_vomo = FakeVomo()

    async def fake_classify(*args, **kwargs):
        return {}, []

    async def fake_extract(evidence, *args, **kwargs):
        return evidence

    hearings_dir = tmp_path / "hearings"
    hearings_dir.mkdir(parents=True, exist_ok=True)

    def _case_dir(case_id: str):
        case_dir = hearings_dir / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        return case_dir

    monkeypatch.setattr(service, "_get_vomo", lambda *args, **kwargs: fake_vomo)
    monkeypatch.setattr(service, "_classify_segments_act_with_llm", fake_classify)
    monkeypatch.setattr(service, "_extract_claims_with_llm", fake_extract)
    async def fake_infer_roles(*a, **kw):
        return {}
    monkeypatch.setattr(service, "_infer_speaker_roles_with_llm", fake_infer_roles)
    monkeypatch.setattr(service, "_detect_contradictions", lambda claims: [])
    monkeypatch.setattr(service, "_build_timeline", lambda claims, segments: [])
    monkeypatch.setattr(service, "_get_hearing_case_dir", _case_dir)

    audio_file = tmp_path / "audio.wav"
    audio_file.write_text("dummy", encoding="utf-8")

    await service.process_hearing_with_progress(
        file_path=str(audio_file),
        case_id="case123",
        format_mode="AUDIENCIA",
        format_enabled=True,
        goal="alegacoes_finais",
        thinking_level="low",
        model_selection="gemini-3-flash-preview",
        high_accuracy=False,
        allow_indirect=True,
        allow_summary=True,
        use_cache=False,
    )

    assert fake_vomo.calls, "format_transcription_async was not called"
    call = fake_vomo.calls[0]
    assert call["mode"] == "AUDIENCIA"
    assert call["allow_indirect"] is True
    assert call["allow_summary"] is True


@pytest.mark.asyncio
async def test_hearing_forwards_skip_audit_flags(monkeypatch, tmp_path):
    service = TranscriptionService()
    fake_vomo = FakeVomo()

    async def fake_classify(*args, **kwargs):
        return {}, []

    async def fake_extract(evidence, *args, **kwargs):
        return evidence

    hearings_dir = tmp_path / "hearings"
    hearings_dir.mkdir(parents=True, exist_ok=True)

    def _case_dir(case_id: str):
        case_dir = hearings_dir / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        return case_dir

    monkeypatch.setattr(service, "_get_vomo", lambda *args, **kwargs: fake_vomo)
    monkeypatch.setattr(service, "_classify_segments_act_with_llm", fake_classify)
    monkeypatch.setattr(service, "_extract_claims_with_llm", fake_extract)
    async def fake_infer_roles(*a, **kw):
        return {}
    monkeypatch.setattr(service, "_infer_speaker_roles_with_llm", fake_infer_roles)
    monkeypatch.setattr(service, "_detect_contradictions", lambda claims: [])
    monkeypatch.setattr(service, "_build_timeline", lambda claims, segments: [])
    monkeypatch.setattr(service, "_get_hearing_case_dir", _case_dir)

    audio_file = tmp_path / "audio.wav"
    audio_file.write_text("dummy", encoding="utf-8")

    await service.process_hearing_with_progress(
        file_path=str(audio_file),
        case_id="case123",
        format_mode="AUDIENCIA",
        format_enabled=True,
        goal="alegacoes_finais",
        thinking_level="low",
        model_selection="gemini-3-flash-preview",
        high_accuracy=False,
        skip_legal_audit=True,
        skip_fidelity_audit=True,
        skip_sources_audit=True,
        use_cache=False,
    )

    assert fake_vomo.calls, "format_transcription_async was not called"
    call = fake_vomo.calls[0]
    assert call["skip_audit"] is True
    assert call["skip_fidelity_audit"] is True
    assert call["skip_sources_audit"] is True
