"""
Shared fixtures and mocks for RAG pipeline tests.

Provides:
- Mock OpenSearch client responses
- Mock Qdrant client responses
- Mock embedding responses
- Sample legal documents (legislation, jurisprudence)
- Sample queries with expected results
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# =============================================================================
# Sample Legal Documents (Brazilian Legal Domain)
# =============================================================================

SAMPLE_LEGISLATION = [
    {
        "chunk_uid": "lei-8666-art-21",
        "text": """Art. 21. Os avisos contendo os resumos dos editais das concorrencias,
        das tomadas de precos, dos concursos e dos leiloes, embora realizados no local
        da reparticao interessada, deverao ser publicados com antecedencia, no minimo,
        por uma vez: I - no Diario Oficial da Uniao, quando se tratar de licitacao feita
        por orgao ou entidade da Administracao Publica Federal.""",
        "metadata": {
            "source": "lei",
            "lei_numero": "8666",
            "artigo": "21",
            "tipo": "legislacao_federal",
        },
        "score": 0.85,
    },
    {
        "chunk_uid": "cf88-art-5",
        "text": """Art. 5o Todos sao iguais perante a lei, sem distincao de qualquer natureza,
        garantindo-se aos brasileiros e aos estrangeiros residentes no Pais a inviolabilidade
        do direito a vida, a liberdade, a igualdade, a seguranca e a propriedade, nos termos
        seguintes: I - homens e mulheres sao iguais em direitos e obrigacoes, nos termos
        desta Constituicao; II - ninguem sera obrigado a fazer ou deixar de fazer alguma
        coisa senao em virtude de lei.""",
        "metadata": {
            "source": "lei",
            "lei_numero": "constituicao_federal",
            "artigo": "5",
            "tipo": "constituicao",
        },
        "score": 0.92,
    },
    {
        "chunk_uid": "clt-art-482",
        "text": """Art. 482 - Constituem justa causa para rescisao do contrato de trabalho
        pelo empregador: a) ato de improbidade; b) incontinencia de conduta ou mau procedimento;
        c) negociacao habitual por conta propria ou alheia sem permissao do empregador, e quando
        constituir ato de concorrencia a empresa para a qual trabalha o empregado, ou for
        prejudicial ao servico.""",
        "metadata": {
            "source": "lei",
            "lei_numero": "CLT",
            "artigo": "482",
            "tipo": "consolidacao",
        },
        "score": 0.78,
    },
    {
        "chunk_uid": "cdc-art-14",
        "text": """Art. 14. O fornecedor de servicos responde, independentemente da existencia
        de culpa, pela reparacao dos danos causados aos consumidores por defeitos relativos
        a prestacao dos servicos, bem como por informacoes insuficientes ou inadequadas sobre
        sua fruicao e riscos. Paragrafo 1o O servico e defeituoso quando nao fornece a
        seguranca que o consumidor dele pode esperar.""",
        "metadata": {
            "source": "lei",
            "lei_numero": "8078",
            "artigo": "14",
            "tipo": "codigo_defesa_consumidor",
        },
        "score": 0.81,
    },
]


SAMPLE_JURISPRUDENCE = [
    {
        "chunk_uid": "stj-resp-123456",
        "text": """RECURSO ESPECIAL. DIREITO CIVIL. RESPONSABILIDADE CIVIL. DANO MORAL.
        QUANTUM INDENIZATORIO. REVISAO. POSSIBILIDADE. O Superior Tribunal de Justica
        admite a revisao do valor fixado a titulo de danos morais quando irrisorio ou
        exorbitante. Recurso especial conhecido e provido para majorar o valor da
        indenizacao para R$ 50.000,00 (cinquenta mil reais).""",
        "metadata": {
            "source": "juris",
            "tribunal": "STJ",
            "tipo_recurso": "REsp",
            "numero": "123456",
            "relator": "Min. Teste",
        },
        "score": 0.88,
    },
    {
        "chunk_uid": "stf-adi-5678",
        "text": """ACAO DIRETA DE INCONSTITUCIONALIDADE. LEI ESTADUAL. COMPETENCIA
        LEGISLATIVA. DIREITO DO TRABALHO. A competencia para legislar sobre direito
        do trabalho e privativa da Uniao, nos termos do art. 22, I, da Constituicao
        Federal. Lei estadual que dispoe sobre materia trabalhista e inconstitucional.
        Acao julgada procedente.""",
        "metadata": {
            "source": "juris",
            "tribunal": "STF",
            "tipo_recurso": "ADI",
            "numero": "5678",
            "relator": "Min. Exemplo",
        },
        "score": 0.91,
    },
    {
        "chunk_uid": "tst-rr-987654",
        "text": """RECURSO DE REVISTA. HORAS EXTRAS. INTERVALO INTRAJORNADA. REDUCAO.
        CONVENIO COLETIVO. VALIDADE. Sumula 437 do TST. O intervalo minimo intrajornada
        de uma hora, previsto no art. 71 da CLT, nao pode ser reduzido por convenio
        coletivo. A reducao configura norma de higiene, saude e seguranca do trabalho.
        Recurso de revista conhecido e provido.""",
        "metadata": {
            "source": "juris",
            "tribunal": "TST",
            "tipo_recurso": "RR",
            "numero": "987654",
            "relator": "Min. Trabalhista",
        },
        "score": 0.75,
    },
]


SAMPLE_MODEL_DOCUMENTS = [
    {
        "chunk_uid": "peca-peticao-inicial",
        "text": """EXCELENTISSIMO SENHOR DOUTOR JUIZ DE DIREITO DA VARA CIVEL DA COMARCA
        DE SAO PAULO - ESTADO DE SAO PAULO. FULANO DE TAL, brasileiro, solteiro,
        advogado, inscrito na OAB/SP sob o n. 123.456, residente e domiciliado na
        Rua Exemplo, n. 100, Bairro Centro, CEP 01234-567, Sao Paulo/SP, vem,
        respeitosamente, perante Vossa Excelencia, propor a presente ACAO DE
        INDENIZACAO POR DANOS MORAIS E MATERIAIS em face de EMPRESA RE S.A.""",
        "metadata": {
            "source": "pecas_modelo",
            "tipo_peca": "peticao_inicial",
            "materia": "civel",
        },
        "score": 0.72,
    },
    {
        "chunk_uid": "peca-contestacao",
        "text": """CONTESTACAO. A re, devidamente qualificada nos autos, por seu
        advogado que esta subscreve, vem, respeitosamente, apresentar CONTESTACAO
        a acao ordinaria proposta pelo autor. Preliminarmente, arguir-se-a a
        ilegitimidade passiva ad causam. No merito, a acao deve ser julgada
        totalmente improcedente pelos motivos que passa a expor.""",
        "metadata": {
            "source": "pecas_modelo",
            "tipo_peca": "contestacao",
            "materia": "civel",
        },
        "score": 0.68,
    },
]


# =============================================================================
# Sample Queries with Expected Results
# =============================================================================

SAMPLE_QUERIES = {
    "licitacao_publicacao": {
        "query": "Qual o prazo de publicacao de edital de licitacao?",
        "expected_sources": ["lei-8666-art-21"],
        "expected_min_score": 0.7,
    },
    "justa_causa_improbidade": {
        "query": "Quais sao as hipoteses de justa causa no direito do trabalho?",
        "expected_sources": ["clt-art-482"],
        "expected_min_score": 0.7,
    },
    "dano_moral_stj": {
        "query": "Revisao de dano moral no STJ",
        "expected_sources": ["stj-resp-123456"],
        "expected_min_score": 0.8,
    },
    "direito_consumidor_defeito": {
        "query": "Responsabilidade do fornecedor por defeito no servico CDC",
        "expected_sources": ["cdc-art-14"],
        "expected_min_score": 0.7,
    },
    "competencia_direito_trabalho": {
        "query": "Competencia legislativa em materia trabalhista",
        "expected_sources": ["stf-adi-5678"],
        "expected_min_score": 0.8,
    },
}


# =============================================================================
# Mock Embedding Data
# =============================================================================

def generate_mock_embedding(text: str, dimensions: int = 3072) -> List[float]:
    """
    Generate a deterministic mock embedding based on text hash.

    This ensures the same text always produces the same embedding,
    which is important for testing consistency.
    """
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()
    # Use hash bytes to seed embedding values
    embedding = []
    for i in range(dimensions):
        byte_idx = i % 32
        val = int(h[byte_idx * 2:(byte_idx + 1) * 2], 16) / 255.0
        # Add some variation based on position
        embedding.append((val - 0.5) * 2 + (i % 10) * 0.01)
    # Normalize
    norm = sum(x ** 2 for x in embedding) ** 0.5
    return [x / norm for x in embedding]


MOCK_EMBEDDINGS = {
    "licitacao": generate_mock_embedding("licitacao edital publicacao"),
    "justa_causa": generate_mock_embedding("justa causa rescisao trabalho"),
    "dano_moral": generate_mock_embedding("dano moral indenizacao"),
    "consumidor": generate_mock_embedding("consumidor fornecedor defeito"),
}


# =============================================================================
# Mock Client Factories
# =============================================================================

@dataclass
class MockOpenSearchResponse:
    """Mock OpenSearch search response."""

    hits: List[Dict[str, Any]] = field(default_factory=list)
    total: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hits": {
                "total": {"value": self.total},
                "hits": [
                    {
                        "_id": h.get("chunk_uid", f"doc_{i}"),
                        "_score": h.get("score", 0.5),
                        "_source": h,
                    }
                    for i, h in enumerate(self.hits)
                ],
            }
        }


def create_mock_opensearch_client(
    documents: Optional[List[Dict[str, Any]]] = None,
) -> MagicMock:
    """
    Create a mock OpenSearch client with predefined responses.

    Args:
        documents: List of documents to return from searches.
                  Defaults to SAMPLE_LEGISLATION + SAMPLE_JURISPRUDENCE.

    Returns:
        Mock OpenSearch client
    """
    docs = documents or (SAMPLE_LEGISLATION + SAMPLE_JURISPRUDENCE)

    mock_client = MagicMock()

    def mock_search(index: str, body: Dict, **kwargs) -> Dict:
        """Simulate OpenSearch search."""
        query_text = ""
        if "query" in body:
            if "match" in body["query"]:
                query_text = list(body["query"]["match"].values())[0]
            elif "multi_match" in body["query"]:
                query_text = body["query"]["multi_match"].get("query", "")
            elif "bool" in body["query"]:
                # Handle bool queries
                should = body["query"]["bool"].get("should", [])
                for clause in should:
                    if "match" in clause:
                        query_text = list(clause["match"].values())[0]
                        break

        size = body.get("size", 10)

        # Filter and sort by score
        filtered = [d for d in docs if query_text.lower() in d.get("text", "").lower()]
        if not filtered:
            filtered = docs  # Return all if no match

        filtered = sorted(filtered, key=lambda x: x.get("score", 0), reverse=True)[:size]

        response = MockOpenSearchResponse(hits=filtered, total=len(filtered))
        return response.to_dict()

    mock_client.search = MagicMock(side_effect=mock_search)
    mock_client.index = MagicMock(return_value={"result": "created"})
    mock_client.delete = MagicMock(return_value={"result": "deleted"})
    mock_client.bulk = MagicMock(return_value={"errors": False})
    mock_client.indices.exists = MagicMock(return_value=True)
    mock_client.indices.create = MagicMock(return_value={"acknowledged": True})

    return mock_client


@dataclass
class MockQdrantSearchResult:
    """Mock Qdrant search result point."""

    id: str
    score: float
    payload: Dict[str, Any]
    vector: Optional[List[float]] = None


def create_mock_qdrant_client(
    documents: Optional[List[Dict[str, Any]]] = None,
) -> MagicMock:
    """
    Create a mock Qdrant client with predefined responses.

    Args:
        documents: List of documents to return from searches.
                  Defaults to SAMPLE_LEGISLATION + SAMPLE_JURISPRUDENCE.

    Returns:
        Mock Qdrant client
    """
    docs = documents or (SAMPLE_LEGISLATION + SAMPLE_JURISPRUDENCE)

    mock_client = MagicMock()

    def mock_search(
        collection_name: str,
        query_vector: List[float],
        limit: int = 10,
        **kwargs,
    ) -> List[MockQdrantSearchResult]:
        """Simulate Qdrant vector search."""
        # Return documents sorted by score
        sorted_docs = sorted(docs, key=lambda x: x.get("score", 0), reverse=True)[:limit]

        return [
            MockQdrantSearchResult(
                id=d.get("chunk_uid", f"doc_{i}"),
                score=d.get("score", 0.5),
                payload={
                    "text": d.get("text", ""),
                    "metadata": d.get("metadata", {}),
                    "chunk_uid": d.get("chunk_uid", ""),
                },
            )
            for i, d in enumerate(sorted_docs)
        ]

    mock_client.search = MagicMock(side_effect=mock_search)
    mock_client.upsert = MagicMock(return_value=None)
    mock_client.delete = MagicMock(return_value=None)
    mock_client.get_collection = MagicMock(
        return_value=MagicMock(
            points_count=len(docs),
            config=MagicMock(params=MagicMock(vectors=MagicMock(size=3072))),
        )
    )
    mock_client.collection_exists = MagicMock(return_value=True)
    mock_client.create_collection = MagicMock(return_value=True)

    return mock_client


def create_mock_embedding_service() -> MagicMock:
    """
    Create a mock embedding service.

    Returns:
        Mock embedding service that generates deterministic embeddings
    """
    mock_service = MagicMock()

    def embed_text(text: str) -> List[float]:
        return generate_mock_embedding(text)

    async def embed_text_async(text: str) -> List[float]:
        return generate_mock_embedding(text)

    def embed_batch(texts: List[str]) -> List[List[float]]:
        return [generate_mock_embedding(t) for t in texts]

    async def embed_batch_async(texts: List[str]) -> List[List[float]]:
        return [generate_mock_embedding(t) for t in texts]

    mock_service.embed = MagicMock(side_effect=embed_text)
    mock_service.embed_async = AsyncMock(side_effect=embed_text_async)
    mock_service.embed_batch = MagicMock(side_effect=embed_batch)
    mock_service.embed_batch_async = AsyncMock(side_effect=embed_batch_async)

    return mock_service


# =============================================================================
# Pytest Fixtures
# =============================================================================

@pytest.fixture
def sample_legislation() -> List[Dict[str, Any]]:
    """Fixture providing sample legislation documents."""
    return SAMPLE_LEGISLATION.copy()


@pytest.fixture
def sample_jurisprudence() -> List[Dict[str, Any]]:
    """Fixture providing sample jurisprudence documents."""
    return SAMPLE_JURISPRUDENCE.copy()


@pytest.fixture
def sample_model_documents() -> List[Dict[str, Any]]:
    """Fixture providing sample model document pieces."""
    return SAMPLE_MODEL_DOCUMENTS.copy()


@pytest.fixture
def all_sample_documents() -> List[Dict[str, Any]]:
    """Fixture providing all sample documents combined."""
    return SAMPLE_LEGISLATION + SAMPLE_JURISPRUDENCE + SAMPLE_MODEL_DOCUMENTS


@pytest.fixture
def sample_queries() -> Dict[str, Dict[str, Any]]:
    """Fixture providing sample queries with expected results."""
    return SAMPLE_QUERIES.copy()


@pytest.fixture
def mock_opensearch_client(all_sample_documents):
    """Fixture providing a mock OpenSearch client."""
    return create_mock_opensearch_client(all_sample_documents)


@pytest.fixture
def mock_qdrant_client(all_sample_documents):
    """Fixture providing a mock Qdrant client."""
    return create_mock_qdrant_client(all_sample_documents)


@pytest.fixture
def mock_embedding_service():
    """Fixture providing a mock embedding service."""
    return create_mock_embedding_service()


@pytest.fixture
def high_score_results() -> List[Dict[str, Any]]:
    """Fixture providing results with high scores (CRAG gate should pass)."""
    return [
        {"chunk_uid": "doc1", "text": "High relevance document", "score": 0.85},
        {"chunk_uid": "doc2", "text": "Another relevant doc", "score": 0.75},
        {"chunk_uid": "doc3", "text": "Third relevant doc", "score": 0.70},
    ]


@pytest.fixture
def low_score_results() -> List[Dict[str, Any]]:
    """Fixture providing results with low scores (CRAG gate should fail)."""
    return [
        {"chunk_uid": "doc1", "text": "Low relevance document", "score": 0.35},
        {"chunk_uid": "doc2", "text": "Another low relevance doc", "score": 0.30},
        {"chunk_uid": "doc3", "text": "Third low relevance doc", "score": 0.25},
    ]


@pytest.fixture
def mixed_score_results() -> List[Dict[str, Any]]:
    """Fixture providing results with mixed scores."""
    return [
        {"chunk_uid": "doc1", "text": "High score doc", "score": 0.80},
        {"chunk_uid": "doc2", "text": "Medium score doc", "score": 0.50},
        {"chunk_uid": "doc3", "text": "Low score doc", "score": 0.20},
        {"chunk_uid": "doc4", "text": "Very low score doc", "score": 0.10},
    ]


@pytest.fixture
def empty_results() -> List[Dict[str, Any]]:
    """Fixture providing empty results."""
    return []


@pytest.fixture
def legal_domain_documents() -> List[Dict[str, Any]]:
    """Fixture providing documents with legal domain patterns."""
    return [
        {
            "chunk_uid": "legal1",
            "text": "Art. 5o da Constituicao Federal preve que todos sao iguais perante a lei.",
            "score": 0.70,
        },
        {
            "chunk_uid": "legal2",
            "text": "Conforme Sumula 331 do TST, o tomador de servicos responde subsidiariamente.",
            "score": 0.65,
        },
        {
            "chunk_uid": "legal3",
            "text": "O acordao proferido pelo STJ no REsp 123456 estabeleceu jurisprudencia.",
            "score": 0.60,
        },
        {
            "chunk_uid": "non-legal",
            "text": "Este e um documento generico sem termos juridicos especificos.",
            "score": 0.75,
        },
    ]


# =============================================================================
# Helper Functions for Tests
# =============================================================================

def assert_valid_evaluation(evaluation: Any) -> None:
    """Assert that a CRAG evaluation has all required fields."""
    assert hasattr(evaluation, "gate_passed")
    assert hasattr(evaluation, "evidence_level")
    assert hasattr(evaluation, "best_score")
    assert hasattr(evaluation, "avg_top3")
    assert hasattr(evaluation, "result_count")
    assert hasattr(evaluation, "reasons")
    assert hasattr(evaluation, "recommended_actions")


def assert_valid_rerank_result(result: Any) -> None:
    """Assert that a rerank result has all required fields."""
    assert hasattr(result, "results")
    assert hasattr(result, "original_count")
    assert hasattr(result, "reranked_count")
    assert hasattr(result, "model_used")
    assert hasattr(result, "duration_ms")


def create_results_with_scores(scores: List[float]) -> List[Dict[str, Any]]:
    """Create a list of results with specific scores."""
    return [
        {
            "chunk_uid": f"doc_{i}",
            "text": f"Document {i} with score {score}",
            "score": score,
        }
        for i, score in enumerate(scores)
    ]


def create_results_with_final_scores(scores: List[float]) -> List[Dict[str, Any]]:
    """Create a list of results with final_score field."""
    return [
        {
            "chunk_uid": f"doc_{i}",
            "text": f"Document {i} with final score {score}",
            "final_score": score,
        }
        for i, score in enumerate(scores)
    ]
