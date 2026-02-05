"""
RedlineService — Geracao de redlines OOXML com tracked changes para Word.

Gera tracked changes OOXML validos (w:ins, w:del) com comentarios
para integracao direta com o painel de revisao do Word 2016+.

Funcionalidades:
- Geracao de redlines OOXML a partir de analise de playbook
- Aplicacao/rejeicao individual e em batch
- Comentarios com bubble no painel de comentarios do Word
- Compativel com Word Desktop e Word Online (via Office.js insertOoxml)
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from xml.sax.saxutils import escape as xml_escape

from app.schemas.playbook_analysis import (
    ClauseAnalysisResult,
    ClauseClassification,
    AnalysisSeverity,
)

logger = logging.getLogger("RedlineService")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AUTHOR = "Iudex AI"
OOXML_NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pkg": "http://schemas.microsoft.com/office/2006/xmlPackage",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
    "w15": "http://schemas.microsoft.com/office/word/2012/wordml",
}

# Severity label mapping
SEVERITY_LABELS = {
    "low": "Baixa",
    "medium": "Media",
    "high": "Alta",
    "critical": "Critica",
}

# Classification label mapping
CLASSIFICATION_LABELS = {
    "compliant": "Conforme",
    "needs_review": "Necessita Revisao",
    "non_compliant": "Nao Conforme",
    "not_found": "Nao Encontrada",
}


# ---------------------------------------------------------------------------
# Redline Data Types
# ---------------------------------------------------------------------------


class RedlineItem:
    """Representa um redline individual com metadados."""

    def __init__(
        self,
        redline_id: str,
        rule_id: str,
        rule_name: str,
        clause_type: str,
        classification: str,
        severity: str,
        original_text: str,
        suggested_text: str,
        explanation: str,
        comment: Optional[str] = None,
        confidence: float = 0.0,
    ):
        self.redline_id = redline_id
        self.rule_id = rule_id
        self.rule_name = rule_name
        self.clause_type = clause_type
        self.classification = classification
        self.severity = severity
        self.original_text = original_text
        self.suggested_text = suggested_text
        self.explanation = explanation
        self.comment = comment
        self.confidence = confidence
        self.applied = False
        self.rejected = False
        self.reviewed = False
        self.created_at = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "redline_id": self.redline_id,
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "clause_type": self.clause_type,
            "classification": self.classification,
            "severity": self.severity,
            "original_text": self.original_text,
            "suggested_text": self.suggested_text,
            "explanation": self.explanation,
            "comment": self.comment,
            "confidence": self.confidence,
            "applied": self.applied,
            "rejected": self.rejected,
            "reviewed": self.reviewed,
            "created_at": self.created_at.isoformat(),
        }


# ---------------------------------------------------------------------------
# OOXML Generation Helpers
# ---------------------------------------------------------------------------


def _escape_xml(text: str) -> str:
    """Escape XML special characters."""
    return xml_escape(text, entities={"'": "&apos;", '"': "&quot;"})


def _generate_rsid() -> str:
    """Generate a unique RSID for OOXML elements."""
    return hashlib.md5(uuid.uuid4().bytes).hexdigest()[:8].upper()


def _now_iso() -> str:
    """Return current UTC datetime in ISO format for OOXML."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _split_into_runs(text: str) -> List[str]:
    """Split text into paragraph-safe runs (split on newlines)."""
    parts = re.split(r"(\r?\n)", text)
    return [p for p in parts if p]


def _build_run_elements(text: str, tag: str = "w:t") -> str:
    """Build w:r elements from text, handling newlines as w:br."""
    runs = []
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if line.strip() or line:
            safe_text = _escape_xml(line)
            runs.append(
                f'<w:r><{tag} xml:space="preserve">{safe_text}</{tag}></w:r>'
            )
        if i < len(lines) - 1:
            runs.append("<w:r><w:br/></w:r>")
    return "".join(runs)


# ---------------------------------------------------------------------------
# OOXML Tracked Change Builders
# ---------------------------------------------------------------------------


def build_deletion_ooxml(
    original_text: str,
    change_id: int = 1,
    author: str = AUTHOR,
    date: Optional[str] = None,
) -> str:
    """Build w:del OOXML element for deleted text (strikethrough red)."""
    date = date or _now_iso()
    safe_text = _escape_xml(original_text)
    return (
        f'<w:del w:id="{change_id}" w:author="{_escape_xml(author)}" w:date="{date}">'
        f'<w:r><w:rPr><w:strike/><w:color w:val="FF0000"/></w:rPr>'
        f'<w:delText xml:space="preserve">{safe_text}</w:delText></w:r>'
        f"</w:del>"
    )


def build_insertion_ooxml(
    new_text: str,
    change_id: int = 2,
    author: str = AUTHOR,
    date: Optional[str] = None,
) -> str:
    """Build w:ins OOXML element for inserted text (underline blue)."""
    date = date or _now_iso()
    safe_text = _escape_xml(new_text)
    return (
        f'<w:ins w:id="{change_id}" w:author="{_escape_xml(author)}" w:date="{date}">'
        f'<w:r><w:rPr><w:u w:val="single"/><w:color w:val="0000FF"/></w:rPr>'
        f'<w:t xml:space="preserve">{safe_text}</w:t></w:r>'
        f"</w:ins>"
    )


def build_comment_ooxml(
    comment_id: int,
    comment_text: str,
    author: str = AUTHOR,
    date: Optional[str] = None,
    initials: str = "IA",
) -> str:
    """Build w:comment element for the comments part."""
    date = date or _now_iso()
    safe_text = _escape_xml(comment_text)
    return (
        f'<w:comment w:id="{comment_id}" w:author="{_escape_xml(author)}" '
        f'w:date="{date}" w:initials="{initials}">'
        f"<w:p><w:r><w:t>{safe_text}</w:t></w:r></w:p>"
        f"</w:comment>"
    )


def build_comment_range_start(comment_id: int) -> str:
    """Build w:commentRangeStart element."""
    return f'<w:commentRangeStart w:id="{comment_id}"/>'


def build_comment_range_end(comment_id: int) -> str:
    """Build w:commentRangeEnd element."""
    return f'<w:commentRangeEnd w:id="{comment_id}"/>'


def build_comment_reference(comment_id: int) -> str:
    """Build w:commentReference run element."""
    return (
        f"<w:r><w:rPr><w:rStyle w:val=\"CommentReference\"/></w:rPr>"
        f'<w:commentReference w:id="{comment_id}"/></w:r>'
    )


# ---------------------------------------------------------------------------
# Full Tracked Change with Comment
# ---------------------------------------------------------------------------


def build_redline_paragraph_ooxml(
    original_text: str,
    new_text: str,
    comment_text: str,
    del_id: int = 1,
    ins_id: int = 2,
    comment_id: int = 1,
    author: str = AUTHOR,
    date: Optional[str] = None,
) -> str:
    """
    Build a complete paragraph with tracked change (delete + insert) and comment.

    The comment range wraps both the deletion and insertion so the
    comment bubble appears in the Review pane linked to the change.
    """
    date = date or _now_iso()

    deletion = build_deletion_ooxml(original_text, del_id, author, date)
    insertion = build_insertion_ooxml(new_text, ins_id, author, date)
    range_start = build_comment_range_start(comment_id)
    range_end = build_comment_range_end(comment_id)
    comment_ref = build_comment_reference(comment_id)

    return (
        f"<w:p>"
        f"{range_start}"
        f"{deletion}"
        f"{insertion}"
        f"{range_end}"
        f"{comment_ref}"
        f"</w:p>"
    )


# ---------------------------------------------------------------------------
# Full OOXML Package Builder
# ---------------------------------------------------------------------------


def build_redline_ooxml_package(
    redline_items: List[RedlineItem],
    include_comments: bool = True,
) -> str:
    """
    Build a complete OOXML package with tracked changes and comments.

    This generates a valid pkg:package that can be inserted via
    Office.js insertOoxml() or used to replace document content.

    Args:
        redline_items: List of RedlineItem objects to include
        include_comments: Whether to include comment part

    Returns:
        Complete OOXML pkg:package string
    """
    date = _now_iso()
    rsid = _generate_rsid()

    # Build body paragraphs and comments
    body_paragraphs = []
    comments = []
    change_counter = 1
    comment_counter = 1

    for item in redline_items:
        if item.applied or item.rejected:
            continue

        if not item.original_text or not item.suggested_text:
            continue

        del_id = change_counter
        change_counter += 1
        ins_id = change_counter
        change_counter += 1
        cmt_id = comment_counter
        comment_counter += 1

        # Build comment text
        comment_parts = []
        comment_parts.append(f"[{item.rule_name}]")
        severity_label = SEVERITY_LABELS.get(item.severity, item.severity)
        classification_label = CLASSIFICATION_LABELS.get(
            item.classification, item.classification
        )
        comment_parts.append(f"Severidade: {severity_label}")
        comment_parts.append(f"Classificacao: {classification_label}")
        if item.explanation:
            comment_parts.append(f"Motivo: {item.explanation}")
        if item.comment:
            comment_parts.append(f"Nota: {item.comment}")
        comment_text = " | ".join(comment_parts)

        # Build paragraph with tracked change
        paragraph = build_redline_paragraph_ooxml(
            original_text=item.original_text,
            new_text=item.suggested_text,
            comment_text=comment_text,
            del_id=del_id,
            ins_id=ins_id,
            comment_id=cmt_id,
            author=AUTHOR,
            date=date,
        )
        body_paragraphs.append(paragraph)

        # Build comment entry
        if include_comments:
            comment = build_comment_ooxml(
                comment_id=cmt_id,
                comment_text=comment_text,
                author=AUTHOR,
                date=date,
            )
            comments.append(comment)

    body_content = "\n".join(body_paragraphs)
    comments_content = "\n".join(comments)

    # Build the full package
    comments_part = ""
    comments_rel = ""
    if include_comments and comments:
        comments_rel = (
            '<Relationship Id="rId2" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments" '
            'Target="comments.xml"/>'
        )
        comments_part = f"""
  <pkg:part pkg:name="/word/comments.xml" pkg:contentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml">
    <pkg:xmlData>
      <w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
        {comments_content}
      </w:comments>
    </pkg:xmlData>
  </pkg:part>"""

    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<pkg:package xmlns:pkg="http://schemas.microsoft.com/office/2006/xmlPackage">
  <pkg:part pkg:name="/_rels/.rels" pkg:contentType="application/vnd.openxmlformats-package.relationships+xml">
    <pkg:xmlData>
      <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
        <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
      </Relationships>
    </pkg:xmlData>
  </pkg:part>
  <pkg:part pkg:name="/word/_rels/document.xml.rels" pkg:contentType="application/vnd.openxmlformats-package.relationships+xml">
    <pkg:xmlData>
      <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
        {comments_rel}
      </Relationships>
    </pkg:xmlData>
  </pkg:part>
  <pkg:part pkg:name="/word/document.xml" pkg:contentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml">
    <pkg:xmlData>
      <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
                  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
        <w:body>
          {body_content}
        </w:body>
      </w:document>
    </pkg:xmlData>
  </pkg:part>{comments_part}
</pkg:package>"""


def build_single_redline_ooxml(
    original_text: str,
    new_text: str,
    comment_text: str,
    author: str = AUTHOR,
) -> str:
    """
    Build OOXML for a single tracked change (replace) with comment.

    Used by the frontend to apply one redline at a time via insertOoxml().
    """
    date = _now_iso()

    del_ooxml = build_deletion_ooxml(original_text, 1, author, date)
    ins_ooxml = build_insertion_ooxml(new_text, 2, author, date)
    range_start = build_comment_range_start(1)
    range_end = build_comment_range_end(1)
    comment_ref = build_comment_reference(1)
    comment_entry = build_comment_ooxml(1, comment_text, author, date)

    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<pkg:package xmlns:pkg="http://schemas.microsoft.com/office/2006/xmlPackage">
  <pkg:part pkg:name="/_rels/.rels" pkg:contentType="application/vnd.openxmlformats-package.relationships+xml">
    <pkg:xmlData>
      <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
        <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
      </Relationships>
    </pkg:xmlData>
  </pkg:part>
  <pkg:part pkg:name="/word/_rels/document.xml.rels" pkg:contentType="application/vnd.openxmlformats-package.relationships+xml">
    <pkg:xmlData>
      <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
        <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments" Target="comments.xml"/>
      </Relationships>
    </pkg:xmlData>
  </pkg:part>
  <pkg:part pkg:name="/word/document.xml" pkg:contentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml">
    <pkg:xmlData>
      <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
                  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
        <w:body>
          <w:p>
            {range_start}
            {del_ooxml}
            {ins_ooxml}
            {range_end}
            {comment_ref}
          </w:p>
        </w:body>
      </w:document>
    </pkg:xmlData>
  </pkg:part>
  <pkg:part pkg:name="/word/comments.xml" pkg:contentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml">
    <pkg:xmlData>
      <w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
        {comment_entry}
      </w:comments>
    </pkg:xmlData>
  </pkg:part>
</pkg:package>"""


# ---------------------------------------------------------------------------
# RedlineService
# ---------------------------------------------------------------------------


class RedlineService:
    """
    Servico para geracao e gerenciamento de redlines OOXML.

    Integra com PlaybookService para executar playbooks no Word
    e gerar tracked changes com comentarios.
    """

    def generate_redlines_from_analysis(
        self,
        clause_results: List[ClauseAnalysisResult],
    ) -> List[RedlineItem]:
        """
        Converte resultados de analise de playbook em RedlineItems.

        Filtra apenas clausulas nao-conformes e needs_review que
        possuem suggested_redline.

        Args:
            clause_results: Lista de ClauseAnalysisResult do PlaybookService

        Returns:
            Lista de RedlineItem prontos para geracao OOXML
        """
        redlines: List[RedlineItem] = []

        for clause in clause_results:
            # Skip compliant and not_found without suggestion
            if clause.classification == ClauseClassification.COMPLIANT:
                continue

            if not clause.suggested_redline or not clause.original_text:
                continue

            redline = RedlineItem(
                redline_id=str(uuid.uuid4()),
                rule_id=clause.rule_id,
                rule_name=clause.rule_name,
                clause_type=clause.clause_type,
                classification=clause.classification.value
                if hasattr(clause.classification, "value")
                else str(clause.classification),
                severity=clause.severity.value
                if hasattr(clause.severity, "value")
                else str(clause.severity),
                original_text=clause.original_text,
                suggested_text=clause.suggested_redline,
                explanation=clause.explanation,
                comment=clause.comment,
                confidence=clause.confidence,
            )
            redlines.append(redline)

        logger.info(
            "Gerados %d redlines de %d clausulas analisadas",
            len(redlines),
            len(clause_results),
        )
        return redlines

    def generate_ooxml_redlines(
        self,
        redline_items: List[RedlineItem],
        include_comments: bool = True,
    ) -> str:
        """
        Gera OOXML completo com tracked changes e comentarios.

        Args:
            redline_items: Lista de RedlineItems
            include_comments: Se deve incluir comentarios no OOXML

        Returns:
            String OOXML pkg:package valida
        """
        return build_redline_ooxml_package(redline_items, include_comments)

    def generate_single_redline_ooxml(
        self,
        redline: RedlineItem,
    ) -> str:
        """
        Gera OOXML para um unico redline com comentario.

        Args:
            redline: RedlineItem individual

        Returns:
            String OOXML pkg:package para inserir via Office.js
        """
        comment_parts = [f"[{redline.rule_name}]"]
        severity_label = SEVERITY_LABELS.get(redline.severity, redline.severity)
        classification_label = CLASSIFICATION_LABELS.get(
            redline.classification, redline.classification
        )
        comment_parts.append(f"Severidade: {severity_label}")
        comment_parts.append(f"Classificacao: {classification_label}")
        if redline.explanation:
            comment_parts.append(f"Motivo: {redline.explanation}")

        comment_text = " | ".join(comment_parts)

        return build_single_redline_ooxml(
            original_text=redline.original_text,
            new_text=redline.suggested_text,
            comment_text=comment_text,
        )

    async def run_playbook_on_word_document(
        self,
        document_content: str,
        playbook_id: str,
        user_id: str,
        db=None,
    ) -> Dict[str, Any]:
        """
        Executa playbook completo no documento Word e retorna redlines.

        Fluxo:
        1. Chama PlaybookService para analisar o conteudo
        2. Converte resultados em RedlineItems
        3. Gera OOXML para cada redline
        4. Retorna resultado completo com redlines, classificacoes, comentarios

        Args:
            document_content: Texto ou OOXML do documento Word
            playbook_id: ID do playbook a executar
            user_id: ID do usuario
            db: Sessao do banco de dados

        Returns:
            Dict com redlines, stats, summary, ooxml_package
        """
        from app.services.playbook_service import PlaybookService

        playbook_svc = PlaybookService()

        # Load playbook info
        playbook = await playbook_svc._load_playbook(playbook_id, db)
        rules = await playbook_svc._load_playbook_rules(playbook_id, db)

        if not rules:
            return {
                "success": False,
                "error": "Playbook sem regras ativas",
                "redlines": [],
                "stats": {},
                "summary": "",
            }

        # Extract clauses
        extracted_clauses = await playbook_svc._extract_clauses(document_content)

        # Analyze all rules
        clause_results = await playbook_svc._analyze_all_rules(
            rules=rules,
            extracted_clauses=extracted_clauses,
            contract_text=document_content,
            party_perspective=getattr(playbook, "party_perspective", "neutro") or "neutro",
        )

        # Generate redlines for non-compliant
        rules_by_id = {r.id: r for r in rules}
        clause_results = await playbook_svc._generate_redlines_for_non_compliant(
            clause_results=clause_results,
            rules_by_id=rules_by_id,
        )

        # Convert to RedlineItems
        redline_items = self.generate_redlines_from_analysis(clause_results)

        # Generate OOXML for each redline
        redlines_with_ooxml = []
        for item in redline_items:
            ooxml = self.generate_single_redline_ooxml(item)
            redline_dict = item.to_dict()
            redline_dict["ooxml"] = ooxml
            redlines_with_ooxml.append(redline_dict)

        # Calculate stats
        compliant = sum(
            1 for c in clause_results
            if c.classification == ClauseClassification.COMPLIANT
        )
        needs_review = sum(
            1 for c in clause_results
            if c.classification == ClauseClassification.NEEDS_REVIEW
        )
        non_compliant = sum(
            1 for c in clause_results
            if c.classification == ClauseClassification.NON_COMPLIANT
        )
        not_found = sum(
            1 for c in clause_results
            if c.classification == ClauseClassification.NOT_FOUND
        )

        # Risk score
        from app.services.playbook_service import _calculate_risk_score

        risk_score = _calculate_risk_score(clause_results)

        # Generate summary
        summary = await playbook_svc._generate_summary(
            playbook_name=playbook.name,
            total_rules=len(rules),
            compliant=compliant,
            needs_review=needs_review,
            non_compliant=non_compliant,
            not_found=not_found,
            risk_score=risk_score,
            clause_results=clause_results,
        )

        # Build full OOXML package with all redlines
        ooxml_package = self.generate_ooxml_redlines(redline_items)

        # Build clause results for frontend
        clauses_data = []
        for c in clause_results:
            clause_dict = {
                "rule_id": c.rule_id,
                "rule_name": c.rule_name,
                "clause_type": c.clause_type,
                "found_in_contract": c.found_in_contract,
                "original_text": c.original_text,
                "classification": c.classification.value
                if hasattr(c.classification, "value")
                else str(c.classification),
                "severity": c.severity.value
                if hasattr(c.severity, "value")
                else str(c.severity),
                "explanation": c.explanation,
                "suggested_redline": c.suggested_redline,
                "comment": c.comment,
                "confidence": c.confidence,
            }
            # Find matching redline
            matching_redline = next(
                (r for r in redline_items if r.rule_id == c.rule_id), None
            )
            if matching_redline:
                clause_dict["redline_id"] = matching_redline.redline_id
            clauses_data.append(clause_dict)

        return {
            "success": True,
            "playbook_id": playbook_id,
            "playbook_name": playbook.name,
            "redlines": redlines_with_ooxml,
            "clauses": clauses_data,
            "stats": {
                "total_rules": len(rules),
                "compliant": compliant,
                "needs_review": needs_review,
                "non_compliant": non_compliant,
                "not_found": not_found,
                "risk_score": risk_score,
                "total_redlines": len(redline_items),
            },
            "summary": summary,
            "ooxml_package": ooxml_package,
        }

    def apply_single_redline(
        self,
        redline_items: List[RedlineItem],
        redline_id: str,
    ) -> Optional[str]:
        """
        Retorna OOXML para aplicar um redline especifico.

        Args:
            redline_items: Lista de RedlineItems da sessao
            redline_id: ID do redline a aplicar

        Returns:
            String OOXML ou None se nao encontrado
        """
        for item in redline_items:
            if item.redline_id == redline_id:
                if item.applied or item.rejected:
                    return None
                item.applied = True
                return self.generate_single_redline_ooxml(item)
        return None

    def apply_all_redlines(
        self,
        redline_items: List[RedlineItem],
        redline_ids: Optional[List[str]] = None,
    ) -> str:
        """
        Retorna OOXML para aplicar todos os redlines (ou subset).

        Args:
            redline_items: Lista de RedlineItems da sessao
            redline_ids: IDs especificos para aplicar (None = todos)

        Returns:
            String OOXML com todos os tracked changes
        """
        items_to_apply = []
        for item in redline_items:
            if item.applied or item.rejected:
                continue
            if redline_ids and item.redline_id not in redline_ids:
                continue
            item.applied = True
            items_to_apply.append(item)

        return self.generate_ooxml_redlines(items_to_apply)

    def reject_redline(
        self,
        redline_items: List[RedlineItem],
        redline_id: str,
    ) -> bool:
        """
        Marca um redline como rejeitado (nao sera aplicado).

        Args:
            redline_items: Lista de RedlineItems
            redline_id: ID do redline a rejeitar

        Returns:
            True se encontrado e rejeitado, False caso contrario
        """
        for item in redline_items:
            if item.redline_id == redline_id:
                item.rejected = True
                item.reviewed = True
                return True
        return False


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

redline_service = RedlineService()
