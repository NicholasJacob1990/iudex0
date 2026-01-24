import sys
import os
import asyncio
import json
import shutil
from typing import Optional, Callable, Tuple, Awaitable, Dict, Any
import logging
import time
import wave
import re
import hashlib
import uuid
from datetime import datetime
from pathlib import Path
from tenacity import RetryError

# Import FidelityMatcher para validação de referências legais
try:
    from app.services.fidelity_matcher import FidelityMatcher
except ImportError:
    FidelityMatcher = None

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

    def _unwrap_retry_error(self, exc: Exception) -> Exception:
        current = exc
        while isinstance(current, RetryError):
            last_attempt = getattr(current, "last_attempt", None)
            if not last_attempt:
                break
            last_exc = last_attempt.exception()
            if not last_exc:
                break
            current = last_exc
        return current

    def _format_exception_message(self, exc: Exception) -> Tuple[str, Exception]:
        root = self._unwrap_retry_error(exc)
        message = str(root).strip() if str(root) else repr(root)
        return message, root

    def _llm_raw_fallback_enabled(self) -> bool:
        value = os.getenv("IUDEX_ALLOW_LLM_FALLBACK_RAW", "1").strip().lower()
        return value not in {"0", "false", "no", "off"}

    def _classify_llm_error(self, exc: Exception) -> Optional[str]:
        message = str(exc or "").lower()
        code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
        if code == 429:
            return "quota_exceeded"
        if any(token in message for token in ("resource_exhausted", "resource exhausted", "quota exceeded", "rate_limit_exceeded", "rate limit exceeded", "too many requests", "429")):
            return "quota_exceeded"
        if any(token in message for token in ("permission_denied", "unauthorized", "api key", "invalid api key", "401", "403")):
            return "auth"
        return None

    def _fallback_markdown_from_raw(self, raw_text: str, title: str, note: Optional[str] = None) -> str:
        safe_title = (title or "Transcrição").strip() or "Transcrição"
        body = (raw_text or "").strip()
        lines: list[str] = []
        if note:
            lines.append(f"<!-- {note.strip()} -->")
        lines.append(f"# {safe_title}")
        lines.append("")
        lines.append(body)
        return "\n".join(lines).strip() + "\n"

    def _build_audit_issues(
        self,
        analysis_report: Optional[dict],
        video_name: str,
        raw_content: Optional[str] = None,
        formatted_content: Optional[str] = None,
    ) -> list[dict]:
        issues: list[dict] = []
        if not analysis_report:
            return issues
        analysis_data = analysis_report
        if isinstance(analysis_data, dict) and analysis_data.get("cli_issues"):
            analysis_data = analysis_data["cli_issues"] or {}

        raw_text = raw_content or ""
        formatted_text = formatted_content or ""

        def _digits_only(value: str) -> str:
            return re.sub(r"\D+", "", value or "")

        def _build_fuzzy_digits_pattern(digits: str) -> str:
            # Matches digits with optional separators like ".", "/", "-" or whitespace between them.
            sep = r"[\s\./-]*"
            return sep.join(list(digits))

        def _extract_raw_evidence(pattern: str, max_hits: int = 3, window: int = 260) -> list[dict]:
            if not raw_text or not pattern:
                return []
            matches: list[dict] = []
            try:
                for match in re.finditer(pattern, raw_text, flags=re.IGNORECASE):
                    start, end = match.span()
                    snippet_start = max(0, start - window)
                    snippet_end = min(len(raw_text), end + window)
                    snippet = raw_text[snippet_start:snippet_end].strip()
                    matches.append(
                        {
                            "match": match.group(0),
                            "start": start,
                            "end": end,
                            "snippet": snippet,
                        }
                    )
                    if len(matches) >= max_hits:
                        break
            except re.error:
                return []
            return matches

        stopwords = {
            "para",
            "com",
            "sem",
            "uma",
            "uns",
            "umas",
            "por",
            "que",
            "dos",
            "das",
            "nos",
            "nas",
            "num",
            "numa",
            "mais",
            "menos",
            "sobre",
            "entre",
            "como",
            "quando",
            "onde",
            "pelo",
            "pela",
            "pelos",
            "pelas",
            "isso",
            "essa",
            "esse",
            "este",
            "esta",
            "ser",
            "ter",
            "são",
            "não",
            "sim",
            "sua",
            "seu",
            "suas",
            "seus",
            "também",
        }

        def _keywords(text: str) -> set[str]:
            tokens = re.findall(r"[A-Za-zÀ-ÿ0-9]{4,}", (text or "").lower())
            out = set()
            for tok in tokens:
                if tok in stopwords:
                    continue
                if tok.isdigit() and len(tok) < 4:
                    continue
                out.add(tok)
            return out

        headings: list[tuple[str, int]] = []
        if formatted_text:
            for m in re.finditer(r"^##\s+(.+)$", formatted_text, flags=re.MULTILINE):
                title = m.group(1).strip()
                if title:
                    headings.append((title, m.start()))

        def _suggest_section_title(evidence_items: list[dict]) -> Optional[str]:
            if not headings or not formatted_text or not evidence_items:
                return None
            evidence_text = "\n\n".join([str(item.get("snippet") or "") for item in evidence_items if item.get("snippet")])
            kw = _keywords(evidence_text)
            if not kw:
                return None

            best_score = 0
            best_title: Optional[str] = None
            max_headings = 60
            for idx, (title, start) in enumerate(headings[:max_headings]):
                end = headings[idx + 1][1] if idx + 1 < len(headings) else len(formatted_text)
                sample = formatted_text[start:min(end, start + 3500)]
                score = len(kw & _keywords(sample))
                if score > best_score:
                    best_score = score
                    best_title = title
            if best_score < 2:
                return None
            return best_title

        for sec in (analysis_data or {}).get("duplicate_sections", [])[:10]:
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

        heading_issues = (analysis_data or {}).get("heading_numbering_issues", [])
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

        for para in (analysis_data or {}).get("duplicate_paragraphs", [])[:10]:
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

        for law in (analysis_data or {}).get("missing_laws", [])[:8]:
            reference = str(law)
            digits = _digits_only(reference)
            law_pattern = None
            if digits:
                law_pattern = rf"\b[Ll]ei\s*(?:n[º°]?\s*)?{_build_fuzzy_digits_pattern(digits)}"
            evidence = _extract_raw_evidence(law_pattern) if law_pattern else []
            suggested_section = _suggest_section_title(evidence)
            issue = {
                "id": f"missing_law_{hash(law) % 10000}",
                "type": "missing_law",
                "fix_type": "content",
                "severity": "warning",
                "reference": reference,
                "description": f"Lei possivelmente ausente: {reference}",
                "suggestion": "Inserir referência contextual ou revisar trecho"
            }
            if evidence:
                issue["raw_evidence"] = evidence
            if suggested_section:
                issue["suggested_section"] = suggested_section
            issues.append(issue)

        for item in (analysis_data or {}).get("missing_sumulas", [])[:8]:
            reference = str(item)
            num = re.sub(r"\D+", "", reference)
            sumula_pattern = None
            if num:
                sumula_pattern = rf"\b[Ss](?:ú|u)mula\s*(?:vinculante\s*)?(?:n[º°]?\s*)?{re.escape(num)}\b"
            evidence = _extract_raw_evidence(sumula_pattern) if sumula_pattern else []
            suggested_section = _suggest_section_title(evidence)
            issue = {
                "id": f"missing_sumula_{hash(item) % 10000}",
                "type": "missing_sumula",
                "fix_type": "content",
                "severity": "warning",
                "reference": reference,
                "description": f"Súmula possivelmente ausente: {reference}",
                "suggestion": "Inserir referência contextual ou revisar trecho"
            }
            if evidence:
                issue["raw_evidence"] = evidence
            if suggested_section:
                issue["suggested_section"] = suggested_section
            issues.append(issue)

        for item in (analysis_data or {}).get("missing_decretos", [])[:6]:
            reference = str(item)
            digits = _digits_only(reference)
            decreto_pattern = None
            if digits:
                decreto_pattern = rf"\b[Dd]ecreto\s*(?:Rio\s*)?(?:n[º°]?\s*)?{_build_fuzzy_digits_pattern(digits)}"
            evidence = _extract_raw_evidence(decreto_pattern) if decreto_pattern else []
            suggested_section = _suggest_section_title(evidence)
            issue = {
                "id": f"missing_decreto_{hash(item) % 10000}",
                "type": "missing_decreto",
                "fix_type": "content",
                "severity": "info",
                "reference": reference,
                "description": f"Decreto possivelmente ausente: {reference}",
                "suggestion": "Inserir referência contextual ou revisar trecho"
            }
            if evidence:
                issue["raw_evidence"] = evidence
            if suggested_section:
                issue["suggested_section"] = suggested_section
            issues.append(issue)

        for item in (analysis_data or {}).get("missing_julgados", [])[:6]:
            reference = str(item)
            
            # NOVO: Usar FidelityMatcher para verificação robusta com matching fuzzy
            # Isso evita falsos positivos como "tema 1070" vs "Tema 1.070"
            if FidelityMatcher is not None:
                exists, matched = FidelityMatcher.exists_in_text(reference, formatted_text, "auto")
                if exists:
                    logger.debug(f"✅ Julgado '{reference}' encontrado como '{matched}' - ignorando")
                    continue
            else:
                # Fallback para matching antigo se FidelityMatcher não disponível
                escaped = re.escape(reference)
                julgado_pattern = re.sub(r"\\\s+", r"\\s+", escaped)
                try:
                    if julgado_pattern and formatted_text and re.search(julgado_pattern, formatted_text, flags=re.IGNORECASE):
                        continue
                except re.error:
                    pass
            
            # Constrói padrão para evidência
            escaped = re.escape(reference)
            julgado_pattern = re.sub(r"\\\s+", r"\\s+", escaped)
            evidence = _extract_raw_evidence(julgado_pattern) if julgado_pattern else []
            suggested_section = _suggest_section_title(evidence)
            issue = {
                "id": f"missing_julgado_{hash(item) % 10000}",
                "type": "missing_julgado",
                "fix_type": "content",
                "severity": "info",
                "reference": reference,
                "description": f"Julgado possivelmente ausente: {reference}",
                "suggestion": "Inserir referência contextual ou revisar trecho",
                "validated": True,  # Flag indicando que passou por validação fuzzy
            }
            if evidence:
                issue["raw_evidence"] = evidence
            if suggested_section:
                issue["suggested_section"] = suggested_section
            issues.append(issue)

        compression_warning = (analysis_data or {}).get("compression_warning")
        if compression_warning:
            issue = {
                "id": f"compression_{hash(compression_warning) % 10000}",
                "type": "compression_warning",
                "fix_type": "content",
                "severity": "warning",
                "compression_ratio": (analysis_data or {}).get("compression_ratio"),
                "description": str(compression_warning),
                "suggestion": "Revisar partes possivelmente condensadas demais"
            }
            issues.append(issue)

        return issues

    async def _auto_apply_content_fixes(
        self,
        final_text: str,
        transcription_text: str,
        video_name: str,
        content_issues: list[dict],
        model_selection: Optional[str] = None
    ) -> tuple[str, bool, list[str]]:
        """Aplica correções de conteúdo automáticas usando LLM (via quality_service)."""
        if not content_issues:
            return final_text, False, []
        
        try:
            from app.services.quality_service import quality_service
            
            # Log detalhado dos issues que serão aplicados
            logger.info(f"🤖 Auto-aplicando {len(content_issues)} correções de conteúdo via LLM...")
            logger.info("=" * 80)
            logger.info("📋 ISSUES DE CONTEÚDO SELECIONADOS PARA AUTO-APLICAÇÃO:")
            
            # Agrupar por tipo para melhor visualização
            issues_by_type = {}
            for issue in content_issues:
                issue_type = issue.get("type", "unknown")
                if issue_type not in issues_by_type:
                    issues_by_type[issue_type] = []
                issues_by_type[issue_type].append(issue)
            
            for issue_type, issues in issues_by_type.items():
                logger.info(f"  📌 {issue_type.upper()} ({len(issues)} issue(s)):")
                for issue in issues:
                    issue_id = issue.get("id", "?")
                    description = issue.get("description", "N/A")
                    severity = issue.get("severity", "info")
                    reference = issue.get("reference", "")
                    
                    desc_preview = description[:100] + "..." if len(description) > 100 else description
                    ref_info = f" | Ref: {reference}" if reference else ""
                    logger.info(f"    • [{severity.upper()}] {issue_id}: {desc_preview}{ref_info}")
            
            logger.info("=" * 80)
            
            result = await quality_service.fix_content_issues_with_llm(
                content=final_text,
                raw_content=transcription_text,
                issues=content_issues,
                model_selection=model_selection,
            )

            corrected_text = result.get("content", final_text) if isinstance(result, dict) else final_text
            applied_ids = []
            if isinstance(result, dict):
                applied_ids = [issue_id for issue_id in (result.get("fixes") or []) if issue_id]
                if result.get("error"):
                    logger.warning(f"⚠️ Auto-aplicar conteúdo retornou erro: {result.get('error')}")

            if (
                isinstance(corrected_text, str)
                and corrected_text.strip()
                and corrected_text.strip() != (final_text or "").strip()
            ):
                char_diff = len(corrected_text) - len(final_text)
                logger.info("=" * 80)
                logger.info(f"✅ CORREÇÕES DE CONTEÚDO APLICADAS AUTOMATICAMENTE:")
                logger.info(f"   • Total de issues: {len(applied_ids)}")
                logger.info(f"   • Tipos de correções: {', '.join(issues_by_type.keys())}")
                logger.info(f"   • Alteração de tamanho: {char_diff:+d} caracteres")
                logger.info(f"   • IDs aplicados: {', '.join(applied_ids[:10])}" + ("..." if len(applied_ids) > 10 else ""))
                logger.info("=" * 80)
                return corrected_text, True, applied_ids
            else:
                logger.warning("=" * 80)
                logger.warning("⚠️ LLM NÃO APLICOU MUDANÇAS DETECTÁVEIS NO CONTEÚDO")
                logger.warning(f"   • Issues enviados: {len(content_issues)}")
                logger.warning(f"   • Conteúdo antes: {len(final_text)} chars")
                logger.warning(f"   • Conteúdo depois: {len(corrected_text) if isinstance(corrected_text, str) else 0} chars")
                logger.warning("=" * 80)
                return final_text, False, []
                
        except Exception as e:
            logger.error("=" * 80)
            logger.error(f"❌ ERRO AO AUTO-APLICAR CORREÇÕES DE CONTEÚDO: {e}")
            logger.error(f"   • Issues tentados: {len(content_issues)}")
            logger.error("=" * 80)
            return final_text, False, []

    async def _auto_apply_structural_fixes(
        self,
        final_text: str,
        transcription_text: str,
        video_name: str
    ) -> tuple[str, bool, list[str]]:
        """Aplica correções estruturais automáticas usando auto_fix_apostilas."""
        try:
            from app.services.quality_service import quality_service
            auto_fix = quality_service._get_auto_fix()
            if not auto_fix:
                logger.info("🔧 auto_fix_apostilas não disponível, pulando correções estruturais")
                return final_text, False, []

            import tempfile

            raw_path = None
            with tempfile.NamedTemporaryFile(mode="w+", suffix=".md", delete=False, encoding="utf-8") as tmp:
                tmp.write(final_text)
                tmp_path = tmp.name

            if transcription_text:
                with tempfile.NamedTemporaryFile(mode="w+", suffix=".txt", delete=False, encoding="utf-8") as raw_tmp:
                    raw_tmp.write(transcription_text)
                    raw_path = raw_tmp.name

            try:
                logger.info(f"🔧 Analisando issues estruturais para auto-aplicação...")
                issues = await asyncio.to_thread(auto_fix.analyze_structural_issues, tmp_path, raw_path)
                total_issues = (issues or {}).get("total_issues", 0)
                
                if total_issues <= 0:
                    logger.info("✨ Nenhum issue estrutural detectado")
                    return final_text, False, []

                # Log detalhado dos issues estruturais
                logger.info("=" * 80)
                logger.info(f"📋 ISSUES ESTRUTURAIS DETECTADOS PARA AUTO-APLICAÇÃO:")
                logger.info(f"   • Total de issues: {total_issues}")
                
                # Listar tipos de issues detectados
                issue_types = {}
                for key, items in issues.items():
                    if key == "total_issues" or not isinstance(items, list):
                        continue
                    if items:
                        issue_types[key] = len(items)
                        logger.info(f"   • {key}: {len(items)} issue(s)")
                        # Log primeiros exemplos de cada tipo
                        for item in items[:3]:
                            if isinstance(item, dict):
                                title = item.get("title", "")[:60]
                                if title:
                                    logger.info(f"      - {title}...")
                            elif isinstance(item, str):
                                logger.info(f"      - {item[:60]}...")
                
                logger.info("=" * 80)

                result = await asyncio.to_thread(auto_fix.apply_structural_fixes_to_file, tmp_path, issues)
                with open(tmp_path, "r", encoding="utf-8") as f:
                    fixed_content = f.read()

                # CRITICAL: Never return empty content - fallback to original
                if not fixed_content or not fixed_content.strip():
                    logger.warning("=" * 80)
                    logger.warning("⚠️ RESULTADO VAZIO APÓS CORREÇÃO ESTRUTURAL, RETORNANDO ORIGINAL")
                    logger.warning("=" * 80)
                    return final_text, False, []

                fixes_applied = result.get("fixes_applied", [])
                if fixes_applied:
                    char_diff = len(fixed_content) - len(final_text)
                    logger.info("=" * 80)
                    logger.info(f"✅ CORREÇÕES ESTRUTURAIS APLICADAS AUTOMATICAMENTE:")
                    logger.info(f"   • Total de correções: {len(fixes_applied)}")
                    logger.info(f"   • Tipos corrigidos: {', '.join(issue_types.keys())}")
                    logger.info(f"   • Alteração de tamanho: {char_diff:+d} caracteres")
                    logger.info(f"   • Correções aplicadas:")
                    for fix in fixes_applied[:15]:  # Mostrar até 15 correções
                        logger.info(f"      - {fix}")
                    if len(fixes_applied) > 15:
                        logger.info(f"      ... e mais {len(fixes_applied) - 15} correções")
                    logger.info("=" * 80)
                    return fixed_content, True, fixes_applied
                else:
                    logger.info("=" * 80)
                    logger.info("ℹ️ Issues detectados, mas nenhuma correção foi aplicada")
                    logger.info("=" * 80)
                return final_text, False, []
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                if raw_path and os.path.exists(raw_path):
                    os.unlink(raw_path)
        except Exception as auto_fix_error:
            logger.error("=" * 80)
            logger.error(f"❌ ERRO AO APLICAR CORREÇÕES ESTRUTURAIS: {auto_fix_error}")
            logger.error("=" * 80)
            return final_text, False, []

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
        matches = re.findall(r'<!--\s*RELATÓRIO:([\s\S]*?)-->', content, re.IGNORECASE)
        if not matches:
            return None
        return matches[-1].strip()

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

    def _copy_cli_artifacts(
        self,
        cli_output_dir: Optional[str],
        output_dir: Path,
        video_name: str,
        mode_suffix: str,
    ) -> dict:
        if not cli_output_dir:
            return {}
        cli_dir = Path(cli_output_dir)
        if not cli_dir.exists():
            return {}

        artifacts = {
            "coverage_path": f"{video_name}_validacao.txt",
            "structure_audit_path": f"{video_name}_{mode_suffix}_verificacao.txt",
            "fidelity_path": f"{video_name}_{mode_suffix}_fidelidade.json",
            "revision_path": f"{video_name}_{mode_suffix}_REVISAO.md",
            "legal_audit_path": f"{video_name}_{mode_suffix}_AUDITORIA.md",
            "preventive_fidelity_json_path": f"{video_name}_{mode_suffix}_AUDITORIA_FIDELIDADE.json",
            "preventive_fidelity_md_path": f"{video_name}_{mode_suffix}_AUDITORIA_FIDELIDADE.md",
        }

        copied = {}
        for key, filename in artifacts.items():
            src = cli_dir / filename
            if src.exists():
                dest = output_dir / filename
                if src.resolve() == dest.resolve():
                    copied[key] = str(dest)
                    continue
                shutil.copy2(src, dest)
                copied[key] = str(dest)

        if copied.get("legal_audit_path"):
            copied["audit_path"] = copied["legal_audit_path"]
        return copied

    def _write_hil_suggestions(
        self,
        output_dir: Path,
        video_name: str,
        mode_suffix: str,
        cli_issues: Optional[dict],
    ) -> Optional[str]:
        if not cli_issues:
            return None
        has_structural = (
            cli_issues.get("total_issues", 0) > 0
            or cli_issues.get("duplicate_sections")
            or cli_issues.get("duplicate_paragraphs")
            or cli_issues.get("heading_numbering_issues")
        )
        if not has_structural:
            return None
        suggestions_path = output_dir / f"{video_name}_{mode_suffix}_SUGESTOES.json"
        suggestions_path.write_text(json.dumps(cli_issues, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(suggestions_path)

    def _run_audit_pipeline(
        self,
        *,
        output_dir: Path,
        report_paths: Dict[str, Any],
        raw_text: Optional[str],
        formatted_text: Optional[str],
        analysis_report: Optional[dict],
        validation_report: Optional[dict],
    ) -> Optional[Dict[str, Any]]:
        try:
            from app.services.audit_pipeline import run_audit_pipeline
        except Exception as e:
            logger.warning(f"Audit pipeline indisponivel: {e}")
            return None
        try:
            return run_audit_pipeline(
                output_dir=output_dir,
                report_paths=report_paths,
                raw_text=raw_text or "",
                formatted_text=formatted_text or "",
                analysis_report=analysis_report,
                validation_report=validation_report,
            )
        except Exception as e:
            logger.warning(f"Falha ao executar audit pipeline: {e}")
            return None

    def _generate_docx(
        self,
        vomo,
        formatted_text: str,
        video_name: str,
        output_dir: Path,
        mode: str,
    ) -> Optional[str]:
        if not formatted_text:
            return None
        try:
            return vomo.save_as_word(formatted_text, video_name, str(output_dir), mode=mode)
        except Exception as e:
            logger.warning(f"Falha ao gerar DOCX: {e}")
            return None

    def _load_legal_audit_report(self, report_paths: Optional[dict]) -> Optional[str]:
        if not report_paths:
            return None
        report_path = report_paths.get("legal_audit_path") or report_paths.get("audit_path")
        if not report_path:
            return None
        try:
            return Path(report_path).read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return None

    def _parse_legal_audit_issues(self, report_text: Optional[str]) -> list[dict]:
        if not report_text:
            return []
        lines = report_text.splitlines()
        issues: list[dict] = []
        in_attention = False
        current = None
        idx = 0

        def _finalize():
            if current:
                issues.append(current.copy())

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("<!--"):
                continue
            if re.match(r"^##\s*2\.", stripped, re.IGNORECASE) and "Pontos" in stripped:
                in_attention = True
                continue
            if in_attention and re.match(r"^##\s*\d+\.", stripped):
                break
            if not in_attention:
                continue
            item_match = re.match(r"^[*-]\s+\*\*\[(.+?)\]\*\*\s*(.+)$", stripped)
            if item_match:
                _finalize()
                idx += 1
                error_type = item_match.group(1).strip()
                excerpt = item_match.group(2).strip()
                current = {
                    "id": f"legal_audit_{idx}",
                    "type": "legal_audit",
                    "fix_type": "content",
                    "severity": "warning",
                    "source": "legal_audit",
                    "title": error_type,
                    "description": f"{error_type}: {excerpt}",
                    "suggestion": "",
                }
                continue
            if current:
                prob_match = re.search(r"problema:\s*(.+)$", stripped, re.IGNORECASE)
                if prob_match:
                    current["description"] = f"{current.get('description', '')} Problema: {prob_match.group(1).strip()}".strip()
                    continue
                sug_match = re.search(r"sugest[aã]o:\s*(.+)$", stripped, re.IGNORECASE)
                if sug_match:
                    current["suggestion"] = sug_match.group(1).strip()
                    continue

        _finalize()

        if issues:
            return issues

        summary_line = None
        for line in lines:
            if line.strip().startswith("## 2."):
                summary_line = line.strip()
                break
        if summary_line:
            return [{
                "id": "legal_audit_summary",
                "type": "legal_audit",
                "fix_type": "content",
                "severity": "warning",
                "source": "legal_audit",
                "title": "Auditoria jurídica",
                "description": "Revisar relatorio completo da auditoria juridica.",
                "suggestion": "",
            }]
        return []

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
        model_selection: Optional[str] = None,
        use_cache: bool = True,
        auto_apply_fixes: bool = True,
        auto_apply_content_fixes: bool = False,
        skip_legal_audit: bool = False,
        skip_audit: Optional[bool] = None,
        skip_fidelity_audit: bool = False,
        skip_sources_audit: bool = False,
    ) -> str:
        """
        Processa um arquivo de áudio/vídeo usando MLX Vomo.
        
        Reflexo do fluxo main() do script original, mas adaptado para serviço.
        """
        try:
            if skip_audit is not None:
                skip_legal_audit = skip_legal_audit or skip_audit
            apply_fixes = auto_apply_fixes
            vomo = self._get_vomo(model_selection=model_selection, thinking_level=thinking_level)
            logger.info(f"🎤 Iniciando processamento Vomo: {file_path} [{mode}]")

            file_ext = Path(file_path).suffix.lower()
            is_text_input = file_ext in [".txt", ".md"]
            transcription_text = None
            cache_hash = None
            if use_cache:
                cache_hash = self._compute_file_hash(file_path)
                transcription_text = self._load_cached_raw(cache_hash, high_accuracy)

            if transcription_text:
                logger.info("♻️ RAW cache hit (pulando transcrição)")
            else:
                if is_text_input:
                    transcription_text = Path(file_path).read_text(encoding="utf-8", errors="ignore")
                else:
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
                if use_cache and cache_hash:
                    self._save_cached_raw(cache_hash, high_accuracy, transcription_text, Path(file_path).name)
            
            if mode == "RAW":
                return {"content": transcription_text, "raw_content": transcription_text, "reports": {}}

            # 3. Formatar (LLM)
            # Observação: `custom_prompt` em `mlx_vomo.py` sobrescreve apenas a camada de estilo/tabelas.
            # Para manter paridade com o CLI, só enviamos `custom_prompt` quando o usuário fornece.
            system_prompt = (custom_prompt or "").strip() or None
            
            # Mapear thinking_level para tokens (simplificado)
            # O script original usa thinking_budget int
            # Executar formatação
            # Definir folder temporário para outputs intermediários
            import tempfile
            from pathlib import Path
            
            video_name = Path(file_path).stem
            mode_suffix = mode.upper() if mode else "APOSTILA"
            with tempfile.TemporaryDirectory() as temp_dir:
                llm_warning: Optional[str] = None
                try:
                    final_text = await vomo.format_transcription_async(
                        transcription_text,
                        video_name=video_name,
                        output_folder=temp_dir,
                        mode=mode,
                        custom_prompt=system_prompt,
                        skip_audit=skip_legal_audit,
                        skip_fidelity_audit=skip_fidelity_audit,
                        skip_sources_audit=skip_sources_audit,
                    )
                except Exception as format_exc:
                    format_message, root_exc = self._format_exception_message(format_exc)
                    classification = self._classify_llm_error(root_exc)
                    if classification and self._llm_raw_fallback_enabled():
                        llm_warning = f"Formatação por IA indisponível ({classification}): {format_message}"
                        logger.warning(f"{llm_warning}. Retornando transcrição bruta.")
                        final_text = self._fallback_markdown_from_raw(transcription_text, video_name, llm_warning)
                    else:
                        raise

                analysis_report = None
                validation_report = None
                cli_issues = None
                auto_applied = False
                original_text = final_text
                issues: list[dict] = []

                try:
                    from app.services.quality_service import quality_service
                    analysis_report = await quality_service.analyze_structural_issues(
                        content=final_text,
                        document_name=video_name,
                        raw_content=transcription_text
                    )
                    cli_issues = (analysis_report or {}).get("cli_issues") or analysis_report
                    validation_report = await quality_service.validate_document_full(
                        raw_content=transcription_text,
                        formatted_content=final_text,
                        document_name=video_name,
                        mode=mode,
                    )

                    if apply_fixes and (analysis_report or {}).get("total_issues", 0) > 0:
                        original_text = final_text
                        final_text, auto_applied, _ = await self._auto_apply_structural_fixes(
                            final_text=final_text,
                            transcription_text=transcription_text,
                            video_name=video_name
                        )
                        if auto_applied:
                            analysis_report = await quality_service.analyze_structural_issues(
                                content=final_text,
                                document_name=video_name,
                                raw_content=transcription_text
                            )
                    
                    # Auto-aplicar correções de conteúdo se habilitado
                    if auto_apply_content_fixes:
                        logger.info("⚙️ Auto-aplicação de correções de conteúdo: ATIVADA")
                        if not transcription_text:
                            logger.warning("⚠️ Transcrição RAW não disponível - correções de conteúdo ignoradas")
                        else:
                            # Build issues from analysis + validation
                            content_issues = self._build_audit_issues(
                                analysis_report, 
                                video_name,
                                raw_content=transcription_text,
                                formatted_content=final_text
                            )
                            # Filter only content issues
                            content_only = [i for i in content_issues if i.get("fix_type") == "content"]

                            legal_report_for_auto = self._extract_audit_report(final_text)
                            if not legal_report_for_auto:
                                legal_report_path = Path(temp_dir) / f"{video_name}_{mode_suffix}_AUDITORIA.md"
                                if legal_report_path.exists():
                                    legal_report_for_auto = legal_report_path.read_text(encoding="utf-8", errors="ignore")
                            legal_issues_for_auto = self._parse_legal_audit_issues(legal_report_for_auto)
                            if legal_issues_for_auto:
                                content_only.extend(legal_issues_for_auto)
                            
                            if content_only:
                                final_text, content_applied, _ = await self._auto_apply_content_fixes(
                                    final_text=final_text,
                                    transcription_text=transcription_text,
                                    video_name=video_name,
                                    content_issues=content_only,
                                    model_selection=model_selection
                                )
                                if content_applied:
                                    logger.info("🔄 Re-analisando documento após correções de conteúdo...")
                                    analysis_report = await quality_service.analyze_structural_issues(
                                        content=final_text,
                                        document_name=video_name,
                                        raw_content=transcription_text
                                    )
                            else:
                                logger.info("ℹ️ Nenhum issue de conteúdo detectado para auto-aplicação")
                    else:
                        logger.info("⚙️ Auto-aplicação de correções de conteúdo: DESATIVADA")

                except Exception as e:
                    logger.warning(f"Falha ao gerar relatorios (nao-bloqueante): {e}")

                report_paths = self._persist_transcription_outputs(
                    video_name=video_name,
                    mode=mode,
                    raw_text=transcription_text,
                    formatted_text=final_text,
                    analysis_report=analysis_report,
                    validation_report=validation_report,
                )
                output_dir = Path(report_paths["output_dir"])
                report_paths.update(
                    self._copy_cli_artifacts(temp_dir, output_dir, video_name, mode_suffix)
                )
                if llm_warning:
                    report_paths["llm_fallback"] = {
                        "enabled": True,
                        "reason": llm_warning,
                    }
                suggestions_path = self._write_hil_suggestions(
                    output_dir, video_name, mode_suffix, cli_issues
                )
                if suggestions_path:
                    report_paths["suggestions_path"] = suggestions_path

                audit_summary = None
                audit_payload = self._run_audit_pipeline(
                    output_dir=output_dir,
                    report_paths=report_paths,
                    raw_text=transcription_text,
                    formatted_text=final_text,
                    analysis_report=analysis_report,
                    validation_report=validation_report,
                )
                if audit_payload:
                    audit_summary = audit_payload.get("summary")
                    if audit_payload.get("summary_path"):
                        report_paths["audit_summary_path"] = audit_payload["summary_path"]
                    if audit_payload.get("report_keys"):
                        report_paths["audit_report_keys"] = audit_payload["report_keys"]

                legal_report = self._load_legal_audit_report(report_paths)
                legal_issues = self._parse_legal_audit_issues(legal_report)
                if legal_issues:
                    issues.extend(legal_issues)

                docx_path = self._generate_docx(vomo, final_text, video_name, output_dir, mode)
                if docx_path:
                    report_paths["docx_path"] = docx_path

                if auto_applied and original_text:
                    original_md_path = output_dir / f"{video_name}_ORIGINAL_{mode_suffix}.md"
                    original_md_path.write_text(original_text or "", encoding="utf-8")
                    report_paths["original_md_path"] = str(original_md_path)
                    original_docx_path = self._generate_docx(
                        vomo, original_text, f"{video_name}_ORIGINAL", output_dir, mode
                    )
                    if original_docx_path:
                        report_paths["original_docx_path"] = original_docx_path

            return final_text

        except Exception as e:
            message, root = self._format_exception_message(e)
            logger.error(f"Erro no serviço de transcrição: {message}")
            if root is not e:
                raise RuntimeError(message) from root
            raise

    async def process_file_with_progress(
        self, 
        file_path: str, 
        mode: str = "APOSTILA", 
        thinking_level: str = "medium",
        custom_prompt: Optional[str] = None,
        high_accuracy: bool = False,
        on_progress: Optional[Callable[[str, int, str], Awaitable[None]]] = None,
        model_selection: Optional[str] = None,
        use_cache: bool = True,
        auto_apply_fixes: bool = True,
        auto_apply_content_fixes: bool = False,
        skip_legal_audit: bool = False,
        skip_audit: Optional[bool] = None,
        skip_fidelity_audit: bool = False,
        skip_sources_audit: bool = False,
    ) -> dict:
        """
        Process file with progress callback for SSE streaming.
        
        on_progress: async callable(stage: str, progress: int, message: str)
        """
        async def emit(stage: str, progress: int, message: str):
            if on_progress:
                await on_progress(stage, progress, message)
        
        try:
            if skip_audit is not None:
                skip_legal_audit = skip_legal_audit or skip_audit
            apply_fixes = auto_apply_fixes
            vomo = self._get_vomo(model_selection=model_selection, thinking_level=thinking_level)
            logger.info(f"🎤 Iniciando processamento Vomo com SSE: {file_path} [{mode}]")
            
            # Stage 1: Audio Optimization (0-20%)
            from pathlib import Path as PathLib
            import os as os_module
            
            file_ext = PathLib(file_path).suffix.lower()
            file_size_mb = os_module.path.getsize(file_path) / (1024 * 1024)
            is_text_input = file_ext in [".txt", ".md"]
            is_video = file_ext in ['.mp4', '.mov', '.mkv', '.avi', '.webm', '.m4v', '.wmv', '.flv']
            cache_hash = None
            transcription_text = None

            if use_cache:
                try:
                    cache_hash = self._compute_file_hash(file_path)
                    transcription_text = self._load_cached_raw(cache_hash, high_accuracy)
                except Exception as cache_error:
                    logger.warning(f"Falha ao carregar cache RAW: {cache_error}")
                    transcription_text = None

            if is_text_input:
                await emit("audio_optimization", 0, f"📄 Texto detectado ({file_ext.upper()}, {file_size_mb:.1f}MB)")
                await emit("audio_optimization", 5, "📥 Lendo arquivo de texto...")
                if transcription_text:
                    await emit("audio_optimization", 20, "♻️ Cache RAW encontrado — pulando leitura")
                else:
                    transcription_text = PathLib(file_path).read_text(encoding="utf-8", errors="ignore")
                    if use_cache and cache_hash:
                        self._save_cached_raw(cache_hash, high_accuracy, transcription_text, PathLib(file_path).name)
                    await emit("audio_optimization", 20, "✅ Texto carregado")

                await emit("transcription", 25, "Texto bruto carregado (transcrição não necessária)")
                await emit("transcription", 60, "Texto pronto ✓")
            else:
                if is_video:
                    await emit("audio_optimization", 0, f"🎬 Vídeo detectado ({file_ext.upper()}, {file_size_mb:.1f}MB)")
                    await emit("audio_optimization", 5, "📤 Extraindo faixa de áudio do vídeo com FFmpeg...")
                else:
                    await emit("audio_optimization", 0, f"🎵 Áudio detectado ({file_ext.upper()}, {file_size_mb:.1f}MB)")
                    await emit("audio_optimization", 5, "🔧 Convertendo para formato otimizado (16kHz mono)...")

                audio_path = None
                if transcription_text:
                    await emit("audio_optimization", 20, "♻️ Cache RAW encontrado — pulando otimização de áudio")
                else:
                    audio_path = await asyncio.to_thread(vomo.optimize_audio, file_path)
                    audio_duration = self._get_wav_duration_seconds(audio_path)
                    duration_str = f"{int(audio_duration // 60)}m{int(audio_duration % 60)}s" if audio_duration > 0 else "estimando..."
                    if is_video:
                        await emit("audio_optimization", 20, f"✅ Áudio extraído do vídeo ({duration_str})")
                    else:
                        await emit("audio_optimization", 20, f"✅ Áudio otimizado ({duration_str})")

                # Stage 2: Transcription (20-60%)
                if transcription_text:
                    await emit("transcription", 25, "♻️ RAW carregado do cache")
                    await emit("transcription", 60, "Transcrição concluída ✓")
                else:
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
                    if use_cache and cache_hash:
                        self._save_cached_raw(cache_hash, high_accuracy, transcription_text, PathLib(file_path).name)
            
            if mode == "RAW":
                return transcription_text

            # Stage 3: Formatting (60-100%)
            await emit("formatting", 65, "Preparando formatação com IA...")
            
            # Observação: `custom_prompt` em `mlx_vomo.py` sobrescreve apenas a camada de estilo/tabelas.
            # Para manter paridade com o CLI, só enviamos `custom_prompt` quando o usuário fornece.
            system_prompt = (custom_prompt or "").strip() or None
            
            import tempfile
            from pathlib import Path
            
            video_name = Path(file_path).stem
            await emit("formatting", 70, "Formatando documento com IA...")
            mode_suffix = mode.upper() if mode else "APOSTILA"

            with tempfile.TemporaryDirectory() as temp_dir:
                llm_warning: Optional[str] = None
                llm_fallback = False
                try:
                    final_text = await vomo.format_transcription_async(
                        transcription_text,
                        video_name=video_name,
                        output_folder=temp_dir,
                        mode=mode,
                        custom_prompt=system_prompt,
                        progress_callback=emit,
                        skip_audit=skip_legal_audit,
                        skip_fidelity_audit=skip_fidelity_audit,
                        skip_sources_audit=skip_sources_audit,
                    )
                    await emit("formatting", 95, "Documento formatado ✓")
                except Exception as format_exc:
                    format_message, root_exc = self._format_exception_message(format_exc)
                    classification = self._classify_llm_error(root_exc)
                    if classification and self._llm_raw_fallback_enabled():
                        llm_warning = f"Formatação por IA indisponível ({classification}). Salvando transcrição bruta."
                        logger.warning(f"{llm_warning} Detalhe: {format_message}")
                        llm_fallback = True
                        final_text = self._fallback_markdown_from_raw(transcription_text, video_name, llm_warning)
                        await emit("formatting", 95, llm_warning)
                    else:
                        raise

                analysis_report = None
                validation_report = None
                report_paths = {}
                issues: list[dict] = []
                cli_issues = None
                auto_applied = False
                auto_applied_fixes = []
                original_text = final_text
                audit_summary = None

                if not llm_fallback:
                    await emit("audit", 96, "Auditando qualidade do documento...")
                    try:
                        from app.services.quality_service import quality_service
                        analysis_report = await quality_service.analyze_structural_issues(
                            content=final_text,
                            document_name=video_name,
                            raw_content=transcription_text
                        )
                        cli_issues = (analysis_report or {}).get("cli_issues") or analysis_report
                        validation_report = await quality_service.validate_document_full(
                            raw_content=transcription_text,
                            formatted_content=final_text,
                            document_name=video_name,
                            mode=mode,
                        )

                        if apply_fixes and (analysis_report or {}).get("total_issues", 0) > 0:
                            await emit("audit", 97, "Aplicando correcoes estruturais automaticamente...")
                            original_text = final_text
                            final_text, auto_applied, auto_applied_fixes = await self._auto_apply_structural_fixes(
                                final_text=final_text,
                                transcription_text=transcription_text,
                                video_name=video_name
                            )
                            if auto_applied:
                                analysis_report = await quality_service.analyze_structural_issues(
                                    content=final_text,
                                    document_name=video_name,
                                    raw_content=transcription_text
                                )
                        
                        if auto_apply_content_fixes:
                            logger.info("⚙️ Auto-aplicação de correções de conteúdo: ATIVADA")
                            if not transcription_text:
                                logger.warning("⚠️ Transcrição RAW não disponível - correções de conteúdo ignoradas")
                                await emit("audit", 97, "RAW ausente - correções de conteúdo ignoradas")
                            else:
                                await emit("audit", 97, "Auto-aplicando correcoes de conteudo via IA...")
                                content_issues = self._build_audit_issues(
                                    analysis_report,
                                    video_name,
                                    raw_content=transcription_text,
                                    formatted_content=final_text
                                )
                                content_only = [i for i in content_issues if i.get("fix_type") == "content"]

                                legal_report_for_auto = self._extract_audit_report(final_text)
                                if not legal_report_for_auto:
                                    legal_report_path = Path(temp_dir) / f"{video_name}_{mode_suffix}_AUDITORIA.md"
                                    if legal_report_path.exists():
                                        legal_report_for_auto = legal_report_path.read_text(encoding="utf-8", errors="ignore")
                                legal_issues_for_auto = self._parse_legal_audit_issues(legal_report_for_auto)
                                if legal_issues_for_auto:
                                    content_only.extend(legal_issues_for_auto)
                                
                                if content_only:
                                    if not original_text:
                                        original_text = final_text
                                    final_text, content_applied, content_fixes = await self._auto_apply_content_fixes(
                                        final_text=final_text,
                                        transcription_text=transcription_text,
                                        video_name=video_name,
                                        content_issues=content_only,
                                        model_selection=model_selection
                                    )
                                    if content_applied:
                                        auto_applied = True
                                        auto_applied_fixes.extend(content_fixes)
                                        logger.info("🔄 Re-analisando documento após correções de conteúdo...")
                                        await emit("audit", 98, "Re-analisando após correções de conteúdo...")
                                        analysis_report = await quality_service.analyze_structural_issues(
                                            content=final_text,
                                            document_name=video_name,
                                            raw_content=transcription_text
                                        )
                                else:
                                    logger.info("ℹ️ Nenhum issue de conteúdo detectado para auto-aplicação")
                        else:
                            logger.info("⚙️ Auto-aplicação de correções de conteúdo: DESATIVADA")

                        issues = self._build_audit_issues(
                            analysis_report,
                            video_name,
                            raw_content=transcription_text,
                            formatted_content=final_text,
                        )

                    except Exception as audit_error:
                        logger.warning(f"Auditoria HIL falhou (nao-bloqueante): {audit_error}")
                        issues = []

                report_paths = self._persist_transcription_outputs(
                    video_name=video_name,
                    mode=mode,
                    raw_text=transcription_text,
                    formatted_text=final_text,
                    analysis_report=analysis_report,
                    validation_report=validation_report,
                )

                output_dir = Path(report_paths["output_dir"])
                report_paths.update(
                    self._copy_cli_artifacts(temp_dir, output_dir, video_name, mode_suffix)
                )
                if llm_warning:
                    report_paths["llm_fallback"] = {
                        "enabled": True,
                        "reason": llm_warning,
                    }
                suggestions_path = self._write_hil_suggestions(
                    output_dir, video_name, mode_suffix, cli_issues
                )
                if suggestions_path:
                    report_paths["suggestions_path"] = suggestions_path

                if not llm_fallback:
                    audit_payload = self._run_audit_pipeline(
                        output_dir=output_dir,
                        report_paths=report_paths,
                        raw_text=transcription_text,
                        formatted_text=final_text,
                        analysis_report=analysis_report,
                        validation_report=validation_report,
                    )
                    if audit_payload:
                        audit_summary = audit_payload.get("summary")
                        if audit_payload.get("summary_path"):
                            report_paths["audit_summary_path"] = audit_payload["summary_path"]
                        if audit_payload.get("report_keys"):
                            report_paths["audit_report_keys"] = audit_payload["report_keys"]

                    legal_report = self._load_legal_audit_report(report_paths)
                    legal_issues = self._parse_legal_audit_issues(legal_report)
                    if legal_issues:
                        issues.extend(legal_issues)

                docx_path = self._generate_docx(vomo, final_text, video_name, output_dir, mode)
                if docx_path:
                    report_paths["docx_path"] = docx_path

                if auto_applied and original_text:
                    original_md_path = output_dir / f"{video_name}_ORIGINAL_{mode_suffix}.md"
                    original_md_path.write_text(original_text or "", encoding="utf-8")
                    report_paths["original_md_path"] = str(original_md_path)
                    original_docx_path = self._generate_docx(
                        vomo, original_text, f"{video_name}_ORIGINAL", output_dir, mode
                    )
                    if original_docx_path:
                        report_paths["original_docx_path"] = original_docx_path

                await emit("audit_complete", 98, json.dumps({
                    "issues": issues,
                    "total_issues": len(issues),
                    "document_preview": final_text[:2000] if final_text else "",
                    "reports": report_paths,
                    "audit_summary": audit_summary,
                    "auto_applied": auto_applied,
                    "auto_applied_fixes": auto_applied_fixes,
                    "llm_fallback": bool(llm_warning),
                    "llm_message": llm_warning,
                }))

            await emit("formatting", 100, "Documento finalizado ✓")
            quality_payload = {
                "validation_report": validation_report,
                "analysis_result": analysis_report,
                "selected_fix_ids": [],
                "applied_fixes": [],
                "suggestions": None,
                "warnings": [llm_warning] if llm_warning else [],
            }
            return {
                "content": final_text,
                "raw_content": transcription_text,
                "reports": report_paths,
                "audit_issues": issues,
                "audit_summary": audit_summary,
                "quality": quality_payload,
            }

        except Exception as e:
            message, root = self._format_exception_message(e)
            logger.error(f"Erro no serviço de transcrição (SSE): {message}")
            if root is not e:
                raise RuntimeError(message) from root
            raise

    async def process_batch_with_progress(
        self, 
        file_paths: list,
        file_names: list,
        mode: str = "APOSTILA", 
        thinking_level: str = "medium",
        custom_prompt: Optional[str] = None,
        high_accuracy: bool = False,
        on_progress: Optional[Callable[[str, int, str], Awaitable[None]]] = None,
        model_selection: Optional[str] = None,
        use_cache: bool = True,
        auto_apply_fixes: bool = True,
        auto_apply_content_fixes: bool = False,
        skip_legal_audit: bool = False,
        skip_audit: Optional[bool] = None,
        skip_fidelity_audit: bool = False,
        skip_sources_audit: bool = False,
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
            if skip_audit is not None:
                skip_legal_audit = skip_legal_audit or skip_audit
            apply_fixes = auto_apply_fixes
            vomo = self._get_vomo(model_selection=model_selection, thinking_level=thinking_level)
            total_files = len(file_paths)
            all_raw_transcriptions = []
            
            logger.info(f"🎤 Iniciando processamento em lote: {total_files} arquivos [{mode}]")
            
            for idx, (file_path, file_name) in enumerate(zip(file_paths, file_names)):
                file_num = idx + 1
                # Calculate progress range for this file (each file gets equal share of 0-60%)
                file_progress_base = int((idx / total_files) * 60)
                file_progress_increment = int(60 / total_files)
                
                # Detect file type
                from pathlib import Path as PathLib
                import os as os_module
                
                file_ext = PathLib(file_path).suffix.lower()
                file_size_mb = os_module.path.getsize(file_path) / (1024 * 1024)
                is_text_input = file_ext in [".txt", ".md"]
                is_video = file_ext in ['.mp4', '.mov', '.mkv', '.avi', '.webm', '.m4v', '.wmv', '.flv']
                
                cache_hash = None
                transcription_text = None
                if use_cache:
                    try:
                        cache_hash = self._compute_file_hash(file_path)
                        transcription_text = self._load_cached_raw(cache_hash, high_accuracy)
                    except Exception as cache_error:
                        logger.warning(f"Falha ao carregar cache RAW ({file_name}): {cache_error}")
                        transcription_text = None

                # Stage: Input handling for this file
                if is_text_input:
                    await emit("batch", file_progress_base, f"[{file_num}/{total_files}] 📄 Texto ({file_ext.upper()}, {file_size_mb:.1f}MB): {file_name}")
                    await emit("batch", file_progress_base + 2, f"[{file_num}/{total_files}] 📥 Lendo arquivo de texto...")

                    if transcription_text:
                        await emit("batch", file_progress_base + 5, f"[{file_num}/{total_files}] ♻️ Cache RAW encontrado: {file_name}")
                    else:
                        transcription_text = PathLib(file_path).read_text(encoding="utf-8", errors="ignore")
                        if use_cache and cache_hash:
                            self._save_cached_raw(cache_hash, high_accuracy, transcription_text, file_name)
                        await emit("batch", file_progress_base + 5, f"[{file_num}/{total_files}] ✅ Texto carregado: {file_name}")

                    transcribe_progress = file_progress_base + int(file_progress_increment * 0.3)
                    await emit("batch", transcribe_progress, f"[{file_num}/{total_files}] 📄 Texto pronto: {file_name}")
                else:
                    # Stage: Audio optimization for this file
                    if is_video:
                        await emit("batch", file_progress_base, f"[{file_num}/{total_files}] 🎬 Vídeo ({file_ext.upper()}, {file_size_mb:.1f}MB): {file_name}")
                        await emit("batch", file_progress_base + 2, f"[{file_num}/{total_files}] 📤 Extraindo áudio do vídeo...")
                    else:
                        await emit("batch", file_progress_base, f"[{file_num}/{total_files}] 🎵 Áudio ({file_ext.upper()}, {file_size_mb:.1f}MB): {file_name}")
                        await emit("batch", file_progress_base + 2, f"[{file_num}/{total_files}] 🔧 Convertendo para 16kHz mono...")

                    audio_path = None
                    if transcription_text:
                        await emit("batch", file_progress_base + 5, f"[{file_num}/{total_files}] ♻️ Cache RAW encontrado: {file_name}")
                    else:
                        audio_path = await asyncio.to_thread(vomo.optimize_audio, file_path)
                        await emit("batch", file_progress_base + 5, f"[{file_num}/{total_files}] ✅ Áudio pronto: {file_name}")

                    # Stage: Transcription for this file
                    transcribe_progress = file_progress_base + int(file_progress_increment * 0.3)
                    if transcription_text:
                        await emit("batch", transcribe_progress, f"[{file_num}/{total_files}] ♻️ RAW em cache: {file_name}")
                    else:
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
                        if use_cache and cache_hash:
                            self._save_cached_raw(cache_hash, high_accuracy, transcription_text, file_name)
                
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
                return {"content": unified_raw, "raw_content": unified_raw, "reports": {}}
            
            # Stage 3: Format unified document (60-100%)
            await emit("formatting", 65, "Preparando formatação unificada...")
            
            # Observação: `custom_prompt` em `mlx_vomo.py` sobrescreve apenas a camada de estilo/tabelas.
            # Para manter paridade com o CLI, só enviamos `custom_prompt` quando o usuário fornece.
            system_prompt = (custom_prompt or "").strip() or None
            
            import tempfile
            
            # Use first file name as base for the unified document
            base_name = file_names[0].rsplit('.', 1)[0] if file_names else "Aulas_Unificadas"
            video_name = f"{base_name}_UNIFICADO"
            
            await emit("formatting", 70, "Formatando documento unificado com IA...")
            mode_suffix = mode.upper() if mode else "APOSTILA"

            with tempfile.TemporaryDirectory() as temp_dir:
                llm_warning: Optional[str] = None
                llm_fallback = False
                try:
                    final_text = await vomo.format_transcription_async(
                        unified_raw,
                        video_name=video_name,
                        output_folder=temp_dir,
                        mode=mode,
                        custom_prompt=system_prompt,
                        progress_callback=emit,
                        skip_audit=skip_legal_audit,
                        skip_fidelity_audit=skip_fidelity_audit,
                        skip_sources_audit=skip_sources_audit,
                    )
                except Exception as format_exc:
                    format_message, root_exc = self._format_exception_message(format_exc)
                    classification = self._classify_llm_error(root_exc)
                    if classification and self._llm_raw_fallback_enabled():
                        llm_warning = f"Formatação por IA indisponível ({classification}). Salvando transcrição bruta unificada."
                        logger.warning(f"{llm_warning} Detalhe: {format_message}")
                        llm_fallback = True
                        final_text = self._fallback_markdown_from_raw(unified_raw, video_name, llm_warning)
                        await emit("formatting", 92, llm_warning)
                    else:
                        raise

                # Stage 4: HIL Audit (95-98%) - Analyze for issues
                analysis_report = None
                validation_report = None
                report_paths = {}
                issues: list[dict] = []
                cli_issues = None
                auto_applied = False
                auto_applied_fixes = []
                original_text = final_text
                audit_summary = None

                if not llm_fallback:
                    await emit("audit", 96, "Auditando qualidade do documento unificado...")
                    try:
                        from app.services.quality_service import quality_service
                        analysis_report = await quality_service.analyze_structural_issues(
                            content=final_text,
                            document_name=video_name,
                            raw_content=unified_raw
                        )
                        cli_issues = (analysis_report or {}).get("cli_issues") or analysis_report
                        validation_report = await quality_service.validate_document_full(
                            raw_content=unified_raw,
                            formatted_content=final_text,
                            document_name=video_name,
                            mode=mode,
                        )

                        if apply_fixes and (analysis_report or {}).get("total_issues", 0) > 0:
                            await emit("audit", 97, "Aplicando correcoes estruturais automaticamente...")
                            original_text = final_text
                            final_text, auto_applied, auto_applied_fixes = await self._auto_apply_structural_fixes(
                                final_text=final_text,
                                transcription_text=unified_raw,
                                video_name=video_name
                            )
                            if auto_applied:
                                analysis_report = await quality_service.analyze_structural_issues(
                                    content=final_text,
                                    document_name=video_name,
                                    raw_content=unified_raw
                                )

                        if auto_apply_content_fixes:
                            logger.info("⚙️ Auto-aplicação de correções de conteúdo: ATIVADA")
                            if not unified_raw:
                                logger.warning("⚠️ Transcrição RAW não disponível - correções de conteúdo ignoradas")
                                await emit("audit", 97, "RAW ausente - correções de conteúdo ignoradas")
                            else:
                                await emit("audit", 97, "Auto-aplicando correcoes de conteudo via IA...")
                                content_issues = self._build_audit_issues(
                                    analysis_report,
                                    video_name,
                                    raw_content=unified_raw,
                                    formatted_content=final_text,
                                )
                                content_only = [i for i in content_issues if i.get("fix_type") == "content"]

                                legal_report_for_auto = self._extract_audit_report(final_text)
                                if not legal_report_for_auto:
                                    legal_report_path = Path(temp_dir) / f"{video_name}_{mode_suffix}_AUDITORIA.md"
                                    if legal_report_path.exists():
                                        legal_report_for_auto = legal_report_path.read_text(encoding="utf-8", errors="ignore")
                                legal_issues_for_auto = self._parse_legal_audit_issues(legal_report_for_auto)
                                if legal_issues_for_auto:
                                    content_only.extend(legal_issues_for_auto)

                                if content_only:
                                    if not original_text:
                                        original_text = final_text
                                    final_text, content_applied, content_fixes = await self._auto_apply_content_fixes(
                                        final_text=final_text,
                                        transcription_text=unified_raw,
                                        video_name=video_name,
                                        content_issues=content_only,
                                        model_selection=model_selection,
                                    )
                                    if content_applied:
                                        auto_applied = True
                                        auto_applied_fixes.extend(content_fixes)
                                        await emit("audit", 98, "Re-analisando após correções de conteúdo...")
                                        analysis_report = await quality_service.analyze_structural_issues(
                                            content=final_text,
                                            document_name=video_name,
                                            raw_content=unified_raw,
                                        )
                                else:
                                    logger.info("ℹ️ Nenhum issue de conteúdo detectado para auto-aplicação")
                        else:
                            logger.info("⚙️ Auto-aplicação de correções de conteúdo: DESATIVADA")

                        issues = self._build_audit_issues(
                            analysis_report,
                            video_name,
                            raw_content=unified_raw,
                            formatted_content=final_text,
                        )

                    except Exception as audit_error:
                        logger.warning(f"Auditoria HIL falhou (nao-bloqueante): {audit_error}")
                        issues = []

                report_paths = self._persist_transcription_outputs(
                    video_name=video_name,
                    mode=mode,
                    raw_text=unified_raw,
                    formatted_text=final_text,
                    analysis_report=analysis_report,
                    validation_report=validation_report,
                )

                output_dir = Path(report_paths["output_dir"])
                report_paths.update(
                    self._copy_cli_artifacts(temp_dir, output_dir, video_name, mode_suffix)
                )
                if llm_warning:
                    report_paths["llm_fallback"] = {
                        "enabled": True,
                        "reason": llm_warning,
                    }
                suggestions_path = self._write_hil_suggestions(
                    output_dir, video_name, mode_suffix, cli_issues
                )
                if suggestions_path:
                    report_paths["suggestions_path"] = suggestions_path

                if not llm_fallback:
                    audit_payload = self._run_audit_pipeline(
                        output_dir=output_dir,
                        report_paths=report_paths,
                        raw_text=unified_raw,
                        formatted_text=final_text,
                        analysis_report=analysis_report,
                        validation_report=validation_report,
                    )
                    if audit_payload:
                        audit_summary = audit_payload.get("summary")
                        if audit_payload.get("summary_path"):
                            report_paths["audit_summary_path"] = audit_payload["summary_path"]
                        if audit_payload.get("report_keys"):
                            report_paths["audit_report_keys"] = audit_payload["report_keys"]

                    legal_report = self._load_legal_audit_report(report_paths)
                    legal_issues = self._parse_legal_audit_issues(legal_report)
                    if legal_issues:
                        issues.extend(legal_issues)

                docx_path = self._generate_docx(vomo, final_text, video_name, output_dir, mode)
                if docx_path:
                    report_paths["docx_path"] = docx_path

                if auto_applied and original_text:
                    original_md_path = output_dir / f"{video_name}_ORIGINAL_{mode_suffix}.md"
                    original_md_path.write_text(original_text or "", encoding="utf-8")
                    report_paths["original_md_path"] = str(original_md_path)
                    original_docx_path = self._generate_docx(
                        vomo, original_text, f"{video_name}_ORIGINAL", output_dir, mode
                    )
                    if original_docx_path:
                        report_paths["original_docx_path"] = original_docx_path

                await emit("audit_complete", 98, json.dumps({
                    "issues": issues,
                    "total_issues": len(issues),
                    "document_preview": final_text[:2000] if final_text else "",
                    "reports": report_paths,
                    "audit_summary": audit_summary,
                    "auto_applied": auto_applied,
                    "auto_applied_fixes": auto_applied_fixes,
                    "llm_fallback": bool(llm_warning),
                    "llm_message": llm_warning,
                }))

            await emit("formatting", 100, f"Documento unificado ({total_files} partes) ✓")
            quality_payload = {
                "validation_report": validation_report,
                "analysis_result": analysis_report,
                "selected_fix_ids": [],
                "applied_fixes": [],
                "suggestions": None,
                "warnings": [llm_warning] if llm_warning else [],
            }
            return {
                "content": final_text,
                "raw_content": unified_raw,
                "reports": report_paths,
                "audit_issues": issues,
                "audit_summary": audit_summary,
                "quality": quality_payload,
            }

        except Exception as e:
            message, root = self._format_exception_message(e)
            logger.error(f"Erro no serviço de transcrição em lote: {message}")
            if root is not e:
                raise RuntimeError(message) from root
            raise

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

    def _get_transcription_cache_dir(self) -> Path:
        try:
            from app.core.config import settings
            base_dir = Path(settings.LOCAL_STORAGE_PATH) / "transcription_cache"
        except Exception:
            base_dir = Path("./storage") / "transcription_cache"
        base_dir.mkdir(parents=True, exist_ok=True)
        return base_dir

    def _get_raw_cache_path(self, file_hash: str, high_accuracy: bool) -> Path:
        suffix = "beam" if high_accuracy else "base"
        return self._get_transcription_cache_dir() / file_hash / f"raw_{suffix}.txt"

    def _load_cached_raw(self, file_hash: str, high_accuracy: bool) -> Optional[str]:
        cache_path = self._get_raw_cache_path(file_hash, high_accuracy)
        if cache_path.exists():
            try:
                return cache_path.read_text(encoding="utf-8")
            except Exception:
                return None
        return None

    def _save_cached_raw(self, file_hash: str, high_accuracy: bool, raw_text: str, source_name: str = "") -> None:
        cache_path = self._get_raw_cache_path(file_hash, high_accuracy)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(raw_text or "", encoding="utf-8")
        meta_path = cache_path.parent / "meta.json"
        try:
            meta = {
                "file_hash": file_hash,
                "high_accuracy": bool(high_accuracy),
                "source_name": source_name,
                "updated_at": datetime.utcnow().isoformat(),
            }
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

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

        def _handle_llm_error(exc: Exception) -> None:
            msg, root = self._format_exception_message(exc)
            classification = self._classify_llm_error(root)
            if classification and self._llm_raw_fallback_enabled():
                logger.warning(f"LLM indisponível ({classification}) ao gerar JSON: {msg}")
                return None
            raise exc

        if getattr(vomo, "provider", "") == "openai":
            client = getattr(vomo, "openai_client", None)
            model = getattr(vomo, "openai_model", "gpt-5-mini-2025-08-07")
            if client:
                try:
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
                except Exception as exc:
                    return _handle_llm_error(exc)

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

            try:
                response_text = await asyncio.to_thread(call_openai)
                return self._safe_json_extract(response_text)
            except Exception as exc:
                return _handle_llm_error(exc)

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

        try:
            response = await asyncio.to_thread(call_gemini)
            response_text = response.text if hasattr(response, "text") else str(response)
            return self._safe_json_extract(response_text)
        except Exception as exc:
            return _handle_llm_error(exc)

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
        allow_indirect: bool = False,
        allow_summary: bool = False,
        use_cache: bool = True,
        auto_apply_fixes: bool = True,
        auto_apply_content_fixes: bool = False,
        skip_legal_audit: bool = False,
        skip_fidelity_audit: bool = False,
        skip_sources_audit: bool = False,
        on_progress: Optional[Callable[[str, int, str], Awaitable[None]]] = None,
    ) -> dict:
        async def emit(stage: str, progress: int, message: str):
            if on_progress:
                await on_progress(stage, progress, message)

        vomo = self._get_vomo(model_selection=model_selection, thinking_level=thinking_level)
        logger.info(f"🎤 Iniciando transcrição de audiência: {file_path} [case_id={case_id}]")

        cache_hash = None
        transcription_text = None
        asr_segments = []
        cache_hit = False
        if use_cache:
            try:
                cache_hash = self._compute_file_hash(file_path)
                transcription_text = self._load_cached_raw(cache_hash, high_accuracy)
                cache_hit = bool(transcription_text)
                if cache_hit:
                    logger.info("♻️ RAW cache hit (pulando transcrição)")
            except Exception as cache_error:
                logger.warning(f"Falha ao carregar cache RAW: {cache_error}")
                transcription_text = None

        await emit("audio_optimization", 0, "Otimizando áudio...")
        audio_path = await asyncio.to_thread(vomo.optimize_audio, file_path)
        await emit("audio_optimization", 20, "Áudio otimizado ✓")

        if cache_hit:
            await emit("transcription", 30, "♻️ RAW cache encontrado — pulando transcrição")
        else:
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

            if use_cache and cache_hash:
                self._save_cached_raw(cache_hash, high_accuracy, transcription_text, Path(file_path).name)
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
            "format_options": {
                "allow_indirect": allow_indirect,
                "allow_summary": allow_summary,
            },
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
        format_source_text = transcript_markdown or (transcription_text or "")
        format_source_label = "transcript_markdown" if transcript_markdown else "raw_transcript"

        format_mode_normalized = (format_mode or "AUDIENCIA").strip().upper()
        if format_mode_normalized == "CUSTOM":
            format_mode_normalized = "AUDIENCIA"
        if format_mode_normalized not in {"AUDIENCIA", "REUNIAO", "DEPOIMENTO", "APOSTILA", "FIDELIDADE"}:
            format_mode_normalized = "AUDIENCIA"
        allow_indirect = bool(allow_indirect)
        allow_summary = bool(allow_summary)
        if format_mode_normalized not in {"AUDIENCIA", "REUNIAO", "DEPOIMENTO"}:
            allow_indirect = False
            allow_summary = False
        if hearing_payload.get("format_options"):
            hearing_payload["format_options"]["allow_indirect"] = allow_indirect
            hearing_payload["format_options"]["allow_summary"] = allow_summary

        video_name = f"hearing_{case_id}"
        formatted_text = None
        formatted_path = None
        docx_path = None
        analysis_report = None
        validation_report = None
        audit_summary = None
        report_paths = {
            "output_dir": str(run_dir),
            "raw_path": str(raw_path),
        }
        format_source_path = run_dir / "transcript_for_formatting.md"
        if format_source_text:
            format_source_path.write_text(format_source_text, encoding="utf-8")
            report_paths["format_source_path"] = str(format_source_path)
            hearing_payload["format_source"] = format_source_label

        if format_enabled:
            await emit("formatting", 75, "Formatando texto da audiência...")
            llm_warning: Optional[str] = None
            llm_fallback = False
            try:
                formatted_text = await vomo.format_transcription_async(
                    format_source_text,
                    video_name=video_name,
                    output_folder=str(run_dir),
                    mode=format_mode_normalized,
                    custom_prompt=custom_prompt,
                    progress_callback=emit,
                    skip_audit=skip_legal_audit,
                    skip_fidelity_audit=skip_fidelity_audit,
                    skip_sources_audit=skip_sources_audit,
                    allow_indirect=allow_indirect,
                    allow_summary=allow_summary,
                )
                await emit("formatting", 92, "Texto formatado ✓")
            except Exception as format_exc:
                format_message, root_exc = self._format_exception_message(format_exc)
                classification = self._classify_llm_error(root_exc)
                if classification and self._llm_raw_fallback_enabled():
                    llm_warning = f"Formatação por IA indisponível ({classification}). Salvando transcrição bruta."
                    logger.warning(f"{llm_warning} Detalhe: {format_message}")
                    llm_fallback = True
                    formatted_text = self._fallback_markdown_from_raw(format_source_text, video_name, llm_warning)
                    await emit("formatting", 92, llm_warning)
                    try:
                        hearing_payload.setdefault("audit", {}).setdefault("warnings", []).append("llm_format_fallback")
                    except Exception:
                        pass
                else:
                    raise

            auto_applied = False
            original_text = formatted_text

            if formatted_text and not llm_fallback:
                try:
                    from app.services.quality_service import quality_service
                    analysis_report = await quality_service.analyze_structural_issues(
                        content=formatted_text,
                        document_name=video_name,
                        raw_content=format_source_text
                    )
                    validation_report = await quality_service.validate_document_full(
                        raw_content=format_source_text,
                        formatted_content=formatted_text,
                        document_name=video_name,
                        mode=format_mode_normalized,
                    )

                    if auto_apply_fixes and (analysis_report or {}).get("total_issues", 0) > 0:
                        original_text = formatted_text
                        formatted_text, auto_applied, _ = await self._auto_apply_structural_fixes(
                            final_text=formatted_text,
                            transcription_text=format_source_text,
                            video_name=video_name
                        )
                        if auto_applied:
                            analysis_report = await quality_service.analyze_structural_issues(
                                content=formatted_text,
                                document_name=video_name,
                                raw_content=format_source_text
                            )

                    if auto_apply_content_fixes:
                        logger.info("⚙️ Auto-aplicação de correções de conteúdo (audiência): ATIVADA")
                        if not format_source_text:
                            logger.warning("⚠️ Transcrição RAW não disponível - correções de conteúdo ignoradas")
                        else:
                            content_issues = self._build_audit_issues(
                                analysis_report,
                                video_name,
                                raw_content=format_source_text,
                                formatted_content=formatted_text
                            )
                            content_only = [i for i in content_issues if i.get("fix_type") == "content"]

                            legal_report_for_auto = self._extract_audit_report(formatted_text)
                            if not legal_report_for_auto:
                                legal_report_path = run_dir / f"{video_name}_{format_mode_normalized}_AUDITORIA.md"
                                if legal_report_path.exists():
                                    legal_report_for_auto = legal_report_path.read_text(encoding="utf-8", errors="ignore")
                            legal_issues_for_auto = self._parse_legal_audit_issues(legal_report_for_auto)
                            if legal_issues_for_auto:
                                content_only.extend(legal_issues_for_auto)

                            if content_only:
                                if not original_text:
                                    original_text = formatted_text
                                formatted_text, content_applied, _ = await self._auto_apply_content_fixes(
                                    final_text=formatted_text,
                                    transcription_text=format_source_text,
                                    video_name=video_name,
                                    content_issues=content_only,
                                    model_selection=model_selection
                                )
                                if content_applied:
                                    auto_applied = True
                                    analysis_report = await quality_service.analyze_structural_issues(
                                        content=formatted_text,
                                        document_name=video_name,
                                        raw_content=format_source_text
                                    )
                            else:
                                logger.info("ℹ️ Nenhum issue de conteúdo detectado para auto-aplicação (audiência)")
                    else:
                        logger.info("⚙️ Auto-aplicação de correções de conteúdo (audiência): DESATIVADA")
                except Exception as audit_error:
                    logger.warning(f"Falha na auditoria de audiência (não-bloqueante): {audit_error}")

            if formatted_text:
                formatted_path = run_dir / f"hearing_formatted_{format_mode_normalized.lower()}.md"
                formatted_path.write_text(formatted_text, encoding="utf-8")
                report_paths["md_path"] = str(formatted_path)
                if llm_warning:
                    report_paths["llm_fallback"] = {
                        "enabled": True,
                        "reason": llm_warning,
                    }

            if analysis_report:
                analysis_path = run_dir / "hearing_analysis.json"
                analysis_path.write_text(json.dumps(analysis_report, ensure_ascii=False, indent=2), encoding="utf-8")
                report_paths["analysis_path"] = str(analysis_path)
            if validation_report:
                validation_path = run_dir / "hearing_validation.json"
                validation_path.write_text(json.dumps(validation_report, ensure_ascii=False, indent=2), encoding="utf-8")
                report_paths["validation_path"] = str(validation_path)

            report_paths.update(
                self._copy_cli_artifacts(str(run_dir), run_dir, video_name, format_mode_normalized)
            )

            if not llm_fallback:
                audit_summary = None
                audit_payload = self._run_audit_pipeline(
                    output_dir=run_dir,
                    report_paths=report_paths,
                    raw_text=format_source_text,
                    formatted_text=formatted_text,
                    analysis_report=analysis_report,
                    validation_report=validation_report,
                )
                if audit_payload:
                    audit_summary = audit_payload.get("summary")
                    if audit_payload.get("summary_path"):
                        report_paths["audit_summary_path"] = audit_payload["summary_path"]
                    if audit_payload.get("report_keys"):
                        report_paths["audit_report_keys"] = audit_payload["report_keys"]

                # Auditoria especializada para hearing (AUDIENCIA/REUNIAO/DEPOIMENTO)
                if format_mode_normalized in {"AUDIENCIA", "REUNIAO", "DEPOIMENTO"}:
                    try:
                        import sys
                        project_root = str(Path(__file__).resolve().parents[4])
                        if project_root not in sys.path:
                            sys.path.insert(0, project_root)
                        from audit_hearing import auditar_hearing_completo, gerar_relatorio_hearing_markdown
                        
                        hearing_audit = auditar_hearing_completo(
                            raw_text=format_source_text or "",
                            formatted_text=formatted_text or "",
                            segments=segments,
                            speakers=payload_speakers,
                            evidence=evidence,
                            claims=claims,
                            contradictions=contradictions,
                            mode=format_mode_normalized,
                        )
                        hearing_payload["audit"]["hearing_fidelity"] = hearing_audit
                        
                        # Adicionar warning se revisão recomendada
                        if hearing_audit.get("recomendacao_hil", {}).get("pausar_para_revisao"):
                            hearing_payload["audit"]["warnings"].append("fidelity_review_recommended")
                        
                        # Gerar relatório markdown
                        hearing_audit_md = gerar_relatorio_hearing_markdown(hearing_audit, video_name)
                        audit_report_path = run_dir / f"{video_name}_AUDITORIA_HEARING.md"
                        audit_report_path.write_text(hearing_audit_md, encoding="utf-8")
                        report_paths["hearing_audit_path"] = str(audit_report_path)
                        
                        logger.info(f"✅ Auditoria de hearing concluída: nota={hearing_audit.get('nota_fidelidade', 0)}/10")
                    except Exception as hearing_audit_error:
                        logger.warning(f"Falha na auditoria de hearing (não-bloqueante): {hearing_audit_error}")

            if formatted_text:
                try:
                    docx_path = vomo.save_as_word(
                        formatted_text=formatted_text,
                        video_name=video_name,
                        output_folder=str(run_dir),
                        mode=format_mode_normalized
                    )
                except Exception as e:
                    logger.warning(f"Falha ao gerar Word da audiência: {e}")
            if docx_path:
                report_paths["docx_path"] = str(docx_path)

        hearing_payload["formatted_text"] = formatted_text
        hearing_payload["formatted_mode"] = format_mode_normalized if format_enabled else None
        hearing_payload["custom_prompt_used"] = bool(custom_prompt)
        hearing_payload["reports"] = {
            "analysis": analysis_report,
            "validation": validation_report,
            "audit_summary": audit_summary,
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
