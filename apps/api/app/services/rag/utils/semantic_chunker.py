"""
Semantic Chunker for Brazilian Legal Documents

Provides intelligent chunking that preserves the structure of Brazilian legal documents:
- Legislation (Leis, Decretos, Medidas Provisorias)
- Court decisions (Acordaos, Sentencas)
- Administrative documents

Features:
- Legal article detection (Art., Paragrafo, Inciso, Alinea)
- Court decision structure detection (Ementa, Relatorio, Voto, Acordao)
- Header hierarchy preservation (Titulo, Capitulo, Secao)
- Sentence-aware fallback chunking
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Pattern
from loguru import logger


# =============================================================================
# ENUMS AND CONSTANTS
# =============================================================================


class DocumentType(str, Enum):
    """Brazilian legal document types."""
    LEI = "lei"
    DECRETO = "decreto"
    MEDIDA_PROVISORIA = "medida_provisoria"
    ACORDAO = "acordao"
    SENTENCA = "sentenca"
    PARECER = "parecer"
    DESPACHO = "despacho"
    PETICAO = "peticao"
    CONTRATO = "contrato"
    EDITAL = "edital"
    PORTARIA = "portaria"
    RESOLUCAO = "resolucao"
    INSTRUCAO_NORMATIVA = "instrucao_normativa"
    UNKNOWN = "unknown"


class ChunkType(str, Enum):
    """Types of semantic chunks."""
    # Legislation structure
    ARTIGO = "artigo"
    PARAGRAFO = "paragrafo"
    INCISO = "inciso"
    ALINEA = "alinea"
    CAPUT = "caput"

    # Court decision structure
    EMENTA = "ementa"
    RELATORIO = "relatorio"
    VOTO = "voto"
    ACORDAO = "acordao"
    DISPOSITIVO = "dispositivo"
    FUNDAMENTACAO = "fundamentacao"

    # Document hierarchy
    TITULO = "titulo"
    CAPITULO = "capitulo"
    SECAO = "secao"
    SUBSECAO = "subsecao"
    LIVRO = "livro"
    PARTE = "parte"

    # Generic
    HEADER = "header"
    PREAMBULO = "preambulo"
    CLAUSULA = "clausula"
    CONSIDERANDO = "considerando"
    PARAGRAPH = "paragraph"
    FALLBACK = "fallback"


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class SemanticChunk:
    """
    Represents a semantically meaningful chunk of a legal document.

    Attributes:
        text: The chunk text content
        chunk_type: Type of legal structure (artigo, ementa, voto, etc.)
        hierarchy: Document hierarchy path (e.g., ["Lei 8.112", "Titulo II", "Art. 5"])
        page: Optional page number
        metadata: Additional metadata (position, references, etc.)
    """
    text: str
    chunk_type: str
    hierarchy: List[str] = field(default_factory=list)
    page: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Ensure defaults are set."""
        if self.hierarchy is None:
            self.hierarchy = []
        if self.metadata is None:
            self.metadata = {}

    @property
    def char_count(self) -> int:
        """Return character count."""
        return len(self.text)

    @property
    def full_reference(self) -> str:
        """Return full hierarchical reference."""
        return " > ".join(self.hierarchy) if self.hierarchy else ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "text": self.text,
            "chunk_type": self.chunk_type,
            "hierarchy": self.hierarchy,
            "page": self.page,
            "metadata": self.metadata,
            "char_count": self.char_count,
            "full_reference": self.full_reference,
        }


@dataclass
class ChunkingConfig:
    """Configuration for semantic chunking."""
    max_chunk_chars: int = 2000
    min_chunk_chars: int = 100
    overlap_chars: int = 200
    preserve_articles: bool = True
    merge_small_chunks: bool = True
    include_hierarchy: bool = True
    sentence_aware_fallback: bool = True


# =============================================================================
# REGEX PATTERNS FOR BRAZILIAN LEGAL DOCUMENTS
# =============================================================================


class LegalPatterns:
    """Comprehensive regex patterns for Brazilian legal document structure."""

    # -------------------------------------------------------------------------
    # LEGISLATION ARTICLE PATTERNS
    # -------------------------------------------------------------------------

    # Art. N / Artigo N (including variations like Art. 1o, Art. 1st, etc.)
    ARTIGO: Pattern = re.compile(
        r'^[\s]*'  # Leading whitespace
        r'(?:Art(?:igo)?\.?\s*)'  # Art. or Artigo
        r'(\d+(?:[o\u00BA]|[a-z]{0,2})?)'  # Number with optional ordinal
        r'(?:[\s\.\-\u2013\u2014]*)?'  # Optional separator
        r'(.*)',  # Rest of the article
        re.IGNORECASE | re.MULTILINE
    )

    # Paragraph patterns: Par. N / Paragrafo N / Paragrafo unico
    PARAGRAFO: Pattern = re.compile(
        r'^[\s]*'
        r'(?:'
        r'\u00A7\s*(\d+(?:[o\u00BA])?)|'  # Section symbol with number
        r'Par(?:\u00E1grafo|agrafo)?\.?\s*(\d+(?:[o\u00BA])?)|'  # Paragrafo N
        r'Par(?:\u00E1grafo|agrafo)?\s+[Uu]nico'  # Paragrafo unico
        r')'
        r'[\s\.\-\u2013\u2014]*'
        r'(.*)',
        re.IGNORECASE | re.MULTILINE
    )

    # Inciso patterns: Roman numerals (I, II, III, etc.)
    INCISO: Pattern = re.compile(
        r'^[\s]*'
        r'((?:X{0,3})(?:IX|IV|V?I{0,3}))'  # Roman numeral
        r'[\s]*[\-\u2013\u2014][\s]*'  # Separator
        r'(.*)',
        re.MULTILINE
    )

    # Alinea patterns: a), b), c), etc.
    ALINEA: Pattern = re.compile(
        r'^[\s]*'
        r'([a-z])\)'  # Letter with closing parenthesis
        r'[\s]*'
        r'(.*)',
        re.MULTILINE
    )

    # -------------------------------------------------------------------------
    # COURT DECISION SECTION PATTERNS
    # -------------------------------------------------------------------------

    EMENTA: Pattern = re.compile(
        r'(?:^|\n)[\s]*'
        r'(?:E\s*M\s*E\s*N\s*T\s*A|EMENTA)'
        r'[\s\:\.\-]*'
        r'(.*?)(?=(?:RELAT[OÓ]RIO|VOTO|AC[OÓ]RD[AÃ]O|\n\s*[A-Z\s]{3,}\s*\n)|$)',
        re.IGNORECASE | re.DOTALL
    )

    RELATORIO: Pattern = re.compile(
        r'(?:^|\n)[\s]*'
        r'(?:R\s*E\s*L\s*A\s*T\s*[OÓ]\s*R\s*I\s*O|RELAT[OÓ]RIO)'
        r'[\s\:\.\-]*'
        r'(.*?)(?=(?:VOTO|FUNDAMENTA[CÇ][AÃ]O|AC[OÓ]RD[AÃ]O|\n\s*[A-Z\s]{3,}\s*\n)|$)',
        re.IGNORECASE | re.DOTALL
    )

    VOTO: Pattern = re.compile(
        r'(?:^|\n)[\s]*'
        r'(?:V\s*O\s*T\s*O|VOTO)'
        r'[\s\:\.\-]*'
        r'(?:DO\s+(?:RELATOR|MINISTRO|DESEMBARGADOR|JUIZ)[A-Z\s\.]*)?'
        r'(.*?)(?=(?:AC[OÓ]RD[AÃ]O|DISPOSITIVO|\n\s*[A-Z\s]{3,}\s*\n)|$)',
        re.IGNORECASE | re.DOTALL
    )

    ACORDAO_SECTION: Pattern = re.compile(
        r'(?:^|\n)[\s]*'
        r'(?:A\s*C\s*[OÓ]\s*R\s*D\s*[AÃ]\s*O|AC[OÓ]RD[AÃ]O)'
        r'[\s\:\.\-]*'
        r'(.*?)(?=(?:CERTID[AÃ]O|PUBLICA[CÇ][AÃ]O|\Z))',
        re.IGNORECASE | re.DOTALL
    )

    DISPOSITIVO: Pattern = re.compile(
        r'(?:^|\n)[\s]*'
        r'(?:D\s*I\s*S\s*P\s*O\s*S\s*I\s*T\s*I\s*V\s*O|DISPOSITIVO)'
        r'[\s\:\.\-]*'
        r'(.*?)(?=(?:AC[OÓ]RD[AÃ]O|CERTID[AÃ]O|\Z))',
        re.IGNORECASE | re.DOTALL
    )

    FUNDAMENTACAO: Pattern = re.compile(
        r'(?:^|\n)[\s]*'
        r'(?:FUNDAMENTA[CÇ][AÃ]O|MOTIVA[CÇ][AÃ]O)'
        r'[\s\:\.\-]*'
        r'(.*?)(?=(?:DISPOSITIVO|AC[OÓ]RD[AÃ]O|CONCLUS[AÃ]O|\Z))',
        re.IGNORECASE | re.DOTALL
    )

    # -------------------------------------------------------------------------
    # HIERARCHY PATTERNS (TITLES, CHAPTERS, SECTIONS)
    # -------------------------------------------------------------------------

    TITULO: Pattern = re.compile(
        r'^[\s]*'
        r'(?:T[IÍ]TULO|TITULO)'
        r'[\s]+'
        r'([IVXLCDM]+|\d+)'  # Roman or Arabic numeral
        r'[\s\-\u2013\u2014]*'
        r'(.*)',
        re.IGNORECASE | re.MULTILINE
    )

    CAPITULO: Pattern = re.compile(
        r'^[\s]*'
        r'(?:CAP[IÍ]TULO|CAPITULO)'
        r'[\s]+'
        r'([IVXLCDM]+|\d+)'
        r'[\s\-\u2013\u2014]*'
        r'(.*)',
        re.IGNORECASE | re.MULTILINE
    )

    SECAO: Pattern = re.compile(
        r'^[\s]*'
        r'(?:SE[CÇ][AÃ]O|SECAO|SEÇÃO)'
        r'[\s]+'
        r'([IVXLCDM]+|\d+)'
        r'[\s\-\u2013\u2014]*'
        r'(.*)',
        re.IGNORECASE | re.MULTILINE
    )

    SUBSECAO: Pattern = re.compile(
        r'^[\s]*'
        r'(?:SUBSE[CÇ][AÃ]O|SUBSECAO|SUBSEÇÃO)'
        r'[\s]+'
        r'([IVXLCDM]+|\d+)'
        r'[\s\-\u2013\u2014]*'
        r'(.*)',
        re.IGNORECASE | re.MULTILINE
    )

    LIVRO: Pattern = re.compile(
        r'^[\s]*'
        r'(?:LIVRO)'
        r'[\s]+'
        r'([IVXLCDM]+|\d+)'
        r'[\s\-\u2013\u2014]*'
        r'(.*)',
        re.IGNORECASE | re.MULTILINE
    )

    PARTE: Pattern = re.compile(
        r'^[\s]*'
        r'(?:PARTE)'
        r'[\s]+'
        r'(GERAL|ESPECIAL|[IVXLCDM]+|\d+)'
        r'[\s\-\u2013\u2014]*'
        r'(.*)',
        re.IGNORECASE | re.MULTILINE
    )

    # -------------------------------------------------------------------------
    # CONTRACT AND ADMINISTRATIVE PATTERNS
    # -------------------------------------------------------------------------

    CLAUSULA: Pattern = re.compile(
        r'^[\s]*'
        r'(?:CL[AÁ]USULA|CLAUSULA)'
        r'[\s]+'
        r'(\d+(?:[aª])?|(?:PRIMEIRA|SEGUNDA|TERCEIRA|QUARTA|QUINTA|'
        r'SEXTA|S[EÉ]TIMA|OITAVA|NONA|D[EÉ]CIMA))'
        r'[\s\-\u2013\u2014:]*'
        r'(.*)',
        re.IGNORECASE | re.MULTILINE
    )

    CONSIDERANDO: Pattern = re.compile(
        r'^[\s]*'
        r'(?:CONSIDERANDO)'
        r'[\s]+(?:QUE)?[\s]*'
        r'(.*)',
        re.IGNORECASE | re.MULTILINE
    )

    # -------------------------------------------------------------------------
    # DOCUMENT TYPE DETECTION PATTERNS
    # -------------------------------------------------------------------------

    DOC_TYPE_LEI: Pattern = re.compile(
        r'(?:LEI(?:\s+COMPLEMENTAR|\s+ORDIN[AÁ]RIA|\s+FEDERAL|\s+ESTADUAL|\s+MUNICIPAL)?'
        r'(?:\s+N[OoºUuMmEeRrOo\.]*)?[\s\.]*\d+)',
        re.IGNORECASE
    )

    DOC_TYPE_DECRETO: Pattern = re.compile(
        r'(?:DECRETO(?:\s+LEI|\s+FEDERAL|\s+ESTADUAL)?'
        r'(?:\s+N[OoºUuMmEeRrOo\.]*)?[\s\.]*\d+)',
        re.IGNORECASE
    )

    DOC_TYPE_MEDIDA_PROVISORIA: Pattern = re.compile(
        r'(?:MEDIDA\s+PROVIS[OÓ]RIA'
        r'(?:\s+N[OoºUuMmEeRrOo\.]*)?[\s\.]*\d+)',
        re.IGNORECASE
    )

    DOC_TYPE_ACORDAO: Pattern = re.compile(
        r'(?:AC[OÓ]RD[AÃ]O|EMENTA[\s\:]+.*?(?:STF|STJ|TRF|TJ|TST|TRT))',
        re.IGNORECASE
    )

    DOC_TYPE_SENTENCA: Pattern = re.compile(
        r'(?:SENTEN[CÇ]A|DISPOSITIVO[\s\:]+.*?(?:JULGO|CONDENO|ABSOLVO))',
        re.IGNORECASE
    )

    DOC_TYPE_PORTARIA: Pattern = re.compile(
        r'(?:PORTARIA(?:\s+N[OoºUuMmEeRrOo\.]*)?[\s\.]*\d+)',
        re.IGNORECASE
    )

    DOC_TYPE_RESOLUCAO: Pattern = re.compile(
        r'(?:RESOLU[CÇ][AÃ]O(?:\s+N[OoºUuMmEeRrOo\.]*)?[\s\.]*\d+)',
        re.IGNORECASE
    )

    # -------------------------------------------------------------------------
    # SENTENCE BOUNDARY PATTERN (for fallback chunking)
    # -------------------------------------------------------------------------

    SENTENCE_END: Pattern = re.compile(
        r'(?<=[.!?;:])'  # End punctuation
        r'(?:\s+|$)'  # Followed by whitespace or end
        r'(?=[A-Z\d"\'(]|$)'  # Followed by uppercase, digit, quote, or end
    )


# =============================================================================
# DOCUMENT TYPE DETECTION
# =============================================================================


def detect_document_type(text: str) -> DocumentType:
    """
    Detect the type of Brazilian legal document.

    Args:
        text: Document text (first ~2000 chars are usually enough)

    Returns:
        DocumentType enum value
    """
    # Use first 3000 chars for detection
    sample = text[:3000] if len(text) > 3000 else text

    # Check patterns in order of specificity
    if LegalPatterns.DOC_TYPE_ACORDAO.search(sample):
        return DocumentType.ACORDAO
    if LegalPatterns.DOC_TYPE_SENTENCA.search(sample):
        return DocumentType.SENTENCA
    if LegalPatterns.DOC_TYPE_MEDIDA_PROVISORIA.search(sample):
        return DocumentType.MEDIDA_PROVISORIA
    if LegalPatterns.DOC_TYPE_DECRETO.search(sample):
        return DocumentType.DECRETO
    if LegalPatterns.DOC_TYPE_LEI.search(sample):
        return DocumentType.LEI
    if LegalPatterns.DOC_TYPE_PORTARIA.search(sample):
        return DocumentType.PORTARIA
    if LegalPatterns.DOC_TYPE_RESOLUCAO.search(sample):
        return DocumentType.RESOLUCAO

    # Check for contract structure
    if LegalPatterns.CLAUSULA.search(sample):
        return DocumentType.CONTRATO

    # Check for general legislation structure (articles)
    if LegalPatterns.ARTIGO.search(sample):
        return DocumentType.LEI

    return DocumentType.UNKNOWN


# =============================================================================
# CHUNKING FUNCTIONS
# =============================================================================


def chunk_legal_document(
    text: str,
    doc_type: str = "auto",
    config: Optional[ChunkingConfig] = None,
) -> List[SemanticChunk]:
    """
    Chunk a legal document preserving its semantic structure.

    Args:
        text: Document text
        doc_type: Document type ("auto" for automatic detection, or specific type)
        config: Chunking configuration

    Returns:
        List of SemanticChunk objects
    """
    if not text or not text.strip():
        return []

    config = config or ChunkingConfig()

    # Detect document type if auto
    if doc_type == "auto":
        detected_type = detect_document_type(text)
        logger.debug(f"Auto-detected document type: {detected_type.value}")
    else:
        try:
            detected_type = DocumentType(doc_type.lower())
        except ValueError:
            detected_type = DocumentType.UNKNOWN

    # Route to appropriate chunker
    if detected_type in (DocumentType.LEI, DocumentType.DECRETO,
                         DocumentType.MEDIDA_PROVISORIA, DocumentType.PORTARIA,
                         DocumentType.RESOLUCAO, DocumentType.INSTRUCAO_NORMATIVA):
        chunks = chunk_lei(text, config)
    elif detected_type in (DocumentType.ACORDAO, DocumentType.SENTENCA):
        chunks = chunk_acordao(text, config)
    elif detected_type == DocumentType.CONTRATO:
        chunks = chunk_contrato(text, config)
    else:
        # Try legislation structure first, fall back to generic
        chunks = chunk_lei(text, config)
        if len(chunks) <= 1:
            chunks = chunk_fallback(text, config)

    # Merge small chunks if configured
    if config.merge_small_chunks:
        chunks = _merge_small_chunks(chunks, config)

    # Add metadata
    for i, chunk in enumerate(chunks):
        chunk.metadata["chunk_index"] = i
        chunk.metadata["total_chunks"] = len(chunks)
        chunk.metadata["doc_type"] = detected_type.value

    return chunks


def chunk_lei(text: str, config: Optional[ChunkingConfig] = None) -> List[SemanticChunk]:
    """
    Chunk legislation by articles and structural hierarchy.

    Args:
        text: Legislation text
        config: Chunking configuration

    Returns:
        List of SemanticChunk objects
    """
    config = config or ChunkingConfig()
    chunks: List[SemanticChunk] = []

    # Track current hierarchy
    hierarchy: List[str] = []

    # Split into lines for processing
    lines = text.split('\n')
    current_chunk_lines: List[str] = []
    current_chunk_type = ChunkType.PREAMBULO.value
    current_article = None

    def _save_current_chunk():
        nonlocal current_chunk_lines, current_chunk_type
        if current_chunk_lines:
            chunk_text = '\n'.join(current_chunk_lines).strip()
            if chunk_text and len(chunk_text) >= config.min_chunk_chars:
                chunks.append(SemanticChunk(
                    text=chunk_text,
                    chunk_type=current_chunk_type,
                    hierarchy=hierarchy.copy(),
                    metadata={"article": current_article} if current_article else {}
                ))
            current_chunk_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current_chunk_lines:
                current_chunk_lines.append(line)
            continue

        # Check for hierarchy markers
        if titulo_match := LegalPatterns.TITULO.match(line):
            _save_current_chunk()
            num, title = titulo_match.groups()
            hierarchy = [f"Titulo {num}"]
            if title.strip():
                hierarchy[-1] += f" - {title.strip()}"
            current_chunk_type = ChunkType.TITULO.value
            current_chunk_lines = [line]
            continue

        if capitulo_match := LegalPatterns.CAPITULO.match(line):
            _save_current_chunk()
            num, title = capitulo_match.groups()
            # Keep titulo in hierarchy if exists
            hierarchy = hierarchy[:1] if hierarchy else []
            hierarchy.append(f"Capitulo {num}")
            if title.strip():
                hierarchy[-1] += f" - {title.strip()}"
            current_chunk_type = ChunkType.CAPITULO.value
            current_chunk_lines = [line]
            continue

        if secao_match := LegalPatterns.SECAO.match(line):
            _save_current_chunk()
            num, title = secao_match.groups()
            # Keep titulo and capitulo
            hierarchy = hierarchy[:2] if len(hierarchy) >= 2 else hierarchy.copy()
            hierarchy.append(f"Secao {num}")
            if title.strip():
                hierarchy[-1] += f" - {title.strip()}"
            current_chunk_type = ChunkType.SECAO.value
            current_chunk_lines = [line]
            continue

        # Check for articles
        if artigo_match := LegalPatterns.ARTIGO.match(line):
            _save_current_chunk()
            art_num = artigo_match.group(1)
            current_article = f"Art. {art_num}"
            # Update hierarchy with article
            base_hierarchy = [h for h in hierarchy if not h.startswith("Art.")]
            hierarchy = base_hierarchy + [current_article]
            current_chunk_type = ChunkType.ARTIGO.value
            current_chunk_lines = [line]
            continue

        # Check for paragraphs within articles
        if LegalPatterns.PARAGRAFO.match(line):
            if current_chunk_type == ChunkType.ARTIGO.value and len(current_chunk_lines) > 1:
                # Save current article chunk and start new paragraph chunk
                _save_current_chunk()
            current_chunk_type = ChunkType.PARAGRAFO.value
            current_chunk_lines.append(line)
            continue

        # Accumulate lines into current chunk
        current_chunk_lines.append(line)

        # Check if chunk is getting too large
        current_text = '\n'.join(current_chunk_lines)
        if len(current_text) > config.max_chunk_chars:
            # Find a good breaking point
            _save_current_chunk()
            current_chunk_type = ChunkType.PARAGRAPH.value

    # Save any remaining content
    _save_current_chunk()

    # If no chunks were created, use fallback
    if not chunks:
        return chunk_fallback(text, config)

    return chunks


def chunk_acordao(text: str, config: Optional[ChunkingConfig] = None) -> List[SemanticChunk]:
    """
    Chunk court decision by sections (Ementa, Relatorio, Voto, Acordao).

    Args:
        text: Court decision text
        config: Chunking configuration

    Returns:
        List of SemanticChunk objects
    """
    config = config or ChunkingConfig()
    chunks: List[SemanticChunk] = []

    # Try to extract document identifier
    doc_id = _extract_acordao_id(text)
    base_hierarchy = [doc_id] if doc_id else []

    # Track which sections we've found
    found_sections: Dict[str, Tuple[int, int, str]] = {}  # section -> (start, end, content)

    # Find all section positions
    section_patterns = [
        (ChunkType.EMENTA.value, LegalPatterns.EMENTA),
        (ChunkType.RELATORIO.value, LegalPatterns.RELATORIO),
        (ChunkType.VOTO.value, LegalPatterns.VOTO),
        (ChunkType.FUNDAMENTACAO.value, LegalPatterns.FUNDAMENTACAO),
        (ChunkType.DISPOSITIVO.value, LegalPatterns.DISPOSITIVO),
        (ChunkType.ACORDAO.value, LegalPatterns.ACORDAO_SECTION),
    ]

    for section_type, pattern in section_patterns:
        match = pattern.search(text)
        if match:
            content = match.group(1) if match.groups() else match.group(0)
            found_sections[section_type] = (match.start(), match.end(), content.strip())

    # Create chunks from found sections
    for section_type, (start, end, content) in sorted(found_sections.items(), key=lambda x: x[1][0]):
        if content and len(content) >= config.min_chunk_chars:
            # Split large sections into sub-chunks
            if len(content) > config.max_chunk_chars:
                sub_chunks = _split_large_section(content, section_type, config)
                for i, sub_content in enumerate(sub_chunks):
                    chunks.append(SemanticChunk(
                        text=sub_content,
                        chunk_type=section_type,
                        hierarchy=base_hierarchy + [section_type.upper()],
                        metadata={"section_part": i + 1, "total_parts": len(sub_chunks)}
                    ))
            else:
                chunks.append(SemanticChunk(
                    text=content,
                    chunk_type=section_type,
                    hierarchy=base_hierarchy + [section_type.upper()],
                ))

    # If no structured sections found, try to chunk by paragraphs
    if not chunks:
        return _chunk_acordao_by_paragraphs(text, base_hierarchy, config)

    return chunks


def chunk_contrato(text: str, config: Optional[ChunkingConfig] = None) -> List[SemanticChunk]:
    """
    Chunk contract by clauses.

    Args:
        text: Contract text
        config: Chunking configuration

    Returns:
        List of SemanticChunk objects
    """
    config = config or ChunkingConfig()
    chunks: List[SemanticChunk] = []

    # Find all clauses
    clause_matches = list(LegalPatterns.CLAUSULA.finditer(text))

    if not clause_matches:
        # No clauses found, use fallback
        return chunk_fallback(text, config)

    # Extract preamble (before first clause)
    if clause_matches[0].start() > 0:
        preamble = text[:clause_matches[0].start()].strip()
        if preamble and len(preamble) >= config.min_chunk_chars:
            chunks.append(SemanticChunk(
                text=preamble,
                chunk_type=ChunkType.PREAMBULO.value,
                hierarchy=["Preambulo"],
            ))

    # Extract each clause
    for i, match in enumerate(clause_matches):
        clause_num = match.group(1)
        clause_title = match.group(2).strip() if match.group(2) else ""

        # Determine end of this clause (start of next or end of text)
        if i < len(clause_matches) - 1:
            clause_end = clause_matches[i + 1].start()
        else:
            clause_end = len(text)

        clause_content = text[match.start():clause_end].strip()

        if clause_content and len(clause_content) >= config.min_chunk_chars:
            hierarchy = [f"Clausula {clause_num}"]
            if clause_title:
                hierarchy[-1] += f" - {clause_title}"

            # Split if too large
            if len(clause_content) > config.max_chunk_chars:
                sub_chunks = _split_large_section(clause_content, ChunkType.CLAUSULA.value, config)
                for j, sub_content in enumerate(sub_chunks):
                    chunks.append(SemanticChunk(
                        text=sub_content,
                        chunk_type=ChunkType.CLAUSULA.value,
                        hierarchy=hierarchy.copy(),
                        metadata={"clause_part": j + 1}
                    ))
            else:
                chunks.append(SemanticChunk(
                    text=clause_content,
                    chunk_type=ChunkType.CLAUSULA.value,
                    hierarchy=hierarchy,
                ))

    return chunks


def chunk_fallback(
    text: str,
    config: Optional[ChunkingConfig] = None,
) -> List[SemanticChunk]:
    """
    Fallback chunking with sentence-aware boundaries.

    Used when no legal structure is detected.

    Args:
        text: Document text
        config: Chunking configuration

    Returns:
        List of SemanticChunk objects
    """
    config = config or ChunkingConfig()
    chunks: List[SemanticChunk] = []

    if config.sentence_aware_fallback:
        # Split by sentences
        sentences = LegalPatterns.SENTENCE_END.split(text)
        sentences = [s.strip() for s in sentences if s.strip()]
    else:
        # Use simple character-based splitting
        sentences = [text]

    current_chunk = ""
    chunk_sentences: List[str] = []

    for sentence in sentences:
        # Check if adding this sentence would exceed max
        potential_chunk = current_chunk + " " + sentence if current_chunk else sentence

        if len(potential_chunk) > config.max_chunk_chars and current_chunk:
            # Save current chunk
            if len(current_chunk) >= config.min_chunk_chars:
                chunks.append(SemanticChunk(
                    text=current_chunk.strip(),
                    chunk_type=ChunkType.FALLBACK.value,
                    hierarchy=[],
                ))

            # Start new chunk with overlap
            if config.overlap_chars > 0 and chunk_sentences:
                # Include some previous sentences for overlap
                overlap_text = ""
                for prev_sentence in reversed(chunk_sentences):
                    if len(overlap_text) + len(prev_sentence) < config.overlap_chars:
                        overlap_text = prev_sentence + " " + overlap_text
                    else:
                        break
                current_chunk = overlap_text.strip() + " " + sentence
            else:
                current_chunk = sentence
            chunk_sentences = [sentence]
        else:
            current_chunk = potential_chunk
            chunk_sentences.append(sentence)

    # Save final chunk
    if current_chunk.strip() and len(current_chunk) >= config.min_chunk_chars:
        chunks.append(SemanticChunk(
            text=current_chunk.strip(),
            chunk_type=ChunkType.FALLBACK.value,
            hierarchy=[],
        ))

    # If still no chunks, just return the whole text as one chunk
    if not chunks and text.strip():
        chunks.append(SemanticChunk(
            text=text.strip(),
            chunk_type=ChunkType.FALLBACK.value,
            hierarchy=[],
        ))

    return chunks


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _extract_acordao_id(text: str) -> Optional[str]:
    """Extract court decision identifier from text."""
    # Common patterns for case numbers
    patterns = [
        r'(?:RE|AI|ADI|ADC|ADPF|HC|MS|RMS|RHC|AgRg|EDcl|REsp|RHC|RECURSO)'
        r'[\s]*(?:N[oº\.]?)?[\s]*(\d+[\d\.\-/]*)',
        r'Processo[\s]*(?:N[oº\.]?)?[\s]*:?[\s]*(\d+[\d\.\-/]*)',
        r'Autos[\s]*(?:N[oº\.]?)?[\s]*:?[\s]*(\d+[\d\.\-/]*)',
    ]

    sample = text[:1000]
    for pattern in patterns:
        match = re.search(pattern, sample, re.IGNORECASE)
        if match:
            return match.group(0).strip()

    return None


def _split_large_section(
    content: str,
    section_type: str,
    config: ChunkingConfig,
) -> List[str]:
    """Split a large section into smaller chunks using sentence boundaries."""
    if len(content) <= config.max_chunk_chars:
        return [content]

    # Split by sentences
    sentences = LegalPatterns.SENTENCE_END.split(content)
    sentences = [s.strip() for s in sentences if s.strip()]

    chunks: List[str] = []
    current = ""

    for sentence in sentences:
        if len(current) + len(sentence) + 1 > config.max_chunk_chars and current:
            chunks.append(current.strip())
            # Add overlap
            overlap_text = current[-config.overlap_chars:] if config.overlap_chars > 0 else ""
            current = overlap_text + " " + sentence
        else:
            current = current + " " + sentence if current else sentence

    if current.strip():
        chunks.append(current.strip())

    return chunks if chunks else [content]


def _chunk_acordao_by_paragraphs(
    text: str,
    base_hierarchy: List[str],
    config: ChunkingConfig,
) -> List[SemanticChunk]:
    """Chunk court decision by paragraphs when no structure is found."""
    chunks: List[SemanticChunk] = []

    # Split by double newlines (paragraphs)
    paragraphs = re.split(r'\n\s*\n', text)

    current_text = ""
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        potential = current_text + "\n\n" + para if current_text else para

        if len(potential) > config.max_chunk_chars and current_text:
            chunks.append(SemanticChunk(
                text=current_text.strip(),
                chunk_type=ChunkType.PARAGRAPH.value,
                hierarchy=base_hierarchy.copy(),
            ))
            current_text = para
        else:
            current_text = potential

    if current_text.strip():
        chunks.append(SemanticChunk(
            text=current_text.strip(),
            chunk_type=ChunkType.PARAGRAPH.value,
            hierarchy=base_hierarchy.copy(),
        ))

    return chunks


def _merge_small_chunks(
    chunks: List[SemanticChunk],
    config: ChunkingConfig,
) -> List[SemanticChunk]:
    """Merge chunks that are too small."""
    if not chunks:
        return chunks

    merged: List[SemanticChunk] = []
    current = chunks[0]

    for next_chunk in chunks[1:]:
        # Merge if current is too small and types are compatible
        can_merge = (
            current.char_count < config.min_chunk_chars
            and current.chunk_type == next_chunk.chunk_type
            and current.char_count + next_chunk.char_count <= config.max_chunk_chars
        )

        if can_merge:
            # Merge chunks
            current = SemanticChunk(
                text=current.text + "\n\n" + next_chunk.text,
                chunk_type=current.chunk_type,
                hierarchy=current.hierarchy,
                page=current.page,
                metadata={**current.metadata, **next_chunk.metadata},
            )
        else:
            # Save current and move to next
            if current.char_count >= config.min_chunk_chars:
                merged.append(current)
            elif merged:
                # Merge with previous if too small
                prev = merged[-1]
                if prev.char_count + current.char_count <= config.max_chunk_chars:
                    merged[-1] = SemanticChunk(
                        text=prev.text + "\n\n" + current.text,
                        chunk_type=prev.chunk_type,
                        hierarchy=prev.hierarchy,
                        page=prev.page,
                        metadata={**prev.metadata, **current.metadata},
                    )
                else:
                    merged.append(current)
            else:
                merged.append(current)
            current = next_chunk

    # Handle last chunk
    if current.char_count >= config.min_chunk_chars:
        merged.append(current)
    elif merged:
        prev = merged[-1]
        if prev.char_count + current.char_count <= config.max_chunk_chars:
            merged[-1] = SemanticChunk(
                text=prev.text + "\n\n" + current.text,
                chunk_type=prev.chunk_type,
                hierarchy=prev.hierarchy,
                page=prev.page,
                metadata={**prev.metadata, **current.metadata},
            )
        else:
            merged.append(current)
    else:
        merged.append(current)

    return merged


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def chunk_with_pages(
    pages: List[Tuple[int, str]],
    doc_type: str = "auto",
    config: Optional[ChunkingConfig] = None,
) -> List[SemanticChunk]:
    """
    Chunk a document with page information (e.g., from PDF extraction).

    Args:
        pages: List of (page_number, text) tuples
        doc_type: Document type
        config: Chunking configuration

    Returns:
        List of SemanticChunk objects with page information
    """
    config = config or ChunkingConfig()

    # Combine all text
    full_text = "\n\n".join(text for _, text in pages)

    # Chunk the full document
    chunks = chunk_legal_document(full_text, doc_type, config)

    # Assign page numbers based on text position
    page_boundaries: List[Tuple[int, int, int]] = []  # (start_pos, end_pos, page_num)
    current_pos = 0
    for page_num, text in pages:
        page_boundaries.append((current_pos, current_pos + len(text), page_num))
        current_pos += len(text) + 2  # +2 for \n\n separator

    for chunk in chunks:
        chunk_start = full_text.find(chunk.text[:100])  # Find approximate position
        if chunk_start >= 0:
            for start, end, page_num in page_boundaries:
                if start <= chunk_start < end:
                    chunk.page = page_num
                    break

    return chunks


def get_chunk_statistics(chunks: List[SemanticChunk]) -> Dict[str, Any]:
    """Get statistics about chunked document."""
    if not chunks:
        return {
            "total_chunks": 0,
            "total_chars": 0,
            "avg_chunk_size": 0,
            "chunk_types": {},
        }

    chunk_types: Dict[str, int] = {}
    for chunk in chunks:
        chunk_types[chunk.chunk_type] = chunk_types.get(chunk.chunk_type, 0) + 1

    total_chars = sum(c.char_count for c in chunks)

    return {
        "total_chunks": len(chunks),
        "total_chars": total_chars,
        "avg_chunk_size": total_chars / len(chunks),
        "min_chunk_size": min(c.char_count for c in chunks),
        "max_chunk_size": max(c.char_count for c in chunks),
        "chunk_types": chunk_types,
        "has_hierarchy": any(c.hierarchy for c in chunks),
    }
