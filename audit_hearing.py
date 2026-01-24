#!/usr/bin/env python3
"""
audit_hearing.py - Auditoria Especializada para Audiências e Reuniões (v1.0)

Métricas adaptadas para transcrições forenses:
- Completude de falas (% sem inaudível)
- Identificação de falantes
- Preservação de evidências
- Coerência cronológica
"""

import re
import json
from typing import Optional
from pathlib import Path

# Thresholds para audiências/reuniões
HEARING_MIN_COMPLETUDE = 0.90  # 90% mínimo de falas audíveis
HEARING_MIN_SPEAKER_ID = 0.80  # 80% mínimo de segments com speaker identificado
HEARING_MIN_EVIDENCE = 1.00   # 100% das evidências devem ser preservadas

GRAVIDADE_ORDEM = {
    "BAIXA": 0,
    "MÉDIA": 1,
    "ALTA": 2,
    "CRÍTICA": 3,
}


def _normalize_gravidade(value: str) -> str:
    if not isinstance(value, str):
        return "BAIXA"
    upper = value.strip().upper()
    if upper in GRAVIDADE_ORDEM:
        return upper
    return "BAIXA"


def _count_inaudible(text: str) -> int:
    """Conta marcações de inaudível no texto."""
    if not text:
        return 0
    patterns = [
        r'\[inaudível\]',
        r'\[inaudivel\]',
        r'\[incompreensível\]',
        r'\[incompreensivel\]',
        r'\[\?\?\?\]',
        r'\[...\]',
    ]
    count = 0
    for pattern in patterns:
        count += len(re.findall(pattern, text, re.IGNORECASE))
    return count


def _extract_timestamps(text: str) -> list[str]:
    """Extrai timestamps do texto."""
    if not text:
        return []
    pattern = r'\[(\d{1,2}:\d{2}(?::\d{2})?)\]'
    return re.findall(pattern, text)


def auditar_completude_falas(
    segments: list[dict],
    formatted_text: str,
) -> dict:
    """
    Verifica completude das falas (% sem marcações de inaudível).
    
    Returns:
        dict com métricas de completude
    """
    total_segments = len(segments)
    if total_segments == 0:
        return {
            "taxa_completude": 1.0,
            "total_segments": 0,
            "segments_com_inaudivel": 0,
            "total_inaudiveis": 0,
            "aprovado": True,
            "gravidade": "BAIXA",
        }
    
    segments_com_inaudivel = 0
    total_inaudiveis = 0
    
    for seg in segments:
        text = seg.get("text", "")
        inaudivel_count = _count_inaudible(text)
        if inaudivel_count > 0:
            segments_com_inaudivel += 1
            total_inaudiveis += inaudivel_count
    
    # Também verificar no texto formatado
    total_inaudiveis += _count_inaudible(formatted_text)
    
    taxa_completude = 1.0 - (segments_com_inaudivel / total_segments) if total_segments > 0 else 1.0
    aprovado = taxa_completude >= HEARING_MIN_COMPLETUDE
    
    if taxa_completude < 0.70:
        gravidade = "CRÍTICA"
    elif taxa_completude < 0.80:
        gravidade = "ALTA"
    elif taxa_completude < HEARING_MIN_COMPLETUDE:
        gravidade = "MÉDIA"
    else:
        gravidade = "BAIXA"
    
    return {
        "taxa_completude": round(taxa_completude, 4),
        "total_segments": total_segments,
        "segments_com_inaudivel": segments_com_inaudivel,
        "total_inaudiveis": total_inaudiveis,
        "aprovado": aprovado,
        "gravidade": gravidade,
    }


def auditar_identificacao_falantes(
    segments: list[dict],
    speakers: list[dict],
) -> dict:
    """
    Verifica identificação de falantes nos segmentos.
    
    Returns:
        dict com métricas de identificação
    """
    total_segments = len(segments)
    if total_segments == 0:
        return {
            "taxa_identificacao": 1.0,
            "total_segments": 0,
            "segments_identificados": 0,
            "segments_nao_identificados": 0,
            "speakers_unicos": 0,
            "speakers_com_nome": 0,
            "aprovado": True,
            "gravidade": "BAIXA",
        }
    
    speaker_ids = {sp.get("speaker_id") for sp in speakers if sp.get("speaker_id")}
    speakers_com_nome = sum(1 for sp in speakers if sp.get("name") and sp.get("name") != sp.get("label"))
    
    segments_identificados = 0
    segments_nao_identificados = 0
    
    for seg in segments:
        speaker_id = seg.get("speaker_id")
        speaker_label = seg.get("speaker_label", "")
        
        if speaker_id and speaker_id in speaker_ids:
            segments_identificados += 1
        elif speaker_label and not speaker_label.startswith("SPEAKER "):
            segments_identificados += 1
        else:
            segments_nao_identificados += 1
    
    taxa_identificacao = segments_identificados / total_segments if total_segments > 0 else 0
    aprovado = taxa_identificacao >= HEARING_MIN_SPEAKER_ID
    
    if taxa_identificacao < 0.50:
        gravidade = "CRÍTICA"
    elif taxa_identificacao < 0.70:
        gravidade = "ALTA"
    elif taxa_identificacao < HEARING_MIN_SPEAKER_ID:
        gravidade = "MÉDIA"
    else:
        gravidade = "BAIXA"
    
    return {
        "taxa_identificacao": round(taxa_identificacao, 4),
        "total_segments": total_segments,
        "segments_identificados": segments_identificados,
        "segments_nao_identificados": segments_nao_identificados,
        "speakers_unicos": len(speaker_ids),
        "speakers_com_nome": speakers_com_nome,
        "aprovado": aprovado,
        "gravidade": gravidade,
    }


def auditar_preservacao_evidencias(
    evidence_raw: list[dict],
    evidence_formatted: list[dict],
    claims: list[dict],
) -> dict:
    """
    Verifica se evidências do RAW foram preservadas no formatado.
    
    Returns:
        dict com métricas de preservação
    """
    total_raw = len(evidence_raw)
    total_formatted = len(evidence_formatted)
    total_claims = len(claims)
    
    if total_raw == 0:
        return {
            "taxa_preservacao": 1.0,
            "evidencias_raw": 0,
            "evidencias_formatted": 0,
            "claims_extraidos": total_claims,
            "evidencias_perdidas": [],
            "aprovado": True,
            "gravidade": "BAIXA",
        }
    
    # Verificar claims_normalized no formatted vs raw
    raw_claims = {ev.get("claim_normalized", "").lower().strip() for ev in evidence_raw if ev.get("claim_normalized")}
    formatted_claims = {ev.get("claim_normalized", "").lower().strip() for ev in evidence_formatted if ev.get("claim_normalized")}
    
    evidencias_perdidas = []
    for rc in raw_claims:
        if rc and rc not in formatted_claims:
            # Verificar se está parcialmente presente
            found = False
            for fc in formatted_claims:
                if rc in fc or fc in rc:
                    found = True
                    break
            if not found:
                evidencias_perdidas.append(rc[:100])
    
    taxa_preservacao = 1.0 - (len(evidencias_perdidas) / total_raw) if total_raw > 0 else 1.0
    aprovado = taxa_preservacao >= HEARING_MIN_EVIDENCE
    
    if taxa_preservacao < 0.80:
        gravidade = "CRÍTICA"
    elif taxa_preservacao < 0.90:
        gravidade = "ALTA"
    elif taxa_preservacao < 1.0:
        gravidade = "MÉDIA"
    else:
        gravidade = "BAIXA"
    
    return {
        "taxa_preservacao": round(taxa_preservacao, 4),
        "evidencias_raw": total_raw,
        "evidencias_formatted": total_formatted,
        "claims_extraidos": total_claims,
        "evidencias_perdidas": evidencias_perdidas[:10],  # Limitar a 10
        "aprovado": aprovado,
        "gravidade": gravidade,
    }


def auditar_coerencia_cronologica(
    segments: list[dict],
) -> dict:
    """
    Verifica se a ordem cronológica dos segmentos está mantida.
    
    Returns:
        dict com métricas de coerência
    """
    total_segments = len(segments)
    if total_segments < 2:
        return {
            "ordem_mantida": True,
            "total_segments": total_segments,
            "inversoes": 0,
            "aprovado": True,
            "gravidade": "BAIXA",
        }
    
    inversoes = 0
    last_start = -1
    
    for seg in segments:
        start = seg.get("start")
        if start is not None:
            if start < last_start:
                inversoes += 1
            last_start = start
    
    ordem_mantida = inversoes == 0
    aprovado = ordem_mantida
    gravidade = "BAIXA" if ordem_mantida else "ALTA"
    
    return {
        "ordem_mantida": ordem_mantida,
        "total_segments": total_segments,
        "inversoes": inversoes,
        "aprovado": aprovado,
        "gravidade": gravidade,
    }


def auditar_contradicoes(
    contradictions: list[dict],
) -> dict:
    """
    Analisa contradições detectadas (informativo, não bloqueante).
    
    Returns:
        dict com análise de contradições
    """
    total = len(contradictions)
    
    # Contradições são informativas, não bloqueiam
    return {
        "total_contradicoes": total,
        "contradicoes": [
            {
                "topic": c.get("topic", ""),
                "reason": c.get("reason", ""),
                "samples": c.get("samples", [])[:2],
            }
            for c in contradictions[:5]
        ],
        "alerta": total > 0,
        "gravidade": "MÉDIA" if total > 3 else ("BAIXA" if total > 0 else "BAIXA"),
    }


def auditar_hearing_completo(
    raw_text: str,
    formatted_text: str,
    segments: list[dict],
    speakers: list[dict],
    evidence: list[dict],
    claims: list[dict],
    contradictions: Optional[list[dict]] = None,
    mode: str = "AUDIENCIA",
) -> dict:
    """
    Auditoria completa de hearing (audiência/reunião).
    
    Executa todas as verificações e consolida resultado.
    
    Args:
        raw_text: Transcrição bruta
        formatted_text: Texto formatado
        segments: Segmentos estruturados
        speakers: Lista de falantes
        evidence: Evidências extraídas
        claims: Claims estruturados
        contradictions: Contradições detectadas (opcional)
        mode: AUDIENCIA, REUNIAO ou DEPOIMENTO
    
    Returns:
        dict com resultado consolidado da auditoria
    """
    if contradictions is None:
        contradictions = []
    
    print(f"\n{'='*80}")
    print(f"🔬 AUDITORIA DE HEARING (v1.0) - Modo: {mode}")
    print(f"{'='*80}")
    
    # Executar auditorias individuais
    completude = auditar_completude_falas(segments, formatted_text)
    identificacao = auditar_identificacao_falantes(segments, speakers)
    preservacao = auditar_preservacao_evidencias(evidence, evidence, claims)
    cronologia = auditar_coerencia_cronologica(segments)
    analise_contradicoes = auditar_contradicoes(contradictions)
    
    # Consolidar gravidade geral
    gravidades = [
        completude.get("gravidade", "BAIXA"),
        identificacao.get("gravidade", "BAIXA"),
        preservacao.get("gravidade", "BAIXA"),
        cronologia.get("gravidade", "BAIXA"),
    ]
    
    gravidade_geral = "BAIXA"
    for g in gravidades:
        if GRAVIDADE_ORDEM.get(g, 0) > GRAVIDADE_ORDEM.get(gravidade_geral, 0):
            gravidade_geral = g
    
    # Determinar aprovação geral
    aprovado = all([
        completude.get("aprovado", True),
        identificacao.get("aprovado", True),
        preservacao.get("aprovado", True),
        cronologia.get("aprovado", True),
    ])
    
    # Calcular nota geral (0-10)
    nota = 10.0
    if not completude.get("aprovado"):
        nota -= 2.5
    if not identificacao.get("aprovado"):
        nota -= 2.0
    if not preservacao.get("aprovado"):
        nota -= 3.0
    if not cronologia.get("aprovado"):
        nota -= 1.5
    if analise_contradicoes.get("total_contradicoes", 0) > 3:
        nota -= 0.5
    
    nota = max(0, min(10, nota))
    
    # Construir recomendação HIL
    areas_criticas = []
    motivos = []
    
    if not completude.get("aprovado"):
        areas_criticas.append("completude_falas")
        motivos.append(f"Taxa de completude baixa: {completude.get('taxa_completude', 0)*100:.1f}%")
    
    if not identificacao.get("aprovado"):
        areas_criticas.append("identificacao_falantes")
        motivos.append(f"Baixa identificação de falantes: {identificacao.get('taxa_identificacao', 0)*100:.1f}%")
    
    if not preservacao.get("aprovado"):
        areas_criticas.append("preservacao_evidencias")
        motivos.append("Evidências potencialmente perdidas")
    
    if not cronologia.get("aprovado"):
        areas_criticas.append("ordem_cronologica")
        motivos.append(f"{cronologia.get('inversoes', 0)} inversão(ões) na ordem temporal")
    
    pausar_para_revisao = not aprovado or gravidade_geral in ("ALTA", "CRÍTICA")
    
    resultado = {
        "aprovado": aprovado,
        "nota_fidelidade": round(nota, 2),
        "gravidade_geral": gravidade_geral,
        "mode": mode,
        
        "completude": completude,
        "identificacao_falantes": identificacao,
        "preservacao_evidencias": preservacao,
        "coerencia_cronologica": cronologia,
        "contradicoes": analise_contradicoes,
        
        "metricas": {
            "taxa_completude": completude.get("taxa_completude", 0),
            "taxa_identificacao": identificacao.get("taxa_identificacao", 0),
            "taxa_preservacao": preservacao.get("taxa_preservacao", 0),
            "ordem_mantida": cronologia.get("ordem_mantida", True),
            "total_segments": len(segments),
            "total_speakers": len(speakers),
            "total_evidence": len(evidence),
            "total_claims": len(claims),
            "total_contradicoes": len(contradictions),
        },
        
        "recomendacao_hil": {
            "pausar_para_revisao": pausar_para_revisao,
            "motivo": " / ".join(motivos) if motivos else "",
            "areas_criticas": areas_criticas,
        },
        
        "source": "audit_hearing",
    }
    
    # Feedback visual
    print(f"\n📋 RESULTADO DA AUDITORIA")
    print(f"{'='*80}")
    
    if aprovado:
        print(f"✅ STATUS: APROVADO")
    else:
        print(f"⚠️ STATUS: REQUER REVISÃO")
    
    print(f"📊 Nota de Fidelidade: {nota:.1f}/10")
    print(f"🎚️  Gravidade Geral: {gravidade_geral}")
    
    print(f"\n📌 Métricas:")
    print(f"   {'✅' if completude.get('aprovado') else '⚠️'} Completude: {completude.get('taxa_completude', 0)*100:.1f}%")
    print(f"   {'✅' if identificacao.get('aprovado') else '⚠️'} Identificação: {identificacao.get('taxa_identificacao', 0)*100:.1f}%")
    print(f"   {'✅' if preservacao.get('aprovado') else '⚠️'} Preservação: {preservacao.get('taxa_preservacao', 0)*100:.1f}%")
    print(f"   {'✅' if cronologia.get('aprovado') else '⚠️'} Cronologia: {'OK' if cronologia.get('ordem_mantida') else 'INVERSÕES'}")
    
    if analise_contradicoes.get("total_contradicoes", 0) > 0:
        print(f"   ℹ️ Contradições: {analise_contradicoes.get('total_contradicoes')} detectada(s)")
    
    if pausar_para_revisao:
        print(f"\n🛑 RECOMENDAÇÃO: PAUSAR PARA REVISÃO HIL")
        print(f"   Motivo: {resultado['recomendacao_hil']['motivo']}")
    
    print(f"{'='*80}\n")
    
    return resultado


def gerar_relatorio_hearing_markdown(
    resultado: dict,
    doc_name: str = "hearing",
) -> str:
    """
    Gera relatório de auditoria em formato Markdown.
    
    Args:
        resultado: Resultado de auditar_hearing_completo
        doc_name: Nome do documento
    
    Returns:
        str: Relatório em Markdown
    """
    aprovado = resultado.get("aprovado", False)
    nota = resultado.get("nota_fidelidade", 0)
    gravidade = resultado.get("gravidade_geral", "BAIXA")
    mode = resultado.get("mode", "AUDIENCIA")
    
    status_emoji = "✅" if aprovado else "⚠️"
    status_text = "APROVADO" if aprovado else "REQUER REVISÃO"
    
    metricas = resultado.get("metricas", {})
    completude = resultado.get("completude", {})
    identificacao = resultado.get("identificacao_falantes", {})
    preservacao = resultado.get("preservacao_evidencias", {})
    cronologia = resultado.get("coerencia_cronologica", {})
    contradicoes = resultado.get("contradicoes", {})
    recom = resultado.get("recomendacao_hil", {})
    
    lines = [
        f"# 🔬 Relatório de Auditoria - {doc_name}",
        "",
        f"**Modo:** {mode}",
        f"**Status:** {status_emoji} {status_text}",
        f"**Nota de Fidelidade:** {nota:.1f}/10",
        f"**Gravidade Geral:** {gravidade}",
        "",
        "---",
        "",
        "## 📊 Métricas de Qualidade",
        "",
        "| Métrica | Valor | Status |",
        "| :--- | :--- | :--- |",
        f"| Completude de Falas | {metricas.get('taxa_completude', 0)*100:.1f}% | {'✅' if completude.get('aprovado') else '⚠️'} |",
        f"| Identificação de Falantes | {metricas.get('taxa_identificacao', 0)*100:.1f}% | {'✅' if identificacao.get('aprovado') else '⚠️'} |",
        f"| Preservação de Evidências | {metricas.get('taxa_preservacao', 0)*100:.1f}% | {'✅' if preservacao.get('aprovado') else '⚠️'} |",
        f"| Ordem Cronológica | {'OK' if metricas.get('ordem_mantida') else 'INVERSÕES'} | {'✅' if cronologia.get('aprovado') else '⚠️'} |",
        "",
        "---",
        "",
        "## 📈 Detalhamento",
        "",
        "### Segmentos e Falantes",
        f"- Total de segmentos: {metricas.get('total_segments', 0)}",
        f"- Segmentos com inaudível: {completude.get('segments_com_inaudivel', 0)}",
        f"- Total de marcações [inaudível]: {completude.get('total_inaudiveis', 0)}",
        f"- Falantes identificados: {identificacao.get('segments_identificados', 0)}",
        f"- Falantes únicos: {metricas.get('total_speakers', 0)}",
        f"- Falantes com nome: {identificacao.get('speakers_com_nome', 0)}",
        "",
        "### Evidências",
        f"- Total de evidências: {metricas.get('total_evidence', 0)}",
        f"- Claims extraídos: {metricas.get('total_claims', 0)}",
    ]
    
    perdidas = preservacao.get("evidencias_perdidas", [])
    if perdidas:
        lines.append("")
        lines.append("**Evidências potencialmente perdidas:**")
        for p in perdidas[:5]:
            lines.append(f"- {p}...")
    
    if contradicoes.get("total_contradicoes", 0) > 0:
        lines.extend([
            "",
            "### Contradições Detectadas",
            f"- Total: {contradicoes.get('total_contradicoes', 0)}",
        ])
        for c in contradicoes.get("contradicoes", [])[:3]:
            lines.append(f"- **{c.get('topic', 'N/A')}**: {c.get('reason', 'N/A')}")
    
    if recom.get("pausar_para_revisao"):
        lines.extend([
            "",
            "---",
            "",
            "## 🛑 Recomendação: Revisão HIL",
            "",
            f"**Motivo:** {recom.get('motivo', 'Problemas detectados')}",
            "",
            "**Áreas críticas:**",
        ])
        for area in recom.get("areas_criticas", []):
            lines.append(f"- {area}")
    
    lines.extend([
        "",
        "---",
        "",
        f"*Gerado por audit_hearing.py v1.0*",
    ])
    
    return "\n".join(lines)


if __name__ == "__main__":
    # Teste básico
    test_segments = [
        {"text": "Bom dia.", "speaker_label": "JUIZ", "speaker_id": "spk_001", "start": 0, "end": 2},
        {"text": "Bom dia, Excelência.", "speaker_label": "ADVOGADO", "speaker_id": "spk_002", "start": 2, "end": 5},
        {"text": "[inaudível] e depois...", "speaker_label": "SPEAKER 1", "start": 5, "end": 8},
    ]
    test_speakers = [
        {"speaker_id": "spk_001", "name": "Dr. João Silva", "role": "juiz"},
        {"speaker_id": "spk_002", "name": "Dra. Maria Santos", "role": "advogado"},
    ]
    test_evidence = [
        {"claim_normalized": "Reunião em 15/01/2024"},
        {"claim_normalized": "Valor de R$ 10.000"},
    ]
    
    result = auditar_hearing_completo(
        raw_text="Bom dia. Bom dia, Excelência. [inaudível] e depois...",
        formatted_text="**JUIZ**: Bom dia.\n\n**ADVOGADO**: Bom dia, Excelência.\n\n**SPEAKER 1**: [inaudível] e depois...",
        segments=test_segments,
        speakers=test_speakers,
        evidence=test_evidence,
        claims=test_evidence,
        contradictions=[],
        mode="AUDIENCIA",
    )
    
    print("\n" + gerar_relatorio_hearing_markdown(result, "teste_audiencia"))
