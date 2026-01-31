"""
Document Editor Tools for Claude Agent SDK

Tools para leitura e edição de documentos jurídicos.
Permite ao agente ler, editar e criar seções em documentos do caso.

v1.0 - 2026-01-26
"""

import asyncio
import hashlib
from typing import Any, Dict, List, Optional, Literal
from datetime import datetime
from loguru import logger


# =============================================================================
# TOOL SCHEMAS (Anthropic Tool Use Format)
# =============================================================================

READ_DOCUMENT_SCHEMA = {
    "name": "read_document",
    "description": """Lê o conteúdo de um documento do caso.

    Use para:
    - Ler documentos anexados ao caso (petições, contratos, etc.)
    - Consultar seções específicas do documento em elaboração
    - Obter contexto para análise ou edição

    Retorna o texto do documento ou seção especificada.""",
    "input_schema": {
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "ID do documento a ler. Use 'current' para o documento em elaboração."
            },
            "page_range": {
                "type": "object",
                "properties": {
                    "start": {
                        "type": "integer",
                        "description": "Página inicial (1-indexed)"
                    },
                    "end": {
                        "type": "integer",
                        "description": "Página final (1-indexed)"
                    }
                },
                "description": "Range de páginas para ler. Se não especificado, lê todo o documento."
            },
            "section_id": {
                "type": "string",
                "description": "ID ou título da seção específica para ler"
            },
            "format": {
                "type": "string",
                "enum": ["text", "markdown", "html"],
                "description": "Formato de retorno do conteúdo",
                "default": "markdown"
            }
        },
        "required": ["document_id"]
    }
}

EDIT_DOCUMENT_SCHEMA = {
    "name": "edit_document",
    "description": """Edita uma seção do documento em elaboração.

    IMPORTANTE: Esta ferramenta modifica o documento. Será solicitada
    aprovação do usuário antes de aplicar a edição.

    Use para:
    - Corrigir erros no texto
    - Reformular argumentos jurídicos
    - Adicionar citações e referências
    - Ajustar formatação

    A edição preserva a estrutura do documento e mantém histórico.""",
    "input_schema": {
        "type": "object",
        "properties": {
            "section_id": {
                "type": "string",
                "description": "ID ou título da seção a editar"
            },
            "new_content": {
                "type": "string",
                "description": "Novo conteúdo da seção em Markdown"
            },
            "edit_type": {
                "type": "string",
                "enum": ["replace", "append", "prepend", "insert"],
                "description": "Tipo de edição: substituir, adicionar no fim, adicionar no início, inserir em posição",
                "default": "replace"
            },
            "insert_position": {
                "type": "integer",
                "description": "Posição de inserção (usado com edit_type='insert')"
            },
            "reason": {
                "type": "string",
                "description": "Motivo da edição (para histórico e revisão)"
            },
            "preserve_formatting": {
                "type": "boolean",
                "description": "Se True, tenta preservar formatação original",
                "default": True
            }
        },
        "required": ["section_id", "new_content"]
    }
}

CREATE_SECTION_SCHEMA = {
    "name": "create_section",
    "description": """Cria uma nova seção no documento em elaboração.

    IMPORTANTE: Esta ferramenta modifica o documento. Será solicitada
    aprovação do usuário antes de criar a seção.

    Use para:
    - Adicionar novas seções de argumentação
    - Criar tópicos adicionais
    - Inserir seções de fundamentação

    A seção será inserida na posição especificada, mantendo a estrutura.""",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Título da nova seção"
            },
            "content": {
                "type": "string",
                "description": "Conteúdo da seção em Markdown"
            },
            "position": {
                "type": "string",
                "enum": ["beginning", "end", "after", "before"],
                "description": "Posição da seção: início, fim, após ou antes de outra seção",
                "default": "end"
            },
            "reference_section_id": {
                "type": "string",
                "description": "ID da seção de referência (para position='after' ou 'before')"
            },
            "level": {
                "type": "integer",
                "description": "Nível hierárquico da seção (1=principal, 2=subseção, etc.)",
                "default": 1,
                "minimum": 1,
                "maximum": 6
            },
            "section_type": {
                "type": "string",
                "enum": [
                    "ementa",
                    "fatos",
                    "direito",
                    "fundamentacao",
                    "jurisprudencia",
                    "pedido",
                    "conclusao",
                    "preliminar",
                    "merito",
                    "custom"
                ],
                "description": "Tipo semântico da seção",
                "default": "custom"
            }
        },
        "required": ["title", "content"]
    }
}


# =============================================================================
# DOCUMENT STORE INTERFACE
# =============================================================================

class DocumentContext:
    """Contexto de documento para o agente."""

    def __init__(
        self,
        case_id: Optional[str] = None,
        job_id: Optional[str] = None,
        tenant_id: str = "default",
        user_id: Optional[str] = None,
    ):
        self.case_id = case_id
        self.job_id = job_id
        self.tenant_id = tenant_id
        self.user_id = user_id
        self._current_document: Optional[Dict[str, Any]] = None
        self._documents: Dict[str, Dict[str, Any]] = {}
        self._edit_history: List[Dict[str, Any]] = []

    def set_current_document(self, document: Dict[str, Any]):
        """Define o documento atual em elaboração."""
        self._current_document = document

    def get_current_document(self) -> Optional[Dict[str, Any]]:
        """Retorna o documento atual."""
        return self._current_document

    def add_document(self, doc_id: str, document: Dict[str, Any]):
        """Adiciona um documento ao contexto."""
        self._documents[doc_id] = document

    def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Retorna um documento pelo ID."""
        if doc_id == "current":
            return self._current_document
        return self._documents.get(doc_id)

    def record_edit(self, edit: Dict[str, Any]):
        """Registra uma edição no histórico."""
        edit["timestamp"] = datetime.now().isoformat()
        edit["edit_id"] = hashlib.md5(
            f"{edit.get('section_id')}:{edit.get('timestamp')}".encode()
        ).hexdigest()[:12]
        self._edit_history.append(edit)

    def get_edit_history(self) -> List[Dict[str, Any]]:
        """Retorna histórico de edições."""
        return self._edit_history


# Contexto global (será injetado pelo executor)
_document_context: Optional[DocumentContext] = None


def get_document_context() -> DocumentContext:
    """Retorna o contexto de documento atual."""
    global _document_context
    if _document_context is None:
        _document_context = DocumentContext()
    return _document_context


def set_document_context(ctx: DocumentContext):
    """Define o contexto de documento."""
    global _document_context
    _document_context = ctx


# =============================================================================
# TOOL IMPLEMENTATIONS
# =============================================================================

async def read_document(
    document_id: str,
    page_range: Optional[Dict[str, int]] = None,
    section_id: Optional[str] = None,
    format: str = "markdown",
    # Contexto do caso (injetado pelo executor)
    case_id: Optional[str] = None,
    tenant_id: str = "default",
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Lê o conteúdo de um documento do caso.

    Args:
        document_id: ID do documento ou 'current' para documento em elaboração
        page_range: Dict com 'start' e 'end' para range de páginas
        section_id: ID ou título da seção específica
        format: Formato de retorno (text, markdown, html)
        case_id: ID do caso
        tenant_id: Tenant para multi-tenancy
        user_id: ID do usuário para RBAC

    Returns:
        Dict com conteúdo do documento
    """
    logger.info(f"[read_document] doc_id={document_id}, section={section_id}")

    ctx = get_document_context()

    # 1. Buscar documento
    document = ctx.get_document(document_id)

    if document is None and document_id != "current":
        # Tentar buscar do DocumentStore do Iudex
        try:
            from app.services.ai.document_store import document_store

            doc_data = await document_store.get_document(
                document_id=document_id,
                tenant_id=tenant_id,
            )
            if doc_data:
                document = doc_data
                ctx.add_document(document_id, document)
        except Exception as e:
            logger.warning(f"[read_document] DocumentStore falhou: {e}")

    if document is None:
        return {
            "success": False,
            "error": f"Documento '{document_id}' não encontrado",
            "document_id": document_id,
        }

    # 2. Extrair conteúdo
    content = document.get("content", "")
    sections = document.get("sections", [])
    metadata = document.get("metadata", {})

    # Filtrar por seção
    if section_id:
        section_content = _find_section(sections, section_id) or _extract_section_from_text(content, section_id)
        if section_content:
            content = section_content
        else:
            return {
                "success": False,
                "error": f"Seção '{section_id}' não encontrada no documento",
                "document_id": document_id,
                "available_sections": [s.get("title") or s.get("id") for s in sections],
            }

    # Filtrar por páginas
    if page_range:
        start = page_range.get("start", 1)
        end = page_range.get("end")
        content = _extract_page_range(content, start, end)

    # Formatar conteúdo
    if format == "text":
        content = _markdown_to_text(content)
    elif format == "html":
        content = _markdown_to_html(content)

    return {
        "success": True,
        "document_id": document_id,
        "title": document.get("title", ""),
        "content": content,
        "sections": [{"id": s.get("id"), "title": s.get("title")} for s in sections],
        "metadata": {
            "total_pages": metadata.get("total_pages"),
            "word_count": len(content.split()),
            "char_count": len(content),
            "format": format,
        },
        "timestamp": datetime.now().isoformat(),
    }


async def edit_document(
    section_id: str,
    new_content: str,
    edit_type: Literal["replace", "append", "prepend", "insert"] = "replace",
    insert_position: Optional[int] = None,
    reason: Optional[str] = None,
    preserve_formatting: bool = True,
    # Contexto do caso (injetado pelo executor)
    case_id: Optional[str] = None,
    tenant_id: str = "default",
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Edita uma seção do documento em elaboração.

    NOTA: Esta função prepara a edição mas NÃO aplica diretamente.
    O executor deve solicitar aprovação do usuário antes de aplicar.

    Args:
        section_id: ID ou título da seção a editar
        new_content: Novo conteúdo
        edit_type: Tipo de edição
        insert_position: Posição de inserção (para insert)
        reason: Motivo da edição
        preserve_formatting: Se True, preserva formatação
        case_id: ID do caso
        tenant_id: Tenant para multi-tenancy
        user_id: ID do usuário

    Returns:
        Dict com preview da edição e metadados
    """
    logger.info(f"[edit_document] section={section_id}, type={edit_type}")

    ctx = get_document_context()
    document = ctx.get_current_document()

    if document is None:
        return {
            "success": False,
            "error": "Nenhum documento em elaboração",
            "requires_approval": False,
        }

    # Buscar seção atual
    sections = document.get("sections", [])
    current_section = _find_section_dict(sections, section_id)

    if current_section is None:
        # Tentar encontrar no conteúdo bruto
        content = document.get("content", "")
        section_text = _extract_section_from_text(content, section_id)
        if not section_text:
            return {
                "success": False,
                "error": f"Seção '{section_id}' não encontrada",
                "available_sections": [s.get("title") or s.get("id") for s in sections],
                "requires_approval": False,
            }
        current_section = {"id": section_id, "title": section_id, "content": section_text}

    # Calcular novo conteúdo
    old_content = current_section.get("content", "")

    if edit_type == "replace":
        result_content = new_content
    elif edit_type == "append":
        result_content = f"{old_content}\n\n{new_content}"
    elif edit_type == "prepend":
        result_content = f"{new_content}\n\n{old_content}"
    elif edit_type == "insert":
        if insert_position is None:
            insert_position = len(old_content) // 2
        result_content = f"{old_content[:insert_position]}\n{new_content}\n{old_content[insert_position:]}"
    else:
        result_content = new_content

    # Gerar diff simplificado
    diff = _generate_diff(old_content, result_content)

    # Registrar edição pendente
    edit_record = {
        "section_id": section_id,
        "edit_type": edit_type,
        "old_content": old_content,
        "new_content": result_content,
        "diff": diff,
        "reason": reason,
        "user_id": user_id,
        "status": "pending_approval",
    }
    ctx.record_edit(edit_record)

    return {
        "success": True,
        "requires_approval": True,
        "edit_id": edit_record.get("edit_id"),
        "section_id": section_id,
        "edit_type": edit_type,
        "preview": {
            "old_content": old_content[:500] + ("..." if len(old_content) > 500 else ""),
            "new_content": result_content[:500] + ("..." if len(result_content) > 500 else ""),
            "diff": diff[:1000],
        },
        "stats": {
            "old_word_count": len(old_content.split()),
            "new_word_count": len(result_content.split()),
            "old_char_count": len(old_content),
            "new_char_count": len(result_content),
        },
        "reason": reason,
        "timestamp": datetime.now().isoformat(),
    }


async def create_section(
    title: str,
    content: str,
    position: Literal["beginning", "end", "after", "before"] = "end",
    reference_section_id: Optional[str] = None,
    level: int = 1,
    section_type: str = "custom",
    # Contexto do caso (injetado pelo executor)
    case_id: Optional[str] = None,
    tenant_id: str = "default",
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Cria uma nova seção no documento em elaboração.

    NOTA: Esta função prepara a criação mas NÃO aplica diretamente.
    O executor deve solicitar aprovação do usuário antes de criar.

    Args:
        title: Título da nova seção
        content: Conteúdo da seção
        position: Posição (beginning, end, after, before)
        reference_section_id: Seção de referência para after/before
        level: Nível hierárquico (1-6)
        section_type: Tipo semântico da seção
        case_id: ID do caso
        tenant_id: Tenant para multi-tenancy
        user_id: ID do usuário

    Returns:
        Dict com preview da nova seção e metadados
    """
    logger.info(f"[create_section] title='{title}', position={position}")

    ctx = get_document_context()
    document = ctx.get_current_document()

    if document is None:
        return {
            "success": False,
            "error": "Nenhum documento em elaboração",
            "requires_approval": False,
        }

    # Gerar ID para a seção
    section_id = hashlib.md5(f"{title}:{datetime.now().isoformat()}".encode()).hexdigest()[:12]

    # Validar posição relativa
    if position in ("after", "before") and not reference_section_id:
        return {
            "success": False,
            "error": f"position='{position}' requer reference_section_id",
            "requires_approval": False,
        }

    if reference_section_id:
        sections = document.get("sections", [])
        ref_section = _find_section_dict(sections, reference_section_id)
        if ref_section is None:
            return {
                "success": False,
                "error": f"Seção de referência '{reference_section_id}' não encontrada",
                "available_sections": [s.get("title") or s.get("id") for s in sections],
                "requires_approval": False,
            }

    # Formatar título com nível
    formatted_title = "#" * level + " " + title

    # Montar seção completa
    section_markdown = f"{formatted_title}\n\n{content}"

    # Registrar criação pendente
    edit_record = {
        "section_id": section_id,
        "edit_type": "create_section",
        "new_section": {
            "id": section_id,
            "title": title,
            "content": content,
            "level": level,
            "section_type": section_type,
            "position": position,
            "reference_section_id": reference_section_id,
        },
        "reason": f"Criar seção: {title}",
        "user_id": user_id,
        "status": "pending_approval",
    }
    ctx.record_edit(edit_record)

    return {
        "success": True,
        "requires_approval": True,
        "edit_id": edit_record.get("edit_id"),
        "section_id": section_id,
        "preview": {
            "markdown": section_markdown[:1000] + ("..." if len(section_markdown) > 1000 else ""),
            "title": title,
            "level": level,
            "section_type": section_type,
        },
        "placement": {
            "position": position,
            "reference_section_id": reference_section_id,
        },
        "stats": {
            "word_count": len(content.split()),
            "char_count": len(content),
        },
        "timestamp": datetime.now().isoformat(),
    }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _find_section(sections: List[Dict], section_id: str) -> Optional[str]:
    """Encontra conteúdo de uma seção pelo ID ou título."""
    for section in sections:
        if section.get("id") == section_id or section.get("title") == section_id:
            return section.get("content", "")
        # Buscar em subseções
        subsections = section.get("subsections", [])
        if subsections:
            result = _find_section(subsections, section_id)
            if result:
                return result
    return None


def _find_section_dict(sections: List[Dict], section_id: str) -> Optional[Dict]:
    """Encontra dict de uma seção pelo ID ou título."""
    for section in sections:
        if section.get("id") == section_id or section.get("title") == section_id:
            return section
        subsections = section.get("subsections", [])
        if subsections:
            result = _find_section_dict(subsections, section_id)
            if result:
                return result
    return None


def _extract_section_from_text(text: str, section_id: str) -> Optional[str]:
    """Extrai seção do texto bruto usando regex."""
    import re

    # Escapar caracteres especiais no ID
    escaped_id = re.escape(section_id)

    # Padrões para encontrar seções
    patterns = [
        rf"(#{1,6}\s*{escaped_id}.*?)(?=#{1,6}\s|\Z)",  # Headers Markdown
        rf"({escaped_id}\s*\n[-=]+\n.*?)(?=\n[A-Z].*?\n[-=]+|\Z)",  # Underline style
        rf"(\d+\.\s*{escaped_id}.*?)(?=\d+\.\s|\Z)",  # Numeração
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()

    return None


def _extract_page_range(text: str, start: int, end: Optional[int]) -> str:
    """Extrai range de páginas do texto (aproximado)."""
    # Assumir ~3000 caracteres por página
    chars_per_page = 3000
    start_char = (start - 1) * chars_per_page
    end_char = (end * chars_per_page) if end else None

    if end_char:
        return text[start_char:end_char]
    return text[start_char:]


def _markdown_to_text(markdown: str) -> str:
    """Converte Markdown para texto plano."""
    import re

    text = markdown
    # Remover headers
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    # Remover bold/italic
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    text = re.sub(r"_([^_]+)_", r"\1", text)
    # Remover links
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Remover código inline
    text = re.sub(r"`([^`]+)`", r"\1", text)

    return text


def _markdown_to_html(markdown: str) -> str:
    """Converte Markdown para HTML básico."""
    try:
        import markdown as md
        return md.markdown(markdown, extensions=["tables", "fenced_code"])
    except ImportError:
        # Fallback simples
        import re
        html = markdown
        # Headers
        for i in range(6, 0, -1):
            pattern = rf"^{'#' * i}\s*(.+)$"
            html = re.sub(pattern, rf"<h{i}>\1</h{i}>", html, flags=re.MULTILINE)
        # Bold
        html = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", html)
        # Italic
        html = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", html)
        # Paragraphs
        html = re.sub(r"\n\n", r"</p>\n<p>", html)
        html = f"<p>{html}</p>"
        return html


def _generate_diff(old: str, new: str) -> str:
    """Gera diff simplificado entre dois textos."""
    try:
        import difflib
        differ = difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile="original",
            tofile="modificado",
            lineterm="",
        )
        return "".join(differ)
    except Exception:
        # Fallback simples
        return f"--- original\n{old[:200]}...\n+++ modificado\n{new[:200]}..."


# =============================================================================
# TOOL REGISTRY
# =============================================================================

DOCUMENT_EDITOR_TOOLS = {
    "read_document": {
        "function": read_document,
        "schema": READ_DOCUMENT_SCHEMA,
        "permission_default": "allow",  # Leitura, pode executar automaticamente
    },
    "edit_document": {
        "function": edit_document,
        "schema": EDIT_DOCUMENT_SCHEMA,
        "permission_default": "ask",  # Escrita, requer aprovação
    },
    "create_section": {
        "function": create_section,
        "schema": CREATE_SECTION_SCHEMA,
        "permission_default": "ask",  # Escrita, requer aprovação
    },
}
