"""
Quality Gate - Heurística rápida de compressão/omissão

Detecta problemas de qualidade no output gerado:
- Compressão excessiva (output muito curto vs input)
- Referências legais omitidas (leis/súmulas/julgados do contexto não aparecem no output)

Aciona safe_mode ou força HIL quando detecta problemas.
"""
import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field, asdict
from loguru import logger


@dataclass
class QualityGateResult:
    """Resultado da avaliação do Quality Gate."""
    passed: bool
    compression_ratio: float
    reference_coverage: float = 1.0
    missing_references: List[str] = field(default_factory=list)
    safe_mode: bool = False
    force_hil: bool = False
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Padrões legais comuns em documentos jurídicos brasileiros
LEGAL_PATTERNS = [
    r"Lei\s*(?:n[º°.]?\s*)?[\d.]+(?:/\d+)?",
    r"Art(?:igo)?\.?\s*\d+",
    r"S[úu]mula\s*(?:Vinculante\s*)?n?[º°.]?\s*\d+",
    r"REsp\s*(?:n[º°.]?\s*)?[\d.]+(?:/[A-Z]{2})?",
    r"RE\s*(?:n[º°.]?\s*)?[\d.]+(?:/[A-Z]{2})?",
    r"HC\s*(?:n[º°.]?\s*)?[\d.]+(?:/[A-Z]{2})?",
    r"ADI\s*(?:n[º°.]?\s*)?[\d.]+",
    r"ADPF\s*(?:n[º°.]?\s*)?[\d.]+",
    r"Decreto\s*(?:n[º°.]?\s*)?[\d.]+(?:/\d+)?",
    r"Portaria\s*(?:n[º°.]?\s*)?[\d.]+(?:/\d+)?",
    r"IN\s*(?:n[º°.]?\s*)?[\d.]+(?:/\d+)?",
    r"MP\s*(?:n[º°.]?\s*)?[\d.]+(?:/\d+)?",
    r"LC\s*(?:n[º°.]?\s*)?[\d.]+(?:/\d+)?",
]


def extract_legal_references(text: str) -> List[str]:
    """
    Extrai referências legais do texto.
    
    Args:
        text: Texto para análise
        
    Returns:
        Lista de referências encontradas (únicas)
    """
    refs = []
    for pattern in LEGAL_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        refs.extend(matches)
    return list(set(refs))


def count_words(text: str) -> int:
    """
    Conta palavras ignorando markup Markdown.
    
    Args:
        text: Texto para contagem
        
    Returns:
        Número de palavras
    """
    # Remove markup comum
    clean = re.sub(r'[#*_`|>\-\[\]\(\)]', ' ', text)
    # Remove URLs
    clean = re.sub(r'https?://\S+', '', clean)
    # Conta palavras
    return len(re.findall(r'\b\w+\b', clean, re.UNICODE))


def normalize_reference(ref: str) -> str:
    """Normaliza referência para comparação."""
    # Remove espaços e pontuação, lowercase
    normalized = re.sub(r'[^\w\d]', '', ref.lower())
    return normalized


def reference_appears_in_text(ref: str, text: str) -> bool:
    """
    Verifica se uma referência aparece no texto (fuzzy).
    
    Considera variações como:
    - "Lei 8.666" vs "Lei nº 8.666/93"
    - "Art. 5" vs "Artigo 5º"
    """
    # Extrai números da referência
    numbers = re.findall(r'\d+', ref)
    if not numbers:
        return False
    
    # Verifica se o número principal aparece no contexto correto
    main_number = numbers[0]
    
    # Padrões de contexto
    ref_lower = ref.lower()
    
    if 'lei' in ref_lower:
        pattern = rf'lei[^0-9]*{main_number}'
    elif 'art' in ref_lower:
        pattern = rf'art[^0-9]*{main_number}'
    elif 'súmula' in ref_lower or 'sumula' in ref_lower:
        pattern = rf's[úu]mula[^0-9]*{main_number}'
    elif 'resp' in ref_lower:
        pattern = rf'resp[^0-9]*{main_number}'
    elif 're' in ref_lower and 're' == ref_lower[:2]:
        pattern = rf'\bre[^0-9]*{main_number}'
    elif 'hc' in ref_lower:
        pattern = rf'hc[^0-9]*{main_number}'
    elif 'adi' in ref_lower:
        pattern = rf'adi[^0-9]*{main_number}'
    elif 'decreto' in ref_lower:
        pattern = rf'decreto[^0-9]*{main_number}'
    else:
        # Fallback: só verifica se o número aparece
        pattern = rf'\b{main_number}\b'
    
    return bool(re.search(pattern, text.lower()))


def quality_gate(
    input_context: str,
    generated_output: str,
    min_compression_ratio: float = 0.15,
    max_compression_ratio: float = 3.5,
    min_reference_coverage: float = 0.5
) -> QualityGateResult:
    """
    Avalia qualidade do output gerado.
    
    Args:
        input_context: Texto de entrada/contexto (prompt + RAG + autos)
        generated_output: Texto gerado pelo LLM
        min_compression_ratio: Ratio mínimo (output muito curto = problema)
        max_compression_ratio: Ratio máximo (output muito longo/repetitivo)
        min_reference_coverage: % mínimo de referências do input que devem aparecer no output
    
    Returns:
        QualityGateResult com diagnóstico completo
    """
    notes = []
    force_hil = False
    safe_mode = False
    
    # 1. Ratio de compressão (palavras)
    input_words = count_words(input_context)
    output_words = count_words(generated_output)
    
    if input_words == 0:
        compression_ratio = 1.0
    else:
        compression_ratio = output_words / input_words
    
    # Avaliar compressão
    if compression_ratio < min_compression_ratio:
        notes.append(
            f"⚠️ Output muito curto (ratio={compression_ratio:.2f} < {min_compression_ratio}). "
            f"Input: {input_words} palavras, Output: {output_words} palavras."
        )
        safe_mode = True
        force_hil = True
    elif compression_ratio > max_compression_ratio:
        notes.append(
            f"⚠️ Output muito longo/possivelmente repetitivo (ratio={compression_ratio:.2f} > {max_compression_ratio})"
        )
        safe_mode = True
    
    # 2. Cobertura de referências legais
    input_refs = extract_legal_references(input_context)
    missing_refs = []
    
    if input_refs:
        for ref in input_refs:
            if not reference_appears_in_text(ref, generated_output):
                missing_refs.append(ref)
        
        coverage = 1.0 - (len(missing_refs) / len(input_refs))
        
        if coverage < min_reference_coverage:
            notes.append(
                f"⚠️ Cobertura de referências baixa ({coverage:.0%}). "
                f"Omitidas: {missing_refs[:5]}{'...' if len(missing_refs) > 5 else ''}"
            )
            force_hil = True
    else:
        coverage = 1.0
    
    # 3. Verificações adicionais
    # Output vazio ou muito pequeno
    if output_words < 50:
        notes.append(f"⚠️ Output extremamente curto ({output_words} palavras)")
        force_hil = True
        safe_mode = True
    
    # Determinar se passou
    passed = not safe_mode and not force_hil
    
    if passed:
        notes.append(
            f"✅ Quality Gate passou (ratio={compression_ratio:.2f}, "
            f"refs_coverage={coverage:.0%}, words={output_words})"
        )
    
    logger.info(
        f"Quality Gate: passed={passed}, ratio={compression_ratio:.2f}, "
        f"missing_refs={len(missing_refs)}, force_hil={force_hil}"
    )
    
    return QualityGateResult(
        passed=passed,
        compression_ratio=round(compression_ratio, 3),
        reference_coverage=round(coverage, 3),
        missing_references=missing_refs[:10],  # Limitar a 10
        safe_mode=safe_mode,
        force_hil=force_hil,
        notes=notes
    )


async def quality_gate_node(state: dict) -> dict:
    """
    Nó do LangGraph que aplica o quality gate.
    
    Avalia cada seção processada e atualiza o state com resultados.
    """
    processed_sections = state.get("processed_sections", [])
    input_text = state.get("input_text", "")
    research_context = state.get("research_context", "")
    
    # Combinar contexto
    full_context = f"{input_text}\n\n{research_context}"
    
    gate_results = []
    any_failed = False
    any_force_hil = False
    
    for i, section in enumerate(processed_sections):
        content = section.get("merged_content", "")
        
        if not content:
            gate_results.append({
                "section": section.get("section_title", f"Seção {i+1}"),
                "passed": False,
                "notes": ["⚠️ Seção vazia"]
            })
            any_failed = True
            continue
        
        # Avaliar seção
        result = quality_gate(full_context, content)
        
        gate_results.append({
            "section": section.get("section_title", f"Seção {i+1}"),
            "passed": result.passed,
            "compression_ratio": result.compression_ratio,
            "reference_coverage": result.reference_coverage,
            "missing_references": result.missing_references,
            "notes": result.notes
        })
        
        if not result.passed:
            any_failed = True
            # Anotar na seção para uso posterior
            section["quality_gate_failed"] = True
            section["quality_gate_notes"] = result.notes
        
        if result.force_hil:
            any_force_hil = True
    
    # Atualizar HIL checklist se necessário
    hil_checklist = state.get("hil_checklist", {})
    if any_force_hil:
        hil_checklist["quality_gate_force_hil"] = True
        existing_notes = hil_checklist.get("evaluation_notes", [])
        if isinstance(existing_notes, list):
            existing_notes.append("Quality Gate detectou problemas de compressão/omissão")
            hil_checklist["evaluation_notes"] = existing_notes
    
    logger.info(
        f"Quality Gate Node: {len(gate_results)} seções avaliadas, "
        f"passed={not any_failed}, force_hil={any_force_hil}"
    )
    
    return {
        **state,
        "quality_gate_results": gate_results,
        "quality_gate_passed": not any_failed,
        "quality_gate_force_hil": any_force_hil,
        "hil_checklist": hil_checklist
    }

