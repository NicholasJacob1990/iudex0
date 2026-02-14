import sys
import os
import asyncio
import json
import shutil
import contextlib
import threading
import concurrent.futures
import select
import socket
from typing import Optional, Callable, Tuple, Awaitable, Dict, Any
import logging
import time
import wave
import re
import hashlib
import uuid
import subprocess
import ipaddress
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from tenacity import RetryError
from app.services.mlx_loader import load_vomo_class

# Import FidelityMatcher para validação de referências legais
try:
    from app.services.fidelity_matcher import FidelityMatcher
except ImportError:
    FidelityMatcher = None

logger = logging.getLogger(__name__)

_VOMO_CLASS = None


def _load_vomo_class():
    """
    Carrega VomoMLX com fallback por caminho absoluto.
    Isso evita falhas quando o runtime da API não resolve a raiz do projeto igual ao CLI.
    """
    global _VOMO_CLASS
    if _VOMO_CLASS is not None:
        return _VOMO_CLASS
    _VOMO_CLASS = load_vomo_class(caller_file=__file__)
    return _VOMO_CLASS


def _whisper_transcribe_worker(
    out_path: str,
    audio_path: str,
    *,
    mode: str,
    high_accuracy: bool,
    diarization: Optional[bool],
    diarization_strict: bool,
    language: Optional[str],
) -> None:
    """
    Transcrição Whisper em processo separado para permitir timeout/terminate.
    """
    import traceback

    payload: Dict[str, Any] = {"ok": False, "result": None, "error": None}
    try:
        VomoMLX = _load_vomo_class()

        vomo = VomoMLX(provider="gemini")
        full_result = vomo.transcribe_file_full(
            audio_path,
            mode=mode,
            high_accuracy=bool(high_accuracy),
            diarization=diarization,
            diarization_strict=bool(diarization_strict),
            language=language,
        )
        payload["ok"] = True
        if isinstance(full_result, dict):
            payload["result"] = {
                "text": full_result.get("text", ""),
                "words": full_result.get("words", []),
                "segments": full_result.get("segments", []),
                "_needs_external_diarization": full_result.get("_needs_external_diarization", False),
            }
        else:
            payload["result"] = {"text": "", "words": []}
    except Exception as e:
        payload["error"] = {"message": str(e), "traceback": traceback.format_exc()}

    try:
        Path(out_path).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except Exception:
        # Evitar crash silencioso do worker (melhor esforço)
        pass


class TranscriptionService:
    def __init__(self):
        # Lazy init: evita importar/carregar MLX/Gemini no boot da API (mantém backend saudável).
        self.vomo = None
        self.vomo_config: Optional[Tuple[str, str, bool, Optional[str]]] = None
        # Protege mutações de self.vomo em cenários concorrentes (ex.: instância compartilhada na API).
        self._vomo_lock = threading.RLock()

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
        if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
            return "timeout"
        message = str(exc or "").lower()
        if any(token in message for token in ("timeout", "timed out", "deadline exceeded")):
            return "timeout"
        code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
        if code == 429:
            return "quota_exceeded"
        if any(token in message for token in ("resource_exhausted", "resource exhausted", "quota exceeded", "rate_limit_exceeded", "rate limit exceeded", "too many requests", "429")):
            return "quota_exceeded"
        if any(token in message for token in ("permission_denied", "unauthorized", "api key", "invalid api key", "401", "403")):
            return "auth"
        return None

    def _safe_int_env(self, name: str, default: int) -> int:
        try:
            value = int(os.getenv(name, str(default)))
            return value if value >= 0 else default
        except Exception:
            return default

    def _compute_adaptive_format_timeouts(self, source_text: str) -> Tuple[int, int, int]:
        chars_per_chunk = max(1000, self._safe_int_env("IUDEX_FORMAT_TIMEOUT_CHARS_PER_CHUNK", 15000))
        per_chunk_timeout = max(30, self._safe_int_env("IUDEX_FORMAT_TIMEOUT_PER_CHUNK_SECONDS", 120))
        base_timeout = max(60, self._safe_int_env("IUDEX_FORMAT_TIMEOUT_SECONDS", 900))

        text_len = len(source_text or "")
        estimated_chunks = max(1, (text_len + chars_per_chunk - 1) // chars_per_chunk)
        global_timeout = max(base_timeout, estimated_chunks * per_chunk_timeout)

        max_timeout = self._safe_int_env("IUDEX_FORMAT_TIMEOUT_MAX_SECONDS", 0)
        if max_timeout > 0:
            global_timeout = min(global_timeout, max_timeout)

        configured_segment = self._safe_int_env("IUDEX_FORMAT_SEGMENT_TIMEOUT_SECONDS", 0)
        if configured_segment > 0:
            segment_timeout = configured_segment
        elif estimated_chunks > 1:
            auto_segment = self._safe_int_env("IUDEX_FORMAT_SEGMENT_TIMEOUT_AUTO_SECONDS", per_chunk_timeout)
            segment_timeout = max(30, auto_segment)
        else:
            segment_timeout = 0

        return global_timeout, segment_timeout, estimated_chunks

    def _resolve_stable_retry_model(self, model_selection: Optional[str]) -> Optional[str]:
        fallback_model = (os.getenv("IUDEX_FORMAT_RETRY_STABLE_MODEL", "gemini-2.0-flash") or "").strip()
        if not fallback_model:
            return None
        selected = (model_selection or "gemini-3-flash-preview").strip().lower()
        if selected.startswith("gemini-3") or "preview" in selected:
            return fallback_model
        return None

    async def _run_llm_format_with_resilience(
        self,
        *,
        vomo,
        source_text: str,
        video_name: str,
        output_folder: str,
        mode: str,
        custom_prompt: Optional[str],
        disable_tables: bool,
        progress_callback: Optional[Callable[[str, int, str], Awaitable[None]]],
        skip_audit: bool,
        skip_fidelity_audit: bool,
        skip_sources_audit: bool,
        model_selection: Optional[str],
        thinking_level: Optional[str],
        include_timestamps: bool = True,
        allow_indirect: bool = False,
        allow_summary: bool = False,
    ):
        normalized_source = source_text or ""
        timeout_seconds, segment_timeout_seconds, estimated_chunks = self._compute_adaptive_format_timeouts(normalized_source)
        format_kwargs = {
            "video_name": video_name,
            "output_folder": output_folder,
            "mode": mode,
            "custom_prompt": custom_prompt,
            "disable_tables": bool(disable_tables),
            "progress_callback": progress_callback,
            "skip_audit": skip_audit,
            "skip_fidelity_audit": skip_fidelity_audit,
            "skip_sources_audit": skip_sources_audit,
            "include_timestamps": bool(include_timestamps),
            "allow_indirect": bool(allow_indirect),
            "allow_summary": bool(allow_summary),
            "segment_timeout_seconds": segment_timeout_seconds or None,
        }

        async def _emit_retry(msg: str):
            if not progress_callback:
                return
            try:
                maybe = progress_callback("formatting", 88, msg)
                if asyncio.iscoroutine(maybe):
                    await maybe
            except Exception:
                pass

        try:
            formatted = await asyncio.wait_for(
                vomo.format_transcription_async(normalized_source, **format_kwargs),
                timeout=timeout_seconds,
            )
            return formatted, vomo
        except Exception as first_exc:
            first_message, first_root = self._format_exception_message(first_exc)
            classification = self._classify_llm_error(first_root)
            if classification not in {"timeout", "quota_exceeded"}:
                raise

            retry_timeout = max(timeout_seconds, int(timeout_seconds * 1.35))
            max_timeout = self._safe_int_env("IUDEX_FORMAT_TIMEOUT_MAX_SECONDS", 0)
            if max_timeout > 0:
                retry_timeout = min(retry_timeout, max_timeout)

            retry_vomo = vomo
            retry_model = self._resolve_stable_retry_model(model_selection)
            retry_label = "mesmo modelo"
            if retry_model:
                retry_vomo = self._get_vomo(model_selection=retry_model, thinking_level=thinking_level)
                retry_label = retry_model
                for attr in ("_current_language", "_output_language", "_current_mode"):
                    if hasattr(vomo, attr):
                        setattr(retry_vomo, attr, getattr(vomo, attr))

            logger.warning(
                "Formatação falhou na 1ª tentativa (%s). Retentando com %s "
                "(timeout=%ss, chunks_est=%s, segment_timeout=%ss). Detalhe: %s",
                classification,
                retry_label,
                retry_timeout,
                estimated_chunks,
                segment_timeout_seconds or 0,
                first_message,
            )
            await _emit_retry("Primeira tentativa falhou. Repetindo formatação com tolerância maior...")

            try:
                formatted = await asyncio.wait_for(
                    retry_vomo.format_transcription_async(normalized_source, **format_kwargs),
                    timeout=retry_timeout,
                )
                logger.info("Formatação recuperada na 2ª tentativa com %s.", retry_label)
                return formatted, retry_vomo
            except Exception as retry_exc:
                retry_message, _ = self._format_exception_message(retry_exc)
                logger.warning(
                    "2ª tentativa de formatação também falhou (modelo=%s). Detalhe: %s",
                    retry_label,
                    retry_message,
                )
                raise RuntimeError(
                    f"LLM formatting failed after retry ({classification}): {retry_message}"
                ) from retry_exc

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
            
            # Constrói padrão para evidência (com fronteira estrita para evitar matches
            # dentro de números maiores, ex.: "1578" dentro de "157835").
            escaped = re.escape(reference)
            julgado_pattern = re.sub(r"\\\s+", r"\\s+", escaped)
            julgado_pattern = rf"(?<![0-9A-Za-z]){julgado_pattern}(?![0-9A-Za-z])"
            evidence = _extract_raw_evidence(julgado_pattern) if julgado_pattern else []
            if raw_text and not evidence:
                # Se não há evidência confiável no RAW, o alerta tende a ser falso positivo.
                continue
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
        model_selection: Optional[str] = None,
        mode: Optional[str] = None,
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
                mode=mode,
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
                # Guard: never lose tables that existed before content fix
                def _count_tables(text: str) -> int:
                    cnt = 0
                    lines = (text or "").splitlines()
                    sep_pat = re.compile(r'^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$')
                    for i in range(len(lines) - 1):
                        h = lines[i].strip()
                        s = lines[i + 1].strip()
                        if '|' in h and h.count('|') >= 2 and sep_pat.match(s):
                            cnt += 1
                    return cnt

                tables_before = _count_tables(final_text)
                tables_after = _count_tables(corrected_text)
                if tables_before > 0 and tables_after == 0:
                    logger.warning("=" * 80)
                    logger.warning(f"⚠️ CONTENT FIX REMOVEU TODAS AS TABELAS ({tables_before} → 0), REVERTENDO")
                    logger.warning("=" * 80)
                    return final_text, False, []

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

                # CRITICAL: Never lose tables that existed before auto-fix
                def _count_md_tables(text: str) -> int:
                    count = 0
                    lines = (text or "").splitlines()
                    sep_pat = re.compile(r'^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$')
                    for i in range(len(lines) - 1):
                        h = lines[i].strip()
                        s = lines[i + 1].strip()
                        if '|' in h and h.count('|') >= 2 and sep_pat.match(s):
                            count += 1
                    return count

                tables_before = _count_md_tables(final_text)
                tables_after = _count_md_tables(fixed_content)
                if tables_before > 0 and tables_after == 0:
                    logger.warning("=" * 80)
                    logger.warning(f"⚠️ AUTO-FIX REMOVEU TODAS AS TABELAS ({tables_before} → 0), REVERTENDO")
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
        with self._vomo_lock:
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
                VomoMLX = _load_vomo_class()  # import tardio resiliente
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

    async def _get_vomo_with_progress(
        self,
        *,
        emit: Callable[[str, int, str], Awaitable[None]],
        model_selection: Optional[str],
        thinking_level: Optional[str],
        ready_message: str,
    ):
        """
        Inicializa VomoMLX sem bloquear o loop de eventos:
        - roda _get_vomo em thread
        - emite heartbeat de progresso enquanto inicializa
        - aplica timeout defensivo para evitar "travamento eterno" em 0%
        """
        try:
            timeout_seconds = int(os.getenv("IUDEX_VOMO_INIT_TIMEOUT_SECONDS", "240"))
        except Exception:
            timeout_seconds = 240

        heartbeat_task: Optional[asyncio.Task] = None
        start_time = time.time()

        async def _heartbeat():
            while True:
                await asyncio.sleep(6)
                elapsed = int(time.time() - start_time)
                # Mantém visualmente "em inicialização" sem avançar de etapa.
                await emit("initializing", 1, f"⏳ Inicializando motor... ({elapsed}s)")

        try:
            heartbeat_task = asyncio.create_task(_heartbeat())
            vomo = await asyncio.wait_for(
                asyncio.to_thread(
                    self._get_vomo,
                    model_selection,
                    thinking_level,
                ),
                timeout=timeout_seconds,
            )
            await emit("initializing", 2, ready_message)
            return vomo
        except asyncio.TimeoutError as e:
            raise RuntimeError(
                f"Timeout ao inicializar VomoMLX após {timeout_seconds}s. "
                "Verifique credenciais/modelo e conectividade."
            ) from e
        finally:
            if heartbeat_task:
                heartbeat_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await heartbeat_task

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

    def _get_audio_duration_seconds(self, audio_path: str) -> float:
        """
        Retorna duração em segundos para WAV/MP3/M4A/etc (best effort).
        Usa wave para WAV e ffprobe para demais formatos.
        """
        if not audio_path:
            return 0.0

        if audio_path.lower().endswith(".wav"):
            return self._get_wav_duration_seconds(audio_path)

        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    audio_path,
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode == 0:
                value = (result.stdout or "").strip()
                if value:
                    duration = float(value)
                    if duration > 0:
                        return duration
        except Exception:
            pass

        return 0.0

    def _extract_audit_report(self, content: str) -> Optional[str]:
        if not content:
            return None
        matches = re.findall(r'<!--\s*RELATÓRIO:([\s\S]*?)-->', content, re.IGNORECASE)
        if not matches:
            return None
        return matches[-1].strip()

    # ================================================================
    # Benchmark: Local Whisper vs AssemblyAI Universal-2
    # ================================================================

    def _is_benchmark_enabled(self) -> bool:
        try:
            from app.core.config import settings
            return bool(settings.BENCHMARK_ASSEMBLYAI and settings.ASSEMBLYAI_API_KEY)
        except Exception:
            return bool(
                os.getenv("BENCHMARK_ASSEMBLYAI", "").strip().lower() in ("1", "true", "yes")
                and os.getenv("ASSEMBLYAI_API_KEY")
            )

    def _get_assemblyai_key(self) -> Optional[str]:
        try:
            from app.core.config import settings
            return settings.ASSEMBLYAI_API_KEY
        except Exception:
            return os.getenv("ASSEMBLYAI_API_KEY")

    def _is_assemblyai_primary_forced(self) -> bool:
        """Verifica se AssemblyAI deve ser forçado como primário (mesmo para APOSTILA/FIDELIDADE)."""
        try:
            from app.core.config import settings
            return bool(settings.ASSEMBLYAI_PRIMARY and settings.ASSEMBLYAI_API_KEY)
        except Exception:
            return bool(
                os.getenv("ASSEMBLYAI_PRIMARY", "").strip().lower() in ("1", "true", "yes")
                and os.getenv("ASSEMBLYAI_API_KEY")
            )

    def _allow_assemblyai_fallback_for_whisper(self) -> bool:
        """
        Controla fallback Whisper -> AssemblyAI quando o usuário escolhe Whisper explicitamente.
        Padrão: desabilitado (respeita escolha explícita de engine).
        """
        try:
            from app.core.config import settings
            return bool(getattr(settings, "ALLOW_ASSEMBLYAI_FALLBACK_FOR_WHISPER", False))
        except Exception:
            return os.getenv(
                "IUDEX_ALLOW_ASSEMBLYAI_FALLBACK_FOR_WHISPER",
                "false",
            ).strip().lower() in ("1", "true", "yes", "on")

    def _is_runpod_configured(self) -> bool:
        """Verifica se RunPod Serverless está configurado."""
        return bool(os.getenv("RUNPOD_API_KEY") and os.getenv("RUNPOD_ENDPOINT_ID"))

    def _resolve_runpod_base_url(self) -> Tuple[str, str]:
        """
        Resolve base URL para servir áudio ao RunPod.

        Precedência:
        1) IUDEX_RUNPOD_PUBLIC_BASE_URL (recomendado para túnel/deploy)
        2) IUDEX_PUBLIC_BASE_URL (alias legado)
        3) IUDEX_BASE_URL
        4) http://localhost:8000 (fallback local)
        """
        for env_key in ("IUDEX_RUNPOD_PUBLIC_BASE_URL", "IUDEX_PUBLIC_BASE_URL", "IUDEX_BASE_URL"):
            raw_value = os.getenv(env_key, "")
            value = raw_value.strip().rstrip("/")
            if value:
                return value, env_key
        return "http://localhost:8000", "default"

    def _is_private_or_loopback_host(self, hostname: str) -> bool:
        host = (hostname or "").strip().lower()
        if not host:
            return True
        if host in {"localhost", "0.0.0.0", "::1"} or host.endswith(".local"):
            return True
        try:
            ip = ipaddress.ip_address(host)
            return bool(
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
                or ip.is_unspecified
            )
        except ValueError:
            # Hostname público (DNS)
            return False

    def _validate_runpod_base_url(self, base_url: str) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise RuntimeError(
                f"Base URL inválida para RunPod: '{base_url}'. "
                "Use IUDEX_RUNPOD_PUBLIC_BASE_URL com URL absoluta (https://...)."
            )

        allow_private = os.getenv(
            "IUDEX_ALLOW_PRIVATE_BASE_URL_FOR_RUNPOD",
            "false",
        ).strip().lower() in {"1", "true", "yes", "on"}
        host = parsed.hostname or ""

        if not allow_private and self._is_private_or_loopback_host(host):
            raise RuntimeError(
                "RunPod não consegue acessar IUDEX_BASE_URL privada/local "
                f"('{base_url}'). Configure IUDEX_RUNPOD_PUBLIC_BASE_URL com uma URL pública "
                "(ex.: túnel cloudflared/ngrok ou domínio do deploy). "
                "Para forçar host privado, defina IUDEX_ALLOW_PRIVATE_BASE_URL_FOR_RUNPOD=true."
            )

    def _extract_transcription_job_id_from_audio_path(self, audio_path: str) -> str:
        """
        Extrai job_id a partir do caminho do áudio.

        Compatível com estruturas:
        - .../transcription_jobs/{job_id}/input/arquivo.ext
        - .../jobs/{job_id}/input/arquivo.ext
        Também tolera caminhos com separador '\\\\' (Windows).
        """
        normalized = f"/{(audio_path or '').replace(chr(92), '/')}".replace("//", "/")

        match = re.search(r"/(?:transcription_jobs|jobs)/([^/]+)/", normalized)
        if match:
            return match.group(1)

        # Fallback defensivo por componentes de path
        parts = [p for p in Path(audio_path).parts if p]
        for marker in ("transcription_jobs", "jobs"):
            if marker in parts:
                idx = parts.index(marker)
                if idx + 1 < len(parts):
                    return parts[idx + 1]

        raise RuntimeError(
            "Não foi possível extrair job_id de: "
            f"{audio_path}. Esperado conter '/transcription_jobs/{{job_id}}/' ou '/jobs/{{job_id}}/'."
        )

    async def _transcribe_runpod(
        self,
        file_path: str,
        audio_path: str,
        language: str = "pt",
        diarization: bool = True,
        emit: Optional[Callable] = None,
        start_progress: int = 25,
        end_progress: int = 60,
    ) -> Optional[dict]:
        """
        Transcreve via RunPod Serverless.

        1. Gera URL temporária para o áudio
        2. Submete job ao RunPod
        3. Poll com progresso até completar
        """
        from app.services.runpod_transcription import get_runpod_client, extract_transcription
        from app.api.endpoints.transcription import generate_runpod_audio_url

        client = get_runpod_client()
        if not client.is_configured:
            raise RuntimeError("RunPod não configurado (RUNPOD_API_KEY / RUNPOD_ENDPOINT_ID)")

        # Gerar URL pública temporária para o áudio
        base_url, base_url_source = self._resolve_runpod_base_url()
        self._validate_runpod_base_url(base_url)
        job_id = self._extract_transcription_job_id_from_audio_path(audio_path)

        audio_url = generate_runpod_audio_url(job_id, base_url)
        logger.info("RunPod base URL (%s): %s", base_url_source, base_url)
        logger.info("RunPod audio URL: %s", audio_url.split("?")[0])
        await asyncio.to_thread(self._preflight_runpod_audio_url, audio_url)

        if emit:
            await emit("transcription", start_progress, "Submetendo job ao RunPod...")

        # Submeter transcrição ao worker oficial faster-whisper (modelo turbo)
        result = await client.submit_job(
            audio_url=audio_url,
            language=language,
            diarization=diarization,
        )

        if emit:
            await emit("transcription", start_progress + 5, f"Job RunPod: {result.run_id}")

        # Poll com progresso
        async def _on_runpod_progress(stage: str, pct: int, msg: str):
            if emit:
                # Mapear 0-100 do RunPod para start_progress-end_progress
                mapped = start_progress + int((end_progress - start_progress) * pct / 100)
                await emit(stage, mapped, msg)

        final = await client.poll_until_complete(
            run_id=result.run_id,
            on_progress=_on_runpod_progress,
        )

        if final.status == "COMPLETED":
            parsed = extract_transcription(final)
            if not parsed or not str(parsed.get("text", "")).strip():
                raise RuntimeError(
                    "RunPod retornou resultado vazio "
                    f"({self._summarize_runpod_output(final.output)})"
                )
            # Apply post-processing (legal dictionary, punctuation, acronyms)
            try:
                from app.services.transcription_postprocessing import postprocess_transcription
                parsed = postprocess_transcription(parsed)
            except Exception as pp_exc:
                logger.warning("Post-processing failed (non-fatal): %s", pp_exc)
            return parsed
        elif final.status == "FAILED":
            raise RuntimeError(f"RunPod job falhou: {self._format_runpod_error(final.error)}")
        elif final.status == "CANCELLED":
            raise asyncio.CancelledError("RunPod job cancelado")
        else:
            raise RuntimeError(f"RunPod status inesperado: {final.status}")

    async def _diarize_via_runpod(
        self,
        audio_path: str,
        segments: list,
        emit: Optional[Callable] = None,
        speakers_expected: Optional[int] = None,
    ) -> list:
        """
        Diarização externa via RunPod diarize endpoint.
        Recebe segmentos do Whisper local e retorna segmentos com speaker labels.
        """
        from app.services.runpod_transcription import get_runpod_client, _merge_diarization
        from app.api.endpoints.transcription import generate_runpod_audio_url

        client = get_runpod_client()
        if not client.diarize_configured:
            raise RuntimeError("RunPod diarize não configurado (RUNPOD_DIARIZE_ENDPOINT_ID)")

        base_url, base_url_source = self._resolve_runpod_base_url()
        self._validate_runpod_base_url(base_url)
        job_id = self._extract_transcription_job_id_from_audio_path(audio_path)
        audio_url = generate_runpod_audio_url(job_id, base_url)

        logger.info("RunPod diarize URL (%s): %s", base_url_source, audio_url.split("?")[0])
        await asyncio.to_thread(self._preflight_runpod_audio_url, audio_url)

        if emit:
            await emit("diarization", 60, "🗣️ Enviando para diarização RunPod...")

        dia_result = await client.submit_diarize_job(
            audio_url=audio_url,
            min_speakers=1,
            max_speakers=speakers_expected or 10,
        )
        if emit:
            await emit("diarization", 62, f"🗣️ Job diarização: {dia_result.run_id}")

        dia_final = await client.poll_until_complete(
            run_id=dia_result.run_id,
            endpoint_id=client.diarize_endpoint_id,
        )

        if dia_final.status == "COMPLETED" and dia_final.output:
            diarization_data = dia_final.output.get("diarization") or dia_final.output
            merged = _merge_diarization(segments, diarization_data)
            if emit:
                num_speakers = diarization_data.get("num_speakers", "?")
                await emit("diarization", 65, f"🗣️ Diarização concluída ({num_speakers} falantes)")
            return merged
        else:
            logger.warning("RunPod diarize falhou: %s", dia_final.error)
            raise RuntimeError(f"RunPod diarize falhou: {dia_final.error or dia_final.status}")

    def _preflight_runpod_audio_url(self, audio_url: str) -> None:
        """
        Valida rapidamente se a URL pública assinada do áudio está acessível
        antes de submeter o job ao RunPod.
        """
        parsed = urlparse(audio_url)
        hostname = (parsed.hostname or "").strip().lower()
        is_cloudflare_tunnel = hostname.endswith(".trycloudflare.com")
        env_name = (
            os.getenv("IUDEX_ENV")
            or os.getenv("ENVIRONMENT")
            or os.getenv("APP_ENV")
            or ""
        ).strip().lower()
        is_production = env_name in {"prod", "production"}
        local_preflight_flag = os.getenv("IUDEX_RUNPOD_PREFLIGHT_LOCAL", "auto").strip().lower()
        if local_preflight_flag in {"1", "true", "yes", "on"}:
            do_local_preflight = True
        elif local_preflight_flag in {"0", "false", "no", "off"}:
            do_local_preflight = False
        else:
            # Default: mantém diagnóstico forte em dev/túneis efêmeros, reduzindo latência em produção.
            do_local_preflight = is_cloudflare_tunnel or not is_production

        req = urllib.request.Request(
            audio_url,
            method="GET",
            headers={
                "Range": "bytes=0-1",
                "User-Agent": "Iudex-RunPod-Preflight/1.0",
            },
        )

        # 1) Pré-validação local: separa erros de token/arquivo de erros de túnel público.
        if do_local_preflight:
            local_port = (os.getenv("IUDEX_API_PORT") or os.getenv("PORT") or "8000").strip()
            local_url = f"http://127.0.0.1:{local_port}{parsed.path}"
            if parsed.query:
                local_url = f"{local_url}?{parsed.query}"
            local_req = urllib.request.Request(
                local_url,
                method="GET",
                headers={
                    "Range": "bytes=0-1",
                    "User-Agent": "Iudex-RunPod-Preflight-Local/1.0",
                },
            )
            try:
                with urllib.request.urlopen(local_req, timeout=10) as local_response:
                    local_status = getattr(local_response, "status", 200)
                    if local_status not in (200, 206):
                        raise RuntimeError(
                            f"Pré-validação local falhou (HTTP {local_status}). "
                            "Verifique assinatura do token e existência do áudio do job."
                        )
            except urllib.error.HTTPError as local_exc:
                if local_exc.code == 403:
                    raise RuntimeError(
                        "Pré-validação local rejeitou o token de áudio (HTTP 403). "
                        "Verifique assinatura/SECRET_KEY e validade do token."
                    ) from local_exc
                if local_exc.code == 404:
                    raise RuntimeError(
                        "Pré-validação local não encontrou o áudio do job (HTTP 404). "
                        "Verifique job_id e arquivo de entrada."
                    ) from local_exc
                raise RuntimeError(
                    f"Pré-validação local do áudio rejeitada (HTTP {local_exc.code}). "
                    "Verifique assinatura do token e disponibilidade da API local."
                ) from local_exc
            except urllib.error.URLError as local_exc:
                raise RuntimeError(
                    f"Pré-validação local do áudio inacessível: {local_exc.reason}. "
                    "Verifique se a API está rodando em 127.0.0.1."
                ) from local_exc
            except (TimeoutError, socket.timeout) as local_exc:
                raise RuntimeError(
                    "Pré-validação local do áudio expirou por timeout. "
                    "Verifique se a API local está responsiva."
                ) from local_exc

        # 2) Validação pública: garante acesso externo (RunPod).
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                status = getattr(response, "status", 200)
                if status not in (200, 206):
                    raise RuntimeError(
                        f"URL pública do áudio retornou HTTP {status}. "
                        "Verifique tunnel/base URL e assinatura do token."
                    )
        except urllib.error.HTTPError as exc:
            if is_cloudflare_tunnel and exc.code in {502, 521, 522, 523, 524, 530}:
                raise RuntimeError(
                    f"URL pública do áudio rejeitada (HTTP {exc.code}). "
                    "Assinatura/token local estão OK, mas o tunnel Cloudflare está offline/expirado. "
                    "Reinicie o tunnel e atualize IUDEX_RUNPOD_PUBLIC_BASE_URL."
                ) from exc
            raise RuntimeError(
                f"URL pública do áudio rejeitada (HTTP {exc.code}). "
                "Verifique tunnel/base URL e assinatura do token."
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"URL pública do áudio inacessível: {exc.reason}. "
                "Verifique se o tunnel está ativo e apontando para a API."
            ) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise RuntimeError(
                "URL pública do áudio expirou por timeout. "
                "Verifique se o tunnel/base URL está ativo e saudável."
            ) from exc

    def _summarize_runpod_output(self, output: Any) -> str:
        """Resumo curto do payload de saída do RunPod para diagnóstico."""
        if output is None:
            return "output=None"
        if isinstance(output, dict):
            keys = sorted(str(k) for k in output.keys())
            return f"dict keys={keys[:12]}"
        if isinstance(output, list):
            return f"list len={len(output)}"
        if isinstance(output, str):
            snippet = output.strip().replace("\n", " ")
            if len(snippet) > 120:
                snippet = snippet[:120] + "..."
            return f"str='{snippet}'"
        return f"type={type(output).__name__}"

    def _format_runpod_error(self, error: Any) -> str:
        """Normaliza erro do RunPod em mensagem acionável."""
        if error is None:
            return "sem detalhes"

        payload: Any = error
        if isinstance(error, str):
            stripped = error.strip()
            if not stripped:
                return "sem detalhes"
            try:
                payload = json.loads(stripped)
            except Exception:
                return stripped

        if isinstance(payload, dict):
            msg = str(payload.get("error_message") or payload.get("message") or payload.get("error") or "")
            tb = str(payload.get("error_traceback") or "")
            combined = f"{msg}\n{tb}".lower()
            if (
                "no such file or directory: 'none'" in combined
                or ("filenotfounderror" in combined and "none" in combined)
            ):
                return (
                    "worker RunPod recebeu áudio inválido/ausente (input None). "
                    "Verifique o handler do endpoint e a URL pública do áudio."
                )
            return json.dumps(payload, ensure_ascii=False)

        return str(payload)

    def _is_provider_fallback_allowed(
        self,
        *,
        requested_engine: Optional[str],
        from_provider: str,
        to_provider: str,
        allow_provider_fallback: Optional[bool],
    ) -> bool:
        """
        Regra central para decidir se troca automática de provider é permitida.

        Precedência:
        1) Flag explícita da requisição (`allow_provider_fallback`)
        2) Regra legado de Whisper -> AssemblyAI (env)
        3) Se o usuário escolheu engine explícita, NÃO fazer fallback
        4) Fallback permitido apenas quando nenhuma engine foi solicitada
        """
        if allow_provider_fallback is not None:
            return bool(allow_provider_fallback)

        requested = (requested_engine or "").strip().lower()
        if requested == "whisper" and from_provider == "whisper" and to_provider == "assemblyai":
            return self._allow_assemblyai_fallback_for_whisper()

        # Se o usuário escolheu uma engine específica, respeitar a escolha
        if requested and requested == from_provider:
            return False

        return True

    def _enforce_fidelity_critical_fallback(
        self,
        *,
        mode: Optional[str],
        allow_provider_fallback: Optional[bool],
    ) -> Optional[bool]:
        """
        Em modo FIDELIDADE, prioriza consistência de engine:
        fallback automático fica desabilitado por padrão.
        """
        mode_upper = (mode or "").strip().upper()
        if mode_upper != "FIDELIDADE":
            return allow_provider_fallback

        force_disable = os.getenv(
            "IUDEX_DISABLE_FALLBACK_IN_FIDELIDADE",
            "true",
        ).strip().lower() in ("1", "true", "yes", "on")

        if force_disable:
            if allow_provider_fallback is not False:
                logger.info(
                    "🔒 Modo FIDELIDADE: fallback de provider forçado para OFF "
                    "(IUDEX_DISABLE_FALLBACK_IN_FIDELIDADE=true)."
                )
            return False

        return allow_provider_fallback

    def _provider_switch_message(
        self,
        *,
        from_provider: str,
        to_provider: str,
        allow_provider_fallback: Optional[bool],
    ) -> str:
        provider_labels = {
            "whisper": "Whisper",
            "assemblyai": "AssemblyAI",
            "elevenlabs": "ElevenLabs",
            "runpod": "RunPod",
        }
        source = provider_labels.get(from_provider, from_provider)
        target = provider_labels.get(to_provider, to_provider)
        basis = "consentido na UI" if allow_provider_fallback is True else "fallback automático"
        return f"⚠️ {source} indisponível, trocando para {target} ({basis})."

    def _normalize_diarization_provider(self, diarization_provider: Optional[str]) -> str:
        provider = (diarization_provider or "auto").strip().lower()
        if provider in {"auto", "local", "runpod", "assemblyai"}:
            return provider
        if provider:
            logger.warning("Provider de diarização inválido '%s' (usando auto).", provider)
        return "auto"

    async def _apply_external_diarization_if_needed(
        self,
        *,
        transcription_result: Dict[str, Any],
        diarization_enabled: bool,
        diarization_required: bool,
        diarization_provider: Optional[str],
        audio_path: str,
        speakers_expected: Optional[int] = None,
        speaker_roles: Optional[list] = None,
        language: Optional[str] = None,
        mode: Optional[str] = None,
        speaker_id_type: Optional[str] = None,
        speaker_id_values: Optional[list] = None,
        emit: Optional[Callable[[str, int, str], Awaitable[None]]] = None,
    ) -> Tuple[list, list]:
        """
        Aplica diarização externa quando Whisper sinaliza ausência de pyannote local.
        Respeita o provider solicitado pelo usuário: auto/local/runpod/assemblyai.
        """
        words = transcription_result.get("words", []) if isinstance(transcription_result, dict) else []
        segments = transcription_result.get("segments", []) if isinstance(transcription_result, dict) else []
        needs_external = bool(
            isinstance(transcription_result, dict)
            and transcription_result.get("_needs_external_diarization")
        )
        if not diarization_enabled or not needs_external:
            return words, segments

        provider = self._normalize_diarization_provider(diarization_provider)
        errors: list[str] = []

        if provider == "local":
            raise RuntimeError(
                "Diarização via Local (pyannote) foi solicitada, mas pyannote não está disponível. "
                "Instale pyannote.audio localmente ou selecione RunPod/AssemblyAI."
            )

        # 1) RunPod (quando auto ou explicitamente runpod)
        if provider in {"auto", "runpod"}:
            from app.services.runpod_transcription import get_runpod_client

            runpod_client = get_runpod_client()
            if runpod_client.diarize_configured:
                try:
                    merged = await self._diarize_via_runpod(
                        audio_path=audio_path,
                        segments=segments,
                        emit=emit,
                        speakers_expected=speakers_expected,
                    )
                    return words, merged
                except Exception as dia_exc:
                    logger.warning("RunPod diarize falhou: %s", dia_exc)
                    errors.append(f"RunPod: {dia_exc}")
            else:
                errors.append("RunPod diarize não configurado (RUNPOD_DIARIZE_ENDPOINT_ID)")

            if provider == "runpod":
                raise RuntimeError(
                    "Diarização via RunPod foi solicitada, mas está indisponível. "
                    + "; ".join(errors)
                )

        # 2) AssemblyAI (quando auto ou explicitamente assemblyai)
        if provider in {"auto", "assemblyai"}:
            if self._get_assemblyai_key():
                try:
                    if emit:
                        await emit("diarization", 60, "🗣️ Diarização via AssemblyAI...")
                        aai_result = await self._transcribe_assemblyai_with_progress(
                            audio_path=audio_path,
                            emit=emit,
                            speaker_roles=speaker_roles,
                            language=language or "pt",
                            speakers_expected=speakers_expected,
                            mode=mode,
                            start_progress=60,
                            end_progress=65,
                            speaker_id_type=speaker_id_type,
                            speaker_id_values=speaker_id_values,
                        )
                    else:
                        aai_result = await asyncio.to_thread(
                            self._transcribe_assemblyai_with_roles,
                            audio_path,
                            speaker_roles,
                            language or "pt",
                            speakers_expected,
                            mode,
                            None,
                            None,
                            None,
                            speaker_id_type,
                            speaker_id_values,
                        )
                    if aai_result:
                        if emit:
                            await emit("diarization", 65, "🗣️ Diarização AssemblyAI concluída ✓")
                        return (
                            aai_result.get("words", words) or words,
                            aai_result.get("segments", segments) or segments,
                        )
                    errors.append("AssemblyAI retornou resultado vazio")
                except Exception as aai_exc:
                    logger.warning("AssemblyAI diarize falhou: %s", aai_exc)
                    errors.append(f"AssemblyAI: {aai_exc}")
            else:
                errors.append("ASSEMBLYAI_API_KEY não configurada")

            if provider == "assemblyai":
                raise RuntimeError(
                    "Diarização via AssemblyAI foi solicitada, mas está indisponível. "
                    + "; ".join(errors)
                )

        if diarization_required:
            detail = "; ".join(errors) if errors else "nenhum provider externo disponível"
            raise RuntimeError(
                "Diarização obrigatória, mas indisponível. "
                f"Detalhes: {detail}. "
                "Instale pyannote.audio localmente ou configure RunPod/AssemblyAI."
            )

        if errors:
            logger.warning("Diarização externa não aplicada (modo soft): %s", "; ".join(errors))
        return words, segments

    def _extract_audio_for_cloud(
        self,
        file_path: str,
        target_format: str = "mp3",
        bitrate: str = "64k",
        sample_rate: int = 16000,
    ) -> str:
        """
        Extrai áudio otimizado para upload em serviços de nuvem (AssemblyAI, ElevenLabs).

        Diferente de vomo.optimize_audio() que gera WAV para Whisper local,
        esta função gera MP3 compacto para upload mais rápido.

        Comparação de tamanho para 6h de áudio:
        - WAV 16kHz mono: ~690MB
        - MP3 64kbps mono: ~173MB (4x menor)
        - MP3 128kbps mono: ~345MB (2x menor)

        Args:
            file_path: Caminho do arquivo de vídeo/áudio
            target_format: Formato de saída (mp3, m4a)
            bitrate: Taxa de bits (64k, 128k)
            sample_rate: Taxa de amostragem (16000 para transcrição)

        Returns:
            Caminho do arquivo de áudio extraído
        """
        import subprocess
        from pathlib import Path

        file_name = Path(file_path).stem
        file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
        cache_key = f"{file_name}_{file_size}_{target_format}_{bitrate}"
        file_hash = hashlib.md5(cache_key.encode()).hexdigest()[:8]
        output_path = f"temp_cloud_{file_hash}.{target_format}"

        # Usar cache se existir
        if os.path.exists(output_path):
            logger.info(f"♻️ Cache de áudio cloud encontrado: {output_path}")
            return output_path

        logger.info(f"🔄 Extraindo áudio para cloud ({target_format} {bitrate})...")

        # Determinar codec baseado no formato
        codec = "libmp3lame" if target_format == "mp3" else "aac"

        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-i", file_path,
            "-vn",  # Sem vídeo
            "-sn",  # Sem legendas
            "-dn",  # Sem data streams
            "-map", "0:a:0?",
            "-ac", "1",  # Mono
            "-ar", str(sample_rate),
            "-c:a", codec,
            "-b:a", bitrate,
            output_path,
            "-hide_banner",
            "-loglevel", "error",
        ]

        try:
            subprocess.run(ffmpeg_cmd, check=True, capture_output=True)
            output_size_mb = os.path.getsize(output_path) / (1024 * 1024)
            input_size_mb = file_size / (1024 * 1024)
            logger.info(f"✅ Áudio extraído: {output_size_mb:.1f}MB (original: {input_size_mb:.1f}MB)")
            return output_path
        except subprocess.CalledProcessError as e:
            logger.error(f"Erro ao extrair áudio: {e.stderr.decode() if e.stderr else e}")
            raise

    def _should_extract_audio_for_cloud(self, file_path: str) -> bool:
        """
        Decide se deve extrair áudio ou enviar arquivo original para cloud.

        Regras:
        - Arquivos > 2GB: DEVE extrair (limite upload AssemblyAI = 2.2GB)
        - Vídeos: extrair economiza bandwidth (vídeo não é usado)
        - Áudios < 500MB: pode enviar direto
        - Áudios 500MB-2GB: extrair se for WAV/FLAC (grandes)
        """
        import mimetypes

        file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
        file_size_mb = file_size / (1024 * 1024)
        ext = Path(file_path).suffix.lower()
        mime_type, _ = mimetypes.guess_type(file_path)

        is_video = mime_type and mime_type.startswith("video") or ext in (".mp4", ".mov", ".avi", ".mkv", ".webm")
        is_lossless = ext in (".wav", ".flac", ".aiff")

        # Arquivo muito grande - DEVE extrair
        if file_size_mb > 2000:  # > 2GB
            logger.info(f"📦 Arquivo > 2GB ({file_size_mb:.0f}MB) - extração obrigatória")
            return True

        # Vídeo - extrair economiza bandwidth
        if is_video:
            logger.info(f"🎬 Vídeo detectado ({file_size_mb:.0f}MB) - extraindo áudio")
            return True

        # Áudio lossless grande - extrair para economizar
        if is_lossless and file_size_mb > 100:
            logger.info(f"🎵 Áudio lossless > 100MB ({file_size_mb:.0f}MB) - extraindo compactado")
            return True

        # Áudio já compactado e pequeno - enviar direto
        logger.info(f"🎵 Áudio compacto ({file_size_mb:.0f}MB) - enviando direto")
        return False

    def _start_assemblyai_benchmark(
        self,
        audio_path: str,
        language: Optional[str] = None,
        area: Optional[str] = None,
        custom_keyterms: Optional[list] = None,
    ) -> concurrent.futures.Future:
        """Dispara transcrição AssemblyAI em thread separada (não bloqueia)."""
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="benchmark-aai")
        future = executor.submit(
            self._run_assemblyai_transcription,
            audio_path,
            language,
            area,
            custom_keyterms,
        )
        executor.shutdown(wait=False)
        return future

    def _upload_file_with_progress(
        self,
        url: str,
        file_path: str,
        headers: dict,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        chunk_size: int = 1024 * 1024,  # 1MB chunks
        max_retries: int = 3,
    ) -> Optional[dict]:
        """
        Upload arquivo com callback de progresso e retry automático.

        Args:
            url: URL de upload
            file_path: Caminho do arquivo
            headers: Headers da requisição
            progress_callback: Callback(bytes_sent, total_bytes) chamado a cada chunk
            chunk_size: Tamanho do chunk em bytes (default 1MB)
            max_retries: Número máximo de tentativas (default 3)

        Returns:
            Response JSON ou None em caso de erro
        """
        import requests as http_requests
        import time as time_module

        file_size = os.path.getsize(file_path)
        last_error = None

        for attempt in range(max_retries):
            bytes_sent = 0

            def file_reader():
                nonlocal bytes_sent
                with open(file_path, "rb") as f:
                    while True:
                        chunk = f.read(chunk_size)
                        if not chunk:
                            break
                        bytes_sent += len(chunk)
                        if progress_callback:
                            try:
                                progress_callback(bytes_sent, file_size)
                            except Exception:
                                pass
                        yield chunk

            try:
                # Usar streaming upload com generator
                # Timeout: 60s connect (mais tolerante), 30min read
                resp = http_requests.post(
                    url,
                    headers=headers,
                    data=file_reader(),
                    timeout=(60, 1800),
                )
                if resp.status_code == 200:
                    return resp.json()
                else:
                    last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    logger.warning(f"Upload failed (attempt {attempt + 1}/{max_retries}): {last_error}")
            except http_requests.exceptions.Timeout as e:
                last_error = f"Timeout: {e}"
                logger.warning(f"Upload timeout (attempt {attempt + 1}/{max_retries}): {file_size / (1024*1024):.1f}MB")
            except http_requests.exceptions.ConnectionError as e:
                last_error = f"Connection error: {e}"
                logger.warning(f"Upload connection error (attempt {attempt + 1}/{max_retries}): {e}")
            except http_requests.exceptions.RequestException as e:
                last_error = f"Request error: {e}"
                logger.warning(f"Upload error (attempt {attempt + 1}/{max_retries}): {e}")

            # Retry com backoff exponencial + jitter: 2-3s, 4-6s, 8-12s
            if attempt < max_retries - 1:
                import random
                base_wait = 2 ** (attempt + 1)
                jitter = random.uniform(0, base_wait * 0.5)  # até 50% de jitter
                wait_time = base_wait + jitter
                logger.info(f"⏳ Aguardando {wait_time:.1f}s antes de retry (tentativa {attempt + 2}/{max_retries})...")
                time_module.sleep(wait_time)

        logger.error(f"Upload falhou após {max_retries} tentativas: {last_error}")
        return None

    async def _transcribe_assemblyai_with_progress(
        self,
        audio_path: str,
        emit: Callable[[str, int, str], Awaitable[None]],
        speaker_roles: Optional[list] = None,
        language: str = "pt",
        speakers_expected: Optional[int] = None,
        mode: Optional[str] = None,
        context: Optional[str] = None,
        start_progress: int = 25,
        end_progress: int = 60,
        area: Optional[str] = None,
        custom_keyterms: Optional[list] = None,
        speaker_id_type: Optional[str] = None,
        speaker_id_values: Optional[list] = None,
    ) -> Optional[dict]:
        """
        Transcreve via AssemblyAI com progresso real via SSE.

        O progresso é dividido em:
        - Upload: start_progress → start_progress + 40% do range
        - Polling: resto do range até end_progress
        """
        import requests as http_requests
        import queue

        api_key = self._get_assemblyai_key()
        if not api_key:
            return None

        base_url = "https://api.assemblyai.com"
        headers = {"authorization": api_key, "content-type": "application/json"}

        # Calcular ranges de progresso
        progress_range = end_progress - start_progress
        upload_end = start_progress + int(progress_range * 0.4)  # Upload = 40% do range
        poll_start = upload_end
        poll_end = end_progress

        # === Cache AAI: Calcular config hash para verificação ===
        config_hash = self._get_aai_config_hash(
            language=language,
            speaker_labels=bool(speaker_roles) or True,
            speakers_expected=speakers_expected,
            mode=mode,
        )

        # === Cache AAI: Verificar se existe transcrição em cache ===
        cached = await self._check_aai_cache(audio_path, config_hash)
        if cached:
            if cached.get("status") == "completed":
                # Transcrição já existe! Extrair e retornar resultado
                await emit("transcription", end_progress, "✅ Usando transcrição em cache (AssemblyAI)")
                aai_response = cached.get("response", {})
                return self._extract_aai_result_from_response(
                    aai_response,
                    cached.get("transcript_id"),
                    speaker_roles,
                    mode,
                    time.time(),  # start_time placeholder
                )
            elif cached.get("status") == "processing":
                # Retomar polling de transcrição existente
                transcript_id = cached.get("transcript_id")
                await emit("transcription", poll_start, f"🔄 Retomando transcrição AAI existente: {transcript_id[:8]}...")
                logger.info(f"🔄 Retomando polling de transcrição AAI: {transcript_id}")
                # Pular upload e ir direto para polling
                poll_url = f"{base_url}/v2/transcript/{transcript_id}"
                poll_start_time = time.time()
                return await self._poll_aai_transcript(
                    poll_url=poll_url,
                    headers=headers,
                    transcript_id=transcript_id,
                    emit=emit,
                    speaker_roles=speaker_roles,
                    mode=mode,
                    poll_start=poll_start,
                    poll_end=poll_end,
                    poll_start_time=poll_start_time,
                    audio_path=audio_path,
                    config_hash=config_hash,
                )

        # 1. Upload com progresso real
        file_size = os.path.getsize(audio_path)
        file_size_mb = file_size / (1024 * 1024)
        start_time = time.time()

        await emit("transcription", start_progress, f"📤 Enviando para AssemblyAI (0/{file_size_mb:.0f}MB)...")

        # Queue para comunicar progresso entre thread e async
        progress_queue: queue.Queue = queue.Queue()
        last_progress_pct = 0

        def on_upload_progress(bytes_sent: int, total_bytes: int):
            nonlocal last_progress_pct
            pct = int((bytes_sent / total_bytes) * 100)
            # Só enfileira a cada 5% para não sobrecarregar
            if pct >= last_progress_pct + 5 or pct == 100:
                last_progress_pct = pct
                progress_queue.put((bytes_sent, total_bytes))

        # Rodar upload em thread separada
        upload_result = None
        upload_error = None

        def do_upload():
            nonlocal upload_result, upload_error
            try:
                upload_result = self._upload_file_with_progress(
                    f"{base_url}/v2/upload",
                    audio_path,
                    {"authorization": api_key},
                    on_upload_progress,
                )
            except Exception as e:
                upload_error = e

        upload_thread = threading.Thread(target=do_upload)
        upload_thread.start()

        # Consumir progresso enquanto upload roda
        while upload_thread.is_alive():
            try:
                bytes_sent, total_bytes = progress_queue.get(timeout=0.5)
                mb_sent = bytes_sent / (1024 * 1024)
                mb_total = total_bytes / (1024 * 1024)
                pct = bytes_sent / total_bytes
                progress = start_progress + int(pct * (upload_end - start_progress))
                await emit("transcription", progress, f"📤 Enviando para AssemblyAI ({mb_sent:.0f}/{mb_total:.0f}MB)...")
            except queue.Empty:
                await asyncio.sleep(0.1)

        upload_thread.join()

        # Drenar fila restante
        while not progress_queue.empty():
            try:
                bytes_sent, total_bytes = progress_queue.get_nowait()
            except queue.Empty:
                break

        if upload_error:
            logger.error(f"AssemblyAI upload error: {upload_error}")
            return None

        if not upload_result or "upload_url" not in upload_result:
            logger.warning("AssemblyAI upload failed - no upload_url")
            return None

        audio_url = upload_result["upload_url"]
        upload_time = time.time() - start_time
        logger.info(f"✅ AssemblyAI upload completo em {upload_time:.1f}s ({file_size_mb:.1f}MB)")
        await emit("transcription", upload_end, f"✅ Upload completo ({upload_time:.0f}s)")

        # 2. Submeter transcrição
        aai_prompt, keyterms = self._get_assemblyai_prompt_for_mode(
            mode=mode,
            language=language,
            area=area,
            speaker_roles=speaker_roles,
            custom_keyterms=custom_keyterms,
        )
        mode_upper = (mode or "APOSTILA").upper()

        data = {
            "audio_url": audio_url,
            "speech_models": ["universal-3-pro"],
            "prompt": aai_prompt,
            "speaker_labels": True,
            "language_code": language,
        }
        if keyterms:
            data["keyterms_prompt"] = keyterms
        if speakers_expected and speakers_expected > 0:
            data["speakers_expected"] = speakers_expected

        # Speaker Identification (v2.33): Identifica falantes por nome ou papel
        if speaker_id_type and speaker_id_values:
            # Validar valores (max 35 chars cada, conforme documentação AssemblyAI)
            valid_values = [v[:35] for v in speaker_id_values if v and v.strip()]
            if valid_values:
                data["speech_understanding"] = {
                    "request": {
                        "speaker_identification": {
                            "speaker_type": speaker_id_type,
                            "known_values": valid_values
                        }
                    }
                }
                logger.info(f"🎭 Speaker Identification ativo: {speaker_id_type} = {valid_values}")

        await emit("transcription", poll_start, f"🎙️ Iniciando transcrição AssemblyAI [{mode_upper}]...")

        try:
            resp = http_requests.post(f"{base_url}/v2/transcript", headers=headers, json=data, timeout=(30, 60))
        except http_requests.exceptions.RequestException as e:
            logger.error(f"AssemblyAI transcript submit error: {e}")
            return None

        if resp.status_code != 200:
            logger.warning(f"AssemblyAI transcript submit failed: {resp.status_code}")
            return None

        transcript_id = resp.json()["id"]
        logger.info(f"📋 AssemblyAI job criado: {transcript_id}")

        # === Cache AAI: Persistir IMEDIATAMENTE após obter transcript_id ===
        self._save_aai_cache(
            file_path=audio_path,
            transcript_id=transcript_id,
            audio_url=audio_url,
            config_hash=config_hash,
            status="processing",
        )

        # 3. Polling com progresso
        poll_url = f"{base_url}/v2/transcript/{transcript_id}"
        poll_count = 0
        max_polls = 4800  # ~4 horas
        poll_timeout = (10, 30)
        poll_start_time = time.time()
        fallback_audio_duration = self._get_audio_duration_seconds(audio_path)
        try:
            unknown_duration_estimated_seconds = float(
                os.getenv("IUDEX_ASSEMBLYAI_UNKNOWN_DURATION_SECONDS", "1800")
            )
        except Exception:
            unknown_duration_estimated_seconds = 1800.0
        try:
            max_poll_minutes = float(os.getenv("IUDEX_ASSEMBLYAI_MAX_POLL_MINUTES", "240"))
        except Exception:
            max_poll_minutes = 240.0

        while poll_count < max_polls:
            try:
                poll_resp = http_requests.get(poll_url, headers=headers, timeout=poll_timeout).json()
            except http_requests.exceptions.RequestException as e:
                logger.warning(f"AssemblyAI poll error (tentativa {poll_count}): {e}")
                poll_count += 1
                await asyncio.sleep(5)
                continue

            status = poll_resp.get("status")
            poll_count += 1
            elapsed_min = (time.time() - poll_start_time) / 60

            if max_poll_minutes and max_poll_minutes > 0 and elapsed_min >= max_poll_minutes:
                logger.error(f"AssemblyAI timeout: excedeu {max_poll_minutes:.0f}min (status={status})")
                try:
                    file_hash = self._compute_file_hash(audio_path)
                    self._update_aai_cache_status(
                        file_hash,
                        status="timeout",
                        audio_duration=poll_resp.get("audio_duration", 0) or 0,
                        result_cached=False,
                    )
                except Exception:
                    pass
                return None

            # Atualizar progresso baseado no tempo (estimativa)
            # AssemblyAI geralmente processa ~10x mais rápido que tempo real
            provider_audio_duration = poll_resp.get("audio_duration") or 0
            effective_audio_duration = provider_audio_duration or fallback_audio_duration
            if effective_audio_duration and effective_audio_duration > 0:
                estimated_total = effective_audio_duration / 10  # ~10x realtime
                progress_ratio = min(0.99, elapsed_min * 60 / max(estimated_total, 60))
            else:
                progress_ratio = min(
                    0.99,
                    elapsed_min * 60 / max(unknown_duration_estimated_seconds, 300),
                )

            progress = poll_start + int(progress_ratio * (poll_end - poll_start))

            if poll_count % 10 == 0:  # Atualiza UI a cada ~30s
                # Mensagens mais claras para o usuário
                if status == "queued":
                    msg = f"⏳ Na fila do AssemblyAI... ({elapsed_min:.0f}min)"
                elif status == "processing":
                    if effective_audio_duration and effective_audio_duration > 0:
                        dur_min = effective_audio_duration / 60
                        est_remaining = max(0, (dur_min / 10) - elapsed_min)
                        msg = f"🎙️ Transcrevendo ({elapsed_min:.0f}min, ~{est_remaining:.0f}min restantes)"
                    else:
                        msg = f"🎙️ Transcrevendo... ({elapsed_min:.0f}min)"
                else:
                    msg = f"⏳ Processando... ({elapsed_min:.0f}min)"
                await emit("transcription", progress, msg)
                logger.info(f"⏳ AssemblyAI polling... status={status}, elapsed={elapsed_min:.1f}min")

            if status == "completed":
                logger.info(f"✅ AssemblyAI completou após {poll_count} polls ({elapsed_min:.1f}min)")
                break
            elif status == "error":
                logger.warning(f"AssemblyAI error: {poll_resp.get('error')}")
                return None

            await asyncio.sleep(3)
        else:
            logger.error(f"AssemblyAI timeout: max polls atingido")
            try:
                file_hash = self._compute_file_hash(audio_path)
                self._update_aai_cache_status(
                    file_hash,
                    status="timeout",
                    audio_duration=0,
                    result_cached=False,
                )
            except Exception:
                pass
            return None

        # 4. Processar resultado (igual ao método sync)
        elapsed = time.time() - start_time
        utterances = poll_resp.get("utterances", [])
        words = poll_resp.get("words", [])
        segments = []
        speaker_set = {}

        ts_interval = self._get_timestamp_interval_for_mode(mode) or 0

        if len(utterances) <= 2 and len(words) > 50 and ts_interval > 0:
            logger.info(f"📝 AssemblyAI: usando words ({len(words)}) para gerar timestamps")
            current_segment_words = []
            segment_start = None

            for word in words:
                word_start = word.get("start", 0) / 1000.0
                word_end = word.get("end", 0) / 1000.0
                word_text = word.get("text", "")
                word_speaker = word.get("speaker", "A")

                if segment_start is None:
                    segment_start = word_start

                current_segment_words.append(word_text)

                if word_end - segment_start >= ts_interval:
                    segments.append({
                        "start": segment_start,
                        "end": word_end,
                        "text": " ".join(current_segment_words),
                        "speaker_label": word_speaker,
                    })
                    if word_speaker not in speaker_set:
                        speaker_set[word_speaker] = {"label": word_speaker, "role": ""}
                    current_segment_words = []
                    segment_start = None

            if current_segment_words:
                last_word = words[-1]
                segments.append({
                    "start": segment_start or 0,
                    "end": last_word.get("end", 0) / 1000.0,
                    "text": " ".join(current_segment_words),
                    "speaker_label": last_word.get("speaker", "A"),
                })
        else:
            for utt in utterances:
                speaker_label = utt.get("speaker", "A")
                segments.append({
                    "start": utt.get("start", 0) / 1000.0,
                    "end": utt.get("end", 0) / 1000.0,
                    "text": utt.get("text", ""),
                    "speaker_label": speaker_label,
                })
                if speaker_label not in speaker_set:
                    speaker_set[speaker_label] = {"label": speaker_label, "role": ""}

        # Mapear roles
        if speaker_roles:
            sorted_speakers = sorted(speaker_set.keys())
            for i, sp in enumerate(sorted_speakers):
                if i < len(speaker_roles):
                    speaker_set[sp]["role"] = speaker_roles[i]

        audio_duration = poll_resp.get("audio_duration", 0)

        # === Cache AAI: Atualizar status para completed ===
        file_hash = self._compute_file_hash(audio_path)
        self._update_aai_cache_status(
            file_hash,
            status="completed",
            audio_duration=audio_duration,
            result_cached=True,
        )

        # Construir texto com timestamps (paridade com path sync)
        text_with_timestamps = self._build_text_with_timestamps(segments, timestamp_interval=ts_interval)

        return {
            "segments": segments,
            "speakers": speaker_set,
            "elapsed_seconds": elapsed,
            "audio_duration": audio_duration,
            "text": poll_resp.get("text", ""),
            "text_with_timestamps": text_with_timestamps,
            "words": words,
            "utterances": utterances,
            "backend": "assemblyai",
            "transcript_id": transcript_id,
            "raw_response": poll_resp,
        }

    def _extract_aai_result_from_response(
        self,
        poll_resp: Dict[str, Any],
        transcript_id: str,
        speaker_roles: Optional[list],
        mode: Optional[str],
        start_time: float,
    ) -> Dict[str, Any]:
        """
        Extrai resultado formatado de uma resposta AAI.
        Usado tanto para resultados frescos quanto para cache.
        """
        elapsed = time.time() - start_time
        utterances = poll_resp.get("utterances", [])
        words = poll_resp.get("words", [])
        segments = []
        speaker_set = {}

        ts_interval = self._get_timestamp_interval_for_mode(mode) or 0

        if len(utterances) <= 2 and len(words) > 50 and ts_interval > 0:
            logger.info(f"📝 AssemblyAI (cache): usando words ({len(words)}) para gerar timestamps")
            current_segment_words = []
            segment_start = None

            for word in words:
                word_start = word.get("start", 0) / 1000.0
                word_end = word.get("end", 0) / 1000.0
                word_text = word.get("text", "")
                word_speaker = word.get("speaker", "A")

                if segment_start is None:
                    segment_start = word_start

                current_segment_words.append(word_text)

                if word_end - segment_start >= ts_interval:
                    segments.append({
                        "start": segment_start,
                        "end": word_end,
                        "text": " ".join(current_segment_words),
                        "speaker_label": word_speaker,
                    })
                    if word_speaker not in speaker_set:
                        speaker_set[word_speaker] = {"label": word_speaker, "role": ""}
                    current_segment_words = []
                    segment_start = None

            if current_segment_words:
                last_word = words[-1]
                segments.append({
                    "start": segment_start or 0,
                    "end": last_word.get("end", 0) / 1000.0,
                    "text": " ".join(current_segment_words),
                    "speaker_label": last_word.get("speaker", "A"),
                })
        else:
            for utt in utterances:
                speaker_label = utt.get("speaker", "A")
                segments.append({
                    "start": utt.get("start", 0) / 1000.0,
                    "end": utt.get("end", 0) / 1000.0,
                    "text": utt.get("text", ""),
                    "speaker_label": speaker_label,
                })
                if speaker_label not in speaker_set:
                    speaker_set[speaker_label] = {"label": speaker_label, "role": ""}

        # Mapear roles
        if speaker_roles:
            sorted_speakers = sorted(speaker_set.keys())
            for i, sp in enumerate(sorted_speakers):
                if i < len(speaker_roles):
                    speaker_set[sp]["role"] = speaker_roles[i]

        audio_duration = poll_resp.get("audio_duration", 0)

        # Construir texto com timestamps (paridade com path sync)
        ts_interval = self._get_timestamp_interval_for_mode(mode) or 0
        text_with_timestamps = self._build_text_with_timestamps(segments, timestamp_interval=ts_interval)

        return {
            "segments": segments,
            "speakers": speaker_set,
            "elapsed_seconds": elapsed,
            "audio_duration": audio_duration,
            "text": poll_resp.get("text", ""),
            "text_with_timestamps": text_with_timestamps,
            "words": words,
            "utterances": utterances,
            "backend": "assemblyai",
            "transcript_id": transcript_id,
            "raw_response": poll_resp,
            "from_cache": True,
        }

    async def _poll_aai_transcript(
        self,
        poll_url: str,
        headers: Dict[str, str],
        transcript_id: str,
        emit: Callable[[str, int, str], Awaitable[None]],
        speaker_roles: Optional[list],
        mode: Optional[str],
        poll_start: int,
        poll_end: int,
        poll_start_time: float,
        audio_path: str,
        config_hash: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Polling de transcrição AAI (usado para retomar transcrições existentes).
        """
        import requests as http_requests

        poll_count = 0
        max_polls = 4800  # ~4 horas
        poll_timeout = (10, 30)
        fallback_audio_duration = self._get_audio_duration_seconds(audio_path)
        try:
            unknown_duration_estimated_seconds = float(
                os.getenv("IUDEX_ASSEMBLYAI_UNKNOWN_DURATION_SECONDS", "1800")
            )
        except Exception:
            unknown_duration_estimated_seconds = 1800.0

        while poll_count < max_polls:
            try:
                poll_resp = http_requests.get(poll_url, headers=headers, timeout=poll_timeout).json()
            except http_requests.exceptions.RequestException as e:
                logger.warning(f"AssemblyAI poll error (tentativa {poll_count}): {e}")
                poll_count += 1
                await asyncio.sleep(5)
                continue

            status = poll_resp.get("status")
            poll_count += 1
            elapsed_min = (time.time() - poll_start_time) / 60

            # Atualizar progresso baseado no tempo (estimativa)
            provider_audio_duration = poll_resp.get("audio_duration") or 0
            effective_audio_duration = provider_audio_duration or fallback_audio_duration
            if effective_audio_duration and effective_audio_duration > 0:
                estimated_total = effective_audio_duration / 10
                progress_ratio = min(0.99, elapsed_min * 60 / max(estimated_total, 60))
            else:
                progress_ratio = min(
                    0.99,
                    elapsed_min * 60 / max(unknown_duration_estimated_seconds, 300),
                )

            progress = poll_start + int(progress_ratio * (poll_end - poll_start))

            if poll_count % 10 == 0:
                if status == "queued":
                    msg = f"⏳ Na fila do AssemblyAI... ({elapsed_min:.0f}min)"
                elif status == "processing":
                    if effective_audio_duration and effective_audio_duration > 0:
                        dur_min = effective_audio_duration / 60
                        est_remaining = max(0, (dur_min / 10) - elapsed_min)
                        msg = f"🎙️ Transcrevendo ({elapsed_min:.0f}min, ~{est_remaining:.0f}min restantes)"
                    else:
                        msg = f"🎙️ Transcrevendo... ({elapsed_min:.0f}min)"
                else:
                    msg = f"⏳ Processando... ({elapsed_min:.0f}min)"
                await emit("transcription", progress, msg)
                logger.info(f"⏳ AssemblyAI polling (retomado)... status={status}, elapsed={elapsed_min:.1f}min")

            if status == "completed":
                logger.info(f"✅ AssemblyAI completou após {poll_count} polls ({elapsed_min:.1f}min) [retomado]")
                break
            elif status == "error":
                logger.warning(f"AssemblyAI error: {poll_resp.get('error')}")
                # Invalidar cache
                file_hash = self._compute_file_hash(audio_path)
                cache_path = self._get_aai_cache_path(file_hash)
                cache_path.unlink(missing_ok=True)
                return None

            await asyncio.sleep(3)
        else:
            logger.error(f"AssemblyAI timeout: max polls atingido [retomado]")
            return None

        # Processar resultado
        audio_duration = poll_resp.get("audio_duration", 0)

        # Atualizar cache
        file_hash = self._compute_file_hash(audio_path)
        self._update_aai_cache_status(
            file_hash,
            status="completed",
            audio_duration=audio_duration,
            result_cached=True,
        )

        return self._extract_aai_result_from_response(
            poll_resp,
            transcript_id,
            speaker_roles,
            mode,
            poll_start_time,
        )

    # Dicionário de keyterms por área de conhecimento
    AREA_KEYTERMS = {
        "juridico": [
            "Art.", "§", "inciso", "alínea", "caput", "STF", "STJ", "TST",
            "Lei nº", "Súmula", "CNPJ", "CPF", "OAB", "réu", "autor",
            "testemunha", "sentença", "acórdão", "recurso", "agravo",
        ],
        "medicina": [
            "mg", "ml", "UI", "IM", "IV", "VO", "bid", "tid", "qid",
            "diagnóstico", "prognóstico", "anamnese", "CID", "CRM",
        ],
        "ti": [
            "API", "REST", "GraphQL", "SQL", "NoSQL", "AWS", "GCP", "Azure",
            "Kubernetes", "Docker", "CI/CD", "Git", "deploy", "endpoint",
        ],
        "engenharia": [
            "MPa", "kN", "m²", "m³", "NBR", "ABNT", "CAD", "BIM",
        ],
        "financeiro": [
            "CNPJ", "CPF", "IRPF", "ICMS", "ISS", "PIS", "COFINS",
            "balanço", "DRE", "ROI", "EBITDA",
        ],
    }

    def _run_assemblyai_transcription(
        self,
        audio_path: str,
        language: Optional[str] = None,
        area: Optional[str] = None,
        custom_keyterms: Optional[list] = None,
    ) -> Optional[dict]:
        """
        Executa transcrição no AssemblyAI (roda em thread).

        Args:
            audio_path: Caminho do arquivo de áudio
            language: Código do idioma (pt, en, es...) ou None para auto-detect
            area: Área de conhecimento (juridico, medicina, ti, engenharia, financeiro)
            custom_keyterms: Lista de termos específicos do usuário
        """
        try:
            import assemblyai as aai
        except ImportError:
            logger.warning("Benchmark: assemblyai não instalado (pip install assemblyai)")
            return None

        api_key = self._get_assemblyai_key()
        if not api_key:
            logger.warning("Benchmark: ASSEMBLYAI_API_KEY não configurada")
            return None

        aai.settings.api_key = api_key

        # Montar keyterms: área + custom do usuário
        keyterms = []
        if area and area.lower() in self.AREA_KEYTERMS:
            keyterms.extend(self.AREA_KEYTERMS[area.lower()])
        if custom_keyterms:
            keyterms.extend(custom_keyterms[:100])
        keyterms = list(set(keyterms))[:200]  # Limite Universal-3: 200 termos

        # Configurar idioma: específico ou auto-detect
        config_kwargs = {
            "speech_models": ["universal-3-pro", "universal-2"],
            "speaker_labels": True,
        }
        if language and language.lower() not in ("auto", ""):
            config_kwargs["language_code"] = language.lower()
        else:
            config_kwargs["language_detection"] = True

        if keyterms:
            config_kwargs["keyterms_prompt"] = keyterms

        config = aai.TranscriptionConfig(**config_kwargs)

        start_time = time.time()
        try:
            transcriber = aai.Transcriber()
            transcript = transcriber.transcribe(audio_path, config=config)

            if transcript.status == aai.TranscriptStatus.error:
                logger.warning(f"Benchmark AAI erro: {transcript.error}")
                return None
        except Exception as e:
            logger.warning(f"Benchmark AAI exception: {e}")
            return None

        elapsed = time.time() - start_time

        segments = []
        if transcript.utterances:
            for utt in transcript.utterances:
                segments.append({
                    "start": utt.start / 1000.0,
                    "end": utt.end / 1000.0,
                    "text": utt.text,
                    "speaker_label": f"SPEAKER_{utt.speaker}",
                })

        return {
            "text": transcript.text or "",
            "segments": segments,
            "elapsed_seconds": elapsed,
            "audio_duration": transcript.audio_duration or 0,
            "num_speakers": len(set(s["speaker_label"] for s in segments)),
        }

    def _extract_local_segments(self, vomo, audio_path: str, high_accuracy: bool) -> Optional[list]:
        """Extrai segmentos do último resultado do VomoMLX (usa cache interno)."""
        try:
            if high_accuracy:
                result = vomo.transcribe_beam_with_segments(audio_path)
            else:
                result = vomo.transcribe_with_segments(audio_path)
            return result.get("segments", [])
        except Exception:
            return None

    def _finalize_benchmark_async(
        self,
        benchmark_future: concurrent.futures.Future,
        local_segments: list,
        local_text: str,
        local_elapsed: float,
        output_dir,
        video_name: str,
        audio_path: str,
    ):
        """Finaliza benchmark em background thread (não bloqueia o retorno da API)."""
        def _run():
            try:
                aai_result = benchmark_future.result(timeout=600)  # 10min max
                if aai_result is None:
                    logger.warning("Benchmark: AssemblyAI retornou None")
                    return

                report = self._compute_benchmark_metrics(
                    local_segments=local_segments,
                    local_text=local_text,
                    local_elapsed=local_elapsed,
                    aai_result=aai_result,
                    audio_path=audio_path,
                )

                # Salvar no output_dir
                out_path = Path(output_dir) if output_dir else Path("./storage/benchmarks")
                out_path.mkdir(parents=True, exist_ok=True)

                # 1. Métricas de comparação
                benchmark_path = out_path / f"{video_name}_BENCHMARK.json"
                benchmark_path.write_text(
                    json.dumps(report, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

                # 2. Transcrição completa do AssemblyAI (texto + segmentos com speakers)
                aai_full_path = out_path / f"{video_name}_ASSEMBLYAI.json"
                aai_full_path.write_text(
                    json.dumps({
                        "text": aai_result.get("text", ""),
                        "segments": aai_result.get("segments", []),
                        "num_speakers": aai_result.get("num_speakers", 0),
                        "audio_duration": aai_result.get("audio_duration", 0),
                        "elapsed_seconds": aai_result.get("elapsed_seconds", 0),
                    }, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

                # 3. Texto formatado do AssemblyAI (legível, com speakers)
                aai_txt_path = out_path / f"{video_name}_ASSEMBLYAI.txt"
                aai_lines = []
                prev_speaker = None
                for seg in aai_result.get("segments", []):
                    spk = seg.get("speaker_label", "")
                    if spk != prev_speaker:
                        aai_lines.append(f"\n{spk}")
                        prev_speaker = spk
                    start = seg.get("start", 0)
                    h, m, s = int(start // 3600), int((start % 3600) // 60), int(start % 60)
                    aai_lines.append(f"[{h:02d}:{m:02d}:{s:02d}] {seg.get('text', '')}")
                aai_txt_path.write_text("\n".join(aai_lines).strip(), encoding="utf-8")

                # 4. Segmentos locais do Whisper (para comparação lado a lado)
                local_full_path = out_path / f"{video_name}_LOCAL_SEGMENTS.json"
                local_full_path.write_text(
                    json.dumps({
                        "text": local_text,
                        "segments": local_segments,
                    }, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

                logger.info(
                    f"📊 Benchmark salvo: {benchmark_path.name}, "
                    f"{aai_full_path.name}, {aai_txt_path.name}, "
                    f"{local_full_path.name}"
                )

                # Também salvar numa pasta central de benchmarks
                self._append_to_benchmark_log(report, video_name)

            except concurrent.futures.TimeoutError:
                logger.warning("Benchmark: AssemblyAI timeout (>10min)")
            except Exception as e:
                logger.warning(f"Benchmark: erro na finalização: {e}")

        thread = threading.Thread(target=_run, name="benchmark-finalize", daemon=True)
        thread.start()

    def _compute_benchmark_metrics(
        self,
        local_segments: list,
        local_text: str,
        local_elapsed: float,
        aai_result: dict,
        audio_path: str,
    ) -> dict:
        """Calcula métricas de concordância entre os dois sistemas."""
        import difflib
        import unicodedata
        import numpy as np
        from scipy.optimize import linear_sum_assignment

        def _normalize(text: str) -> str:
            text = text.lower()
            text = unicodedata.normalize("NFD", text)
            text = "".join(c for c in text if unicodedata.category(c) != "Mn")
            text = re.sub(r"[^\w\s]", " ", text)
            return re.sub(r"\s+", " ", text).strip()

        def _ngrams(text: str, n: int) -> set:
            words = text.split()
            return {tuple(words[i:i+n]) for i in range(len(words) - n + 1)} if len(words) >= n else set()

        def _jaccard(a: set, b: set) -> float:
            union = a | b
            return len(a & b) / len(union) if union else 1.0

        # --- Text metrics ---
        norm_local = _normalize(local_text)
        norm_aai = _normalize(aai_result["text"])
        global_sim = difflib.SequenceMatcher(None, norm_local, norm_aai).ratio()
        bigram_ov = _jaccard(_ngrams(norm_local, 2), _ngrams(norm_aai, 2))
        trigram_ov = _jaccard(_ngrams(norm_local, 3), _ngrams(norm_aai, 3))

        # Windowed concordance (30s windows)
        aai_segs = aai_result["segments"]
        max_end = max(
            max((s.get("end", 0) for s in local_segments), default=0),
            max((s.get("end", 0) for s in aai_segs), default=0),
        )
        window_sims = []
        t = 0.0
        while t < max_end:
            t_end = t + 30.0
            text_l = " ".join(
                s.get("text", "") for s in local_segments
                if s.get("start", 0) < t_end and s.get("end", 0) > t
            )
            text_a = " ".join(
                s.get("text", "") for s in aai_segs
                if s.get("start", 0) < t_end and s.get("end", 0) > t
            )
            nl, na = _normalize(text_l), _normalize(text_a)
            if not nl and not na:
                window_sims.append({"start": t, "similarity": 1.0})
            elif not nl or not na:
                window_sims.append({"start": t, "similarity": 0.0})
            else:
                window_sims.append({
                    "start": t,
                    "similarity": difflib.SequenceMatcher(None, nl, na).ratio(),
                })
            t = t_end

        sims_vals = [w["similarity"] for w in window_sims]

        # --- Diarization metrics ---
        speakers_l = sorted(set(s.get("speaker_label", "") for s in local_segments if s.get("speaker_label")))
        speakers_a = sorted(set(s.get("speaker_label", "") for s in aai_segs if s.get("speaker_label")))

        slot_dur = 0.5
        n_slots = int(max_end / slot_dur) + 1 if max_end > 0 else 0

        def _fill_slots(segs):
            slots = [None] * n_slots
            for s in segs:
                i_s = int(s.get("start", 0) / slot_dur)
                i_e = min(int(s.get("end", 0) / slot_dur) + 1, n_slots)
                for i in range(i_s, i_e):
                    slots[i] = s.get("speaker_label", "")
            return slots

        slots_l = _fill_slots(local_segments) if n_slots > 0 else []
        slots_a = _fill_slots(aai_segs) if n_slots > 0 else []

        # Hungarian matching
        speaker_mapping = {}
        agreement_ratio = 0.0
        if speakers_l and speakers_a and n_slots > 0:
            matrix = np.zeros((len(speakers_l), len(speakers_a)))
            for i, sl in enumerate(speakers_l):
                for j, sa in enumerate(speakers_a):
                    matrix[i][j] = sum(
                        1 for k in range(n_slots)
                        if k < len(slots_l) and k < len(slots_a)
                        and slots_l[k] == sl and slots_a[k] == sa
                    )
            row_ind, col_ind = linear_sum_assignment(-matrix)
            for r, c in zip(row_ind, col_ind):
                if r < len(speakers_l) and c < len(speakers_a):
                    speaker_mapping[speakers_l[r]] = speakers_a[c]

            agree = 0
            total = 0
            for k in range(min(len(slots_l), len(slots_a))):
                if slots_l[k] is None and slots_a[k] is None:
                    continue
                total += 1
                if speaker_mapping.get(slots_l[k]) == slots_a[k]:
                    agree += 1
            agreement_ratio = agree / total if total > 0 else 0.0

        # Turn detection
        def _detect_turns(segs):
            turns = []
            prev = None
            for s in sorted(segs, key=lambda x: x.get("start", 0)):
                spk = s.get("speaker_label", "")
                if spk and spk != prev:
                    turns.append(s.get("start", 0))
                    prev = spk
            return turns

        turns_l = _detect_turns(local_segments)
        turns_a = _detect_turns(aai_segs)

        def _match_turns(ta, tb, tol=2.0):
            used = set()
            matched = 0
            diffs = []
            for t in ta:
                best_d, best_i = None, None
                for idx, t2 in enumerate(tb):
                    if idx in used:
                        continue
                    d = abs(t - t2)
                    if d <= tol and (best_d is None or d < best_d):
                        best_d, best_i = d, idx
                if best_i is not None:
                    matched += 1
                    used.add(best_i)
                    diffs.append(best_d)
            return matched, len(ta), diffs

        m_la, t_la, d_la = _match_turns(turns_l, turns_a)
        m_al, t_al, d_al = _match_turns(turns_a, turns_l)
        all_diffs = d_la + d_al

        # Speech coverage
        def _coverage(segs, total_dur):
            if total_dur <= 0:
                return 0.0
            return min(sum(s.get("end", 0) - s.get("start", 0) for s in segs) / total_dur, 1.0)

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "audio_path": str(audio_path),
            "text": {
                "global_similarity": round(global_sim, 4),
                "bigram_overlap": round(bigram_ov, 4),
                "trigram_overlap": round(trigram_ov, 4),
                "window_mean": round(float(np.mean(sims_vals)), 4) if sims_vals else 0.0,
                "window_min": round(float(np.min(sims_vals)), 4) if sims_vals else 0.0,
                "window_max": round(float(np.max(sims_vals)), 4) if sims_vals else 0.0,
                "per_window": window_sims,
            },
            "diarization": {
                "speakers_local": len(speakers_l),
                "speakers_aai": len(speakers_a),
                "agreement_ratio": round(agreement_ratio, 4),
                "speaker_mapping": speaker_mapping,
                "turn_precision": round(m_la / t_la, 4) if t_la > 0 else 0.0,
                "turn_recall": round(m_al / t_al, 4) if t_al > 0 else 0.0,
                "turn_timing_mean_diff": round(float(np.mean(all_diffs)), 3) if all_diffs else 0.0,
                "turn_timing_median_diff": round(float(np.median(all_diffs)), 3) if all_diffs else 0.0,
                "speech_coverage_local": round(_coverage(local_segments, max_end), 4),
                "speech_coverage_aai": round(_coverage(aai_segs, max_end), 4),
            },
            "performance": {
                "local_elapsed_seconds": round(local_elapsed, 1),
                "aai_elapsed_seconds": round(aai_result.get("elapsed_seconds", 0), 1),
                "audio_duration": round(max_end, 1),
                "local_rtf": round(local_elapsed / max_end, 4) if max_end > 0 else 0.0,
                "aai_rtf": round(aai_result.get("elapsed_seconds", 0) / max_end, 4) if max_end > 0 else 0.0,
                "speedup_ratio": round(aai_result.get("elapsed_seconds", 1) / local_elapsed, 2) if local_elapsed > 0 else 0.0,
            },
            "cost": {
                "assemblyai_usd": round((max_end / 3600) * 0.90, 2),
                "local_usd": 0.0,
            },
        }

    def _append_to_benchmark_log(self, report: dict, video_name: str):
        """Salva resultado na pasta central de benchmarks para análise agregada."""
        try:
            from app.core.config import settings
            base = Path(settings.LOCAL_STORAGE_PATH) / "benchmarks"
        except Exception:
            base = Path("./storage") / "benchmarks"
        base.mkdir(parents=True, exist_ok=True)

        log_path = base / "benchmark_log.jsonl"
        entry = {
            "video_name": video_name,
            **report,
        }
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # ================================================================
    # AssemblyAI: Transcrição primária para AUDIENCIA/REUNIAO
    # ================================================================

    def _get_timestamp_interval_for_mode(self, mode: Optional[str]) -> int:
        """
        Retorna intervalo de timestamps baseado no modo.

        - APOSTILA/FIDELIDADE/RAW: 60s (aulas longas, menos trocas)
        - Outros modos: 0 (por utterance, cada segmento tem timestamp)
        """
        mode_upper = (mode or "").upper()
        if mode_upper in ("APOSTILA", "FIDELIDADE", "RAW"):
            return 60
        return 0  # Por utterance

    def _get_assemblyai_prompt_for_mode(
        self,
        mode: Optional[str],
        language: str = "auto",
        area: Optional[str] = None,
        speaker_roles: Optional[list] = None,
        custom_keyterms: Optional[list] = None,
    ) -> tuple[str, list[str]]:
        """
        Retorna (prompt, keyterms_list) para AssemblyAI.
        Foco: transcrição bruta fiel, sem formatação.

        Args:
            mode: Modo de transcrição (APOSTILA, AUDIENCIA, REUNIAO, LEGENDA, etc.)
            language: Código do idioma (pt, en, es, auto, etc.)
            area: Área de conhecimento (juridico, medicina, ti, engenharia, financeiro)
            speaker_roles: Lista de roles/participantes esperados
            custom_keyterms: Termos específicos do usuário para melhorar reconhecimento

        Returns:
            Tupla (prompt: str, keyterms: list[str])
        """
        mode_upper = (mode or "APOSTILA").upper()

        # Montar keyterms: área + custom do usuário
        keyterms = []
        if area and area.lower() in self.AREA_KEYTERMS:
            keyterms.extend(self.AREA_KEYTERMS[area.lower()])
        if custom_keyterms:
            keyterms.extend(custom_keyterms[:100])  # Limite de 100 custom
        # Limitar a 200 (limite do Universal-3)
        keyterms = list(set(keyterms))[:200]

        # Prompts focados em TRANSCRIÇÃO BRUTA FIEL (sem formatação)
        # A formatação vem depois (Gemini/GPT no mlx_vomo.py)
        prompts = {
            "APOSTILA": (
                "Verbatim transcription of educational content. "
                "Preserve exactly: technical terms, proper nouns, numbers, "
                "foreign expressions, citations, references. "
                "Do not correct grammar or paraphrase. "
                "Mark unclear speech as [INAUDIBLE]."
            ),
            "FIDELIDADE": (
                "Literal verbatim transcription. "
                "Transcribe everything exactly as spoken including hesitations. "
                "Do not correct, interpret, or omit anything. "
                "Mark unclear speech as [INAUDIBLE]."
            ),
            "AUDIENCIA": (
                "Legal hearing transcription. "
                "Preserve exactly: case numbers, dates, monetary values, names, "
                "legal citations, procedural terms. "
                "Mark: [INAUDIBLE], [OVERLAPPING], [PAUSE] when relevant. "
                "Do not correct grammar or interpret meaning."
            ),
            "REUNIAO": (
                "Meeting transcription. "
                "Preserve exactly: names, dates, action items, numbers, "
                "technical terms, acronyms, decisions. "
                "Do not correct grammar or paraphrase."
            ),
            "DEPOIMENTO": (
                "Testimony transcription. "
                "Preserve exactly: dates, times, names, addresses, sequences of events. "
                "Mark: [HESITATION], [PAUSE], [INAUDIBLE] when relevant. "
                "Transcribe literally without corrections."
            ),
            "LEGENDA": (
                "Transcription for subtitles. "
                "Preserve: dialogue, names, places. "
                "Mark: [MUSIC], [APPLAUSE], [LAUGHTER] for non-speech audio."
            ),
        }

        base_prompt = prompts.get(mode_upper, prompts["APOSTILA"])

        # Adicionar contexto de área se fornecido
        if area:
            base_prompt = f"{area.capitalize()} domain. " + base_prompt

        # Adicionar speakers se fornecidos
        if speaker_roles:
            roles_str = ", ".join(str(r) for r in speaker_roles[:10])
            base_prompt += f" Speakers: {roles_str}."

        return base_prompt, keyterms

    def _transcribe_assemblyai_with_roles(
        self,
        audio_path: str,
        speaker_roles: Optional[list] = None,
        language: str = "pt",
        speakers_expected: Optional[int] = None,
        mode: Optional[str] = None,
        context: Optional[str] = None,
        area: Optional[str] = None,
        custom_keyterms: Optional[list] = None,
        speaker_id_type: Optional[str] = None,
        speaker_id_values: Optional[list] = None,
    ) -> Optional[dict]:
        """
        Transcreve via AssemblyAI Universal-3 Pro com:
        - Prompting em linguagem natural (instrui o modelo sobre como transcrever)
        - Speaker identification por role
        - Audio tagging de eventos sonoros
        - Suporte a múltiplos idiomas
        - Keyterms para melhorar reconhecimento de termos específicos

        Args:
            audio_path: Caminho do arquivo de áudio
            speaker_roles: Lista de roles esperados (ex: ["Juiz", "Advogado", "Testemunha"])
            language: Código do idioma (pt, en, es, fr, de, it, ja, zh, ko, etc.)
            speakers_expected: Número esperado de speakers
            mode: Modo de transcrição (APOSTILA, AUDIENCIA, REUNIAO, LEGENDA, etc.)
            context: Contexto adicional (ex: "audiência trabalhista", "filme de comédia")
            area: Área de conhecimento (juridico, medicina, ti, engenharia, financeiro)
            custom_keyterms: Termos específicos do usuário para melhorar reconhecimento

        Returns dict com: text, segments, speakers, elapsed_seconds, audio_duration, backend
        """
        import requests as http_requests

        api_key = self._get_assemblyai_key()
        if not api_key:
            return None

        base_url = "https://api.assemblyai.com"
        headers = {"authorization": api_key, "content-type": "application/json"}

        # === Cache AAI: Calcular config hash para verificação ===
        config_hash = self._get_aai_config_hash(
            language=language,
            speaker_labels=bool(speaker_roles) or True,
            speakers_expected=speakers_expected,
            mode=mode,
        )

        # === Cache AAI: Verificar se existe transcrição em cache ===
        # Nota: Este método é síncrono, então usamos uma verificação simplificada
        file_hash = self._compute_file_hash(audio_path)
        cache_path = self._get_aai_cache_path(file_hash)

        if cache_path.exists():
            try:
                cache = json.loads(cache_path.read_text(encoding="utf-8"))
                if cache.get("config_hash") == config_hash:
                    transcript_id = cache.get("transcript_id")
                    if transcript_id:
                        # Verificar status no AAI (sync)
                        try:
                            status_resp = http_requests.get(
                                f"{base_url}/v2/transcript/{transcript_id}",
                                headers={"authorization": api_key},
                                timeout=(10, 30),
                            )
                            if status_resp.status_code == 200:
                                aai_data = status_resp.json()
                                if aai_data.get("status") == "completed":
                                    logger.info(f"✅ Usando cache AAI (sync): {transcript_id}")
                                    # Retornar resultado do cache
                                    return self._extract_aai_result_sync(
                                        aai_data, transcript_id, speaker_roles, mode, time.time()
                                    )
                                elif aai_data.get("status") in ("processing", "queued"):
                                    logger.info(f"🔄 Retomando transcrição AAI (sync): {transcript_id}")
                                    # Ir direto para polling
                                    poll_url = f"{base_url}/v2/transcript/{transcript_id}"
                                    return self._poll_aai_transcript_sync(
                                        poll_url, headers, transcript_id, speaker_roles, mode,
                                        audio_path, config_hash, time.time()
                                    )
                        except Exception as e:
                            logger.warning(f"Erro ao verificar cache AAI: {e}")
            except Exception as e:
                logger.warning(f"Erro ao ler cache AAI: {e}")

        # 1. Upload do arquivo local (timeout generoso para arquivos grandes de até 10h)
        start_time = time.time()
        file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
        # Timeout: 30s connect + 30min read (arquivos grandes podem demorar)
        upload_timeout = (30, 1800)
        logger.info(f"📤 AssemblyAI: uploading audio ({file_size_mb:.1f}MB)...")
        try:
            with open(audio_path, "rb") as f:
                upload_resp = http_requests.post(
                    f"{base_url}/v2/upload",
                    headers={"authorization": api_key},
                    data=f,
                    timeout=upload_timeout,
                )
        except http_requests.exceptions.Timeout:
            logger.error(f"AssemblyAI upload timeout após {upload_timeout[1]}s para arquivo de {file_size_mb:.1f}MB")
            return None
        except http_requests.exceptions.RequestException as e:
            logger.error(f"AssemblyAI upload error: {e}")
            return None
        if upload_resp.status_code != 200:
            logger.warning(f"AssemblyAI upload failed: {upload_resp.status_code} - {upload_resp.text[:200]}")
            return None
        audio_url = upload_resp.json()["upload_url"]
        logger.info(f"✅ AssemblyAI upload completo em {time.time() - start_time:.1f}s")

        # 2. Obter prompt e keyterms para o modo/área
        aai_prompt, keyterms = self._get_assemblyai_prompt_for_mode(
            mode=mode,
            language=language,
            area=area,
            speaker_roles=speaker_roles,
            custom_keyterms=custom_keyterms,
        )
        mode_upper = (mode or "APOSTILA").upper()

        # 3. Submeter transcrição com Universal-3 Pro (primeiro modelo promptable)
        # IMPORTANTE: usar "speech_models" (array), não "speech_model" (deprecated)
        data = {
            "audio_url": audio_url,
            "speech_models": ["universal-3-pro"],  # Modelo com suporte a prompting
            "prompt": aai_prompt,  # Instrução em linguagem natural
            "speaker_labels": True,
            "language_code": language,
        }

        if keyterms:
            data["keyterms_prompt"] = keyterms
        if speakers_expected and speakers_expected > 0:
            data["speakers_expected"] = speakers_expected

        # Speaker Identification (v2.33): Identifica falantes por nome ou papel
        if speaker_id_type and speaker_id_values:
            valid_values = [v[:35] for v in speaker_id_values if v and v.strip()]
            if valid_values:
                data["speech_understanding"] = {
                    "request": {
                        "speaker_identification": {
                            "speaker_type": speaker_id_type,
                            "known_values": valid_values
                        }
                    }
                }
                logger.info(f"🎭 Speaker Identification ativo: {speaker_id_type} = {valid_values}")

        logger.info(f"🎙️ AssemblyAI Universal-3 Pro [{mode_upper}]: transcribing...")
        try:
            resp = http_requests.post(f"{base_url}/v2/transcript", headers=headers, json=data, timeout=(30, 60))
        except http_requests.exceptions.RequestException as e:
            logger.error(f"AssemblyAI transcript submit error: {e}")
            return None
        if resp.status_code != 200:
            logger.warning(f"AssemblyAI transcript submit failed: {resp.status_code} - {resp.text[:500]}")
            return None

        transcript_id = resp.json()["id"]
        logger.info(f"📋 AssemblyAI job criado: {transcript_id}")

        # === Cache AAI: Persistir IMEDIATAMENTE após obter transcript_id ===
        self._save_aai_cache(
            file_path=audio_path,
            transcript_id=transcript_id,
            audio_url=audio_url,
            config_hash=config_hash,
            status="processing",
        )

        # 3. Poll até completar (com logging de progresso)
        # Limite: 4800 polls * 3s = 4 horas (suficiente para áudios de 10h)
        poll_url = f"{base_url}/v2/transcript/{transcript_id}"
        poll_count = 0
        max_polls = 4800  # ~4 horas
        poll_timeout = (10, 30)  # 10s connect, 30s read
        while poll_count < max_polls:
            try:
                poll_resp = http_requests.get(poll_url, headers=headers, timeout=poll_timeout).json()
            except http_requests.exceptions.RequestException as e:
                logger.warning(f"AssemblyAI poll error (tentativa {poll_count}): {e}")
                poll_count += 1
                time.sleep(5)
                continue
            status = poll_resp.get("status")
            poll_count += 1

            # Log a cada 20 polls (~1min)
            if poll_count % 20 == 0:
                dur = poll_resp.get("audio_duration")
                dur_str = f"{dur/60:.1f}min" if dur else "?"
                elapsed_min = (poll_count * 3) / 60
                logger.info(f"⏳ AssemblyAI polling... status={status}, duração={dur_str}, elapsed={elapsed_min:.1f}min")

            if status == "completed":
                logger.info(f"✅ AssemblyAI completou após {poll_count} polls ({poll_count * 3 / 60:.1f}min)")
                break
            elif status == "error":
                logger.warning(f"AssemblyAI error: {poll_resp.get('error')}")
                return None
            time.sleep(3)
        else:
            logger.error(f"AssemblyAI timeout: max polls ({max_polls}) atingido após {max_polls * 3 / 3600:.1f}h")
            return None

        elapsed = time.time() - start_time

        # 4. Extrair utterances com roles
        utterances = poll_resp.get("utterances", [])
        words = poll_resp.get("words", [])
        segments = []
        speaker_set = {}

        # Se temos poucas utterances mas muitas words, construir segments a partir de words
        # Isso acontece quando há apenas 1 speaker - AAI agrupa tudo em 1 utterance
        ts_interval = self._get_timestamp_interval_for_mode(mode) or 0

        if len(utterances) <= 2 and len(words) > 50 and ts_interval > 0:
            # Agrupar words em segmentos de ~ts_interval segundos
            logger.info(f"📝 AssemblyAI: usando words ({len(words)}) para gerar timestamps a cada {ts_interval}s")
            current_segment_words = []
            segment_start = None

            for word in words:
                word_start = word.get("start", 0) / 1000.0
                word_end = word.get("end", 0) / 1000.0
                word_text = word.get("text", "")
                word_speaker = word.get("speaker", "A")

                if segment_start is None:
                    segment_start = word_start

                current_segment_words.append(word_text)

                # Criar novo segmento a cada ts_interval segundos
                if word_end - segment_start >= ts_interval:
                    segments.append({
                        "start": segment_start,
                        "end": word_end,
                        "text": " ".join(current_segment_words),
                        "speaker_label": word_speaker,
                    })
                    if word_speaker not in speaker_set:
                        speaker_set[word_speaker] = {"label": word_speaker, "role": ""}
                    current_segment_words = []
                    segment_start = None

            # Adicionar último segmento
            if current_segment_words:
                last_word = words[-1]
                segments.append({
                    "start": segment_start or 0,
                    "end": last_word.get("end", 0) / 1000.0,
                    "text": " ".join(current_segment_words),
                    "speaker_label": last_word.get("speaker", "A"),
                })
        else:
            # Usar utterances normalmente
            for utt in utterances:
                speaker = utt.get("speaker", "Unknown")
                segments.append({
                    "start": utt["start"] / 1000.0,
                    "end": utt["end"] / 1000.0,
                    "text": utt["text"],
                    "speaker_label": speaker,
                })
                if speaker not in speaker_set:
                    speaker_set[speaker] = {
                        "label": speaker,
                        "role": speaker if speaker_roles and speaker in speaker_roles else "",
                    }

        audio_duration = poll_resp.get("audio_duration", 0)

        logger.info(
            f"✅ AssemblyAI: {len(segments)} segments, "
            f"{len(speaker_set)} speakers, {elapsed:.1f}s"
        )

        # === Cache AAI: Atualizar status para completed ===
        self._update_aai_cache_status(
            file_hash,
            status="completed",
            audio_duration=audio_duration,
            result_cached=True,
        )

        # Construir texto com timestamps
        text_with_timestamps = self._build_text_with_timestamps(segments, timestamp_interval=ts_interval)

        return {
            "text": poll_resp.get("text", ""),
            "text_with_timestamps": text_with_timestamps,
            "segments": segments,
            "speakers": list(speaker_set.values()),
            "elapsed_seconds": elapsed,
            "audio_duration": audio_duration,
            "num_speakers": len(speaker_set),
            "backend": "assemblyai",
            "transcript_id": transcript_id,
            "raw_response": poll_resp,
        }

    def _extract_aai_result_sync(
        self,
        poll_resp: Dict[str, Any],
        transcript_id: str,
        speaker_roles: Optional[list],
        mode: Optional[str],
        start_time: float,
    ) -> Dict[str, Any]:
        """
        Extrai resultado formatado de uma resposta AAI (versão síncrona).
        Usado para recuperação de cache no método síncrono.
        """
        elapsed = time.time() - start_time
        utterances = poll_resp.get("utterances", [])
        words = poll_resp.get("words", [])
        segments = []
        speaker_set = {}

        ts_interval = self._get_timestamp_interval_for_mode(mode) or 0

        if len(utterances) <= 2 and len(words) > 50 and ts_interval > 0:
            current_segment_words = []
            segment_start = None

            for word in words:
                word_start = word.get("start", 0) / 1000.0
                word_end = word.get("end", 0) / 1000.0
                word_text = word.get("text", "")
                word_speaker = word.get("speaker", "A")

                if segment_start is None:
                    segment_start = word_start

                current_segment_words.append(word_text)

                if word_end - segment_start >= ts_interval:
                    segments.append({
                        "start": segment_start,
                        "end": word_end,
                        "text": " ".join(current_segment_words),
                        "speaker_label": word_speaker,
                    })
                    if word_speaker not in speaker_set:
                        speaker_set[word_speaker] = {"label": word_speaker, "role": ""}
                    current_segment_words = []
                    segment_start = None

            if current_segment_words:
                last_word = words[-1]
                segments.append({
                    "start": segment_start or 0,
                    "end": last_word.get("end", 0) / 1000.0,
                    "text": " ".join(current_segment_words),
                    "speaker_label": last_word.get("speaker", "A"),
                })
        else:
            for utt in utterances:
                speaker = utt.get("speaker", "Unknown")
                segments.append({
                    "start": utt["start"] / 1000.0,
                    "end": utt["end"] / 1000.0,
                    "text": utt["text"],
                    "speaker_label": speaker,
                })
                if speaker not in speaker_set:
                    speaker_set[speaker] = {
                        "label": speaker,
                        "role": speaker if speaker_roles and speaker in speaker_roles else "",
                    }

        audio_duration = poll_resp.get("audio_duration", 0)
        text_with_timestamps = self._build_text_with_timestamps(segments, timestamp_interval=ts_interval)

        return {
            "text": poll_resp.get("text", ""),
            "text_with_timestamps": text_with_timestamps,
            "segments": segments,
            "speakers": list(speaker_set.values()),
            "elapsed_seconds": elapsed,
            "audio_duration": audio_duration,
            "num_speakers": len(speaker_set),
            "backend": "assemblyai",
            "transcript_id": transcript_id,
            "raw_response": poll_resp,
            "from_cache": True,
        }

    def _poll_aai_transcript_sync(
        self,
        poll_url: str,
        headers: Dict[str, str],
        transcript_id: str,
        speaker_roles: Optional[list],
        mode: Optional[str],
        audio_path: str,
        config_hash: str,
        start_time: float,
    ) -> Optional[Dict[str, Any]]:
        """
        Polling síncrono de transcrição AAI (usado para retomar transcrições existentes).
        """
        import requests as http_requests

        poll_count = 0
        max_polls = 4800
        poll_timeout = (10, 30)
        poll_start_time = time.time()
        try:
            max_poll_minutes = float(os.getenv("IUDEX_ASSEMBLYAI_MAX_POLL_MINUTES", "240"))
        except Exception:
            max_poll_minutes = 240.0

        while poll_count < max_polls:
            try:
                poll_resp = http_requests.get(poll_url, headers=headers, timeout=poll_timeout).json()
            except http_requests.exceptions.RequestException as e:
                logger.warning(f"AssemblyAI poll error (sync, tentativa {poll_count}): {e}")
                poll_count += 1
                time.sleep(5)
                continue

            status = poll_resp.get("status")
            poll_count += 1
            elapsed_min = (time.time() - poll_start_time) / 60
            if max_poll_minutes and max_poll_minutes > 0 and elapsed_min >= max_poll_minutes:
                logger.error(f"AssemblyAI timeout (sync, retomado): excedeu {max_poll_minutes:.0f}min (status={status})")
                file_hash = self._compute_file_hash(audio_path)
                cache_path = self._get_aai_cache_path(file_hash)
                try:
                    cache_path.unlink(missing_ok=True)
                except Exception:
                    pass
                return None

            if poll_count % 20 == 0:
                dur = poll_resp.get("audio_duration")
                dur_str = f"{dur/60:.1f}min" if dur else "?"
                elapsed_est_min = (poll_count * 3) / 60
                logger.info(f"⏳ AssemblyAI polling (sync, retomado)... status={status}, duração={dur_str}, elapsed={elapsed_est_min:.1f}min")

            if status == "completed":
                logger.info(f"✅ AssemblyAI completou (sync, retomado) após {poll_count} polls")
                break
            elif status == "error":
                logger.warning(f"AssemblyAI error: {poll_resp.get('error')}")
                file_hash = self._compute_file_hash(audio_path)
                cache_path = self._get_aai_cache_path(file_hash)
                cache_path.unlink(missing_ok=True)
                return None

            time.sleep(3)
        else:
            logger.error(f"AssemblyAI timeout (sync, retomado): max polls atingido")
            return None

        # Atualizar cache
        file_hash = self._compute_file_hash(audio_path)
        audio_duration = poll_resp.get("audio_duration", 0)
        self._update_aai_cache_status(
            file_hash,
            status="completed",
            audio_duration=audio_duration,
            result_cached=True,
        )

        return self._extract_aai_result_sync(
            poll_resp, transcript_id, speaker_roles, mode, start_time
        )

    def _build_text_with_timestamps(
        self,
        segments: list,
        timestamp_interval: int = 60,
        include_speakers: bool = True,
    ) -> str:
        """
        Constrói texto com timestamps e speaker labels (estilo Whisper).

        Args:
            segments: Lista de segmentos com start, end, text, speaker_label
            timestamp_interval: Intervalo em segundos para inserir timestamps.
                               0 = timestamp em cada utterance (por segmento)
                               60 = timestamp a cada 60 segundos (padrão para APOSTILA)
            include_speakers: Se True, inclui headers de speaker nas mudanças
        """
        if not segments:
            return ""

        lines = []
        last_timestamp = -999
        current_speaker = None
        per_utterance = (timestamp_interval == 0)

        def _fmt_ts(seconds: float) -> str:
            m, s = divmod(int(seconds), 60)
            h, m = divmod(m, 60)
            return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"

        for seg in segments:
            start = seg.get("start", 0)
            text = (seg.get("text") or "").strip()
            speaker = seg.get("speaker_label", "")
            if not text:
                continue

            # Mudança de speaker → quebra + header
            if include_speakers and speaker and speaker != current_speaker:
                if lines:
                    lines.append("")  # Linha em branco para separar
                lines.append(f"{speaker}")
                current_speaker = speaker
                last_timestamp = -999  # Reset para forçar timestamp no novo speaker

            # Inserir timestamp: por utterance (0) ou a cada N segundos
            if per_utterance or (start - last_timestamp >= timestamp_interval):
                lines.append(f"[{_fmt_ts(start)}] {text}")
                last_timestamp = start
            else:
                lines.append(text)

        return "\n".join(lines)

    # ================================================================
    # ElevenLabs Scribe v2: Transcrição primária para LEGENDAS
    # ================================================================

    def _get_elevenlabs_key(self) -> Optional[str]:
        """Retorna a API key do ElevenLabs se configurada."""
        try:
            from app.core.config import settings
            return settings.ELEVENLABS_API_KEY
        except Exception:
            return os.environ.get("ELEVENLABS_API_KEY")

    def _transcribe_elevenlabs_scribe(
        self,
        audio_path: str,
        language: str = "pt",
        diarize: bool = True,
        tag_audio_events: bool = True,
    ) -> Optional[dict]:
        """
        Transcreve via ElevenLabs Scribe v2 com timestamps precisos por palavra.
        Ideal para geração de legendas (SRT/VTT).

        Features:
        - Timestamps word-level precisos
        - Diarização de até 32 falantes
        - Detecção de eventos de áudio (risos, música, aplausos)
        - Suporta arquivos de até 3GB / 10h
        - Cache de resultados para evitar reprocessamento

        Returns dict com: text, segments, words, speakers, elapsed_seconds, audio_duration, backend
        """
        import requests as http_requests

        api_key = self._get_elevenlabs_key()
        if not api_key:
            logger.warning("ElevenLabs API key não configurada")
            return None

        # === Cache ElevenLabs: Calcular config hash e verificar cache ===
        config_hash = self._get_elevenlabs_config_hash(
            language=language,
            diarize=diarize,
            tag_audio_events=tag_audio_events,
        )

        cached = self._check_elevenlabs_cache(audio_path, config_hash)
        if cached:
            logger.info(f"✅ Usando cache ElevenLabs para {Path(audio_path).name}")
            return cached

        url = "https://api.elevenlabs.io/v1/speech-to-text"
        headers = {"xi-api-key": api_key}

        start_time = time.time()
        logger.info(f"🎬 ElevenLabs Scribe: transcrevendo {Path(audio_path).name}...")

        try:
            with open(audio_path, "rb") as f:
                files = {"file": (Path(audio_path).name, f)}
                data = {
                    "model_id": "scribe_v1",  # scribe_v1 é o modelo atual
                    "language_code": language if language != "auto" else None,
                    "diarize": str(diarize).lower(),
                    "tag_audio_events": str(tag_audio_events).lower(),
                }
                # Remove None values
                data = {k: v for k, v in data.items() if v is not None}

                response = http_requests.post(url, headers=headers, files=files, data=data, timeout=600)

            if response.status_code != 200:
                logger.warning(f"ElevenLabs Scribe failed: {response.status_code} - {response.text[:200]}")
                return None

            result = response.json()
            elapsed = time.time() - start_time

        except Exception as e:
            logger.warning(f"ElevenLabs Scribe exception: {e}")
            return None

        # Processar palavras em segments (agrupar por sentença/fala)
        words = result.get("words", [])
        text = result.get("text", "")
        detected_language = result.get("language_code", language)

        # Agrupar palavras em segments por speaker e pausas
        segments = []
        speaker_set = {}
        current_segment = None

        for word_data in words:
            word_type = word_data.get("type", "word")
            if word_type not in ("word", "audio_event"):
                continue  # Pular spacings

            speaker = word_data.get("speaker_id", "speaker_0")
            word_text = word_data.get("text", "")
            word_start = word_data.get("start", 0)
            word_end = word_data.get("end", 0)

            # Registrar speaker
            if speaker not in speaker_set:
                speaker_set[speaker] = {"label": speaker, "role": ""}

            # Criar novo segment se: novo speaker, pausa > 1.5s, ou primeiro word
            should_split = (
                current_segment is None
                or current_segment["speaker_label"] != speaker
                or (word_start - current_segment["end"]) > 1.5
            )

            if should_split:
                if current_segment and current_segment["text"].strip():
                    segments.append(current_segment)
                current_segment = {
                    "start": word_start,
                    "end": word_end,
                    "text": word_text,
                    "speaker_label": speaker,
                    "words": [word_data],  # Guardar words para legendas word-level
                }
            else:
                current_segment["end"] = word_end
                current_segment["text"] += word_text
                current_segment["words"].append(word_data)

        # Adicionar último segment
        if current_segment and current_segment["text"].strip():
            segments.append(current_segment)

        # Calcular duração do áudio
        audio_duration = 0
        if segments:
            audio_duration = max(s["end"] for s in segments)

        logger.info(
            f"✅ ElevenLabs Scribe: {len(segments)} segments, "
            f"{len(words)} words, {len(speaker_set)} speakers, {elapsed:.1f}s"
        )

        # Construir texto com timestamps (como Whisper faz)
        text_with_timestamps = self._build_text_with_timestamps(segments)

        result_dict = {
            "text": text,
            "text_with_timestamps": text_with_timestamps,
            "segments": segments,
            "words": words,  # Words originais para legendas word-level
            "speakers": list(speaker_set.values()),
            "elapsed_seconds": elapsed,
            "audio_duration": audio_duration,
            "num_speakers": len(speaker_set),
            "backend": "elevenlabs",
            "language_detected": detected_language,
            "raw_response": result,
        }

        # === Cache ElevenLabs: Salvar resultado para evitar reprocessamento ===
        self._save_elevenlabs_cache(audio_path, config_hash, result_dict)

        return result_dict

    def _start_whisper_benchmark_for_hearing(
        self,
        vomo,
        audio_path: str,
        high_accuracy: bool,
    ) -> concurrent.futures.Future:
        """Dispara Whisper local em thread separada para benchmark (quando AAI é primário)."""
        def _run():
            try:
                whisper_start = time.time()
                if high_accuracy and hasattr(vomo, "transcribe_beam_with_segments"):
                    structured = vomo.transcribe_beam_with_segments(audio_path)
                elif hasattr(vomo, "transcribe_with_segments"):
                    structured = vomo.transcribe_with_segments(audio_path)
                else:
                    return None
                whisper_elapsed = time.time() - whisper_start
                return {
                    "text": structured.get("text", ""),
                    "segments": structured.get("segments", []),
                    "elapsed_seconds": whisper_elapsed,
                }
            except Exception as e:
                logger.warning(f"Benchmark Whisper (hearing) falhou: {e}")
                return None

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="benchmark-whisper")
        future = executor.submit(_run)
        executor.shutdown(wait=False)
        return future

    def _start_whisper_benchmark_for_apostila(
        self,
        audio_path: str,
        mode: str,
        high_accuracy: bool,
        diarization,
        diarization_strict: bool,
        language: Optional[str],
    ) -> concurrent.futures.Future:
        """Dispara Whisper local em thread separada para benchmark (apostila com AAI primário)."""
        def _run():
            try:
                VomoMLX = _load_vomo_class()
                vomo_bench = VomoMLX()
                whisper_start = time.time()
                text = vomo_bench.transcribe_file(
                    audio_path,
                    mode=mode,
                    high_accuracy=high_accuracy,
                    diarization=diarization,
                    diarization_strict=diarization_strict,
                    language=language,
                )
                whisper_elapsed = time.time() - whisper_start
                # Extrair segmentos se disponíveis
                segments = []
                try:
                    if high_accuracy and hasattr(vomo_bench, "transcribe_beam_with_segments"):
                        structured = vomo_bench.transcribe_beam_with_segments(audio_path)
                    elif hasattr(vomo_bench, "transcribe_with_segments"):
                        structured = vomo_bench.transcribe_with_segments(audio_path)
                    else:
                        structured = {}
                    segments = structured.get("segments", [])
                except Exception:
                    pass
                return {
                    "text": text,
                    "segments": segments,
                    "elapsed_seconds": whisper_elapsed,
                }
            except Exception as e:
                logger.warning(f"Benchmark Whisper (apostila) falhou: {e}")
                return None

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="bench-whisper-apost")
        future = executor.submit(_run)
        executor.shutdown(wait=False)
        return future

    def _finalize_hearing_benchmark(
        self,
        aai_result: dict,
        whisper_future: concurrent.futures.Future,
        output_dir,
        video_name: str,
        audio_path: str,
    ):
        """Finaliza benchmark hearing em background: compara AAI (primário) vs Whisper."""
        def _run():
            try:
                whisper_result = whisper_future.result(timeout=600)
                if whisper_result is None:
                    logger.warning("Benchmark hearing: Whisper retornou None")
                    return

                # Calcular métricas (invertido: AAI é "local_text", Whisper é "aai")
                # Reusar compute_benchmark_metrics trocando os papéis
                report = self._compute_benchmark_metrics(
                    local_segments=aai_result.get("segments", []),
                    local_text=aai_result.get("text", ""),
                    local_elapsed=aai_result.get("elapsed_seconds", 0),
                    aai_result=whisper_result,
                    audio_path=audio_path,
                )
                # Anotar que o "primário" era AAI
                report["primary_backend"] = "assemblyai"
                report["secondary_backend"] = "local_whisper"

                out_path = Path(output_dir) if output_dir else Path("./storage/benchmarks")
                out_path.mkdir(parents=True, exist_ok=True)

                # Métricas
                benchmark_path = out_path / f"{video_name}_BENCHMARK.json"
                benchmark_path.write_text(
                    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
                )

                # Transcrição do Whisper (para comparação)
                whisper_path = out_path / f"{video_name}_WHISPER_LOCAL.json"
                whisper_path.write_text(
                    json.dumps(whisper_result, ensure_ascii=False, indent=2), encoding="utf-8"
                )

                logger.info(f"📊 Benchmark hearing salvo: {benchmark_path.name}")
                self._append_to_benchmark_log(report, video_name)

            except concurrent.futures.TimeoutError:
                logger.warning("Benchmark hearing: Whisper timeout (>10min)")
            except Exception as e:
                logger.warning(f"Benchmark hearing: erro: {e}")

        thread = threading.Thread(target=_run, name="benchmark-hearing", daemon=True)
        thread.start()

    # ==================== GERAÇÃO DE LEGENDAS (SRT/VTT) ====================

    @staticmethod
    def _format_timestamp_srt(seconds: float) -> str:
        """Formata segundos para o formato SRT: HH:MM:SS,mmm"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    @staticmethod
    def _format_timestamp_vtt(seconds: float) -> str:
        """Formata segundos para o formato WebVTT: HH:MM:SS.mmm"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"

    @staticmethod
    def _generate_srt(segments: list) -> str:
        """
        Gera conteúdo SRT a partir de segments com start/end/text/speaker_label.

        Formato SRT:
        1
        00:00:00,000 --> 00:00:03,200
        SPEAKER 1: Texto da primeira fala

        2
        00:00:03,200 --> 00:00:07,500
        SPEAKER 2: Texto da segunda fala
        """
        lines = []
        for i, seg in enumerate(segments, 1):
            start = TranscriptionService._format_timestamp_srt(seg.get("start", 0))
            end = TranscriptionService._format_timestamp_srt(seg.get("end", 0))
            speaker = seg.get("speaker_label", "")
            text = (seg.get("text", "") or "").strip()
            prefix = f"{speaker}: " if speaker else ""
            lines.append(f"{i}")
            lines.append(f"{start} --> {end}")
            lines.append(f"{prefix}{text}")
            lines.append("")  # Linha em branco entre entradas
        return "\n".join(lines)

    @staticmethod
    def _generate_vtt(segments: list) -> str:
        """
        Gera conteúdo WebVTT a partir de segments.

        Formato WebVTT:
        WEBVTT

        00:00:00.000 --> 00:00:03.200
        <v SPEAKER 1>Texto da primeira fala

        00:00:03.200 --> 00:00:07.500
        <v SPEAKER 2>Texto da segunda fala
        """
        lines = ["WEBVTT", ""]
        for seg in segments:
            start = TranscriptionService._format_timestamp_vtt(seg.get("start", 0))
            end = TranscriptionService._format_timestamp_vtt(seg.get("end", 0))
            speaker = seg.get("speaker_label", "")
            text = (seg.get("text", "") or "").strip()
            voice_tag = f"<v {speaker}>" if speaker else ""
            lines.append(f"{start} --> {end}")
            lines.append(f"{voice_tag}{text}")
            lines.append("")  # Linha em branco entre entradas
        return "\n".join(lines)

    def _persist_transcription_outputs(
        self,
        video_name: str,
        mode: str,
        raw_text: str,
        formatted_text: str,
        analysis_report: Optional[dict] = None,
        validation_report: Optional[dict] = None,
        segments: Optional[list] = None,
        subtitle_format: Optional[str] = None,
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

        result = {
            "output_dir": str(output_dir),
            "raw_path": str(raw_path),
            "md_path": str(md_path),
            "analysis_path": str(analysis_path) if analysis_report else None,
            "validation_path": str(validation_path) if validation_report else None,
            "audit_path": str(audit_path) if audit_report else None,
        }

        # Salvar segments e legendas (SRT/VTT) se disponíveis
        if segments and subtitle_format:
            # Salvar segments brutos como JSON
            segments_path = output_dir / f"{video_name}_segments.json"
            segments_path.write_text(json.dumps(segments, ensure_ascii=False, indent=2), encoding="utf-8")
            result["segments_path"] = str(segments_path)

            # Gerar e salvar SRT
            if subtitle_format in ("srt", "both"):
                srt_path = output_dir / f"{video_name}.srt"
                srt_content = self._generate_srt(segments)
                srt_path.write_text(srt_content, encoding="utf-8")
                result["srt_path"] = str(srt_path)
                logger.info(f"📝 Legenda SRT gerada: {srt_path.name}")

            # Gerar e salvar VTT
            if subtitle_format in ("vtt", "both"):
                vtt_path = output_dir / f"{video_name}.vtt"
                vtt_content = self._generate_vtt(segments)
                vtt_path.write_text(vtt_content, encoding="utf-8")
                result["vtt_path"] = str(vtt_path)
                logger.info(f"📝 Legenda VTT gerada: {vtt_path.name}")

        return result

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
            "title_drift_path": f"{video_name}_{mode_suffix}_TITLE_DRIFT.json",
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

    def _load_title_drift_telemetry(self, report_paths: Optional[dict]) -> dict:
        if not isinstance(report_paths, dict):
            return {}
        drift_path = report_paths.get("title_drift_path")
        if not drift_path:
            return {}
        try:
            path = Path(drift_path)
            if not path.exists():
                return {}
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {
                    "headers_changed_count": int(data.get("headers_changed_count") or 0),
                    "headers_restored_count": int(data.get("headers_restored_count") or 0),
                    "headers_degraded_count": int(data.get("headers_degraded_count") or 0),
                    "headers_diff": data.get("headers_diff") or [],
                }
        except Exception as exc:
            logger.warning(f"Falha ao carregar telemetria de drift de títulos: {exc}")
        return {}

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

    async def _transcribe_with_progress_stream(
        self,
        vomo,
        audio_path: str,
        emit: Callable[[str, int, str], Awaitable[None]],
        start_progress: int,
        end_progress: int,
        mode: str = "APOSTILA",
        high_accuracy: bool = False,
        diarization: Optional[bool] = None,
        diarization_strict: bool = False,
        language: Optional[str] = None,
    ) -> dict:
        """
        Transcreve áudio com progresso baseado em tempo estimado.
        Emite atualizações periódicas de progresso para a UI.

        Returns:
            dict: {"text": str, "words": list} para suporte a timestamps por palavra
        """
        # Estimar duração do áudio para calcular progresso
        audio_duration = self._get_wav_duration_seconds(audio_path)
        # MLX Whisper processa ~1x tempo real em M1/M2, ~0.5x em M3
        estimated_processing_time = audio_duration * 0.8 if audio_duration > 0 else 300

        # Timeout defensivo: evita jobs eternamente "running" quando Whisper trava.
        # 0 = desabilita.
        default_timeout = min(8 * 3600, max(1800, int(estimated_processing_time * 2.5)))
        try:
            whisper_timeout_seconds = int(os.getenv("IUDEX_WHISPER_TIMEOUT_SECONDS", str(default_timeout)))
        except Exception:
            whisper_timeout_seconds = default_timeout

        # Rodar transcrição em processo separado para permitir terminate em travamentos.
        import multiprocessing
        import tempfile

        ctx = multiprocessing.get_context("spawn")
        tmp_out = tempfile.NamedTemporaryFile(prefix="iudex_whisper_", suffix=".json", delete=False)
        out_path = tmp_out.name
        tmp_out.close()
        proc = ctx.Process(
            target=_whisper_transcribe_worker,
            kwargs={
                "out_path": out_path,
                "audio_path": audio_path,
                "mode": mode,
                "high_accuracy": high_accuracy,
                "diarization": diarization,
                "diarization_strict": diarization_strict,
                "language": language,
            },
        )
        proc.start()

        start_time = time.time()
        last_progress = start_progress
        last_emit_time = 0.0
        progress_range = end_progress - start_progress
        try:
            heartbeat_every = float(os.getenv("IUDEX_PROGRESS_HEARTBEAT_SECONDS", "12"))
        except Exception:
            heartbeat_every = 12.0

        # Emitir progresso periódico baseado em tempo
        while proc.is_alive():
            elapsed = time.time() - start_time

            # Calcular progresso estimado (máx 95% até terminar)
            if estimated_processing_time > 0:
                estimated_pct = min(95, int((elapsed / estimated_processing_time) * 100))
            else:
                # Progresso lento se não souber duração
                estimated_pct = min(95, int(elapsed / 10))  # 10% a cada 10s

            # Mapear para range de progresso
            current_progress = start_progress + int((estimated_pct / 100) * progress_range)
            now = time.time()

            should_emit = False
            if current_progress > last_progress:
                last_progress = current_progress
                should_emit = True
            elif heartbeat_every > 0 and (now - last_emit_time) >= heartbeat_every:
                # Heartbeat: mantém a UI viva mesmo quando o progresso "estaciona"
                should_emit = True

            if should_emit:
                elapsed_str = f"{int(elapsed // 60)}m{int(elapsed % 60):02d}s"

                # Estimar tempo restante
                if estimated_pct > 0:
                    eta = (elapsed / estimated_pct) * (100 - estimated_pct)
                    eta_str = f"{int(eta // 60)}m{int(eta % 60):02d}s"
                else:
                    eta_str = "calculando..."

                await emit(
                    "transcription",
                    int(current_progress),
                    f"🎙️ Transcrevendo... {estimated_pct}% [{elapsed_str} / ~{eta_str}]"
                )
                last_emit_time = now

            if whisper_timeout_seconds and whisper_timeout_seconds > 0 and elapsed >= whisper_timeout_seconds:
                try:
                    proc.terminate()
                except Exception:
                    pass
                try:
                    proc.join(timeout=10)
                except Exception:
                    pass
                raise TimeoutError(
                    f"Whisper timeout após {int(elapsed)}s (limite={whisper_timeout_seconds}s)"
                )

            # Aguardar 3 segundos SEM BLOQUEAR o event loop (fix: usar asyncio.sleep em vez de done_event.wait)
            await asyncio.sleep(3.0)

        proc.join(timeout=10)

        # Emitir progresso final
        total_time = time.time() - start_time
        total_str = f"{int(total_time // 60)}m{int(total_time % 60):02d}s"
        await emit(
            "transcription",
            end_progress - 1,
            f"🎙️ Transcrição finalizada em {total_str}"
        )

        try:
            if proc.exitcode not in (0, None):
                raise RuntimeError(f"Whisper worker exitcode={proc.exitcode}")
            if not os.path.exists(out_path):
                raise RuntimeError("Whisper worker não gerou arquivo de saída")
            payload = json.loads(Path(out_path).read_text(encoding="utf-8", errors="ignore") or "{}")
            if not payload.get("ok"):
                err = (payload.get("error") or {}).get("message") or "Whisper worker falhou"
                raise RuntimeError(err)
            result = payload.get("result") or {}
            return {
                "text": result.get("text") or "",
                "words": result.get("words") or [],
                "segments": result.get("segments") or [],
                "_needs_external_diarization": result.get("_needs_external_diarization", False),
            }
        finally:
            try:
                os.unlink(out_path)
            except Exception:
                pass

    async def _transcribe_whisper_with_optional_external_diarization(
        self,
        *,
        vomo,
        audio_path: str,
        mode: str,
        high_accuracy: bool,
        diarization: Optional[bool],
        diarization_strict: bool,
        language: Optional[str],
        diarization_enabled: bool,
        diarization_required: bool,
        diarization_provider: Optional[str],
        speakers_expected: Optional[int] = None,
        speaker_roles: Optional[list] = None,
        speaker_id_type: Optional[str] = None,
        speaker_id_values: Optional[list] = None,
        emit: Optional[Callable[[str, int, str], Awaitable[None]]] = None,
    ) -> dict:
        """
        Executa Whisper (full result) e, quando necessário, aplica diarização externa.
        """
        result = await asyncio.to_thread(
            vomo.transcribe_file_full,
            audio_path,
            mode=mode,
            high_accuracy=high_accuracy,
            diarization=diarization,
            diarization_strict=diarization_strict,
            language=language,
        )
        if not isinstance(result, dict):
            result = {"text": str(result or ""), "words": [], "segments": []}

        words, segments = await self._apply_external_diarization_if_needed(
            transcription_result=result,
            diarization_enabled=diarization_enabled,
            diarization_required=diarization_required,
            diarization_provider=diarization_provider,
            audio_path=audio_path,
            speakers_expected=speakers_expected,
            speaker_roles=speaker_roles,
            language=language,
            mode=mode,
            speaker_id_type=speaker_id_type,
            speaker_id_values=speaker_id_values,
            emit=emit,
        )
        result["words"] = words
        result["segments"] = segments
        return {
            "text": result.get("text") or "",
            "words": result.get("words") or [],
            "segments": result.get("segments") or [],
            "_needs_external_diarization": bool(result.get("_needs_external_diarization")),
        }

    async def process_file(
        self,
        file_path: str,
        mode: str = "APOSTILA",
        thinking_level: str = "medium",
        custom_prompt: Optional[str] = None,
        high_accuracy: bool = False,
        transcription_engine: str = "whisper",
        diarization: Optional[bool] = None,
        diarization_strict: bool = False,
        model_selection: Optional[str] = None,
        use_cache: bool = True,
        auto_apply_fixes: bool = True,
        auto_apply_content_fixes: bool = False,
        skip_legal_audit: bool = False,
        skip_audit: Optional[bool] = None,
        skip_fidelity_audit: bool = False,
        skip_sources_audit: bool = False,
        language: Optional[str] = None,
        output_language: Optional[str] = None,
        speaker_roles: Optional[list] = None,
        speakers_expected: Optional[int] = None,
        subtitle_format: Optional[str] = None,
        area: Optional[str] = None,
        custom_keyterms: Optional[list] = None,
        allow_provider_fallback: Optional[bool] = None,
        diarization_provider: Optional[str] = None,
    ) -> str:
        """
        Processa um arquivo de áudio/vídeo usando MLX Vomo.

        Reflexo do fluxo main() do script original, mas adaptado para serviço.
        """
        try:
            if skip_audit is not None:
                skip_legal_audit = skip_legal_audit or skip_audit
            allow_provider_fallback = self._enforce_fidelity_critical_fallback(
                mode=mode,
                allow_provider_fallback=allow_provider_fallback,
            )
            apply_fixes = auto_apply_fixes
            vomo = self._get_vomo(model_selection=model_selection, thinking_level=thinking_level)
            vomo._current_language = (language or "pt").strip().lower()
            vomo._output_language = (output_language or "").strip().lower() or None
            vomo._current_mode = (mode or "APOSTILA").strip().upper()
            logger.info(f"🎤 Iniciando processamento Vomo: {file_path} [{mode}] [lang={vomo._current_language}]")
            diarization_enabled, diarization_required = (False, False)
            try:
                diarization_enabled, diarization_required = vomo.resolve_diarization_policy(
                    mode, diarization=diarization, diarization_strict=diarization_strict
                )
            except Exception:
                pass
            diarization_provider = self._normalize_diarization_provider(diarization_provider)

            file_ext = Path(file_path).suffix.lower()
            is_text_input = file_ext in [".txt", ".md"]
            transcription_text = None
            transcription_words: list = []
            transcription_segments: list = []
            cache_hash = None
            _benchmark_future = None
            _local_segments = None
            _whisper_elapsed = 0.0
            _requested_engine_cache = (transcription_engine or "whisper").strip().lower()
            _skip_raw_cache = (
                (mode or "").upper() == "RAW"
                and not is_text_input
                and _requested_engine_cache in {"assemblyai", "elevenlabs", "runpod"}
            )
            if use_cache and not _skip_raw_cache:
                cache_hash = self._compute_file_hash(file_path)
                transcription_text = self._load_cached_raw(cache_hash, high_accuracy, diarization_enabled)
            elif use_cache and _skip_raw_cache:
                logger.info("RAW + provider cloud: cache de texto desabilitado para preservar words/segments")

            if transcription_text:
                logger.info("♻️ RAW cache hit (pulando transcrição)")
            else:
                if is_text_input:
                    transcription_text = Path(file_path).read_text(encoding="utf-8", errors="ignore")
                else:
                    # 1. Otimizar Áudio (Extrair se for vídeo)
                    audio_path = vomo.optimize_audio(file_path)

                    # 2. Transcrever
                    if diarization_enabled:
                        logger.info(
                            "🗣️  Diarização habilitada (%s, provider=%s)",
                            "strict" if diarization_required else "soft",
                            diarization_provider,
                        )
                    if high_accuracy:
                        logger.info("🎯 Usando Beam Search (High Accuracy)")

                    # Modo ElevenLabs primário: selecionado via frontend OU (legenda + key disponível se não especificou outro)
                    _engine_elevenlabs = transcription_engine == "elevenlabs"
                    _elevenlabs_primary = (
                        _engine_elevenlabs
                        and self._get_elevenlabs_key()
                    )

                    # Modo AAI primário: diarização + speaker_roles + AAI key
                    # NOTA: Para APOSTILA/FIDELIDADE (aulas), Whisper é primário por padrão
                    # Mas pode ser forçado AAI via ASSEMBLYAI_PRIMARY=true (não exige speaker_roles)
                    # OU via transcription_engine="assemblyai" no frontend
                    _mode_upper = (mode or "APOSTILA").upper()
                    _force_aai = self._is_assemblyai_primary_forced()
                    _engine_aai = transcription_engine == "assemblyai"
                    _engine_whisper = transcription_engine == "whisper"
                    _force_aai_effective = _force_aai and not _engine_whisper
                    _aai_primary = (
                        not _elevenlabs_primary
                        and self._get_assemblyai_key()
                        and (
                            _engine_aai  # Selecionado via frontend
                            or _force_aai_effective  # Forçado via env (exceto quando Whisper explícito)
                            or (
                                not _engine_whisper
                                and
                                _mode_upper not in ("APOSTILA", "FIDELIDADE")
                                and diarization_enabled
                                and speaker_roles
                            )
                        )
                    )
                    _requested_engine = (transcription_engine or "whisper").strip().lower()
                    if _requested_engine in {"assemblyai", "elevenlabs"} and not _elevenlabs_primary and not _aai_primary:
                        _can_switch_missing_provider = self._is_provider_fallback_allowed(
                            requested_engine=transcription_engine,
                            from_provider=_requested_engine,
                            to_provider="whisper",
                            allow_provider_fallback=allow_provider_fallback,
                        )
                        if not _can_switch_missing_provider:
                            raise RuntimeError(
                                f"{_requested_engine} indisponível e fallback para Whisper foi desabilitado."
                            )
                        logger.warning(
                            self._provider_switch_message(
                                from_provider=_requested_engine,
                                to_provider="whisper",
                                allow_provider_fallback=allow_provider_fallback,
                            )
                        )

                    if _elevenlabs_primary:
                        logger.info("🎬 ElevenLabs primário para legendas")
                        _el_start = time.time()
                        el_result = None
                        try:
                            el_result = self._transcribe_elevenlabs_scribe(
                                audio_path=audio_path,
                                language=language or "pt",
                                diarize=True,
                                tag_audio_events=True,
                            )
                        except Exception as el_exc:
                            logger.warning("ElevenLabs falhou: %s", el_exc)

                        if el_result:
                            # Usar texto com timestamps se disponível (como Whisper faz)
                            transcription_text = el_result.get("text_with_timestamps") or el_result["text"]
                            transcription_words = el_result.get("words", []) or []
                            transcription_segments = el_result.get("segments", []) or []
                            _whisper_elapsed = time.time() - _el_start
                            self._elevenlabs_result = el_result
                            self._aai_apostila_result = None
                        elif self._get_assemblyai_key():
                            _can_eleven_to_aai = self._is_provider_fallback_allowed(
                                requested_engine=transcription_engine,
                                from_provider="elevenlabs",
                                to_provider="assemblyai",
                                allow_provider_fallback=allow_provider_fallback,
                            )
                            if not _can_eleven_to_aai:
                                raise RuntimeError(
                                    "ElevenLabs indisponível e fallback para AssemblyAI foi desabilitado."
                                )
                            # Fallback: AssemblyAI (em thread separada para não bloquear)
                            logger.warning(
                                self._provider_switch_message(
                                    from_provider="elevenlabs",
                                    to_provider="assemblyai",
                                    allow_provider_fallback=allow_provider_fallback,
                                )
                            )
                            aai_result = await asyncio.to_thread(
                                self._transcribe_assemblyai_with_roles,
                                audio_path, None, language or "pt", None, mode,
                            )
                            if aai_result:
                                # Usar texto com timestamps se disponível
                                transcription_text = aai_result.get("text_with_timestamps") or aai_result["text"]
                                transcription_words = aai_result.get("words", []) or []
                                transcription_segments = aai_result.get("segments", []) or []
                                self._aai_apostila_result = aai_result
                                self._elevenlabs_result = None
                            else:
                                _can_aai_to_whisper = self._is_provider_fallback_allowed(
                                    requested_engine=transcription_engine,
                                    from_provider="assemblyai",
                                    to_provider="whisper",
                                    allow_provider_fallback=allow_provider_fallback,
                                )
                                if not _can_aai_to_whisper:
                                    raise RuntimeError(
                                        "AssemblyAI indisponível após fallback e troca para Whisper foi desabilitada."
                                    )
                                # Fallback final: Whisper
                                logger.warning(
                                    self._provider_switch_message(
                                        from_provider="assemblyai",
                                        to_provider="whisper",
                                        allow_provider_fallback=allow_provider_fallback,
                                    )
                                )
                                whisper_result = await self._transcribe_whisper_with_optional_external_diarization(
                                    vomo=vomo,
                                    audio_path=audio_path,
                                    mode=mode,
                                    high_accuracy=high_accuracy,
                                    diarization=diarization,
                                    diarization_strict=diarization_strict,
                                    language=language,
                                    diarization_enabled=diarization_enabled,
                                    diarization_required=diarization_required,
                                    diarization_provider=diarization_provider,
                                    speakers_expected=speakers_expected,
                                    speaker_roles=speaker_roles,
                                )
                                transcription_text = whisper_result.get("text", "")
                                transcription_words = whisper_result.get("words", [])
                                transcription_segments = whisper_result.get("segments", [])
                                self._aai_apostila_result = None
                                self._elevenlabs_result = None
                        else:
                            _can_eleven_to_whisper = self._is_provider_fallback_allowed(
                                requested_engine=transcription_engine,
                                from_provider="elevenlabs",
                                to_provider="whisper",
                                allow_provider_fallback=allow_provider_fallback,
                            )
                            if not _can_eleven_to_whisper:
                                raise RuntimeError(
                                    "ElevenLabs indisponível e fallback para Whisper foi desabilitado."
                                )
                            # Fallback: Whisper
                            logger.warning(
                                self._provider_switch_message(
                                    from_provider="elevenlabs",
                                    to_provider="whisper",
                                    allow_provider_fallback=allow_provider_fallback,
                                )
                            )
                            whisper_result = await self._transcribe_whisper_with_optional_external_diarization(
                                vomo=vomo,
                                audio_path=audio_path,
                                mode=mode,
                                high_accuracy=high_accuracy,
                                diarization=diarization,
                                diarization_strict=diarization_strict,
                                language=language,
                                diarization_enabled=diarization_enabled,
                                diarization_required=diarization_required,
                                diarization_provider=diarization_provider,
                                speakers_expected=speakers_expected,
                                speaker_roles=speaker_roles,
                            )
                            transcription_text = whisper_result.get("text", "")
                            transcription_words = whisper_result.get("words", [])
                            transcription_segments = whisper_result.get("segments", [])
                            self._aai_apostila_result = None
                            self._elevenlabs_result = None

                    elif _aai_primary:
                        logger.info("🗣️ AAI primário (audiência/reunião) com roles: %s", speaker_roles)

                        # Disparar Whisper em paralelo para benchmark
                        if self._is_benchmark_enabled():
                            logger.info("📊 Benchmark Whisper em paralelo (AAI primário)")
                            _benchmark_future = self._start_whisper_benchmark_for_apostila(
                                audio_path, mode, high_accuracy, diarization,
                                diarization_strict, language,
                            )

                        _aai_start = time.time()
                        aai_result = None
                        try:
                            # Rodar em thread separada para não bloquear o event loop
                            aai_result = await asyncio.to_thread(
                                self._transcribe_assemblyai_with_roles,
                                audio_path, speaker_roles, language or "pt", speakers_expected, mode,
                            )
                        except Exception as aai_exc:
                            logger.warning("AssemblyAI falhou (audiência/reunião), usando Whisper: %s", aai_exc)

                        if aai_result:
                            # Usar texto com timestamps se disponível (como Whisper faz)
                            transcription_text = aai_result.get("text_with_timestamps") or aai_result["text"]
                            transcription_words = aai_result.get("words", []) or []
                            transcription_segments = aai_result.get("segments", []) or []
                            _whisper_elapsed = time.time() - _aai_start
                            # Salvar artefatos AAI (serão colocados no output_dir após persist)
                            self._aai_apostila_result = aai_result
                        else:
                            _can_aai_to_whisper = self._is_provider_fallback_allowed(
                                requested_engine=transcription_engine,
                                from_provider="assemblyai",
                                to_provider="whisper",
                                allow_provider_fallback=allow_provider_fallback,
                            )
                            if not _can_aai_to_whisper:
                                raise RuntimeError(
                                    "AssemblyAI indisponível e fallback para Whisper foi desabilitado."
                                )
                            # Fallback: Whisper local
                            logger.warning(
                                self._provider_switch_message(
                                    from_provider="assemblyai",
                                    to_provider="whisper",
                                    allow_provider_fallback=allow_provider_fallback,
                                )
                            )
                            _whisper_start = time.time()
                            whisper_result = await self._transcribe_whisper_with_optional_external_diarization(
                                vomo=vomo,
                                audio_path=audio_path,
                                mode=mode,
                                high_accuracy=high_accuracy,
                                diarization=diarization,
                                diarization_strict=diarization_strict,
                                language=language,
                                diarization_enabled=diarization_enabled,
                                diarization_required=diarization_required,
                                diarization_provider=diarization_provider,
                                speakers_expected=speakers_expected,
                                speaker_roles=speaker_roles,
                            )
                            transcription_text = whisper_result.get("text", "")
                            transcription_words = whisper_result.get("words", [])
                            transcription_segments = whisper_result.get("segments", [])
                            _whisper_elapsed = time.time() - _whisper_start
                            self._aai_apostila_result = None
                    else:
                        # Fluxo padrão: Whisper primário
                        self._aai_apostila_result = None

                        # Benchmark: dispara AssemblyAI em paralelo se habilitado
                        _benchmark_future = None
                        if self._is_benchmark_enabled():
                            logger.info("📊 Benchmark AssemblyAI habilitado — disparando em paralelo")
                            # Usa area fornecida, ou default "juridico" para modos AUDIENCIA/DEPOIMENTO
                            _effective_area = area or ("juridico" if mode and mode.upper() in ("AUDIENCIA", "DEPOIMENTO") else None)
                            _benchmark_future = self._start_assemblyai_benchmark(
                                audio_path,
                                language=language,
                                area=_effective_area,
                                custom_keyterms=custom_keyterms,
                            )

                        _whisper_start = time.time()
                        whisper_result = await self._transcribe_whisper_with_optional_external_diarization(
                            vomo=vomo,
                            audio_path=audio_path,
                            mode=mode,
                            high_accuracy=high_accuracy,
                            diarization=diarization,
                            diarization_strict=diarization_strict,
                            language=language,
                            diarization_enabled=diarization_enabled,
                            diarization_required=diarization_required,
                            diarization_provider=diarization_provider,
                            speakers_expected=speakers_expected,
                            speaker_roles=speaker_roles,
                        )
                        transcription_text = whisper_result.get("text", "")
                        transcription_words = whisper_result.get("words", [])
                        transcription_segments = whisper_result.get("segments", [])
                        _whisper_elapsed = time.time() - _whisper_start

                        # Capturar segmentos locais para benchmark (usa cache do VomoMLX)
                        _local_segments = None
                        if _benchmark_future is not None:
                            try:
                                _local_segments = self._extract_local_segments(vomo, audio_path, high_accuracy)
                            except Exception as seg_exc:
                                logger.warning(f"Benchmark: falha ao extrair segmentos locais: {seg_exc}")
                if use_cache and cache_hash:
                    self._save_cached_raw(
                        cache_hash,
                        high_accuracy,
                        diarization_enabled,
                        transcription_text,
                        Path(file_path).name,
                    )
            
            if mode == "RAW":
                _raw_result: Dict[str, Any] = {
                    "content": transcription_text,
                    "raw_content": transcription_text,
                    "reports": {},
                }
                if transcription_words:
                    _raw_result["words"] = transcription_words
                if transcription_segments:
                    _raw_result["segments"] = transcription_segments
                return _raw_result

            # 3. Formatar (LLM)
            if vomo is None:
                logger.warning("⚠️ Vomo ausente antes da formatação em process_file — fallback sync")
                vomo = self._get_vomo(model_selection=model_selection, thinking_level=thinking_level)
                if vomo is None:
                    raise RuntimeError("Motor de formatação indisponível (VomoMLX não inicializado).")
                vomo._current_language = (language or "pt").strip().lower()
                vomo._output_language = (output_language or "").strip().lower() or None
                vomo._current_mode = (mode or "APOSTILA").strip().upper()

            # Observação: em `mlx_vomo.py`, `custom_prompt` tem comportamento dependente do modo:
            # - APOSTILA/AUDIENCIA/REUNIAO: personaliza apenas tabelas/extras (preserva tom/estilo/estrutura do modo).
            # - Outros modos: substitui STYLE+TABLE (preserva HEAD/STRUCTURE/FOOTER).
            # Para manter paridade com o CLI/UI, só enviamos `custom_prompt` quando o usuário fornece.
            system_prompt = (custom_prompt or "").strip() or None
            
            # Mapear thinking_level para tokens (simplificado)
            # O script original usa thinking_budget int
            # Executar formatação
            # Definir folder temporário para outputs intermediários
            import tempfile
            from pathlib import Path
            
            video_name = Path(file_path).stem
            mode_suffix = mode.upper() if mode else "APOSTILA"
            report_paths = {}
            with tempfile.TemporaryDirectory() as temp_dir:
                llm_warning: Optional[str] = None
                table_recovery_meta: Optional[dict] = None
                try:
                    final_text, vomo = await self._run_llm_format_with_resilience(
                        vomo=vomo,
                        source_text=transcription_text,
                        video_name=video_name,
                        output_folder=temp_dir,
                        mode=mode,
                        custom_prompt=system_prompt,
                        disable_tables=False,
                        progress_callback=None,
                        skip_audit=skip_legal_audit,
                        skip_fidelity_audit=skip_fidelity_audit,
                        skip_sources_audit=skip_sources_audit,
                        model_selection=model_selection,
                        thinking_level=thinking_level,
                    )

                    try:
                        mode_upper = (mode or 'APOSTILA').strip().upper()
                        raw_words = len(re.findall(r'\S+', transcription_text or ''))
                        def _has_md_table(markdown_text: str) -> bool:
                            lines_md = (markdown_text or '').splitlines()
                            sep_pattern = re.compile(r'^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$')
                            for idx_line in range(len(lines_md) - 1):
                                header = lines_md[idx_line].strip()
                                sep = lines_md[idx_line + 1].strip()
                                if '|' not in header or '|' not in sep:
                                    continue
                                if header.count('|') < 2:
                                    continue
                                if sep_pattern.match(sep):
                                    return True
                            return False
                        has_table = _has_md_table(final_text or '')

                        if mode_upper in {'APOSTILA', 'FIDELIDADE'} and not has_table and raw_words >= 1200:
                            preventive_path = Path(temp_dir) / f'{video_name}_{mode_upper}_AUDITORIA_FIDELIDADE.json'
                            retention_ratio = None
                            fidelity_score = None
                            if preventive_path.exists():
                                try:
                                    payload = json.loads(preventive_path.read_text(encoding='utf-8', errors='ignore') or '{}')
                                    if isinstance(payload, dict):
                                        metricas = payload.get('metricas') if isinstance(payload.get('metricas'), dict) else {}
                                        if metricas.get('taxa_retencao') is not None:
                                            retention_ratio = float(metricas.get('taxa_retencao'))
                                        elif payload.get('taxa_compressao_estimada') is not None:
                                            compressao = float(payload.get('taxa_compressao_estimada'))
                                            if compressao > 1:
                                                compressao = compressao / 100.0
                                            if 0 <= compressao <= 1:
                                                retention_ratio = 1.0 - compressao
                                        if payload.get('nota_fidelidade') is not None:
                                            fidelity_score = float(payload.get('nota_fidelidade'))
                                except Exception:
                                    retention_ratio = None

                            if retention_ratio is None:
                                fmt_words = len(re.findall(r'\S+', final_text or ''))
                                retention_ratio = (fmt_words / raw_words) if raw_words > 0 else None

                            low_retention = retention_ratio is not None and retention_ratio < 0.60
                            low_score = fidelity_score is not None and fidelity_score <= 6.0

                            if low_retention or low_score:
                                table_recovery_meta = {
                                    'triggered': True,
                                    'reason': 'missing_tables_with_content_loss',
                                    'retention_ratio': retention_ratio,
                                    'fidelity_score': fidelity_score,
                                    'mode': mode_upper,
                                }
                                retry_prompt = ((system_prompt.strip() + '\n\n') if system_prompt and system_prompt.strip() else '') + (
                                    'MODO DE RECUPERACAO AUTOMATICA DE TABELAS\n'
                                    '- Preserve fidelidade ao RAW.\n'
                                    '- Reintroduza tabelas markdown quando houver comparacao de itens.\n'
                                    '- Nao invente fatos.'
                                )
                                recovered_text = await vomo.format_transcription_async(
                                    transcription_text,
                                    video_name=video_name,
                                    output_folder=temp_dir,
                                    mode=mode,
                                    custom_prompt=retry_prompt,
                                    disable_tables=False,
                                    skip_audit=skip_legal_audit,
                                    skip_fidelity_audit=skip_fidelity_audit,
                                    skip_sources_audit=skip_sources_audit,
                                )
                                recovered_has_table = _has_md_table(recovered_text or '')
                                rec_words = len(re.findall(r'\S+', recovered_text or ''))
                                recovered_retention = (rec_words / raw_words) if raw_words > 0 else None
                                retention_gain = (
                                    (recovered_retention - retention_ratio)
                                    if (retention_ratio is not None and recovered_retention is not None)
                                    else 0.0
                                )
                                if recovered_has_table or retention_gain >= 0.08:
                                    final_text = recovered_text
                                    table_recovery_meta['applied'] = True
                                else:
                                    table_recovery_meta['applied'] = False
                                table_recovery_meta['recovered_has_table'] = recovered_has_table
                                table_recovery_meta['recovered_retention_ratio'] = recovered_retention
                    except Exception as table_recovery_err:
                        logger.warning(f'Falha na recuperacao automatica de tabelas: {table_recovery_err}')
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
                                    model_selection=model_selection,
                                    mode=mode,
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

                # Coletar segments para legendas (ElevenLabs > AAI > Whisper)
                _segments_for_subtitles = None
                if subtitle_format:
                    el_result = getattr(self, "_elevenlabs_result", None)
                    aai_apostila = getattr(self, "_aai_apostila_result", None)
                    if el_result and el_result.get("segments"):
                        _segments_for_subtitles = el_result["segments"]
                        logger.info(f"📝 Usando {len(_segments_for_subtitles)} segments do ElevenLabs para legendas")
                    elif aai_apostila and aai_apostila.get("segments"):
                        _segments_for_subtitles = aai_apostila["segments"]
                        logger.info(f"📝 Usando {len(_segments_for_subtitles)} segments do AssemblyAI para legendas")
                    elif _local_segments:
                        _segments_for_subtitles = _local_segments
                        logger.info(f"📝 Usando {len(_segments_for_subtitles)} segments do Whisper para legendas")

                report_paths = self._persist_transcription_outputs(
                    video_name=video_name,
                    mode=mode,
                    raw_text=transcription_text,
                    formatted_text=final_text,
                    analysis_report=analysis_report,
                    validation_report=validation_report,
                    segments=_segments_for_subtitles,
                    subtitle_format=subtitle_format,
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
                if table_recovery_meta:
                    report_paths['table_recovery'] = table_recovery_meta
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

                title_drift = self._load_title_drift_telemetry(report_paths)

            # Benchmark: finalizar comparação em background (não bloqueia retorno)
            _benchmark_output_dir = report_paths.get("output_dir") if report_paths else None

            if not is_text_input and getattr(self, "_aai_apostila_result", None) and _benchmark_future is not None:
                # AAI primário: comparar com Whisper (benchmark invertido)
                self._finalize_hearing_benchmark(
                    aai_result=self._aai_apostila_result,
                    whisper_future=_benchmark_future,
                    output_dir=_benchmark_output_dir,
                    video_name=video_name,
                    audio_path=audio_path,
                )
                # Salvar artefatos AAI no output_dir
                if _benchmark_output_dir:
                    try:
                        out = Path(_benchmark_output_dir)
                        aai_json_path = out / f"{video_name}_ASSEMBLYAI.json"
                        aai_txt_path = out / f"{video_name}_ASSEMBLYAI.txt"
                        aai_json_path.write_text(
                            json.dumps(self._aai_apostila_result, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                        aai_txt_path.write_text(
                            self._aai_apostila_result.get("text", ""),
                            encoding="utf-8",
                        )
                    except Exception as save_exc:
                        logger.warning(f"Falha ao salvar artefatos AAI apostila: {save_exc}")
                self._aai_apostila_result = None
            elif not is_text_input and _benchmark_future is not None and _local_segments is not None:
                # Whisper primário: comparar com AAI (benchmark normal)
                self._finalize_benchmark_async(
                    benchmark_future=_benchmark_future,
                    local_segments=_local_segments,
                    local_text=transcription_text,
                    local_elapsed=_whisper_elapsed,
                    output_dir=_benchmark_output_dir,
                    video_name=video_name,
                    audio_path=audio_path if not is_text_input else file_path,
                )

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
        disable_tables: bool = False,
        high_accuracy: bool = False,
        transcription_engine: str = "whisper",
        diarization: Optional[bool] = None,
        diarization_strict: bool = False,
        diarization_provider: Optional[str] = None,
        on_progress: Optional[Callable[[str, int, str], Awaitable[None]]] = None,
        model_selection: Optional[str] = None,
        use_cache: bool = True,
        auto_apply_fixes: bool = True,
        auto_apply_content_fixes: bool = False,
        skip_legal_audit: bool = False,
        skip_audit: Optional[bool] = None,
        skip_fidelity_audit: bool = False,
        skip_sources_audit: bool = False,
        language: Optional[str] = None,
        output_language: Optional[str] = None,
        speaker_roles: Optional[list] = None,
        speakers_expected: Optional[int] = None,
        subtitle_format: Optional[str] = None,
        area: Optional[str] = None,
        custom_keyterms: Optional[list] = None,
        speaker_id_type: Optional[str] = None,
        speaker_id_values: Optional[list] = None,
        allow_provider_fallback: Optional[bool] = None,
        job_id: Optional[str] = None,
    ) -> dict:
        """
        Process file with progress callback for SSE streaming.

        on_progress: async callable(stage: str, progress: int, message: str)
        """
        _last_registry_update = [0.0]

        async def emit(stage: str, progress: int, message: str):
            if on_progress:
                await on_progress(stage, progress, message)
            # Atualizar job registry a cada 3s para que polling reflita progresso real
            now = time.time()
            if job_id and now - _last_registry_update[0] >= 3.0:
                _last_registry_update[0] = now
                try:
                    job_manager.update_transcription_job(
                        job_id, progress=progress, stage=stage, message=message,
                    )
                except Exception:
                    pass

        title_drift: dict = {
            "headers_changed_count": 0,
            "headers_restored_count": 0,
            "headers_degraded_count": 0,
            "headers_diff": [],
        }

        try:
            if skip_audit is not None:
                skip_legal_audit = skip_legal_audit or skip_audit
            allow_provider_fallback = self._enforce_fidelity_critical_fallback(
                mode=mode,
                allow_provider_fallback=allow_provider_fallback,
            )
            apply_fixes = auto_apply_fixes

            # Determinar se AAI/RunPod é primário ANTES de inicializar vomo
            _mode_upper_early = (mode or "APOSTILA").upper()
            _requested_engine_sse = (transcription_engine or "whisper").strip().lower()
            _engine_aai_early = _requested_engine_sse == "assemblyai"
            _aai_key_available = self._get_assemblyai_key() is not None
            _use_aai_primary_early = _engine_aai_early and _aai_key_available
            _engine_runpod_early = _requested_engine_sse == "runpod"
            _use_runpod_primary_early = _engine_runpod_early and self._is_runpod_configured()
            _skip_vomo_init = _use_aai_primary_early or _use_runpod_primary_early

            # Emit progress BEFORE initializing vomo (can be slow due to Vertex AI/Gemini connection)
            await emit("initializing", 0, "🚀 Inicializando motor de transcrição...")
            if _requested_engine_sse in {"assemblyai", "elevenlabs", "runpod"}:
                _provider_available = (
                    (_requested_engine_sse == "assemblyai" and self._get_assemblyai_key() is not None)
                    or (_requested_engine_sse == "elevenlabs" and self._get_elevenlabs_key() is not None)
                    or (_requested_engine_sse == "runpod" and self._is_runpod_configured())
                )
                if not _provider_available:
                    _can_switch_missing_provider = self._is_provider_fallback_allowed(
                        requested_engine=transcription_engine,
                        from_provider=_requested_engine_sse,
                        to_provider="whisper",
                        allow_provider_fallback=allow_provider_fallback,
                    )
                    if not _can_switch_missing_provider:
                        raise RuntimeError(
                            f"{_requested_engine_sse} indisponível e fallback para Whisper foi desabilitado."
                        )
                    await emit(
                        "initializing",
                        2,
                        self._provider_switch_message(
                            from_provider=_requested_engine_sse,
                            to_provider="whisper",
                            allow_provider_fallback=allow_provider_fallback,
                        ),
                    )

            # Só inicializar VomoMLX se não for AAI/RunPod primário
            vomo = None
            if not _skip_vomo_init:
                vomo = await self._get_vomo_with_progress(
                    emit=emit,
                    model_selection=model_selection,
                    thinking_level=thinking_level,
                    ready_message="✅ Motor de transcrição pronto (Whisper)",
                )
            elif _use_runpod_primary_early:
                await emit("initializing", 2, "✅ Motor RunPod GPU selecionado")
            else:
                await emit("initializing", 2, "✅ Motor AssemblyAI selecionado")

            _current_language = (language or "pt").strip().lower()
            _output_language = (output_language or "").strip().lower() or None
            _current_mode = _mode_upper_early

            if vomo:
                vomo._current_language = _current_language
                vomo._output_language = _output_language
                vomo._current_mode = _current_mode

            async def _ensure_vomo_for_whisper_fallback():
                nonlocal vomo
                if vomo is None:
                    await emit("transcription", 36, "🔄 Inicializando Whisper para fallback...")
                    try:
                        timeout_seconds = int(os.getenv("IUDEX_VOMO_INIT_TIMEOUT_SECONDS", "240"))
                    except Exception:
                        timeout_seconds = 240

                    start_ts = time.time()
                    heartbeat_task: Optional[asyncio.Task] = None

                    async def _heartbeat():
                        while True:
                            await asyncio.sleep(6)
                            elapsed = int(time.time() - start_ts)
                            await emit("transcription", 36, f"⏳ Inicializando Whisper para fallback... ({elapsed}s)")

                    try:
                        heartbeat_task = asyncio.create_task(_heartbeat())
                        vomo = await asyncio.wait_for(
                            asyncio.to_thread(
                                self._get_vomo,
                                model_selection,
                                thinking_level,
                            ),
                            timeout=timeout_seconds,
                        )
                    except asyncio.TimeoutError as e:
                        raise RuntimeError(
                            f"Timeout ao inicializar Whisper fallback após {timeout_seconds}s."
                        ) from e
                    finally:
                        if heartbeat_task:
                            heartbeat_task.cancel()
                            with contextlib.suppress(asyncio.CancelledError):
                                await heartbeat_task
                    vomo._current_language = _current_language
                    vomo._output_language = _output_language
                    vomo._current_mode = _current_mode
                return vomo

            async def _ensure_vomo_for_formatting():
                nonlocal vomo
                if vomo is None:
                    await emit("formatting", 66, "🔄 Inicializando motor de formatação...")
                    try:
                        timeout_seconds = int(os.getenv("IUDEX_VOMO_INIT_TIMEOUT_SECONDS", "240"))
                    except Exception:
                        timeout_seconds = 240

                    start_ts = time.time()
                    heartbeat_task: Optional[asyncio.Task] = None

                    async def _heartbeat():
                        while True:
                            await asyncio.sleep(6)
                            elapsed = int(time.time() - start_ts)
                            await emit("formatting", 66, f"⏳ Inicializando motor de formatação... ({elapsed}s)")

                    try:
                        heartbeat_task = asyncio.create_task(_heartbeat())
                        vomo = await asyncio.wait_for(
                            asyncio.to_thread(
                                self._get_vomo,
                                model_selection,
                                thinking_level,
                            ),
                            timeout=timeout_seconds,
                        )
                    except asyncio.TimeoutError as e:
                        raise RuntimeError(
                            f"Timeout ao inicializar motor de formatação após {timeout_seconds}s."
                        ) from e
                    finally:
                        if heartbeat_task:
                            heartbeat_task.cancel()
                            with contextlib.suppress(asyncio.CancelledError):
                                await heartbeat_task
                    vomo._current_language = _current_language
                    vomo._output_language = _output_language
                    vomo._current_mode = _current_mode
                return vomo

            async def _run_whisper_with_external_diarization(
                whisper_engine,
                *,
                start_progress: int,
                end_progress: int,
            ) -> dict:
                result = await self._transcribe_with_progress_stream(
                    whisper_engine,
                    audio_path,
                    emit,
                    start_progress=start_progress,
                    end_progress=end_progress,
                    mode=mode,
                    high_accuracy=high_accuracy,
                    diarization=diarization,
                    diarization_strict=diarization_strict,
                    language=language,
                )
                words, segments = await self._apply_external_diarization_if_needed(
                    transcription_result=result,
                    diarization_enabled=diarization_enabled,
                    diarization_required=diarization_required,
                    diarization_provider=diarization_provider,
                    audio_path=audio_path,
                    speakers_expected=speakers_expected,
                    speaker_roles=speaker_roles,
                    language=language,
                    mode=mode,
                    speaker_id_type=speaker_id_type,
                    speaker_id_values=speaker_id_values,
                    emit=emit,
                )
                result["words"] = words
                result["segments"] = segments
                return result

            logger.info(f"🎤 Iniciando processamento Vomo com SSE: {file_path} [{mode}] [lang={_current_language}] [engine={transcription_engine}]")
            diarization_enabled, diarization_required = (False, False)
            diarization_provider = self._normalize_diarization_provider(diarization_provider)

            # Resolver política de diarização
            if vomo:
                try:
                    diarization_enabled, diarization_required = vomo.resolve_diarization_policy(
                        mode, diarization=diarization, diarization_strict=diarization_strict
                    )
                except Exception:
                    pass
            else:
                # Para AAI, diarização é habilitada se solicitada
                diarization_enabled = diarization if diarization is not None else True
                diarization_required = diarization_strict
            
            # Stage 1: Audio Optimization (0-20%)
            from pathlib import Path as PathLib
            import os as os_module
            
            file_ext = PathLib(file_path).suffix.lower()
            file_size_mb = os_module.path.getsize(file_path) / (1024 * 1024)
            is_text_input = file_ext in [".txt", ".md"]
            is_video = file_ext in ['.mp4', '.mov', '.mkv', '.avi', '.webm', '.m4v', '.wmv', '.flv']
            cache_hash = None
            transcription_text = None
            transcription_words: list = []  # Word-level timestamps para player interativo
            transcription_segments: list = []  # Segmentos temporais para fallback de visualização

            _skip_raw_cache_sse = (
                (mode or "").upper() == "RAW"
                and not is_text_input
                and _requested_engine_sse in {"assemblyai", "elevenlabs", "runpod"}
            )
            if use_cache and not _skip_raw_cache_sse:
                try:
                    cache_hash = self._compute_file_hash(file_path)
                    transcription_text = self._load_cached_raw(cache_hash, high_accuracy, diarization_enabled)
                except Exception as cache_error:
                    logger.warning(f"Falha ao carregar cache RAW: {cache_error}")
                    transcription_text = None
            elif use_cache and _skip_raw_cache_sse:
                logger.info("RAW + provider cloud (SSE): cache de texto desabilitado para preservar words/segments")

            if is_text_input:
                await emit("audio_optimization", 0, f"📄 Texto detectado ({file_ext.upper()}, {file_size_mb:.1f}MB)")
                await emit("audio_optimization", 5, "📥 Lendo arquivo de texto...")
                if transcription_text:
                    await emit("audio_optimization", 20, "♻️ Cache RAW encontrado — pulando leitura")
                else:
                    transcription_text = PathLib(file_path).read_text(encoding="utf-8", errors="ignore")
                    if use_cache and cache_hash:
                        self._save_cached_raw(
                            cache_hash,
                            high_accuracy,
                            diarization_enabled,
                            transcription_text,
                            PathLib(file_path).name,
                        )
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
                cloud_audio_prepared = False
                if transcription_text:
                    await emit("audio_optimization", 20, "♻️ Cache RAW encontrado — pulando otimização de áudio")
                else:
                    label = "Extraindo áudio (FFmpeg)" if is_video else "Otimizando áudio (FFmpeg)"
                    estimated_total = max(90.0, file_size_mb * (4.0 if is_video else 2.0))
                    done_event = asyncio.Event()
                    ticker = asyncio.create_task(
                        self._emit_progress_while_running(
                            emit,
                            done_event,
                            "audio_optimization",
                            5,
                            20,
                            label,
                            estimated_total,
                            interval_seconds=3.0,
                        )
                    )
                    try:
                        if vomo is not None:
                            audio_path = await asyncio.to_thread(vomo.optimize_audio, file_path)
                        elif self._should_extract_audio_for_cloud(file_path):
                            audio_path = await asyncio.to_thread(
                                self._extract_audio_for_cloud,
                                file_path,
                                "mp3",
                                "64k",
                            )
                            cloud_audio_prepared = True
                        else:
                            audio_path = file_path
                            cloud_audio_prepared = True
                    finally:
                        done_event.set()
                        try:
                            await ticker
                        except Exception:
                            pass
                    audio_duration = self._get_wav_duration_seconds(audio_path)
                    duration_str = f"{int(audio_duration // 60)}m{int(audio_duration % 60)}s" if audio_duration > 0 else "estimando..."
                    if cloud_audio_prepared:
                        prepared_size_mb = os.path.getsize(audio_path) / (1024 * 1024) if audio_path and os.path.exists(audio_path) else 0.0
                        await emit("audio_optimization", 20, f"✅ Áudio preparado para provider cloud ({prepared_size_mb:.0f}MB)")
                    elif is_video:
                        await emit("audio_optimization", 20, f"✅ Áudio extraído do vídeo ({duration_str})")
                    else:
                        await emit("audio_optimization", 20, f"✅ Áudio otimizado ({duration_str})")

                # Stage 2: Transcription (20-60%)
                if transcription_text:
                    await emit("transcription", 25, "♻️ RAW carregado do cache")
                    await emit("transcription", 60, "Transcrição concluída ✓")
                else:
                    audio_duration = self._get_wav_duration_seconds(audio_path)
                    if diarization_enabled:
                        logger.info(
                            "🗣️  Diarização habilitada (%s, provider=%s)",
                            "strict" if diarization_required else "soft",
                            diarization_provider,
                        )
                    if high_accuracy:
                        logger.info("🎯 Usando Beam Search (High Accuracy)")

                    # Decidir backend: ElevenLabs primário quando selecionado
                    _engine_elevenlabs_sse = _requested_engine_sse == "elevenlabs"
                    _elevenlabs_primary_sse = (
                        _engine_elevenlabs_sse
                        and self._get_elevenlabs_key()
                    )

                    # RunPod primário quando selecionado e configurado
                    _engine_runpod_sse = _requested_engine_sse == "runpod"
                    _runpod_primary_sse = _engine_runpod_sse and self._is_runpod_configured()

                    # AAI primário se diarização + roles + key (e não é legenda/aula)
                    # NOTA: Para APOSTILA/FIDELIDADE (aulas), Whisper é primário por padrão
                    # Mas pode ser forçado AAI via ASSEMBLYAI_PRIMARY=true (não exige speaker_roles)
                    # OU via transcription_engine="assemblyai" no frontend
                    _mode_upper_sse = (mode or "APOSTILA").upper()
                    _force_aai_sse = self._is_assemblyai_primary_forced()
                    _engine_aai_sse = _requested_engine_sse == "assemblyai"
                    _engine_whisper_sse = _requested_engine_sse == "whisper"
                    _force_aai_effective_sse = _force_aai_sse and not _engine_whisper_sse
                    _aai_primary_sse = (
                        not _elevenlabs_primary_sse
                        and self._get_assemblyai_key()
                        and (
                            _engine_aai_sse  # Selecionado via frontend
                            or _force_aai_effective_sse  # Forçado via env (exceto quando Whisper explícito)
                            or (
                                not _engine_whisper_sse
                                and
                                _mode_upper_sse not in ("APOSTILA", "FIDELIDADE")
                                and diarization_enabled
                                and speaker_roles
                            )
                        )
                    )

                    # Preparar áudio otimizado para cloud se AAI/ElevenLabs for primário
                    cloud_audio_path = audio_path  # Default: usa WAV existente
                    if (not cloud_audio_prepared) and (_aai_primary_sse or _elevenlabs_primary_sse) and self._should_extract_audio_for_cloud(file_path):
                        try:
                            await emit("audio_optimization", 22, "🔄 Otimizando para upload cloud (MP3)...")
                            cloud_audio_path = await asyncio.to_thread(
                                self._extract_audio_for_cloud, file_path, "mp3", "64k"
                            )
                            cloud_size_mb = os.path.getsize(cloud_audio_path) / (1024 * 1024)
                            await emit("audio_optimization", 24, f"✅ Áudio otimizado para cloud ({cloud_size_mb:.0f}MB)")
                        except Exception as cloud_extract_err:
                            logger.warning(f"Extração cloud falhou, usando WAV: {cloud_extract_err}")
                            cloud_audio_path = audio_path

                    if _elevenlabs_primary_sse:
                        await emit("transcription", 25, "🎬 Transcrevendo via ElevenLabs Scribe...")
                        done_event = asyncio.Event()
                        ticker = asyncio.create_task(
                            self._emit_progress_while_running(
                                emit, done_event, "transcription", 25, 60,
                                "Transcrevendo (ElevenLabs)",
                                audio_duration * 0.3 if audio_duration > 0 else 0.0,
                            )
                        )
                        el_result_sse = None
                        try:
                            el_result_sse = await asyncio.to_thread(
                                self._transcribe_elevenlabs_scribe,
                                cloud_audio_path,  # Usar áudio otimizado para cloud
                                language or "pt",
                                True,  # diarize
                                True,  # tag_audio_events
                            )
                        except Exception as el_exc:
                            logger.warning("ElevenLabs falhou (SSE legendas): %s", el_exc)
                        finally:
                            done_event.set()
                            try:
                                await ticker
                            except Exception:
                                pass

                        if el_result_sse:
                            transcription_text = el_result_sse["text"]
                            transcription_words = el_result_sse.get("words", [])
                            transcription_segments = el_result_sse.get("segments", [])
                            self._elevenlabs_result = el_result_sse
                            self._aai_apostila_result = None
                            await emit("transcription", 60, "Transcrição ElevenLabs concluída ✓")
                        elif self._get_assemblyai_key():
                            _can_eleven_to_aai_sse = self._is_provider_fallback_allowed(
                                requested_engine=transcription_engine,
                                from_provider="elevenlabs",
                                to_provider="assemblyai",
                                allow_provider_fallback=allow_provider_fallback,
                            )
                            if not _can_eleven_to_aai_sse:
                                raise RuntimeError(
                                    "ElevenLabs indisponível e fallback para AssemblyAI foi desabilitado."
                                )
                            # Fallback AAI
                            await emit(
                                "transcription",
                                35,
                                self._provider_switch_message(
                                    from_provider="elevenlabs",
                                    to_provider="assemblyai",
                                    allow_provider_fallback=allow_provider_fallback,
                                ),
                            )
                            aai_result_fallback = await asyncio.to_thread(
                                self._transcribe_assemblyai_with_roles,
                                cloud_audio_path, None, language or "pt", None, mode,  # Usar áudio otimizado
                            )
                            if aai_result_fallback:
                                transcription_text = aai_result_fallback.get("text_with_timestamps") or aai_result_fallback["text"]
                                transcription_words = aai_result_fallback.get("words", [])
                                transcription_segments = aai_result_fallback.get("segments", [])
                                self._aai_apostila_result = aai_result_fallback
                                self._elevenlabs_result = None
                                await emit("transcription", 60, "Transcrição AssemblyAI concluída ✓")
                            else:
                                _can_aai_to_whisper_sse = self._is_provider_fallback_allowed(
                                    requested_engine=transcription_engine,
                                    from_provider="assemblyai",
                                    to_provider="whisper",
                                    allow_provider_fallback=allow_provider_fallback,
                                )
                                if not _can_aai_to_whisper_sse:
                                    raise RuntimeError(
                                        "AssemblyAI indisponível após fallback e troca para Whisper foi desabilitada."
                                    )
                                # Fallback Whisper
                                await emit(
                                    "transcription",
                                    40,
                                    self._provider_switch_message(
                                        from_provider="assemblyai",
                                        to_provider="whisper",
                                        allow_provider_fallback=allow_provider_fallback,
                                    ),
                                )
                                whisper_vomo = await _ensure_vomo_for_whisper_fallback()
                                whisper_result = await _run_whisper_with_external_diarization(
                                    whisper_vomo,
                                    start_progress=40,
                                    end_progress=60,
                                )
                                transcription_text = whisper_result.get("text", "")
                                transcription_words = whisper_result.get("words", [])
                                transcription_segments = whisper_result.get("segments", [])
                                self._aai_apostila_result = None
                                self._elevenlabs_result = None
                                await emit("transcription", 60, "Transcrição Whisper concluída ✓")
                        else:
                            _can_eleven_to_whisper_sse = self._is_provider_fallback_allowed(
                                requested_engine=transcription_engine,
                                from_provider="elevenlabs",
                                to_provider="whisper",
                                allow_provider_fallback=allow_provider_fallback,
                            )
                            if not _can_eleven_to_whisper_sse:
                                raise RuntimeError(
                                    "ElevenLabs indisponível e fallback para Whisper foi desabilitado."
                                )
                            # Fallback Whisper (sem AAI key)
                            await emit(
                                "transcription",
                                35,
                                self._provider_switch_message(
                                    from_provider="elevenlabs",
                                    to_provider="whisper",
                                    allow_provider_fallback=allow_provider_fallback,
                                ),
                            )
                            whisper_vomo = await _ensure_vomo_for_whisper_fallback()
                            whisper_result = await _run_whisper_with_external_diarization(
                                whisper_vomo,
                                start_progress=35,
                                end_progress=60,
                            )
                            transcription_text = whisper_result.get("text", "")
                            transcription_words = whisper_result.get("words", [])
                            transcription_segments = whisper_result.get("segments", [])
                            self._aai_apostila_result = None
                            self._elevenlabs_result = None
                            await emit("transcription", 60, "Transcrição Whisper concluída ✓")

                    elif _aai_primary_sse:
                        # Whisper em paralelo para benchmark
                        _benchmark_future_sse = None
                        if self._is_benchmark_enabled():
                            _benchmark_future_sse = self._start_whisper_benchmark_for_apostila(
                                audio_path, mode, high_accuracy, diarization,
                                diarization_strict, language,
                            )

                        # Usar nova função com progresso real de upload
                        aai_result_sse = None
                        try:
                            aai_result_sse = await self._transcribe_assemblyai_with_progress(
                                cloud_audio_path,  # Usar áudio otimizado para cloud (MP3 64k)
                                emit,
                                speaker_roles=speaker_roles,
                                language=language or "pt",
                                speakers_expected=speakers_expected,
                                mode=mode,
                                start_progress=25,
                                end_progress=60,
                                speaker_id_type=speaker_id_type,
                                speaker_id_values=speaker_id_values,
                            )
                        except Exception as aai_exc:
                            logger.warning("AssemblyAI falhou (SSE): %s", aai_exc)

                        if aai_result_sse:
                            transcription_text = aai_result_sse.get("text_with_timestamps") or aai_result_sse["text"]
                            transcription_words = aai_result_sse.get("words", [])
                            transcription_segments = aai_result_sse.get("segments", [])
                            self._aai_apostila_result = aai_result_sse
                            await emit("transcription", 60, "Transcrição AssemblyAI concluída ✓")
                        else:
                            _can_aai_to_whisper_sse = self._is_provider_fallback_allowed(
                                requested_engine=transcription_engine,
                                from_provider="assemblyai",
                                to_provider="whisper",
                                allow_provider_fallback=allow_provider_fallback,
                            )
                            if not _can_aai_to_whisper_sse:
                                raise RuntimeError(
                                    "AssemblyAI indisponível e fallback para Whisper foi desabilitado."
                                )
                            # Fallback Whisper
                            await emit(
                                "transcription",
                                35,
                                self._provider_switch_message(
                                    from_provider="assemblyai",
                                    to_provider="whisper",
                                    allow_provider_fallback=allow_provider_fallback,
                                ),
                            )
                            self._aai_apostila_result = None
                            whisper_vomo = await _ensure_vomo_for_whisper_fallback()
                            whisper_result = await _run_whisper_with_external_diarization(
                                whisper_vomo,
                                start_progress=35,
                                end_progress=60,
                            )
                            transcription_text = whisper_result.get("text", "")
                            transcription_words = whisper_result.get("words", [])
                            transcription_segments = whisper_result.get("segments", [])
                            await emit("transcription", 60, "Transcrição Whisper concluída ✓")
                    elif _runpod_primary_sse:
                        # RunPod Serverless: transcrição via GPU cloud
                        self._aai_apostila_result = None
                        _benchmark_future_sse = None
                        await emit("transcription", 25, "Enviando para RunPod GPU cloud...")
                        try:
                            runpod_result = await self._transcribe_runpod(
                                file_path=file_path,
                                audio_path=audio_path,
                                language=language or "pt",
                                diarization=diarization_enabled,
                                emit=emit,
                                start_progress=25,
                                end_progress=60,
                            )
                            if runpod_result and str(runpod_result.get("text", "")).strip():
                                transcription_text = runpod_result["text"]
                                transcription_words = runpod_result.get("words", []) or []
                                transcription_segments = runpod_result.get("segments", []) or []
                                await emit("transcription", 60, "Transcrição RunPod concluída ✓")
                            else:
                                raise RuntimeError("RunPod retornou resultado vazio")
                        except Exception as runpod_exc:
                            logger.warning("RunPod falhou (SSE): %s", runpod_exc)
                            await emit("transcription", 34, f"⚠️ RunPod falhou: {runpod_exc}")
                            _can_runpod_to_whisper = self._is_provider_fallback_allowed(
                                requested_engine=transcription_engine,
                                from_provider="runpod",
                                to_provider="whisper",
                                allow_provider_fallback=allow_provider_fallback,
                            )
                            if not _can_runpod_to_whisper:
                                raise RuntimeError(
                                    f"RunPod indisponível e fallback para Whisper foi desabilitado: {runpod_exc}"
                                )
                            await emit(
                                "transcription", 35,
                                self._provider_switch_message(
                                    from_provider="runpod",
                                    to_provider="whisper",
                                    allow_provider_fallback=allow_provider_fallback,
                                ),
                            )
                            whisper_vomo = await _ensure_vomo_for_whisper_fallback()
                            whisper_result = await _run_whisper_with_external_diarization(
                                whisper_vomo,
                                start_progress=35,
                                end_progress=60,
                            )
                            transcription_text = whisper_result.get("text", "")
                            transcription_words = whisper_result.get("words", [])
                            transcription_segments = whisper_result.get("segments", [])
                            self._aai_apostila_result = None
                            await emit("transcription", 60, "Transcrição Whisper concluída ✓")
                    else:
                        # Fluxo padrão: Whisper primário com progresso em tempo real
                        self._aai_apostila_result = None
                        _benchmark_future_sse = None
                        await emit("transcription", 25, "Iniciando transcrição com Whisper MLX...")
                        try:
                            transcription_result = await _run_whisper_with_external_diarization(
                                vomo,
                                start_progress=25,
                                end_progress=60,
                            )
                            transcription_text = transcription_result.get("text", "")
                            transcription_words = transcription_result.get("words", [])
                            transcription_segments = transcription_result.get("segments", [])
                            await emit("transcription", 60, "Transcrição concluída ✓")
                        except Exception as whisper_exc:
                            logger.warning("Whisper falhou (SSE), avaliando fallback: %s", whisper_exc)
                            _allow_aai_fallback = self._is_provider_fallback_allowed(
                                requested_engine=transcription_engine,
                                from_provider="whisper",
                                to_provider="assemblyai",
                                allow_provider_fallback=allow_provider_fallback,
                            )
                            if not _allow_aai_fallback:
                                logger.warning("Fallback Whisper->AssemblyAI desabilitado para esta execução.")
                                raise
                            if not self._get_assemblyai_key():
                                raise

                            # Fallback: AssemblyAI com áudio otimizado para cloud (MP3 64k) quando possível
                            fallback_cloud = audio_path
                            try:
                                if self._should_extract_audio_for_cloud(file_path):
                                    await emit("transcription", 27, "🔄 Otimizando para fallback cloud (MP3)...")
                                    fallback_cloud = await asyncio.to_thread(
                                        self._extract_audio_for_cloud, file_path, "mp3", "64k"
                                    )
                            except Exception as cloud_extract_err:
                                logger.warning("Fallback cloud falhou, usando WAV: %s", cloud_extract_err)
                                fallback_cloud = audio_path

                            await emit(
                                "transcription",
                                30,
                                self._provider_switch_message(
                                    from_provider="whisper",
                                    to_provider="assemblyai",
                                    allow_provider_fallback=allow_provider_fallback,
                                ),
                            )
                            aai_result_fallback = None
                            try:
                                aai_result_fallback = await self._transcribe_assemblyai_with_progress(
                                    fallback_cloud,
                                    emit,
                                    speaker_roles=speaker_roles,
                                    language=language or "pt",
                                    speakers_expected=speakers_expected,
                                    mode=mode,
                                    start_progress=25,
                                    end_progress=60,
                                    speaker_id_type=speaker_id_type,
                                    speaker_id_values=speaker_id_values,
                                )
                            except Exception as aai_exc:
                                logger.warning("Fallback AssemblyAI falhou (SSE): %s", aai_exc)

                            if not aai_result_fallback:
                                raise

                            transcription_text = aai_result_fallback.get("text_with_timestamps") or aai_result_fallback.get("text") or ""
                            transcription_words = aai_result_fallback.get("words", [])
                            transcription_segments = aai_result_fallback.get("segments", [])
                            self._aai_apostila_result = aai_result_fallback
                            await emit("transcription", 60, "Transcrição AssemblyAI concluída ✓")

                    if use_cache and cache_hash:
                        self._save_cached_raw(
                            cache_hash,
                            high_accuracy,
                            diarization_enabled,
                            transcription_text,
                            PathLib(file_path).name,
                        )
            
            if mode == "RAW":
                raw_result = {
                    "content": transcription_text,
                    "raw_content": transcription_text,
                    "words": transcription_words,
                    "reports": {},
                }
                if transcription_segments:
                    raw_result["segments"] = transcription_segments
                return raw_result

            # Stage 3: Formatting (60-100%)
            await emit("formatting", 65, "Preparando formatação com IA...")
            vomo = await _ensure_vomo_for_formatting()
            if vomo is None:
                logger.warning("⚠️ _ensure_vomo_for_formatting retornou None — fallback sync")
                vomo = self._get_vomo(model_selection=model_selection, thinking_level=thinking_level)
                if vomo is None:
                    raise RuntimeError("Motor de formatação indisponível (VomoMLX não inicializado).")
                vomo._current_language = _current_language
                vomo._output_language = _output_language
                vomo._current_mode = _current_mode

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
                table_recovery_meta: Optional[dict] = None
                try:
                    final_text, vomo = await self._run_llm_format_with_resilience(
                        vomo=vomo,
                        source_text=transcription_text,
                        video_name=video_name,
                        output_folder=temp_dir,
                        mode=mode,
                        custom_prompt=system_prompt,
                        disable_tables=bool(disable_tables),
                        progress_callback=emit,
                        skip_audit=skip_legal_audit,
                        skip_fidelity_audit=skip_fidelity_audit,
                        skip_sources_audit=skip_sources_audit,
                        model_selection=model_selection,
                        thinking_level=thinking_level,
                    )

                    try:
                        mode_upper = (mode or 'APOSTILA').strip().upper()
                        raw_words = len(re.findall(r'\S+', transcription_text or ''))
                        def _has_md_table(markdown_text: str) -> bool:
                            lines_md = (markdown_text or '').splitlines()
                            sep_pattern = re.compile(r'^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$')
                            for idx_line in range(len(lines_md) - 1):
                                header = lines_md[idx_line].strip()
                                sep = lines_md[idx_line + 1].strip()
                                if '|' not in header or '|' not in sep:
                                    continue
                                if header.count('|') < 2:
                                    continue
                                if sep_pattern.match(sep):
                                    return True
                            return False
                        has_table = _has_md_table(final_text or '')

                        if mode_upper in {'APOSTILA', 'FIDELIDADE'} and not bool(disable_tables) and not has_table and raw_words >= 1200:
                            preventive_path = Path(temp_dir) / f'{video_name}_{mode_upper}_AUDITORIA_FIDELIDADE.json'
                            retention_ratio = None
                            fidelity_score = None
                            if preventive_path.exists():
                                try:
                                    payload = json.loads(preventive_path.read_text(encoding='utf-8', errors='ignore') or '{}')
                                    if isinstance(payload, dict):
                                        metricas = payload.get('metricas') if isinstance(payload.get('metricas'), dict) else {}
                                        if metricas.get('taxa_retencao') is not None:
                                            retention_ratio = float(metricas.get('taxa_retencao'))
                                        elif payload.get('taxa_compressao_estimada') is not None:
                                            compressao = float(payload.get('taxa_compressao_estimada'))
                                            if compressao > 1:
                                                compressao = compressao / 100.0
                                            if 0 <= compressao <= 1:
                                                retention_ratio = 1.0 - compressao
                                        if payload.get('nota_fidelidade') is not None:
                                            fidelity_score = float(payload.get('nota_fidelidade'))
                                except Exception:
                                    retention_ratio = None

                            if retention_ratio is None:
                                fmt_words = len(re.findall(r'\S+', final_text or ''))
                                retention_ratio = (fmt_words / raw_words) if raw_words > 0 else None

                            low_retention = retention_ratio is not None and retention_ratio < 0.60
                            low_score = fidelity_score is not None and fidelity_score <= 6.0

                            if low_retention or low_score:
                                table_recovery_meta = {
                                    'triggered': True,
                                    'reason': 'missing_tables_with_content_loss',
                                    'retention_ratio': retention_ratio,
                                    'fidelity_score': fidelity_score,
                                    'mode': mode_upper,
                                }
                                await emit('formatting', 90, 'Detectado risco de perda critica sem tabelas. Aplicando segunda passada...')
                                retry_prompt = ((system_prompt.strip() + '\n\n') if system_prompt and system_prompt.strip() else '') + (
                                    'MODO DE RECUPERACAO AUTOMATICA DE TABELAS\n'
                                    '- Preserve fidelidade ao RAW.\n'
                                    '- Reintroduza tabelas markdown quando houver comparacao de itens.\n'
                                    '- Nao invente fatos.'
                                )
                                recovered_text = await vomo.format_transcription_async(
                                    transcription_text,
                                    video_name=video_name,
                                    output_folder=temp_dir,
                                    mode=mode,
                                    custom_prompt=retry_prompt,
                                    disable_tables=False,
                                    progress_callback=emit,
                                    skip_audit=skip_legal_audit,
                                    skip_fidelity_audit=skip_fidelity_audit,
                                    skip_sources_audit=skip_sources_audit,
                                )
                                recovered_has_table = _has_md_table(recovered_text or '')
                                rec_words = len(re.findall(r'\S+', recovered_text or ''))
                                recovered_retention = (rec_words / raw_words) if raw_words > 0 else None
                                retention_gain = (
                                    (recovered_retention - retention_ratio)
                                    if (retention_ratio is not None and recovered_retention is not None)
                                    else 0.0
                                )
                                if recovered_has_table or retention_gain >= 0.08:
                                    final_text = recovered_text
                                    table_recovery_meta['applied'] = True
                                    await emit('formatting', 95, 'Segunda passada concluiu recuperacao de tabelas.')
                                else:
                                    table_recovery_meta['applied'] = False
                                table_recovery_meta['recovered_has_table'] = recovered_has_table
                                table_recovery_meta['recovered_retention_ratio'] = recovered_retention
                    except Exception as table_recovery_err:
                        logger.warning(f'Falha na recuperacao automatica de tabelas (SSE): {table_recovery_err}')
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
                        try:
                            structural_timeout = int(os.getenv("IUDEX_HIL_STRUCTURAL_AUDIT_TIMEOUT_SECONDS", "300"))
                        except Exception:
                            structural_timeout = 300
                        try:
                            analysis_report = await asyncio.wait_for(
                                quality_service.analyze_structural_issues(
                                    content=final_text,
                                    document_name=video_name,
                                    raw_content=transcription_text
                                ),
                                timeout=structural_timeout,
                            )
                        except asyncio.TimeoutError:
                            logger.warning("⏳ Timeout na análise estrutural (audit). Prosseguindo sem relatório completo.")
                            await emit("audit", 96, "Timeout na análise estrutural; continuando...")
                            analysis_report = {"total_issues": 0, "cli_issues": {}, "error": "Timeout na análise estrutural"}
                        cli_issues = (analysis_report or {}).get("cli_issues") or analysis_report
                        try:
                            audit_timeout = int(os.getenv("IUDEX_HIL_AUDIT_TIMEOUT_SECONDS", "600"))
                        except Exception:
                            audit_timeout = 600
                        try:
                            validation_report = await asyncio.wait_for(
                                quality_service.validate_document_full(
                                    raw_content=transcription_text,
                                    formatted_content=final_text,
                                    document_name=video_name,
                                    mode=mode,
                                ),
                                timeout=audit_timeout,
                            )
                        except asyncio.TimeoutError:
                            logger.warning("⏳ Timeout na validação de fidelidade (audit). Prosseguindo sem relatório completo.")
                            await emit("audit", 96, "Timeout na validação de fidelidade; continuando...")
                            validation_report = {"approved": False, "score": 0, "error": "Timeout na validação de fidelidade"}

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
                                        model_selection=model_selection,
                                        mode=mode,
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

                # Coletar segments para legendas (ElevenLabs > AAI > Whisper)
                _segments_for_subtitles_sse = None
                if subtitle_format:
                    el_result_sse = getattr(self, "_elevenlabs_result", None)
                    aai_apostila_sse = getattr(self, "_aai_apostila_result", None)
                    if el_result_sse and el_result_sse.get("segments"):
                        _segments_for_subtitles_sse = el_result_sse["segments"]
                        logger.info(f"🎬 Usando {len(_segments_for_subtitles_sse)} segments do ElevenLabs para legendas")
                    elif aai_apostila_sse and aai_apostila_sse.get("segments"):
                        _segments_for_subtitles_sse = aai_apostila_sse["segments"]
                        logger.info(f"🎬 Usando {len(_segments_for_subtitles_sse)} segments do AAI para legendas")
                    elif not is_text_input and audio_path:
                        # Extrair segments do Whisper se disponível
                        try:
                            _segments_for_subtitles_sse = self._extract_local_segments(vomo, audio_path, high_accuracy)
                            if _segments_for_subtitles_sse:
                                logger.info(f"🎬 Usando {len(_segments_for_subtitles_sse)} segments do Whisper para legendas")
                        except Exception as seg_exc:
                            logger.warning(f"Legendas: falha ao extrair segments Whisper: {seg_exc}")

                report_paths = self._persist_transcription_outputs(
                    video_name=video_name,
                    mode=mode,
                    raw_text=transcription_text,
                    formatted_text=final_text,
                    analysis_report=analysis_report,
                    validation_report=validation_report,
                    segments=_segments_for_subtitles_sse,
                    subtitle_format=subtitle_format,
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
                if table_recovery_meta:
                    report_paths['table_recovery'] = table_recovery_meta
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

                title_drift = self._load_title_drift_telemetry(report_paths)

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
                    "title_drift": title_drift,
                }))

            # Benchmark AAI apostila (SSE): finalizar se AAI primário
            if not is_text_input and getattr(self, "_aai_apostila_result", None):
                _bm_out = report_paths.get("output_dir") if report_paths else None
                _bm_future = locals().get("_benchmark_future_sse")
                if _bm_future is not None:
                    self._finalize_hearing_benchmark(
                        aai_result=self._aai_apostila_result,
                        whisper_future=_bm_future,
                        output_dir=_bm_out,
                        video_name=video_name,
                        audio_path=audio_path,
                    )
                if _bm_out:
                    try:
                        out = PathLib(_bm_out)
                        aai_j = out / f"{video_name}_ASSEMBLYAI.json"
                        aai_t = out / f"{video_name}_ASSEMBLYAI.txt"
                        aai_j.write_text(
                            json.dumps(self._aai_apostila_result, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                        aai_t.write_text(
                            self._aai_apostila_result.get("text", ""),
                            encoding="utf-8",
                        )
                    except Exception as save_exc:
                        logger.warning(f"Falha ao salvar artefatos AAI apostila SSE: {save_exc}")
                self._aai_apostila_result = None

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
                "words": transcription_words,  # Word-level timestamps para player interativo
                "reports": report_paths,
                "audit_issues": issues,
                "audit_summary": audit_summary,
                "quality": quality_payload,
                "headers_changed_count": title_drift.get("headers_changed_count", 0) if isinstance(title_drift, dict) else 0,
                "headers_restored_count": title_drift.get("headers_restored_count", 0) if isinstance(title_drift, dict) else 0,
                "headers_degraded_count": title_drift.get("headers_degraded_count", 0) if isinstance(title_drift, dict) else 0,
                "headers_diff": title_drift.get("headers_diff", []) if isinstance(title_drift, dict) else [],
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
        disable_tables: bool = False,
        high_accuracy: bool = False,
        transcription_engine: str = "whisper",
        diarization: Optional[bool] = None,
        diarization_strict: bool = False,
        diarization_provider: Optional[str] = None,
        on_progress: Optional[Callable[[str, int, str], Awaitable[None]]] = None,
        model_selection: Optional[str] = None,
        use_cache: bool = True,
        auto_apply_fixes: bool = True,
        auto_apply_content_fixes: bool = False,
        skip_legal_audit: bool = False,
        skip_audit: Optional[bool] = None,
        skip_fidelity_audit: bool = False,
        skip_sources_audit: bool = False,
        language: Optional[str] = None,
        output_language: Optional[str] = None,
        allow_provider_fallback: Optional[bool] = None,
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

        title_drift: dict = {
            "headers_changed_count": 0,
            "headers_restored_count": 0,
            "headers_degraded_count": 0,
            "headers_diff": [],
        }

        try:
            if skip_audit is not None:
                skip_legal_audit = skip_legal_audit or skip_audit
            allow_provider_fallback = self._enforce_fidelity_critical_fallback(
                mode=mode,
                allow_provider_fallback=allow_provider_fallback,
            )
            apply_fixes = auto_apply_fixes
            _requested_engine_batch = (transcription_engine or "whisper").strip().lower()

            # Emit progress BEFORE initializing vomo (can be slow due to Vertex AI/Gemini connection)
            await emit("initializing", 0, "🚀 Inicializando motor de transcrição...")
            if _requested_engine_batch in {"assemblyai", "elevenlabs"}:
                _provider_available = (
                    (_requested_engine_batch == "assemblyai" and self._get_assemblyai_key() is not None)
                    or (_requested_engine_batch == "elevenlabs" and self._get_elevenlabs_key() is not None)
                )
                if not _provider_available:
                    _can_switch_missing_provider = self._is_provider_fallback_allowed(
                        requested_engine=transcription_engine,
                        from_provider=_requested_engine_batch,
                        to_provider="whisper",
                        allow_provider_fallback=allow_provider_fallback,
                    )
                    if not _can_switch_missing_provider:
                        raise RuntimeError(
                            f"{_requested_engine_batch} indisponível e fallback para Whisper foi desabilitado."
                        )
                    await emit(
                        "initializing",
                        2,
                        self._provider_switch_message(
                            from_provider=_requested_engine_batch,
                            to_provider="whisper",
                            allow_provider_fallback=allow_provider_fallback,
                        ),
                    )
            vomo = await self._get_vomo_with_progress(
                emit=emit,
                model_selection=model_selection,
                thinking_level=thinking_level,
                ready_message="✅ Motor de transcrição pronto",
            )

            vomo._current_language = (language or "pt").strip().lower()
            vomo._output_language = (output_language or "").strip().lower() or None
            vomo._current_mode = (mode or "APOSTILA").strip().upper()
            total_files = len(file_paths)
            all_raw_transcriptions = []
            diarization_enabled, diarization_required = (False, False)
            try:
                diarization_enabled, diarization_required = vomo.resolve_diarization_policy(
                    mode, diarization=diarization, diarization_strict=diarization_strict
                )
            except Exception:
                pass
            diarization_provider = self._normalize_diarization_provider(diarization_provider)
            
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
                        transcription_text = self._load_cached_raw(cache_hash, high_accuracy, diarization_enabled)
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
                            self._save_cached_raw(
                                cache_hash,
                                high_accuracy,
                                diarization_enabled,
                                transcription_text,
                                file_name,
                            )
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
                        # Verificar se AAI deve ser primário (para áudios longos)
                        _force_aai_batch = self._is_assemblyai_primary_forced()
                        _aai_key = self._get_assemblyai_key()
                        _engine_aai_batch = transcription_engine == "assemblyai"
                        _engine_whisper_batch = transcription_engine == "whisper"
                        _force_aai_effective_batch = _force_aai_batch and not _engine_whisper_batch
                        audio_duration = self._get_wav_duration_seconds(audio_path)

                        if (_engine_aai_batch or _force_aai_effective_batch) and _aai_key:
                            # AssemblyAI como primário (melhor para áudios longos) - com progresso real
                            logger.info(f"🗣️ AAI primário (batch) para {file_name} ({audio_duration:.0f}s)")

                            # Iniciar benchmark Whisper em paralelo (se habilitado)
                            _benchmark_future_batch = None
                            if self._is_benchmark_enabled():
                                logger.info(f"🔬 Iniciando benchmark Whisper em paralelo para {file_name}")
                                _benchmark_future_batch = self._start_whisper_benchmark_for_apostila(
                                    audio_path, mode, high_accuracy, diarization,
                                    diarization_strict, language,
                                )

                            # Wrapper de emit para adicionar prefixo de batch
                            async def batch_emit(stage: str, progress: int, message: str):
                                # Mapear progresso de 25-60 para o range do arquivo atual
                                pct = (progress - 25) / 35  # 0.0 a 1.0
                                actual_progress = transcribe_progress + int(pct * (file_progress_increment - 5))
                                await emit("batch", actual_progress, f"[{file_num}/{total_files}] {message}")

                            aai_result = await self._transcribe_assemblyai_with_progress(
                                audio_path,
                                batch_emit,
                                speaker_roles=None,
                                language=language or "pt",
                                speakers_expected=None,
                                mode=mode,
                                start_progress=25,
                                end_progress=60,
                            )
                            if aai_result:
                                transcription_text = aai_result.get("text_with_timestamps") or aai_result.get("text", "")
                                logger.info(f"✅ AAI batch concluído para {file_name}")

                                # Coletar resultado do benchmark Whisper (se rodando)
                                if _benchmark_future_batch:
                                    try:
                                        whisper_result = _benchmark_future_batch.result(timeout=1)
                                        if whisper_result:
                                            logger.info(f"🔬 Benchmark Whisper concluído para {file_name}")
                                            # Gerar comparação
                                            comparison = self._compare_transcriptions(
                                                whisper_result, aai_result, file_name
                                            )
                                            if comparison:
                                                self._log_benchmark_result(comparison, file_name)
                                    except Exception as bench_exc:
                                        logger.debug(f"Benchmark ainda rodando ou falhou: {bench_exc}")
                            else:
                                _can_aai_to_whisper_batch = self._is_provider_fallback_allowed(
                                    requested_engine=transcription_engine,
                                    from_provider="assemblyai",
                                    to_provider="whisper",
                                    allow_provider_fallback=allow_provider_fallback,
                                )
                                if not _can_aai_to_whisper_batch:
                                    await emit(
                                        "batch",
                                        transcribe_progress + 5,
                                        f"[{file_num}/{total_files}] ❌ AssemblyAI indisponível e fallback para Whisper desabilitado",
                                    )
                                    transcription_text = "[ERRO: AssemblyAI indisponível e fallback para Whisper desabilitado]"
                                    logger.error("Fallback AssemblyAI->Whisper desabilitado para %s", file_name)
                                # Fallback para Whisper se AAI falhar
                                if _can_aai_to_whisper_batch:
                                    logger.warning(f"⚠️ AAI falhou para {file_name}, usando Whisper")
                                    await emit(
                                        "batch",
                                        transcribe_progress + 5,
                                        f"[{file_num}/{total_files}] {self._provider_switch_message(from_provider='assemblyai', to_provider='whisper', allow_provider_fallback=allow_provider_fallback)}",
                                    )
                                    whisper_result = await self._transcribe_whisper_with_optional_external_diarization(
                                        vomo=vomo,
                                        audio_path=audio_path,
                                        mode=mode,
                                        high_accuracy=high_accuracy,
                                        diarization=diarization,
                                        diarization_strict=diarization_strict,
                                        language=language,
                                        diarization_enabled=diarization_enabled,
                                        diarization_required=diarization_required,
                                        diarization_provider=diarization_provider,
                                    )
                                    transcription_text = whisper_result.get("text", "")
                        else:
                            # Whisper como primário (padrão)
                            await emit("batch", transcribe_progress, f"[{file_num}/{total_files}] 🎙️ Whisper Transcrevendo: {file_name}")
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

                            if diarization_enabled:
                                logger.info(
                                    "🗣️  Diarização habilitada (%s, provider=%s) para %s",
                                    "strict" if diarization_required else "soft",
                                    diarization_provider,
                                    file_name,
                                )
                            if high_accuracy:
                                logger.info(f"🎯 Usando Beam Search (High Accuracy) para {file_name}")

                            # v2.34: Tratamento de erro para arquivos muito longos
                            try:
                                whisper_result = await self._transcribe_whisper_with_optional_external_diarization(
                                    vomo=vomo,
                                    audio_path=audio_path,
                                    mode=mode,
                                    high_accuracy=high_accuracy,
                                    diarization=diarization,
                                    diarization_strict=diarization_strict,
                                    language=language,
                                    diarization_enabled=diarization_enabled,
                                    diarization_required=diarization_required,
                                    diarization_provider=diarization_provider,
                                )
                                transcription_text = whisper_result.get("text", "")
                            except Exception as whisper_exc:
                                logger.error(f"❌ Erro Whisper para {file_name}: {whisper_exc}")
                                _allow_aai_fallback_batch = self._is_provider_fallback_allowed(
                                    requested_engine=transcription_engine,
                                    from_provider="whisper",
                                    to_provider="assemblyai",
                                    allow_provider_fallback=allow_provider_fallback,
                                )
                                if not _allow_aai_fallback_batch:
                                    await emit(
                                        "batch",
                                        transcribe_progress + 5,
                                        f"[{file_num}/{total_files}] ❌ Erro Whisper (fallback para AssemblyAI desabilitado)",
                                    )
                                    transcription_text = f"[ERRO: Transcrição Whisper falhou - {whisper_exc}]"
                                else:
                                    await emit(
                                        "batch",
                                        transcribe_progress + 5,
                                        f"[{file_num}/{total_files}] {self._provider_switch_message(from_provider='whisper', to_provider='assemblyai', allow_provider_fallback=allow_provider_fallback)}",
                                    )
                                    # Fallback para AssemblyAI se disponível
                                    _fallback_aai_key = self._get_assemblyai_key()
                                    if _fallback_aai_key:
                                        try:
                                            # Criar emit wrapper para o fallback
                                            async def _fallback_emit(stage: str, progress: int, message: str):
                                                pct = (progress - 25) / 35
                                                actual_progress = transcribe_progress + int(pct * (file_progress_increment - 5))
                                                await emit("batch", actual_progress, f"[{file_num}/{total_files}] {message}")

                                            aai_fallback_result = await self._transcribe_assemblyai_with_progress(
                                                audio_path,
                                                _fallback_emit,
                                                speaker_roles=None,
                                                language=language or "pt",
                                                speakers_expected=None,
                                                mode=mode,
                                                start_progress=25,
                                                end_progress=60,
                                            )
                                            if aai_fallback_result:
                                                transcription_text = aai_fallback_result.get("text_with_timestamps") or aai_fallback_result.get("text", "")
                                                logger.info(f"✅ Fallback AAI concluído para {file_name}")
                                        except Exception as aai_fb_exc:
                                            logger.error(f"❌ Fallback AAI também falhou: {aai_fb_exc}")
                                            transcription_text = f"[ERRO: Transcrição falhou - {whisper_exc}]"
                                    else:
                                        transcription_text = f"[ERRO: Transcrição falhou - {whisper_exc}]"

                            done_event.set()
                            try:
                                await ticker
                            except Exception:
                                pass

                            # v2.34: Validar que temos conteúdo
                            if not transcription_text or len(transcription_text.strip()) < 50:
                                logger.warning(f"⚠️ Transcrição vazia ou muito curta para {file_name} ({len(transcription_text or '')} chars)")
                                await emit("batch", transcribe_progress + 8, f"[{file_num}/{total_files}] ⚠️ Resultado vazio, verificando...")

                        if use_cache and cache_hash:
                            self._save_cached_raw(
                                cache_hash,
                                high_accuracy,
                                diarization_enabled,
                                transcription_text,
                                file_name,
                            )
                
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
            if vomo is None:
                logger.warning("⚠️ Vomo ausente antes da formatação em lote — fallback sync")
                vomo = self._get_vomo(model_selection=model_selection, thinking_level=thinking_level)
                if vomo is None:
                    raise RuntimeError("Motor de formatação indisponível (VomoMLX não inicializado).")
                vomo._current_language = (language or "pt").strip().lower()
                vomo._output_language = (output_language or "").strip().lower() or None
                vomo._current_mode = (mode or "APOSTILA").strip().upper()
            
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
                table_recovery_meta: Optional[dict] = None
                try:
                    final_text, vomo = await self._run_llm_format_with_resilience(
                        vomo=vomo,
                        source_text=unified_raw,
                        video_name=video_name,
                        output_folder=temp_dir,
                        mode=mode,
                        custom_prompt=system_prompt,
                        disable_tables=bool(disable_tables),
                        progress_callback=emit,
                        skip_audit=skip_legal_audit,
                        skip_fidelity_audit=skip_fidelity_audit,
                        skip_sources_audit=skip_sources_audit,
                        model_selection=model_selection,
                        thinking_level=thinking_level,
                    )

                    try:
                        mode_upper = (mode or 'APOSTILA').strip().upper()
                        raw_words = len(re.findall(r'\S+', unified_raw or ''))
                        def _has_md_table(markdown_text: str) -> bool:
                            lines_md = (markdown_text or '').splitlines()
                            sep_pattern = re.compile(r'^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$')
                            for idx_line in range(len(lines_md) - 1):
                                header = lines_md[idx_line].strip()
                                sep = lines_md[idx_line + 1].strip()
                                if '|' not in header or '|' not in sep:
                                    continue
                                if header.count('|') < 2:
                                    continue
                                if sep_pattern.match(sep):
                                    return True
                            return False
                        has_table = _has_md_table(final_text or '')

                        if mode_upper in {'APOSTILA', 'FIDELIDADE'} and not bool(disable_tables) and not has_table and raw_words >= 1200:
                            preventive_path = Path(temp_dir) / f'{video_name}_{mode_upper}_AUDITORIA_FIDELIDADE.json'
                            retention_ratio = None
                            fidelity_score = None
                            if preventive_path.exists():
                                try:
                                    payload = json.loads(preventive_path.read_text(encoding='utf-8', errors='ignore') or '{}')
                                    if isinstance(payload, dict):
                                        metricas = payload.get('metricas') if isinstance(payload.get('metricas'), dict) else {}
                                        if metricas.get('taxa_retencao') is not None:
                                            retention_ratio = float(metricas.get('taxa_retencao'))
                                        elif payload.get('taxa_compressao_estimada') is not None:
                                            compressao = float(payload.get('taxa_compressao_estimada'))
                                            if compressao > 1:
                                                compressao = compressao / 100.0
                                            if 0 <= compressao <= 1:
                                                retention_ratio = 1.0 - compressao
                                        if payload.get('nota_fidelidade') is not None:
                                            fidelity_score = float(payload.get('nota_fidelidade'))
                                except Exception:
                                    retention_ratio = None

                            if retention_ratio is None:
                                fmt_words = len(re.findall(r'\S+', final_text or ''))
                                retention_ratio = (fmt_words / raw_words) if raw_words > 0 else None

                            low_retention = retention_ratio is not None and retention_ratio < 0.60
                            low_score = fidelity_score is not None and fidelity_score <= 6.0

                            if low_retention or low_score:
                                table_recovery_meta = {
                                    'triggered': True,
                                    'reason': 'missing_tables_with_content_loss',
                                    'retention_ratio': retention_ratio,
                                    'fidelity_score': fidelity_score,
                                    'mode': mode_upper,
                                }
                                await emit('formatting', 90, 'Detectado risco de perda critica sem tabelas. Aplicando segunda passada...')
                                retry_prompt = ((system_prompt.strip() + '\n\n') if system_prompt and system_prompt.strip() else '') + (
                                    'MODO DE RECUPERACAO AUTOMATICA DE TABELAS\n'
                                    '- Preserve fidelidade ao RAW.\n'
                                    '- Reintroduza tabelas markdown quando houver comparacao de itens.\n'
                                    '- Nao invente fatos.'
                                )
                                recovered_text = await vomo.format_transcription_async(
                                    unified_raw,
                                    video_name=video_name,
                                    output_folder=temp_dir,
                                    mode=mode,
                                    custom_prompt=retry_prompt,
                                    disable_tables=False,
                                    progress_callback=emit,
                                    skip_audit=skip_legal_audit,
                                    skip_fidelity_audit=skip_fidelity_audit,
                                    skip_sources_audit=skip_sources_audit,
                                )
                                recovered_has_table = _has_md_table(recovered_text or '')
                                rec_words = len(re.findall(r'\S+', recovered_text or ''))
                                recovered_retention = (rec_words / raw_words) if raw_words > 0 else None
                                retention_gain = (
                                    (recovered_retention - retention_ratio)
                                    if (retention_ratio is not None and recovered_retention is not None)
                                    else 0.0
                                )
                                if recovered_has_table or retention_gain >= 0.08:
                                    final_text = recovered_text
                                    table_recovery_meta['applied'] = True
                                    await emit('formatting', 95, 'Segunda passada concluiu recuperacao de tabelas.')
                                else:
                                    table_recovery_meta['applied'] = False
                                table_recovery_meta['recovered_has_table'] = recovered_has_table
                                table_recovery_meta['recovered_retention_ratio'] = recovered_retention
                    except Exception as table_recovery_err:
                        logger.warning(f'Falha na recuperacao automatica de tabelas (batch): {table_recovery_err}')
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
                                        mode=mode,
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
                if table_recovery_meta:
                    report_paths['table_recovery'] = table_recovery_meta
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

                title_drift = self._load_title_drift_telemetry(report_paths)

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
                    "title_drift": title_drift,
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
                "headers_changed_count": title_drift.get("headers_changed_count", 0) if isinstance(title_drift, dict) else 0,
                "headers_restored_count": title_drift.get("headers_restored_count", 0) if isinstance(title_drift, dict) else 0,
                "headers_degraded_count": title_drift.get("headers_degraded_count", 0) if isinstance(title_drift, dict) else 0,
                "headers_diff": title_drift.get("headers_diff", []) if isinstance(title_drift, dict) else [],
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

    def _get_raw_cache_path(self, file_hash: str, high_accuracy: bool, diarization_enabled: bool) -> Path:
        suffix = "beam" if high_accuracy else "base"
        diar_suffix = "diar" if diarization_enabled else "nodiar"
        return self._get_transcription_cache_dir() / file_hash / f"raw_{suffix}_{diar_suffix}.txt"

    def _get_raw_cache_path_legacy(self, file_hash: str, high_accuracy: bool) -> Path:
        """Compat: caches antigos não diferenciavam diarização."""
        suffix = "beam" if high_accuracy else "base"
        return self._get_transcription_cache_dir() / file_hash / f"raw_{suffix}.txt"

    def _load_cached_raw(self, file_hash: str, high_accuracy: bool, diarization_enabled: bool) -> Optional[str]:
        cache_path = self._get_raw_cache_path(file_hash, high_accuracy, diarization_enabled)
        if cache_path.exists():
            try:
                return cache_path.read_text(encoding="utf-8")
            except Exception:
                return None
        # Compat: só faz fallback para cache legado quando diarização está OFF
        if not diarization_enabled:
            legacy_path = self._get_raw_cache_path_legacy(file_hash, high_accuracy)
            if legacy_path.exists():
                try:
                    return legacy_path.read_text(encoding="utf-8")
                except Exception:
                    return None
        return None

    def _save_cached_raw(
        self,
        file_hash: str,
        high_accuracy: bool,
        diarization_enabled: bool,
        raw_text: str,
        source_name: str = "",
    ) -> None:
        cache_path = self._get_raw_cache_path(file_hash, high_accuracy, diarization_enabled)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(raw_text or "", encoding="utf-8")
        meta_path = cache_path.parent / "meta.json"
        try:
            meta = {
                "file_hash": file_hash,
                "high_accuracy": bool(high_accuracy),
                "diarization_enabled": bool(diarization_enabled),
                "source_name": source_name,
                "updated_at": datetime.utcnow().isoformat(),
            }
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    # ==================== AssemblyAI Cache Methods ====================
    # Sistema de cache para recuperação de transcrições AAI interrompidas
    # Persiste transcript_id imediatamente após submit para evitar perda de dados

    def _get_aai_cache_dir(self) -> Path:
        """Retorna diretório de cache para transcrições AssemblyAI."""
        try:
            from app.core.config import settings
            base_dir = Path(settings.LOCAL_STORAGE_PATH) / "aai_transcripts"
        except Exception:
            base_dir = Path("./storage") / "aai_transcripts"
        base_dir.mkdir(parents=True, exist_ok=True)
        return base_dir

    def _get_aai_cache_path(self, file_hash: str) -> Path:
        """Retorna caminho do cache AAI para um arquivo específico."""
        return self._get_aai_cache_dir() / f"{file_hash}.json"

    def _get_aai_config_hash(
        self,
        language: str = "pt",
        speaker_labels: bool = True,
        speakers_expected: Optional[int] = None,
        mode: Optional[str] = None,
    ) -> str:
        """Calcula hash da configuração para invalidação de cache."""
        config = {
            "language": language,
            "speaker_labels": speaker_labels,
            "speakers_expected": speakers_expected,
            "mode": mode or "default",
        }
        return hashlib.md5(json.dumps(config, sort_keys=True).encode()).hexdigest()[:8]

    def _save_aai_cache(
        self,
        file_path: str,
        transcript_id: str,
        audio_url: str,
        config_hash: str,
        status: str = "processing",
    ) -> None:
        """
        Salva transcript_id no cache imediatamente após submit.

        CRÍTICO: Este método deve ser chamado IMEDIATAMENTE após obter
        o transcript_id do AssemblyAI para garantir recuperação em caso
        de interrupção.
        """
        file_hash = self._compute_file_hash(file_path)
        cache_path = self._get_aai_cache_path(file_hash)

        cache_data = {
            "file_hash": file_hash,
            "file_name": Path(file_path).name,
            "file_size_bytes": Path(file_path).stat().st_size,
            "transcript_id": transcript_id,
            "audio_url": audio_url,
            "submitted_at": datetime.utcnow().isoformat() + "Z",
            "completed_at": None,
            "status": status,
            "config_hash": config_hash,
            "result_cached": False,
        }

        cache_path.write_text(json.dumps(cache_data, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info(f"💾 Cache AAI salvo: {transcript_id} → {file_hash[:8]}")

    def _update_aai_cache_status(
        self,
        file_hash: str,
        status: str,
        audio_duration: Optional[float] = None,
        result_cached: bool = False,
    ) -> None:
        """Atualiza status do cache AAI."""
        cache_path = self._get_aai_cache_path(file_hash)
        if not cache_path.exists():
            return

        try:
            cache_data = json.loads(cache_path.read_text(encoding="utf-8"))
            cache_data["status"] = status
            if status == "completed":
                cache_data["completed_at"] = datetime.utcnow().isoformat() + "Z"
            if audio_duration is not None:
                cache_data["audio_duration_seconds"] = audio_duration
            if result_cached:
                cache_data["result_cached"] = True
            cache_path.write_text(json.dumps(cache_data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Falha ao atualizar cache AAI: {e}")

    async def _fetch_aai_transcript_status(
        self,
        transcript_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Busca status/resultado de um transcript_id no AssemblyAI.
        Retorna None se não conseguir acessar ou se transcrição não existe.
        """
        import requests as http_requests

        api_key = self._get_assemblyai_key()
        if not api_key:
            return None

        base_url = "https://api.assemblyai.com"
        headers = {"authorization": api_key}
        poll_url = f"{base_url}/v2/transcript/{transcript_id}"

        try:
            resp = http_requests.get(poll_url, headers=headers, timeout=(10, 30))
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 404:
                logger.info(f"⚠️ Transcrição AAI não encontrada: {transcript_id}")
                return None
            else:
                logger.warning(f"AAI status check failed: {resp.status_code}")
                return None
        except http_requests.exceptions.RequestException as e:
            logger.warning(f"AAI status check error: {e}")
            return None

    async def _check_aai_cache(
        self,
        file_path: str,
        config_hash: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Verifica se existe transcrição AAI em cache para o arquivo.

        Retorna:
        - Dict com resultado completo se transcrição está pronta
        - Dict com {"status": "processing", "transcript_id": ...} se ainda processando
        - None se não há cache válido ou cache incompatível
        """
        file_hash = self._compute_file_hash(file_path)
        cache_path = self._get_aai_cache_path(file_hash)

        if not cache_path.exists():
            return None

        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Erro ao ler cache AAI: {e}")
            return None

        # Verificar se config é compatível
        if cache.get("config_hash") != config_hash:
            logger.info(f"⚠️ Cache AAI existe mas config diferente: {file_hash[:8]}")
            # Manter cache antigo mas retornar None para reprocessar
            return None

        transcript_id = cache.get("transcript_id")
        if not transcript_id:
            return None

        # Verificar status atual no AssemblyAI
        aai_response = await self._fetch_aai_transcript_status(transcript_id)

        if not aai_response:
            # Não conseguiu acessar AAI - cache pode estar inválido
            # Mas não deletar ainda, pode ser erro de rede temporário
            logger.info(f"⚠️ Não conseguiu verificar status AAI para {transcript_id}")
            return None

        aai_status = aai_response.get("status")

        if aai_status == "completed":
            # Transcrição pronta! Atualizar cache e retornar resultado
            self._update_aai_cache_status(
                file_hash,
                status="completed",
                audio_duration=aai_response.get("audio_duration"),
                result_cached=True,
            )
            logger.info(f"✅ Usando cache AAI: {transcript_id} (completo)")
            return {"status": "completed", "transcript_id": transcript_id, "response": aai_response}

        elif aai_status == "processing" or aai_status == "queued":
            # Ainda processando - retornar para continuar polling
            logger.info(f"🔄 Retomando polling AAI: {transcript_id} (status={aai_status})")
            return {"status": "processing", "transcript_id": transcript_id}

        elif aai_status == "error":
            # Transcrição falhou no AAI - invalidar cache
            logger.warning(f"❌ Transcrição AAI falhou: {transcript_id} - {aai_response.get('error')}")
            cache_path.unlink(missing_ok=True)
            return None

        return None

    # ==================== End AssemblyAI Cache Methods ====================

    # ==================== ElevenLabs Cache Methods ====================
    # Cache de resultados completos para evitar reprocessamento do mesmo arquivo
    # (ElevenLabs é síncrono - não há job_id para recuperação)

    def _get_elevenlabs_cache_dir(self) -> Path:
        """Retorna diretório de cache para transcrições ElevenLabs."""
        try:
            from app.core.config import settings
            base_dir = Path(settings.LOCAL_STORAGE_PATH) / "elevenlabs_transcripts"
        except Exception:
            base_dir = Path("./storage") / "elevenlabs_transcripts"
        base_dir.mkdir(parents=True, exist_ok=True)
        return base_dir

    def _get_elevenlabs_cache_path(self, file_hash: str) -> Path:
        """Retorna caminho do cache ElevenLabs para um arquivo específico."""
        return self._get_elevenlabs_cache_dir() / f"{file_hash}.json"

    def _get_elevenlabs_config_hash(
        self,
        language: str = "pt",
        diarize: bool = True,
        tag_audio_events: bool = True,
    ) -> str:
        """Calcula hash da configuração ElevenLabs para invalidação de cache."""
        config = {
            "language": language,
            "diarize": diarize,
            "tag_audio_events": tag_audio_events,
        }
        return hashlib.md5(json.dumps(config, sort_keys=True).encode()).hexdigest()[:8]

    def _save_elevenlabs_cache(
        self,
        file_path: str,
        config_hash: str,
        result: Dict[str, Any],
    ) -> None:
        """
        Salva resultado completo do ElevenLabs no cache.
        Como ElevenLabs é síncrono, cachea o resultado final (não há job_id).
        """
        file_hash = self._compute_file_hash(file_path)
        cache_path = self._get_elevenlabs_cache_path(file_hash)

        # Remover raw_response para economizar espaço (pode ser grande)
        result_to_cache = {k: v for k, v in result.items() if k != "raw_response"}

        cache_data = {
            "file_hash": file_hash,
            "file_name": Path(file_path).name,
            "file_size_bytes": Path(file_path).stat().st_size,
            "config_hash": config_hash,
            "cached_at": datetime.utcnow().isoformat() + "Z",
            "backend": "elevenlabs",
            "result": result_to_cache,
        }

        cache_path.write_text(json.dumps(cache_data, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info(f"💾 Cache ElevenLabs salvo: {file_hash[:8]}")

    def _check_elevenlabs_cache(
        self,
        file_path: str,
        config_hash: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Verifica se existe resultado ElevenLabs em cache para o arquivo.
        Retorna o resultado cacheado se config compatível, None caso contrário.
        """
        file_hash = self._compute_file_hash(file_path)
        cache_path = self._get_elevenlabs_cache_path(file_hash)

        if not cache_path.exists():
            return None

        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Erro ao ler cache ElevenLabs: {e}")
            return None

        # Verificar se config é compatível
        if cache.get("config_hash") != config_hash:
            logger.info(f"⚠️ Cache ElevenLabs existe mas config diferente: {file_hash[:8]}")
            return None

        result = cache.get("result")
        if result:
            logger.info(f"✅ Usando cache ElevenLabs: {file_hash[:8]}")
            result["from_cache"] = True
            return result

        return None

    # ==================== End ElevenLabs Cache Methods ====================

    # ==================== Whisper Server Cache Methods ====================
    # Cache para Whisper em servidor externo (RunPod, etc.)
    # Preparado para futuro - quando implementar servidor Whisper externo
    # Se o servidor for async (job_id + polling), usar padrão similar ao AAI
    # Se for síncrono, usar padrão similar ao ElevenLabs

    def _get_whisper_server_cache_dir(self) -> Path:
        """Retorna diretório de cache para transcrições Whisper (servidor externo)."""
        try:
            from app.core.config import settings
            base_dir = Path(settings.LOCAL_STORAGE_PATH) / "whisper_server_transcripts"
        except Exception:
            base_dir = Path("./storage") / "whisper_server_transcripts"
        base_dir.mkdir(parents=True, exist_ok=True)
        return base_dir

    def _get_whisper_server_cache_path(self, file_hash: str) -> Path:
        """Retorna caminho do cache Whisper Server para um arquivo específico."""
        return self._get_whisper_server_cache_dir() / f"{file_hash}.json"

    def _get_whisper_server_config_hash(
        self,
        language: str = "pt",
        model: str = "large-v3",
        beam_size: int = 5,
        word_timestamps: bool = True,
    ) -> str:
        """Calcula hash da configuração Whisper Server para invalidação de cache."""
        config = {
            "language": language,
            "model": model,
            "beam_size": beam_size,
            "word_timestamps": word_timestamps,
        }
        return hashlib.md5(json.dumps(config, sort_keys=True).encode()).hexdigest()[:8]

    def _save_whisper_server_cache(
        self,
        file_path: str,
        config_hash: str,
        result: Dict[str, Any],
        job_id: Optional[str] = None,
        status: str = "completed",
    ) -> None:
        """
        Salva resultado/job_id do Whisper Server no cache.

        Se o servidor for async (como RunPod):
        - Salva job_id imediatamente após submit (status="processing")
        - Atualiza com resultado quando completar (status="completed")

        Se for síncrono:
        - Salva resultado completo diretamente
        """
        file_hash = self._compute_file_hash(file_path)
        cache_path = self._get_whisper_server_cache_path(file_hash)

        # Remover campos grandes para economizar espaço
        result_to_cache = None
        if result:
            result_to_cache = {k: v for k, v in result.items() if k not in ("raw_response", "words")}

        cache_data = {
            "file_hash": file_hash,
            "file_name": Path(file_path).name,
            "file_size_bytes": Path(file_path).stat().st_size,
            "config_hash": config_hash,
            "job_id": job_id,
            "status": status,
            "submitted_at": datetime.utcnow().isoformat() + "Z" if status == "processing" else None,
            "completed_at": datetime.utcnow().isoformat() + "Z" if status == "completed" else None,
            "backend": "whisper_server",
            "result": result_to_cache,
        }

        cache_path.write_text(json.dumps(cache_data, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info(f"💾 Cache Whisper Server salvo: {file_hash[:8]} (status={status})")

    def _check_whisper_server_cache(
        self,
        file_path: str,
        config_hash: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Verifica se existe resultado/job Whisper Server em cache.

        Retorna:
        - Dict com resultado se completo e config compatível
        - Dict com {"status": "processing", "job_id": ...} se ainda processando
        - None se não há cache válido
        """
        file_hash = self._compute_file_hash(file_path)
        cache_path = self._get_whisper_server_cache_path(file_hash)

        if not cache_path.exists():
            return None

        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Erro ao ler cache Whisper Server: {e}")
            return None

        # Verificar se config é compatível
        if cache.get("config_hash") != config_hash:
            logger.info(f"⚠️ Cache Whisper Server existe mas config diferente: {file_hash[:8]}")
            return None

        status = cache.get("status")

        if status == "completed":
            result = cache.get("result")
            if result:
                logger.info(f"✅ Usando cache Whisper Server: {file_hash[:8]}")
                result["from_cache"] = True
                return result

        elif status == "processing":
            job_id = cache.get("job_id")
            if job_id:
                logger.info(f"🔄 Job Whisper Server em andamento: {job_id}")
                return {"status": "processing", "job_id": job_id}

        return None

    def _update_whisper_server_cache_status(
        self,
        file_hash: str,
        status: str,
        result: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Atualiza status do cache Whisper Server."""
        cache_path = self._get_whisper_server_cache_path(file_hash)
        if not cache_path.exists():
            return

        try:
            cache_data = json.loads(cache_path.read_text(encoding="utf-8"))
            cache_data["status"] = status
            if status == "completed":
                cache_data["completed_at"] = datetime.utcnow().isoformat() + "Z"
                if result:
                    result_to_cache = {k: v for k, v in result.items() if k not in ("raw_response", "words")}
                    cache_data["result"] = result_to_cache
            cache_path.write_text(json.dumps(cache_data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Falha ao atualizar cache Whisper Server: {e}")

    # ==================== End Whisper Server Cache Methods ====================

    # ==================== Whisper Server (RunPod) Integration ====================
    # Integração com servidor Whisper externo em GPU (RunPod, Modal, etc.)
    # API assíncrona: submit → job_id → polling → resultado

    def _get_whisper_server_url(self) -> Optional[str]:
        """Retorna URL do servidor Whisper externo se configurado."""
        try:
            from app.core.config import settings
            return getattr(settings, "WHISPER_SERVER_URL", None)
        except Exception:
            return os.environ.get("WHISPER_SERVER_URL")

    def _get_whisper_server_key(self) -> Optional[str]:
        """Retorna API key do servidor Whisper se configurado."""
        try:
            from app.core.config import settings
            return getattr(settings, "WHISPER_SERVER_API_KEY", None)
        except Exception:
            return os.environ.get("WHISPER_SERVER_API_KEY")

    def _is_whisper_server_available(self) -> bool:
        """Verifica se o servidor Whisper externo está configurado."""
        return bool(self._get_whisper_server_url() and self._get_whisper_server_key())

    async def _transcribe_whisper_server_with_progress(
        self,
        audio_path: str,
        emit: Callable[[str, int, str], Awaitable[None]],
        language: str = "pt",
        model: str = "large-v3",
        beam_size: int = 5,
        word_timestamps: bool = True,
        diarize: bool = True,
        start_progress: int = 25,
        end_progress: int = 60,
    ) -> Optional[Dict[str, Any]]:
        """
        Transcreve via servidor Whisper externo (RunPod) com progresso.

        API esperada do servidor:
        - POST /transcribe (multipart) → {"job_id": "xxx"}
        - GET /status/{job_id} → {"status": "processing|completed|error", "progress": 0-100}
        - GET /result/{job_id} → {"text": "...", "segments": [...], ...}

        Features:
        - Upload com progresso
        - Polling assíncrono com recovery
        - Cache de job_id para recuperação
        """
        import aiohttp
        import aiofiles

        server_url = self._get_whisper_server_url()
        api_key = self._get_whisper_server_key()

        if not server_url or not api_key:
            logger.warning("Whisper Server não configurado")
            return None

        headers = {"Authorization": f"Bearer {api_key}"}

        # Calcular config hash e verificar cache
        config_hash = self._get_whisper_server_config_hash(
            language=language,
            model=model,
            beam_size=beam_size,
            word_timestamps=word_timestamps,
        )

        # Verificar cache (job existente ou resultado completo)
        cached = self._check_whisper_server_cache(audio_path, config_hash)
        if cached:
            if cached.get("status") == "completed" and cached.get("result"):
                await emit("transcription", end_progress, "✅ Usando transcrição em cache (Whisper Server)")
                result = cached.get("result", {})
                result["from_cache"] = True
                return result
            elif cached.get("status") == "processing":
                job_id = cached.get("job_id")
                if job_id:
                    await emit("transcription", start_progress, f"🔄 Retomando job Whisper: {job_id[:8]}...")
                    logger.info(f"🔄 Retomando polling de job Whisper Server: {job_id}")
                    # Ir direto para polling
                    return await self._poll_whisper_server_job(
                        server_url=server_url,
                        headers=headers,
                        job_id=job_id,
                        emit=emit,
                        audio_path=audio_path,
                        config_hash=config_hash,
                        poll_start=start_progress,
                        poll_end=end_progress,
                    )

        # Calcular progresso
        progress_range = end_progress - start_progress
        upload_end = start_progress + int(progress_range * 0.3)
        poll_start = upload_end

        # 1. Upload do arquivo
        file_size = os.path.getsize(audio_path)
        file_size_mb = file_size / (1024 * 1024)
        await emit("transcription", start_progress, f"📤 Enviando para Whisper Server (0/{file_size_mb:.0f}MB)...")

        start_time = time.time()

        try:
            async with aiohttp.ClientSession() as session:
                # Preparar form data
                data = aiohttp.FormData()
                async with aiofiles.open(audio_path, "rb") as f:
                    file_content = await f.read()
                data.add_field(
                    "file",
                    file_content,
                    filename=Path(audio_path).name,
                    content_type="audio/mpeg",
                )
                data.add_field("language", language)
                data.add_field("model", model)
                data.add_field("beam_size", str(beam_size))
                data.add_field("word_timestamps", str(word_timestamps).lower())
                data.add_field("diarize", str(diarize).lower())

                # Submit job
                async with session.post(
                    f"{server_url}/transcribe",
                    headers=headers,
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=300),
                ) as resp:
                    if resp.status != 200 and resp.status != 202:
                        error_text = await resp.text()
                        logger.error(f"Whisper Server submit failed: {resp.status} - {error_text[:200]}")
                        return None

                    result = await resp.json()
                    job_id = result.get("job_id")

                    if not job_id:
                        logger.error("Whisper Server não retornou job_id")
                        return None

        except Exception as e:
            logger.error(f"Whisper Server upload error: {e}")
            return None

        upload_time = time.time() - start_time
        logger.info(f"✅ Whisper Server upload completo em {upload_time:.1f}s - job_id: {job_id}")
        await emit("transcription", upload_end, f"✅ Upload completo ({upload_time:.0f}s)")

        # SALVAR CACHE IMEDIATAMENTE
        self._save_whisper_server_cache(
            file_path=audio_path,
            config_hash=config_hash,
            result=None,
            job_id=job_id,
            status="processing",
        )

        # 2. Polling
        return await self._poll_whisper_server_job(
            server_url=server_url,
            headers=headers,
            job_id=job_id,
            emit=emit,
            audio_path=audio_path,
            config_hash=config_hash,
            poll_start=poll_start,
            poll_end=end_progress,
        )

    async def _poll_whisper_server_job(
        self,
        server_url: str,
        headers: Dict[str, str],
        job_id: str,
        emit: Callable[[str, int, str], Awaitable[None]],
        audio_path: str,
        config_hash: str,
        poll_start: int,
        poll_end: int,
    ) -> Optional[Dict[str, Any]]:
        """Polling de job Whisper Server até completar."""
        import aiohttp

        poll_count = 0
        max_polls = 2400  # ~2 horas (3s interval)
        poll_start_time = time.time()

        async with aiohttp.ClientSession() as session:
            while poll_count < max_polls:
                try:
                    async with session.get(
                        f"{server_url}/status/{job_id}",
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as resp:
                        if resp.status != 200:
                            logger.warning(f"Whisper Server status check failed: {resp.status}")
                            poll_count += 1
                            await asyncio.sleep(5)
                            continue

                        status_data = await resp.json()

                except Exception as e:
                    logger.warning(f"Whisper Server poll error: {e}")
                    poll_count += 1
                    await asyncio.sleep(5)
                    continue

                status = status_data.get("status")
                progress_pct = status_data.get("progress", 0)
                poll_count += 1
                elapsed_min = (time.time() - poll_start_time) / 60

                # Atualizar progresso
                progress = poll_start + int((progress_pct / 100) * (poll_end - poll_start))

                if poll_count % 10 == 0:
                    if status == "queued":
                        msg = f"⏳ Na fila do Whisper Server... ({elapsed_min:.0f}min)"
                    elif status == "processing":
                        msg = f"🎙️ Transcrevendo ({progress_pct}%, {elapsed_min:.0f}min)"
                    else:
                        msg = f"⏳ Processando... ({elapsed_min:.0f}min)"
                    await emit("transcription", progress, msg)
                    logger.info(f"⏳ Whisper Server polling... status={status}, progress={progress_pct}%, elapsed={elapsed_min:.1f}min")

                if status == "completed":
                    logger.info(f"✅ Whisper Server completou após {poll_count} polls ({elapsed_min:.1f}min)")

                    # Buscar resultado
                    try:
                        async with session.get(
                            f"{server_url}/result/{job_id}",
                            headers=headers,
                            timeout=aiohttp.ClientTimeout(total=60),
                        ) as result_resp:
                            if result_resp.status != 200:
                                logger.error(f"Whisper Server result fetch failed: {result_resp.status}")
                                return None

                            result = await result_resp.json()

                    except Exception as e:
                        logger.error(f"Whisper Server result fetch error: {e}")
                        return None

                    # Atualizar cache
                    file_hash = self._compute_file_hash(audio_path)
                    self._update_whisper_server_cache_status(file_hash, "completed", result)

                    # Formatar resultado
                    return self._format_whisper_server_result(result, job_id, time.time() - poll_start_time)

                elif status == "error":
                    error_msg = status_data.get("error", "Unknown error")
                    logger.error(f"Whisper Server error: {error_msg}")
                    # Invalidar cache
                    file_hash = self._compute_file_hash(audio_path)
                    cache_path = self._get_whisper_server_cache_path(file_hash)
                    cache_path.unlink(missing_ok=True)
                    return None

                await asyncio.sleep(3)

        logger.error(f"Whisper Server timeout: max polls atingido")
        return None

    def _format_whisper_server_result(
        self,
        result: Dict[str, Any],
        job_id: str,
        elapsed: float,
    ) -> Dict[str, Any]:
        """Formata resultado do Whisper Server para padrão interno."""
        segments = result.get("segments", [])
        words = result.get("words", [])
        text = result.get("text", "")

        # Extrair speakers se disponível
        speaker_set = {}
        for seg in segments:
            speaker = seg.get("speaker", "A")
            if speaker not in speaker_set:
                speaker_set[speaker] = {"label": speaker, "role": ""}

        # Calcular duração
        audio_duration = 0
        if segments:
            audio_duration = max(s.get("end", 0) for s in segments)

        return {
            "text": text,
            "segments": segments,
            "words": words,
            "speakers": list(speaker_set.values()),
            "elapsed_seconds": elapsed,
            "audio_duration": audio_duration,
            "num_speakers": len(speaker_set),
            "backend": "whisper_server",
            "job_id": job_id,
            "raw_response": result,
        }

    def _transcribe_whisper_server_sync(
        self,
        audio_path: str,
        language: str = "pt",
        model: str = "large-v3",
        beam_size: int = 5,
        word_timestamps: bool = True,
        diarize: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        Versão síncrona da transcrição via Whisper Server.
        Para uso em contextos não-async.
        """
        import requests as http_requests

        server_url = self._get_whisper_server_url()
        api_key = self._get_whisper_server_key()

        if not server_url or not api_key:
            logger.warning("Whisper Server não configurado")
            return None

        headers = {"Authorization": f"Bearer {api_key}"}

        # Verificar cache
        config_hash = self._get_whisper_server_config_hash(
            language=language,
            model=model,
            beam_size=beam_size,
            word_timestamps=word_timestamps,
        )

        cached = self._check_whisper_server_cache(audio_path, config_hash)
        if cached:
            if cached.get("status") == "completed" and cached.get("result"):
                logger.info(f"✅ Usando cache Whisper Server (sync)")
                result = cached.get("result", {})
                result["from_cache"] = True
                return result
            elif cached.get("status") == "processing":
                job_id = cached.get("job_id")
                if job_id:
                    logger.info(f"🔄 Retomando job Whisper Server (sync): {job_id}")
                    # Ir para polling
                    return self._poll_whisper_server_job_sync(
                        server_url, headers, job_id, audio_path, config_hash
                    )

        # 1. Upload
        start_time = time.time()
        file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
        logger.info(f"📤 Whisper Server: uploading {Path(audio_path).name} ({file_size_mb:.1f}MB)...")

        try:
            with open(audio_path, "rb") as f:
                files = {"file": (Path(audio_path).name, f)}
                data = {
                    "language": language,
                    "model": model,
                    "beam_size": str(beam_size),
                    "word_timestamps": str(word_timestamps).lower(),
                    "diarize": str(diarize).lower(),
                }
                resp = http_requests.post(
                    f"{server_url}/transcribe",
                    headers=headers,
                    files=files,
                    data=data,
                    timeout=300,
                )

            if resp.status_code not in (200, 202):
                logger.error(f"Whisper Server submit failed: {resp.status_code}")
                return None

            job_id = resp.json().get("job_id")
            if not job_id:
                logger.error("Whisper Server não retornou job_id")
                return None

        except Exception as e:
            logger.error(f"Whisper Server upload error: {e}")
            return None

        logger.info(f"✅ Whisper Server upload completo - job_id: {job_id}")

        # Salvar cache
        self._save_whisper_server_cache(
            file_path=audio_path,
            config_hash=config_hash,
            result=None,
            job_id=job_id,
            status="processing",
        )

        # 2. Polling
        return self._poll_whisper_server_job_sync(
            server_url, headers, job_id, audio_path, config_hash
        )

    def _poll_whisper_server_job_sync(
        self,
        server_url: str,
        headers: Dict[str, str],
        job_id: str,
        audio_path: str,
        config_hash: str,
    ) -> Optional[Dict[str, Any]]:
        """Polling síncrono de job Whisper Server."""
        import requests as http_requests

        poll_count = 0
        max_polls = 2400
        poll_start_time = time.time()

        while poll_count < max_polls:
            try:
                resp = http_requests.get(
                    f"{server_url}/status/{job_id}",
                    headers=headers,
                    timeout=30,
                )
                if resp.status_code != 200:
                    poll_count += 1
                    time.sleep(5)
                    continue

                status_data = resp.json()

            except Exception as e:
                logger.warning(f"Whisper Server poll error (sync): {e}")
                poll_count += 1
                time.sleep(5)
                continue

            status = status_data.get("status")
            progress_pct = status_data.get("progress", 0)
            poll_count += 1

            if poll_count % 20 == 0:
                elapsed_min = (time.time() - poll_start_time) / 60
                logger.info(f"⏳ Whisper Server polling (sync)... status={status}, progress={progress_pct}%, elapsed={elapsed_min:.1f}min")

            if status == "completed":
                elapsed = time.time() - poll_start_time
                logger.info(f"✅ Whisper Server completou (sync) após {poll_count} polls")

                # Buscar resultado
                try:
                    result_resp = http_requests.get(
                        f"{server_url}/result/{job_id}",
                        headers=headers,
                        timeout=60,
                    )
                    if result_resp.status_code != 200:
                        return None
                    result = result_resp.json()
                except Exception as e:
                    logger.error(f"Whisper Server result fetch error (sync): {e}")
                    return None

                # Atualizar cache
                file_hash = self._compute_file_hash(audio_path)
                self._update_whisper_server_cache_status(file_hash, "completed", result)

                return self._format_whisper_server_result(result, job_id, elapsed)

            elif status == "error":
                logger.error(f"Whisper Server error: {status_data.get('error')}")
                file_hash = self._compute_file_hash(audio_path)
                cache_path = self._get_whisper_server_cache_path(file_hash)
                cache_path.unlink(missing_ok=True)
                return None

            time.sleep(3)

        logger.error(f"Whisper Server timeout (sync): max polls atingido")
        return None

    # ==================== End Whisper Server Integration ====================

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

    async def _infer_speaker_roles_with_llm(
        self,
        segments: list[dict],
        goal: str,
        vomo,
        max_samples_per_speaker: int = 5,
    ) -> dict[str, str]:
        """
        Infere o papel de cada speaker (Juiz, Advogado, Testemunha, etc.) baseado no conteúdo das falas.

        Args:
            segments: Lista de segmentos com speaker_label e text
            goal: Objetivo da audiência (ex: "alegacoes_finais", "instrucao")
            vomo: Instância do Vomo para chamadas LLM
            max_samples_per_speaker: Máximo de amostras por speaker

        Returns:
            Dict mapeando speaker_label para role inferido
        """
        if not segments:
            return {}

        # Agrupar segmentos por speaker e pegar amostras
        speaker_samples: dict[str, list[str]] = {}
        for seg in segments:
            label = seg.get("speaker_label", "")
            text = (seg.get("text") or "").strip()
            if not label or not text:
                continue
            if label not in speaker_samples:
                speaker_samples[label] = []
            if len(speaker_samples[label]) < max_samples_per_speaker:
                # Limitar tamanho de cada amostra
                speaker_samples[label].append(text[:300])

        if not speaker_samples:
            return {}

        # Construir prompt para inferência
        samples_text = []
        for label, texts in sorted(speaker_samples.items()):
            samples_text.append(f"{label}:\n" + "\n".join(f'  - "{t}"' for t in texts))

        goal_context = {
            "alegacoes_finais": "audiência de instrução e julgamento (alegações finais)",
            "instrucao": "audiência de instrução (oitiva de testemunhas/partes)",
            "conciliacao": "audiência de conciliação",
            "custodia": "audiência de custódia",
            "interrogatorio": "interrogatório do réu",
        }.get(goal, "audiência judicial")

        prompt = f"""Analise as falas de uma {goal_context} e identifique o PAPEL de cada falante.

PAPÉIS POSSÍVEIS (use exatamente estes termos):
- Juiz (quem conduz, defere, indefere, decide)
- Advogado (quem faz perguntas, representa parte)
- Promotor (Ministério Público, acusação)
- Defensor (advogado de defesa, defensor público)
- Testemunha (quem responde perguntas sobre fatos)
- Perito (quem presta esclarecimentos técnicos)
- Parte (autor ou réu falando diretamente)
- Escrivão (quem faz registros, chama partes)
- Outro (se não for possível identificar)

FALAS POR SPEAKER:
{chr(10).join(samples_text)}

Responda APENAS em JSON, sem explicações:
{{"roles": {{"SPEAKER 1": "Juiz", "SPEAKER 2": "Testemunha"}}}}
"""

        try:
            parsed = await self._llm_generate_json(vomo, prompt, max_tokens=500, temperature=0.1)
            if parsed and "roles" in parsed:
                return {str(k): str(v) for k, v in parsed["roles"].items()}
        except Exception as e:
            logger.warning(f"Falha ao inferir papéis: {e}")

        return {}

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

    def _render_hearing_markdown(self, hearing_payload: dict, *, include_timestamps: bool = True) -> str:
        speakers = {sp["speaker_id"]: sp for sp in hearing_payload.get("speakers", [])}
        segments = hearing_payload.get("segments", []) or []
        segment_map = {seg.get("id"): seg for seg in segments if seg.get("id")}
        blocks = hearing_payload.get("blocks", []) or []

        def _render_segment_line(seg: dict) -> str:
            speaker_id = seg.get("speaker_id")
            speaker = speakers.get(speaker_id, {})
            name = speaker.get("name") or seg.get("speaker_label", "SPEAKER")
            role = speaker.get("role")
            label = f"{name} ({role})" if role else name
            ts = seg.get("timestamp_hint")
            ts_prefix = f"[{ts}] " if (include_timestamps and ts) else ""
            text = (seg.get("text") or "").strip()
            if not text:
                return ""
            return f"**{label}**: {ts_prefix}{text}"

        # Preferir markdown por blocos (chunking natural) quando disponível.
        if blocks:
            lines: list[str] = []
            for idx, block in enumerate(blocks, start=1):
                act_type = (block.get("act_type") or "turn").strip()
                speaker_label = (block.get("speaker_label") or "").strip()
                topics = block.get("topics") or []
                topic_hint = ""
                if topics:
                    topic_hint = f" — {topics[0]}"
                speaker_hint = f" ({speaker_label})" if speaker_label else ""
                lines.append(f"## Bloco {idx:02d} — {act_type}{topic_hint}{speaker_hint}")

                rendered_any = False
                for seg_id in (block.get("segment_ids") or []):
                    seg = segment_map.get(seg_id)
                    if not seg:
                        continue
                    line = _render_segment_line(seg)
                    if line:
                        rendered_any = True
                        lines.append(line)

                if not rendered_any:
                    # Fallback: usar texto agregado do bloco se não conseguirmos reconstruir por IDs.
                    block_text = (block.get("text") or "").strip()
                    if block_text:
                        lines.append(block_text)

                lines.append("")

            return "\n\n".join([ln for ln in lines if ln is not None]).strip()

        # Fallback legacy: lista linear por segmentos
        lines: list[str] = []
        for seg in segments:
            line = _render_segment_line(seg)
            if line:
                lines.append(line)
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
        include_timestamps: bool = True,
        allow_indirect: bool = False,
        allow_summary: bool = False,
        use_cache: bool = True,
        auto_apply_fixes: bool = True,
        auto_apply_content_fixes: bool = False,
        skip_legal_audit: bool = False,
        skip_fidelity_audit: bool = False,
        skip_sources_audit: bool = False,
        on_progress: Optional[Callable[[str, int, str], Awaitable[None]]] = None,
        language: Optional[str] = None,
        output_language: Optional[str] = None,
        speaker_roles: Optional[list] = None,
        speakers_expected: Optional[int] = None,
        transcription_engine: str = "whisper",
        allow_provider_fallback: Optional[bool] = None,
    ) -> dict:
        async def emit(stage: str, progress: int, message: str):
            if on_progress:
                await on_progress(stage, progress, message)

        allow_provider_fallback = self._enforce_fidelity_critical_fallback(
            mode=format_mode,
            allow_provider_fallback=allow_provider_fallback,
        )

        # Determinar motor de transcrição
        _requested_engine_hearing = (transcription_engine or "whisper").strip().lower()
        _use_elevenlabs_hearing = _requested_engine_hearing == "elevenlabs" and self._get_elevenlabs_key() is not None
        _use_aai_hearing = _requested_engine_hearing == "assemblyai" and self._get_assemblyai_key() is not None
        _use_whisper_hearing = not _use_aai_hearing and not _use_elevenlabs_hearing
        logger.info(f"🎤 Motor de transcrição (hearing): {transcription_engine} [EL={_use_elevenlabs_hearing}] [AAI={_use_aai_hearing}]")

        # Inicializar VomoMLX (necessário para otimização de áudio e fallback)
        await emit("initializing", 0, "🚀 Inicializando motor de transcrição...")
        if _requested_engine_hearing in {"assemblyai", "elevenlabs"}:
            _provider_available = (
                (_requested_engine_hearing == "assemblyai" and self._get_assemblyai_key() is not None)
                or (_requested_engine_hearing == "elevenlabs" and self._get_elevenlabs_key() is not None)
            )
            if not _provider_available:
                _can_switch_missing_provider = self._is_provider_fallback_allowed(
                    requested_engine=transcription_engine,
                    from_provider=_requested_engine_hearing,
                    to_provider="whisper",
                    allow_provider_fallback=allow_provider_fallback,
                )
                if not _can_switch_missing_provider:
                    raise RuntimeError(
                        f"{_requested_engine_hearing} indisponível e fallback para Whisper foi desabilitado."
                    )
                await emit(
                    "initializing",
                    3,
                    self._provider_switch_message(
                        from_provider=_requested_engine_hearing,
                        to_provider="whisper",
                        allow_provider_fallback=allow_provider_fallback,
                    ),
                )
        vomo = await self._get_vomo_with_progress(
            emit=emit,
            model_selection=model_selection,
            thinking_level=thinking_level,
            ready_message="✅ Motor de transcrição pronto",
        )
        # Setar idioma antes de qualquer chamada de transcrição
        vomo._current_language = (language or "pt").strip().lower()
        vomo._output_language = (output_language or "").strip().lower() or None
        vomo._current_mode = (format_mode or "AUDIENCIA").strip().upper()
        logger.info(f"🎤 Iniciando transcrição de audiência: {file_path} [case_id={case_id}] [lang={vomo._current_language}]")
        diarization_enabled, diarization_required = (False, False)
        try:
            diarization_enabled, diarization_required = vomo.resolve_diarization_policy(format_mode)
            vomo.set_diarization_policy(enabled=diarization_enabled, required=diarization_required)
        except Exception:
            pass

        include_timestamps = bool(include_timestamps)
        cache_hash = None
        transcription_text = None
        asr_segments = []
        cache_hit = False
        if use_cache:
            try:
                cache_hash = self._compute_file_hash(file_path)
                transcription_text = self._load_cached_raw(cache_hash, high_accuracy, diarization_enabled)
                cache_hit = bool(transcription_text)
                if cache_hit:
                    logger.info("♻️ RAW cache hit (pulando transcrição)")
            except Exception as cache_error:
                logger.warning(f"Falha ao carregar cache RAW: {cache_error}")
                transcription_text = None

        await emit("audio_optimization", 0, "Otimizando áudio...")
        estimated_total = 120.0
        done_event = asyncio.Event()
        ticker = asyncio.create_task(
            self._emit_progress_while_running(
                emit,
                done_event,
                "audio_optimization",
                0,
                20,
                "Otimizando áudio (FFmpeg)",
                estimated_total,
                interval_seconds=3.0,
            )
        )
        try:
            audio_path = await asyncio.to_thread(vomo.optimize_audio, file_path)
        finally:
            done_event.set()
            try:
                await ticker
            except Exception:
                pass
        await emit("audio_optimization", 20, "Áudio otimizado ✓")

        _hearing_aai_result = None
        _hearing_elevenlabs_result = None
        _hearing_whisper_future = None

        if cache_hit:
            await emit("transcription", 30, "♻️ RAW cache encontrado — pulando transcrição")
        else:
            # Usar ElevenLabs se selecionado pelo usuário e chave disponível
            if _use_elevenlabs_hearing:
                await emit("transcription", 30, "Transcrevendo com ElevenLabs Scribe...")
                try:
                    _hearing_elevenlabs_result = await asyncio.to_thread(
                        self._transcribe_elevenlabs_scribe,
                        audio_path,
                        language or "pt",
                        True,  # diarize
                        True,  # tag_audio_events
                    )
                except Exception as el_exc:
                    logger.warning(f"ElevenLabs falhou: {el_exc}")
                    _hearing_elevenlabs_result = None

                if _hearing_elevenlabs_result:
                    transcription_text = _hearing_elevenlabs_result.get("text", "")
                    asr_segments = _hearing_elevenlabs_result.get("segments", [])
                    await emit("transcription", 55, f"ElevenLabs: {len(asr_segments)} segments, {_hearing_elevenlabs_result.get('num_speakers', 0)} speakers ✓")

            # Usar AssemblyAI se selecionado pelo usuário e chave disponível
            aai_key = self._get_assemblyai_key()
            if _use_aai_hearing and aai_key and not _hearing_elevenlabs_result:
                await emit("transcription", 30, "Transcrevendo com AssemblyAI Universal-2...")

                # Disparar Whisper local em paralelo para benchmark
                if self._is_benchmark_enabled():
                    logger.info("📊 Benchmark: disparando Whisper local em paralelo")
                    _hearing_whisper_future = self._start_whisper_benchmark_for_hearing(
                        vomo, audio_path, high_accuracy
                    )

                try:
                    _hearing_aai_result = await asyncio.to_thread(
                        self._transcribe_assemblyai_with_roles,
                        audio_path,
                        speaker_roles,
                        (language or "pt"),
                        speakers_expected,
                        format_mode,  # modo para timestamp_interval
                    )
                except Exception as aai_exc:
                    logger.warning(f"AssemblyAI falhou: {aai_exc}")
                    _hearing_aai_result = None

            if _hearing_aai_result:
                # AAI como primário: usar resultado
                transcription_text = _hearing_aai_result.get("text", "")
                asr_segments = _hearing_aai_result.get("segments", [])
                await emit("transcription", 55, f"AssemblyAI: {len(asr_segments)} utterances, {_hearing_aai_result.get('num_speakers', 0)} speakers ✓")

                # Salvar resultado bruto do AAI no storage do caso
                try:
                    case_dir = self._get_hearing_case_dir(case_id)
                    aai_raw_path = case_dir / "assemblyai_raw.json"
                    aai_raw_path.write_text(
                        json.dumps(_hearing_aai_result, ensure_ascii=False, indent=2, default=str),
                        encoding="utf-8",
                    )
                    aai_txt_path = case_dir / "assemblyai_transcript.txt"
                    aai_lines = []
                    prev_spk = None
                    for seg in asr_segments:
                        spk = seg.get("speaker_label", "")
                        if spk != prev_spk:
                            aai_lines.append(f"\n{spk}")
                            prev_spk = spk
                        start = seg.get("start", 0)
                        h, m, s = int(start // 3600), int((start % 3600) // 60), int(start % 60)
                        aai_lines.append(f"[{h:02d}:{m:02d}:{s:02d}] {seg.get('text', '')}")
                    aai_txt_path.write_text("\n".join(aai_lines).strip(), encoding="utf-8")
                except Exception as save_exc:
                    logger.warning(f"Falha ao salvar AAI raw: {save_exc}")

            if not _hearing_aai_result and not _hearing_elevenlabs_result:
                if not _use_whisper_hearing:
                    _source_provider = "assemblyai" if _use_aai_hearing else "elevenlabs"
                    _can_switch_to_whisper = self._is_provider_fallback_allowed(
                        requested_engine=transcription_engine,
                        from_provider=_source_provider,
                        to_provider="whisper",
                        allow_provider_fallback=allow_provider_fallback,
                    )
                    if not _can_switch_to_whisper:
                        raise RuntimeError(
                            f"{_source_provider} indisponível e fallback para Whisper foi desabilitado."
                        )
                    await emit(
                        "transcription",
                        30,
                        self._provider_switch_message(
                            from_provider=_source_provider,
                            to_provider="whisper",
                            allow_provider_fallback=allow_provider_fallback,
                        ),
                    )
                # Whisper local (fluxo principal ou fallback)
                engine_msg = "Whisper MLX" if _use_whisper_hearing else "Whisper MLX (fallback)"
                await emit("transcription", 30, f"Transcrevendo com {engine_msg}...")
                structured = None
                if high_accuracy and hasattr(vomo, "transcribe_beam_with_segments"):
                    structured = await asyncio.to_thread(vomo.transcribe_beam_with_segments, audio_path)
                elif hasattr(vomo, "transcribe_with_segments"):
                    structured = await asyncio.to_thread(vomo.transcribe_with_segments, audio_path)

                if structured:
                    transcription_text = structured.get("text") or ""
                    asr_segments = structured.get("segments") or []
                else:
                    transcribe_file_fn = getattr(vomo, "transcribe_file", None)
                    if callable(transcribe_file_fn):
                        transcription_text = await asyncio.to_thread(
                            transcribe_file_fn,
                            audio_path,
                            mode=format_mode,
                            high_accuracy=high_accuracy,
                            language=language,
                        )
                    else:
                        transcribe_fn = getattr(vomo, "transcribe", None)
                        if callable(transcribe_fn):
                            transcription_text = await asyncio.to_thread(
                                transcribe_fn,
                                audio_path,
                            )
                        else:
                            raise AttributeError("Vomo transcriber missing transcribe_file/transcribe")
                    asr_segments = []

            if use_cache and cache_hash:
                self._save_cached_raw(
                    cache_hash,
                    high_accuracy,
                    diarization_enabled,
                    transcription_text,
                    Path(file_path).name,
                )
        await emit("transcription", 60, "Transcrição concluída ✓")

        await emit("structuring", 70, "Estruturando segmentos, falantes e evidências...")
        if asr_segments:
            segments = self._build_hearing_segments_from_asr(asr_segments)
        else:
            segments = self._build_hearing_segments(vomo, transcription_text)

        segments_no_ts = None
        if not include_timestamps:
            ts_leading_re = re.compile(r"^\[\d{1,2}:\d{2}(?::\d{2})?\]\s*")
            segments_no_ts = []
            for seg in segments:
                try:
                    new_seg = dict(seg)
                    text = (new_seg.get("text") or "").strip()
                    if text:
                        new_seg["text"] = ts_leading_re.sub("", text).strip()
                    segments_no_ts.append(new_seg)
                except Exception:
                    segments_no_ts.append(seg)

        speaker_labels = sorted({seg["speaker_label"] for seg in segments})
        registry = self._load_speaker_registry(case_id)
        speakers, label_to_id = self._ensure_registry_speakers(registry, speaker_labels)

        # Inferir papéis dos speakers via LLM (substitui enrollment de voz)
        await emit("structuring", 72, "Inferindo papéis dos falantes via IA...")
        inferred_roles = await self._infer_speaker_roles_with_llm(segments, goal, vomo)

        # Aplicar papéis inferidos ao registry
        for sp in registry.get("speakers", []):
            label = sp.get("label")
            if label and label in inferred_roles:
                sp["role"] = inferred_roles[label]
                sp["source"] = "llm_inference"

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
                "include_timestamps": include_timestamps,
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
        transcript_markdown = self._render_hearing_markdown(hearing_payload, include_timestamps=True)
        transcript_markdown_no_ts = None
        if not include_timestamps:
            payload_no_ts = dict(hearing_payload)
            if segments_no_ts is not None:
                payload_no_ts["segments"] = segments_no_ts
            transcript_markdown_no_ts = self._render_hearing_markdown(payload_no_ts, include_timestamps=False)

            def _strip_timestamps_from_markdown(text: Optional[str]) -> Optional[str]:
                if not text:
                    return text
                # Remove timestamp after speaker label and standalone timestamps.
                text = re.sub(
                    r"(?m)^(\\*\\*[^\\n]*\\*\\*:\\s*)\\[\\d{1,2}:\\d{2}(?::\\d{2})?\\]\\s*",
                    r"\\1",
                    text,
                )
                text = re.sub(r"(?m)^\\[\\d{1,2}:\\d{2}(?::\\d{2})?\\]\\s*", "", text)
                return text

            transcript_markdown_no_ts = _strip_timestamps_from_markdown(transcript_markdown_no_ts)

        hearing_payload["transcript_markdown"] = transcript_markdown
        structured_path.write_text(json.dumps(hearing_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        if include_timestamps:
            format_source_text = transcript_markdown or (transcription_text or "")
            format_source_label = "transcript_markdown" if transcript_markdown else "raw_transcript"
        else:
            format_source_text = transcript_markdown_no_ts or transcript_markdown or (transcription_text or "")
            format_source_label = "transcript_markdown_no_timestamps" if transcript_markdown_no_ts else ("transcript_markdown" if transcript_markdown else "raw_transcript")

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
        if not include_timestamps and transcript_markdown_no_ts:
            clean_transcript_path = run_dir / "hearing_transcript_no_timestamps.md"
            clean_transcript_path.write_text(transcript_markdown_no_ts, encoding="utf-8")
            report_paths["transcript_no_timestamps_path"] = str(clean_transcript_path)

        if format_enabled:
            await emit("formatting", 75, "Formatando texto da audiência...")
            llm_warning: Optional[str] = None
            llm_fallback = False
            try:
                formatted_text, vomo = await self._run_llm_format_with_resilience(
                    vomo=vomo,
                    source_text=format_source_text,
                    video_name=video_name,
                    output_folder=str(run_dir),
                    mode=format_mode_normalized,
                    custom_prompt=custom_prompt,
                    disable_tables=False,
                    progress_callback=emit,
                    skip_audit=skip_legal_audit,
                    skip_fidelity_audit=skip_fidelity_audit,
                    skip_sources_audit=skip_sources_audit,
                    model_selection=model_selection,
                    thinking_level=thinking_level,
                    include_timestamps=bool(include_timestamps),
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
                                    model_selection=model_selection,
                                    mode=format_mode_normalized,
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

        # Benchmark: finalizar comparação AAI vs Whisper em background
        if _hearing_aai_result and _hearing_whisper_future is not None:
            case_dir = self._get_hearing_case_dir(case_id)
            self._finalize_hearing_benchmark(
                aai_result=_hearing_aai_result,
                whisper_future=_hearing_whisper_future,
                output_dir=str(case_dir),
                video_name=Path(file_path).stem,
                audio_path=audio_path,
            )

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
