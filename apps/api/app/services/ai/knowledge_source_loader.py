"""Knowledge Source Loader — Loads and formats knowledge sources for workflow prompt nodes.

Supports:
- vault_file: Individual library items (documents, templates)
- vault_folder: All items in a library folder
- web_search: Real-time web search
- legal_db: Jurisprudence and legislation databases
- brazilian_legal: Direct integration with Brazilian legal APIs (STF, STJ, legislacao)
- rag: RAG/vector search against knowledge base
- corpus: Hybrid search (OpenSearch + Qdrant) across Corpus collections
- pje: PJe process data via TecJustiça REST API

# PJe/TecJustiça configuration:
#   TECJUSTICA_API_URL - Base URL of the TecJustiça REST API
#   TECJUSTICA_API_KEY - API key for authentication
#   TECJUSTICA_MNI_CPF - CPF for MNI authentication
#   TECJUSTICA_MNI_SENHA - Password for MNI authentication
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger


class KnowledgeSourceLoader:
    """Loads knowledge sources for workflow prompt nodes.

    Each prompt node can have up to 2 knowledge sources attached.
    Sources are loaded at execution time and injected as context.
    """

    MAX_SOURCES_PER_BLOCK = 2
    _bnp_client = None  # Singleton for token cache reuse

    async def load_sources(
        self,
        sources: List[Dict[str, Any]],
        query: str,
        user_id: Optional[str] = None,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Load all knowledge sources and return formatted context + citations.

        Args:
            sources: List of source configs [{type, id, ...}]
            query: Search query for search-based sources
            user_id: User ID for permission-scoped access

        Returns:
            Tuple of (context_text, citations_list)
        """
        if not sources:
            return "", []

        if len(sources) > self.MAX_SOURCES_PER_BLOCK:
            logger.warning(
                f"[KnowledgeSourceLoader] {len(sources)} sources exceeds max "
                f"{self.MAX_SOURCES_PER_BLOCK}, truncating"
            )
            sources = sources[: self.MAX_SOURCES_PER_BLOCK]

        context_parts: List[str] = []
        citations: List[Dict[str, Any]] = []

        for i, source in enumerate(sources):
            source_type = source.get("type", "")
            try:
                if source_type == "vault_file":
                    text, cites = await self._load_vault_file(source, user_id)
                elif source_type == "vault_folder":
                    text, cites = await self._load_vault_folder(source, user_id)
                elif source_type == "web_search":
                    text, cites = await self._load_web_search(query)
                elif source_type == "legal_db":
                    text, cites = await self._load_legal_db(source, query)
                elif source_type == "rag":
                    text, cites = await self._load_rag(source, query)
                elif source_type == "brazilian_legal":
                    text, cites = await self._load_brazilian_legal(
                        source, query, user_id
                    )
                elif source_type == "corpus":
                    text, cites = await self._load_corpus(
                        source, query, user_id
                    )
                elif source_type == "pje":
                    text, cites = await self._load_pje(source, query, user_id)
                elif source_type == "bnp":
                    text, cites = await self._load_bnp(source, query, user_id)
                else:
                    logger.warning(
                        f"[KnowledgeSourceLoader] Unknown source type: {source_type}"
                    )
                    continue

                if text:
                    context_parts.append(f"[Fonte {i + 1}: {source_type}]\n{text}")
                citations.extend(cites)

            except Exception as e:
                logger.error(
                    f"[KnowledgeSourceLoader] Failed to load {source_type}: {e}"
                )
                context_parts.append(
                    f"[Fonte {i + 1}: {source_type} — Erro ao carregar: {e}]"
                )

        context_text = "\n\n---\n\n".join(context_parts)
        return context_text, citations

    async def _load_vault_file(
        self, source: Dict[str, Any], user_id: Optional[str]
    ) -> Tuple[str, List[Dict]]:
        """Load a single library item by ID."""
        file_id = source.get("id", "")
        if not file_id:
            return "", []

        try:
            from app.core.database import AsyncSessionLocal
            from app.models.library import LibraryItem

            async with AsyncSessionLocal() as db:
                item = await db.get(LibraryItem, file_id)
                if not item:
                    return f"[Arquivo não encontrado: {file_id}]", []

                # Check permission — deny access when user_id missing unless shared
                if not user_id:
                    if not item.is_shared:
                        return "[Acesso negado ao arquivo]", []
                elif item.user_id != user_id and not item.is_shared:
                    return "[Acesso negado ao arquivo]", []

                # Load content from storage
                content = await self._get_file_content(item.resource_id)
                citation = {
                    "id": item.id,
                    "title": item.name,
                    "type": (
                        item.type.value
                        if hasattr(item.type, "value")
                        else str(item.type)
                    ),
                    "source_type": "vault_file",
                }
                return content, [citation]

        except Exception as e:
            logger.error(f"[KnowledgeSourceLoader] vault_file error: {e}")
            return "", []

    async def _load_vault_folder(
        self, source: Dict[str, Any], user_id: Optional[str]
    ) -> Tuple[str, List[Dict]]:
        """Load all items in a library folder."""
        folder_id = source.get("id", "")
        if not folder_id:
            return "", []

        try:
            from app.core.database import AsyncSessionLocal
            from app.models.library import LibraryItem
            from sqlalchemy import select

            async with AsyncSessionLocal() as db:
                stmt = select(LibraryItem).where(
                    LibraryItem.folder_id == folder_id
                )
                if user_id:
                    stmt = stmt.where(
                        (LibraryItem.user_id == user_id)
                        | (LibraryItem.is_shared == True)  # noqa: E712
                    )
                else:
                    # No user_id — only return shared items
                    stmt = stmt.where(LibraryItem.is_shared == True)  # noqa: E712
                result = await db.execute(stmt.limit(20))
                items = result.scalars().all()

                parts = []
                citations = []
                for item in items:
                    content = await self._get_file_content(item.resource_id)
                    if content:
                        parts.append(f"### {item.name}\n{content[:3000]}")
                        citations.append(
                            {
                                "id": item.id,
                                "title": item.name,
                                "type": (
                                    item.type.value
                                    if hasattr(item.type, "value")
                                    else str(item.type)
                                ),
                                "source_type": "vault_folder",
                            }
                        )

                return "\n\n".join(parts), citations

        except Exception as e:
            logger.error(f"[KnowledgeSourceLoader] vault_folder error: {e}")
            return "", []

    async def _load_web_search(self, query: str) -> Tuple[str, List[Dict]]:
        """Perform web search and format results."""
        if not query:
            return "", []

        try:
            from app.services.web_search_service import WebSearchService

            service = WebSearchService()
            results = await service.search(query, max_results=5)

            parts = []
            citations = []
            for i, r in enumerate(results or []):
                title = r.get("title", f"Resultado {i + 1}")
                snippet = r.get("snippet", r.get("content", ""))
                url = r.get("url", r.get("link", ""))
                parts.append(f"**{title}**\n{snippet}")
                citations.append(
                    {
                        "id": f"web_{i}",
                        "title": title,
                        "link": url,
                        "excerpt": snippet[:200],
                        "source_type": "web_search",
                    }
                )

            return "\n\n".join(parts), citations

        except Exception as e:
            logger.error(f"[KnowledgeSourceLoader] web_search error: {e}")
            return "", []

    async def _load_legal_db(
        self, source: Dict[str, Any], query: str
    ) -> Tuple[str, List[Dict]]:
        """Search legal databases (jurisprudence, legislation)."""
        db_type = source.get(
            "db_type", "jurisprudence"
        )  # jurisprudence or legislation
        court = source.get("court", "")
        try:
            limit = min(max(int(source.get("limit", 5)), 1), 20)
        except (ValueError, TypeError):
            limit = 5

        try:
            if db_type == "jurisprudence":
                from app.services.jurisprudence_service import JurisprudenceService

                service = JurisprudenceService()
                results = await service.search(
                    query=query, court=court, limit=limit
                )
            elif db_type == "legislation":
                from app.services.legislation_service import LegislationService

                service = LegislationService()
                results = await service.search(query=query, limit=limit)
            else:
                return "", []

            parts = []
            citations = []
            for i, r in enumerate(results or []):
                if isinstance(r, dict):
                    title = r.get(
                        "title", r.get("ementa", f"Resultado {i + 1}")
                    )
                    content = r.get(
                        "content", r.get("text", r.get("ementa", ""))
                    )
                    link = r.get("link", r.get("url", ""))
                else:
                    title = f"Resultado {i + 1}"
                    content = str(r)
                    link = ""

                parts.append(f"**{title}**\n{content[:2000]}")
                citations.append(
                    {
                        "id": f"legal_{db_type}_{i}",
                        "title": title,
                        "link": link,
                        "excerpt": content[:200],
                        "source_type": f"legal_{db_type}",
                    }
                )

            return "\n\n".join(parts), citations

        except Exception as e:
            logger.error(f"[KnowledgeSourceLoader] legal_db error: {e}")
            return "", []

    async def _load_rag(
        self, source: Dict[str, Any], query: str
    ) -> Tuple[str, List[Dict]]:
        """Search RAG/vector knowledge base."""
        rag_sources = source.get("sources", [])
        top_k = source.get("limit", 10)

        try:
            from app.services.rag_module import get_scoped_knowledge_graph

            rag = get_scoped_knowledge_graph()
            results = rag.hybrid_search(
                query=query,
                sources=rag_sources or None,
                top_k=top_k,
                include_global=True,
            )

            parts = []
            citations = []
            for i, r in enumerate(results or []):
                if isinstance(r, dict):
                    content = r.get("content", str(r))
                    title = r.get("title", r.get("source", f"RAG {i + 1}"))
                    score = r.get("score", 0)
                else:
                    content = str(r)
                    title = f"RAG {i + 1}"
                    score = 0

                parts.append(content[:2000])
                citations.append(
                    {
                        "id": f"rag_{i}",
                        "title": title,
                        "score": score,
                        "excerpt": content[:200],
                        "source_type": "rag",
                    }
                )

            return "\n\n".join(parts), citations

        except Exception as e:
            logger.error(f"[KnowledgeSourceLoader] rag error: {e}")
            return "", []

    async def _load_corpus(
        self,
        source: Dict[str, Any],
        query: str,
        user_id: Optional[str] = None,
    ) -> Tuple[str, List[Dict]]:
        """Search Corpus (hybrid OpenSearch + Qdrant) for workflow context."""
        collections = source.get("collections", [])
        scope = source.get("scope", "global")
        try:
            limit = min(max(int(source.get("limit", 10)), 1), 20)
        except (ValueError, TypeError):
            limit = 10

        try:
            from app.core.database import AsyncSessionLocal
            from app.services.corpus_service import CorpusService

            parts = []
            citations = []
            async with AsyncSessionLocal() as db:
                service = CorpusService(db)
                response = await service.search_corpus(
                    query=query,
                    collections=collections or None,
                    scope=scope,
                    user_id=user_id or "",
                    limit=limit,
                )

                # Process results inside the session to avoid DetachedInstanceError
                for i, result in enumerate(response.results or []):
                    text = result.chunk_text or ""
                    coll = result.collection or "corpus"
                    score = result.score or 0
                    doc_id = result.document_id or ""
                    meta = result.metadata or {}

                    parts.append(
                        f"### [{coll.upper()}] "
                        f"{meta.get('title', f'Resultado {i + 1}')}\n"
                        f"{text[:2000]}"
                    )
                    citations.append(
                        {
                            "id": f"corpus_{coll}_{i}",
                            "title": meta.get(
                                "title", f"Corpus - {coll} #{i + 1}"
                            ),
                            "collection": coll,
                            "score": score,
                            "document_id": doc_id,
                            "excerpt": text[:200],
                            "source_type": "corpus",
                        }
                    )

            return "\n\n".join(parts), citations

        except Exception as e:
            logger.error(f"[KnowledgeSourceLoader] corpus error: {e}")
            return "", []

    async def _load_brazilian_legal(
        self,
        source: Dict[str, Any],
        query: str,
        user_id: Optional[str] = None,
    ) -> Tuple[str, List[Dict]]:
        """Search Brazilian legal databases (STF, STJ, legislation)."""
        databases = source.get("databases", ["stf", "stj", "legislacao"])
        limit = source.get("limit", 5)

        parts: List[str] = []
        citations: List[Dict[str, Any]] = []

        import httpx
        from urllib.parse import quote_plus

        async with httpx.AsyncClient(timeout=15.0) as client:
            for db_name in databases:
                try:
                    if db_name == "stf":
                        results = await self._search_stf(client, query, limit)
                    elif db_name == "stj":
                        results = await self._search_stj(client, query, limit)
                    elif db_name == "legislacao":
                        results = await self._search_legislacao(
                            client, query, limit
                        )
                    else:
                        continue

                    for i, r in enumerate(results):
                        parts.append(
                            f"### [{db_name.upper()}] {r['title']}\n"
                            f"{r['text'][:2000]}"
                        )
                        citations.append(
                            {
                                "id": f"br_legal_{db_name}_{i}",
                                "title": r["title"],
                                "source_type": "brazilian_legal",
                                "database": db_name,
                                "url": r.get("url", ""),
                                "excerpt": r["text"][:200],
                            }
                        )
                except Exception as e:
                    logger.error(
                        f"[KnowledgeSourceLoader] {db_name} search error: {e}"
                    )

        return "\n\n".join(parts), citations

    async def _search_stf(
        self, client: "httpx.AsyncClient", query: str, limit: int
    ) -> list:
        """Search STF jurisprudence API."""
        try:
            url = "https://jurisprudencia.stf.jus.br/api/search/stf"
            params = {
                "query": query,
                "page": 1,
                "sort": "RELEVANCIA",
            }
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                return []

            data = resp.json()
            results = []
            for item in (data.get("result", []) or [])[:limit]:
                title = item.get("title", item.get("id", "STF"))
                text = item.get(
                    "body",
                    item.get("ementa", item.get("summary", "")),
                )
                item_url = item.get(
                    "url",
                    f"https://jurisprudencia.stf.jus.br/pages/search/"
                    f"{item.get('id', '')}",
                )
                results.append(
                    {
                        "title": str(title),
                        "text": str(text),
                        "url": str(item_url),
                    }
                )
            return results
        except Exception as e:
            logger.error(f"[STF API] Error: {e}")
            return []

    async def _search_stj(
        self, client: "httpx.AsyncClient", query: str, limit: int
    ) -> list:
        """Search STJ jurisprudence."""
        try:
            url = "https://scon.stj.jus.br/SCON/pesquisar.jsp"
            params = {
                "livre": query,
                "tipo_visualizacao": "RESUMO",
                "thesaurus": "JURIDICO",
                "p": "true",
            }
            resp = await client.get(
                url, params=params, follow_redirects=True
            )
            if resp.status_code != 200:
                return []

            # STJ returns HTML; for production, parse HTML properly
            text = resp.text
            results = []
            if text:
                results.append(
                    {
                        "title": f"STJ - Pesquisa: {query[:50]}",
                        "text": (
                            f"Resultados da pesquisa no STJ para: {query}. "
                            f"Acesse o portal para detalhes completos."
                        ),
                        "url": (
                            f"https://scon.stj.jus.br/SCON/"
                            f"pesquisar.jsp?livre={quote_plus(query)}"
                        ),
                    }
                )
            return results[:limit]
        except Exception as e:
            logger.error(f"[STJ API] Error: {e}")
            return []

    async def _search_legislacao(
        self, client: "httpx.AsyncClient", query: str, limit: int
    ) -> list:
        """Search Brazilian federal legislation."""
        try:
            results = [
                {
                    "title": f"Legislação Federal - {query[:50]}",
                    "text": (
                        f"Pesquisa legislativa para: {query}. "
                        f"Consulte planalto.gov.br para texto integral."
                    ),
                    "url": (
                        f"https://legislacao.planalto.gov.br/legisla/"
                        f"legislacao.nsf/FrmConsultaWeb1?"
                        f"OpenForm&query={query}"
                    ),
                }
            ]
            return results[:limit]
        except Exception as e:
            logger.error(f"[Legislacao] Error: {e}")
            return []

    async def _load_pje(
        self,
        source: Dict[str, Any],
        query: str,
        user_id: Optional[str] = None,
    ) -> Tuple[str, List[Dict]]:
        """Query PJe via TecJustiça REST API for process information.

        Credentials resolution order:
        1. source config (source['mni_cpf'], source['mni_senha']) — per-workflow override
        2. User preferences (preferences['pje_credentials']) — per-user config
        3. Environment variables (TECJUSTICA_MNI_CPF, etc.) — global fallback
        """
        import os
        import re

        import httpx

        api_url = source.get("api_url") or os.getenv("TECJUSTICA_API_URL", "http://localhost:8000")
        api_key = source.get("api_key") or os.getenv("TECJUSTICA_API_KEY", "")

        # Per-user credentials: try to load from user preferences
        mni_cpf = source.get("mni_cpf", "")
        mni_senha = source.get("mni_senha", "")

        if (not mni_cpf or not mni_senha) and user_id:
            try:
                from app.core.database import AsyncSessionLocal
                from app.models.user import User
                from sqlalchemy import select

                async with AsyncSessionLocal() as db:
                    result = await db.execute(select(User).where(User.id == user_id))
                    user = result.scalar_one_or_none()
                    if user:
                        prefs = user.preferences or {}
                        pje_creds = prefs.get("pje_credentials", {})
                        mni_cpf = mni_cpf or pje_creds.get("cpf", "") or user.cpf or ""
                        raw_senha = pje_creds.get("senha", "")
                        if raw_senha:
                            try:
                                from app.core.credential_encryption import decrypt_credential
                                mni_senha = mni_senha or decrypt_credential(raw_senha)
                            except ImportError:
                                mni_senha = mni_senha or raw_senha
            except Exception as e:
                logger.warning(f"[KnowledgeSourceLoader] Failed to load PJe user creds: {e}")

        # Global fallback
        mni_cpf = mni_cpf or os.getenv("TECJUSTICA_MNI_CPF", "")
        mni_senha = mni_senha or os.getenv("TECJUSTICA_MNI_SENHA", "")

        # The source config may specify a process number directly
        numero_processo = source.get("numero_processo", "")
        search_mode = source.get("mode", "auto")  # auto, processo, documentos

        # If no process number, try to extract from query
        if not numero_processo and query:
            # Try to find CNJ process number pattern (NNNNNNN-DD.AAAA.J.TR.OOOO)
            match = re.search(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}", query)
            if match:
                numero_processo = match.group()

        if not numero_processo:
            return "", []

        parts: List[str] = []
        citations: List[Dict[str, Any]] = []

        headers = {
            "X-API-KEY": api_key,
            "X-MNI-CPF": mni_cpf,
            "X-MNI-SENHA": mni_senha,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # 1. Get process data
                resp = await client.get(
                    f"{api_url}/api/v1/processo/{numero_processo}",
                    headers=headers,
                )
                if resp.status_code == 200:
                    data = resp.json()

                    # Format process info
                    processo_text = self._format_pje_processo(
                        data, numero_processo
                    )
                    parts.append(processo_text)

                    citations.append(
                        {
                            "id": f"pje_processo_{numero_processo}",
                            "title": f"Processo {numero_processo}",
                            "source_type": "pje",
                            "numero_processo": numero_processo,
                            "excerpt": processo_text[:200],
                        }
                    )

                    # 2. If mode includes documents, get document list
                    if search_mode in ("auto", "documentos"):
                        doc_resp = await client.get(
                            f"{api_url}/api/v1/processo/{numero_processo}/documentos/ids",
                            headers=headers,
                        )
                        if doc_resp.status_code == 200:
                            doc_ids = doc_resp.json()
                            if isinstance(doc_ids, list):
                                doc_list = ", ".join(
                                    str(d) for d in doc_ids[:20]
                                )
                                parts.append(
                                    f"### Documentos disponíveis\n"
                                    f"IDs: {doc_list}\n"
                                    f"Total: {len(doc_ids)} documentos"
                                )
                                citations.append(
                                    {
                                        "id": f"pje_docs_{numero_processo}",
                                        "title": f"Documentos - Processo {numero_processo}",
                                        "source_type": "pje",
                                        "document_count": len(doc_ids),
                                        "excerpt": f"{len(doc_ids)} documentos encontrados",
                                    }
                                )

                    # 3. Get cover page
                    if search_mode in ("auto", "capa"):
                        capa_resp = await client.get(
                            f"{api_url}/api/v1/processo/{numero_processo}/capa",
                            headers=headers,
                        )
                        if capa_resp.status_code == 200:
                            content_type = capa_resp.headers.get(
                                "content-type", ""
                            )
                            if content_type.startswith("application/json"):
                                capa_data = capa_resp.json()
                            else:
                                capa_data = {
                                    "text": capa_resp.text[:3000]
                                }
                            capa_text = self._format_pje_capa(capa_data)
                            if capa_text:
                                parts.append(capa_text)

        except Exception as e:
            logger.error(f"[KnowledgeSourceLoader] PJe error: {type(e).__name__}")
            return "Erro ao consultar PJe. Verifique suas credenciais e tente novamente.", []

        return "\n\n".join(parts), citations

    def _format_pje_processo(self, data: dict, numero: str) -> str:
        """Format PJe process data into readable text."""
        lines = [f"### Processo PJe: {numero}"]

        if isinstance(data, dict):
            # Common fields in PJe process response
            for key in [
                "classe",
                "classeJudicial",
                "orgaoJulgador",
                "dataAjuizamento",
                "grau",
                "nivelSigilo",
                "competencia",
                "localidade",
            ]:
                val = data.get(key)
                if val:
                    label = key.replace("_", " ").title()
                    lines.append(f"**{label}**: {val}")

            # Parties/Polos
            for polo_key in ["poloAtivo", "polo_ativo", "partes"]:
                polos = data.get(polo_key)
                if polos and isinstance(polos, list):
                    lines.append(
                        f"\n**{polo_key.replace('_', ' ').title()}**:"
                    )
                    for p in polos[:10]:
                        if isinstance(p, dict):
                            nome = p.get(
                                "nome", p.get("nomeCompleto", str(p))
                            )
                            lines.append(f"- {nome}")
                        else:
                            lines.append(f"- {p}")

            # Movements
            movs = data.get("movimentos", data.get("movimentacoes", []))
            if movs and isinstance(movs, list):
                lines.append(
                    f"\n**Últimas Movimentações** ({len(movs)} total):"
                )
                for m in movs[:10]:
                    if isinstance(m, dict):
                        dt = m.get("dataHora", m.get("data", ""))
                        desc = m.get(
                            "nome",
                            m.get("descricao", m.get("complemento", "")),
                        )
                        lines.append(f"- [{dt}] {desc}")
                    else:
                        lines.append(f"- {m}")
        else:
            lines.append(str(data)[:2000])

        return "\n".join(lines)

    def _format_pje_capa(self, data: dict) -> str:
        """Format PJe cover page data."""
        if not data:
            return ""
        if isinstance(data, dict):
            text = data.get("text", data.get("conteudo", ""))
            if text:
                return f"### Capa do Processo\n{text[:2000]}"
        return ""

    async def _load_bnp(
        self,
        source: Dict[str, Any],
        query: str,
        user_id: Optional[str] = None,
    ) -> Tuple[str, List[Dict]]:
        """Search BNP (Banco Nacional de Precedentes) for qualified precedents."""
        from app.services.mcp_servers.bnp_server import BNPClient

        tipo = source.get("tipo", "todos")
        try:
            limit = min(max(int(source.get("limit", 10)), 1), 20)
        except (ValueError, TypeError):
            limit = 10
        tribunal = source.get("tribunal")

        # Create per-request client (avoids sharing tokens across users)
        client = BNPClient()
        try:
            result = await client.search_precedentes(
                query=query, tipo=tipo, tribunal=tribunal, page=1, size=limit
            )

            items = result.get(
                "content", result.get("items", result.get("data", []))
            )
            if not isinstance(items, list):
                return "", []

            parts: List[str] = []
            citations: List[Dict[str, Any]] = []
            for i, item in enumerate(items[:limit]):
                if not isinstance(item, dict):
                    continue
                titulo = item.get(
                    "titulo",
                    item.get("tema", f"Precedente #{i + 1}"),
                )
                tese = item.get(
                    "tese",
                    item.get("teseJuridica", item.get("ementa", "")),
                )
                numero = item.get("numero", item.get("id", ""))
                tipo_prec = item.get(
                    "_tipo", item.get("tipo", item.get("especie", ""))
                )
                tribunal = item.get("tribunal", item.get("orgao", ""))

                text = f"### {titulo}"
                if numero:
                    text += f" (No {numero})"
                text += f"\n**Tipo**: {tipo_prec} | **Tribunal**: {tribunal}"
                if tese:
                    text += f"\n**Tese**: {tese[:1500]}"
                parts.append(text)

                citations.append(
                    {
                        "id": f"bnp_{tipo_prec}_{i}",
                        "title": titulo,
                        "source_type": "bnp",
                        "tipo": tipo_prec,
                        "tribunal": tribunal,
                        "numero": numero,
                        "excerpt": (tese or titulo)[:200],
                    }
                )

            return "\n\n".join(parts), citations
        except Exception as e:
            logger.error(f"[KnowledgeSourceLoader] BNP error: {e}")
            return "", []

    async def _get_file_content(self, resource_id: str) -> str:
        """Get file content from storage by resource_id."""
        try:
            from app.services.storage_service import storage_service

            content = await storage_service.get_text(resource_id)
            return content or ""
        except Exception as e:
            logger.debug(
                f"[KnowledgeSourceLoader] Could not load file content: {e}"
            )
            return f"[Conteúdo indisponível: {resource_id}]"
