"""
Serviço de Embeddings Jurídicos Brasileiros Especializados

Inspirado na abordagem Harvey AI + Voyage AI para embeddings legais customizados,
adaptado para o contexto do direito brasileiro.

Estratégia multi-embedding:
  1. Embedding primário: Voyage AI voyage-law-2 (quando VOYAGE_API_KEY configurada)
  2. Embedding secundário: OpenAI text-embedding-3-large (fallback)
  3. Embedding terciário (fallback): Sentence Transformers multilingual
  4. Embedding léxico: BM25 otimizado com vocabulário jurídico brasileiro

Cadeia de fallback: Voyage AI -> OpenAI -> Sentence Transformers local

Features:
  - Pré-processamento jurídico (normalização, expansão de abreviações)
  - Vocabulário jurídico especializado (sinônimos, termos técnicos)
  - Query augmentation para busca jurídica (HyDE jurídico, multi-query)
  - Segmentação inteligente de textos longos (respeita limites de cláusulas/artigos)
  - Integração plug-and-play com pipeline RAG existente (legal_mode=True)
  - Voyage AI como provider primário para domínio jurídico (+6% em benchmarks)
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.services.rag.config import get_rag_config

from app.services.rag.legal_vocabulary import (
    CITATION_PATTERNS,
    LEGAL_ABBREVIATIONS,
    LEGAL_STOPWORDS,
    LEGAL_SYNONYMS,
    NOISE_PATTERNS,
    PRESERVE_TERMS,
    CitationPattern,
    NormativeLevel,
    clean_legal_noise,
    detect_normative_level,
    expand_with_synonyms,
    extract_citations,
    get_synonyms,
)

logger = logging.getLogger(__name__)

# Importações condicionais
try:
    from rank_bm25 import BM25Okapi  # type: ignore
except ImportError:
    BM25Okapi = None  # type: ignore

try:
    import openai
    from openai import AsyncOpenAI, OpenAI
except ImportError:
    openai = None  # type: ignore
    AsyncOpenAI = None  # type: ignore
    OpenAI = None  # type: ignore

try:
    from sentence_transformers import SentenceTransformer  # type: ignore
except ImportError:
    SentenceTransformer = None  # type: ignore

# Voyage AI provider
try:
    from app.services.rag.voyage_embeddings import (
        VoyageEmbeddingsProvider,
        VoyageModel,
        get_voyage_provider,
        is_voyage_available,
    )
except ImportError:
    VoyageEmbeddingsProvider = None  # type: ignore
    VoyageModel = None  # type: ignore
    get_voyage_provider = None  # type: ignore
    is_voyage_available = lambda: False  # type: ignore


# =============================================================================
# Configuração
# =============================================================================


@dataclass
class LegalEmbeddingConfig:
    """Configuração para o serviço de embeddings jurídicos."""

    # Voyage AI (provider primário para domínio jurídico)
    use_voyage: bool = True  # Habilitar Voyage AI quando disponível
    voyage_legal_model: str = "voyage-law-2"
    voyage_general_model: str = "voyage-3-large"

    # Modelo OpenAI (fallback quando Voyage não disponível)
    primary_model: str = "text-embedding-3-large"
    primary_dimensions: int = 3072
    primary_instruction: str = (
        "Represent this Brazilian legal text for retrieval. "
        "Focus on legal concepts, statutes, case law references, "
        "and doctrinal principles from Brazilian law."
    )

    # Modelo terciário (Sentence Transformers) — fallback local
    fallback_model: str = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
    use_fallback: bool = True

    # BM25 léxico
    enable_bm25: bool = True
    bm25_k1: float = 1.5
    bm25_b: float = 0.75

    # Pré-processamento
    expand_abbreviations: bool = True
    normalize_legal_terms: bool = True
    remove_noise: bool = True
    remove_stopwords: bool = False  # Cuidado: pode remover contexto importante

    # Segmentação
    max_segment_tokens: int = 512
    segment_overlap_tokens: int = 64
    respect_article_boundaries: bool = True

    # Query augmentation
    enable_hyde: bool = True
    hyde_model: str = "gemini-2.0-flash"
    hyde_max_tokens: int = 300
    enable_multi_query: bool = True
    multi_query_count: int = 3
    enable_synonym_expansion: bool = True

    # Cache
    cache_ttl_seconds: int = 3600

    @classmethod
    def from_env(cls) -> "LegalEmbeddingConfig":
        """Carrega configuração das variáveis de ambiente."""

        def _bool(name: str, default: bool) -> bool:
            val = os.getenv(name)
            return val.lower() in ("1", "true", "yes", "on") if val else default

        def _int(name: str, default: int) -> int:
            val = os.getenv(name)
            try:
                return int(val) if val else default
            except ValueError:
                return default

        def _float(name: str, default: float) -> float:
            val = os.getenv(name)
            try:
                return float(val) if val else default
            except ValueError:
                return default

        return cls(
            use_voyage=_bool("LEGAL_USE_VOYAGE", True),
            voyage_legal_model=os.getenv("VOYAGE_DEFAULT_MODEL", "voyage-law-2"),
            voyage_general_model=os.getenv("VOYAGE_FALLBACK_MODEL", "voyage-3-large"),
            primary_model=os.getenv("LEGAL_EMBEDDING_MODEL", "text-embedding-3-large"),
            primary_dimensions=_int("LEGAL_EMBEDDING_DIMENSIONS", 3072),
            fallback_model=os.getenv(
                "LEGAL_FALLBACK_MODEL",
                "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
            ),
            use_fallback=_bool("LEGAL_USE_FALLBACK", True),
            enable_bm25=_bool("LEGAL_ENABLE_BM25", True),
            bm25_k1=_float("LEGAL_BM25_K1", 1.5),
            bm25_b=_float("LEGAL_BM25_B", 0.75),
            expand_abbreviations=_bool("LEGAL_EXPAND_ABBREVIATIONS", True),
            normalize_legal_terms=_bool("LEGAL_NORMALIZE_TERMS", True),
            remove_noise=_bool("LEGAL_REMOVE_NOISE", True),
            max_segment_tokens=_int("LEGAL_MAX_SEGMENT_TOKENS", 512),
            segment_overlap_tokens=_int("LEGAL_SEGMENT_OVERLAP_TOKENS", 64),
            respect_article_boundaries=_bool("LEGAL_RESPECT_ARTICLE_BOUNDARIES", True),
            enable_hyde=_bool("LEGAL_ENABLE_HYDE", True),
            hyde_model=os.getenv("LEGAL_HYDE_MODEL", "gemini-2.0-flash"),
            hyde_max_tokens=_int("LEGAL_HYDE_MAX_TOKENS", 300),
            enable_multi_query=_bool("LEGAL_ENABLE_MULTI_QUERY", True),
            multi_query_count=_int("LEGAL_MULTI_QUERY_COUNT", 3),
            enable_synonym_expansion=_bool("LEGAL_ENABLE_SYNONYM_EXPANSION", True),
            cache_ttl_seconds=_int("LEGAL_CACHE_TTL", 3600),
        )


# =============================================================================
# Pré-processamento Jurídico
# =============================================================================


class LegalPreprocessor:
    """
    Pré-processador de textos jurídicos brasileiros.

    Responsável por:
    - Normalizar abreviações (art. -> artigo, inc. -> inciso)
    - Expandir siglas de tribunais (STF, STJ, etc.)
    - Remover ruído processual
    - Preservar termos técnicos que não devem ser tokenizados
    """

    def __init__(self, config: LegalEmbeddingConfig) -> None:
        self.config = config
        # Pre-compila regex para abreviacoes (case-insensitive, word boundary)
        self._abbrev_patterns: List[Tuple[re.Pattern[str], str]] = []
        if config.expand_abbreviations:
            for abbrev, expanded in LEGAL_ABBREVIATIONS.items():
                # Escapar caracteres especiais em regex
                escaped = re.escape(abbrev)
                # Para siglas em maiúsculas (STF, STJ), usar word boundary
                if abbrev.isupper() and len(abbrev) >= 2:
                    pat = re.compile(rf"\b{escaped}\b", re.IGNORECASE)
                else:
                    pat = re.compile(rf"(?<!\w){escaped}(?!\w)", re.IGNORECASE)
                self._abbrev_patterns.append((pat, expanded))

    def preprocess(self, text: str) -> str:
        """
        Aplica todo o pipeline de pré-processamento jurídico.

        Args:
            text: Texto bruto

        Returns:
            Texto normalizado e limpo
        """
        if not text or not text.strip():
            return ""

        result = text

        # 1. Remover ruído processual
        if self.config.remove_noise:
            result = clean_legal_noise(result)

        # 2. Expandir abreviações
        if self.config.expand_abbreviations:
            result = self._expand_abbreviations(result)

        # 3. Normalizar termos jurídicos
        if self.config.normalize_legal_terms:
            result = self._normalize_terms(result)

        # 4. Remover stopwords jurídicas (opcional, desabilitado por default)
        if self.config.remove_stopwords:
            result = self._remove_stopwords(result)

        return result.strip()

    def preprocess_query(self, query: str) -> str:
        """
        Pré-processamento específico para queries (mais leve que documentos).
        Não remove ruído, apenas normaliza termos e expande abreviações.
        """
        if not query or not query.strip():
            return ""

        result = query.strip()

        # Expandir abreviações
        if self.config.expand_abbreviations:
            result = self._expand_abbreviations(result)

        # Normalizar termos
        if self.config.normalize_legal_terms:
            result = self._normalize_terms(result)

        return result.strip()

    def _expand_abbreviations(self, text: str) -> str:
        """Expande abreviações jurídicas mantendo o original entre parênteses."""
        result = text
        for pattern, expanded in self._abbrev_patterns:
            # Substituir mantendo contexto: "art. 5" -> "artigo 5"
            result = pattern.sub(expanded, result)
        return result

    def _normalize_terms(self, text: str) -> str:
        """Normaliza variações ortográficas e de formatação."""
        result = text

        # Normalizar numeração de artigos
        result = re.sub(
            r"(?i)\bartigo\s+(\d+)[°ºª]?",
            r"artigo \1",
            result,
        )

        # Normalizar parágrafo único
        result = re.sub(
            r"(?i)\bpar[áa]grafo\s+[úu]nico\b",
            "parágrafo único",
            result,
        )

        # Normalizar incisos romanos (manter como estão)
        # Normalizar referências a leis
        result = re.sub(
            r"(?i)\blei\s+n[°ºo]?\s*\.?\s*",
            "lei número ",
            result,
        )

        return result

    def _remove_stopwords(self, text: str) -> str:
        """Remove stopwords jurídicas que não agregam significado semântico."""
        words = text.split()
        filtered = []
        for word in words:
            clean_word = word.strip(".,;:!?()[]\"'").lower()
            if clean_word not in LEGAL_STOPWORDS:
                filtered.append(word)
        return " ".join(filtered)


# =============================================================================
# Segmentação Inteligente de Textos Jurídicos
# =============================================================================


class LegalSegmenter:
    """
    Segmenta textos jurídicos longos respeitando limites naturais
    de artigos, parágrafos, incisos e cláusulas.
    """

    # Padrões que indicam início de nova unidade semântica
    _ARTICLE_START = re.compile(
        r"(?i)(?:^|\n)\s*(?:"
        r"art(?:igo)?\.?\s*\d+"
        r"|§\s*(?:\d+|único)"
        r"|cap[íi]tulo\s+[IVXLCDM]+"
        r"|t[íi]tulo\s+[IVXLCDM]+"
        r"|se[çc][ãa]o\s+[IVXLCDM]+"
        r"|cl[áa]usula\s+\d+"
        r")",
        re.UNICODE,
    )

    def __init__(self, config: LegalEmbeddingConfig) -> None:
        self.config = config
        # Aproximação: ~4 chars por token
        self._max_chars = config.max_segment_tokens * 4
        self._overlap_chars = config.segment_overlap_tokens * 4

    def segment(self, text: str) -> List[str]:
        """
        Segmenta um texto jurídico longo em chunks menores.

        Se respect_article_boundaries está ativado, tenta quebrar
        nos limites naturais de artigos/parágrafos/cláusulas.
        """
        if not text or not text.strip():
            return []

        text = text.strip()

        # Texto cabe em um único segmento
        if len(text) <= self._max_chars:
            return [text]

        if self.config.respect_article_boundaries:
            segments = self._segment_by_structure(text)
        else:
            segments = self._segment_by_size(text)

        return [s.strip() for s in segments if s.strip()]

    def _segment_by_structure(self, text: str) -> List[str]:
        """Segmenta respeitando estrutura de artigos e cláusulas."""
        # Encontrar todos os pontos de quebra natural
        boundaries = [m.start() for m in self._ARTICLE_START.finditer(text)]

        if not boundaries:
            return self._segment_by_size(text)

        # Garantir que começa do início
        if boundaries[0] != 0:
            boundaries.insert(0, 0)

        segments: List[str] = []
        current_start = 0
        current_text = ""

        for i, boundary in enumerate(boundaries):
            # Extrair bloco até a próxima boundary
            next_boundary = boundaries[i + 1] if i + 1 < len(boundaries) else len(text)
            block = text[boundary:next_boundary]

            # Se adicionar este bloco excede o limite, fechar segmento atual
            if current_text and len(current_text) + len(block) > self._max_chars:
                segments.append(current_text)
                # Overlap: incluir final do segmento anterior
                overlap_text = current_text[-self._overlap_chars:] if self._overlap_chars > 0 else ""
                current_text = overlap_text + block
            else:
                current_text += block

            # Se o bloco sozinho excede o limite, quebrar por tamanho
            if len(current_text) > self._max_chars * 1.5:
                sub_segments = self._segment_by_size(current_text)
                segments.extend(sub_segments[:-1])
                current_text = sub_segments[-1] if sub_segments else ""

        # Adicionar último segmento
        if current_text.strip():
            segments.append(current_text)

        return segments

    def _segment_by_size(self, text: str) -> List[str]:
        """Segmentação simples por tamanho com overlap."""
        segments: List[str] = []
        step = max(1, self._max_chars - self._overlap_chars)
        pos = 0

        while pos < len(text):
            end = pos + self._max_chars
            chunk = text[pos:end]

            # Tentar quebrar em um ponto natural (fim de frase)
            if end < len(text):
                # Procurar último ponto final, ponto-e-vírgula, ou quebra de linha
                last_break = max(
                    chunk.rfind(". "),
                    chunk.rfind(".\n"),
                    chunk.rfind(";\n"),
                    chunk.rfind("\n\n"),
                )
                if last_break > self._max_chars * 0.5:  # Pelo menos metade do chunk
                    chunk = chunk[: last_break + 1]

            segments.append(chunk)
            pos += len(chunk) - self._overlap_chars if self._overlap_chars > 0 else len(chunk)

        return segments


# =============================================================================
# BM25 Jurídico Otimizado
# =============================================================================


class LegalBM25:
    """
    BM25 otimizado com vocabulário jurídico brasileiro.

    Diferenças do BM25 padrão:
    - Tokenização consciente de termos jurídicos compostos
    - Pesos ajustados para textos legais (k1=1.5, b=0.75)
    - Suporte a termos que devem ser preservados como unidade
    """

    def __init__(self, config: LegalEmbeddingConfig) -> None:
        self.config = config
        self._corpus_tokenized: List[List[str]] = []
        self._bm25: Optional[Any] = None
        self._preprocessor = LegalPreprocessor(config)

    def _tokenize(self, text: str) -> List[str]:
        """Tokeniza texto preservando termos jurídicos compostos."""
        processed = self._preprocessor.preprocess(text).lower()

        # Substituir termos compostos por tokens únicos (com underscore)
        for term in PRESERVE_TERMS:
            if term.lower() in processed:
                token = term.lower().replace(" ", "_").replace("-", "_")
                processed = processed.replace(term.lower(), token)

        # Tokenizar
        tokens = re.findall(r"\b[\w_]+\b", processed)

        # Filtrar tokens muito curtos (exceto siglas conhecidas)
        return [t for t in tokens if len(t) >= 2]

    def index(self, documents: List[str]) -> None:
        """Indexa um corpus de documentos para busca BM25."""
        if BM25Okapi is None:
            logger.warning("rank_bm25 não disponível, BM25 desabilitado")
            return

        self._corpus_tokenized = [self._tokenize(doc) for doc in documents]
        self._bm25 = BM25Okapi(
            self._corpus_tokenized,
            k1=self.config.bm25_k1,
            b=self.config.bm25_b,
        )
        logger.info(f"BM25 indexado com {len(documents)} documentos")

    def search(self, query: str, top_k: int = 10) -> List[Tuple[int, float]]:
        """
        Busca BM25 no corpus indexado.

        Returns:
            Lista de (doc_index, score) ordenada por relevância
        """
        if self._bm25 is None:
            return []

        tokenized_query = self._tokenize(query)
        if not tokenized_query:
            return []

        scores = self._bm25.get_scores(tokenized_query)

        # Ordenar por score e retornar top_k
        indexed_scores = [(i, float(s)) for i, s in enumerate(scores) if s > 0]
        indexed_scores.sort(key=lambda x: x[1], reverse=True)
        return indexed_scores[:top_k]


# =============================================================================
# Query Augmentation Jurídico
# =============================================================================


class LegalQueryAugmenter:
    """
    Expande queries com contexto jurídico.

    Técnicas:
    1. Expansão com sinônimos jurídicos
    2. HyDE adaptado para contexto jurídico
    3. Multi-query com variações terminológicas
    """

    def __init__(self, config: LegalEmbeddingConfig) -> None:
        self.config = config
        self._preprocessor = LegalPreprocessor(config)

    def expand_query(self, query: str) -> List[str]:
        """
        Gera variações expandidas de uma query jurídica.

        Returns:
            Lista de queries expandidas (inclui a original preprocessada)
        """
        processed = self._preprocessor.preprocess_query(query)
        queries = [processed]

        # Expansão com sinônimos
        if self.config.enable_synonym_expansion:
            expanded = expand_with_synonyms(processed)
            if expanded != processed:
                queries.append(expanded)

        # Multi-query com variações terminológicas
        if self.config.enable_multi_query:
            variations = self._generate_terminology_variations(processed)
            queries.extend(variations)

        # Deduplica mantendo ordem
        seen: set[str] = set()
        unique: List[str] = []
        for q in queries:
            normalized = q.strip().lower()
            if normalized and normalized not in seen:
                seen.add(normalized)
                unique.append(q.strip())

        return unique

    async def generate_hyde_document(self, query: str) -> Optional[str]:
        """
        Gera um documento hipotético jurídico (HyDE) para a query.

        Usa LLM para gerar um texto que seria a resposta ideal,
        adaptado para o domínio jurídico brasileiro.
        """
        if not self.config.enable_hyde:
            return None

        prompt = self._build_hyde_prompt(query)

        try:
            # Tentar Gemini primeiro (conforme config padrão do projeto)
            hyde_doc = await self._call_hyde_llm(prompt)
            if hyde_doc:
                return hyde_doc
        except Exception as e:
            logger.warning(f"HyDE LLM falhou: {e}")

        return None

    def _generate_terminology_variations(self, query: str) -> List[str]:
        """
        Gera variações terminológicas de uma query.

        Ex: "responsabilidade do réu" ->
            ["responsabilidade do demandado", "imputação do requerido"]
        """
        variations: List[str] = []
        words = query.lower().split()

        for i, word in enumerate(words):
            clean = word.strip(".,;:!?()[]\"'")
            synonyms = get_synonyms(clean)
            if synonyms:
                # Gerar até 2 variações por sinônimo encontrado
                for syn in list(synonyms - {clean})[:2]:
                    new_words = words.copy()
                    new_words[i] = syn
                    variation = " ".join(new_words)
                    if variation not in variations:
                        variations.append(variation)

            if len(variations) >= self.config.multi_query_count:
                break

        return variations[: self.config.multi_query_count]

    def _build_hyde_prompt(self, query: str) -> str:
        """Constrói o prompt HyDE adaptado para o direito brasileiro."""
        return (
            "Você é um jurista brasileiro especialista. "
            "Dada a seguinte consulta jurídica, redija um parágrafo "
            "técnico e preciso que seria encontrado em um documento "
            "jurídico relevante (lei, jurisprudência, doutrina ou peça processual). "
            "Use terminologia jurídica brasileira precisa. "
            "Não invente leis ou números de artigos específicos.\n\n"
            f"Consulta: {query}\n\n"
            "Documento hipotético relevante:"
        )

    async def _call_hyde_llm(self, prompt: str) -> Optional[str]:
        """Chama o LLM para gerar o documento HyDE."""
        model = self.config.hyde_model

        # Tentar Google Gemini
        if "gemini" in model.lower():
            try:
                from google import genai  # type: ignore

                client = genai.Client()
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=model,
                    contents=prompt,
                )
                if response and response.text:
                    return response.text[: self.config.hyde_max_tokens * 4]
            except Exception as e:
                logger.debug(f"Gemini HyDE falhou: {e}")

        # Fallback: OpenAI
        try:
            api_key = os.getenv("OPENAI_API_KEY")
            if api_key:
                client = AsyncOpenAI(api_key=api_key)
                response = await client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=self.config.hyde_max_tokens,
                    temperature=0.3,
                )
                if response.choices:
                    return response.choices[0].message.content
        except Exception as e:
            logger.debug(f"OpenAI HyDE falhou: {e}")

        return None


# =============================================================================
# Serviço Principal de Embeddings Jurídicos
# =============================================================================


@dataclass
class LegalEmbeddingResult:
    """Resultado de embedding com metadata."""

    vector: List[float]
    model: str
    processing_time_ms: float
    preprocessed_text: str
    normative_level: NormativeLevel = NormativeLevel.DOUTRINA
    citations_found: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LegalSearchResult:
    """Resultado de busca com scores multi-embedding."""

    text: str
    semantic_score: float
    bm25_score: float
    combined_score: float
    normative_level: NormativeLevel
    citations: List[Dict[str, str]]
    metadata: Dict[str, Any] = field(default_factory=dict)


class LegalEmbeddingsService:
    """
    Serviço de embeddings jurídicos brasileiros especializados.

    Combina:
    - Embeddings semânticos (OpenAI/SentenceTransformers) com pré-processamento jurídico
    - Embeddings léxicos (BM25) com vocabulário jurídico
    - Query augmentation (HyDE, multi-query, sinônimos)

    Uso:
        service = LegalEmbeddingsService()
        # Embedding de documento
        result = service.embed_document(text, legal_mode=True)
        # Embedding de query
        result = service.embed_query(query, legal_mode=True)
        # Busca com comparação
        results = await service.search_with_comparison(query, documents)
    """

    def __init__(
        self,
        config: Optional[LegalEmbeddingConfig] = None,
    ) -> None:
        self.config = config or LegalEmbeddingConfig.from_env()
        self._preprocessor = LegalPreprocessor(self.config)
        self._segmenter = LegalSegmenter(self.config)
        self._bm25 = LegalBM25(self.config)
        self._query_augmenter = LegalQueryAugmenter(self.config)

        # Embeddings service (reutiliza o existente do pipeline)
        self._embeddings_service: Optional[Any] = None
        self._fallback_model: Optional[Any] = None

        # Voyage AI provider
        self._voyage_provider: Optional[Any] = None

        self._initialized = False
        logger.info("LegalEmbeddingsService criado (lazy init)")

    def _ensure_initialized(self) -> None:
        """Inicializa serviços de embedding sob demanda."""
        if self._initialized:
            return

        # 1. Tentar Voyage AI como provider primário
        if self.config.use_voyage and is_voyage_available():
            try:
                self._voyage_provider = get_voyage_provider()
                logger.info(
                    "LegalEmbeddingsService: Voyage AI habilitado como provider primário "
                    "(model=%s)",
                    self.config.voyage_legal_model,
                )
            except Exception as e:
                logger.warning(f"Falha ao inicializar Voyage AI: {e}")
                self._voyage_provider = None

        # 2. Reutilizar o EmbeddingsService existente do pipeline (OpenAI fallback)
        try:
            from app.services.rag.core.embeddings import get_embeddings_service

            self._embeddings_service = get_embeddings_service()
            logger.info("LegalEmbeddingsService: OpenAI EmbeddingsService disponível como fallback")
        except Exception as e:
            logger.warning(f"Falha ao carregar EmbeddingsService: {e}")

        # 3. Inicializar fallback local se configurado
        if self.config.use_fallback and SentenceTransformer is not None:
            try:
                self._fallback_model = SentenceTransformer(self.config.fallback_model)
                logger.info(
                    f"LegalEmbeddingsService: SentenceTransformer fallback carregado ({self.config.fallback_model})"
                )
            except Exception as e:
                logger.warning(f"Falha ao carregar modelo fallback: {e}")

        self._initialized = True

    # -------------------------------------------------------------------------
    # Embedding de Documentos
    # -------------------------------------------------------------------------

    def embed_document(
        self,
        text: str,
        *,
        legal_mode: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> LegalEmbeddingResult:
        """
        Gera embedding para um documento jurídico.

        Args:
            text: Texto do documento
            legal_mode: Se True, aplica pré-processamento jurídico
            metadata: Metadata adicional

        Returns:
            LegalEmbeddingResult com vetor e metadata
        """
        self._ensure_initialized()
        start = time.time()

        # Pré-processamento
        if legal_mode:
            processed = self._preprocessor.preprocess(text)
        else:
            processed = text.strip()

        # Detectar nível normativo e citações
        normative_level = detect_normative_level(text) if legal_mode else NormativeLevel.DOUTRINA
        citations = extract_citations(text) if legal_mode else []

        # Gerar embedding
        vector = self._generate_embedding(
            processed, input_type="document", legal_mode=legal_mode
        )

        # Determinar modelo usado
        active_model = self.config.primary_model
        if self._voyage_provider is not None:
            active_model = self._get_voyage_model(legal_mode)

        elapsed_ms = (time.time() - start) * 1000

        return LegalEmbeddingResult(
            vector=vector,
            model=active_model,
            processing_time_ms=elapsed_ms,
            preprocessed_text=processed,
            normative_level=normative_level,
            citations_found=len(citations),
            metadata={
                **(metadata or {}),
                "legal_mode": legal_mode,
                "normative_level": normative_level.name,
                "citations_count": len(citations),
            },
        )

    def embed_documents(
        self,
        texts: List[str],
        *,
        legal_mode: bool = True,
    ) -> List[LegalEmbeddingResult]:
        """Gera embeddings para múltiplos documentos."""
        self._ensure_initialized()
        start = time.time()

        # Pré-processar todos
        if legal_mode:
            processed = [self._preprocessor.preprocess(t) for t in texts]
        else:
            processed = [t.strip() for t in texts]

        # Gerar embeddings em batch
        vectors = self._generate_embeddings_batch(
            processed, input_type="document", legal_mode=legal_mode
        )

        # Determinar modelo usado
        active_model = self.config.primary_model
        if self._voyage_provider is not None:
            active_model = self._get_voyage_model(legal_mode)

        elapsed_ms = (time.time() - start) * 1000
        per_doc_ms = elapsed_ms / len(texts) if texts else 0

        results: List[LegalEmbeddingResult] = []
        for i, (text, proc, vec) in enumerate(zip(texts, processed, vectors)):
            normative_level = detect_normative_level(text) if legal_mode else NormativeLevel.DOUTRINA
            citations = extract_citations(text) if legal_mode else []
            results.append(
                LegalEmbeddingResult(
                    vector=vec,
                    model=active_model,
                    processing_time_ms=per_doc_ms,
                    preprocessed_text=proc,
                    normative_level=normative_level,
                    citations_found=len(citations),
                    metadata={
                        "legal_mode": legal_mode,
                        "normative_level": normative_level.name,
                        "citations_count": len(citations),
                    },
                )
            )

        logger.info(
            f"Embeddings gerados: {len(texts)} docs em {elapsed_ms:.1f}ms "
            f"(legal_mode={legal_mode})"
        )
        return results

    # -------------------------------------------------------------------------
    # Embedding de Queries
    # -------------------------------------------------------------------------

    def embed_query(
        self,
        query: str,
        *,
        legal_mode: bool = True,
    ) -> LegalEmbeddingResult:
        """
        Gera embedding para uma query de busca jurídica.

        Quando legal_mode=True:
        - Aplica pré-processamento jurídico na query
        - Adiciona instrução customizada para contexto jurídico
        """
        self._ensure_initialized()
        start = time.time()

        if legal_mode:
            processed = self._preprocessor.preprocess_query(query)
        else:
            processed = query.strip()

        vector = self._generate_embedding(
            processed, input_type="query", legal_mode=legal_mode
        )

        active_model = self.config.primary_model
        if self._voyage_provider is not None:
            active_model = self._get_voyage_model(legal_mode)

        elapsed_ms = (time.time() - start) * 1000

        return LegalEmbeddingResult(
            vector=vector,
            model=active_model,
            processing_time_ms=elapsed_ms,
            preprocessed_text=processed,
            metadata={"legal_mode": legal_mode, "type": "query"},
        )

    async def embed_query_augmented(
        self,
        query: str,
        *,
        legal_mode: bool = True,
    ) -> List[LegalEmbeddingResult]:
        """
        Gera múltiplos embeddings para uma query usando augmentation.

        Retorna embeddings para:
        1. Query original (preprocessada)
        2. Query expandida com sinônimos
        3. Variações terminológicas
        4. Documento hipotético (HyDE) — se habilitado
        """
        self._ensure_initialized()
        results: List[LegalEmbeddingResult] = []

        # Gerar variações da query
        expanded_queries = self._query_augmenter.expand_query(query)

        # Gerar HyDE document
        hyde_doc: Optional[str] = None
        if self.config.enable_hyde and legal_mode:
            hyde_doc = await self._query_augmenter.generate_hyde_document(query)
            if hyde_doc:
                expanded_queries.append(hyde_doc)

        # Gerar embeddings para todas as variações
        for q in expanded_queries:
            result = self.embed_query(q, legal_mode=legal_mode)
            result.metadata["is_hyde"] = (q == hyde_doc) if hyde_doc else False
            result.metadata["is_original"] = (q == expanded_queries[0])
            results.append(result)

        logger.info(
            f"Query augmentation: {len(results)} variações geradas "
            f"(hyde={'sim' if hyde_doc else 'não'})"
        )
        return results

    # -------------------------------------------------------------------------
    # Segmentação
    # -------------------------------------------------------------------------

    def segment_document(
        self,
        text: str,
        *,
        legal_mode: bool = True,
    ) -> List[str]:
        """
        Segmenta um documento jurídico longo em chunks.

        Quando legal_mode=True, respeita limites de artigos/cláusulas.
        """
        if legal_mode:
            processed = self._preprocessor.preprocess(text)
        else:
            processed = text.strip()

        return self._segmenter.segment(processed)

    # -------------------------------------------------------------------------
    # Busca com Comparação (para endpoint /embeddings/compare)
    # -------------------------------------------------------------------------

    async def search_with_comparison(
        self,
        query: str,
        documents: List[str],
        *,
        top_k: int = 10,
    ) -> Dict[str, Any]:
        """
        Compara resultados de busca com e sem otimização jurídica.

        Returns:
            Dict com resultados "standard" e "legal" para comparação
        """
        self._ensure_initialized()

        # Busca PADRÃO (sem otimização jurídica)
        standard_start = time.time()
        standard_query_emb = self.embed_query(query, legal_mode=False)
        standard_doc_embs = self.embed_documents(documents, legal_mode=False)
        standard_scores = self._compute_similarity_scores(
            standard_query_emb.vector,
            [d.vector for d in standard_doc_embs],
        )
        standard_time = (time.time() - standard_start) * 1000

        # Busca JURÍDICA (com otimização completa)
        legal_start = time.time()

        # Embedding semântico com pré-processamento
        legal_query_emb = self.embed_query(query, legal_mode=True)
        legal_doc_embs = self.embed_documents(documents, legal_mode=True)
        semantic_scores = self._compute_similarity_scores(
            legal_query_emb.vector,
            [d.vector for d in legal_doc_embs],
        )

        # BM25 léxico
        bm25_scores = [0.0] * len(documents)
        if self.config.enable_bm25 and BM25Okapi is not None:
            processed_docs = [self._preprocessor.preprocess(d) for d in documents]
            self._bm25.index(processed_docs)
            processed_query = self._preprocessor.preprocess_query(query)
            bm25_results = self._bm25.search(processed_query, top_k=len(documents))
            for idx, score in bm25_results:
                bm25_scores[idx] = score

        # Normalizar BM25 scores para [0, 1]
        max_bm25 = max(bm25_scores) if bm25_scores and max(bm25_scores) > 0 else 1.0
        bm25_normalized = [s / max_bm25 for s in bm25_scores]

        # Score combinado (RRF-style)
        combined_scores: List[float] = []
        for sem, bm25 in zip(semantic_scores, bm25_normalized):
            combined = 0.7 * sem + 0.3 * bm25  # Peso maior para semântico
            combined_scores.append(combined)

        legal_time = (time.time() - legal_start) * 1000

        # Construir resultados com ranking
        standard_results = self._rank_results(documents, standard_scores, top_k)
        legal_results = self._rank_results_legal(
            documents, semantic_scores, bm25_normalized, combined_scores, top_k
        )

        return {
            "query": query,
            "standard": {
                "results": standard_results,
                "processing_time_ms": round(standard_time, 2),
                "model": self.config.primary_model,
            },
            "legal": {
                "results": legal_results,
                "processing_time_ms": round(legal_time, 2),
                "model": self.config.primary_model,
                "preprocessing": {
                    "original_query": query,
                    "processed_query": legal_query_emb.preprocessed_text,
                    "abbreviations_expanded": self.config.expand_abbreviations,
                    "bm25_enabled": self.config.enable_bm25,
                },
            },
            "comparison": {
                "ranking_changes": self._compute_ranking_changes(
                    standard_results, legal_results
                ),
                "score_improvements": self._compute_score_improvements(
                    standard_scores, combined_scores
                ),
            },
        }

    # -------------------------------------------------------------------------
    # Integração com Pipeline RAG Existente
    # -------------------------------------------------------------------------

    def preprocess_for_ingestion(
        self,
        text: str,
        *,
        legal_mode: bool = True,
    ) -> Dict[str, Any]:
        """
        Pré-processa documento para ingestão no pipeline RAG.

        Retorna dict compatível com o pipeline existente, adicionando
        metadata jurídica quando legal_mode=True.
        """
        if legal_mode:
            processed_text = self._preprocessor.preprocess(text)
            citations = extract_citations(text)
            normative_level = detect_normative_level(text)
            segments = self._segmenter.segment(processed_text)
        else:
            processed_text = text.strip()
            citations = []
            normative_level = NormativeLevel.DOUTRINA
            segments = self._segmenter.segment(processed_text)

        return {
            "processed_text": processed_text,
            "segments": segments,
            "legal_metadata": {
                "legal_mode": legal_mode,
                "normative_level": normative_level.name,
                "normative_level_value": int(normative_level),
                "citations": citations,
                "citations_count": len(citations),
            },
        }

    def preprocess_query_for_search(
        self,
        query: str,
        *,
        legal_mode: bool = True,
    ) -> Dict[str, Any]:
        """
        Pré-processa query para busca no pipeline RAG.

        Retorna dict com query processada e expansões.
        """
        if legal_mode:
            processed = self._preprocessor.preprocess_query(query)
            expanded = self._query_augmenter.expand_query(query)
        else:
            processed = query.strip()
            expanded = [processed]

        return {
            "original_query": query,
            "processed_query": processed,
            "expanded_queries": expanded,
            "legal_mode": legal_mode,
        }

    # -------------------------------------------------------------------------
    # Métodos Internos
    # -------------------------------------------------------------------------

    def _get_voyage_model(self, legal_mode: bool = True) -> str:
        """Retorna o modelo Voyage adequado baseado no modo."""
        if legal_mode:
            return self.config.voyage_legal_model
        return self.config.voyage_general_model

    def _generate_embedding(
        self,
        text: str,
        *,
        input_type: str = "document",
        legal_mode: bool = True,
    ) -> List[float]:
        """
        Gera um único embedding usando a cadeia de fallback:
          1. Voyage AI (quando disponível e configurado)
          2. OpenAI via EmbeddingsService do pipeline
          3. SentenceTransformers local

        Args:
            text: Texto para gerar embedding.
            input_type: "document" ou "query" (usado pelo Voyage para otimização).
            legal_mode: Se True, usa modelo jurídico do Voyage.
        """
        if not text.strip():
            return [0.0] * self.config.primary_dimensions

        # 1. Tentar Voyage AI
        if self._voyage_provider is not None:
            try:
                model = self._get_voyage_model(legal_mode)
                # Voyage é async, executar em loop
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None
                if loop is not None and loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        future = pool.submit(
                            asyncio.run,
                            self._voyage_provider.embed_query(
                                text, model=model, input_type=input_type
                            ),
                        )
                        return future.result(timeout=30)
                else:
                    return asyncio.run(
                        self._voyage_provider.embed_query(
                            text, model=model, input_type=input_type
                        )
                    )
            except Exception as e:
                logger.warning(f"Voyage AI embedding falhou, tentando fallback: {e}")

        # 2. Tentar serviço OpenAI (reutiliza o do pipeline)
        if self._embeddings_service is not None:
            try:
                return self._embeddings_service.embed_query(text)
            except Exception as e:
                logger.warning(f"OpenAI embedding falhou: {e}")

        # 3. Fallback para SentenceTransformers
        if self._fallback_model is not None:
            try:
                vec = self._fallback_model.encode(
                    [text], normalize_embeddings=True, show_progress_bar=False
                )
                return [float(x) for x in vec[0].tolist()]
            except Exception as e:
                logger.warning(f"SentenceTransformer fallback falhou: {e}")

        # Último recurso: vetor zero
        logger.error("Nenhum serviço de embedding disponível")
        return [0.0] * self.config.primary_dimensions

    def _generate_embeddings_batch(
        self,
        texts: List[str],
        *,
        input_type: str = "document",
        legal_mode: bool = True,
    ) -> List[List[float]]:
        """
        Gera embeddings em batch com cadeia de fallback:
          1. Voyage AI (batch otimizado)
          2. OpenAI via EmbeddingsService
          3. SentenceTransformers local
        """
        if not texts:
            return []

        # 1. Tentar Voyage AI
        if self._voyage_provider is not None:
            try:
                model = self._get_voyage_model(legal_mode)
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None
                if loop is not None and loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        future = pool.submit(
                            asyncio.run,
                            self._voyage_provider.embed_batch(
                                texts, model=model, input_type=input_type
                            ),
                        )
                        return future.result(timeout=120)
                else:
                    return asyncio.run(
                        self._voyage_provider.embed_batch(
                            texts, model=model, input_type=input_type
                        )
                    )
            except Exception as e:
                logger.warning(f"Voyage AI batch embedding falhou, tentando fallback: {e}")

        # 2. Tentar OpenAI
        if self._embeddings_service is not None:
            try:
                return self._embeddings_service.embed_many(texts)
            except Exception as e:
                logger.warning(f"OpenAI batch embedding falhou: {e}")

        # 3. Fallback para SentenceTransformers
        if self._fallback_model is not None:
            try:
                vecs = self._fallback_model.encode(
                    texts, normalize_embeddings=True, show_progress_bar=False
                )
                return [[float(x) for x in v.tolist()] for v in vecs]
            except Exception as e:
                logger.warning(f"SentenceTransformer batch fallback falhou: {e}")

        return [[0.0] * self.config.primary_dimensions for _ in texts]

    @staticmethod
    def _compute_similarity_scores(
        query_vector: List[float],
        doc_vectors: List[List[float]],
    ) -> List[float]:
        """Calcula cosine similarity entre query e documentos."""
        import math

        def _dot(a: List[float], b: List[float]) -> float:
            return sum(x * y for x, y in zip(a, b))

        def _norm(v: List[float]) -> float:
            return math.sqrt(sum(x * x for x in v))

        q_norm = _norm(query_vector)
        if q_norm == 0:
            return [0.0] * len(doc_vectors)

        scores: List[float] = []
        for dv in doc_vectors:
            d_norm = _norm(dv)
            if d_norm == 0:
                scores.append(0.0)
            else:
                scores.append(_dot(query_vector, dv) / (q_norm * d_norm))
        return scores

    @staticmethod
    def _rank_results(
        documents: List[str],
        scores: List[float],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """Rankeia resultados por score."""
        indexed = [(i, s) for i, s in enumerate(scores)]
        indexed.sort(key=lambda x: x[1], reverse=True)

        results: List[Dict[str, Any]] = []
        for rank, (idx, score) in enumerate(indexed[:top_k]):
            results.append({
                "rank": rank + 1,
                "doc_index": idx,
                "text_preview": documents[idx][:200],
                "score": round(score, 4),
            })
        return results

    @staticmethod
    def _rank_results_legal(
        documents: List[str],
        semantic_scores: List[float],
        bm25_scores: List[float],
        combined_scores: List[float],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """Rankeia resultados com scores detalhados."""
        indexed = [(i, c) for i, c in enumerate(combined_scores)]
        indexed.sort(key=lambda x: x[1], reverse=True)

        results: List[Dict[str, Any]] = []
        for rank, (idx, combined) in enumerate(indexed[:top_k]):
            normative = detect_normative_level(documents[idx])
            citations = extract_citations(documents[idx])
            results.append({
                "rank": rank + 1,
                "doc_index": idx,
                "text_preview": documents[idx][:200],
                "combined_score": round(combined, 4),
                "semantic_score": round(semantic_scores[idx], 4),
                "bm25_score": round(bm25_scores[idx], 4),
                "normative_level": normative.name,
                "citations_count": len(citations),
            })
        return results

    @staticmethod
    def _compute_ranking_changes(
        standard: List[Dict[str, Any]],
        legal: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Calcula mudanças de ranking entre busca padrão e jurídica."""
        changes: List[Dict[str, Any]] = []

        std_ranks = {r["doc_index"]: r["rank"] for r in standard}
        legal_ranks = {r["doc_index"]: r["rank"] for r in legal}

        all_docs = set(std_ranks.keys()) | set(legal_ranks.keys())
        for doc_idx in all_docs:
            std_rank = std_ranks.get(doc_idx)
            leg_rank = legal_ranks.get(doc_idx)
            if std_rank is not None and leg_rank is not None:
                delta = std_rank - leg_rank  # Positivo = subiu no ranking jurídico
                if delta != 0:
                    changes.append({
                        "doc_index": doc_idx,
                        "standard_rank": std_rank,
                        "legal_rank": leg_rank,
                        "delta": delta,
                        "direction": "up" if delta > 0 else "down",
                    })

        changes.sort(key=lambda x: abs(x["delta"]), reverse=True)
        return changes

    @staticmethod
    def _compute_score_improvements(
        standard_scores: List[float],
        legal_scores: List[float],
    ) -> Dict[str, Any]:
        """Calcula estatísticas de melhoria de scores."""
        if not standard_scores or not legal_scores:
            return {}

        improvements = [l - s for s, l in zip(standard_scores, legal_scores)]
        return {
            "avg_improvement": round(sum(improvements) / len(improvements), 4),
            "max_improvement": round(max(improvements), 4),
            "min_improvement": round(min(improvements), 4),
            "docs_improved": sum(1 for i in improvements if i > 0),
            "docs_degraded": sum(1 for i in improvements if i < 0),
            "docs_unchanged": sum(1 for i in improvements if i == 0),
        }


# =============================================================================
# Singleton e Factory
# =============================================================================

_legal_service: Optional[LegalEmbeddingsService] = None
_legal_service_lock = threading.Lock()


def get_legal_embeddings_service() -> LegalEmbeddingsService:
    """Retorna o singleton do serviço de embeddings jurídicos (thread-safe)."""
    global _legal_service
    if _legal_service is not None:
        return _legal_service

    with _legal_service_lock:
        if _legal_service is None:
            _legal_service = LegalEmbeddingsService()

    return _legal_service


def reset_legal_embeddings_service() -> None:
    """Reseta o singleton (útil para testes)."""
    global _legal_service
    with _legal_service_lock:
        _legal_service = None
