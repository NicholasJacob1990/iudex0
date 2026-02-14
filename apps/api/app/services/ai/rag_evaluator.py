"""
Legal domain RAG evaluation metrics.

Beyond standard RAGAS metrics, implements:
- Citation coverage: % of claims with source attribution
- Temporal validity: % of cited laws still in force
- Jurisdiction match: correct jurisdiction in answer
- Legal entity accuracy: correct extraction of articles, laws, sumulas

Brazilian legal system specific patterns and validations.
"""

from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass, field
import re
from datetime import datetime


@dataclass
class LegalEvalResult:
    """Result of legal-specific evaluation."""
    citation_coverage: float  # 0.0-1.0
    temporal_validity: float  # 0.0-1.0
    jurisdiction_match: bool
    entity_precision: float  # 0.0-1.0
    entity_recall: float  # 0.0-1.0
    details: Dict = field(default_factory=dict)


# =============================================================================
# Brazilian Legal Reference Patterns
# =============================================================================

# Patterns for laws (Lei, Decreto, MP, etc.)
LAW_PATTERNS = [
    # Lei ordinaria: Lei 8.666/93, Lei n. 14.133/2021, Lei nº 13.709
    r"Lei\s+(?:n[°º.]?\s*)?(\d{1,5})[/.-]?(\d{2,4})?",
    # Lei Complementar: LC 101/2000, Lei Complementar 123
    r"(?:LC|Lei\s+Complementar)\s+(?:n[°º.]?\s*)?(\d{1,5})[/.-]?(\d{2,4})?",
    # Decreto: Decreto 9.412/2018, Decreto-Lei 200/67
    r"Decreto(?:-Lei)?\s+(?:n[°º.]?\s*)?(\d{1,6})[/.-]?(\d{2,4})?",
    # Medida Provisoria: MP 927/2020, Medida Provisória 1.045
    r"(?:MP|Medida\s+Provis[oó]ria)\s+(?:n[°º.]?\s*)?(\d{1,5})[/.-]?(\d{2,4})?",
    # Resolucao: Resolução 4.658/2018
    r"Resolu[cç][aã]o\s+(?:n[°º.]?\s*)?(\d{1,5})[/.-]?(\d{2,4})?",
    # Portaria: Portaria 123/2020
    r"Portaria\s+(?:n[°º.]?\s*)?(\d{1,5})[/.-]?(\d{2,4})?",
    # Instrucao Normativa: IN 1234/2020
    r"(?:IN|Instru[çc][aã]o\s+Normativa)\s+(?:n[°º.]?\s*)?(\d{1,5})[/.-]?(\d{2,4})?",
    # Constituicao Federal
    r"(?:CF|Constitui[çc][aã]o\s+Federal)(?:\s+de\s+\d{4})?",
    # Codigo Civil, Penal, Processo Civil, etc.
    r"C[óo]digo\s+(?:Civil|Penal|de\s+Processo\s+Civil|de\s+Processo\s+Penal|Tribut[aá]rio|de\s+Defesa\s+do\s+Consumidor)",
    # CLT
    r"CLT|Consolida[çc][aã]o\s+das\s+Leis\s+do\s+Trabalho",
    # ECA
    r"ECA|Estatuto\s+da\s+Crian[çc]a\s+e\s+(?:do\s+)?Adolescente",
    # Estatuto do Idoso, Cidade, etc.
    r"Estatuto\s+(?:do\s+Idoso|da\s+Cidade|da\s+Advocacia)",
]

# Article patterns
ARTICLE_PATTERNS = [
    # Art. 5, Art. 5°, Art. 5º
    r"Art(?:igo)?[.]?\s*(\d{1,4})(?:[°º])?",
    # Art. 5, I, II
    r"Art(?:igo)?[.]?\s*(\d{1,4})(?:[°º])?,?\s*([IVXLCDM]+(?:\s*,\s*[IVXLCDM]+)*)",
    # Art. 5, § 1º, Art. 5, §§ 1º e 2º
    r"Art(?:igo)?[.]?\s*(\d{1,4})(?:[°º])?,?\s*[§§]+\s*(\d+[°º]?)",
    # Paragrafo unico
    r"(?:par[aá]grafo\s+[úu]nico|§\s*[úu]nico)",
    # Inciso I, II
    r"inciso[s]?\s+([IVXLCDM]+(?:\s*(?:,|e|a)\s*[IVXLCDM]+)*)",
    # Alinea a, b
    r"al[ií]nea[s]?\s+['\"]?([a-z])(?:['\"])?(?:\s*(?:,|e|a)\s*['\"]?([a-z])['\"]?)*",
]

# Sumula patterns
SUMULA_PATTERNS = [
    # Sumula 331 TST, Sumula nº 473 STF
    r"S[úu]mula\s+(?:n[°º.]?\s*)?(\d{1,4})(?:\s+(?:do\s+)?(?:STF|STJ|TST|TRF|TRT|TSE))?",
    # Sumula Vinculante 13
    r"S[úu]mula\s+Vinculante\s+(?:n[°º.]?\s*)?(\d{1,3})",
    # OJ 123 SDI-1
    r"(?:OJ|Orienta[çc][aã]o\s+Jurisprudencial)\s+(?:n[°º.]?\s*)?(\d{1,4})(?:\s+(?:SDI|SBDI)[-]?\d?)?",
]

# Decision/case patterns
DECISION_PATTERNS = [
    # RE 123456, REsp 1234567
    r"(?:RE|REsp|RR|RO|AI|AgR|ED|HC|MS|ADI|ADC|ADPF|RCL|ACO|Rcl)\s*[\-]?\s*(\d{4,8})",
    # Processo 0001234-12.2020.5.01.0001
    r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}",
    # Processo SEI 12345.123456/2020-12
    r"(?:SEI\s+)?(\d{5}\.\d{6}/\d{4}-\d{2})",
]

# Jurisdiction patterns
JURISDICTION_PATTERNS = {
    "federal": [
        r"(?:TRF|STF|STJ|TST|TSE|TNU|Justi[çc]a\s+Federal)",
        r"Lei\s+Federal",
        r"Constitui[çc][aã]o\s+Federal",
        r"Uni[aã]o",
    ],
    "estadual": [
        r"TJ[A-Z]{2}",  # TJSP, TJRJ, etc.
        r"Tribunal\s+de\s+Justi[çc]a\s+(?:do\s+)?(?:Estado\s+(?:de|do)\s+)?([A-Z]{2}|\w+)",
        r"Lei\s+Estadual",
        r"Estado\s+(?:de|do)\s+(?:S[aã]o\s+Paulo|Rio\s+de\s+Janeiro|Minas\s+Gerais|\w+)",
    ],
    "municipal": [
        r"Lei\s+Municipal",
        r"Prefeitura",
        r"Munic[ií]pio\s+(?:de|do)\s+\w+",
        r"C[aâ]mara\s+Municipal",
    ],
    "trabalhista": [
        r"TST|TRT",
        r"CLT",
        r"Justi[çc]a\s+do\s+Trabalho",
        r"Vara\s+do\s+Trabalho",
    ],
}

# Known revoked/superseded laws database
# Format: {"normalized_ref": {"status": "revoked"|"partially_revoked", "superseded_by": str, "year_revoked": int}}
REVOKED_LAWS_DB: Dict[str, Dict] = {
    "lei_8666_1993": {
        "status": "partially_revoked",
        "superseded_by": "Lei 14.133/2021",
        "year_revoked": 2021,
        "note": "Revogada pela nova Lei de Licitações, com período de transição até 2024",
    },
    "lei_10520_2002": {
        "status": "revoked",
        "superseded_by": "Lei 14.133/2021",
        "year_revoked": 2021,
        "note": "Pregão incorporado à nova Lei de Licitações",
    },
    "decreto_lei_200_1967": {
        "status": "partially_revoked",
        "superseded_by": None,
        "year_revoked": None,
        "note": "Parcialmente vigente, vários artigos revogados por leis posteriores",
    },
    "lei_8112_1990": {
        "status": "current",
        "note": "Estatuto dos Servidores Públicos Federais - vigente com alterações",
    },
    "mp_927_2020": {
        "status": "revoked",
        "superseded_by": None,
        "year_revoked": 2020,
        "note": "Perdeu eficácia por não ter sido convertida em lei",
    },
    "mp_936_2020": {
        "status": "converted",
        "superseded_by": "Lei 14.020/2020",
        "year_revoked": 2020,
        "note": "Convertida em lei",
    },
    "lei_4320_1964": {
        "status": "current",
        "note": "Lei de Direito Financeiro - vigente",
    },
    "lc_101_2000": {
        "status": "current",
        "note": "Lei de Responsabilidade Fiscal - vigente",
    },
}

# States abbreviation map
BRAZILIAN_STATES = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas",
    "BA": "Bahia", "CE": "Ceará", "DF": "Distrito Federal", "ES": "Espírito Santo",
    "GO": "Goiás", "MA": "Maranhão", "MT": "Mato Grosso", "MS": "Mato Grosso do Sul",
    "MG": "Minas Gerais", "PA": "Pará", "PB": "Paraíba", "PR": "Paraná",
    "PE": "Pernambuco", "PI": "Piauí", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte",
    "RS": "Rio Grande do Sul", "RO": "Rondônia", "RR": "Roraima", "SC": "Santa Catarina",
    "SP": "São Paulo", "SE": "Sergipe", "TO": "Tocantins",
}


# =============================================================================
# Legal Claim Extraction
# =============================================================================

def extract_legal_claims(text: str) -> List[str]:
    """
    Extract legal claims/assertions from text.

    Legal claims are statements about:
    - What the law says (normative statements)
    - Deadlines and procedural rules
    - Rights and obligations
    - Jurisprudential understanding

    Returns list of claim strings.
    """
    if not text:
        return []

    claims: List[str] = []

    # Split into sentences
    sentences = re.split(r'[.!?]\s+', text)

    # Patterns indicating legal claims
    claim_indicators = [
        # Normative indicators
        r"(?:deve|deverá|devem|deverão)\s+",
        r"(?:é|são)\s+(?:obrigatóri[oa]|vedad[oa]|permitid[oa]|facultad[oa])",
        r"(?:compete|cabe|incumbe|cumpre)\s+",
        r"(?:prescreve|dispõe|estabelece|determina|prevê)\s+",
        r"(?:nos\s+termos|conforme|segundo|de\s+acordo\s+com)\s+",
        r"(?:o\s+prazo|prazo\s+de)\s+\d+\s+(?:dias?|meses?|anos?)",
        # Rights and obligations
        r"(?:tem|têm|terá|terão)\s+direito\s+",
        r"(?:é|são)\s+(?:assegurad[oa]|garantid[oa]|resguardad[oa])",
        r"(?:fica|ficam)\s+(?:garantid[oa]|assegurad[oa]|autorizado)",
        # Jurisprudential
        r"(?:entende|entendeu|entendimento)\s+(?:o\s+)?(?:STF|STJ|TST|TRF|TJ)",
        r"(?:jurisprudência|súmula|orientação)\s+(?:pacífica|consolidada|dominante)",
        r"(?:conforme|segundo)\s+(?:posicionamento|entendimento)",
        # Legal references
        r"(?:Lei|Decreto|MP|LC|IN|Resolução|Portaria)\s+(?:n[°º.]?\s*)?\d+",
        r"Art(?:igo)?[.]?\s*\d+",
        r"S[úu]mula\s+(?:Vinculante\s+)?\d+",
    ]

    combined_pattern = "|".join(f"({p})" for p in claim_indicators)

    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence) < 20:  # Too short to be a meaningful claim
            continue

        # Check if sentence contains legal claim indicators
        if re.search(combined_pattern, sentence, re.IGNORECASE):
            claims.append(sentence)

    return claims


def count_cited_claims(text: str) -> Tuple[int, int]:
    """
    Count claims that have source citations.

    Returns (cited_count, total_claims_count).
    """
    claims = extract_legal_claims(text)
    if not claims:
        return (0, 0)

    # Patterns indicating citations
    citation_patterns = [
        # Law references
        r"(?:Lei|Decreto|LC|MP|IN|Resolução)\s+(?:n[°º.]?\s*)?\d+[/.-]?\d*",
        r"Art(?:igo)?[.]?\s*\d+",
        # Sumulas
        r"S[úu]mula\s+(?:Vinculante\s+)?(?:n[°º.]?\s*)?\d+",
        # Case references
        r"(?:RE|REsp|RR|ADI|HC|MS)\s*\d+",
        # Numeric footnote references
        r"\[\d+\]",
        r"\(\d+\)",
        # Named references
        r"\((?:op\.\s*cit\.|ibid\.|idem)\)",
        # Explicit source mentions
        r"(?:conforme|segundo|nos\s+termos\s+d[oa]|de\s+acordo\s+com)\s+",
    ]

    combined = "|".join(f"({p})" for p in citation_patterns)

    cited_count = 0
    for claim in claims:
        if re.search(combined, claim, re.IGNORECASE):
            cited_count += 1

    return (cited_count, len(claims))


def evaluate_citation_coverage(answer: str) -> float:
    """
    What percentage of legal claims in the answer have citations?

    Claims are statements about law (e.g., "o prazo é de 5 dias")
    Citations are references like "Art. 109", "Lei 8.666", "[1]"

    Returns score between 0.0 and 1.0.
    """
    cited, total = count_cited_claims(answer)
    if total == 0:
        return 1.0  # No claims = no citation needed
    return cited / total


# =============================================================================
# Law Reference Extraction and Temporal Validity
# =============================================================================

def extract_cited_laws(text: str) -> List[str]:
    """
    Extract all law references from text (Lei X, Decreto Y, etc.)

    Returns normalized list of law references.

    Handles Brazilian law numbering formats:
    - Lei 8.666/93 (with thousands separator dot)
    - Lei 14.133/2021
    - Lei nº 13.709/2018
    - LC 101/2000
    """
    if not text:
        return []

    laws: Set[str] = set()

    def _normalize_law_number(num_str: str) -> str:
        """Remove thousand separators from law number."""
        # Remove dots that are thousands separators (not year separators)
        return num_str.replace(".", "")

    # Patterns that capture the full number including dots, then year
    # Format: (regex_pattern, law_type_prefix)
    patterns = [
        # Lei ordinaria: Lei 8.666/93, Lei n. 14.133/2021, Lei nº 13.709
        (r"Lei\s+(?:n[°º.]?\s*)?(\d{1,3}(?:\.\d{3})*|\d{1,6})[/.-](\d{2,4})", "Lei"),
        (r"Lei\s+(?:n[°º.]?\s*)?(\d{1,3}(?:\.\d{3})*|\d{1,6})(?![/.\d])", "Lei"),
        # Lei Complementar: LC 101/2000, Lei Complementar 123/2006
        (r"(?:LC|Lei\s+Complementar)\s+(?:n[°º.]?\s*)?(\d{1,3}(?:\.\d{3})*|\d{1,6})[/.-](\d{2,4})", "LC"),
        (r"(?:LC|Lei\s+Complementar)\s+(?:n[°º.]?\s*)?(\d{1,3}(?:\.\d{3})*|\d{1,6})(?![/.\d])", "LC"),
        # Decreto: Decreto 9.412/2018, Decreto-Lei 200/67
        (r"Decreto\s+(?:n[°º.]?\s*)?(\d{1,3}(?:\.\d{3})*|\d{1,6})[/.-](\d{2,4})", "Decreto"),
        (r"Decreto\s+(?:n[°º.]?\s*)?(\d{1,3}(?:\.\d{3})*|\d{1,6})(?![/.\d])", "Decreto"),
        # Decreto-Lei: Decreto-Lei 200/67
        (r"Decreto-Lei\s+(?:n[°º.]?\s*)?(\d{1,3}(?:\.\d{3})*|\d{1,6})[/.-](\d{2,4})", "Decreto-Lei"),
        (r"Decreto-Lei\s+(?:n[°º.]?\s*)?(\d{1,3}(?:\.\d{3})*|\d{1,6})(?![/.\d])", "Decreto-Lei"),
        # Medida Provisoria: MP 927/2020, Medida Provisória 1.045/2021
        (r"(?:MP|Medida\s+Provis[oó]ria)\s+(?:n[°º.]?\s*)?(\d{1,3}(?:\.\d{3})*|\d{1,6})[/.-](\d{2,4})", "MP"),
        (r"(?:MP|Medida\s+Provis[oó]ria)\s+(?:n[°º.]?\s*)?(\d{1,3}(?:\.\d{3})*|\d{1,6})(?![/.\d])", "MP"),
        # Resolucao: Resolução 4.658/2018
        (r"Resolu[cç][aã]o\s+(?:n[°º.]?\s*)?(\d{1,3}(?:\.\d{3})*|\d{1,6})[/.-](\d{2,4})", "Resolucao"),
        (r"Resolu[cç][aã]o\s+(?:n[°º.]?\s*)?(\d{1,3}(?:\.\d{3})*|\d{1,6})(?![/.\d])", "Resolucao"),
        # Instrucao Normativa: IN 1234/2020
        (r"(?:IN|Instru[çc][aã]o\s+Normativa)\s+(?:n[°º.]?\s*)?(\d{1,3}(?:\.\d{3})*|\d{1,6})[/.-](\d{2,4})", "IN"),
        (r"(?:IN|Instru[çc][aã]o\s+Normativa)\s+(?:n[°º.]?\s*)?(\d{1,3}(?:\.\d{3})*|\d{1,6})(?![/.\d])", "IN"),
    ]

    for pattern, tipo in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            numero_raw = match.group(1)
            numero = _normalize_law_number(numero_raw)

            # Check if we captured a year (patterns with 2 groups)
            ano = ""
            if len(match.groups()) > 1 and match.group(2):
                ano = match.group(2)
                # Normalize 2-digit years
                if len(ano) == 2:
                    ano = f"19{ano}" if int(ano) > 50 else f"20{ano}"

            if ano:
                laws.add(f"{tipo} {numero}/{ano}")
            else:
                laws.add(f"{tipo} {numero}")

    # Special cases - codes (these don't have numbers)
    code_patterns = [
        (r"C[óo]digo\s+Civil(?!\s+de\s+Processo)", "Codigo Civil"),
        (r"C[óo]digo\s+Penal(?!\s+de\s+Processo)", "Codigo Penal"),
        (r"C[óo]digo\s+de\s+Processo\s+Civil|\bCPC\b", "CPC"),
        (r"C[óo]digo\s+de\s+Processo\s+Penal|\bCPP\b", "CPP"),
        (r"C[óo]digo\s+Tribut[aá]rio\s+Nacional|\bCTN\b", "CTN"),
        (r"C[óo]digo\s+de\s+Defesa\s+do\s+Consumidor|\bCDC\b", "CDC"),
        (r"\bCLT\b|Consolida[çc][aã]o\s+das\s+Leis\s+do\s+Trabalho", "CLT"),
        (r"\bCF(?:/88)?\b|Constitui[çc][aã]o\s+Federal", "CF/88"),
        (r"\bECA\b|Estatuto\s+da\s+Crian[çc]a", "ECA"),
    ]

    for pattern, normalized in code_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            laws.add(normalized)

    return sorted(laws)


def _normalize_law_ref(law_ref: str) -> str:
    """Normalize a law reference to a standard key format."""
    # Remove accents and normalize
    ref = law_ref.lower().strip()
    ref = re.sub(r'[áàâã]', 'a', ref)
    ref = re.sub(r'[éèê]', 'e', ref)
    ref = re.sub(r'[íìî]', 'i', ref)
    ref = re.sub(r'[óòôõ]', 'o', ref)
    ref = re.sub(r'[úùû]', 'u', ref)
    ref = re.sub(r'ç', 'c', ref)

    # Extract type and numbers
    match = re.match(r"(lei|lc|decreto|mp|in|resolucao)[\s\-]*(\d+)[/.-]?(\d+)?", ref)
    if match:
        tipo = match.group(1)
        numero = match.group(2)
        ano = match.group(3) or ""
        if ano:
            return f"{tipo}_{numero}_{ano}"
        return f"{tipo}_{numero}"

    return ref.replace(" ", "_").replace("/", "_").replace("-", "_")


def is_law_current(law_ref: str) -> Tuple[bool, Optional[Dict]]:
    """
    Check if a law is still in force.

    Returns (is_current, info_dict or None).

    Known revoked/superseded laws are checked against REVOKED_LAWS_DB.
    For unknown laws, returns (True, None) as we can't determine status.
    """
    normalized = _normalize_law_ref(law_ref)

    if normalized in REVOKED_LAWS_DB:
        info = REVOKED_LAWS_DB[normalized]
        status = info.get("status", "unknown")
        is_current = status in ("current", "partially_revoked", "converted")
        return (is_current, info)

    # Check year-based heuristics for known patterns
    match = re.search(r"(\d{4})$", normalized)
    if match:
        year = int(match.group(1))
        # Very old laws (pre-1988) might be outdated but we can't be sure
        if year < 1988:
            return (True, {"note": "Lei anterior a CF/88 - verificar vigência"})

    # Unknown law - assume current
    return (True, None)


def evaluate_temporal_validity(answer: str) -> Tuple[float, List[str]]:
    """
    What percentage of cited laws are still in force?

    Returns (score, list of outdated citations).
    """
    laws = extract_cited_laws(answer)
    if not laws:
        return (1.0, [])

    outdated: List[str] = []
    current_count = 0

    for law in laws:
        is_current, info = is_law_current(law)
        if is_current:
            current_count += 1
        else:
            note = ""
            if info:
                superseded = info.get("superseded_by")
                if superseded:
                    note = f" (substituída por {superseded})"
                elif info.get("note"):
                    note = f" ({info['note']})"
            outdated.append(f"{law}{note}")

    score = current_count / len(laws) if laws else 1.0
    return (score, outdated)


# =============================================================================
# Jurisdiction Matching
# =============================================================================

def _extract_jurisdiction_from_text(text: str) -> Set[str]:
    """Extract mentioned jurisdictions from text."""
    jurisdictions: Set[str] = set()

    for jurisdiction, patterns in JURISDICTION_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                jurisdictions.add(jurisdiction)
                break

    return jurisdictions


def _has_federal_indicators(text: str) -> bool:
    """Check if text contains federal law indicators."""
    federal_law_patterns = [
        # Federal laws by number (major federal laws)
        r"Lei\s+(?:n[°º.]?\s*)?(?:8\.?666|14\.?133|8\.?112|13\.?709|10\.?520|12\.?846)",
        r"(?:LC|Lei\s+Complementar)\s+(?:n[°º.]?\s*)?101",
        # Federal codes
        r"\b(?:CPC|CPP|CTN|CDC|CLT|ECA)\b",
        r"C[óo]digo\s+(?:Civil|Penal|de\s+Processo)",
        # Constitution
        r"(?:CF|Constitui[çc][aã]o\s+Federal)",
        # Federal decree
        r"Decreto\s+(?:Federal|n[°º.]?\s*\d)",
    ]
    for pattern in federal_law_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def evaluate_jurisdiction_match(
    query: str,
    answer: str,
    expected_jurisdiction: Optional[str] = None
) -> bool:
    """
    Does the answer cite laws from the correct jurisdiction?

    Brazilian jurisdictions: Federal, Estadual (SP, RJ, etc.), Municipal, Trabalhista

    If expected_jurisdiction is provided, checks if answer matches it.
    Otherwise, infers expected from query and checks consistency.
    """
    if expected_jurisdiction:
        expected = expected_jurisdiction.lower()
        answer_jurisdictions = _extract_jurisdiction_from_text(answer)

        # If expected is specific state, check for estadual or that state
        if expected in [s.lower() for s in BRAZILIAN_STATES.keys()]:
            return "estadual" in answer_jurisdictions or expected in answer.lower()

        # For federal jurisdiction, also check for federal law citations
        if expected == "federal":
            if "federal" in answer_jurisdictions:
                return True
            # Check if answer cites federal laws (Lei, Decreto, CF, etc.)
            return _has_federal_indicators(answer)

        return expected in answer_jurisdictions

    # Infer from query
    query_jurisdictions = _extract_jurisdiction_from_text(query)
    answer_jurisdictions = _extract_jurisdiction_from_text(answer)

    # If query mentions a jurisdiction, answer should include it
    if query_jurisdictions:
        # For federal queries, also accept federal law citations
        if "federal" in query_jurisdictions:
            if "federal" in answer_jurisdictions or _has_federal_indicators(answer):
                return True
        return bool(query_jurisdictions & answer_jurisdictions)

    # No jurisdiction specified in query - any is acceptable
    return True


# =============================================================================
# Legal Entity Extraction
# =============================================================================

def extract_legal_entities(text: str) -> Dict[str, List[str]]:
    """
    Extract legal entities by type:
    - laws: ["Lei 8.666/93", "Lei 14.133/21"]
    - articles: ["Art. 5", "Art. 109, I"]
    - sumulas: ["Súmula 331 TST", "Súmula Vinculante 13"]
    - decisions: ["RE 123456", "ADI 1234"]

    Returns dict with entity lists by type.
    """
    if not text:
        return {"laws": [], "articles": [], "sumulas": [], "decisions": []}

    entities: Dict[str, Set[str]] = {
        "laws": set(),
        "articles": set(),
        "sumulas": set(),
        "decisions": set(),
    }

    # Laws
    entities["laws"].update(extract_cited_laws(text))

    # Articles - improved pattern to capture various formats
    # Art. 5, Art. 5°, Art. 5, caput, Art. 5, I, Art. 5, § 1º
    # Important: process patterns in order of specificity (most specific first)
    article_patterns = [
        # Art. X, § Y (with paragraph) - must come before inciso pattern
        (r"Art(?:igo)?[.]?\s*(\d{1,4})[°º]?,?\s*([§]+\s*\d+[°º]?(?:\s*e\s*\d+[°º]?)?)", "paragraph"),
        # Art. X, caput - must come before inciso pattern (caput starts with 'c')
        (r"Art(?:igo)?[.]?\s*(\d{1,4})[°º]?,?\s*(caput)\b", "caput"),
        # Art. X, I, II (with roman numeral inciso - must be uppercase and followed by word boundary or comma)
        # Only match valid Roman numerals: I, V, X, L, C, D, M and combinations
        (r"Art(?:igo)?[.]?\s*(\d{1,4})[°º]?,\s*([IVXLCDM]+(?:\s*(?:,|e|a)\s*[IVXLCDM]+)*)(?=\s|,|$|\.)", "inciso"),
    ]

    matched_articles: Set[str] = set()

    for pattern, match_type in article_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            art_num = match.group(1)
            complement = match.group(2).strip() if len(match.groups()) > 1 and match.group(2) else ""

            # For inciso pattern, validate it's actually Roman numerals (not just single letters)
            if match_type == "inciso":
                # Skip if it looks like part of a word (e.g., "Art. 5, caput" -> "c" is not valid)
                if len(complement) == 1 and complement.lower() in ['c', 'd', 'l', 'm']:
                    # Check if followed by lowercase letters (part of word)
                    end_pos = match.end()
                    if end_pos < len(text) and text[end_pos:end_pos+1].isalpha():
                        continue

            if complement:
                matched_articles.add(f"Art. {art_num}, {complement}")
            else:
                matched_articles.add(f"Art. {art_num}")

    # Find standalone articles (not matched by specific patterns above)
    standalone_pattern = r"Art(?:igo)?[.]?\s*(\d{1,4})[°º]?"
    for match in re.finditer(standalone_pattern, text, re.IGNORECASE):
        art_num = match.group(1)
        base_art = f"Art. {art_num}"
        # Check if this article was already matched with a complement
        already_matched = any(base_art in matched for matched in matched_articles)
        if not already_matched:
            # Check if followed by comma + complement (would be caught by patterns above)
            end_pos = match.end()
            remaining = text[end_pos:end_pos+20] if end_pos < len(text) else ""
            if not re.match(r'\s*,\s*(?:[§IVXLCDM]|caput)', remaining, re.IGNORECASE):
                matched_articles.add(base_art)

    entities["articles"].update(matched_articles)

    # Sumulas
    sumula_patterns = [
        r"S[úu]mula\s+Vinculante\s+(?:n[°º.]?\s*)?(\d{1,3})",
        r"S[úu]mula\s+(?:n[°º.]?\s*)?(\d{1,4})(?:\s+(?:do\s+)?(?P<tribunal>STF|STJ|TST|TRF|TRT|TSE))?",
        r"(?:OJ|Orienta[çc][aã]o\s+Jurisprudencial)\s+(?:n[°º.]?\s*)?(\d{1,4})(?:\s+(?P<orgao>SDI|SBDI)[-]?\d?)?",
    ]

    for pattern in sumula_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            full_match = match.group(0).strip()
            # Normalize
            full_match = re.sub(r'\s+', ' ', full_match)
            entities["sumulas"].add(full_match)

    # Decisions
    decision_patterns = [
        r"(?:RE|REsp|RR|RO|AI|AgR|ED|HC|MS|ADI|ADC|ADPF|RCL|ACO|Rcl)\s*[\-]?\s*(\d{4,8})",
        r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}",  # CNJ number
    ]

    for pattern in decision_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            entities["decisions"].add(match.group(0).strip())

    return {k: sorted(v) for k, v in entities.items()}


def _normalize_entity(entity: str) -> str:
    """Normalize an entity for comparison."""
    normalized = entity.lower().strip()
    normalized = re.sub(r'[áàâã]', 'a', normalized)
    normalized = re.sub(r'[éèê]', 'e', normalized)
    normalized = re.sub(r'[íìî]', 'i', normalized)
    normalized = re.sub(r'[óòôõ]', 'o', normalized)
    normalized = re.sub(r'[úùû]', 'u', normalized)
    normalized = re.sub(r'ç', 'c', normalized)
    normalized = re.sub(r'[°º]', '', normalized)
    normalized = re.sub(r'\s+', ' ', normalized)
    normalized = re.sub(r'[.,;:]+$', '', normalized)
    return normalized


def evaluate_entity_accuracy(
    answer: str,
    expected_entities: List[str]
) -> Tuple[float, float]:
    """
    Compare extracted entities against expected.

    Returns (precision, recall).

    Precision: Of the entities in the answer, how many are correct?
    Recall: Of the expected entities, how many appear in the answer?
    """
    if not expected_entities:
        return (1.0, 1.0)  # No expected entities = perfect match

    # Extract all entities from answer
    answer_entities = extract_legal_entities(answer)
    all_answer_entities: Set[str] = set()
    for entity_list in answer_entities.values():
        all_answer_entities.update(entity_list)

    # Normalize for comparison
    normalized_answer = {_normalize_entity(e) for e in all_answer_entities}
    normalized_expected = {_normalize_entity(e) for e in expected_entities}

    # Calculate matches (using fuzzy matching for entities)
    matches = 0
    for expected in normalized_expected:
        for answer_ent in normalized_answer:
            # Exact match or substring match for flexibility
            if expected == answer_ent or expected in answer_ent or answer_ent in expected:
                matches += 1
                break

    # Precision and recall
    precision = matches / len(normalized_answer) if normalized_answer else 1.0
    recall = matches / len(normalized_expected) if normalized_expected else 1.0

    return (precision, recall)


# =============================================================================
# Main Evaluation Function
# =============================================================================

def evaluate_legal_answer(
    query: str,
    answer: str,
    ground_truth: str,
    expected_entities: Optional[List[str]] = None,
    expected_jurisdiction: Optional[str] = None
) -> LegalEvalResult:
    """
    Run all legal-specific evaluations on an answer.

    Args:
        query: The original legal question
        answer: The RAG-generated answer
        ground_truth: The expected/correct answer
        expected_entities: List of expected legal entities (laws, articles, etc.)
        expected_jurisdiction: Expected jurisdiction (federal, estadual, etc.)

    Returns:
        LegalEvalResult with all metrics
    """
    # Citation coverage
    citation_coverage = evaluate_citation_coverage(answer)

    # Temporal validity
    temporal_score, outdated_laws = evaluate_temporal_validity(answer)

    # Jurisdiction match
    jurisdiction_match = evaluate_jurisdiction_match(
        query, answer, expected_jurisdiction
    )

    # Entity accuracy
    if expected_entities:
        precision, recall = evaluate_entity_accuracy(answer, expected_entities)
    else:
        # Extract entities from ground truth as expected
        gt_entities = extract_legal_entities(ground_truth)
        all_gt_entities: List[str] = []
        for entity_list in gt_entities.values():
            all_gt_entities.extend(entity_list)

        if all_gt_entities:
            precision, recall = evaluate_entity_accuracy(answer, all_gt_entities)
        else:
            precision, recall = (1.0, 1.0)

    # Build details
    details = {
        "claims_extracted": len(extract_legal_claims(answer)),
        "cited_claims": count_cited_claims(answer)[0],
        "laws_cited": extract_cited_laws(answer),
        "outdated_laws": outdated_laws,
        "entities_found": extract_legal_entities(answer),
        "jurisdictions_mentioned": list(_extract_jurisdiction_from_text(answer)),
        "query_jurisdictions": list(_extract_jurisdiction_from_text(query)),
        "expected_jurisdiction": expected_jurisdiction,
    }

    return LegalEvalResult(
        citation_coverage=round(citation_coverage, 4),
        temporal_validity=round(temporal_score, 4),
        jurisdiction_match=jurisdiction_match,
        entity_precision=round(precision, 4),
        entity_recall=round(recall, 4),
        details=details,
    )


# =============================================================================
# Integration with RAGAS
# =============================================================================

def add_legal_metrics_to_ragas(results: Dict) -> Dict:
    """
    Add legal metrics to RAGAS evaluation results.

    Expects results dict with:
    - samples: List of dicts with 'question', 'answer', 'ground_truth'

    Adds legal_metrics to each sample and summary.
    """
    samples = results.get("samples", [])
    if not samples:
        return results

    legal_summaries = {
        "citation_coverage": [],
        "temporal_validity": [],
        "jurisdiction_match": [],
        "entity_precision": [],
        "entity_recall": [],
    }

    for sample in samples:
        query = sample.get("question", "") or sample.get("query", "")
        answer = sample.get("answer", "")
        ground_truth = sample.get("ground_truth", "") or sample.get("reference", "")
        expected_entities = sample.get("expected_entities")
        expected_jurisdiction = sample.get("expected_jurisdiction")

        # Evaluate
        legal_result = evaluate_legal_answer(
            query=query,
            answer=answer,
            ground_truth=ground_truth,
            expected_entities=expected_entities,
            expected_jurisdiction=expected_jurisdiction,
        )

        # Add to sample
        sample["legal_metrics"] = {
            "citation_coverage": legal_result.citation_coverage,
            "temporal_validity": legal_result.temporal_validity,
            "jurisdiction_match": legal_result.jurisdiction_match,
            "entity_precision": legal_result.entity_precision,
            "entity_recall": legal_result.entity_recall,
            "details": legal_result.details,
        }

        # Accumulate for summary
        legal_summaries["citation_coverage"].append(legal_result.citation_coverage)
        legal_summaries["temporal_validity"].append(legal_result.temporal_validity)
        legal_summaries["jurisdiction_match"].append(1.0 if legal_result.jurisdiction_match else 0.0)
        legal_summaries["entity_precision"].append(legal_result.entity_precision)
        legal_summaries["entity_recall"].append(legal_result.entity_recall)

    # Calculate averages for summary
    def safe_avg(values: List[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    results["summary"] = results.get("summary", {})
    results["summary"]["legal_citation_coverage"] = round(safe_avg(legal_summaries["citation_coverage"]), 4)
    results["summary"]["legal_temporal_validity"] = round(safe_avg(legal_summaries["temporal_validity"]), 4)
    results["summary"]["legal_jurisdiction_match"] = round(safe_avg(legal_summaries["jurisdiction_match"]), 4)
    results["summary"]["legal_entity_precision"] = round(safe_avg(legal_summaries["entity_precision"]), 4)
    results["summary"]["legal_entity_recall"] = round(safe_avg(legal_summaries["entity_recall"]), 4)

    # Combined legal score (weighted average)
    legal_score = (
        0.25 * results["summary"]["legal_citation_coverage"] +
        0.20 * results["summary"]["legal_temporal_validity"] +
        0.15 * results["summary"]["legal_jurisdiction_match"] +
        0.20 * results["summary"]["legal_entity_precision"] +
        0.20 * results["summary"]["legal_entity_recall"]
    )
    results["summary"]["legal_score"] = round(legal_score, 4)

    return results


# =============================================================================
# Batch Evaluation Helper
# =============================================================================

def evaluate_legal_batch(
    samples: List[Dict],
    verbose: bool = False
) -> Dict:
    """
    Evaluate a batch of legal Q&A samples.

    Args:
        samples: List of dicts with 'query', 'answer', 'ground_truth'
        verbose: Print detailed results

    Returns:
        Dict with summary and per-sample results
    """
    results = {"samples": samples, "summary": {}}
    results = add_legal_metrics_to_ragas(results)

    if verbose:
        print(f"\n{'='*60}")
        print("LEGAL RAG EVALUATION RESULTS")
        print(f"{'='*60}")
        print(f"Samples evaluated: {len(samples)}")
        print(f"\nSummary Metrics:")
        for key, value in results["summary"].items():
            if key.startswith("legal_"):
                print(f"  {key}: {value:.4f}")
        print(f"\n{'='*60}")

    return results


# =============================================================================
# RAGAs Integration — Métricas padrão + legais combinadas
# =============================================================================

async def evaluate_with_ragas(
    samples: List[Dict],
    metrics: Optional[List[str]] = None,
    llm_provider: str = "openai",
) -> Dict:
    """
    Avalia com RAGAs (métricas padrão) + métricas legais brasileiras.

    Métricas RAGAs disponíveis:
    - faithfulness: resposta é fiel aos contextos recuperados?
    - answer_relevancy: resposta é relevante à pergunta?
    - context_precision: contextos recuperados são precisos?
    - context_recall: contextos cobrem a resposta esperada?

    Métricas legais (sempre incluídas):
    - citation_coverage, temporal_validity, jurisdiction_match
    - entity_precision, entity_recall

    Args:
        samples: Lista de dicts com keys:
            - question (str): Pergunta
            - answer (str): Resposta gerada
            - contexts (List[str]): Contextos recuperados
            - ground_truth (str): Resposta de referência (opcional)
        metrics: Lista de métricas RAGAs a usar (None = todas)
        llm_provider: Provider LLM para RAGAs ("openai" ou "default")

    Returns:
        Dict com 'ragas_scores', 'legal_scores', 'combined_score', 'per_sample'
    """
    result = {
        "ragas_scores": {},
        "legal_scores": {},
        "combined_score": 0.0,
        "per_sample": [],
        "ragas_available": False,
    }

    # --- Parte 1: Métricas RAGAs ---
    try:
        from ragas import evaluate as ragas_evaluate
        from ragas.metrics import (
            Faithfulness,
            ResponseRelevancy,
            LLMContextPrecisionWithoutReference,
            LLMContextRecall,
        )
        from ragas import EvaluationDataset, SingleTurnSample

        available_metrics = {
            "faithfulness": Faithfulness(),
            "answer_relevancy": ResponseRelevancy(),
            "context_precision": LLMContextPrecisionWithoutReference(),
            "context_recall": LLMContextRecall(),
        }

        selected = metrics or list(available_metrics.keys())
        ragas_metrics = [available_metrics[m] for m in selected if m in available_metrics]

        # Montar dataset RAGAs
        ragas_samples = []
        for s in samples:
            ragas_samples.append(SingleTurnSample(
                user_input=s.get("question", ""),
                response=s.get("answer", ""),
                retrieved_contexts=s.get("contexts", []),
                reference=s.get("ground_truth", ""),
            ))

        dataset = EvaluationDataset(samples=ragas_samples)
        ragas_result = ragas_evaluate(dataset=dataset, metrics=ragas_metrics)

        # Extrair scores
        for metric_name in selected:
            if metric_name in available_metrics:
                score = ragas_result.get(metric_name, 0.0)
                if score is not None:
                    result["ragas_scores"][metric_name] = round(float(score), 4)

        result["ragas_available"] = True

    except ImportError:
        result["ragas_scores"] = {
            "error": "ragas não instalado. Execute: pip install ragas>=0.2.0"
        }
    except Exception as e:
        result["ragas_scores"] = {"error": f"RAGAs evaluation failed: {str(e)}"}

    # --- Parte 2: Métricas legais (sempre executam) ---
    legal_results_data = {"samples": samples}
    legal_results_data = add_legal_metrics_to_ragas(legal_results_data)
    result["legal_scores"] = legal_results_data.get("summary", {})

    # --- Parte 3: Score combinado ---
    ragas_scores = result["ragas_scores"]
    legal_scores = result["legal_scores"]

    weights = {
        # RAGAs (50% do total)
        "faithfulness": 0.15,
        "answer_relevancy": 0.15,
        "context_precision": 0.10,
        "context_recall": 0.10,
        # Legal (50% do total)
        "legal_citation_coverage": 0.15,
        "legal_temporal_validity": 0.10,
        "legal_jurisdiction_match": 0.10,
        "legal_entity_precision": 0.075,
        "legal_entity_recall": 0.075,
    }

    combined = 0.0
    total_weight = 0.0
    for key, weight in weights.items():
        value = ragas_scores.get(key) or legal_scores.get(key)
        if value is not None and isinstance(value, (int, float)):
            combined += weight * float(value)
            total_weight += weight

    result["combined_score"] = round(combined / total_weight, 4) if total_weight > 0 else 0.0

    # Per-sample results
    for i, s in enumerate(samples):
        sample_result = {
            "question": s.get("question", ""),
            "legal_metrics": s.get("legal_metrics", {}),
        }
        result["per_sample"].append(sample_result)

    return result


# =============================================================================
# Command-line interface
# =============================================================================

if __name__ == "__main__":
    # Example usage
    sample_answer = """
    Conforme disposto na Lei 8.666/93, Art. 21, o prazo mínimo para publicação
    do edital de licitação é de 30 dias para concorrência. A Súmula 331 do TST
    estabelece a responsabilidade subsidiária do tomador de serviços.

    O STF, no RE 760931, firmou entendimento sobre a constitucionalidade
    da terceirização de atividade-fim. De acordo com o Art. 37, XXI da CF/88,
    a licitação é obrigatória para contratações públicas.

    A MP 927/2020 flexibilizou regras trabalhistas durante a pandemia.
    """

    sample_query = "Qual o prazo para publicação de edital de licitação federal?"
    sample_ground_truth = "O prazo mínimo é de 30 dias para concorrência, conforme Art. 21 da Lei 14.133/2021."

    result = evaluate_legal_answer(
        query=sample_query,
        answer=sample_answer,
        ground_truth=sample_ground_truth,
        expected_entities=["Lei 14.133/2021", "Art. 21"],
        expected_jurisdiction="federal"
    )

    print("Legal Evaluation Result:")
    print(f"  Citation Coverage: {result.citation_coverage:.2%}")
    print(f"  Temporal Validity: {result.temporal_validity:.2%}")
    print(f"  Jurisdiction Match: {result.jurisdiction_match}")
    print(f"  Entity Precision: {result.entity_precision:.2%}")
    print(f"  Entity Recall: {result.entity_recall:.2%}")
    print(f"\nDetails:")
    print(f"  Laws cited: {result.details['laws_cited']}")
    print(f"  Outdated laws: {result.details['outdated_laws']}")
    print(f"  Entities found: {result.details['entities_found']}")
