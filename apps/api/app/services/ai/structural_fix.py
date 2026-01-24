"""
Structural Fix - Correções determinísticas de estrutura

Aplica correções automáticas e seguras:
- Remove parágrafos duplicados
- Normaliza hierarquia de headings
- Limpa artefatos de geração (linhas vazias, tags XML, etc.)
- Renumera seções se necessário

Todas as operações são determinísticas (sem LLM).
"""
import re
import hashlib
from typing import Dict, Any, List, Set, Tuple
from dataclasses import dataclass, field, asdict
from loguru import logger

from app.services.ai.document_store import resolve_full_document, store_full_document_state


@dataclass
class StructuralFixResult:
    """Resultado das correções estruturais."""
    original_length: int
    fixed_length: int
    duplicates_removed: int = 0
    headings_normalized: int = 0
    sections_renumbered: bool = False
    artifacts_cleaned: int = 0
    changes: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def normalize_for_dedup(text: str) -> str:
    """
    Normaliza texto para comparação de duplicatas.
    
    Remove pontuação, espaços extras e converte para lowercase.
    """
    # Remove pontuação
    normalized = re.sub(r'[^\w\s]', '', text.lower())
    # Normaliza espaços
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return normalized


def fingerprint(text: str) -> str:
    """
    Gera fingerprint MD5 de um parágrafo para detecção de duplicatas.
    """
    normalized = normalize_for_dedup(text)
    return hashlib.md5(normalized.encode()).hexdigest()[:12]


def remove_duplicate_paragraphs(text: str, min_chars: int = 80) -> Tuple[str, int]:
    """
    Remove parágrafos duplicados, mantendo a primeira ocorrência.
    
    Args:
        text: Texto para processar
        min_chars: Mínimo de caracteres para considerar duplicata
        
    Returns:
        (texto_limpo, num_removidos)
    """
    paragraphs = text.split('\n\n')
    seen_fps: Set[str] = set()
    unique_paragraphs = []
    removed = 0
    
    for para in paragraphs:
        stripped = para.strip()
        
        # Manter parágrafos especiais sem verificar duplicatas:
        # - Curtos demais
        # - Headings (#)
        # - Listas (- ou *)
        # - Tabelas (|)
        # - Blockquotes (>)
        # - Separadores (---)
        if (len(stripped) < min_chars or 
            stripped.startswith('#') or 
            stripped.startswith('-') or
            stripped.startswith('*') or
            stripped.startswith('|') or
            stripped.startswith('>') or
            stripped.startswith('---')):
            unique_paragraphs.append(para)
            continue
        
        fp = fingerprint(stripped)
        if fp in seen_fps:
            removed += 1
            logger.debug(f"Duplicado removido: {stripped[:50]}...")
        else:
            seen_fps.add(fp)
            unique_paragraphs.append(para)
    
    return '\n\n'.join(unique_paragraphs), removed


def normalize_headings(text: str) -> Tuple[str, int]:
    """
    Normaliza hierarquia de headings.
    
    Garante:
    - # para título principal (H1)
    - ## para seções (H2)
    - ### para subseções (H3)
    - #### para sub-subseções (H4)
    
    Se o documento começa com ## ou ###, ajusta todos os níveis.
    
    Returns:
        (texto_normalizado, num_alterações)
    """
    lines = text.split('\n')
    new_lines = []
    changes = 0
    
    # Detectar nível mínimo usado
    min_level = 6
    for line in lines:
        match = re.match(r'^(#{1,6})\s', line)
        if match:
            level = len(match.group(1))
            min_level = min(min_level, level)
    
    # Se já começa com H1, não precisa ajustar
    if min_level <= 1:
        return text, 0
    
    # Ajustar níveis
    adjustment = min_level - 1
    for line in lines:
        match = re.match(r'^(#{1,6})(\s.*)$', line)
        if match:
            current_level = len(match.group(1))
            new_level = max(1, current_level - adjustment)
            new_line = '#' * new_level + match.group(2)
            if new_line != line:
                changes += 1
            new_lines.append(new_line)
        else:
            new_lines.append(line)
    
    return '\n'.join(new_lines), changes


def clean_artifacts(text: str) -> Tuple[str, int]:
    """
    Remove artefatos comuns de geração por LLM.
    
    Returns:
        (texto_limpo, num_artefatos_removidos)
    """
    count = 0
    
    # 1. Múltiplas linhas vazias → máximo 2
    new_text = re.sub(r'\n{4,}', '\n\n\n', text)
    if new_text != text:
        count += 1
        text = new_text
    
    # 2. Espaços/tabs no fim das linhas
    new_text = re.sub(r'[ \t]+$', '', text, flags=re.MULTILINE)
    if new_text != text:
        count += 1
        text = new_text
    
    # 3. Separadores duplicados
    new_text = re.sub(r'(---\n)+', '---\n', text)
    if new_text != text:
        count += 1
        text = new_text
    
    # 4. Tags XML residuais
    new_text = re.sub(
        r'</?(?:peca|secao|texto|conteudo|documento|resposta|output)[^>]*>',
        '',
        text,
        flags=re.IGNORECASE
    )
    if new_text != text:
        count += 1
        text = new_text
    
    # 5. Marcadores de código desnecessários
    new_text = re.sub(r'^```(?:markdown|md)?\s*\n', '', text)
    new_text = re.sub(r'\n```\s*$', '', new_text)
    if new_text != text:
        count += 1
        text = new_text
    
    # 6. Prefixos de resposta de IA
    patterns_to_remove = [
        r'^(?:Aqui está|Segue|Veja abaixo)[^:]*:\s*\n+',
        r'^(?:Claro|Certo|Entendido)[,!.]?\s*\n+',
        r'^(?:Como solicitado|Conforme pedido)[^:]*:\s*\n+',
    ]
    for pattern in patterns_to_remove:
        new_text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        if new_text != text:
            count += 1
            text = new_text
    
    return text.strip(), count


def fix_broken_lists(text: str) -> str:
    """
    Corrige listas quebradas por linhas vazias extras.
    """
    # Padrão: item de lista seguido de linha vazia e outro item
    # Isso quebra a lista em Markdown
    text = re.sub(r'(\n- [^\n]+)\n\n(- )', r'\1\n\2', text)
    text = re.sub(r'(\n\* [^\n]+)\n\n(\* )', r'\1\n\2', text)
    text = re.sub(r'(\n\d+\. [^\n]+)\n\n(\d+\. )', r'\1\n\2', text)
    return text


def renumber_sections(text: str) -> Tuple[str, bool]:
    """
    Renumera seções se houver inconsistência.
    
    Detecta padrões como "I.", "1.", "1.1" e verifica se estão em ordem.
    
    Returns:
        (texto, foi_renumerado)
    """
    # Verificar numeração decimal
    decimal_pattern = r'^##\s*(\d+)\.'
    lines = text.split('\n')
    
    numbers = []
    for line in lines:
        match = re.match(decimal_pattern, line)
        if match:
            numbers.append(int(match.group(1)))
    
    if numbers:
        expected = list(range(1, len(numbers) + 1))
        if numbers != expected:
            logger.warning(f"Seções fora de ordem: {numbers} (esperado: {expected})")
            # TODO: Implementar renumeração automática
            # Por enquanto, apenas detecta
            return text, False
    
    return text, False


def structural_fix(text: str) -> Tuple[StructuralFixResult, str]:
    """
    Aplica todas as correções estruturais.
    
    Args:
        text: Documento Markdown para corrigir
        
    Returns:
        (StructuralFixResult, texto_corrigido)
    """
    original_length = len(text)
    changes = []
    
    # 1. Limpar artefatos
    text, artifacts_count = clean_artifacts(text)
    if artifacts_count > 0:
        changes.append(f"Removidos {artifacts_count} artefatos de geração")
    
    # 2. Corrigir listas quebradas
    text_before = text
    text = fix_broken_lists(text)
    if text != text_before:
        changes.append("Listas quebradas corrigidas")
    
    # 3. Remover parágrafos duplicados
    text, dups_removed = remove_duplicate_paragraphs(text)
    if dups_removed > 0:
        changes.append(f"Removidos {dups_removed} parágrafos duplicados")
    
    # 4. Normalizar headings
    text, headings_fixed = normalize_headings(text)
    if headings_fixed > 0:
        changes.append(f"Normalizados {headings_fixed} headings")
    
    # 5. Renumerar seções (se necessário)
    text, renumbered = renumber_sections(text)
    if renumbered:
        changes.append("Seções renumeradas")
    
    result = StructuralFixResult(
        original_length=original_length,
        fixed_length=len(text),
        duplicates_removed=dups_removed,
        headings_normalized=headings_fixed,
        sections_renumbered=renumbered,
        artifacts_cleaned=artifacts_count,
        changes=changes
    )
    
    if changes:
        logger.info(f"Structural Fix: {changes}")
    
    return result, text


async def structural_fix_node(state: dict) -> dict:
    """
    Nó do LangGraph que aplica correções estruturais.
    
    Deve rodar ANTES do audit_node para garantir documento limpo.
    """
    full_document = resolve_full_document(state)
    
    if not full_document:
        logger.warning("Structural Fix: documento vazio, pulando")
        return {
            **state,
            "structural_fix_result": StructuralFixResult(0, 0).to_dict()
        }
    
    result, fixed_document = structural_fix(full_document)
    
    logger.info(
        f"Structural Fix Node: {result.duplicates_removed} duplicados, "
        f"{result.headings_normalized} headings, "
        f"{result.artifacts_cleaned} artefatos"
    )
    
    updated_state = {
        **state,
        "structural_fix_result": result.to_dict()
    }
    return store_full_document_state(updated_state, fixed_document)
