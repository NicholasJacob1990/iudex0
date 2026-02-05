"""
Jurisprudence Verifier — Shepardização Brasileira

Serviço de verificação de vigência de citações jurídicas.
Equivalente à "Shepardização" do direito americano, adaptado para o BR:
- Extrai citações de texto jurídico (leis, súmulas, jurisprudência)
- Verifica vigência via web search + LLM
- Classifica status: vigente, superada, revogada, alterada, inconstitucional
- Persiste resultados com TTL de 7 dias
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger
from pydantic import BaseModel, Field

from app.services.web_search_service import web_search_service
from app.services.api_call_tracker import record_api_call
from app.services.rag.legal_vocabulary import (
    CITATION_PATTERNS as _VOCAB_CITATION_PATTERNS,
    CitationPattern,
)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class ExtractedCitation(BaseModel):
    """Citação extraída de um texto jurídico."""
    text: str = Field(..., description="Texto original da citação")
    citation_type: str = Field(..., description="Tipo: sumula, lei, artigo, jurisprudencia, etc.")
    normalized: Optional[str] = Field(None, description="Forma normalizada (ex: Súmula 331/TST)")
    position: Optional[int] = Field(None, description="Posição no texto original")


class VerificationResult(BaseModel):
    """Resultado da verificação de vigência de uma citação."""
    citation_text: str
    citation_type: str
    citation_normalized: Optional[str] = None
    status: str = "nao_verificada"
    confidence: float = 0.0
    details: Optional[str] = None
    source_url: Optional[str] = None
    verification_sources: Dict[str, Any] = Field(default_factory=dict)
    verified_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ShepardizationReport(BaseModel):
    """Relatório completo de shepardização de um documento."""
    document_id: Optional[str] = None
    total_citations: int = 0
    verified: int = 0
    vigentes: int = 0
    problematic: int = 0
    citations: List[VerificationResult] = Field(default_factory=list)
    summary: Optional[str] = None
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ---------------------------------------------------------------------------
# Regex patterns para extração de citações brasileiras
#
# Fonte canônica: app.services.rag.legal_vocabulary.CITATION_PATTERNS
# Os patterns são convertidos de CitationPattern (dataclass) para o formato
# tuple (type, label, regex) usado por este módulo.
# Patterns exclusivos da shepardização (ex: acordao genérico) são adicionados
# ao final para maior cobertura.
# ---------------------------------------------------------------------------

# Mapeamento de name (legal_vocabulary) → citation_type usado por _normalize_citation.
# Nomes não listados aqui passam como estão (fallback em _normalize_citation retorna raw).
_NAME_TO_CTYPE = {
    "artigo_lei": "artigo",
    "lei_numero": "lei",
    "lei_complementar": "lei",
    "medida_provisoria": "medida_provisoria",
    "decreto": "decreto",
    "codigo_referencia": "legislacao",
    "constituicao_artigo": "constituicao",
    "cnj_number": "jurisprudencia",
    "recurso_especial": "acordao",
    "recurso_extraordinario": "acordao",
    "habeas_corpus": "acordao",
    "adi": "acordao",
    "agravo": "acordao",
    "tribunal_decisao": "jurisprudencia",
    "sumula_vinculante": "sumula_vinculante",
    "sumula_stf": "sumula",
    "sumula_stj": "sumula",
    "sumula_generica": "sumula",
    "oj_tst": "jurisprudencia",
}


def _adapt_citation_patterns() -> List[Tuple[str, str, re.Pattern]]:
    """Converte CitationPattern (legal_vocabulary) para formato tuple do verifier."""
    adapted: List[Tuple[str, str, re.Pattern]] = []
    for cp in _VOCAB_CITATION_PATTERNS:
        ctype = _NAME_TO_CTYPE.get(cp.name, cp.name)
        adapted.append((ctype, cp.description, cp.pattern))

    # Pattern exclusivo do verifier: acórdão genérico com cobertura mais ampla
    # de siglas processuais (Rcl, ARE, Pet, etc.) não cobertos por legal_vocabulary
    adapted.append((
        "acordao",
        "Acórdão genérico (REsp, RE, HC, MS, ADI, ADPF, AgRg, etc.)",
        re.compile(
            r"((?:REsp|RE|HC|MS|ADI|ADC|ADPF|AgRg|AgInt|RMS|RHC|Rcl|AI|ARE|Pet|Rp|SS|SL|AC|STA)\s*(?:n[ºo°.]?\s*)?[\d./-]+)",
            re.IGNORECASE,
        ),
    ))
    return adapted


CITATION_PATTERNS: List[Tuple[str, str, re.Pattern]] = _adapt_citation_patterns()


# ---------------------------------------------------------------------------
# Prompt templates para análise LLM
# ---------------------------------------------------------------------------

EXTRACTION_SYSTEM_PROMPT = """Você é um especialista em direito brasileiro.
Extraia TODAS as citações jurídicas do texto fornecido.
Para cada citação, identifique:
1. O texto exato da citação
2. O tipo (sumula, sumula_vinculante, lei, artigo, jurisprudencia, acordao, decreto, medida_provisoria, constituicao, outro)
3. A forma normalizada (ex: "Súmula 331/TST", "Lei 8.666/1993", "Art. 5º da CF/88")

Retorne APENAS um JSON array com objetos:
[
  {"text": "...", "citation_type": "...", "normalized": "..."},
  ...
]
Sem explicações adicionais."""

VERIFICATION_SYSTEM_PROMPT = """Você é um especialista em verificação de vigência de normas e jurisprudência brasileira.

Analise os resultados da pesquisa web fornecidos e determine o status atual da citação jurídica.

Classifique com UM dos seguintes status:
- "vigente" — ainda é "good law", em vigor e aplicável
- "superada" — entendimento foi superado por decisão mais recente ou nova tese
- "revogada" — norma expressamente revogada por lei posterior
- "alterada" — norma foi alterada/modificada (indicar a alteração)
- "inconstitucional" — declarada inconstitucional pelo STF (ADI, ADPF, etc.)
- "nao_verificada" — não foi possível determinar o status com segurança

Retorne APENAS um JSON:
{
  "status": "...",
  "confidence": 0.0-1.0,
  "details": "explicação breve do status atual",
  "source_url": "URL da fonte principal que comprova o status"
}"""


# ---------------------------------------------------------------------------
# Cache local em disco (TTL 7 dias)
# ---------------------------------------------------------------------------

class _VerificationCache:
    """Cache em disco para resultados de verificação."""

    def __init__(self, ttl_days: int = 7):
        self.cache_dir = Path(__file__).parent.parent / "data" / "citation_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl = timedelta(days=ttl_days)

    def _key(self, citation_normalized: str) -> str:
        return hashlib.md5(citation_normalized.lower().strip().encode()).hexdigest()

    def get(self, citation_normalized: str) -> Optional[Dict[str, Any]]:
        """Retorna resultado cacheado se existir e não expirado."""
        path = self.cache_dir / f"{self._key(citation_normalized)}.json"
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            cached_at = datetime.fromisoformat(data.get("cached_at", ""))
            if datetime.now(timezone.utc) - cached_at.replace(tzinfo=timezone.utc) > self.ttl:
                path.unlink(missing_ok=True)
                return None
            return data
        except Exception as e:
            logger.warning(f"Erro ao ler cache de citação: {e}")
            return None

    def set(self, citation_normalized: str, result: Dict[str, Any]) -> None:
        """Salva resultado no cache."""
        path = self.cache_dir / f"{self._key(citation_normalized)}.json"
        try:
            data = {**result, "cached_at": datetime.now(timezone.utc).isoformat()}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Erro ao salvar cache de citação: {e}")


# ---------------------------------------------------------------------------
# Serviço principal
# ---------------------------------------------------------------------------

class JurisprudenceVerifier:
    """Serviço de verificação de vigência de citações jurídicas (Shepardização BR)."""

    def __init__(self):
        self.cache = _VerificationCache(ttl_days=7)
        logger.info("JurisprudenceVerifier inicializado")

    # ------------------------------------------------------------------
    # 1) Extração de citações
    # ------------------------------------------------------------------

    def extract_citations_regex(self, text: str) -> List[ExtractedCitation]:
        """Extrai citações usando regex (rápido, sem custo de API)."""
        if not text or not text.strip():
            return []

        citations: List[ExtractedCitation] = []
        seen: set[str] = set()

        for ctype, label, pattern in CITATION_PATTERNS:
            for match in pattern.finditer(text):
                raw = match.group(0).strip()
                # Evitar duplicatas
                norm_key = re.sub(r"\s+", " ", raw.lower())
                if norm_key in seen:
                    continue
                seen.add(norm_key)

                # Normalizar
                normalized = self._normalize_citation(raw, ctype, match)

                citations.append(
                    ExtractedCitation(
                        text=raw,
                        citation_type=ctype,
                        normalized=normalized,
                        position=match.start(),
                    )
                )

        # Ordenar por posição no texto
        citations.sort(key=lambda c: c.position or 0)
        logger.info(f"Regex extraiu {len(citations)} citações")
        return citations

    async def extract_citations_llm(
        self,
        text: str,
        model: str = "gemini-2.0-flash",
    ) -> List[ExtractedCitation]:
        """Extrai citações usando LLM para maior cobertura."""
        # Limitar texto para não estourar contexto
        truncated = text[:8000] if len(text) > 8000 else text

        try:
            from google import genai  # type: ignore

            client = genai.Client()

            response = await asyncio.to_thread(
                client.models.generate_content,
                model=model,
                contents=f"{EXTRACTION_SYSTEM_PROMPT}\n\nTexto:\n{truncated}",
            )

            record_api_call(
                kind="citation_extraction",
                provider="gemini",
                success=True,
            )

            raw_text = response.text.strip()
            # Extrair JSON do resultado
            parsed = self._parse_json_response(raw_text, expect="array")
            if not parsed or not isinstance(parsed, list):
                logger.warning("LLM não retornou array válido para extração de citações")
                return []

            citations = []
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                citations.append(
                    ExtractedCitation(
                        text=item.get("text", ""),
                        citation_type=item.get("citation_type", "outro"),
                        normalized=item.get("normalized"),
                    )
                )
            logger.info(f"LLM extraiu {len(citations)} citações")
            return citations

        except Exception as e:
            logger.error(f"Erro na extração LLM de citações: {e}")
            record_api_call(
                kind="citation_extraction",
                provider="gemini",
                success=False,
            )
            return []

    async def extract_citations(
        self,
        text: str,
        use_llm: bool = True,
        model: str = "gemini-2.0-flash",
    ) -> List[ExtractedCitation]:
        """
        Extrai citações combinando regex + LLM.

        Regex primeiro (rápido/grátis), depois LLM para pegar citações mais complexas.
        Deduplicação por normalized form.
        """
        regex_citations = self.extract_citations_regex(text)

        if not use_llm:
            return regex_citations

        llm_citations = await self.extract_citations_llm(text, model=model)

        # Merge com deduplicação
        seen: set[str] = set()
        merged: List[ExtractedCitation] = []

        for c in regex_citations:
            key = (c.normalized or c.text).lower().strip()
            if key not in seen:
                seen.add(key)
                merged.append(c)

        for c in llm_citations:
            key = (c.normalized or c.text).lower().strip()
            if key not in seen:
                seen.add(key)
                merged.append(c)

        logger.info(
            f"Extração combinada: {len(regex_citations)} regex + "
            f"{len(llm_citations)} LLM = {len(merged)} únicas"
        )
        return merged

    # ------------------------------------------------------------------
    # 2) Verificação de vigência
    # ------------------------------------------------------------------

    async def verify_citation(
        self,
        citation: ExtractedCitation,
        use_cache: bool = True,
    ) -> VerificationResult:
        """Verifica a vigência de uma única citação."""
        norm = citation.normalized or citation.text
        logger.info(f"Verificando citação: {norm}")

        # Checar cache
        if use_cache:
            cached = self.cache.get(norm)
            if cached:
                logger.info(f"Cache hit para '{norm}'")
                return VerificationResult(
                    citation_text=citation.text,
                    citation_type=citation.citation_type,
                    citation_normalized=norm,
                    status=cached.get("status", "nao_verificada"),
                    confidence=cached.get("confidence", 0.0),
                    details=cached.get("details"),
                    source_url=cached.get("source_url"),
                    verification_sources=cached.get("verification_sources", {}),
                    verified_at=cached.get("verified_at", datetime.now(timezone.utc).isoformat()),
                )

        # Construir query de busca adequada ao tipo
        search_query = self._build_search_query(citation)

        # Buscar na web (fontes jurídicas brasileiras)
        web_results = await web_search_service.search_legal(
            query=search_query,
            num_results=5,
            use_cache=True,
        )

        # Construir contexto para análise LLM
        web_context = self._format_web_results(web_results)

        # Analisar via LLM
        analysis = await self._analyze_with_llm(
            citation=citation,
            web_context=web_context,
        )

        result = VerificationResult(
            citation_text=citation.text,
            citation_type=citation.citation_type,
            citation_normalized=norm,
            status=analysis.get("status", "nao_verificada"),
            confidence=analysis.get("confidence", 0.0),
            details=analysis.get("details"),
            source_url=analysis.get("source_url"),
            verification_sources={
                "web_search": {
                    "query": search_query,
                    "source": web_results.get("source", "unknown"),
                    "results_count": web_results.get("total", 0),
                },
                "llm_analysis": True,
            },
        )

        # Salvar no cache
        if use_cache and result.status != "nao_verificada":
            self.cache.set(norm, result.model_dump())

        return result

    async def verify_citations(
        self,
        citations: List[ExtractedCitation],
        use_cache: bool = True,
        max_concurrent: int = 3,
    ) -> List[VerificationResult]:
        """Verifica múltiplas citações com concorrência controlada."""
        if not citations:
            return []

        semaphore = asyncio.Semaphore(max_concurrent)

        async def _verify_with_semaphore(c: ExtractedCitation) -> VerificationResult:
            async with semaphore:
                try:
                    return await self.verify_citation(c, use_cache=use_cache)
                except Exception as e:
                    logger.error(f"Erro ao verificar '{c.text}': {e}")
                    return VerificationResult(
                        citation_text=c.text,
                        citation_type=c.citation_type,
                        citation_normalized=c.normalized,
                        status="nao_verificada",
                        confidence=0.0,
                        details=f"Erro na verificação: {str(e)}",
                    )

        results = await asyncio.gather(
            *[_verify_with_semaphore(c) for c in citations]
        )
        return list(results)

    # ------------------------------------------------------------------
    # 3) Shepardização completa de texto/documento
    # ------------------------------------------------------------------

    async def verify_text(
        self,
        text: str,
        use_llm_extraction: bool = True,
        use_cache: bool = True,
        max_concurrent: int = 3,
    ) -> ShepardizationReport:
        """
        Shepardização completa: extrai citações de texto e verifica todas.

        Args:
            text: Texto jurídico para analisar
            use_llm_extraction: Usar LLM além de regex para extrair citações
            use_cache: Usar cache de verificações anteriores
            max_concurrent: Máximo de verificações simultâneas
        """
        # 1. Extrair citações
        citations = await self.extract_citations(
            text, use_llm=use_llm_extraction
        )

        if not citations:
            return ShepardizationReport(
                total_citations=0,
                summary="Nenhuma citação jurídica encontrada no texto.",
            )

        # 2. Verificar todas
        results = await self.verify_citations(
            citations, use_cache=use_cache, max_concurrent=max_concurrent
        )

        # 3. Montar relatório
        vigentes = sum(1 for r in results if r.status == "vigente")
        problematic = sum(
            1
            for r in results
            if r.status in ("superada", "revogada", "alterada", "inconstitucional")
        )
        nao_verificadas = sum(1 for r in results if r.status == "nao_verificada")

        summary_parts = [
            f"Total de citações encontradas: {len(results)}.",
            f"Vigentes: {vigentes}.",
        ]
        if problematic > 0:
            summary_parts.append(
                f"ATENÇÃO: {problematic} citação(ões) com problema de vigência."
            )
        if nao_verificadas > 0:
            summary_parts.append(
                f"{nao_verificadas} não puderam ser verificadas."
            )

        return ShepardizationReport(
            total_citations=len(results),
            verified=len(results) - nao_verificadas,
            vigentes=vigentes,
            problematic=problematic,
            citations=results,
            summary=" ".join(summary_parts),
        )

    async def shepardize_document(
        self,
        document_id: str,
        document_text: str,
        use_cache: bool = True,
    ) -> ShepardizationReport:
        """
        Shepardização completa de um documento pelo ID.

        Args:
            document_id: ID do documento no banco
            document_text: Conteúdo textual do documento
            use_cache: Usar cache de verificações anteriores
        """
        report = await self.verify_text(
            text=document_text,
            use_llm_extraction=True,
            use_cache=use_cache,
        )
        report.document_id = document_id
        return report

    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------

    def _normalize_citation(
        self, raw: str, ctype: str, match: re.Match
    ) -> str:
        """Normaliza texto de citação para forma canônica."""
        groups = match.groups()

        if ctype == "sumula_vinculante":
            return f"Súmula Vinculante {groups[0]}"

        if ctype == "sumula":
            num = groups[0]
            tribunal = groups[1] if len(groups) > 1 and groups[1] else ""
            if tribunal:
                return f"Súmula {num}/{tribunal.upper()}"
            return f"Súmula {num}"

        if ctype == "lei":
            num = groups[0] if groups else ""
            ano = groups[1] if len(groups) > 1 else ""
            return f"Lei {num}/{ano}" if ano else f"Lei {num}"

        if ctype == "artigo":
            art = groups[0] if groups else ""
            return f"Art. {art}" if art else raw

        if ctype == "decreto":
            num = groups[0] if groups else ""
            ano = groups[1] if len(groups) > 1 else ""
            return f"Decreto {num}/{ano}" if ano else f"Decreto {num}"

        if ctype == "medida_provisoria":
            num = groups[0] if groups else ""
            ano = groups[1] if len(groups) > 1 else ""
            return f"MP {num}/{ano}" if ano else f"MP {num}"

        if ctype == "constituicao":
            art = groups[0] if groups and groups[0] else ""
            return f"CF/88 Art. {art}" if art else "CF/88"

        # jurisprudencia, acordao — usar texto extraído
        return raw.strip()

    def _build_search_query(self, citation: ExtractedCitation) -> str:
        """Constrói query de busca adequada ao tipo de citação."""
        norm = citation.normalized or citation.text
        ctype = citation.citation_type

        if ctype in ("sumula", "sumula_vinculante"):
            return f"{norm} vigência cancelada superada status atual"

        if ctype == "lei":
            return f"{norm} vigência revogada alterada status atual legislação"

        if ctype == "artigo":
            return f"{norm} vigência alteração revogação status atual"

        if ctype in ("decreto", "medida_provisoria"):
            return f"{norm} vigência revogação status atual"

        if ctype == "constituicao":
            return f"{norm} emenda constitucional alteração ADI inconstitucionalidade"

        if ctype in ("jurisprudencia", "acordao"):
            return f"{norm} entendimento superado vigência tema atual"

        return f"{norm} vigência status atual direito brasileiro"

    def _format_web_results(self, web_results: Dict[str, Any]) -> str:
        """Formata resultados web para contexto LLM."""
        results = web_results.get("results", [])
        if not results:
            return "Nenhum resultado encontrado na pesquisa web."

        lines = []
        for idx, r in enumerate(results[:5], 1):
            title = r.get("title", "")
            url = r.get("url", "")
            snippet = r.get("snippet", "")
            content = r.get("content", "")
            text_block = content[:500] if content else snippet
            lines.append(f"[{idx}] {title}\nURL: {url}\n{text_block}\n")

        return "\n".join(lines)

    async def _analyze_with_llm(
        self,
        citation: ExtractedCitation,
        web_context: str,
    ) -> Dict[str, Any]:
        """Usa LLM para analisar status de vigência com base nos resultados web."""
        norm = citation.normalized or citation.text

        prompt = (
            f"{VERIFICATION_SYSTEM_PROMPT}\n\n"
            f"## Citação a verificar\n"
            f"- Texto: {citation.text}\n"
            f"- Tipo: {citation.citation_type}\n"
            f"- Normalizado: {norm}\n\n"
            f"## Resultados da pesquisa web\n"
            f"{web_context}\n\n"
            f"Analise e retorne o JSON com o status de vigência."
        )

        try:
            from google import genai  # type: ignore

            client = genai.Client()

            response = await asyncio.to_thread(
                client.models.generate_content,
                model="gemini-2.0-flash",
                contents=prompt,
            )

            record_api_call(
                kind="citation_verification",
                provider="gemini",
                success=True,
            )

            raw_text = response.text.strip()
            parsed = self._parse_json_response(raw_text, expect="object")

            if parsed and isinstance(parsed, dict):
                # Validar status
                valid_statuses = {
                    "vigente", "superada", "revogada",
                    "alterada", "inconstitucional", "nao_verificada",
                }
                status = parsed.get("status", "nao_verificada")
                if status not in valid_statuses:
                    status = "nao_verificada"

                confidence = parsed.get("confidence", 0.0)
                if not isinstance(confidence, (int, float)):
                    confidence = 0.0
                confidence = max(0.0, min(1.0, float(confidence)))

                return {
                    "status": status,
                    "confidence": confidence,
                    "details": parsed.get("details"),
                    "source_url": parsed.get("source_url"),
                }

            logger.warning(f"LLM não retornou JSON válido para verificação de '{norm}'")
            return {"status": "nao_verificada", "confidence": 0.0}

        except Exception as e:
            logger.error(f"Erro na análise LLM de vigência para '{norm}': {e}")
            record_api_call(
                kind="citation_verification",
                provider="gemini",
                success=False,
            )
            return {
                "status": "nao_verificada",
                "confidence": 0.0,
                "details": f"Erro na análise: {str(e)}",
            }

    @staticmethod
    def _parse_json_response(
        text: str, expect: str = "object"
    ) -> Optional[Any]:
        """Extrai JSON de resposta LLM (remove fences, etc.)."""
        if not text:
            return None
        raw = text.strip()
        # Remover fences markdown
        fence_match = re.search(
            r"```(?:json)?\s*([\s\S]*?)\s*```", raw, flags=re.IGNORECASE
        )
        if fence_match:
            raw = fence_match.group(1).strip()
        try:
            return json.loads(raw)
        except Exception:
            pass

        if expect in ("array", "any"):
            arr_match = re.search(r"(\[[\s\S]*\])", raw)
            if arr_match:
                try:
                    return json.loads(arr_match.group(1))
                except Exception:
                    pass
        if expect in ("object", "any"):
            obj_match = re.search(r"(\{[\s\S]*\})", raw)
            if obj_match:
                try:
                    return json.loads(obj_match.group(1))
                except Exception:
                    pass
        return None


# ---------------------------------------------------------------------------
# Instância global
# ---------------------------------------------------------------------------
jurisprudence_verifier = JurisprudenceVerifier()
