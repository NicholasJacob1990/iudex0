"""
Corpus Chat Tool — Integração do Corpus (RAG) com o chat do agente.

Permite que o agente busque automaticamente no Corpus quando o usuário
faz perguntas que podem ser respondidas com base nos documentos indexados.

Uso:
    from app.services.corpus_chat_tool import search_corpus_for_chat, format_corpus_context

    # Busca no Corpus e retorna contexto formatado
    context = await search_corpus_for_chat(
        query="Qual o prazo para recurso especial?",
        user_id="user-123",
    )
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Coleções padrão para busca automática no chat
DEFAULT_CHAT_COLLECTIONS = ["lei", "juris", "doutrina", "pecas_modelo", "sei"]

# Limite de caracteres por chunk no contexto do chat
MAX_CHUNK_CHARS = 1500

# Limite total de caracteres de contexto Corpus no prompt
MAX_CORPUS_CONTEXT_CHARS = 10000


def format_corpus_context(
    results: List[Dict[str, Any]],
    query: str,
    max_chars: int = MAX_CORPUS_CONTEXT_CHARS,
) -> str:
    """
    Formata resultados do Corpus como contexto para injeção no prompt do chat.

    Gera um bloco XML com chunks numerados, incluindo metadados de fonte,
    coleção e score para permitir citações precisas pelo agente.

    Args:
        results: Lista de resultados do Corpus (dicts com chunk_text, collection, score, metadata).
        query: Query original do usuário.
        max_chars: Limite máximo de caracteres no contexto gerado.

    Returns:
        String formatada para injeção no system instruction, ou string vazia se sem resultados.
    """
    if not results:
        return ""

    header = (
        "### CORPUS — Base de Conhecimento\n"
        "<corpus_context>\n"
        "Os trechos abaixo foram recuperados automaticamente da base de conhecimento (Corpus).\n"
        "Use-os como referência para fundamentar sua resposta.\n"
        "Cite as fontes usando o formato: [Corpus: coleção - título, chunk N]\n\n"
    )
    footer = "\n</corpus_context>"

    lines = [header]
    total_chars = len(header) + len(footer)

    for i, result in enumerate(results, 1):
        chunk_text = (result.get("chunk_text") or result.get("text") or "").strip()
        if not chunk_text:
            continue

        # Truncar chunks muito longos
        if len(chunk_text) > MAX_CHUNK_CHARS:
            chunk_text = chunk_text[:MAX_CHUNK_CHARS].rstrip() + "..."

        collection = result.get("collection") or "documento"
        score = result.get("score")
        source_type = result.get("source") or "hybrid"
        metadata = result.get("metadata") or {}
        title = metadata.get("title") or metadata.get("doc_title") or ""
        doc_id = result.get("document_id") or metadata.get("doc_id") or ""

        # Construir atributos do chunk
        attrs = [f'id="{i}"']
        if collection:
            attrs.append(f'coleção="{collection}"')
        if title:
            safe_title = str(title).replace('"', "'")
            attrs.append(f'título="{safe_title}"')
        if doc_id:
            attrs.append(f'doc_id="{doc_id}"')
        if source_type:
            attrs.append(f'busca="{source_type}"')
        if score is not None:
            try:
                attrs.append(f'relevância="{float(score):.3f}"')
            except (TypeError, ValueError):
                pass

        chunk_block = f'<chunk {" ".join(attrs)}>\n{chunk_text}\n</chunk>\n'

        # Verificar limite de caracteres
        if total_chars + len(chunk_block) > max_chars:
            break

        lines.append(chunk_block)
        total_chars += len(chunk_block)

    # Se não temos chunks, não gerar contexto
    if len(lines) <= 1:
        return ""

    lines.append(footer)
    return "".join(lines)


async def search_corpus_for_chat(
    query: str,
    user_id: str,
    org_id: Optional[str] = None,
    collections: Optional[List[str]] = None,
    scope: Optional[str] = None,
    limit: int = 5,
    db=None,
) -> str:
    """
    Busca no Corpus e retorna contexto formatado para o chat.

    Esta é a função principal que o chat deve chamar para integrar
    o Corpus nas respostas do agente.

    Args:
        query: Pergunta ou consulta do usuário.
        user_id: ID do usuário autenticado.
        org_id: ID da organização (se aplicável).
        collections: Lista de coleções para buscar (None = todas).
        scope: Escopo da busca (None = sem filtro).
        limit: Número máximo de resultados.
        db: Sessão do banco de dados (AsyncSession).

    Returns:
        String formatada com contexto do Corpus, ou string vazia se sem resultados.
    """
    if not query or not query.strip():
        return ""

    effective_collections = collections or DEFAULT_CHAT_COLLECTIONS

    try:
        if db is not None:
            # Caminho principal: usar CorpusService com sessão do banco
            from app.services.corpus_service import CorpusService

            corpus = CorpusService(db)
            response = await corpus.search_corpus(
                query=query.strip(),
                collections=effective_collections,
                scope=scope,
                user_id=user_id,
                org_id=org_id,
                limit=limit,
            )

            if not response.results:
                logger.debug(f"Corpus: sem resultados para '{query[:80]}'")
                return ""

            # Converter CorpusSearchResult para dicts
            results_dicts = []
            for r in response.results:
                results_dicts.append({
                    "chunk_text": r.chunk_text,
                    "collection": r.collection,
                    "score": r.score,
                    "source": r.source,
                    "document_id": r.document_id,
                    "metadata": r.metadata or {},
                })

            context = format_corpus_context(results_dicts, query)
            if context:
                logger.info(
                    f"Corpus: {len(response.results)} resultados para '{query[:60]}' "
                    f"({len(context)} chars)"
                )
            return context

        else:
            # Fallback: busca direta nos backends RAG (sem sessão do banco)
            return await _search_corpus_direct(
                query=query.strip(),
                collections=effective_collections,
                user_id=user_id,
                org_id=org_id,
                scope=scope,
                limit=limit,
            )

    except Exception as exc:
        logger.warning(f"Corpus search para chat falhou: {exc}", exc_info=True)
        return ""


async def _search_corpus_direct(
    query: str,
    collections: List[str],
    user_id: str,
    org_id: Optional[str] = None,
    scope: Optional[str] = None,
    limit: int = 5,
) -> str:
    """
    Busca direta nos backends RAG sem passar pelo CorpusService.

    Útil quando não temos uma sessão de banco disponível.
    """
    from app.services.corpus_service import (
        COLLECTION_TO_OS_INDEX,
        COLLECTION_TO_QDRANT,
        _get_opensearch_service,
        _get_qdrant_service,
    )

    results: List[Dict[str, Any]] = []
    tenant_id = org_id or user_id

    # Busca lexical (OpenSearch)
    try:
        os_service = _get_opensearch_service()
        os_indices = [
            COLLECTION_TO_OS_INDEX[c]
            for c in collections
            if c in COLLECTION_TO_OS_INDEX
        ]
        if os_indices:
            lexical_results = os_service.search_lexical(
                query=query,
                indices=os_indices,
                top_k=limit,
                scope=scope,
                user_id=user_id,
                include_global=True,
            )
            for hit in lexical_results:
                results.append({
                    "chunk_text": hit.get("text", ""),
                    "collection": hit.get("metadata", {}).get("source_type"),
                    "score": hit.get("score", 0.0),
                    "source": "lexical",
                    "document_id": hit.get("metadata", {}).get("doc_id"),
                    "metadata": hit.get("metadata", {}),
                })
    except Exception as e:
        logger.warning(f"Corpus chat: busca lexical falhou: {e}")

    # Busca vetorial (Qdrant)
    try:
        qdrant = _get_qdrant_service()
        # Obter embedding
        embedding = None
        try:
            from app.services.rag.core.embeddings import get_embeddings_service
            service = get_embeddings_service()
            embedding = service.embed_query(query)
        except Exception:
            pass

        if embedding:
            for coll in collections:
                if coll not in COLLECTION_TO_QDRANT:
                    continue
                try:
                    vector_results = qdrant.search(
                        collection_type=COLLECTION_TO_QDRANT[coll],
                        query_vector=embedding,
                        tenant_id=tenant_id,
                        user_id=user_id,
                        top_k=limit,
                        scopes=[scope] if scope else None,
                    )
                    for hit in vector_results:
                        results.append({
                            "chunk_text": hit.text,
                            "collection": coll,
                            "score": hit.score,
                            "source": "vector",
                            "document_id": hit.metadata.get("doc_id"),
                            "metadata": hit.metadata,
                        })
                except Exception as e:
                    logger.warning(f"Corpus chat: busca vetorial em {coll} falhou: {e}")
    except Exception as e:
        logger.warning(f"Corpus chat: busca vetorial falhou: {e}")

    # Deduplicar e ordenar por score
    seen_texts = set()
    unique_results = []
    for r in sorted(results, key=lambda x: x.get("score", 0), reverse=True):
        text_key = (r.get("chunk_text") or "")[:200]
        if text_key and text_key not in seen_texts:
            seen_texts.add(text_key)
            unique_results.append(r)

    unique_results = unique_results[:limit]

    return format_corpus_context(unique_results, query)


def should_search_corpus(
    message: str,
    rag_sources: Optional[List[str]] = None,
    rag_mode: str = "manual",
    has_attachments: bool = False,
) -> bool:
    """
    Decide se o chat deve buscar automaticamente no Corpus.

    Retorna True quando:
    - A mensagem não é trivial (saudação, etc.)
    - Nenhuma fonte RAG foi selecionada explicitamente OU rag_mode é 'auto'
    - A mensagem parece ser uma pergunta ou consulta substantiva

    Args:
        message: Texto da mensagem do usuário.
        rag_sources: Fontes RAG explicitamente selecionadas.
        rag_mode: Modo RAG ('auto' ou 'manual').
        has_attachments: Se a mensagem tem anexos.

    Returns:
        True se deve buscar no Corpus automaticamente.
    """
    if not message or not message.strip():
        return False

    clean = message.strip().lower().rstrip("!?.,:;")

    # Mensagens triviais — não buscar
    trivial_words = {
        "oi", "olá", "ola", "bom dia", "boa tarde", "boa noite",
        "obrigado", "obrigada", "valeu", "ok", "sim", "não", "nao",
        "tudo bem", "tchau", "bye", "hello", "hi", "hey",
        "ok", "certo", "entendi", "perfeito",
    }
    if len(clean.split()) <= 3 and clean in trivial_words:
        return False

    # Mensagens muito curtas (< 5 chars) — provavelmente não é uma consulta
    if len(clean) < 5:
        return False

    # Se rag_mode é 'auto', SEMPRE buscar (exceto triviais)
    if rag_mode == "auto":
        return True

    # Se já tem fontes RAG explícitas, a pipeline normal já cuida
    if rag_sources:
        return False

    # Se tem anexos, o sistema já processa via attachment_mode
    if has_attachments:
        return False

    # Heurística: buscar se a mensagem parece ser uma pergunta/consulta substantiva
    # Palavras-chave que indicam consulta jurídica ou informacional
    query_indicators = {
        "qual", "quais", "como", "onde", "quando", "quanto", "quem",
        "porque", "por que", "por quê", "o que", "é possível",
        "explique", "explica", "defina", "define", "descreva",
        "artigo", "lei", "decreto", "resolução", "súmula",
        "jurisprudência", "precedente", "tribunal", "stf", "stj",
        "prazo", "recurso", "petição", "contestação", "apelação",
        "doutrina", "conceito", "princípio", "fundamento",
        "argumento", "tese", "caso", "processo",
        "contrato", "cláusula", "obrigação", "responsabilidade",
        "direito", "dever", "competência", "jurisdição",
        "busque", "pesquise", "encontre", "procure", "verifique",
    }

    words = set(clean.split())
    if words & query_indicators:
        return True

    # Se a mensagem tem mais de 10 palavras, provavelmente é uma consulta
    if len(clean.split()) >= 10:
        return True

    # Interrogativas
    if message.strip().endswith("?"):
        return True

    return False
