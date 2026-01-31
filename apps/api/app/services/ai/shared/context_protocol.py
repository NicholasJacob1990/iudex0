"""
ContextProtocol - Protocolo de contexto (case bundle).

Define estruturas padronizadas para passar contexto de caso
entre os diferentes executors e componentes do sistema.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class DocumentType(str, Enum):
    """Tipo de documento no bundle."""
    PETICAO = "peticao"
    CONTESTACAO = "contestacao"
    SENTENCA = "sentenca"
    ACORDAO = "acordao"
    PARECER = "parecer"
    CONTRATO = "contrato"
    PROCURACAO = "procuracao"
    OUTRO = "outro"


@dataclass
class DocumentReference:
    """
    Referência a um documento no bundle.

    Attributes:
        id: ID único do documento
        title: Título do documento
        doc_type: Tipo do documento
        storage_ref: Referência no storage (S3, local, etc.)
        excerpt: Trecho relevante (preview)
        metadata: Metadados adicionais
    """
    id: str
    title: str
    doc_type: DocumentType = DocumentType.OUTRO
    storage_ref: Optional[str] = None
    excerpt: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "id": self.id,
            "title": self.title,
            "doc_type": self.doc_type.value,
            "storage_ref": self.storage_ref,
            "excerpt": self.excerpt,
            "metadata": self.metadata
        }


@dataclass
class CaseParty:
    """
    Parte do processo.

    Attributes:
        name: Nome da parte
        role: Papel (autor, réu, terceiro, etc.)
        cpf_cnpj: CPF ou CNPJ (opcional)
        lawyer: Advogado responsável
    """
    name: str
    role: str
    cpf_cnpj: Optional[str] = None
    lawyer: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "name": self.name,
            "role": self.role,
            "cpf_cnpj": self.cpf_cnpj,
            "lawyer": self.lawyer
        }


@dataclass
class CaseBundle:
    """
    Bundle de contexto do caso.

    Contém todas as informações relevantes do caso para
    processamento pelos agentes de IA.

    Attributes:
        case_id: ID único do caso
        case_number: Número do processo
        court: Tribunal/vara
        subject: Assunto/tipo da ação
        parties: Partes envolvidas
        documents: Documentos do caso
        facts: Fatos relevantes
        legal_grounds: Fundamentos jurídicos
        requests: Pedidos
        metadata: Metadados adicionais
    """
    case_id: str
    case_number: Optional[str] = None
    court: Optional[str] = None
    subject: Optional[str] = None
    parties: List[CaseParty] = field(default_factory=list)
    documents: List[DocumentReference] = field(default_factory=list)
    facts: List[str] = field(default_factory=list)
    legal_grounds: List[str] = field(default_factory=list)
    requests: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário serializável."""
        return {
            "case_id": self.case_id,
            "case_number": self.case_number,
            "court": self.court,
            "subject": self.subject,
            "parties": [p.to_dict() for p in self.parties],
            "documents": [d.to_dict() for d in self.documents],
            "facts": self.facts,
            "legal_grounds": self.legal_grounds,
            "requests": self.requests,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CaseBundle":
        """
        Cria CaseBundle a partir de dicionário.

        Args:
            data: Dicionário com dados do bundle

        Returns:
            Instância de CaseBundle
        """
        parties = [
            CaseParty(**p) if isinstance(p, dict) else p
            for p in data.get("parties", [])
        ]

        documents = [
            DocumentReference(
                id=d["id"],
                title=d["title"],
                doc_type=DocumentType(d.get("doc_type", "outro")),
                storage_ref=d.get("storage_ref"),
                excerpt=d.get("excerpt"),
                metadata=d.get("metadata", {})
            ) if isinstance(d, dict) else d
            for d in data.get("documents", [])
        ]

        return cls(
            case_id=data["case_id"],
            case_number=data.get("case_number"),
            court=data.get("court"),
            subject=data.get("subject"),
            parties=parties,
            documents=documents,
            facts=data.get("facts", []),
            legal_grounds=data.get("legal_grounds", []),
            requests=data.get("requests", []),
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.utcnow()
        )

    def get_summary(self, max_length: int = 500) -> str:
        """
        Gera resumo do caso para contexto.

        Args:
            max_length: Tamanho máximo do resumo

        Returns:
            Resumo textual do caso
        """
        parts = []

        if self.case_number:
            parts.append(f"Processo: {self.case_number}")

        if self.court:
            parts.append(f"Juízo: {self.court}")

        if self.subject:
            parts.append(f"Assunto: {self.subject}")

        if self.parties:
            party_str = ", ".join([f"{p.name} ({p.role})" for p in self.parties[:4]])
            parts.append(f"Partes: {party_str}")

        if self.facts:
            facts_preview = "; ".join(self.facts[:3])
            parts.append(f"Fatos: {facts_preview[:200]}")

        summary = " | ".join(parts)
        return summary[:max_length] if len(summary) > max_length else summary

    def add_document(self, doc: DocumentReference) -> None:
        """Adiciona documento ao bundle."""
        self.documents.append(doc)

    def add_party(self, party: CaseParty) -> None:
        """Adiciona parte ao bundle."""
        self.parties.append(party)


class ContextProtocol:
    """
    Protocolo para gerenciamento de contexto.

    Fornece métodos utilitários para manipular e validar
    contexto de caso entre componentes.
    """

    @staticmethod
    def validate_bundle(bundle: CaseBundle) -> List[str]:
        """
        Valida um CaseBundle.

        Args:
            bundle: Bundle a validar

        Returns:
            Lista de erros (vazia se válido)
        """
        errors = []

        if not bundle.case_id:
            errors.append("case_id é obrigatório")

        if bundle.parties and not all(p.name and p.role for p in bundle.parties):
            errors.append("Todas as partes devem ter nome e role")

        if bundle.documents and not all(d.id and d.title for d in bundle.documents):
            errors.append("Todos os documentos devem ter id e title")

        return errors

    @staticmethod
    def merge_bundles(base: CaseBundle, overlay: CaseBundle) -> CaseBundle:
        """
        Merge dois bundles, sobrescrevendo com overlay.

        Args:
            base: Bundle base
            overlay: Bundle com dados a sobrescrever

        Returns:
            Novo CaseBundle merged
        """
        return CaseBundle(
            case_id=overlay.case_id or base.case_id,
            case_number=overlay.case_number or base.case_number,
            court=overlay.court or base.court,
            subject=overlay.subject or base.subject,
            parties=overlay.parties if overlay.parties else base.parties,
            documents=base.documents + overlay.documents,
            facts=base.facts + overlay.facts,
            legal_grounds=base.legal_grounds + overlay.legal_grounds,
            requests=base.requests + overlay.requests,
            metadata={**base.metadata, **overlay.metadata}
        )

    @staticmethod
    def extract_context_for_prompt(
        bundle: CaseBundle,
        include_documents: bool = True,
        max_doc_excerpts: int = 5
    ) -> str:
        """
        Extrai contexto formatado para prompt de LLM.

        Args:
            bundle: Bundle de contexto
            include_documents: Se deve incluir excerpts de documentos
            max_doc_excerpts: Máximo de excerpts a incluir

        Returns:
            Texto formatado para inclusão em prompt
        """
        sections = []

        # Informações básicas
        sections.append("=== CONTEXTO DO CASO ===")
        sections.append(bundle.get_summary())

        # Partes
        if bundle.parties:
            sections.append("\n--- PARTES ---")
            for party in bundle.parties:
                lawyer_info = f" (Adv: {party.lawyer})" if party.lawyer else ""
                sections.append(f"- {party.name}: {party.role}{lawyer_info}")

        # Fatos
        if bundle.facts:
            sections.append("\n--- FATOS RELEVANTES ---")
            for i, fact in enumerate(bundle.facts, 1):
                sections.append(f"{i}. {fact}")

        # Fundamentos
        if bundle.legal_grounds:
            sections.append("\n--- FUNDAMENTOS JURÍDICOS ---")
            for ground in bundle.legal_grounds:
                sections.append(f"- {ground}")

        # Pedidos
        if bundle.requests:
            sections.append("\n--- PEDIDOS ---")
            for request in bundle.requests:
                sections.append(f"- {request}")

        # Documentos
        if include_documents and bundle.documents:
            sections.append("\n--- DOCUMENTOS ---")
            for doc in bundle.documents[:max_doc_excerpts]:
                sections.append(f"\n[{doc.title}] ({doc.doc_type.value})")
                if doc.excerpt:
                    sections.append(f"Trecho: {doc.excerpt[:300]}...")

        return "\n".join(sections)
