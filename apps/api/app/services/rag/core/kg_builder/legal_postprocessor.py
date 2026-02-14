"""
Post-processing for the legal Neo4j knowledge graph.

This module ports the most useful parts of the standalone `ingest_v2.py`
post-processing into the Iudex KG Builder context:
- Fix obvious label/type confusions (Tema vs Decisao)
- Normalize a few noisy name variants
- Merge duplicates while preserving relationships (APOC when available)

It is designed to be safe and optional (env-gated in the KG Builder pipeline).
"""

from __future__ import annotations

import logging
import os
import re
from datetime import date
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

def _env_bool(name: str, default: bool = False) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    if not v:
        return default
    return v in ("1", "true", "t", "yes", "y", "on")


@dataclass
class LegalPostProcessStats:
    tema_from_decisao: int = 0
    decisao_name_normalized: int = 0
    decisao_duplicates_merged: int = 0
    artigo_duplicates_merged: int = 0
    sumula_duplicates_merged: int = 0
    decisao_relabel_to_tribunal: int = 0
    temas_invalidos_removidos: int = 0
    self_loops_removidos: int = 0
    decisao_interpreta_trimmed: int = 0
    decisao_fixa_tese_trimmed: int = 0
    decisao_julga_tema_trimmed: int = 0
    artigo_names_normalized: int = 0
    compound_decisao_removed: int = 0
    aplica_to_aplica_sumula_migrated: int = 0
    decisao_python_normalized: int = 0
    sumula_python_normalized: int = 0
    lei_python_normalized: int = 0
    tese_python_normalized: int = 0
    doutrina_python_normalized: int = 0
    doutrina_duplicates_merged: int = 0
    caselaw_python_normalized: int = 0
    caselaw_duplicates_merged: int = 0
    statute_python_normalized: int = 0
    statute_duplicates_merged: int = 0
    directive_python_normalized: int = 0
    directive_duplicates_merged: int = 0
    regulation_python_normalized: int = 0
    regulation_duplicates_merged: int = 0
    treaty_python_normalized: int = 0
    treaty_duplicates_merged: int = 0
    international_decision_python_normalized: int = 0
    international_decision_duplicates_merged: int = 0
    relationships_deduped: int = 0
    garbage_artigo_removed: int = 0
    subdispositivo_de_inferred: int = 0
    # Normative chain validation stats
    orphan_artigos_fixed: int = 0
    orphan_subdispositivos_fixed: int = 0
    orphan_artigos_remaining: int = 0
    orphan_subdispositivos_remaining: int = 0
    temporal_relationships_enriched: int = 0
    # Link inference stats (Phase 1: structural)
    transitive_remete_a_inferred: int = 0
    transitive_cita_inferred: int = 0
    co_citation_links_inferred: int = 0
    parent_inheritance_links_inferred: int = 0
    symmetric_cita_inferred: int = 0
    jurisprudence_cluster_links_inferred: int = 0
    # Link inference stats (Phase 2: embedding similarity)
    embedding_decisao_links_inferred: int = 0
    embedding_sumula_links_inferred: int = 0
    embedding_doutrina_links_inferred: int = 0
    embedding_artigo_links_inferred: int = 0
    embedding_cross_type_links_inferred: int = 0
    # Link inference stats (Phase 3: LLM validation)
    llm_links_suggested: int = 0
    llm_links_created: int = 0
    llm_api_calls: int = 0
    llm_evidence_validated: int = 0
    llm_evidence_failed: int = 0
    llm_l2_candidates_validated: int = 0
    llm_l2_candidates_rejected: int = 0
    # Link inference stats (Phase 3b: exploratory)
    exploratory_isolated_found: int = 0
    exploratory_nodes_explored: int = 0
    exploratory_links_created: int = 0
    exploratory_api_calls: int = 0
    warnings: List[str] = None

    def __post_init__(self) -> None:
        if self.warnings is None:
            self.warnings = []


# ============================================================
# NORMALIZATION CONSTANTS
# ============================================================

_SIGLAS_ALL = frozenset([
    "CF", "CC", "CPC", "CTN", "CDC", "CP", "CLT", "LEF", "LMS",
    "ADCT", "ECA", "CTB", "LINDB", "LRF",
])

_NAME_EXPANSIONS: List[Tuple[str, str]] = [
    ("Constituição Federal", "CF"), ("Constituicao Federal", "CF"), ("CRFB", "CF"),
    ("Código Civil", "CC"), ("Codigo Civil", "CC"),
    ("Código de Processo Civil", "CPC"), ("Codigo de Processo Civil", "CPC"),
    ("Código Tributário Nacional", "CTN"), ("Codigo Tributario Nacional", "CTN"),
    ("Código de Defesa do Consumidor", "CDC"), ("Codigo de Defesa do Consumidor", "CDC"),
    ("Código Penal", "CP"), ("Codigo Penal", "CP"),
    ("Consolidação das Leis do Trabalho", "CLT"), ("Consolidacao das Leis do Trabalho", "CLT"),
    ("Código de 2015", "CPC"), ("Codigo de 2015", "CPC"),
]

# ============================================================
# TEMPORAL NORMALIZATION (best-effort)
# ============================================================

_MONTHS_PT: Dict[str, int] = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,
    "mar\u00e7o": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}

_RE_DMY = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})\b")
_RE_LONG_PT = re.compile(
    r"\b(\d{1,2})\s+de\s+([A-Za-z\u00c0-\u00ff]+)\s+de\s+(\d{4})\b",
    flags=re.IGNORECASE,
)


def _date_to_iso(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}-{d.day:02d}"


def _parse_date_iso(text: str) -> Optional[Tuple[str, str]]:
    """
    Extract a single date from text.

    Returns (date_raw, date_iso) or None.
    """
    raw = (text or "").strip()
    if not raw:
        return None

    m = _RE_DMY.search(raw)
    if m:
        try:
            dd = int(m.group(1))
            mm = int(m.group(2))
            yy = int(m.group(3))
            if yy < 100:
                yy = 2000 + yy if yy < 50 else 1900 + yy
            d = date(yy, mm, dd)
            return (m.group(0), _date_to_iso(d))
        except Exception:
            pass

    m = _RE_LONG_PT.search(raw)
    if m:
        try:
            dd = int(m.group(1))
            month_raw = (m.group(2) or "").strip().lower()
            yy = int(m.group(3))
            mm = _MONTHS_PT.get(month_raw)
            if mm:
                d = date(yy, mm, dd)
                return (m.group(0), _date_to_iso(d))
        except Exception:
            pass

    return None


def _enrich_temporal_relationships(session) -> int:
    """
    Best-effort enrichment: when a relationship has `evidence` and the evidence contains
    an explicit date, set `date_raw` and `date_iso` on the relationship.
    """
    target_types = [
        "REVOGA",
        "ALTERA",
        "PUBLICADA_EM",
        "ENTRA_EM_VIGOR_EM",
        "VIGORA_DESDE",
        "VIGORA_ATE",
    ]
    updated = 0

    rows = list(
        session.run(
            "MATCH ()-[r]->() "
            "WHERE type(r) IN $types AND r.evidence IS NOT NULL "
            "  AND (r.date_iso IS NULL OR trim(toString(r.date_iso)) = '') "
            "RETURN id(r) AS rid, type(r) AS t, toString(r.evidence) AS ev "
            "LIMIT 5000",
            types=target_types,
        )
    )
    if not rows:
        return 0

    for row in rows:
        rid = row.get("rid")
        ev = row.get("ev") or ""
        parsed = _parse_date_iso(str(ev))
        if not parsed:
            continue
        date_raw, date_iso = parsed
        try:
            session.run(
                "MATCH ()-[r]->() WHERE id(r) = $rid "
                "SET r.date_raw = $raw, r.date_iso = $iso "
                "RETURN 1",
                rid=rid,
                raw=date_raw,
                iso=date_iso,
            )
            updated += 1
        except Exception:
            continue

    return updated

# Gender fixes: feminine nouns that should use "da" not "do"
_GENDER_FIXES: List[Tuple[str, str]] = [
    ("do Lei ", "da Lei "), ("do Lei", "da Lei"),
    ("do LC ", "da LC "), ("do LC", "da LC"),
    ("do EC ", "da EC "), ("do EC", "da EC"),
    ("do LINDB", "da LINDB"),
    ("do LRF", "da LRF"),
    ("do Resoluc", "da Resoluc"),
]

# Relationship types to exclude from dedup (infrastructure rels)
_INFRA_REL_TYPES = frozenset(["FROM_CHUNK", "FROM_DOCUMENT", "NEXT_CHUNK"])


# ============================================================
# NORMALIZATION FUNCTIONS (ported from fix_normalization.py)
# ============================================================


def _normalize_artigo_name(name: str) -> str:
    """Aggressive normalization for Artigo node names."""
    n = name
    # Accented chars
    n = n.replace("§", "par.").replace("º", "o").replace("ª", "a")
    # Code name expansions
    for long, short in _NAME_EXPANSIONS:
        n = n.replace(long, short)
    # Standardize prepositions to "do" for siglas
    for sigla in _SIGLAS_ALL:
        n = n.replace(f" da {sigla}", f" do {sigla}")
        n = n.replace(f" na {sigla}", f" do {sigla}")
    # Fix feminine nouns/siglas back to "da"
    for wrong, right in _GENDER_FIXES:
        n = n.replace(wrong, right)
    # Paragraph normalization
    n = n.replace(", par.", " par.").replace(",par.", " par.")
    n = re.sub(r"par\.\s+", "par.", n)
    # Inciso normalization
    n = n.replace(", inc.", " inc.").replace(",inc.", " inc.")
    n = n.replace(", inciso ", " inc.").replace(" inciso ", " inc.")
    # nº removal
    n = n.replace("nº ", "").replace("n° ", "").replace("Nº ", "")
    # Remove trailing period (but not "par.")
    if n.endswith(".") and not n.endswith("par."):
        n = n.rstrip(".")
    # Multiple spaces
    n = re.sub(r"\s+", " ", n).strip()
    return n


def _normalize_decisao_name(name: str) -> str:
    """Normalize Decisao names: remove dots in numbers, accents."""
    n = name
    n = n.replace("nº ", "").replace("n° ", "").replace("Nº ", "")
    n = n.replace("Repercussão", "Repercussao")
    # Remove dots in case numbers: "4.650" -> "4650" (2 passes)
    n = re.sub(r"(\d)\.(\d)", r"\1\2", n)
    n = re.sub(r"(\d)\.(\d)", r"\1\2", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def _normalize_sumula_name(name: str) -> str:
    """Normalize Sumula names: remove accents."""
    n = name
    n = n.replace("Súmula", "Sumula").replace("súmula", "sumula")
    n = n.replace("nº ", "").replace("n° ", "").replace("Nº ", "")
    n = re.sub(r"\s+", " ", n).strip()
    return n


def _normalize_lei_name(name: str) -> str:
    """Normalize Lei names: expansions + Lei Complementar → LC."""
    n = name
    for long, short in _NAME_EXPANSIONS:
        n = n.replace(long, short)
    n = n.replace("nº ", "").replace("n° ", "").replace("Nº ", "")
    n = re.sub(r"Lei Complementar (\d)", r"LC \1", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def _normalize_tese_name(name: str) -> str:
    """Light normalization for Tese: trailing period removal."""
    n = name.strip()
    n = n.rstrip(".")
    n = re.sub(r"\s+", " ", n).strip()
    return n


def _normalize_doutrina_name(name: str) -> str:
    """Normalize Doutrina names: standardize author names and book titles."""
    n = name
    # Remove honorifics and standardize
    n = n.replace(" Junior", " Jr.").replace(" Júnior", " Jr.")
    n = n.replace(" Filho", " Filho").replace(" Filha", " Filha")
    # Remove extra quotes
    n = n.replace('"', '').replace("'", '')
    # Multiple spaces
    n = re.sub(r"\s+", " ", n).strip()
    return n


def _normalize_caselaw_name(name: str) -> str:
    """Normalize CaseLaw (Common Law precedents): standardize case citations."""
    n = name
    # Standardize "v." vs "v" vs "vs." vs "vs"
    n = re.sub(r'\s+vs?\.?\s+', ' v. ', n, flags=re.IGNORECASE)
    # Remove extra spaces around brackets
    n = re.sub(r'\s*\[\s*', ' [', n)
    n = re.sub(r'\s*\]\s*', '] ', n)
    # Remove extra spaces around parentheses
    n = re.sub(r'\s*\(\s*', ' (', n)
    n = re.sub(r'\s*\)\s*', ') ', n)
    # Multiple spaces
    n = re.sub(r"\s+", " ", n).strip()
    return n


def _normalize_statute_name(name: str) -> str:
    """Normalize Statute names: standardize statute/code citations."""
    n = name
    # Standardize "Act" capitalization
    n = re.sub(r'\sact\s', ' Act ', n)
    n = re.sub(r'\sAct of\s', ' Act of ', n)
    # Remove extra quotes
    n = n.replace('"', '').replace("'", '')
    # Multiple spaces
    n = re.sub(r"\s+", " ", n).strip()
    return n


def _normalize_directive_name(name: str) -> str:
    """Normalize EU Directive names: standardize directive citations."""
    n = name
    # Standardize "Directive" capitalization
    n = re.sub(r'\sdirective\s', ' Directive ', n, flags=re.IGNORECASE)
    # Standardize number format: (EU) or (EC)
    n = re.sub(r'\(eu\)', '(EU)', n, flags=re.IGNORECASE)
    n = re.sub(r'\(ec\)', '(EC)', n, flags=re.IGNORECASE)
    # Multiple spaces
    n = re.sub(r"\s+", " ", n).strip()
    return n


def _normalize_regulation_name(name: str) -> str:
    """Normalize EU Regulation names: standardize regulation citations."""
    n = name
    # Standardize "Regulation" capitalization
    n = re.sub(r'\sregulation\s', ' Regulation ', n, flags=re.IGNORECASE)
    # Standardize number format: (EU) or (EC)
    n = re.sub(r'\(eu\)', '(EU)', n, flags=re.IGNORECASE)
    n = re.sub(r'\(ec\)', '(EC)', n, flags=re.IGNORECASE)
    # Multiple spaces
    n = re.sub(r"\s+", " ", n).strip()
    return n


def _normalize_treaty_name(name: str) -> str:
    """Normalize Treaty names: standardize treaty/convention citations."""
    n = name
    # Standardize common terms
    n = re.sub(r'\sconvencao\s', ' Convencao ', n, flags=re.IGNORECASE)
    n = re.sub(r'\sconvention\s', ' Convention ', n, flags=re.IGNORECASE)
    n = re.sub(r'\spacto\s', ' Pacto ', n, flags=re.IGNORECASE)
    n = re.sub(r'\spact\s', ' Pact ', n, flags=re.IGNORECASE)
    n = re.sub(r'\streaty\s', ' Treaty ', n, flags=re.IGNORECASE)
    # Remove extra quotes
    n = n.replace('"', '').replace("'", '')
    # Multiple spaces
    n = re.sub(r"\s+", " ", n).strip()
    return n


def _normalize_international_decision_name(name: str) -> str:
    """Normalize InternationalDecision names: standardize international court citations."""
    n = name
    # Standardize court abbreviations
    n = n.replace("Corte IDH", "Corte IDH")  # Inter-American Court
    n = n.replace("CIDH", "Corte IDH")
    n = re.sub(r'\sICJ\s', ' ICJ ', n)  # International Court of Justice
    n = re.sub(r'\sECHR\s', ' ECHR ', n)  # European Court of Human Rights
    # Standardize "Case" vs "Caso"
    n = re.sub(r'\scaso\s', ' Caso ', n, flags=re.IGNORECASE)
    n = re.sub(r'\scase\s', ' Case ', n, flags=re.IGNORECASE)
    # Remove extra quotes
    n = n.replace('"', '').replace("'", '')
    # Multiple spaces
    n = re.sub(r"\s+", " ", n).strip()
    return n


def _apply_normalization(
    session, label: str, fn: Callable[[str], str],
    *, page_size: int = 1000,
) -> int:
    """Read nodes of a label in pages, apply fn in Python, write back changed ones."""
    changed = 0
    skip = 0
    while True:
        rows = list(session.run(
            f"MATCH (n:{label}) WHERE n.name IS NOT NULL "
            "RETURN elementId(n) AS eid, n.name AS name "
            "SKIP $skip LIMIT $limit",
            skip=skip, limit=page_size,
        ))
        if not rows:
            break
        for row in rows:
            old_name = row["name"]
            new_name = fn(old_name)
            if new_name != old_name:
                session.run(
                    f"MATCH (n:{label}) WHERE elementId(n) = $eid SET n.name = $new",
                    eid=row["eid"], new=new_name,
                )
                changed += 1
        skip += page_size
    return changed


def _has_apoc_merge(session) -> bool:
    try:
        r = session.run(
            "CALL dbms.procedures() YIELD name "
            "WHERE name = 'apoc.refactor.mergeNodes' "
            "RETURN count(*) AS c"
        ).single()
        return bool(r and int(r["c"] or 0) > 0)
    except Exception:
        return False


def _infer_subdispositivo_de(session) -> int:
    """
    Create deterministic structural edges between Artigo subdevices and their parent Artigo.

    We infer parent IDs purely from the `entity_id` format (no JSON metadata parsing):
    - Inciso nodes: `..._i...` -> parent = split(entity_id, "_i")[0]
    - Paragrafo nodes: `..._p...` (without inciso) -> parent = split(entity_id, "_p")[0]

    Only links when both child and parent nodes exist.
    """
    total = 0

    # Inciso -> (paragraph or base article)
    r = session.run(
        "MATCH (child:Artigo) "
        "WHERE child.entity_id CONTAINS '_i' "
        "WITH child, split(child.entity_id, '_i')[0] AS parent_id "
        "MATCH (parent:Artigo {entity_id: parent_id}) "
        "MERGE (child)-[rel:SUBDISPOSITIVO_DE]->(parent) "
        "ON CREATE SET rel.created_at = datetime() "
        "SET rel.updated_at = datetime(), "
        "    rel.source = 'derived_rule', "
        "    rel.rule = 'subdispositivo_de', "
        "    rel.layer = 'derived', "
        "    rel.verified = true, "
        "    rel.confidence = 1.0 "
        "RETURN count(rel) AS c"
    ).single()
    total += int(r["c"] or 0) if r else 0

    # Paragrafo -> base article (avoid also linking inciso->base directly)
    r = session.run(
        "MATCH (child:Artigo) "
        "WHERE child.entity_id CONTAINS '_p' AND NOT child.entity_id CONTAINS '_i' "
        "WITH child, split(child.entity_id, '_p')[0] AS parent_id "
        "MATCH (parent:Artigo {entity_id: parent_id}) "
        "MERGE (child)-[rel:SUBDISPOSITIVO_DE]->(parent) "
        "ON CREATE SET rel.created_at = datetime() "
        "SET rel.updated_at = datetime(), "
        "    rel.source = 'derived_rule', "
        "    rel.rule = 'subdispositivo_de', "
        "    rel.layer = 'derived', "
        "    rel.verified = true, "
        "    rel.confidence = 1.0 "
        "RETURN count(rel) AS c"
    ).single()
    total += int(r["c"] or 0) if r else 0

    return total


def _validate_normative_chains(session) -> Dict[str, int]:
    """
    Validate and fix normative chain integrity:
    1. Artigos without PERTENCE_A to any Lei/fonte normativa (orphan artigos)
    2. Subdispositivos (§/inciso/alínea) without SUBDISPOSITIVO_DE (orphan subdispositivos)

    Tries to infer missing links from entity name patterns before giving up.
    """
    result: Dict[str, int] = {
        "orphan_artigos_fixed": 0,
        "orphan_subdispositivos_fixed": 0,
        "orphan_artigos_remaining": 0,
        "orphan_subdispositivos_remaining": 0,
    }

    # --- 1. Fix orphan Artigos (no PERTENCE_A to any Lei) ---
    # Try to infer Lei from the Artigo name pattern: "Art. X do/da SIGLA"
    _re_lei_from_name = re.compile(
        r"(?:do|da|dos|das)\s+([A-Z][A-Za-z0-9./\s]+?)(?:\s*$)",
    )

    orphan_artigos = list(session.run(
        "MATCH (a:Artigo) "
        "WHERE a.name IS NOT NULL "
        "  AND NOT (a)-[:PERTENCE_A]->(:Lei) "
        "  AND NOT (a)-[:SUBDISPOSITIVO_DE]->() "
        "RETURN elementId(a) AS eid, a.name AS name "
        "LIMIT 2000"
    ))

    for row in orphan_artigos:
        name = row["name"] or ""
        m = _re_lei_from_name.search(name)
        if not m:
            continue
        lei_name = m.group(1).strip()
        # Try to find existing Lei node
        lei_match = session.run(
            "MATCH (l:Lei) WHERE l.name = $name RETURN elementId(l) AS eid LIMIT 1",
            name=lei_name,
        ).single()
        if lei_match:
            session.run(
                "MATCH (a:Artigo) WHERE elementId(a) = $aeid "
                "MATCH (l:Lei) WHERE elementId(l) = $leid "
                "MERGE (a)-[r:PERTENCE_A]->(l) "
                "ON CREATE SET r.source = 'normative_chain_validation', "
                "  r.created_at = datetime(), r.confidence = 0.9",
                aeid=row["eid"], leid=lei_match["eid"],
            )
            result["orphan_artigos_fixed"] += 1

    # Count remaining orphans
    remaining = session.run(
        "MATCH (a:Artigo) "
        "WHERE a.name IS NOT NULL "
        "  AND NOT (a)-[:PERTENCE_A]->(:Lei) "
        "  AND NOT (a)-[:SUBDISPOSITIVO_DE]->() "
        "RETURN count(a) AS c"
    ).single()
    result["orphan_artigos_remaining"] = int(remaining["c"] or 0) if remaining else 0

    # --- 2. Fix orphan subdispositivos (§/inciso without SUBDISPOSITIVO_DE) ---
    # Look for Artigo nodes whose names contain "par." or "inc." but have no
    # SUBDISPOSITIVO_DE edge. Try to find their parent Artigo by stripping the
    # subdispositivo part from the name.
    _re_subdispositivo = re.compile(
        r"^(Art\.\s*\d+[A-Za-z]?(?:-[A-Za-z])?)[\s,]+(?:par\.|inc\.|al\.)",
    )

    orphan_subdisp = list(session.run(
        "MATCH (s:Artigo) "
        "WHERE s.name IS NOT NULL "
        "  AND (s.name CONTAINS 'par.' OR s.name CONTAINS 'inc.' OR s.name CONTAINS 'al.') "
        "  AND NOT (s)-[:SUBDISPOSITIVO_DE]->(:Artigo) "
        "RETURN elementId(s) AS eid, s.name AS name "
        "LIMIT 2000"
    ))

    for row in orphan_subdisp:
        name = row["name"] or ""
        m = _re_subdispositivo.match(name)
        if not m:
            continue
        # Extract the base article part (e.g., "Art. 150" from "Art. 150 par.1o do CTN")
        base_art = m.group(1).strip()
        # Find the lei suffix if present
        lei_suffix_match = _re_lei_from_name.search(name)
        if lei_suffix_match:
            parent_name = f"{base_art} {lei_suffix_match.group(0).strip()}"
        else:
            parent_name = base_art

        parent_match = session.run(
            "MATCH (p:Artigo) WHERE p.name = $name "
            "  AND NOT (p.name CONTAINS 'par.' OR p.name CONTAINS 'inc.' OR p.name CONTAINS 'al.') "
            "RETURN elementId(p) AS eid LIMIT 1",
            name=parent_name,
        ).single()
        if parent_match:
            session.run(
                "MATCH (s:Artigo) WHERE elementId(s) = $seid "
                "MATCH (p:Artigo) WHERE elementId(p) = $peid "
                "MERGE (s)-[r:SUBDISPOSITIVO_DE]->(p) "
                "ON CREATE SET r.source = 'normative_chain_validation', "
                "  r.created_at = datetime(), r.confidence = 0.9",
                seid=row["eid"], peid=parent_match["eid"],
            )
            result["orphan_subdispositivos_fixed"] += 1

    # Count remaining orphan subdispositivos
    remaining_sub = session.run(
        "MATCH (s:Artigo) "
        "WHERE s.name IS NOT NULL "
        "  AND (s.name CONTAINS 'par.' OR s.name CONTAINS 'inc.' OR s.name CONTAINS 'al.') "
        "  AND NOT (s)-[:SUBDISPOSITIVO_DE]->(:Artigo) "
        "RETURN count(s) AS c"
    ).single()
    result["orphan_subdispositivos_remaining"] = int(remaining_sub["c"] or 0) if remaining_sub else 0

    return result


def post_process_legal_graph(driver, *, database: str) -> LegalPostProcessStats:
    """
    Run a few fast post-processing passes.

    Notes:
    - Requires a Neo4j driver (sync).
    - Uses APOC mergeNodes when available; otherwise does a minimal merge that
      preserves relationships by reattaching (may create duplicate rels).
    """
    stats = LegalPostProcessStats()

    with driver.session(database=database) as session:
        has_apoc = _has_apoc_merge(session)
        if not has_apoc:
            stats.warnings.append("apoc.refactor.mergeNodes not available; using fallback merge")

        # 0a) Python-side aggressive normalization (accents, gender, paragraph/inciso).
        # Replaces old Cypher-based step with comprehensive Python functions.
        for label, fn, stat_name in [
            ("Artigo", _normalize_artigo_name, "artigo_names_normalized"),
            ("Decisao", _normalize_decisao_name, "decisao_python_normalized"),
            ("Sumula", _normalize_sumula_name, "sumula_python_normalized"),
            ("Lei", _normalize_lei_name, "lei_python_normalized"),
            ("Tese", _normalize_tese_name, "tese_python_normalized"),
            ("Doutrina", _normalize_doutrina_name, "doutrina_python_normalized"),
            ("CaseLaw", _normalize_caselaw_name, "caselaw_python_normalized"),
            ("Statute", _normalize_statute_name, "statute_python_normalized"),
            ("Directive", _normalize_directive_name, "directive_python_normalized"),
            ("Regulation", _normalize_regulation_name, "regulation_python_normalized"),
            ("Treaty", _normalize_treaty_name, "treaty_python_normalized"),
            ("InternationalDecision", _normalize_international_decision_name, "international_decision_python_normalized"),
        ]:
            try:
                setattr(stats, stat_name, _apply_normalization(session, label, fn))
            except Exception as e:
                stats.warnings.append(f"{label.lower()}_normalization_failed:{e}")

        # 1) Fix nodes labeled as Decisao but clearly are Tema
        try:
            res = session.run(
                "MATCH (d:Decisao) "
                "WHERE d.name STARTS WITH 'Tema ' OR d.name STARTS WITH 'Tema' "
                "WITH d LIMIT 500 "
                "REMOVE d:Decisao "
                "SET d:Tema "
                "RETURN count(*) AS c"
            ).single()
            stats.tema_from_decisao = int(res["c"] or 0) if res else 0
        except Exception as e:
            stats.warnings.append(f"tema_from_decisao_failed:{e}")

        # 2) Normalize a small set of noisy decision name patterns
        try:
            res = session.run(
                "MATCH (d:Decisao) "
                "WHERE d.name CONTAINS 'nº ' "
                "SET d.name = replace(d.name, 'nº ', '') "
                "RETURN count(*) AS c"
            ).single()
            stats.decisao_name_normalized += int(res["c"] or 0) if res else 0
        except Exception as e:
            stats.warnings.append(f"decisao_name_normalized_failed:{e}")

        # 2b) Normalize 'nº ' on core legal nodes as well (cheap, safe).
        try:
            session.run(
                "MATCH (n) WHERE (n:Artigo OR n:Sumula OR n:Tema OR n:Lei) AND n.name CONTAINS 'nº ' "
                "SET n.name = replace(n.name, 'nº ', '')"
            )
        except Exception as e:
            stats.warnings.append(f"name_normalized_core_failed:{e}")

        # 2c) Remove obvious self-loops (noise).
        try:
            res = session.run(
                "MATCH (a)-[r:REMETE_A|CITA|INTERPRETA|APLICA|FUNDAMENTA|CONFIRMA|SUPERA|DISTINGUE|COMPLEMENTA|CITA_DOUTRINA|ANALISA]->(a) "
                "DELETE r RETURN count(r) AS c"
            ).single()
            stats.self_loops_removidos = int(res["c"] or 0) if res else 0
        except Exception as e:
            stats.warnings.append(f"self_loops_failed:{e}")

        # 2d) Remove invalid Tema nodes (Tema without any number).
        try:
            res = session.run(
                "MATCH (t:Tema) "
                "WHERE (t.numero IS NULL OR trim(toString(t.numero)) = '') "
                "  AND (t.name IS NULL OR NOT t.name =~ '.*\\\\d+.*') "
                "DETACH DELETE t "
                "RETURN count(*) AS c"
            ).single()
            stats.temas_invalidos_removidos = int(res["c"] or 0) if res else 0
        except Exception as e:
            stats.warnings.append(f"temas_invalidos_failed:{e}")

        # 2e) Relabel "Decisao" nodes that are clearly tribunals/hubs (avoid Tribunal hub noise).
        # v2 parity: expanded patterns beyond conservative exact-match.
        try:
            res = session.run(
                "MATCH (d:Decisao) "
                "WHERE d.name IS NOT NULL AND ("
                "  d.name =~ '(?i)^(STJ|STF|TST|TRF.*|TJ.*|TRT.*|Tribunal.*|Corte Especial.*)$' "
                "  OR d.name =~ '(?i)^(Jurisprud.ncia.*|Informativo.*|Precedente.*|Decis.o d[eo].*|Julgamento d[eo].*|Posicionamento.*)' "
                "  OR d.name =~ '(?i)^(Caso .*|An.lise pel[oa].*|D.vida sobre.*|Honor.rios.*|Prazo Prescricional.*)' "
                "  OR d.name =~ '(?i)^(STJ \\\\(.*|STJ -.*|Enunciado.*|Resolu..o.*|Provimento.*|RG d[eo].*)' "
                "  OR d.name =~ '(?i)^(Repercuss.o Geral(?! \\\\d).*)' "
                "  OR d.name =~ '^\\\\d+\\\\.\\\\d+\\\\.\\\\d+$' "
                "  OR d.name =~ '(?i)^ADIs? [^\\\\d]' "
                "  OR d.name =~ '(?i)^ADI$' "
                ") "
                "REMOVE d:Decisao SET d:Tribunal "
                "RETURN count(*) AS c"
            ).single()
            stats.decisao_relabel_to_tribunal = int(res["c"] or 0) if res else 0
        except Exception as e:
            stats.warnings.append(f"decisao_relabel_failed:{e}")

        # 2f) Merge duplicate Artigo/Sumula by name (APOC required).
        if has_apoc:
            try:
                r = session.run(
                    "MATCH (a:Artigo) "
                    "WITH a.name AS name, collect(a) AS nodes "
                    "WHERE name IS NOT NULL AND size(nodes) > 1 "
                    "CALL apoc.refactor.mergeNodes(nodes, {properties:'combine', mergeRels:true}) "
                    "YIELD node "
                    "RETURN count(DISTINCT name) AS c"
                ).single()
                stats.artigo_duplicates_merged = int(r["c"] or 0) if r else 0
            except Exception as e:
                stats.warnings.append(f"artigo_merge_failed:{e}")

            try:
                r = session.run(
                    "MATCH (s:Sumula) "
                    "WITH s.name AS name, collect(s) AS nodes "
                    "WHERE name IS NOT NULL AND size(nodes) > 1 "
                    "CALL apoc.refactor.mergeNodes(nodes, {properties:'combine', mergeRels:true}) "
                    "YIELD node "
                    "RETURN count(DISTINCT name) AS c"
                ).single()
                stats.sumula_duplicates_merged = int(r["c"] or 0) if r else 0
            except Exception as e:
                stats.warnings.append(f"sumula_merge_failed:{e}")

            try:
                r = session.run(
                    "MATCH (d:Doutrina) "
                    "WITH d.name AS name, collect(d) AS nodes "
                    "WHERE name IS NOT NULL AND size(nodes) > 1 "
                    "CALL apoc.refactor.mergeNodes(nodes, {properties:'combine', mergeRels:true}) "
                    "YIELD node "
                    "RETURN count(DISTINCT name) AS c"
                ).single()
                stats.doutrina_duplicates_merged = int(r["c"] or 0) if r else 0
            except Exception as e:
                stats.warnings.append(f"doutrina_merge_failed:{e}")

            # Merge international entities
            for label, stat_name in [
                ("CaseLaw", "caselaw_duplicates_merged"),
                ("Statute", "statute_duplicates_merged"),
                ("Directive", "directive_duplicates_merged"),
                ("Regulation", "regulation_duplicates_merged"),
                ("Treaty", "treaty_duplicates_merged"),
                ("InternationalDecision", "international_decision_duplicates_merged"),
            ]:
                try:
                    r = session.run(
                        f"MATCH (n:{label}) "
                        "WITH n.name AS name, collect(n) AS nodes "
                        "WHERE name IS NOT NULL AND size(nodes) > 1 "
                        "CALL apoc.refactor.mergeNodes(nodes, {properties:'combine', mergeRels:true}) "
                        "YIELD node "
                        "RETURN count(DISTINCT name) AS c"
                    ).single()
                    setattr(stats, stat_name, int(r["c"] or 0) if r else 0)
                except Exception as e:
                    stats.warnings.append(f"{label.lower()}_merge_failed:{e}")
        else:
            stats.warnings.append("entity_merge_skipped_without_apoc")

        # 3) Merge duplicate Decisao by name while preserving relationships
        try:
            if has_apoc:
                # Merge duplicates in groups to avoid huge transactions.
                result = session.run(
                    "MATCH (d:Decisao) "
                    "WITH d.name AS name, collect(d) AS nodes "
                    "WHERE name IS NOT NULL AND size(nodes) > 1 "
                    "CALL apoc.refactor.mergeNodes(nodes, {properties:'combine', mergeRels:true}) "
                    "YIELD node "
                    "RETURN count(node) AS merged_groups"
                ).single()
                stats.decisao_duplicates_merged = int(result["merged_groups"] or 0) if result else 0
            else:
                stats.warnings.append("decisao_merge_skipped_without_apoc")
        except Exception as e:
            stats.warnings.append(f"decisao_merge_failed:{e}")

        # 3b) Remove compound Decisao nodes (v2 step 10: "ADIs 4296, 4357 e 4425").
        try:
            res = session.run(
                "MATCH (d:Decisao) "
                "WHERE d.name CONTAINS ' e ' AND d.name =~ '.*\\\\d+.*,.*\\\\d+.*' "
                "DETACH DELETE d RETURN count(d) AS c"
            ).single()
            stats.compound_decisao_removed = int(res["c"] or 0) if res else 0
        except Exception as e:
            stats.warnings.append(f"compound_decisao_failed:{e}")

        # 3c) Migrate APLICA -> APLICA_SUMULA for Decisao->Sumula relationships.
        try:
            res = session.run(
                "MATCH (d:Decisao)-[r:APLICA]->(s:Sumula) "
                "CREATE (d)-[:APLICA_SUMULA {source: 'migrated_from_aplica'}]->(s) "
                "DELETE r "
                "RETURN count(r) AS c"
            ).single()
            stats.aplica_to_aplica_sumula_migrated = int(res["c"] or 0) if res else 0
        except Exception as e:
            stats.warnings.append(f"aplica_sumula_migration_failed:{e}")

        # 3d) Deduplicate parallel relationships created by node merges.
        try:
            total_deduped = 0
            rel_types_rows = list(session.run(
                "MATCH ()-[r]->() "
                "RETURN DISTINCT type(r) AS t"
            ))
            for row in rel_types_rows:
                rt = row["t"]
                if rt in _INFRA_REL_TYPES:
                    continue
                r = session.run(
                    f"MATCH (a)-[r:`{rt}`]->(b) "
                    "WITH a, b, collect(r) AS rels "
                    "WHERE size(rels) > 1 "
                    "WITH rels "
                    "UNWIND rels[1..] AS dup "
                    "DELETE dup "
                    "RETURN count(*) AS deleted"
                ).single()
                total_deduped += int(r["deleted"] or 0) if r else 0
            stats.relationships_deduped = total_deduped
        except Exception as e:
            stats.warnings.append(f"relationship_dedup_failed:{e}")

        # 3d.1) Temporal enrichment (best-effort): extract explicit dates from relationship evidence.
        if _env_bool("KG_BUILDER_ENRICH_TEMPORAL_RELATIONS", True):
            try:
                stats.temporal_relationships_enriched = _enrich_temporal_relationships(session)
            except Exception as e:
                stats.warnings.append(f"temporal_rel_enrich_failed:{e}")

        # 3e) Remove garbage Artigo nodes with very short names (< 5 chars).
        try:
            r = session.run(
                "MATCH (a:Artigo) WHERE a.name IS NOT NULL AND size(a.name) < 5 "
                "DETACH DELETE a RETURN count(a) AS c"
            ).single()
            stats.garbage_artigo_removed = int(r["c"] or 0) if r else 0
        except Exception as e:
            stats.warnings.append(f"garbage_cleanup_failed:{e}")

        # 3f) Deterministic structural inference:
        # Create SUBDISPOSITIVO_DE edges (paragrafo/inciso -> artigo-pai).
        # Safe: depends only on parsed entity_id format; no LLM.
        if _env_bool("KG_BUILDER_INFER_SUBDISPOSITIVO_DE", True):
            try:
                stats.subdispositivo_de_inferred = _infer_subdispositivo_de(session)
            except Exception as e:
                stats.warnings.append(f"subdispositivo_infer_failed:{e}")

        # 3g) Normative chain validation: fix orphan artigos and subdispositivos.
        # Tries to infer missing PERTENCE_A and SUBDISPOSITIVO_DE from entity names.
        if _env_bool("KG_BUILDER_VALIDATE_NORMATIVE_CHAINS", False):
            try:
                chain_stats = _validate_normative_chains(session)
                stats.orphan_artigos_fixed = chain_stats["orphan_artigos_fixed"]
                stats.orphan_subdispositivos_fixed = chain_stats["orphan_subdispositivos_fixed"]
                stats.orphan_artigos_remaining = chain_stats["orphan_artigos_remaining"]
                stats.orphan_subdispositivos_remaining = chain_stats["orphan_subdispositivos_remaining"]
                logger.info(
                    "Normative chain validation: artigos_fixed=%d subdisp_fixed=%d "
                    "artigos_remaining=%d subdisp_remaining=%d",
                    chain_stats["orphan_artigos_fixed"],
                    chain_stats["orphan_subdispositivos_fixed"],
                    chain_stats["orphan_artigos_remaining"],
                    chain_stats["orphan_subdispositivos_remaining"],
                )
            except Exception as e:
                stats.warnings.append(f"normative_chain_validation_failed:{e}")
                logger.warning(f"Normative chain validation failed: {e}")

        # 4) Enforce conservative caps per Decisao to avoid "hubby" noise (prompt-level rule).
        # Keep earliest relationships (by internal id) and delete the rest.
        try:
            r = session.run(
                "MATCH (d:Decisao)-[r:INTERPRETA]->() "
                "WITH d, r ORDER BY id(r) ASC "
                "WITH d, collect(r) AS rels "
                "WHERE size(rels) > 3 "
                "WITH rels[3..] AS extra "
                "FOREACH (r IN extra | DELETE r) "
                "RETURN size(extra) AS trimmed"
            ).single()
            stats.decisao_interpreta_trimmed = int(r["trimmed"] or 0) if r else 0
        except Exception as e:
            stats.warnings.append(f"decisao_interpreta_trim_failed:{e}")

        try:
            r = session.run(
                "MATCH (d:Decisao)-[r:FIXA_TESE]->() "
                "WITH d, r ORDER BY id(r) ASC "
                "WITH d, collect(r) AS rels "
                "WHERE size(rels) > 1 "
                "WITH rels[1..] AS extra "
                "FOREACH (r IN extra | DELETE r) "
                "RETURN size(extra) AS trimmed"
            ).single()
            stats.decisao_fixa_tese_trimmed = int(r["trimmed"] or 0) if r else 0
        except Exception as e:
            stats.warnings.append(f"decisao_fixa_tese_trim_failed:{e}")

        try:
            r = session.run(
                "MATCH (d:Decisao)-[r:JULGA_TEMA]->() "
                "WITH d, r ORDER BY id(r) ASC "
                "WITH d, collect(r) AS rels "
                "WHERE size(rels) > 1 "
                "WITH rels[1..] AS extra "
                "FOREACH (r IN extra | DELETE r) "
                "RETURN size(extra) AS trimmed"
            ).single()
            stats.decisao_julga_tema_trimmed = int(r["trimmed"] or 0) if r else 0
        except Exception as e:
            stats.warnings.append(f"decisao_julga_tema_trim_failed:{e}")

        # ============================================================
        # LINK INFERENCE (Phases 1, 2, 3)
        # ============================================================

        # Phase 1: Structural inference (deterministic rules)
        if _env_bool("KG_BUILDER_INFER_LINKS_STRUCTURAL", False):
            try:
                from .link_inference import run_structural_inference

                inference_stats = run_structural_inference(
                    session,
                    enable_transitive=True,
                    enable_co_citation=True,
                    enable_inheritance=True,
                    enable_symmetric=True,
                    enable_clustering=True
                )

                stats.transitive_remete_a_inferred = inference_stats.transitive_remete_a
                stats.transitive_cita_inferred = inference_stats.transitive_cita
                stats.co_citation_links_inferred = inference_stats.co_citation_cita
                stats.parent_inheritance_links_inferred = inference_stats.parent_inheritance_remete_a
                stats.symmetric_cita_inferred = inference_stats.symmetric_cita
                stats.jurisprudence_cluster_links_inferred = inference_stats.jurisprudence_cluster

                logger.info(f"Phase 1 (structural): {inference_stats.total_inferred} links inferred")

            except Exception as e:
                stats.warnings.append(f"structural_link_inference_failed:{e}")
                logger.warning(f"Structural link inference failed: {e}")

        # Phase 2: Embedding similarity
        l2_candidates_for_l3 = []
        if _env_bool("KG_BUILDER_INFER_LINKS_EMBEDDING", False):
            try:
                from .link_predictor import run_embedding_based_inference

                # Determinar se usa thresholds adaptativos ou fixos
                use_adaptive = _env_bool("KG_BUILDER_USE_ADAPTIVE_THRESHOLDS", True)
                use_budget_alloc = _env_bool("KG_BUILDER_USE_BUDGET_ALLOCATION", True)
                pass_to_l3 = _env_bool("KG_BUILDER_PASS_L2_TO_L3", True)

                # Se adaptive, thresholds fixos são ignorados (usa percentil)
                decisao_threshold = None if use_adaptive else float(os.getenv("KG_BUILDER_EMBEDDING_THRESHOLD_DECISAO", "0.85"))
                sumula_threshold = None if use_adaptive else float(os.getenv("KG_BUILDER_EMBEDDING_THRESHOLD_SUMULA", "0.88"))
                doutrina_threshold = None if use_adaptive else float(os.getenv("KG_BUILDER_EMBEDDING_THRESHOLD_DOUTRINA", "0.82"))

                embedding_stats = run_embedding_based_inference(
                    session,
                    enable_decisao=True,
                    enable_sumula=True,
                    enable_doutrina=True,
                    enable_artigo=_env_bool("KG_BUILDER_INFER_LINKS_ARTIGO", True),
                    enable_cross_type=_env_bool("KG_BUILDER_INFER_LINKS_CROSS_TYPE", True),
                    decisao_threshold=decisao_threshold,
                    sumula_threshold=sumula_threshold,
                    doutrina_threshold=doutrina_threshold,
                    use_adaptive_threshold=use_adaptive,
                    use_budget_allocation=use_budget_alloc,
                    total_budget=int(os.getenv("KG_BUILDER_EMBEDDING_TOTAL_BUDGET", "10000")),
                    pass_to_l3=pass_to_l3,
                )

                stats.embedding_decisao_links_inferred = embedding_stats.decisao_cita_by_similarity
                stats.embedding_sumula_links_inferred = embedding_stats.sumula_cita_by_similarity
                stats.embedding_doutrina_links_inferred = embedding_stats.doutrina_cita_by_similarity
                stats.embedding_artigo_links_inferred = embedding_stats.artigo_by_similarity
                stats.embedding_cross_type_links_inferred = embedding_stats.cross_type_by_similarity
                l2_candidates_for_l3 = embedding_stats.candidates_for_l3 or []

                logger.info(f"Phase 2 (embedding): {embedding_stats.total_inferred} candidates created")

            except Exception as e:
                stats.warnings.append(f"embedding_link_inference_failed:{e}")
                logger.warning(f"Embedding-based link inference failed: {e}")

        # Phase 3: LLM validation (most expensive, use sparingly)
        if _env_bool("KG_BUILDER_INFER_LINKS_LLM", False):
            try:
                from .llm_link_suggester import run_llm_based_inference

                llm_stats = run_llm_based_inference(
                    session,
                    model_provider=os.getenv("KG_BUILDER_LLM_PROVIDER", "openai"),
                    model=os.getenv("KG_BUILDER_LLM_MODEL", "gpt-4o-mini"),
                    enable_decisao=True,
                    enable_doutrina=True,
                    max_decisao_pairs=int(os.getenv("KG_BUILDER_LLM_MAX_DECISAO_PAIRS", "50")),
                    max_doutrina_pairs=int(os.getenv("KG_BUILDER_LLM_MAX_DOUTRINA_PAIRS", "30")),
                    min_confidence=float(os.getenv("KG_BUILDER_LLM_MIN_CONFIDENCE", "0.75")),
                    l2_candidates=l2_candidates_for_l3 if l2_candidates_for_l3 else None,
                )

                stats.llm_links_suggested = llm_stats.links_suggested
                stats.llm_links_created = llm_stats.links_created
                stats.llm_api_calls = llm_stats.llm_api_calls
                stats.llm_evidence_validated = llm_stats.evidence_validated
                stats.llm_evidence_failed = llm_stats.evidence_failed
                stats.llm_l2_candidates_validated = llm_stats.l2_candidates_validated
                stats.llm_l2_candidates_rejected = llm_stats.l2_candidates_rejected

                logger.info(
                    f"Phase 3 (LLM): {llm_stats.links_suggested} suggested, "
                    f"{llm_stats.links_created} created, {llm_stats.llm_api_calls} API calls"
                )

            except Exception as e:
                stats.warnings.append(f"llm_link_inference_failed:{e}")
                logger.warning(f"LLM-based link inference failed: {e}")

        # Phase 3b: Exploratory enrichment (isolated nodes)
        if _env_bool("KG_BUILDER_INFER_LINKS_EXPLORATORY", False):
            try:
                from .llm_explorer import run_exploratory_enrichment

                exploratory_stats = run_exploratory_enrichment(
                    session,
                    node_types=None,  # All explorable types
                    max_degree=int(os.getenv("KG_BUILDER_EXPLORATORY_MAX_DEGREE", "1")),
                    max_nodes=int(os.getenv("KG_BUILDER_EXPLORATORY_MAX_NODES", "50")),
                    model_provider=os.getenv("KG_BUILDER_LLM_PROVIDER", "openai"),
                    model=os.getenv("KG_BUILDER_LLM_MODEL", "gpt-4o-mini"),
                    min_confidence=float(os.getenv("KG_BUILDER_EXPLORATORY_MIN_CONFIDENCE", "0.80")),
                )

                stats.exploratory_isolated_found = exploratory_stats.isolated_nodes_found
                stats.exploratory_nodes_explored = exploratory_stats.nodes_explored
                stats.exploratory_links_created = exploratory_stats.suggestions_created
                stats.exploratory_api_calls = exploratory_stats.llm_api_calls

                logger.info(
                    f"Phase 3b (exploratory): {exploratory_stats.suggestions_created} "
                    f"candidates from {exploratory_stats.nodes_explored} isolated nodes"
                )

            except Exception as e:
                stats.warnings.append(f"exploratory_link_inference_failed:{e}")
                logger.warning(f"Exploratory link inference failed: {e}")

    # Calculate total inferred links
    total_structural = (
        stats.transitive_remete_a_inferred +
        stats.transitive_cita_inferred +
        stats.co_citation_links_inferred +
        stats.parent_inheritance_links_inferred +
        stats.symmetric_cita_inferred +
        stats.jurisprudence_cluster_links_inferred
    )
    total_embedding = (
        stats.embedding_decisao_links_inferred +
        stats.embedding_sumula_links_inferred +
        stats.embedding_doutrina_links_inferred +
        stats.embedding_artigo_links_inferred +
        stats.embedding_cross_type_links_inferred
    )
    total_inferred = (
        total_structural + total_embedding +
        stats.llm_links_created + stats.exploratory_links_created
    )

    logger.info(
        "Legal post-process complete: "
        "artigo_norm=%d decisao_norm=%d sumula_norm=%d "
        "lei_norm=%d tese_norm=%d tema_relabel=%d "
        "decisao_merged=%d artigo_merged=%d sumula_merged=%d "
        "compound_removed=%d aplica_migrated=%d "
        "deduped=%d garbage=%d subdisp=%d "
        "inferred_structural=%d inferred_embedding=%d inferred_llm=%d total_inferred=%d "
        "warnings=%d",
        stats.artigo_names_normalized,
        stats.decisao_python_normalized,
        stats.sumula_python_normalized,
        stats.lei_python_normalized,
        stats.tese_python_normalized,
        stats.tema_from_decisao,
        stats.decisao_duplicates_merged,
        stats.artigo_duplicates_merged,
        stats.sumula_duplicates_merged,
        stats.compound_decisao_removed,
        stats.aplica_to_aplica_sumula_migrated,
        stats.relationships_deduped,
        stats.garbage_artigo_removed,
        stats.subdispositivo_de_inferred,
        total_structural,
        total_embedding,
        stats.llm_links_created,
        total_inferred,
        len(stats.warnings or []),
    )
    return stats
