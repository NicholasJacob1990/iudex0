"""
HIL Decision Engine - Universal Rules for Human-in-the-Loop

This module implements a unified decision system that automatically determines
when HIL is mandatory based on 10 objective risk factors.

Works for any document type: petição, parecer, contrato, e-mail, nota, minuta.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from loguru import logger


@dataclass
class HILChecklist:
    """
    Universal checklist with 10 risk factors for HIL decision.
    
    If ANY factor is true (or meets threshold), HIL is mandatory.
    """
    
    # 1. Context: Destiny and Risk
    destino_externo: bool = False  # Document sent to third parties
    risco_alto: bool = False       # High impact ($$, penal, regulatory, reputational)
    
    # 2. Scope Changes
    novas_teses_ou_pedidos: bool = False  # New thesis/request not in input
    desvio_playbook: bool = False         # Deviation from standard policy
    
    # 3. Citations
    num_citacoes_externas: int = 0    # Laws, súmulas, precedentes cited
    num_citacoes_suspeitas: int = 0   # Suspicious/invalid citations found
    num_citacoes_pendentes: int = 0   # Claims that require citation / pending validation
    
    # 4. Consistency
    contradicao_interna: bool = False      # Internal contradictions
    fato_inventado: bool = False           # Invented facts not in input
    fato_relevante_ignorado: bool = False  # Relevant fact ignored
    
    # 5. Confidence
    score_confianca: float = 1.0  # Overall confidence score (0.0 - 1.0)
    
    # Metadata
    triggered_factors: List[str] = field(default_factory=list)
    evaluation_notes: List[str] = field(default_factory=list)
    
    def requires_hil(self) -> bool:
        """
        The core decision function.
        Returns True if ANY condition triggers mandatory HIL.
        """
        return (
            self.destino_externo or
            self.risco_alto or
            self.novas_teses_ou_pedidos or
            self.desvio_playbook or
            self.num_citacoes_externas >= 1 or
            self.num_citacoes_suspeitas >= 1 or
            self.num_citacoes_pendentes >= 1 or
            self.contradicao_interna or
            self.fato_inventado or
            self.fato_relevante_ignorado or
            self.score_confianca < 0.7
        )
    
    def get_triggered_factors(self) -> List[str]:
        """Returns list of factors that triggered HIL requirement"""
        factors = []
        
        if self.destino_externo:
            factors.append("destino_externo: Documento será enviado a terceiros")
        if self.risco_alto:
            factors.append("risco_alto: Alto impacto (valor, penal, tributário)")
        if self.novas_teses_ou_pedidos:
            factors.append("novas_teses_ou_pedidos: Nova tese/pedido introduzido")
        if self.desvio_playbook:
            factors.append("desvio_playbook: Recomendação diferente da política padrão")
        if self.num_citacoes_externas >= 1:
            factors.append(f"citacoes_externas: {self.num_citacoes_externas} citação(ões) a verificar")
        if self.num_citacoes_suspeitas >= 1:
            factors.append(f"citacoes_suspeitas: {self.num_citacoes_suspeitas} citação(ões) suspeita(s)")
        if self.num_citacoes_pendentes >= 1:
            factors.append(f"citacoes_pendentes: {self.num_citacoes_pendentes} item(ns) exigem validação/citação")
        if self.contradicao_interna:
            factors.append("contradicao_interna: Contradição detectada no documento")
        if self.fato_inventado:
            factors.append("fato_inventado: Fato não presente nos insumos")
        if self.fato_relevante_ignorado:
            factors.append("fato_relevante_ignorado: Fato essencial não utilizado")
        if self.score_confianca < 0.7:
            factors.append(f"baixa_confianca: Score {self.score_confianca:.2f} < 0.7")
        
        self.triggered_factors = factors
        return factors
    
    def get_hil_level(self) -> str:
        """
        Returns HIL level based on severity of triggered factors.
        
        Returns:
            'none': No HIL needed
            'review': Standard human review
            'critical': Critical review (high risk or suspicious citations)
        """
        if not self.requires_hil():
            return "none"
        
        # Critical if any of these
        if (self.risco_alto or 
            self.num_citacoes_suspeitas >= 1 or 
            self.fato_inventado or 
            self.contradicao_interna):
            return "critical"
        
        return "review"
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON/SSE"""
        return {
            "destino_externo": self.destino_externo,
            "risco_alto": self.risco_alto,
            "novas_teses_ou_pedidos": self.novas_teses_ou_pedidos,
            "desvio_playbook": self.desvio_playbook,
            "num_citacoes_externas": self.num_citacoes_externas,
            "num_citacoes_suspeitas": self.num_citacoes_suspeitas,
            "num_citacoes_pendentes": self.num_citacoes_pendentes,
            "contradicao_interna": self.contradicao_interna,
            "fato_inventado": self.fato_inventado,
            "fato_relevante_ignorado": self.fato_relevante_ignorado,
            "score_confianca": self.score_confianca,
            "requires_hil": self.requires_hil(),
            "hil_level": self.get_hil_level(),
            "triggered_factors": self.get_triggered_factors(),
            "evaluation_notes": self.evaluation_notes
        }


def evaluate_context_from_request(
    destino: str = "uso_interno",
    risco: str = "baixo"
) -> HILChecklist:
    """
    Create initial checklist from user request metadata.
    
    Args:
        destino: One of 'uso_interno', 'cliente', 'contraparte', 'autoridade', 'regulador'
        risco: One of 'baixo', 'medio', 'alto'
    """
    checklist = HILChecklist()
    
    # Evaluate destiny
    if destino != "uso_interno":
        checklist.destino_externo = True
        checklist.evaluation_notes.append(f"Destino: {destino} (externo)")
    
    # Evaluate risk
    if risco == "alto":
        checklist.risco_alto = True
        checklist.evaluation_notes.append("Risco classificado como ALTO pelo usuário")
    
    return checklist


def evaluate_citations_from_audit(
    checklist: HILChecklist,
    audit_report: Optional[Dict[str, Any]]
) -> HILChecklist:
    """
    Update checklist with citation analysis from audit.
    """
    if not audit_report:
        return checklist
    
    citations = audit_report.get("citations", [])
    markdown = audit_report.get("markdown", "")
    
    # Count external citations
    checklist.num_citacoes_externas = len(citations)
    
    # Count suspicious citations (marked with 🔴 in audit)
    suspicious = [c for c in citations if c.get("suspicious", False)]
    if "🔴" in markdown:
        # Also count from markdown markers
        import re
        suspicious_count = len(re.findall(r"🔴", markdown))
        checklist.num_citacoes_suspeitas = max(len(suspicious), suspicious_count)
    else:
        checklist.num_citacoes_suspeitas = len(suspicious)
    
    if checklist.num_citacoes_suspeitas > 0:
        checklist.evaluation_notes.append(
            f"Auditoria encontrou {checklist.num_citacoes_suspeitas} citação(ões) suspeita(s)"
        )
    
    return checklist


def evaluate_consistency_from_debate(
    checklist: HILChecklist,
    has_divergence: bool,
    divergence_summary: str = ""
) -> HILChecklist:
    """
    Update checklist with consistency analysis from multi-agent debate.
    """
    if has_divergence:
        checklist.contradicao_interna = True
        checklist.evaluation_notes.append(
            f"Divergência entre agentes: {divergence_summary[:100]}..."
        )
    
    return checklist


def evaluate_confidence_score(
    checklist: HILChecklist,
    audit_status: str = "aprovado",
    debate_rounds: int = 4,
    citations_valid_ratio: float = 1.0
) -> HILChecklist:
    """
    Calculate overall confidence score based on multiple factors.
    
    Score components:
    - Audit status: +0.3 if approved, +0.15 if with caveats, 0 if rejected
    - Debate consensus: +0.3 if no divergence
    - Citations ratio: +0.3 * valid_ratio
    - Base: +0.1
    """
    score = 0.1  # Base
    
    # Audit component
    if audit_status == "aprovado":
        score += 0.3
    elif audit_status == "aprovado_ressalvas":
        score += 0.15
    # reprovado adds 0
    
    # Debate component
    if not checklist.contradicao_interna:
        score += 0.3
    
    # Citations component
    score += 0.3 * citations_valid_ratio
    
    checklist.score_confianca = min(score, 1.0)
    checklist.evaluation_notes.append(f"Score de confiança calculado: {score:.2f}")
    
    return checklist


class HILDecisionEngine:
    """
    Main engine that orchestrates all evaluations and provides final decision.
    """
    
    def __init__(self):
        self.checklist: Optional[HILChecklist] = None
    
    def evaluate(
        self,
        # From user request
        destino: str = "uso_interno",
        risco: str = "baixo",
        # From audit
        audit_report: Optional[Dict[str, Any]] = None,
        audit_status: str = "aprovado",
        # From debate
        has_divergence: bool = False,
        divergence_summary: str = ""
    ) -> HILChecklist:
        """
        Full evaluation pipeline.
        """
        # 1. Context from request
        self.checklist = evaluate_context_from_request(destino, risco)
        
        # 2. Citations from audit
        self.checklist = evaluate_citations_from_audit(self.checklist, audit_report)
        
        # 3. Consistency from debate
        self.checklist = evaluate_consistency_from_debate(
            self.checklist, has_divergence, divergence_summary
        )
        
        # 4. Calculate confidence
        valid_ratio = 1.0
        if self.checklist.num_citacoes_externas > 0:
            valid_ratio = 1.0 - (self.checklist.num_citacoes_suspeitas / self.checklist.num_citacoes_externas)
        
        self.checklist = evaluate_confidence_score(
            self.checklist,
            audit_status=audit_status,
            citations_valid_ratio=valid_ratio
        )
        
        # Log decision
        if self.checklist.requires_hil():
            logger.info(f"🛑 HIL REQUIRED: {self.checklist.get_triggered_factors()}")
        else:
            logger.info("✅ HIL NOT REQUIRED: All checks passed")
        
        return self.checklist
    
    def get_decision(self) -> Dict[str, Any]:
        """Returns serializable decision object"""
        if not self.checklist:
            return {"requires_hil": False, "hil_level": "none"}
        return self.checklist.to_dict()


# Global instance
hil_engine = HILDecisionEngine()
