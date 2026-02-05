"""
Regional Sources Catalog — Catálogo explícito de Fontes Regionais (por jurisdição).

Objetivo:
- Dar ao usuário um seletor "Harvey-like" de fontes públicas por jurisdição, com sub-fontes.
- Permitir filtragem segura no Corpus Global via `metadata.source_id` (OpenSearch) / `source_id` (Qdrant payload).

Notas:
- Este catálogo é *declarativo*: ele não faz crawling/sync. Ele só descreve "o que é" uma fonte.
- A filtragem só funciona se os chunks foram indexados com `source_id` coerente com este catálogo.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional


@dataclass(frozen=True)
class RegionalSource:
    id: str
    label: str
    jurisdiction: str  # ISO-3166 alpha-2 (BR, US, UK...), EU, INT
    collections: List[str]  # rag sources (lei, juris, doutrina, ...)
    domains: List[str]
    description: Optional[str] = None
    status: Optional[str] = None  # EA/GA, etc (informativo)
    sync: Optional[str] = None  # live/weekly, etc (informativo)


_CATALOG: List[RegionalSource] = [
    # ---------------------------------------------------------------------
    # BR — Brasil
    # ---------------------------------------------------------------------
    RegionalSource(
        id="br_planalto",
        label="Planalto (Legislação)",
        jurisdiction="BR",
        collections=["lei"],
        domains=["www.planalto.gov.br"],
        description="Leis, decretos e normas federais (portal Planalto).",
        status="GA",
        sync="manual",
    ),
    RegionalSource(
        id="br_lexml",
        label="LexML (Legislação)",
        jurisdiction="BR",
        collections=["lei"],
        domains=["www.lexml.gov.br"],
        description="Agregador de legislação e atos normativos (LexML).",
        status="GA",
        sync="manual",
    ),
    RegionalSource(
        id="br_stf",
        label="STF (Jurisprudência)",
        jurisdiction="BR",
        collections=["juris"],
        domains=["portal.stf.jus.br", "www.stf.jus.br"],
        description="Jurisprudência e decisões do Supremo Tribunal Federal.",
        status="GA",
        sync="manual",
    ),
    RegionalSource(
        id="br_stj",
        label="STJ (Jurisprudência)",
        jurisdiction="BR",
        collections=["juris"],
        domains=["www.stj.jus.br"],
        description="Jurisprudência e decisões do Superior Tribunal de Justiça.",
        status="GA",
        sync="manual",
    ),
    RegionalSource(
        id="br_tst",
        label="TST (Jurisprudência)",
        jurisdiction="BR",
        collections=["juris"],
        domains=["www.tst.jus.br"],
        description="Jurisprudência trabalhista do Tribunal Superior do Trabalho.",
        status="EA",
        sync="manual",
    ),
    RegionalSource(
        id="br_cnj",
        label="CNJ (Regulação)",
        jurisdiction="BR",
        collections=["doutrina", "juris"],
        domains=["www.cnj.jus.br"],
        description="Resoluções, provimentos e atos do Conselho Nacional de Justiça.",
        status="EA",
        sync="manual",
    ),
    RegionalSource(
        id="br_dou",
        label="Diário Oficial (DOU)",
        jurisdiction="BR",
        collections=["sei", "doutrina", "lei"],
        domains=["www.in.gov.br"],
        description="Publicações oficiais federais (DOU).",
        status="EA",
        sync="manual",
    ),
    # ---------------------------------------------------------------------
    # US — Estados Unidos
    # ---------------------------------------------------------------------
    RegionalSource(
        id="us_supreme_court",
        label="US Supreme Court",
        jurisdiction="US",
        collections=["juris"],
        domains=["www.supremecourt.gov"],
        description="Decisões e materiais do Supreme Court of the United States.",
        status="EA",
        sync="manual",
    ),
    RegionalSource(
        id="us_cornell_law",
        label="Cornell LII",
        jurisdiction="US",
        collections=["lei", "doutrina"],
        domains=["www.law.cornell.edu"],
        description="Leis e materiais jurídicos (Legal Information Institute).",
        status="EA",
        sync="manual",
    ),
    # ---------------------------------------------------------------------
    # EU — União Europeia
    # ---------------------------------------------------------------------
    RegionalSource(
        id="eu_eurlex",
        label="EUR-Lex",
        jurisdiction="EU",
        collections=["lei"],
        domains=["eur-lex.europa.eu"],
        description="Direito da União Europeia (regulamentos, diretivas, etc.).",
        status="EA",
        sync="manual",
    ),
    RegionalSource(
        id="eu_curia",
        label="CURIA (CJEU)",
        jurisdiction="EU",
        collections=["juris"],
        domains=["curia.europa.eu"],
        description="Jurisprudência do Tribunal de Justiça da União Europeia.",
        status="EA",
        sync="manual",
    ),
    # ---------------------------------------------------------------------
    # UK — Reino Unido
    # ---------------------------------------------------------------------
    RegionalSource(
        id="uk_legislation",
        label="legislation.gov.uk",
        jurisdiction="UK",
        collections=["lei"],
        domains=["www.legislation.gov.uk"],
        description="Legislação do Reino Unido (UK legislation portal).",
        status="EA",
        sync="manual",
    ),
    RegionalSource(
        id="uk_bailii",
        label="BAILII",
        jurisdiction="UK",
        collections=["juris"],
        domains=["www.bailii.org"],
        description="Base pública de jurisprudência do Reino Unido e Irlanda.",
        status="EA",
        sync="manual",
    ),
    # ---------------------------------------------------------------------
    # INT — Internacional (multi/geral)
    # ---------------------------------------------------------------------
    RegionalSource(
        id="int_wipo",
        label="WIPO",
        jurisdiction="INT",
        collections=["lei", "doutrina"],
        domains=["www.wipo.int"],
        description="Organização Mundial da Propriedade Intelectual (normas e materiais).",
        status="EA",
        sync="manual",
    ),
]


def get_regional_sources_catalog() -> Dict[str, object]:
    """
    Retorna o catálogo como dict serializável, para uso em endpoints.
    """
    sources = []
    jurisdictions: List[str] = []
    seen_j = set()
    for s in _CATALOG:
        jurisdictions.append(s.jurisdiction)
        seen_j.add(s.jurisdiction)
        sources.append(
            {
                "id": s.id,
                "label": s.label,
                "jurisdiction": s.jurisdiction,
                "collections": list(s.collections or []),
                "domains": list(s.domains or []),
                "description": s.description,
                "status": s.status,
                "sync": s.sync,
            }
        )
    jurisdictions = sorted(list(seen_j))
    return {
        "sources": sources,
        "jurisdictions": jurisdictions,
        "updated_at": datetime.now(timezone.utc),
    }

