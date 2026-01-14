import sys
import os
import asyncio
import json
from typing import Optional, Callable, Tuple, Awaitable
import logging
import time
import wave
import re
import hashlib
import uuid
from datetime import datetime
from pathlib import Path

# Adicionar raiz do projeto ao path para importar mlx_vomo
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../../"))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

logger = logging.getLogger(__name__)

class TranscriptionService:
    def __init__(self):
        # Lazy init: evita importar/carregar MLX/Gemini no boot da API (mantém backend saudável).
        self.vomo = None
        self.vomo_config: Optional[Tuple[str, str, bool, Optional[str]]] = None

    def _resolve_model_selection(self, model_selection: Optional[str]) -> Tuple[str, str, bool, Optional[str]]:
        default_gemini = "gemini-3-flash-preview"
        if not model_selection:
            return ("gemini", default_gemini, False, None)
        model_key = model_selection.strip().lower()
        if model_key.startswith("gpt"):
            openai_model = "gpt-5-mini-2025-08-07" if model_key in ("gpt-5-mini", "gpt-5-mini-2025-08-07") else model_selection
            return ("gemini", default_gemini, True, openai_model)
        if model_key.startswith("gemini"):
            return ("gemini", model_selection, False, None)
        return ("gemini", model_selection, False, None)

    def _get_vomo(
        self,
        model_selection: Optional[str] = None,
        thinking_level: Optional[str] = None,
        provider: Optional[str] = None
    ):
        if provider:
            provider_key = provider.strip().lower()
            if provider_key == "openai":
                llm_model = model_selection or "gpt-5-mini-2025-08-07"
                use_openai_primary = False
                openai_model = llm_model
            else:
                llm_model = model_selection or "gemini-3-flash-preview"
                use_openai_primary = False
                openai_model = None
                if model_selection and model_selection.strip().lower().startswith("gpt"):
                    use_openai_primary = True
                    openai_model = model_selection
            provider = provider_key
        else:
            provider, llm_model, use_openai_primary, openai_model = self._resolve_model_selection(model_selection)
        desired_config = (provider, llm_model, use_openai_primary, openai_model)
        if self.vomo is not None and getattr(self.vomo, "provider", None) == provider:
            self.vomo.llm_model = llm_model
            self.vomo.use_openai_primary = use_openai_primary
            if openai_model:
                self.vomo.openai_model = openai_model
            if thinking_level:
                self.vomo.thinking_level = thinking_level
            self.vomo_config = desired_config
            return self.vomo
        try:
            from mlx_vomo import VomoMLX  # import tardio (pode falhar por deps opcionais)
            self.vomo = VomoMLX(provider=provider)
            if llm_model:
                self.vomo.llm_model = llm_model
            self.vomo.use_openai_primary = use_openai_primary
            if openai_model:
                self.vomo.openai_model = openai_model
            if thinking_level:
                self.vomo.thinking_level = thinking_level
            self.vomo_config = desired_config
            return self.vomo
        except Exception as e:
            logger.error(f"❌ VomoMLX indisponível (import/init falhou): {e}")
            raise RuntimeError(f"VomoMLX indisponível: {e}")

    def _get_wav_duration_seconds(self, audio_path: str) -> float:
        if not audio_path.lower().endswith(".wav"):
            return 0.0
        try:
            with wave.open(audio_path, "rb") as wav:
                frames = wav.getnframes()
                rate = wav.getframerate()
                if rate > 0:
                    return float(frames) / float(rate)
        except Exception:
            return 0.0
        return 0.0

    def _extract_audit_report(self, content: str) -> Optional[str]:
        if not content:
            return None
        match = re.search(r'<!--\s*RELATÓRIO:([\s\S]*?)-->', content, re.IGNORECASE)
        if not match:
            return None
        return match.group(1).strip()

    def _persist_transcription_outputs(
        self,
        video_name: str,
        mode: str,
        raw_text: str,
        formatted_text: str,
        analysis_report: Optional[dict] = None,
        validation_report: Optional[dict] = None,
    ) -> dict:
        try:
            from app.core.config import settings
            base_dir = Path(settings.LOCAL_STORAGE_PATH) / "transcriptions"
        except Exception:
            base_dir = Path("./storage") / "transcriptions"

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = base_dir / video_name / timestamp
        output_dir.mkdir(parents=True, exist_ok=True)

        mode_suffix = mode.upper() if mode else "APOSTILA"
        raw_path = output_dir / f"{video_name}_RAW.txt"
        md_path = output_dir / f"{video_name}_{mode_suffix}.md"
        analysis_path = output_dir / f"{video_name}_{mode_suffix}_ANALISE.json"
        validation_path = output_dir / f"{video_name}_{mode_suffix}_FIDELIDADE.json"
        audit_path = output_dir / f"{video_name}_{mode_suffix}_AUDITORIA.md"

        raw_path.write_text(raw_text or "", encoding="utf-8")
        md_path.write_text(formatted_text or "", encoding="utf-8")

        if analysis_report:
            analysis_path.write_text(json.dumps(analysis_report, ensure_ascii=False, indent=2), encoding="utf-8")
        if validation_report:
            validation_path.write_text(json.dumps(validation_report, ensure_ascii=False, indent=2), encoding="utf-8")

        audit_report = self._extract_audit_report(formatted_text or "")
        if audit_report:
            audit_path.write_text(audit_report, encoding="utf-8")

        return {
            "output_dir": str(output_dir),
            "raw_path": str(raw_path),
            "md_path": str(md_path),
            "analysis_path": str(analysis_path) if analysis_report else None,
            "validation_path": str(validation_path) if validation_report else None,
            "audit_path": str(audit_path) if audit_report else None,
        }

    async def _emit_progress_while_running(
        self,
        emit: Callable[[str, int, str], Awaitable[None]],
        done_event: asyncio.Event,
        stage: str,
        start_progress: int,
        end_progress: int,
        label: str,
        estimated_total_seconds: float,
        interval_seconds: float = 2.5
    ) -> None:
        start_time = time.time()
        last_progress = start_progress
        while not done_event.is_set():
            elapsed = time.time() - start_time
            if estimated_total_seconds > 0:
                ratio = min(0.95, elapsed / estimated_total_seconds)
                progress = start_progress + int(ratio * max(1, end_progress - start_progress))
            else:
                progress = min(end_progress - 1, start_progress + int(elapsed / 8))

            if progress < start_progress:
                progress = start_progress
            if progress != last_progress:
                last_progress = progress

            if estimated_total_seconds > 0:
                message = f"{label} ({elapsed:.0f}s / ~{estimated_total_seconds:.0f}s)"
            else:
                message = f"{label} ({elapsed:.0f}s)"

            await emit(stage, progress, message)
            try:
                await asyncio.wait_for(done_event.wait(), timeout=interval_seconds)
            except asyncio.TimeoutError:
                continue

    async def process_file(
        self, 
        file_path: str, 
        mode: str = "APOSTILA", 
        thinking_level: str = "medium",
        custom_prompt: Optional[str] = None,
        high_accuracy: bool = False,
        model_selection: Optional[str] = None
    ) -> str:
        """
        Processa um arquivo de áudio/vídeo usando MLX Vomo.
        
        Reflexo do fluxo main() do script original, mas adaptado para serviço.
        """
        try:
            vomo = self._get_vomo(model_selection=model_selection, thinking_level=thinking_level)
            logger.info(f"🎤 Iniciando processamento Vomo: {file_path} [{mode}]")
            
            # 1. Otimizar Áudio (Extrair se for vídeo)
            audio_path = vomo.optimize_audio(file_path)
            
            # 2. Transcrever (MLX Whisper)
            # Nota: transcribe é síncrono no script original (usa GPU/Metal)
            # Executamos em threadpool se necessário, mas por enquanto direto pois é CPU/GPU bound
            if high_accuracy:
                logger.info("🎯 Usando Beam Search (High Accuracy)")
                transcription_text = vomo.transcribe_beam_search(audio_path)
            else:
                transcription_text = vomo.transcribe(audio_path)
            
            if mode == "RAW":
                return transcription_text

            # 3. Formatar (Gemini)
            # Configurar prompt customizado se houver
            system_prompt = None
            if custom_prompt:
                system_prompt = custom_prompt
            elif mode == "APOSTILA":
                system_prompt = vomo.PROMPT_APOSTILA_ACTIVE
            elif mode == "FIDELIDADE":
                system_prompt = vomo.PROMPT_FIDELIDADE
            
            # Mapear thinking_level para tokens (simplificado)
            # O script original usa thinking_budget int
            # Executar formatação
            # Definir folder temporário para outputs intermediários
            import tempfile
            from pathlib import Path
            
            video_name = Path(file_path).stem
            with tempfile.TemporaryDirectory() as temp_dir:
                final_text = await vomo.format_transcription_async(
                    transcription_text,
                    video_name=video_name,
                    output_folder=temp_dir,
                    mode=mode,
                    custom_prompt=system_prompt
                )

            analysis_report = None
            validation_report = None
            try:
                from app.services.quality_service import quality_service
                analysis_report = await quality_service.analyze_structural_issues(
                    content=final_text,
                    document_name=video_name,
                    raw_content=transcription_text
                )
                validation_report = await quality_service.validate_document_full(
                    raw_content=transcription_text,
                    formatted_content=final_text,
                    document_name=video_name
                )
            except Exception as e:
                logger.warning(f"Falha ao gerar relatórios (não-bloqueante): {e}")

            self._persist_transcription_outputs(
                video_name=video_name,
                mode=mode,
                raw_text=transcription_text,
                formatted_text=final_text,
                analysis_report=analysis_report,
                validation_report=validation_report,
            )

            return final_text

        except Exception as e:
            logger.error(f"Erro no serviço de transcrição: {e}")
            raise e

    async def process_file_with_progress(
        self, 
        file_path: str, 
        mode: str = "APOSTILA", 
        thinking_level: str = "medium",
        custom_prompt: Optional[str] = None,
        high_accuracy: bool = False,
        on_progress: Optional[Callable[[str, int, str], Awaitable[None]]] = None,
        model_selection: Optional[str] = None
    ) -> dict:
        """
        Process file with progress callback for SSE streaming.
        
        on_progress: async callable(stage: str, progress: int, message: str)
        """
        async def emit(stage: str, progress: int, message: str):
            if on_progress:
                await on_progress(stage, progress, message)
        
        try:
            vomo = self._get_vomo(model_selection=model_selection, thinking_level=thinking_level)
            logger.info(f"🎤 Iniciando processamento Vomo com SSE: {file_path} [{mode}]")
            
            # Stage 1: Audio Optimization (0-20%)
            await emit("audio_optimization", 0, "Otimizando áudio...")
            audio_path = await asyncio.to_thread(vomo.optimize_audio, file_path)
            await emit("audio_optimization", 20, "Áudio otimizado ✓")
            
            # Stage 2: Transcription (20-60%)
            await emit("transcription", 25, "Iniciando transcrição com Whisper MLX...")
            audio_duration = self._get_wav_duration_seconds(audio_path)
            rtf_estimate = 1.6 if high_accuracy else 0.9
            estimated_total = audio_duration * rtf_estimate if audio_duration > 0 else 0.0
            done_event = asyncio.Event()
            ticker = asyncio.create_task(
                self._emit_progress_while_running(
                    emit,
                    done_event,
                    "transcription",
                    25,
                    60,
                    "Transcrevendo",
                    estimated_total
                )
            )
            if high_accuracy:
                logger.info("🎯 Usando Beam Search (High Accuracy)")
                transcription_text = await asyncio.to_thread(vomo.transcribe_beam_search, audio_path)
            else:
                transcription_text = await asyncio.to_thread(vomo.transcribe, audio_path)
            done_event.set()
            try:
                await ticker
            except Exception:
                pass
            await emit("transcription", 60, "Transcrição concluída ✓")
            
            if mode == "RAW":
                return transcription_text

            # Stage 3: Formatting (60-100%)
            await emit("formatting", 65, "Preparando formatação com IA...")
            
            # Configure prompt
            system_prompt = None
            if custom_prompt:
                system_prompt = custom_prompt
            elif mode == "APOSTILA":
                system_prompt = vomo.PROMPT_APOSTILA_ACTIVE
            elif mode == "FIDELIDADE":
                system_prompt = vomo.PROMPT_FIDELIDADE
            
            import tempfile
            from pathlib import Path
            
            video_name = Path(file_path).stem
            await emit("formatting", 70, "Formatando documento com IA...")
            
            with tempfile.TemporaryDirectory() as temp_dir:
                final_text = await vomo.format_transcription_async(
                    transcription_text,
                    video_name=video_name,
                    output_folder=temp_dir,
                    mode=mode,
                    custom_prompt=system_prompt,
                    progress_callback=emit
                )
            
            await emit("formatting", 95, "Documento formatado ✓")
            
            # Stage 4: HIL Audit (95-98%) - Analyze for issues
            await emit("audit", 96, "Auditando qualidade do documento...")
            analysis_report = None
            validation_report = None
            report_paths = {}
            try:
                from app.services.quality_service import quality_service
                analysis_report = await quality_service.analyze_structural_issues(
                    content=final_text,
                    document_name=video_name,
                    raw_content=transcription_text
                )
                validation_report = await quality_service.validate_document_full(
                    raw_content=transcription_text,
                    formatted_content=final_text,
                    document_name=video_name
                )

                issues = []
                for sec in (analysis_report or {}).get("duplicate_sections", [])[:10]:
                    title = sec.get("title") or sec.get("similar_to") or "Sem título"
                    issues.append({
                        "id": f"dup_sec_{hash(title) % 10000}",
                        "type": "duplicate_section",
                        "fix_type": "structural",
                        "severity": "warning",
                        "title": title,
                        "description": f"Seção duplicada: {title}",
                        "suggestion": "Mesclar ou remover duplicata"
                    })

                heading_issues = (analysis_report or {}).get("heading_numbering_issues", [])
                if heading_issues:
                    issues.append({
                        "id": f"heading_numbering_{hash(video_name) % 10000}",
                        "type": "heading_numbering",
                        "fix_type": "structural",
                        "severity": "info",
                        "description": heading_issues[0].get(
                            "description",
                            "Numeração de títulos H2 fora de sequência ou ausente."
                        ),
                        "suggestion": "Renumerar automaticamente os títulos H2 na ordem atual"
                    })

                for para in (analysis_report or {}).get("duplicate_paragraphs", [])[:10]:
                    fingerprint = para.get("fingerprint") or ""
                    issues.append({
                        "id": f"dup_para_{fingerprint or hash(para.get('preview', '')[:50]) % 10000}",
                        "type": "duplicate_paragraph",
                        "fix_type": "structural",
                        "severity": "info",
                        "fingerprint": fingerprint,
                        "description": f"Parágrafo repetido: {para.get('preview', '')[:80]}...",
                        "suggestion": "Remover repetição"
                    })

                for law in (analysis_report or {}).get("missing_laws", [])[:8]:
                    issues.append({
                        "id": f"missing_law_{hash(law) % 10000}",
                        "type": "missing_law",
                        "fix_type": "content",
                        "severity": "warning",
                        "description": f"Lei possivelmente ausente: {law}",
                        "suggestion": "Inserir referência contextual ou revisar trecho"
                    })

                for item in (analysis_report or {}).get("missing_sumulas", [])[:8]:
                    issues.append({
                        "id": f"missing_sumula_{hash(item) % 10000}",
                        "type": "missing_sumula",
                        "fix_type": "content",
                        "severity": "warning",
                        "description": f"Súmula possivelmente ausente: {item}",
                        "suggestion": "Inserir referência contextual ou revisar trecho"
                    })

                for item in (analysis_report or {}).get("missing_decretos", [])[:6]:
                    issues.append({
                        "id": f"missing_decreto_{hash(item) % 10000}",
                        "type": "missing_decreto",
                        "fix_type": "content",
                        "severity": "info",
                        "description": f"Decreto possivelmente ausente: {item}",
                        "suggestion": "Inserir referência contextual ou revisar trecho"
                    })

                for item in (analysis_report or {}).get("missing_julgados", [])[:6]:
                    issues.append({
                        "id": f"missing_julgado_{hash(item) % 10000}",
                        "type": "missing_julgado",
                        "fix_type": "content",
                        "severity": "info",
                        "description": f"Julgado possivelmente ausente: {item}",
                        "suggestion": "Inserir referência contextual ou revisar trecho"
                    })

                compression_warning = (analysis_report or {}).get("compression_warning")
                if compression_warning:
                    issues.append({
                        "id": f"compression_{hash(compression_warning) % 10000}",
                        "type": "compression_warning",
                        "fix_type": "content",
                        "severity": "warning",
                        "description": str(compression_warning),
                        "suggestion": "Revisar partes possivelmente condensadas demais"
                    })

                report_paths = self._persist_transcription_outputs(
                    video_name=video_name,
                    mode=mode,
                    raw_text=transcription_text,
                    formatted_text=final_text,
                    analysis_report=analysis_report,
                    validation_report=validation_report,
                )

                # Emit audit results for HIL review
                await emit("audit_complete", 98, json.dumps({
                    "issues": issues,
                    "total_issues": len(issues),
                    "document_preview": final_text[:2000] if final_text else "",
                    "reports": report_paths
                }))

            except Exception as audit_error:
                logger.warning(f"Auditoria HIL falhou (não-bloqueante): {audit_error}")
                report_paths = self._persist_transcription_outputs(
                    video_name=video_name,
                    mode=mode,
                    raw_text=transcription_text,
                    formatted_text=final_text,
                    analysis_report=None,
                    validation_report=None,
                )
                await emit("audit_complete", 98, json.dumps({"issues": [], "total_issues": 0}))

            await emit("formatting", 100, "Documento finalizado ✓")
            return {"content": final_text, "reports": report_paths}

        except Exception as e:
            logger.error(f"Erro no serviço de transcrição (SSE): {e}")
            raise e

    async def process_batch_with_progress(
        self, 
        file_paths: list,
        file_names: list,
        mode: str = "APOSTILA", 
        thinking_level: str = "medium",
        custom_prompt: Optional[str] = None,
        high_accuracy: bool = False,
        on_progress: Optional[Callable[[str, int, str], Awaitable[None]]] = None,
        model_selection: Optional[str] = None
    ) -> dict:
        """
        Process multiple files in sequence, unifying transcriptions.
        
        Args:
            file_paths: List of paths to audio/video files
            file_names: List of original filenames for display
            mode: APOSTILA, FIDELIDADE, or RAW
            on_progress: async callable(stage, progress, message)
        
        Returns:
            Unified transcription text
        """
        async def emit(stage: str, progress: int, message: str):
            if on_progress:
                await on_progress(stage, progress, message)
        
        try:
            vomo = self._get_vomo(model_selection=model_selection, thinking_level=thinking_level)
            total_files = len(file_paths)
            all_raw_transcriptions = []
            
            logger.info(f"🎤 Iniciando processamento em lote: {total_files} arquivos [{mode}]")
            
            for idx, (file_path, file_name) in enumerate(zip(file_paths, file_names)):
                file_num = idx + 1
                # Calculate progress range for this file (each file gets equal share of 0-60%)
                file_progress_base = int((idx / total_files) * 60)
                file_progress_increment = int(60 / total_files)
                
                # Stage: Audio optimization for this file
                await emit("batch", file_progress_base, f"[{file_num}/{total_files}] Otimizando áudio: {file_name}")
                audio_path = await asyncio.to_thread(vomo.optimize_audio, file_path)
                await emit("batch", file_progress_base + 5, f"[{file_num}/{total_files}] Áudio OK: {file_name}")
                
                # Stage: Transcription for this file
                transcribe_progress = file_progress_base + int(file_progress_increment * 0.3)
                await emit("batch", transcribe_progress, f"[{file_num}/{total_files}] Whisper Transcrevendo: {file_name}")
                audio_duration = self._get_wav_duration_seconds(audio_path)
                rtf_estimate = 1.6 if high_accuracy else 0.9
                estimated_total = audio_duration * rtf_estimate if audio_duration > 0 else 0.0
                done_event = asyncio.Event()
                ticker = asyncio.create_task(
                    self._emit_progress_while_running(
                        emit,
                        done_event,
                        "batch",
                        transcribe_progress,
                        file_progress_base + file_progress_increment - 1,
                        f"[{file_num}/{total_files}] Transcrevendo",
                        estimated_total,
                        interval_seconds=3.0
                    )
                )
                
                if high_accuracy:
                    logger.info(f"🎯 Usando Beam Search para {file_name}")
                    transcription_text = await asyncio.to_thread(vomo.transcribe_beam_search, audio_path)
                else:
                    transcription_text = await asyncio.to_thread(vomo.transcribe, audio_path)
                done_event.set()
                try:
                    await ticker
                except Exception:
                    pass
                
                # Add to collection with part separator
                part_header = f"## PARTE {file_num}: {file_name}"
                all_raw_transcriptions.append(f"{part_header}\n\n{transcription_text}")
                
                complete_progress = file_progress_base + file_progress_increment
                await emit("batch", complete_progress, f"[{file_num}/{total_files}] ✓ Concluído: {file_name}")
            
            # Unified raw transcription with separators
            await emit("batch", 60, f"Unificando {total_files} transcrições...")
            unified_raw = "\n\n---\n\n".join(all_raw_transcriptions)
            
            if mode == "RAW":
                await emit("batch", 100, "Transcrição bruta unificada ✓")
                return unified_raw
            
            # Stage 3: Format unified document (60-100%)
            await emit("formatting", 65, "Preparando formatação unificada...")
            
            # Configure prompt
            system_prompt = None
            if custom_prompt:
                system_prompt = custom_prompt
            elif mode == "APOSTILA":
                system_prompt = vomo.PROMPT_APOSTILA_ACTIVE
            elif mode == "FIDELIDADE":
                system_prompt = vomo.PROMPT_FIDELIDADE
            
            import tempfile
            
            # Use first file name as base for the unified document
            base_name = file_names[0].rsplit('.', 1)[0] if file_names else "Aulas_Unificadas"
            video_name = f"{base_name}_UNIFICADO"
            
            await emit("formatting", 70, "Formatando documento unificado com IA...")
            
            with tempfile.TemporaryDirectory() as temp_dir:
                final_text = await vomo.format_transcription_async(
                    unified_raw,
                    video_name=video_name,
                    output_folder=temp_dir,
                    mode=mode,
                    custom_prompt=system_prompt,
                    progress_callback=emit
                )

            # Stage 4: HIL Audit (95-98%) - Analyze for issues
            await emit("audit", 96, "Auditando qualidade do documento unificado...")
            analysis_report = None
            validation_report = None
            report_paths = {}
            try:
                from app.services.quality_service import quality_service
                analysis_report = await quality_service.analyze_structural_issues(
                    content=final_text,
                    document_name=video_name,
                    raw_content=unified_raw
                )
                validation_report = await quality_service.validate_document_full(
                    raw_content=unified_raw,
                    formatted_content=final_text,
                    document_name=video_name
                )

                issues = []
                for sec in (analysis_report or {}).get("duplicate_sections", [])[:10]:
                    title = sec.get("title") or sec.get("similar_to") or "Sem título"
                    issues.append({
                        "id": f"dup_sec_{hash(title) % 10000}",
                        "type": "duplicate_section",
                        "fix_type": "structural",
                        "severity": "warning",
                        "title": title,
                        "description": f"Seção duplicada: {title}",
                        "suggestion": "Mesclar ou remover duplicata"
                    })

                heading_issues = (analysis_report or {}).get("heading_numbering_issues", [])
                if heading_issues:
                    issues.append({
                        "id": f"heading_numbering_{hash(video_name) % 10000}",
                        "type": "heading_numbering",
                        "fix_type": "structural",
                        "severity": "info",
                        "description": heading_issues[0].get(
                            "description",
                            "Numeração de títulos H2 fora de sequência ou ausente."
                        ),
                        "suggestion": "Renumerar automaticamente os títulos H2 na ordem atual"
                    })

                for para in (analysis_report or {}).get("duplicate_paragraphs", [])[:10]:
                    fingerprint = para.get("fingerprint") or ""
                    issues.append({
                        "id": f"dup_para_{fingerprint or hash(para.get('preview', '')[:50]) % 10000}",
                        "type": "duplicate_paragraph",
                        "fix_type": "structural",
                        "severity": "info",
                        "fingerprint": fingerprint,
                        "description": f"Parágrafo repetido: {para.get('preview', '')[:80]}...",
                        "suggestion": "Remover repetição"
                    })

                for law in (analysis_report or {}).get("missing_laws", [])[:8]:
                    issues.append({
                        "id": f"missing_law_{hash(law) % 10000}",
                        "type": "missing_law",
                        "fix_type": "content",
                        "severity": "warning",
                        "description": f"Lei possivelmente ausente: {law}",
                        "suggestion": "Inserir referência contextual ou revisar trecho"
                    })

                for item in (analysis_report or {}).get("missing_sumulas", [])[:8]:
                    issues.append({
                        "id": f"missing_sumula_{hash(item) % 10000}",
                        "type": "missing_sumula",
                        "fix_type": "content",
                        "severity": "warning",
                        "description": f"Súmula possivelmente ausente: {item}",
                        "suggestion": "Inserir referência contextual ou revisar trecho"
                    })

                for item in (analysis_report or {}).get("missing_decretos", [])[:6]:
                    issues.append({
                        "id": f"missing_decreto_{hash(item) % 10000}",
                        "type": "missing_decreto",
                        "fix_type": "content",
                        "severity": "info",
                        "description": f"Decreto possivelmente ausente: {item}",
                        "suggestion": "Inserir referência contextual ou revisar trecho"
                    })

                for item in (analysis_report or {}).get("missing_julgados", [])[:6]:
                    issues.append({
                        "id": f"missing_julgado_{hash(item) % 10000}",
                        "type": "missing_julgado",
                        "fix_type": "content",
                        "severity": "info",
                        "description": f"Julgado possivelmente ausente: {item}",
                        "suggestion": "Inserir referência contextual ou revisar trecho"
                    })

                compression_warning = (analysis_report or {}).get("compression_warning")
                if compression_warning:
                    issues.append({
                        "id": f"compression_{hash(compression_warning) % 10000}",
                        "type": "compression_warning",
                        "fix_type": "content",
                        "severity": "warning",
                        "description": str(compression_warning),
                        "suggestion": "Revisar partes possivelmente condensadas demais"
                    })

                report_paths = self._persist_transcription_outputs(
                    video_name=video_name,
                    mode=mode,
                    raw_text=unified_raw,
                    formatted_text=final_text,
                    analysis_report=analysis_report,
                    validation_report=validation_report,
                )

                await emit("audit_complete", 98, json.dumps({
                    "issues": issues,
                    "total_issues": len(issues),
                    "document_preview": final_text[:2000] if final_text else "",
                    "reports": report_paths
                }))
            except Exception as audit_error:
                logger.warning(f"Auditoria HIL falhou (não-bloqueante): {audit_error}")
                report_paths = self._persist_transcription_outputs(
                    video_name=video_name,
                    mode=mode,
                    raw_text=unified_raw,
                    formatted_text=final_text,
                    analysis_report=None,
                    validation_report=None,
                )
                await emit("audit_complete", 98, json.dumps({"issues": [], "total_issues": 0}))

            await emit("formatting", 100, f"Documento unificado ({total_files} partes) ✓")
            return {"content": final_text, "reports": report_paths}

        except Exception as e:
            logger.error(f"Erro no serviço de transcrição em lote: {e}")
            raise e

    def _sanitize_case_id(self, case_id: str) -> str:
        if not case_id:
            return "case"
        safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", case_id).strip("_")
        return safe or "case"

    def _get_hearing_case_dir(self, case_id: str) -> Path:
        try:
            from app.core.config import settings
            base_dir = Path(settings.LOCAL_STORAGE_PATH) / "hearings"
        except Exception:
            base_dir = Path("./storage") / "hearings"
        safe_case_id = self._sanitize_case_id(case_id)
        case_dir = base_dir / safe_case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        return case_dir

    def _compute_file_hash(self, file_path: str) -> str:
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as handle:
            for chunk in iter(lambda: handle.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _load_speaker_registry(self, case_id: str) -> dict:
        case_dir = self._get_hearing_case_dir(case_id)
        registry_path = case_dir / "speaker_registry.json"
        if registry_path.exists():
            try:
                return json.loads(registry_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {
            "case_id": case_id,
            "roles": [
                "juiz",
                "mp",
                "defesa",
                "testemunha",
                "serventuario",
                "parte",
                "perito",
                "outro",
            ],
            "speakers": [],
            "updated_at": datetime.utcnow().isoformat(),
        }

    def _save_speaker_registry(self, case_id: str, registry: dict) -> Path:
        case_dir = self._get_hearing_case_dir(case_id)
        registry_path = case_dir / "speaker_registry.json"
        registry["updated_at"] = datetime.utcnow().isoformat()
        registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
        return registry_path

    def _ensure_registry_speakers(self, registry: dict, speaker_labels: list[str]) -> tuple[list[dict], dict]:
        speakers = registry.get("speakers", [])
        label_map = {sp.get("label"): sp for sp in speakers if sp.get("label")}
        for label in speaker_labels:
            if label not in label_map:
                speaker_id = f"spk_{uuid.uuid4().hex[:8]}"
                new_speaker = {
                    "speaker_id": speaker_id,
                    "label": label,
                    "name": label,
                    "role": "outro",
                    "confidence": 0.0,
                    "source": "auto",
                    "enrollment_files": [],
                }
                speakers.append(new_speaker)
                label_map[label] = new_speaker
        registry["speakers"] = speakers
        return speakers, {label: label_map[label]["speaker_id"] for label in label_map}

    def _extract_timestamp_hint(self, text: str) -> Optional[str]:
        if not text:
            return None
        match = re.search(r"\[(\d{1,2}:\d{2}(?::\d{2})?)\]", text)
        if match:
            return match.group(1)
        return None

    def _build_hearing_segments(self, vomo, transcription_text: str) -> list[dict]:
        segments = []
        try:
            raw_segments = vomo._segment_raw_transcription(transcription_text)
        except Exception:
            raw_segments = [{"speaker": "SPEAKER 1", "content": transcription_text or ""}]
        for idx, seg in enumerate(raw_segments):
            content = (seg.get("content") or "").strip()
            segments.append({
                "id": f"seg_{idx + 1:04d}",
                "start": None,
                "end": None,
                "speaker_label": seg.get("speaker") or "SPEAKER 1",
                "text": content,
                "timestamp_hint": self._extract_timestamp_hint(content),
            })
        return segments

    def _build_hearing_segments_from_asr(self, asr_segments: list[dict]) -> list[dict]:
        segments = []
        for idx, seg in enumerate(asr_segments):
            start = seg.get("start")
            segments.append({
                "id": f"seg_{idx + 1:04d}",
                "start": start,
                "end": seg.get("end"),
                "speaker_label": seg.get("speaker_label") or "SPEAKER 1",
                "text": (seg.get("text") or "").strip(),
                "timestamp_hint": self._format_seconds_timestamp(start),
            })
        return segments

    def _score_text(self, text: str) -> tuple[int, list[str]]:
        if not text:
            return 0, []
        score = 0
        reasons = []

        if re.search(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", text):
            score += 15
            reasons.append("data")
        if re.search(r"\bR\$\s?\d+|\b\d+[.,]\d+\b", text):
            score += 12
            reasons.append("valor")
        if re.search(r"\b(não|nunca|jamais)\b", text, re.IGNORECASE):
            score += 8
            reasons.append("negacao")
        if re.search(r"\b(confesso|admito|reconheço|reconheco)\b", text, re.IGNORECASE):
            score += 15
            reasons.append("confissao")
        if re.search(r"\b(documento|prova|whatsapp|áudio|audio|vídeo|video)\b", text, re.IGNORECASE):
            score += 10
            reasons.append("prova_documental")
        if re.search(r"\b(juiz|promotor|defesa|testemunha)\b", text, re.IGNORECASE):
            score += 5
            reasons.append("papel")

        return min(score, 100), reasons

    def _build_hearing_blocks(self, segments: list[dict], act_map: Optional[dict] = None) -> list[dict]:
        blocks = []
        current = None
        for seg in segments:
            seg_id = seg.get("id")
            act_info = act_map.get(seg_id, {}) if act_map else {}
            act_type = act_info.get("act_type") or "turn"
            topic = act_info.get("topic")
            score, reasons = self._score_text(seg.get("text", ""))

            if current and current["act_type"] == act_type and current["speaker_label"] == seg.get("speaker_label"):
                current["segment_ids"].append(seg_id)
                current["text"] = f"{current['text']}\n{seg.get('text', '').strip()}"
                current["score_sum"] += score
                current["score_count"] += 1
                current["relevance_reasons"] = list(set(current["relevance_reasons"] + reasons))
                if topic:
                    current_topics = set(current.get("topics", []))
                    current_topics.add(topic)
                    current["topics"] = sorted(current_topics)
                continue

            block_id = f"blk_{seg_id}"
            current = {
                "id": block_id,
                "segment_ids": [seg_id],
                "speaker_label": seg.get("speaker_label"),
                "act_type": act_type,
                "text": seg.get("text"),
                "score_sum": score,
                "score_count": 1,
                "relevance_reasons": reasons,
                "topics": [topic] if topic else [],
            }
            blocks.append(current)

        for block in blocks:
            count = block.pop("score_count", 1)
            score_sum = block.pop("score_sum", 0)
            block["relevance_score"] = min(100, int(score_sum / max(count, 1)))

        return blocks

    def _build_hearing_evidence(self, blocks: list[dict]) -> list[dict]:
        evidence = []
        idx = 1
        for block in blocks:
            if (block.get("relevance_score") or 0) < 40:
                continue
            quote = (block.get("text") or "").strip()
            if not quote:
                continue
            evidence.append({
                "id": f"ev_{idx:04d}",
                "block_id": block["id"],
                "segment_ids": block.get("segment_ids") or [],
                "quote_verbatim": quote[:400],
                "claim_normalized": "",
                "topics": [],
                "relevance_score": block.get("relevance_score", 0),
                "relevance_reasons": block.get("relevance_reasons") or [],
                "source": "heuristic",
            })
            idx += 1
        return evidence

    def _safe_json_extract(self, text: str):
        if not text:
            return None
        cleaned = text.strip().replace("```json", "").replace("```", "")
        for pattern in (r"\[[\s\S]*\]", r"\{[\s\S]*\}"):
            match = re.search(pattern, cleaned)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    return None
        return None

    async def _llm_generate_json(self, vomo, prompt: str, max_tokens: int = 1500, temperature: float = 0.2):
        if not vomo or not hasattr(vomo, "client"):
            return None

        if getattr(vomo, "provider", "") == "openai":
            client = getattr(vomo, "openai_client", None)
            model = getattr(vomo, "openai_model", "gpt-5-mini-2025-08-07")
            if client:
                response = await client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "Responda apenas com JSON válido."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=temperature,
                    max_completion_tokens=max_tokens,
                )
                return self._safe_json_extract(response.choices[0].message.content or "")

            def call_openai():
                response = vomo.client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "Responda apenas com JSON válido."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=temperature,
                    max_completion_tokens=max_tokens,
                )
                return response.choices[0].message.content or ""

            response_text = await asyncio.to_thread(call_openai)
            return self._safe_json_extract(response_text)

        try:
            from google.genai import types
        except Exception:
            types = None

        def call_gemini():
            config = None
            if types:
                config = types.GenerateContentConfig(
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                    thinking_config=types.ThinkingConfig(
                        include_thoughts=False,
                        thinking_level="LOW"
                    ),
                )
            return vomo.client.models.generate_content(
                model=vomo.llm_model,
                contents=prompt,
                config=config,
            )

        response = await asyncio.to_thread(call_gemini)
        response_text = response.text if hasattr(response, "text") else str(response)
        return self._safe_json_extract(response_text)

    def _coerce_act_type(self, act_type: str) -> str:
        if not act_type:
            return "turn"
        allowed = {
            "pergunta",
            "resposta",
            "contradita",
            "esclarecimento",
            "decisao",
            "encaminhamento",
            "leitura",
            "turn",
            "outro",
        }
        normalized = act_type.strip().lower().replace("ç", "c")
        return normalized if normalized in allowed else "turn"

    def _guess_act_type(self, text: str) -> str:
        if not text:
            return "turn"
        lowered = text.lower()
        if "?" in text:
            return "pergunta"
        if any(token in lowered for token in ("respondo", "sim", "não", "nao")):
            return "resposta"
        if any(token in lowered for token in ("decido", "defiro", "indefiro", "fica decidido")):
            return "decisao"
        if any(token in lowered for token in ("encaminho", "determino", "designo", "ficou marcado")):
            return "encaminhamento"
        if any(token in lowered for token in ("leitura", "consta", "documento", "oficio")):
            return "leitura"
        return "turn"

    async def _classify_segments_act_with_llm(
        self,
        segments: list[dict],
        speakers: list[dict],
        goal: str,
        vomo,
        max_segments: int = 200,
        batch_size: int = 25,
    ) -> tuple[dict, list[str]]:
        act_map: dict = {}
        warnings: list[str] = []
        if not segments:
            return act_map, warnings

        if len(segments) > max_segments:
            warnings.append("act_classification_truncated")
        batch_targets = segments[:max_segments]
        speaker_map = {sp.get("speaker_id"): sp for sp in speakers}

        for i in range(0, len(batch_targets), batch_size):
            batch = batch_targets[i:i + batch_size]
            items = []
            for seg in batch:
                speaker_id = seg.get("speaker_id")
                speaker = speaker_map.get(speaker_id, {})
                items.append({
                    "id": seg.get("id"),
                    "speaker_label": seg.get("speaker_label"),
                    "role": speaker.get("role"),
                    "text": (seg.get("text") or "")[:400],
                })

            prompt = f"""Classifique trechos de audiência em atos processuais.

Atos possíveis: pergunta, resposta, contradita, esclarecimento, decisao, encaminhamento, leitura, outro.
Para cada item, retorne id, act_type e um topic curto (tema).

Responda em JSON:
{{"segments":[{{"id":"seg_0001","act_type":"pergunta","topic":"tema"}}]}}

Itens:
{json.dumps(items, ensure_ascii=False)}
"""

            parsed = await self._llm_generate_json(vomo, prompt, max_tokens=1200, temperature=0.2)
            if not parsed or "segments" not in parsed:
                for seg in batch:
                    act_map[seg.get("id")] = {
                        "act_type": self._guess_act_type(seg.get("text", "")),
                        "topic": None,
                    }
                continue

            for entry in parsed.get("segments", []):
                seg_id = entry.get("id")
                if not seg_id:
                    continue
                act_map[seg_id] = {
                    "act_type": self._coerce_act_type(entry.get("act_type")),
                    "topic": entry.get("topic"),
                }

        for seg in segments[max_segments:]:
            act_map[seg.get("id")] = {
                "act_type": self._guess_act_type(seg.get("text", "")),
                "topic": None,
            }

        return act_map, warnings

    async def _extract_claims_with_llm(
        self,
        evidence: list[dict],
        speakers: list[dict],
        goal: str,
        vomo
    ) -> list[dict]:
        """
        Usa LLM para extrair afirmações factuais estruturadas (claim_normalized) e tópicos.
        
        Args:
            evidence: Lista de evidências com quote_verbatim populado
            speakers: Lista de falantes para contexto
            goal: Objetivo jurídico (peticao_inicial, contestacao, alegacoes_finais, sentenca)
            vomo: Instância VomoMLX com cliente LLM
            
        Returns:
            Lista de evidências enriquecidas com claim_normalized e topics
        """
        if not evidence or not hasattr(vomo, 'client'):
            return evidence
            
        goal_context = {
            "peticao_inicial": "petição inicial (autor buscando provas de direito violado)",
            "contestacao": "contestação (réu buscando elementos de defesa)",
            "alegacoes_finais": "alegações finais (momento de síntese probatória)",
            "sentenca": "fundamentação de sentença (análise de provas para decisão)"
        }
        
        goal_desc = goal_context.get(goal, "análise jurídica geral")
        enriched_map = {}
        batch_size = 4

        if len(evidence) > 80:
            ranked = sorted(
                list(enumerate(evidence)),
                key=lambda item: item[1].get("relevance_score", 0),
                reverse=True
            )[:80]
            target_indices = [idx for idx, _ in ranked]
        else:
            target_indices = list(range(len(evidence)))

        selected = [evidence[idx] for idx in target_indices]
        
        for i in range(0, len(selected), batch_size):
            batch = selected[i:i+batch_size]
            quotes_text = ""
            for idx, ev in enumerate(batch):
                quotes_text += f"\n[{idx+1}] \"{ev.get('quote_verbatim', '')}\"\n"
            
            extraction_prompt = f"""Você é um assistente jurídico especializado em análise de audiências.

OBJETIVO: Extrair afirmações factuais estruturadas para uso em {goal_desc}.

Para cada trecho abaixo, extraia:
1. claim_normalized: afirmação factual técnica (quem + fez/disse + o quê + quando/onde), até 2 frases.
2. topics: 1-3 tópicos legais (ex: autoria, materialidade, nexo_causal, dano, confissao, alibi, prova_documental, contradicao).
3. polarity: "affirm" ou "deny".
4. confidence: número entre 0 e 1.
5. time_refs: datas/horários citados (se houver).

TRECHOS:
{quotes_text}

Responda APENAS com JSON válido:
[{{"idx": 1, "claim_normalized": "...", "topics": ["..."], "polarity": "affirm", "confidence": 0.7, "time_refs": []}}]
"""
            
            try:
                parsed = await self._llm_generate_json(vomo, extraction_prompt, max_tokens=1800, temperature=0.25)
                if parsed:
                    extraction_map = {ex.get("idx"): ex for ex in parsed}
                    for idx, ev in enumerate(batch):
                        ex = extraction_map.get(idx + 1, {})
                        ev["claim_normalized"] = ex.get("claim_normalized", "")
                        ev["topics"] = ex.get("topics", [])
                        ev["polarity"] = ex.get("polarity", "affirm")
                        ev["confidence"] = ex.get("confidence", 0.5)
                        ev["time_refs"] = ex.get("time_refs", [])
                        ev["source"] = "llm"
                        enriched_map[target_indices[i + idx]] = ev
            except Exception as e:
                logger.warning(f"Falha ao extrair claims via LLM: {e}")

        final = []
        for idx, ev in enumerate(evidence):
            final.append(enriched_map.get(idx, ev))

        return final

    def _build_claims_from_evidence(self, evidence: list[dict], segments: list[dict]) -> list[dict]:
        segment_map = {seg.get("id"): seg for seg in segments}
        claims = []
        for idx, ev in enumerate(evidence):
            seg_ids = ev.get("segment_ids") or []
            first_seg = segment_map.get(seg_ids[0]) if seg_ids else None
            claims.append({
                "id": f"cl_{idx + 1:04d}",
                "segment_ids": seg_ids,
                "speaker_id": first_seg.get("speaker_id") if first_seg else None,
                "speaker_label": first_seg.get("speaker_label") if first_seg else None,
                "quote_verbatim": ev.get("quote_verbatim"),
                "claim_normalized": ev.get("claim_normalized"),
                "topics": ev.get("topics") or [],
                "polarity": ev.get("polarity", "affirm"),
                "confidence": ev.get("confidence", 0.5),
                "time_refs": ev.get("time_refs", []),
                "relevance_score": ev.get("relevance_score", 0),
                "relevance_reasons": ev.get("relevance_reasons", []),
            })
        return claims

    def _extract_numbers(self, text: str) -> list[str]:
        if not text:
            return []
        numbers = re.findall(r"\b\d+(?:[.,]\d+)?\b", text)
        return numbers

    def _detect_contradictions(self, claims: list[dict]) -> list[dict]:
        contradictions = []
        if not claims:
            return contradictions
        topic_map: dict[str, list[dict]] = {}
        for cl in claims:
            topics = cl.get("topics") or ["geral"]
            for topic in topics:
                topic_map.setdefault(topic, []).append(cl)

        idx = 1
        for topic, items in topic_map.items():
            polarities = {item.get("polarity") for item in items if item.get("polarity")}
            numbers = set()
            for item in items:
                numbers.update(self._extract_numbers(item.get("claim_normalized", "")))

            if len(polarities) > 1 or len(numbers) > 1:
                contradictions.append({
                    "id": f"ctr_{idx:04d}",
                    "topic": topic,
                    "claim_ids": [item.get("id") for item in items],
                    "reason": "polaridade_oposta" if len(polarities) > 1 else "valores_divergentes",
                    "samples": [item.get("claim_normalized") for item in items[:3]],
                })
                idx += 1

        return contradictions

    def _extract_dates_from_text(self, text: str) -> list[str]:
        if not text:
            return []
        dates = re.findall(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", text)
        months = {
            "janeiro": "01",
            "fevereiro": "02",
            "marco": "03",
            "março": "03",
            "abril": "04",
            "maio": "05",
            "junho": "06",
            "julho": "07",
            "agosto": "08",
            "setembro": "09",
            "outubro": "10",
            "novembro": "11",
            "dezembro": "12",
        }
        text_lower = text.lower()
        for month, number in months.items():
            match = re.search(rf"(\d{{1,2}})\s+de\s+{month}\s+de\s+(\d{{4}})", text_lower)
            if match:
                day = match.group(1).zfill(2)
                year = match.group(2)
                dates.append(f"{day}/{number}/{year}")
        return dates

    def _build_timeline(self, claims: list[dict], segments: list[dict]) -> list[dict]:
        timeline = []
        segment_map = {seg.get("id"): seg for seg in segments}
        idx = 1
        for cl in claims:
            dates = cl.get("time_refs") or self._extract_dates_from_text(cl.get("claim_normalized", ""))
            if not dates:
                continue
            seg_ids = cl.get("segment_ids") or []
            first_seg = segment_map.get(seg_ids[0]) if seg_ids else None
            for date_str in dates:
                timeline.append({
                    "id": f"tl_{idx:04d}",
                    "date": date_str,
                    "claim_id": cl.get("id"),
                    "segment_ids": seg_ids,
                    "speaker_id": cl.get("speaker_id"),
                    "summary": cl.get("claim_normalized"),
                    "audio_timestamp": first_seg.get("timestamp_hint") if first_seg else None,
                })
                idx += 1

        return timeline

    def _apply_goal_based_relevance(
        self,
        evidence: list[dict],
        goal: str,
        speakers: list[dict]
    ) -> list[dict]:
        """
        Ajusta scores de relevância baseado no objetivo jurídico.
        """
        goal_boosts = {
            "peticao_inicial": {"confissao": 20, "dano": 15, "nexo_causal": 15, "valor": 10},
            "contestacao": {"negacao": 15, "alibi": 20, "contradicao": 15},
            "alegacoes_finais": {"confissao": 15, "nexo_causal": 15, "materialidade": 15, "autoria": 15},
            "sentenca": {"confissao": 10, "prova_documental": 15, "materialidade": 15, "autoria": 15}
        }
        boosts = goal_boosts.get(goal, {})
        
        for ev in evidence:
            for topic in ev.get("topics", []):
                topic_lower = topic.lower().replace(" ", "_")
                ev["relevance_score"] = min(100, ev.get("relevance_score", 0) + boosts.get(topic_lower, 0))
            for reason in ev.get("relevance_reasons", []):
                ev["relevance_score"] = min(100, ev.get("relevance_score", 0) + boosts.get(reason, 0))
        
        return evidence

    def _format_seconds_timestamp(self, seconds: Optional[float]) -> Optional[str]:
        if seconds is None:
            return None
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"


    def _get_embeddings_path(self, case_id: str) -> Path:
        case_dir = self._get_hearing_case_dir(case_id)
        return case_dir / "speaker_embeddings.json"

    def _load_speaker_embeddings(self, case_id: str) -> dict:
        embeddings_path = self._get_embeddings_path(case_id)
        if embeddings_path.exists():
            try:
                return json.loads(embeddings_path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_speaker_embeddings(self, case_id: str, data: dict) -> Path:
        embeddings_path = self._get_embeddings_path(case_id)
        embeddings_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return embeddings_path

    def _load_audio_samples(self, audio_path: str) -> tuple[Optional["np.ndarray"], Optional[int]]:
        try:
            import soundfile as sf
            audio, sr = sf.read(audio_path, always_2d=False)
            return audio, sr
        except Exception:
            try:
                import librosa
                audio, sr = librosa.load(audio_path, sr=None, mono=True)
                return audio, sr
            except Exception:
                return None, None

    def _compute_mfcc_embedding(self, audio: "np.ndarray", sr: int) -> Optional[list[float]]:
        try:
            import numpy as np
            import librosa
            if audio is None or sr is None:
                return None
            if audio.ndim > 1:
                audio = np.mean(audio, axis=1)
            mfcc = librosa.feature.mfcc(y=audio, sr=sr, n_mfcc=20)
            if mfcc.size == 0:
                return None
            embedding = np.mean(mfcc, axis=1)
            return embedding.astype(float).tolist()
        except Exception:
            return None

    def _get_ecapa_classifier(self):
        if hasattr(self, "_ecapa_classifier"):
            return self._ecapa_classifier
        try:
            from speechbrain.pretrained import EncoderClassifier
        except Exception:
            try:
                from speechbrain.inference import EncoderClassifier
            except Exception:
                self._ecapa_classifier = None
                return None
        try:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            classifier = EncoderClassifier.from_hparams(
                source="speechbrain/spkrec-ecapa-voxceleb",
                savedir="pretrained_models/spkrec-ecapa-voxceleb",
                run_opts={"device": device},
            )
            self._ecapa_classifier = classifier
            return classifier
        except Exception:
            self._ecapa_classifier = None
            return None

    def _compute_ecapa_embedding(self, audio: "np.ndarray", sr: int, classifier) -> Optional[list[float]]:
        try:
            import numpy as np
            import torch
            if audio is None or sr is None or classifier is None:
                return None
            if audio.ndim > 1:
                audio = np.mean(audio, axis=1)
            if sr != 16000:
                import librosa
                audio = librosa.resample(audio, orig_sr=sr, target_sr=16000)
                sr = 16000
            if len(audio) < sr * 0.3:
                return None
            tensor = torch.tensor(audio, dtype=torch.float32).unsqueeze(0)
            with torch.no_grad():
                emb = classifier.encode_batch(tensor)
            emb = emb.squeeze().detach().cpu().numpy()
            return emb.astype(float).tolist()
        except Exception:
            return None

    def _compute_voice_embedding(self, audio: "np.ndarray", sr: int, classifier=None) -> tuple[Optional[list[float]], Optional[str]]:
        if classifier is None:
            classifier = self._get_ecapa_classifier()
        if classifier is not None:
            embedding = self._compute_ecapa_embedding(audio, sr, classifier)
            if embedding:
                return embedding, "ecapa"
        embedding = self._compute_mfcc_embedding(audio, sr)
        if embedding:
            return embedding, "mfcc"
        return None, None

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        import numpy as np
        va = np.array(a, dtype=float)
        vb = np.array(b, dtype=float)
        denom = (np.linalg.norm(va) * np.linalg.norm(vb)) or 1.0
        return float(np.dot(va, vb) / denom)

    def _compute_label_embeddings(self, audio_path: str, segments: list[dict]) -> dict:
        import numpy as np

        audio, sr = self._load_audio_samples(audio_path)
        if audio is None or sr is None:
            return {}

        # Collect up to 60s of audio per speaker_label
        speaker_spans: dict[str, list[tuple[float, float]]] = {}
        for seg in segments:
            start = seg.get("start")
            end = seg.get("end")
            label = seg.get("speaker_label")
            if start is None or end is None or not label:
                continue
            speaker_spans.setdefault(label, []).append((float(start), float(end)))

        classifier = self._get_ecapa_classifier()
        label_embeddings = {}
        for label, spans in speaker_spans.items():
            total = 0.0
            embeddings = []
            method_used = None
            for start, end in spans:
                duration = max(0.0, end - start)
                if duration <= 0:
                    continue
                if total >= 60.0:
                    break
                take = min(duration, 60.0 - total)
                total += take
                start_idx = int(start * sr)
                end_idx = int((start + take) * sr)
                clip = audio[start_idx:end_idx]
                emb, method = self._compute_voice_embedding(clip, sr, classifier)
                if emb:
                    embeddings.append(emb)
                    method_used = method_used or method

            if embeddings:
                emb_array = np.array(embeddings, dtype=float)
                mean_emb = np.mean(emb_array, axis=0)
                label_embeddings[label] = {
                    "embedding": mean_emb.astype(float).tolist(),
                    "method": method_used or "mfcc",
                }

        return label_embeddings

    def _match_label_embeddings(self, label_embeddings: dict, enrolled_embeddings: dict, threshold: float = 0.75) -> dict:
        matches = {}
        enrolled_vectors = {
            speaker_id: payload
            for speaker_id, payload in enrolled_embeddings.items()
            if payload.get("embedding")
        }
        for label, payload in label_embeddings.items():
            embedding = payload.get("embedding") if isinstance(payload, dict) else payload
            method = payload.get("method") if isinstance(payload, dict) else None
            if not embedding:
                continue
            best_id = None
            best_score = 0.0
            for speaker_id, stored_payload in enrolled_vectors.items():
                stored_method = stored_payload.get("method")
                stored_emb = stored_payload.get("embedding")
                if method and stored_method and stored_method != method:
                    continue
                if not stored_emb:
                    continue
                score = self._cosine_similarity(embedding, stored_emb)
                if score > best_score:
                    best_score = score
                    best_id = speaker_id
            if best_id and best_score >= threshold:
                matches[label] = {"speaker_id": best_id, "score": best_score}
        return matches

    def _apply_embedding_matches(self, registry: dict, matches: dict) -> dict:
        speakers = registry.get("speakers", [])
        speakers_map = {sp.get("speaker_id"): sp for sp in speakers}
        for match in matches.values():
            speaker_id = match["speaker_id"]
            score = match["score"]
            if speaker_id in speakers_map:
                speakers_map[speaker_id]["confidence"] = round(float(score), 4)
                speakers_map[speaker_id]["source"] = "enrollment_match"
        registry["speakers"] = list(speakers_map.values())
        return registry

    def _render_hearing_markdown(self, hearing_payload: dict) -> str:
        speakers = {sp["speaker_id"]: sp for sp in hearing_payload.get("speakers", [])}
        lines = []
        for seg in hearing_payload.get("segments", []):
            speaker_id = seg.get("speaker_id")
            speaker = speakers.get(speaker_id, {})
            name = speaker.get("name") or seg.get("speaker_label", "SPEAKER")
            role = speaker.get("role")
            label = f"{name} ({role})" if role else name
            ts = seg.get("timestamp_hint")
            ts_prefix = f"[{ts}] " if ts else ""
            text = seg.get("text") or ""
            if text:
                lines.append(f"**{label}**: {ts_prefix}{text}")
        return "\n\n".join(lines)

    def enroll_hearing_speaker(self, case_id: str, name: str, role: str, file_path: str) -> dict:
        case_dir = self._get_hearing_case_dir(case_id)
        enrollment_dir = case_dir / "enrollment"
        enrollment_dir.mkdir(parents=True, exist_ok=True)

        speaker_id = f"spk_{uuid.uuid4().hex[:8]}"
        speaker_dir = enrollment_dir / speaker_id
        speaker_dir.mkdir(parents=True, exist_ok=True)
        filename = Path(file_path).name
        target_path = speaker_dir / filename
        os.replace(file_path, target_path)

        registry = self._load_speaker_registry(case_id)
        speakers = registry.get("speakers", [])
        speaker = {
            "speaker_id": speaker_id,
            "label": name or "FALANTE",
            "name": name or "FALANTE",
            "role": role or "outro",
            "confidence": 0.0,
            "source": "enrollment",
            "enrollment_files": [str(target_path)],
        }
        speakers.append(speaker)
        registry["speakers"] = speakers
        self._save_speaker_registry(case_id, registry)

        embedding = None
        method = None
        try:
            audio, sr = self._load_audio_samples(str(target_path))
            if audio is not None and sr is not None:
                embedding, method = self._compute_voice_embedding(audio, sr, self._get_ecapa_classifier())
        except Exception:
            embedding = None

        if embedding:
            embeddings_store = self._load_speaker_embeddings(case_id)
            embeddings_store[speaker_id] = {
                "speaker_id": speaker_id,
                "embedding": embedding,
                "method": method or "mfcc",
                "updated_at": datetime.utcnow().isoformat(),
            }
            self._save_speaker_embeddings(case_id, embeddings_store)

        return speaker

    def update_hearing_speakers(self, case_id: str, updates: list[dict]) -> list[dict]:
        registry = self._load_speaker_registry(case_id)
        speakers = registry.get("speakers", [])
        speaker_map = {sp.get("speaker_id"): sp for sp in speakers}
        for update in updates:
            speaker_id = update.get("speaker_id")
            if not speaker_id or speaker_id not in speaker_map:
                continue
            speaker = speaker_map[speaker_id]
            if update.get("name") is not None:
                speaker["name"] = update["name"]
            if update.get("role") is not None:
                speaker["role"] = update["role"]
            if update.get("source"):
                speaker["source"] = update["source"]
        registry["speakers"] = speakers
        self._save_speaker_registry(case_id, registry)
        return speakers

    async def process_hearing_with_progress(
        self,
        file_path: str,
        case_id: str,
        goal: str = "alegacoes_finais",
        thinking_level: str = "medium",
        model_selection: Optional[str] = None,
        high_accuracy: bool = False,
        format_mode: str = "AUDIENCIA",
        custom_prompt: Optional[str] = None,
        format_enabled: bool = True,
        on_progress: Optional[Callable[[str, int, str], Awaitable[None]]] = None,
    ) -> dict:
        async def emit(stage: str, progress: int, message: str):
            if on_progress:
                await on_progress(stage, progress, message)

        vomo = self._get_vomo(model_selection=model_selection, thinking_level=thinking_level)
        logger.info(f"🎤 Iniciando transcrição de audiência: {file_path} [case_id={case_id}]")

        await emit("audio_optimization", 0, "Otimizando áudio...")
        audio_path = await asyncio.to_thread(vomo.optimize_audio, file_path)
        await emit("audio_optimization", 20, "Áudio otimizado ✓")

        await emit("transcription", 30, "Transcrevendo com Whisper MLX...")
        structured = None
        if high_accuracy and hasattr(vomo, "transcribe_beam_with_segments"):
            structured = await asyncio.to_thread(vomo.transcribe_beam_with_segments, audio_path)
        elif hasattr(vomo, "transcribe_with_segments"):
            structured = await asyncio.to_thread(vomo.transcribe_with_segments, audio_path)

        if structured:
            transcription_text = structured.get("text") or ""
            asr_segments = structured.get("segments") or []
        else:
            if high_accuracy:
                transcription_text = await asyncio.to_thread(vomo.transcribe_beam_search, audio_path)
            else:
                transcription_text = await asyncio.to_thread(vomo.transcribe, audio_path)
            asr_segments = []
        await emit("transcription", 60, "Transcrição concluída ✓")

        await emit("structuring", 70, "Estruturando segmentos, falantes e evidências...")
        if asr_segments:
            segments = self._build_hearing_segments_from_asr(asr_segments)
        else:
            segments = self._build_hearing_segments(vomo, transcription_text)
        speaker_labels = sorted({seg["speaker_label"] for seg in segments})
        registry = self._load_speaker_registry(case_id)
        speakers, label_to_id = self._ensure_registry_speakers(registry, speaker_labels)

        matches = {}
        if any(seg.get("start") is not None for seg in segments):
            label_embeddings = self._compute_label_embeddings(audio_path, segments)
            enrolled_embeddings = self._load_speaker_embeddings(case_id)
            matches = self._match_label_embeddings(label_embeddings, enrolled_embeddings, threshold=0.75)
            if matches:
                for label, match in matches.items():
                    label_to_id[label] = match["speaker_id"]
                registry = self._apply_embedding_matches(registry, matches)

        self._save_speaker_registry(case_id, registry)

        for seg in segments:
            seg["speaker_id"] = label_to_id.get(seg["speaker_label"])

        used_speakers = {seg.get("speaker_id") for seg in segments if seg.get("speaker_id")}
        payload_speakers = [sp for sp in registry.get("speakers", []) if sp.get("speaker_id") in used_speakers]

        act_map, act_warnings = await self._classify_segments_act_with_llm(
            segments=segments,
            speakers=payload_speakers,
            goal=goal,
            vomo=vomo,
        )
        blocks = self._build_hearing_blocks(segments, act_map)
        evidence = self._build_hearing_evidence(blocks)
        claims_truncated = len(evidence) > 80
        await emit("structuring", 78, "Extraindo claims estruturados via IA...")
        evidence = await self._extract_claims_with_llm(evidence, payload_speakers, goal, vomo)
        evidence = self._apply_goal_based_relevance(evidence, goal, payload_speakers)
        claims = self._build_claims_from_evidence(evidence, segments)
        contradictions = self._detect_contradictions(claims)
        timeline = self._build_timeline(claims, segments)

        warnings = []
        if not matches:
            warnings.append("sem_match_enrollment")
        if not format_enabled:
            warnings.append("sem_formatacao")
        warnings.extend(act_warnings)
        if claims_truncated:
            warnings.append("claims_truncated")

        hearing_payload = {
            "case_id": case_id,
            "goal": goal,
            "media": {
                "file_hash": self._compute_file_hash(audio_path),
                "filename": Path(file_path).name,
                "created_at": datetime.utcnow().isoformat(),
                "duration": self._get_wav_duration_seconds(audio_path),
            },
            "segments": segments,
            "speakers": payload_speakers,
            "blocks": blocks,
            "evidence": evidence,
            "claims": claims,
            "contradictions": contradictions,
            "timeline": timeline,
            "audit": {
                "pipeline_version": "hearing_v1",
                "model_selection": model_selection,
                "warnings": warnings,
            },
        }

        case_dir = self._get_hearing_case_dir(case_id)
        run_dir = case_dir / "runs" / datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        run_dir.mkdir(parents=True, exist_ok=True)
        structured_path = run_dir / "hearing_structured.json"
        json_path = run_dir / "hearing.json"
        raw_path = run_dir / "transcript_raw.txt"
        transcript_markdown = self._render_hearing_markdown(hearing_payload)

        hearing_payload["transcript_markdown"] = transcript_markdown
        structured_path.write_text(json.dumps(hearing_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        format_mode_normalized = (format_mode or "AUDIENCIA").strip().upper()
        if format_mode_normalized == "CUSTOM":
            format_mode_normalized = "AUDIENCIA"
        if format_mode_normalized not in {"AUDIENCIA", "DEPOIMENTO", "APOSTILA", "FIDELIDADE"}:
            format_mode_normalized = "AUDIENCIA"

        formatted_text = None
        formatted_path = None
        docx_path = None
        analysis_report = None
        validation_report = None
        report_paths = {}

        if format_enabled:
            await emit("formatting", 75, "Formatando texto da audiência...")
            formatted_text = await vomo.format_transcription_async(
                transcription_text,
                video_name=f"hearing_{case_id}",
                output_folder=str(run_dir),
                mode=format_mode_normalized,
                custom_prompt=custom_prompt,
                progress_callback=emit,
            )
            await emit("formatting", 92, "Texto formatado ✓")

            if formatted_text:
                formatted_path = run_dir / f"hearing_formatted_{format_mode_normalized.lower()}.md"
                formatted_path.write_text(formatted_text, encoding="utf-8")

            if formatted_text:
                try:
                    from app.services.quality_service import quality_service
                    analysis_report = await quality_service.analyze_structural_issues(
                        content=formatted_text,
                        document_name=f"hearing_{case_id}",
                        raw_content=transcription_text
                    )
                    validation_report = await quality_service.validate_document_full(
                        raw_content=transcription_text,
                        formatted_content=formatted_text,
                        document_name=f"hearing_{case_id}"
                    )
                except Exception as audit_error:
                    logger.warning(f"Falha na auditoria de audiência (não-bloqueante): {audit_error}")

            if analysis_report:
                analysis_path = run_dir / "hearing_analysis.json"
                analysis_path.write_text(json.dumps(analysis_report, ensure_ascii=False, indent=2), encoding="utf-8")
                report_paths["analysis_path"] = str(analysis_path)
            if validation_report:
                validation_path = run_dir / "hearing_validation.json"
                validation_path.write_text(json.dumps(validation_report, ensure_ascii=False, indent=2), encoding="utf-8")
                report_paths["validation_path"] = str(validation_path)

            if formatted_text:
                try:
                    docx_path = vomo.save_as_word(
                        formatted_text=formatted_text,
                        video_name=f"hearing_{case_id}",
                        output_folder=str(run_dir),
                        mode=format_mode_normalized
                    )
                except Exception as e:
                    logger.warning(f"Falha ao gerar Word da audiência: {e}")

        hearing_payload["formatted_text"] = formatted_text
        hearing_payload["formatted_mode"] = format_mode_normalized if format_enabled else None
        hearing_payload["custom_prompt_used"] = bool(custom_prompt)
        hearing_payload["reports"] = {
            "analysis": analysis_report,
            "validation": validation_report,
        }

        json_path.write_text(json.dumps(hearing_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        raw_path.write_text(transcription_text or "", encoding="utf-8")

        await emit("structuring", 95, "JSON canônico gerado ✓")
        await emit("complete", 100, "Processamento finalizado ✓")

        return {
            "hearing": hearing_payload,
            "paths": {
                "structured_path": str(structured_path),
                "json_path": str(json_path),
                "raw_path": str(raw_path),
                "formatted_path": str(formatted_path) if formatted_path else None,
                "docx_path": str(docx_path) if docx_path else None,
                **report_paths,
            },
        }

transcription_service = TranscriptionService()
