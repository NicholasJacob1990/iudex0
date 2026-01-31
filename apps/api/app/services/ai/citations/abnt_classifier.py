"""
ABNT Citation Classifier — Classifica e formata fontes em ABNT completo.

Classifica fontes por tipo (web, jurisprudência, legislação, doutrina, artigo)
e formata referências bibliográficas no padrão ABNT.
"""

from enum import Enum
from typing import Dict, List, Any, Optional
from datetime import datetime
import re


class SourceType(Enum):
    WEB = "web"
    JURISPRUDENCIA = "jurisprudencia"
    LEGISLACAO = "legislacao"
    DOUTRINA = "doutrina"
    ARTIGO = "artigo"
    AUTOS = "autos"


# Domínios conhecidos para classificação
JURISPRUDENCIA_DOMAINS = [
    "stf.jus.br", "stj.jus.br", "tst.jus.br",
    "trf1.jus.br", "trf2.jus.br", "trf3.jus.br", "trf4.jus.br", "trf5.jus.br", "trf6.jus.br",
    "tjsp.jus.br", "tjrj.jus.br", "tjmg.jus.br", "tjrs.jus.br", "tjpr.jus.br",
    "tjsc.jus.br", "tjba.jus.br", "tjpe.jus.br", "tjce.jus.br", "tjgo.jus.br",
    "tjdft.jus.br", "tjes.jus.br", "tjal.jus.br", "tjma.jus.br",
    "cnj.jus.br", "jusbrasil.com.br",
]

LEGISLACAO_DOMAINS = [
    "planalto.gov.br", "senado.leg.br", "camara.leg.br",
    "normas.leg.br", "lexml.gov.br",
]

ACADEMIC_DOMAINS = [
    "scielo.br", "scholar.google", "periodicos.capes",
    "bdtd.ibict.br", "repositorio.", "revista.",
]

# Padrões regex para detecção
JURIS_PATTERNS = [
    r"(?i)(STF|STJ|TST|TRF|TJ[A-Z]{2})\b",
    r"(?i)(RE|REsp|HC|MS|ADI|ADPF|AgRg|EDcl)\s*n?[ºo.]?\s*[\d.]",
    r"(?i)s[uú]mula\s*(vinculante\s*)?\s*n?[ºo.]?\s*\d+",
    r"(?i)relator[a]?\s*:?\s*(min|des|dr)",
]

LEGISLACAO_PATTERNS = [
    r"(?i)lei\s*(complementar\s*)?n?[ºo.]?\s*[\d.]",
    r"(?i)(decreto|portaria|resolução|instrução normativa)\s*n?[ºo.]?\s*[\d.]",
    r"(?i)art\.?\s*\d+.*(?:CF|constituição|código|lei)",
    r"(?i)código\s+(civil|penal|processo|trabalho|tributário|defesa)",
]


def classify_source(source: Dict[str, Any]) -> SourceType:
    """
    Classifica uma fonte pelo URL, título e metadados.

    Prioridade: domínio > padrões no título > fallback web.
    """
    url = str(source.get("url", "")).lower()
    title = str(source.get("title", "")).lower()
    text = f"{title} {url}"

    # 1. Classificação por domínio
    for domain in JURISPRUDENCIA_DOMAINS:
        if domain in url:
            return SourceType.JURISPRUDENCIA

    for domain in LEGISLACAO_DOMAINS:
        if domain in url:
            return SourceType.LEGISLACAO

    for domain in ACADEMIC_DOMAINS:
        if domain in url:
            return SourceType.ARTIGO

    # 2. Classificação por padrões no título/texto
    juris_score = sum(1 for p in JURIS_PATTERNS if re.search(p, text))
    legis_score = sum(1 for p in LEGISLACAO_PATTERNS if re.search(p, text))

    if juris_score >= 2:
        return SourceType.JURISPRUDENCIA
    if legis_score >= 2:
        return SourceType.LEGISLACAO
    if juris_score == 1 and legis_score == 0:
        return SourceType.JURISPRUDENCIA
    if legis_score == 1 and juris_score == 0:
        return SourceType.LEGISLACAO

    # 3. Heurísticas adicionais
    if source.get("source_type") == "autos" or source.get("from_rag_local"):
        return SourceType.AUTOS

    if any(kw in text for kw in ["isbn", "editora", "edição", "ed."]):
        return SourceType.DOUTRINA

    if any(kw in text for kw in ["revista", "periódico", "v.", "vol.", "issn"]):
        return SourceType.ARTIGO

    return SourceType.WEB


def _pt_br_month(month: int) -> str:
    meses = [
        "jan.", "fev.", "mar.", "abr.", "maio", "jun.",
        "jul.", "ago.", "set.", "out.", "nov.", "dez."
    ]
    return meses[max(0, min(11, month - 1))]


def _pt_br_month_full(month: int) -> str:
    meses = [
        "janeiro", "fevereiro", "março", "abril", "maio", "junho",
        "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"
    ]
    return meses[max(0, min(11, month - 1))]


def _access_date(accessed_at: Optional[datetime] = None) -> str:
    dt = accessed_at or datetime.now()
    return f"{dt.day} {_pt_br_month(dt.month)} {dt.year}"


def format_abnt_web(source: Dict[str, Any], accessed_at: Optional[datetime] = None) -> str:
    """ABNT para fontes web."""
    author = source.get("author") or source.get("institution") or ""
    title = source.get("title", "Fonte")
    url = source.get("url", "")

    author_part = f"{author.upper()}. " if author else ""
    access = _access_date(accessed_at)

    if url:
        return f"{author_part}**{title}**. Disponível em: <{url}>. Acesso em: {access}."
    return f"{author_part}**{title}**."


def format_abnt_jurisprudencia(source: Dict[str, Any]) -> str:
    """ABNT para jurisprudência."""
    tribunal = source.get("tribunal", "").upper()
    tipo_recurso = source.get("tipo_recurso", "")
    numero = source.get("numero", "")
    relator = source.get("relator", "")
    data_julgamento = source.get("data_julgamento", "")
    ementa = source.get("ementa_resumo", "")

    # Tenta extrair do título se campos não estão preenchidos
    title = source.get("title", "")
    if not tribunal:
        m = re.search(r"(?i)(STF|STJ|TST|TRF\d|TJ[A-Z]{2})", title)
        if m:
            tribunal = m.group(1).upper()

    parts = []
    if tribunal:
        parts.append(f"{tribunal}.")
    if tipo_recurso and numero:
        parts.append(f"{tipo_recurso} nº {numero}.")
    elif title:
        parts.append(f"{title}.")
    if relator:
        parts.append(f"Relator(a): {relator}.")
    if data_julgamento:
        parts.append(f"Julgamento: {data_julgamento}.")
    if ementa:
        parts.append(f"{ementa[:200]}.")

    url = source.get("url", "")
    if url:
        parts.append(f"Disponível em: <{url}>.")
        parts.append(f"Acesso em: {_access_date()}.")

    return " ".join(parts)


def format_abnt_legislacao(source: Dict[str, Any]) -> str:
    """ABNT para legislação."""
    pais = source.get("pais", "BRASIL")
    tipo_norma = source.get("tipo_norma", "")
    numero = source.get("numero", "")
    data = source.get("data", "")
    descricao = source.get("descricao", "")

    title = source.get("title", "")

    parts = [f"{pais.upper()}."]
    if tipo_norma and numero:
        parts.append(f"{tipo_norma} nº {numero},")
    elif title:
        parts.append(f"{title}.")
    if data:
        parts.append(f"de {data}.")
    if descricao:
        parts.append(f"{descricao}.")

    url = source.get("url", "")
    if url:
        parts.append(f"Disponível em: <{url}>.")
        parts.append(f"Acesso em: {_access_date()}.")

    return " ".join(parts)


def format_abnt_doutrina(source: Dict[str, Any]) -> str:
    """ABNT para livros/doutrina."""
    autor = source.get("author", source.get("autor", ""))
    titulo = source.get("title", source.get("titulo", ""))
    edicao = source.get("edicao", "")
    local = source.get("local", "")
    editora = source.get("editora", "")
    ano = source.get("ano", "")
    paginas = source.get("paginas", "")

    parts = []
    if autor:
        # Converter "Nome Sobrenome" -> "SOBRENOME, Nome"
        names = autor.strip().split()
        if len(names) > 1:
            parts.append(f"{names[-1].upper()}, {' '.join(names[:-1])}.")
        else:
            parts.append(f"{autor.upper()}.")

    if titulo:
        parts.append(f"**{titulo}**.")
    if edicao:
        parts.append(f"{edicao}.")
    if local and editora:
        parts.append(f"{local}: {editora},")
    elif editora:
        parts.append(f"{editora},")
    if ano:
        parts.append(f"{ano}.")
    if paginas:
        parts.append(f"p. {paginas}.")

    return " ".join(parts)


def format_abnt_artigo(source: Dict[str, Any]) -> str:
    """ABNT para artigos científicos."""
    autor = source.get("author", source.get("autor", ""))
    titulo_artigo = source.get("title", source.get("titulo", ""))
    revista = source.get("revista", source.get("journal", ""))
    volume = source.get("volume", "")
    numero = source.get("numero_revista", source.get("issue", ""))
    paginas = source.get("paginas", source.get("pages", ""))
    ano = source.get("ano", source.get("year", ""))

    parts = []
    if autor:
        names = autor.strip().split()
        if len(names) > 1:
            parts.append(f"{names[-1].upper()}, {' '.join(names[:-1])}.")
        else:
            parts.append(f"{autor.upper()}.")

    if titulo_artigo:
        parts.append(f"{titulo_artigo}.")
    if revista:
        parts.append(f"**{revista}**,")
    if volume:
        parts.append(f"v. {volume},")
    if numero:
        parts.append(f"n. {numero},")
    if paginas:
        parts.append(f"p. {paginas},")
    if ano:
        parts.append(f"{ano}.")

    url = source.get("url", "")
    if url:
        parts.append(f"Disponível em: <{url}>.")
        parts.append(f"Acesso em: {_access_date()}.")

    return " ".join(parts)


def format_abnt_full(source: Dict[str, Any], source_type: Optional[SourceType] = None) -> str:
    """Formata referência ABNT completa baseada no tipo classificado."""
    if source_type is None:
        source_type = classify_source(source)

    formatters = {
        SourceType.WEB: format_abnt_web,
        SourceType.JURISPRUDENCIA: format_abnt_jurisprudencia,
        SourceType.LEGISLACAO: format_abnt_legislacao,
        SourceType.DOUTRINA: format_abnt_doutrina,
        SourceType.ARTIGO: format_abnt_artigo,
        SourceType.AUTOS: format_abnt_web,  # fallback para web format
    }

    formatter = formatters.get(source_type, format_abnt_web)
    try:
        return formatter(source)
    except Exception:
        # Fallback seguro
        title = source.get("title", "Fonte")
        url = source.get("url", "")
        return format_abnt_web({"title": title, "url": url})


def build_full_references_section(
    sources: List[Dict[str, Any]],
    heading: str = "REFERÊNCIAS BIBLIOGRÁFICAS",
) -> str:
    """
    Gera seção completa de referências bibliográficas em ABNT.
    Agrupa por tipo e numera sequencialmente.
    """
    if not sources:
        return ""

    lines = [f"\n---\n\n## {heading}\n"]

    for i, source in enumerate(sources, 1):
        source_type = classify_source(source)
        ref = format_abnt_full(source, source_type)
        lines.append(f"[{source.get('number', i)}] {ref}")

    return "\n".join(lines) + "\n"
