"""
Citation Validator Subagent (Haiku) with safe deterministic fallback.

Runs a lightweight subagent focused on citation consistency and coverage.
If model execution is unavailable, falls back to deterministic checks.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from loguru import logger

from app.services.ai.shared.sse_protocol import SSEEventType


_CITATION_KEY_PATTERN = re.compile(r"\[(\d{1,3})\]")


def _extract_json_strict(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    raw = text.strip()

    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw, flags=re.IGNORECASE)
    if fence:
        raw = fence.group(1).strip()

    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        pass

    block = re.search(r"(\{[\s\S]*\})", raw)
    if not block:
        return None
    try:
        data = json.loads(block.group(1))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _deterministic_baseline(document_text: str, citations_map: Any) -> Dict[str, Any]:
    used = {
        str(match)
        for match in _CITATION_KEY_PATTERN.findall(document_text or "")
        if str(match).isdigit()
    }
    used_keys = sorted(used, key=lambda k: int(k))

    citation_dict = citations_map if isinstance(citations_map, dict) else {}
    available_keys = [str(k) for k in citation_dict.keys() if str(k).isdigit()]
    available_keys = sorted(set(available_keys), key=lambda k: int(k))

    missing_keys = [k for k in used_keys if k not in citation_dict]
    orphan_keys = [k for k in available_keys if k not in used]

    total_used = len(used_keys)
    total_missing = len(missing_keys)
    coverage = 1.0 if total_used == 0 else max(0.0, 1.0 - (total_missing / total_used))

    return {
        "used_keys": used_keys,
        "missing_keys": missing_keys,
        "orphan_keys": orphan_keys,
        "total_used": total_used,
        "total_missing": total_missing,
        "total_orphans": len(orphan_keys),
        "coverage": round(coverage, 3),
    }


@dataclass
class _SubagentSession:
    executor: Any
    created_at: float
    last_used_at: float
    runs: int = 0


class CitationValidatorSubagentPool:
    """Small in-memory pool to reuse subagent executors across validations."""

    def __init__(self, model: str = "claude-haiku-4-5", ttl_seconds: int = 1800, max_sessions: int = 16):
        self.model = model
        self.ttl_seconds = ttl_seconds
        self.max_sessions = max_sessions
        self._sessions: Dict[str, _SubagentSession] = {}
        self._lock = asyncio.Lock()

    async def _get_or_create_session(self, session_key: str):
        now = time.time()
        async with self._lock:
            self._prune_locked(now)
            existing = self._sessions.get(session_key)
            if existing:
                existing.last_used_at = now
                existing.runs += 1
                return existing.executor

            executor = self._create_executor()
            if executor is None:
                return None

            self._sessions[session_key] = _SubagentSession(
                executor=executor,
                created_at=now,
                last_used_at=now,
                runs=1,
            )
            return executor

    def _prune_locked(self, now: float) -> None:
        stale_keys = [
            key
            for key, session in self._sessions.items()
            if (now - session.last_used_at) > self.ttl_seconds
        ]
        for key in stale_keys:
            self._sessions.pop(key, None)

        if len(self._sessions) <= self.max_sessions:
            return

        by_oldest = sorted(self._sessions.items(), key=lambda item: item[1].last_used_at)
        overflow = len(self._sessions) - self.max_sessions
        for key, _session in by_oldest[:overflow]:
            self._sessions.pop(key, None)

    def _create_executor(self):
        try:
            from app.services.ai.claude_agent.executor import AgentConfig, ClaudeAgentExecutor
            from app.services.ai.shared import ToolExecutionContext
        except Exception as exc:
            logger.warning(f"Citation validator could not import executor: {exc}")
            return None

        config = AgentConfig(
            model=self.model,
            max_iterations=3,
            max_tokens=2200,
            enable_checkpoints=False,
            use_sdk=False,
            enable_thinking=False,
            enable_code_execution=False,
        )
        executor = ClaudeAgentExecutor(config=config)

        # Keep toolset minimal for consistency and cost.
        try:
            executor.load_unified_tools(
                include_mcp=False,
                tool_names=["verify_citation"],
                execution_context=ToolExecutionContext(
                    user_id="citation-validator",
                    tenant_id="citation-validator",
                ),
            )
        except Exception as exc:
            logger.debug(f"Citation validator subagent loaded without tools: {exc}")

        return executor

    async def _run_subagent(
        self,
        *,
        executor: Any,
        prompt: str,
        session_key: str,
        user_id: Optional[str],
        case_id: Optional[str],
    ) -> Dict[str, Any]:
        text_chunks = []
        final_text = ""
        metadata: Dict[str, Any] = {}

        async for event in executor.run(
            prompt=prompt,
            system_prompt=(
                "Voce e um validador de citacoes juridicas. Responda APENAS JSON valido "
                "seguindo o schema solicitado."
            ),
            user_id=user_id or "citation-validator",
            case_id=case_id,
            session_id=session_key,
        ):
            event_type = getattr(event, "type", "")
            if hasattr(event_type, "value"):
                event_type = event_type.value
            data = getattr(event, "data", {}) or {}

            if event_type == SSEEventType.TOKEN.value:
                token = str(data.get("token") or "")
                if token:
                    text_chunks.append(token)
            elif event_type == SSEEventType.DONE.value:
                final_text = str(data.get("final_text") or "").strip()
                if isinstance(data.get("metadata"), dict):
                    metadata = dict(data["metadata"])
            elif event_type == SSEEventType.ERROR.value:
                raise RuntimeError(str(data.get("error") or "citation validator subagent failed"))

        return {
            "text": final_text or "".join(text_chunks).strip(),
            "metadata": metadata,
        }

    async def validate(
        self,
        *,
        document_text: str,
        citations_map: Any,
        session_key: str,
        user_id: Optional[str] = None,
        case_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        baseline = _deterministic_baseline(document_text, citations_map)
        citation_dict = citations_map if isinstance(citations_map, dict) else {}

        if not os.getenv("ANTHROPIC_API_KEY"):
            return {
                **baseline,
                "subagent_enabled": False,
                "subagent_status": "skipped_no_api_key",
                "claims_without_citation": [],
                "suspicious_citations": [],
                "summary": "Subagente indisponivel sem ANTHROPIC_API_KEY. Resultado deterministico aplicado.",
            }

        executor = await self._get_or_create_session(session_key)
        if executor is None:
            return {
                **baseline,
                "subagent_enabled": False,
                "subagent_status": "skipped_executor_unavailable",
                "claims_without_citation": [],
                "suspicious_citations": [],
                "summary": "Subagente indisponivel (executor). Resultado deterministico aplicado.",
            }

        citations_preview = {
            str(k): {
                "title": (v or {}).get("title"),
                "url": (v or {}).get("url"),
                "snippet": str((v or {}).get("snippet") or "")[:400],
            }
            for k, v in list(citation_dict.items())[:40]
        }
        prompt = (
            "Valide consistencia de citacoes no texto juridico.\n"
            "Retorne JSON com as chaves:\n"
            "- coverage (0..1)\n"
            "- claims_without_citation (array de strings)\n"
            "- suspicious_citations (array de objetos {key, reason})\n"
            "- summary (string curta)\n\n"
            f"TEXTO:\n{(document_text or '')[:12000]}\n\n"
            f"CITATIONS_MAP:\n{json.dumps(citations_preview, ensure_ascii=False, default=str)}\n"
        )

        try:
            subagent_raw = await self._run_subagent(
                executor=executor,
                prompt=prompt,
                session_key=session_key,
                user_id=user_id,
                case_id=case_id,
            )
            parsed = _extract_json_strict(subagent_raw.get("text", "")) or {}
        except Exception as exc:
            logger.warning(f"Citation validator subagent execution failed: {exc}")
            return {
                **baseline,
                "subagent_enabled": True,
                "subagent_status": "failed",
                "claims_without_citation": [],
                "suspicious_citations": [],
                "summary": f"Subagente falhou ({exc}). Resultado deterministico aplicado.",
            }

        coverage = parsed.get("coverage", baseline.get("coverage"))
        try:
            coverage = float(coverage)
        except Exception:
            coverage = baseline.get("coverage", 1.0)
        coverage = max(0.0, min(1.0, coverage))

        claims_without = parsed.get("claims_without_citation")
        if not isinstance(claims_without, list):
            claims_without = []
        claims_without = [str(item).strip() for item in claims_without if str(item).strip()][:30]

        suspicious = parsed.get("suspicious_citations")
        if not isinstance(suspicious, list):
            suspicious = []
        normalized_suspicious = []
        for item in suspicious[:30]:
            if isinstance(item, dict):
                normalized_suspicious.append(
                    {
                        "key": str(item.get("key") or "").strip(),
                        "reason": str(item.get("reason") or "inconsistencia").strip(),
                    }
                )
            elif item:
                normalized_suspicious.append({"key": "", "reason": str(item).strip()})

        return {
            **baseline,
            "coverage": round(coverage, 3),
            "subagent_enabled": True,
            "subagent_status": "ok",
            "claims_without_citation": claims_without,
            "suspicious_citations": normalized_suspicious,
            "summary": str(parsed.get("summary") or "").strip()
            or "Validacao de citacoes concluida pelo subagente.",
            "subagent_metadata": subagent_raw.get("metadata") or {},
        }


_citation_validator_pool = CitationValidatorSubagentPool()


async def validate_citations_with_subagent(
    *,
    document_text: str,
    citations_map: Any,
    session_key: Optional[str] = None,
    user_id: Optional[str] = None,
    case_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Validate citations using a persistent Haiku subagent, with fallback.
    """
    session = (session_key or "").strip() or "citation-validator-session"
    return await _citation_validator_pool.validate(
        document_text=document_text or "",
        citations_map=citations_map or {},
        session_key=session,
        user_id=user_id,
        case_id=case_id,
    )

