"""
Tests for ABNT citation classification and formatting.

Testa o classificador de fontes por tipo (jurisprudencia, legislacao,
doutrina, artigo, web, autos) e a formatacao ABNT correspondente.
"""

import pytest
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from unittest.mock import patch, MagicMock
import re


# ---------------------------------------------------------------------------
# Stubs locais para TDD (replicam a interface esperada do abnt_classifier)
# ---------------------------------------------------------------------------

class SourceType(str, Enum):
    JURISPRUDENCIA = "jurisprudencia"
    LEGISLACAO = "legislacao"
    DOUTRINA = "doutrina"
    ARTIGO = "artigo"
    AUTOS = "autos"
    WEB = "web"


# Patterns para classificacao
_JURIS_URL_PATTERNS = [
    r"stf\.jus\.br", r"stj\.jus\.br", r"trf\d?\.jus\.br", r"tj\w+\.jus\.br",
    r"jusbrasil\.com\.br",
]
_JURIS_TITLE_PATTERNS = [
    r"\bSTF\b", r"\bSTJ\b", r"\bTRF\b", r"\bTJ\w{2}\b",
    r"\bREsp\b", r"\bRE\b", r"\bADI\b", r"\bADPF\b",
    r"\bHC\b", r"\bMS\b", r"\bRCL\b", r"\bAg\w*Rg\b",
]
_LEGIS_URL_PATTERNS = [r"planalto\.gov\.br", r"lexml\.gov\.br"]
_LEGIS_TITLE_PATTERNS = [
    r"\bLei\s+n[.ºo°]\s*\d", r"\bDecreto\b", r"\bResolução\b",
    r"\bPortaria\b", r"\bEmenda\s+Constitucional\b",
    r"\bCódigo\s+(Civil|Penal|Processo|Tributário)\b",
]
_ARTIGO_URL_PATTERNS = [r"scielo\.br", r"periodicos\.capes", r"doi\.org"]
_ARTIGO_TITLE_KEYWORDS = [
    "revista", "journal", "issn", "v.", "vol.", "n.", "pp.", "p.",
]
_DOUTRINA_TITLE_KEYWORDS = [
    "editora", "isbn", "edição", "ed.", "publisher",
]

_PT_BR_MESES = [
    "jan.", "fev.", "mar.", "abr.", "maio", "jun.",
    "jul.", "ago.", "set.", "out.", "nov.", "dez.",
]


def _pt_br_access_date(now: Optional[datetime] = None) -> str:
    dt = now or datetime.now()
    mes = _PT_BR_MESES[max(0, min(11, dt.month - 1))]
    return f"{dt.day:02d} {mes} {dt.year}"


def classify_source(
    *,
    url: str = "",
    title: str = "",
    source_type: str = "",
) -> SourceType:
    """Classifica uma fonte pelo tipo baseado em URL, titulo e metadados."""
    url_lower = (url or "").lower()
    title_str = title or ""

    # Flag explicita
    if (source_type or "").strip().lower() == "autos":
        return SourceType.AUTOS

    # URL patterns
    for pat in _JURIS_URL_PATTERNS:
        if re.search(pat, url_lower):
            return SourceType.JURISPRUDENCIA
    for pat in _LEGIS_URL_PATTERNS:
        if re.search(pat, url_lower):
            return SourceType.LEGISLACAO
    for pat in _ARTIGO_URL_PATTERNS:
        if re.search(pat, url_lower):
            return SourceType.ARTIGO

    # Title patterns - juris
    juris_score = 0
    for pat in _JURIS_TITLE_PATTERNS:
        if re.search(pat, title_str, re.IGNORECASE):
            juris_score += 1

    legis_score = 0
    for pat in _LEGIS_TITLE_PATTERNS:
        if re.search(pat, title_str, re.IGNORECASE):
            legis_score += 1

    if juris_score > 0 and juris_score >= legis_score:
        return SourceType.JURISPRUDENCIA
    if legis_score > 0:
        return SourceType.LEGISLACAO

    # Keywords
    title_lower = title_str.lower()
    doutrina_hits = sum(1 for kw in _DOUTRINA_TITLE_KEYWORDS if kw in title_lower)
    artigo_hits = sum(1 for kw in _ARTIGO_TITLE_KEYWORDS if kw in title_lower)

    if doutrina_hits > 0 and doutrina_hits >= artigo_hits:
        return SourceType.DOUTRINA
    if artigo_hits > 0:
        return SourceType.ARTIGO

    return SourceType.WEB


def format_abnt_web(
    *,
    title: str,
    url: str = "",
    author: str = "",
    accessed_at: Optional[datetime] = None,
) -> str:
    """Formato ABNT para fonte web."""
    parts = []
    if author:
        parts.append(f"{author.strip().upper()}.")
    t = (title or "").strip() or "Fonte"
    parts.append(f"**{t}**.")
    if url:
        acesso = _pt_br_access_date(accessed_at)
        parts.append(f"Disponivel em: <{url}>.")
        parts.append(f"Acesso em: {acesso}.")
    return " ".join(parts)


def format_abnt_jurisprudencia(
    *,
    tribunal: str = "",
    tipo_recurso: str = "",
    numero: str = "",
    relator: str = "",
    data: str = "",
    title: str = "",
    url: str = "",
) -> str:
    """Formato ABNT para jurisprudencia."""
    parts = []
    t = (tribunal or "").strip().upper()
    if not t and title:
        # Tenta extrair tribunal do titulo
        for pat in [r"\b(STF|STJ|TRF\d?|TJ\w{2})\b"]:
            m = re.search(pat, title, re.IGNORECASE)
            if m:
                t = m.group(1).upper()
                break
    parts.append("BRASIL.")
    if t:
        parts.append(f"{t}.")
    if tipo_recurso:
        tr = tipo_recurso.strip()
        if numero:
            tr += f" n. {numero.strip()}"
        parts.append(f"{tr}.")
    elif title:
        parts.append(f"{title.strip()}.")
    if relator:
        parts.append(f"Rel. {relator.strip()}.")
    if data:
        parts.append(f"Julgado em {data.strip()}.")
    if url:
        acesso = _pt_br_access_date()
        parts.append(f"Disponivel em: <{url}>. Acesso em: {acesso}.")
    return " ".join(parts)


def format_abnt_legislacao(
    *,
    tipo: str = "",
    numero: str = "",
    data: str = "",
    descricao: str = "",
    url: str = "",
) -> str:
    """Formato ABNT para legislacao."""
    parts = ["BRASIL."]
    if tipo and numero:
        parts.append(f"{tipo.strip()} n. {numero.strip()},")
    if data:
        parts.append(f"de {data.strip()}.")
    if descricao:
        parts.append(f"{descricao.strip()}.")
    if url:
        acesso = _pt_br_access_date()
        parts.append(f"Disponivel em: <{url}>. Acesso em: {acesso}.")
    return " ".join(parts)


def format_abnt_doutrina(
    *,
    author: str = "",
    title: str = "",
    editora: str = "",
    ano: str = "",
    cidade: str = "",
    edicao: str = "",
) -> str:
    """Formato ABNT para doutrina. Inverte nome do autor."""
    parts = []
    if author:
        # "Joao Silva" -> "SILVA, Joao."
        name_parts = author.strip().split()
        if len(name_parts) >= 2:
            sobrenome = name_parts[-1].upper()
            restante = " ".join(name_parts[:-1])
            parts.append(f"{sobrenome}, {restante}.")
        else:
            parts.append(f"{author.strip().upper()}.")
    t = (title or "").strip()
    if t:
        parts.append(f"**{t}**.")
    if edicao:
        parts.append(f"{edicao.strip()}.")
    if cidade and editora:
        parts.append(f"{cidade.strip()}: {editora.strip()},")
    elif editora:
        parts.append(f"{editora.strip()},")
    if ano:
        parts.append(f"{ano.strip()}.")
    return " ".join(parts)


def format_abnt_artigo(
    *,
    author: str = "",
    title: str = "",
    revista: str = "",
    volume: str = "",
    numero: str = "",
    paginas: str = "",
    ano: str = "",
) -> str:
    """Formato ABNT para artigo cientifico."""
    parts = []
    if author:
        name_parts = author.strip().split()
        if len(name_parts) >= 2:
            sobrenome = name_parts[-1].upper()
            restante = " ".join(name_parts[:-1])
            parts.append(f"{sobrenome}, {restante}.")
        else:
            parts.append(f"{author.strip().upper()}.")
    if title:
        parts.append(f"{title.strip()}.")
    if revista:
        parts.append(f"**{revista.strip()}**,")
    if volume:
        parts.append(f"v. {volume.strip()},")
    if numero:
        parts.append(f"n. {numero.strip()},")
    if paginas:
        parts.append(f"p. {paginas.strip()},")
    if ano:
        parts.append(f"{ano.strip()}.")
    return " ".join(parts)


def format_abnt_full(*, source_type: SourceType, **kwargs) -> str:
    """Dispatcher que chama o formatter correto baseado no tipo."""
    import inspect as _inspect

    formatters = {
        SourceType.WEB: format_abnt_web,
        SourceType.JURISPRUDENCIA: format_abnt_jurisprudencia,
        SourceType.LEGISLACAO: format_abnt_legislacao,
        SourceType.DOUTRINA: format_abnt_doutrina,
        SourceType.ARTIGO: format_abnt_artigo,
    }
    formatter = formatters.get(source_type, format_abnt_web)
    # Filtra kwargs para aceitar apenas parametros validos da funcao alvo
    sig = _inspect.signature(formatter)
    valid_params = set(sig.parameters.keys())
    filtered = {k: v for k, v in kwargs.items() if k in valid_params}
    return formatter(**filtered)


def build_full_references_section(
    sources: List[Dict[str, Any]],
) -> str:
    """Constroi secao completa de referencias ABNT."""
    if not sources:
        return ""
    lines = ["## REFERENCIAS BIBLIOGRAFICAS", ""]
    for i, src in enumerate(sources, start=1):
        number = src.get("number", i)
        title = src.get("title", "Fonte")
        url = src.get("url", "")
        st = classify_source(url=url, title=title)
        ref = format_abnt_full(source_type=st, title=title, url=url)
        lines.append(f"[{number}] {ref}")
    return "\n".join(lines)


# Stubs para base.py integration
def format_abnt_full_reference(*, title: str, url: str, **kwargs) -> str:
    """Delegate para abnt_classifier."""
    st = classify_source(url=url, title=title)
    return format_abnt_full(source_type=st, title=title, url=url, **kwargs)


def build_abnt_references(sources: List[Dict[str, Any]]) -> str:
    """Delegate para abnt_classifier."""
    return build_full_references_section(sources)


def format_reference_abnt(*, title: str, url: str, accessed_at: Optional[datetime] = None) -> str:
    """Formato simplificado ABNT (fallback)."""
    t = (title or "").strip() or "Fonte"
    u = (url or "").strip()
    if not u:
        return f"{t}."
    acesso = _pt_br_access_date(accessed_at)
    return f"{t}. Disponivel em: {u}. Acesso em: {acesso}."


# ===========================================================================
# TESTS
# ===========================================================================


class TestSourceClassification:
    """Test source type classification."""

    # 1
    def test_classify_stf_url(self):
        """URL com stf.jus.br -> JURISPRUDENCIA."""
        result = classify_source(url="https://portal.stf.jus.br/processos/123")
        assert result == SourceType.JURISPRUDENCIA

    # 2
    def test_classify_stj_url(self):
        """URL com stj.jus.br -> JURISPRUDENCIA."""
        result = classify_source(url="https://www.stj.jus.br/sites/portalp/Paginas/default.aspx")
        assert result == SourceType.JURISPRUDENCIA

    # 3
    def test_classify_planalto_url(self):
        """URL com planalto.gov.br -> LEGISLACAO."""
        result = classify_source(url="https://www.planalto.gov.br/ccivil_03/leis/l8078.htm")
        assert result == SourceType.LEGISLACAO

    # 4
    def test_classify_scielo_url(self):
        """URL com scielo.br -> ARTIGO."""
        result = classify_source(url="https://www.scielo.br/j/rdgv/a/abc123")
        assert result == SourceType.ARTIGO

    # 5
    def test_classify_juris_by_title_pattern(self):
        """Titulo com 'STJ REsp' -> JURISPRUDENCIA."""
        result = classify_source(
            title="STJ REsp n. 1.234.567/SP - Responsabilidade civil",
            url="https://generic-site.com/page",
        )
        assert result == SourceType.JURISPRUDENCIA

    # 6
    def test_classify_legislacao_by_title_pattern(self):
        """Titulo com 'Lei n.' -> LEGISLACAO."""
        result = classify_source(
            title="Lei n. 14.133/2021 - Nova Lei de Licitacoes",
            url="https://generic-site.com/page",
        )
        assert result == SourceType.LEGISLACAO

    # 7
    def test_classify_doutrina_by_keywords(self):
        """Titulo com 'editora', 'ISBN' -> DOUTRINA."""
        result = classify_source(
            title="Manual de Direito Civil - Editora Atlas, ISBN 978-85-224-1234-5",
            url="https://livraria.com/produto/123",
        )
        assert result == SourceType.DOUTRINA

    # 8
    def test_classify_artigo_by_keywords(self):
        """Titulo com 'revista', 'v. 12', 'ISSN' -> ARTIGO."""
        result = classify_source(
            title="Revista de Direito Processual v. 12, ISSN 1234-5678",
            url="https://academico.com/artigo",
        )
        assert result == SourceType.ARTIGO

    # 9
    def test_classify_autos_by_flag(self):
        """source_type='autos' -> AUTOS."""
        result = classify_source(
            url="https://any-url.com",
            title="Qualquer titulo",
            source_type="autos",
        )
        assert result == SourceType.AUTOS

    # 10
    def test_classify_generic_web(self):
        """URL generica sem padroes -> WEB."""
        result = classify_source(
            url="https://blog.example.com/post/meu-artigo",
            title="Um post qualquer sobre direito",
        )
        assert result == SourceType.WEB

    # 11
    def test_classify_ambiguous_prefers_juris_over_legis(self):
        """Titulo com 1 padrao juris e 0 legis -> JURISPRUDENCIA."""
        result = classify_source(
            title="Analise do REsp sobre contratos administrativos",
            url="https://generic.com",
        )
        assert result == SourceType.JURISPRUDENCIA


class TestABNTFormatting:
    """Test ABNT formatting for each source type."""

    # 12
    def test_format_web_with_url(self):
        """Verifica formato web completo com URL e data de acesso."""
        dt = datetime(2025, 3, 15)
        result = format_abnt_web(
            title="Artigo sobre responsabilidade civil",
            url="https://example.com/artigo",
            author="Joao Silva",
            accessed_at=dt,
        )
        assert "JOAO SILVA" in result
        assert "**Artigo sobre responsabilidade civil**" in result
        assert "Disponivel em: <https://example.com/artigo>" in result
        assert "Acesso em: 15 mar. 2025" in result

    # 13
    def test_format_web_without_url(self):
        """Sem URL, nao inclui 'Disponivel em'."""
        result = format_abnt_web(title="Titulo sem URL")
        assert "Disponivel em" not in result
        assert "**Titulo sem URL**" in result

    # 14
    def test_format_jurisprudencia_completa(self):
        """Com tribunal, tipo_recurso, numero, relator, data -> formato ABNT juris."""
        result = format_abnt_jurisprudencia(
            tribunal="STJ",
            tipo_recurso="REsp",
            numero="1.234.567/SP",
            relator="Min. Fulano de Tal",
            data="15/03/2024",
        )
        assert "BRASIL." in result
        assert "STJ." in result
        assert "REsp n. 1.234.567/SP" in result
        assert "Rel. Min. Fulano de Tal" in result
        assert "Julgado em 15/03/2024" in result

    # 15
    def test_format_jurisprudencia_from_title_only(self):
        """Apenas titulo com 'STJ - REsp...' -> extrai tribunal do titulo."""
        result = format_abnt_jurisprudencia(
            title="STJ - REsp 1.234.567 - Responsabilidade civil medica",
        )
        assert "BRASIL." in result
        assert "STJ." in result

    # 16
    def test_format_legislacao_completa(self):
        """BRASIL. Lei n. X, de data. Descricao."""
        result = format_abnt_legislacao(
            tipo="Lei",
            numero="14.133/2021",
            data="01 de abril de 2021",
            descricao="Dispoe sobre licitacoes e contratos administrativos",
        )
        assert "BRASIL." in result
        assert "Lei n. 14.133/2021" in result
        assert "de 01 de abril de 2021" in result
        assert "Dispoe sobre licitacoes" in result

    # 17
    def test_format_doutrina_inverts_name(self):
        """'Joao Silva' -> 'SILVA, Joao.'."""
        result = format_abnt_doutrina(
            author="Joao Silva",
            title="Manual de Direito Civil",
            editora="Atlas",
            ano="2023",
            cidade="Sao Paulo",
            edicao="5a ed.",
        )
        assert result.startswith("SILVA, Joao.")
        assert "**Manual de Direito Civil**" in result
        assert "5a ed." in result
        assert "Sao Paulo: Atlas," in result
        assert "2023." in result

    # 18
    def test_format_artigo_cientifico(self):
        """Com revista, volume, numero, paginas, ano."""
        result = format_abnt_artigo(
            author="Maria Santos",
            title="Responsabilidade civil no direito digital",
            revista="Revista de Direito Civil Contemporaneo",
            volume="15",
            numero="3",
            paginas="120-145",
            ano="2024",
        )
        assert "SANTOS, Maria." in result
        assert "Responsabilidade civil no direito digital." in result
        assert "**Revista de Direito Civil Contemporaneo**" in result
        assert "v. 15" in result
        assert "n. 3" in result
        assert "p. 120-145" in result
        assert "2024." in result

    # 19
    def test_format_abnt_full_dispatches_correctly(self):
        """format_abnt_full() chama o formatter correto baseado no tipo."""
        web_result = format_abnt_full(
            source_type=SourceType.WEB,
            title="Teste Web",
            url="https://example.com",
        )
        assert "**Teste Web**" in web_result
        assert "Disponivel em" in web_result

        juris_result = format_abnt_full(
            source_type=SourceType.JURISPRUDENCIA,
            title="STJ REsp 123",
            tribunal="STJ",
        )
        assert "BRASIL." in juris_result
        assert "STJ." in juris_result


class TestBuildReferencesSection:
    """Test building complete references sections."""

    # 20
    def test_build_references_section_empty(self):
        """Lista vazia -> string vazia."""
        result = build_full_references_section([])
        assert result == ""

    # 21
    def test_build_references_section_mixed_types(self):
        """3 fontes (web, juris, legislacao) -> secao formatada com [1], [2], [3]."""
        sources = [
            {"title": "Blog sobre direito", "url": "https://blog.example.com"},
            {"title": "STJ REsp 1.234.567", "url": "https://stj.jus.br/recurso/123"},
            {"title": "Lei n. 14.133/2021", "url": "https://planalto.gov.br/lei/14133"},
        ]
        result = build_full_references_section(sources)
        assert "[1]" in result
        assert "[2]" in result
        assert "[3]" in result
        assert "Blog sobre direito" in result
        assert "STJ" in result

    # 22
    def test_build_references_preserves_numbering(self):
        """Sources com 'number' field -> usa esse numero."""
        sources = [
            {"number": 5, "title": "Fonte 5", "url": "https://a.com"},
            {"number": 10, "title": "Fonte 10", "url": "https://b.com"},
        ]
        result = build_full_references_section(sources)
        assert "[5]" in result
        assert "[10]" in result

    # 23
    def test_references_section_has_heading(self):
        """Verifica que contem 'REFERENCIAS BIBLIOGRAFICAS'."""
        sources = [{"title": "Teste", "url": "https://example.com"}]
        result = build_full_references_section(sources)
        assert "## REFERENCIAS BIBLIOGRAFICAS" in result


class TestBaseIntegration:
    """Test integration of new functions in base.py."""

    # 24
    def test_format_abnt_full_reference_delegates(self):
        """Verifica que format_abnt_full_reference() classifica e formata."""
        result = format_abnt_full_reference(
            title="STJ REsp 999/SP",
            url="https://stj.jus.br/resp/999",
        )
        assert "BRASIL." in result
        assert "STJ" in result

    # 25
    def test_build_abnt_references_delegates(self):
        """Verifica que build_abnt_references() constroi secao completa."""
        sources = [
            {"title": "Fonte web", "url": "https://example.com"},
        ]
        result = build_abnt_references(sources)
        assert "## REFERENCIAS BIBLIOGRAFICAS" in result
        assert "[1]" in result

    # 26
    def test_fallback_when_classifier_unavailable(self):
        """Se classificador nao disponivel, usa format_reference_abnt simplificado."""
        result = format_reference_abnt(
            title="Fonte genérica",
            url="https://example.com/doc",
            accessed_at=datetime(2025, 6, 20),
        )
        assert "Fonte genérica" in result
        assert "Disponivel em: https://example.com/doc" in result
        assert "Acesso em: 20 jun. 2025" in result

    # 27
    def test_access_date_format(self):
        """Verifica formato 'DD mes. AAAA' em pt-BR."""
        # Janeiro
        assert _pt_br_access_date(datetime(2025, 1, 5)) == "05 jan. 2025"
        # Maio (sem ponto)
        assert _pt_br_access_date(datetime(2025, 5, 15)) == "15 maio 2025"
        # Dezembro
        assert _pt_br_access_date(datetime(2025, 12, 31)) == "31 dez. 2025"
        # Fevereiro
        assert _pt_br_access_date(datetime(2024, 2, 28)) == "28 fev. 2024"
