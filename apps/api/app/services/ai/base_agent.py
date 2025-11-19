"""
Classe base para agentes de IA
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from loguru import logger


@dataclass
class AgentResponse:
    """Resposta de um agente"""
    content: str
    thinking: Optional[str] = None
    tokens_used: int = 0
    model: str = ""
    cost: float = 0.0
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class AgentReview:
    """Revisão de um agente"""
    agent_name: str
    original_content: str
    suggested_changes: str
    comments: List[str]
    score: float  # 0-10
    approved: bool
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class BaseAgent(ABC):
    """
    Classe base abstrata para agentes de IA
    """
    
    def __init__(
        self,
        name: str,
        role: str,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4000
    ):
        self.name = name
        self.role = role
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        logger.info(f"Inicializando agente: {self.name} ({self.role}) - Modelo: {self.model}")
    
    @abstractmethod
    async def generate(
        self,
        prompt: str,
        context: Dict[str, Any],
        system_prompt: Optional[str] = None
    ) -> AgentResponse:
        """
        Gera conteúdo baseado no prompt e contexto
        """
        pass
    
    @abstractmethod
    async def review(
        self,
        content: str,
        context: Dict[str, Any],
        criteria: List[str]
    ) -> AgentReview:
        """
        Revisa conteúdo gerado por outro agente
        """
        pass
    
    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """
        Calcula o custo da operação
        Implementação específica em cada agente
        """
        return 0.0
    
    def _format_context(self, context: Dict[str, Any]) -> str:
        """
        Formata o contexto para inclusão no prompt
        """
        formatted = []
        
        if context.get("documents"):
            formatted.append("## Documentos do Processo")
            for doc in context["documents"]:
                formatted.append(f"### {doc.get('name', 'Documento')}")
                formatted.append(doc.get("content", ""))
        
        if context.get("jurisprudence"):
            formatted.append("\n## Jurisprudência Relevante")
            for jur in context["jurisprudence"]:
                formatted.append(f"### {jur.get('number', '')}")
                formatted.append(jur.get("ementa", ""))
        
        if context.get("legislation"):
            formatted.append("\n## Legislação Aplicável")
            for leg in context["legislation"]:
                formatted.append(f"### {leg.get('name', '')}")
                formatted.append(leg.get("content", ""))
        
        if context.get("user_instructions"):
            formatted.append("\n## Instruções do Usuário")
            formatted.append(context["user_instructions"])
        
        return "\n\n".join(formatted)

