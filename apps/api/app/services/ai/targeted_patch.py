"""
Targeted Patch - Correção localizada de omissões

Em vez de reescrever o documento inteiro quando há problemas:
1. Identifica o ponto de inserção (âncora)
2. Gera apenas o trecho a inserir
3. Aplica o patch no ponto correto

Mais eficiente e menos propenso a alucinações que reescrita completa.
"""
import re
import json
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from loguru import logger

from app.services.ai.document_store import resolve_full_document, store_full_document_state


@dataclass
class PatchOperation:
    """Representa uma operação de patch."""
    anchor: str  # Texto âncora (onde inserir)
    position: str  # "before" | "after" | "replace"
    content: str  # Conteúdo a inserir
    reason: str  # Motivo da correção
    section: Optional[str] = None  # Seção alvo (se aplicável)
    applied: bool = False  # Se foi aplicado com sucesso
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PatchResult:
    """Resultado da aplicação de patches."""
    patches_generated: int
    patches_applied: int
    patches_failed: int
    document_modified: bool
    details: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def find_anchor_position(document: str, anchor: str) -> Optional[int]:
    """
    Encontra posição da âncora no documento.
    
    Tenta match exato primeiro, depois fuzzy.
    """
    if not anchor or not document:
        return None
    
    # 1. Match exato
    pos = document.find(anchor)
    if pos != -1:
        return pos
    
    # 2. Match case-insensitive
    pos = document.lower().find(anchor.lower())
    if pos != -1:
        return pos
    
    # 3. Match fuzzy (primeiras palavras significativas)
    anchor_words = [w for w in anchor.split() if len(w) > 3][:5]
    if len(anchor_words) >= 2:
        pattern = r'\b' + r'\s+'.join(re.escape(w) for w in anchor_words) + r'\b'
        match = re.search(pattern, document, re.IGNORECASE)
        if match:
            return match.start()
    
    # 4. Match por números/referências legais
    numbers = re.findall(r'\d+', anchor)
    if numbers:
        main_num = numbers[0]
        pattern = rf'\b{main_num}\b'
        for match in re.finditer(pattern, document):
            start = max(0, match.start() - 50)
            end = min(len(document), match.end() + 50)
            context = document[start:end].lower()
            matches = sum(1 for w in anchor_words if w.lower() in context)
            if matches >= 2:
                return match.start()
    
    return None


def apply_single_patch(document: str, patch: PatchOperation) -> Tuple[str, bool]:
    """Aplica um único patch ao documento."""
    pos = find_anchor_position(document, patch.anchor)
    
    if pos is None:
        logger.warning(f"Âncora não encontrada: '{patch.anchor[:50]}...'")
        return document, False
    
    if patch.position == "after":
        anchor_end = pos + len(patch.anchor)
        end_pos = document.find('\n\n', anchor_end)
        if end_pos == -1:
            end_pos = document.find('\n', anchor_end)
        if end_pos == -1:
            end_pos = len(document)
        new_doc = document[:end_pos] + "\n\n" + patch.content.strip() + document[end_pos:]
        
    elif patch.position == "before":
        start_pos = document.rfind('\n\n', 0, pos)
        if start_pos == -1:
            start_pos = document.rfind('\n', 0, pos)
        if start_pos == -1:
            start_pos = 0
        else:
            start_pos += 1 if document[start_pos] == '\n' else 2
        new_doc = document[:start_pos] + patch.content.strip() + "\n\n" + document[start_pos:]
        
    elif patch.position == "replace":
        anchor_end = pos + len(patch.anchor)
        new_doc = document[:pos] + patch.content.strip() + document[anchor_end:]
        
    else:
        logger.warning(f"Posição de patch inválida: {patch.position}")
        return document, False
    
    logger.info(f"Patch aplicado ({patch.position}): {patch.reason[:50]}...")
    return new_doc, True


def apply_patches(document: str, patches: List[PatchOperation]) -> Tuple[str, PatchResult]:
    """Aplica múltiplos patches ao documento."""
    if not patches:
        return document, PatchResult(0, 0, 0, False)
    
    patches_with_pos = []
    for patch in patches:
        pos = find_anchor_position(document, patch.anchor)
        patches_with_pos.append((pos if pos else float('inf'), patch))
    
    # aplicar de trás para frente
    patches_with_pos.sort(key=lambda x: x[0], reverse=True)
    
    applied = 0
    failed = 0
    details = []
    modified_doc = document
    
    for _, patch in patches_with_pos:
        new_doc, success = apply_single_patch(modified_doc, patch)
        
        if success:
            modified_doc = new_doc
            applied += 1
            patch.applied = True
            details.append({
                "anchor": patch.anchor[:50],
                "position": patch.position,
                "reason": patch.reason,
                "status": "applied"
            })
        else:
            failed += 1
            details.append({
                "anchor": patch.anchor[:50],
                "position": patch.position,
                "reason": patch.reason,
                "status": "failed"
            })
    
    result = PatchResult(
        patches_generated=len(patches),
        patches_applied=applied,
        patches_failed=failed,
        document_modified=applied > 0,
        details=details
    )
    
    return modified_doc, result


async def generate_targeted_patches(
    document: str,
    issues: List[str],
    drafter,
    mode: str = "PETICAO"
) -> List[PatchOperation]:
    """Gera patches localizados para cada issue usando LLM."""
    patches: List[PatchOperation] = []
    if not issues or not drafter:
        return patches
    
    prompt = f"""Você é um revisor jurídico. Analise os problemas abaixo e gere PATCHES LOCALIZADOS.

## PROBLEMAS IDENTIFICADOS:
{chr(10).join(['- ' + issue for issue in issues])}

## DOCUMENTO ({mode}):
{document[:12000]}

## INSTRUÇÕES:
Para CADA problema, gere um patch localizado. Responda APENAS com JSON válido:

{{
  "patches": [
    {{
      "issue": "descrição breve do problema",
      "anchor": "texto EXATO do documento onde inserir (copie literalmente)",
      "position": "after",
      "content": "texto a inserir",
      "reason": "explicação da correção"
    }}
  ]
}}

REGRAS CRÍTICAS:
1. O "anchor" DEVE ser texto que existe EXATAMENTE no documento. Copie do documento acima.
2. Use "position": "after" para adicionar conteúdo novo após um parágrafo.
3. Use "position": "before" para adicionar antes de um parágrafo.
4. Use "position": "replace" APENAS para corrigir citações/números errados.
5. O "content" deve ser conciso e focado no problema específico.
6. NÃO invente citações, jurisprudência ou dados.
7. Se não conseguir gerar patch para algum problema, omita-o.
"""
    
    try:
        resp = drafter._generate_with_retry(prompt)
        if not resp or not resp.text:
            logger.warning("Resposta vazia do drafter para patches")
            return patches
        
        text = resp.text.strip()
        if text.startswith("```"):
            text = re.sub(r'^```(?:json)?', '', text).strip()
            text = re.sub(r'```$', '', text).strip()
        
        json_match = re.search(r'\{[\s\S]*\}', text)
        if not json_match:
            logger.warning("JSON não encontrado na resposta")
            return patches
        
        data = json.loads(json_match.group(0))
        for p in data.get("patches", []):
            anchor = (p.get("anchor") or "").strip()
            position = (p.get("position") or "after").lower()
            content = (p.get("content") or "").strip()
            reason = (p.get("reason") or p.get("issue") or "").strip()
            if not anchor or not content:
                continue
            if position not in ("before", "after", "replace"):
                position = "after"
            patches.append(PatchOperation(anchor=anchor, position=position, content=content, reason=reason))
        
        logger.info(f"Gerados {len(patches)} patches localizados")
        
    except json.JSONDecodeError as e:
        logger.error(f"Erro ao parsear JSON de patches: {e}")
    except Exception as e:
        logger.error(f"Erro ao gerar patches: {e}")
    
    return patches


async def targeted_patch_node(state: dict) -> dict:
    """Nó do LangGraph que aplica patches localizados."""
    issues = state.get("audit_issues", [])
    if not issues:
        logger.info("Targeted Patch: sem issues, pulando")
        return {
            **state,
            "patches_applied": [],
            "targeted_patch_used": False,
            "patch_result": PatchResult(0, 0, 0, False).to_dict()
        }
    
    drafter = None
    try:
        from app.services.ai.gemini_drafter import GeminiDrafterWrapper
        drafter = GeminiDrafterWrapper()
    except ImportError:
        logger.warning("GeminiDrafterWrapper não disponível para patches")
    
    if not drafter:
        return {
            **state,
            "targeted_patch_used": False,
            "patch_result": PatchResult(0, 0, 0, False).to_dict()
        }
    
    document = resolve_full_document(state)
    mode = state.get("mode", "PETICAO")
    
    patches = await generate_targeted_patches(document, issues, drafter, mode)
    if not patches:
        logger.warning("Nenhum patch gerado, fallback para propose_corrections")
        return {
            **state,
            "targeted_patch_used": False,
            "patch_result": PatchResult(0, 0, 0, False).to_dict()
        }
    
    modified_doc, result = apply_patches(document, patches)
    logger.info(f"Targeted Patch: {result.patches_applied}/{result.patches_generated} aplicados")
    
    if result.patches_applied > 0:
        destino = (state.get("destino") or "uso_interno").lower()
        risco = (state.get("risco") or "baixo").lower()
        auto_approve = bool(state.get("auto_approve_hil", False))
        require_approval = (destino != "uso_interno" or risco == "alto") and not auto_approve

        if require_approval:
            return {
                **state,
                "proposed_corrections": modified_doc,
                "patches_applied": result.details,
                "targeted_patch_used": True,
                "patch_result": result.to_dict(),
                "corrections_diff": f"{result.patches_applied} patches aplicados"
            }

        updated_state = {
            **state,
            "proposed_corrections": None,
            "patches_applied": result.details,
            "targeted_patch_used": True,
            "patch_result": result.to_dict(),
            "corrections_diff": f"{result.patches_applied} patches aplicados",
            "human_approved_corrections": True
        }
        return store_full_document_state(updated_state, modified_doc)
    
    return {
        **state,
        "targeted_patch_used": False,
        "patch_result": result.to_dict()
    }
