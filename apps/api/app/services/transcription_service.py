import sys
import os
import asyncio
import json
from typing import Optional, Callable, Tuple, Awaitable
import logging
import time
import wave
import re
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

transcription_service = TranscriptionService()
