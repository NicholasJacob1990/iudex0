"""
Orquestrador de múltiplos agentes de IA
Sistema que coordena Claude, Gemini e GPT trabalhando juntos
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from loguru import logger

from app.services.ai.agents import ClaudeAgent, GeminiAgent, GPTAgent
from app.services.ai.base_agent import AgentResponse, AgentReview


@dataclass
class MultiAgentResult:
    """Resultado do processamento multi-agente"""
    final_content: str
    reviews: List[AgentReview]
    consensus: bool
    conflicts: List[str]
    total_tokens: int
    total_cost: float
    processing_time_seconds: float
    metadata: Dict[str, Any]


class MultiAgentOrchestrator:
    """
    Orquestrador que coordena múltiplos agentes de IA
    
    Fluxo:
    1. Claude gera o documento inicial
    2. Gemini revisa precisão jurídica
    3. GPT revisa qualidade textual
    4. Orquestrador consolida feedback
    5. Claude aplica correções (se necessário)
    6. Retorna documento final
    """
    
    def __init__(self):
        logger.info("Inicializando Multi-Agent Orchestrator")
        
        self.claude = ClaudeAgent()
        self.gemini = GeminiAgent()
        self.gpt = GPTAgent()
        
        self.agents = {
            "generator": self.claude,
            "legal_reviewer": self.gemini,
            "text_reviewer": self.gpt
        }
        
        logger.info("✅ Todos os agentes inicializados")
    
    async def generate_document(
        self,
        prompt: str,
        context: Dict[str, Any],
        effort_level: int = 3
    ) -> MultiAgentResult:
        """
        Gera documento com nível de esforço variável
        
        Níveis de esforço:
        1-2: Apenas Claude (rápido)
        3: Claude + revisão rápida
        4-5: Fluxo completo multi-agente com múltiplas iterações
        """
        import time
        start_time = time.time()
        
        logger.info(f"🚀 Iniciando geração de documento - Nível de esforço: {effort_level}")
        
        total_tokens = 0
        total_cost = 0.0
        reviews: List[AgentReview] = []
        conflicts: List[str] = []
        
        try:
            # Fase 1: Geração inicial (Claude)
            logger.info("📝 Fase 1: Geração inicial com Claude...")
            initial_response = await self.claude.generate(prompt, context)
            current_content = initial_response.content
            total_tokens += initial_response.tokens_used
            total_cost += initial_response.cost
            
            logger.info(f"✅ Documento inicial gerado ({len(current_content)} caracteres)")
            
            # Nível baixo: retornar direto
            if effort_level <= 2:
                logger.info("⚡ Nível de esforço baixo - Retornando documento inicial")
                processing_time = time.time() - start_time
                
                return MultiAgentResult(
                    final_content=current_content,
                    reviews=reviews,
                    consensus=True,
                    conflicts=conflicts,
                    total_tokens=total_tokens,
                    total_cost=total_cost,
                    processing_time_seconds=processing_time,
                    metadata={
                        "effort_level": effort_level,
                        "iterations": 1,
                        "agents_used": ["claude"]
                    }
                )
            
            # Fase 2: Revisão jurídica (Gemini)
            logger.info("⚖️ Fase 2: Revisão jurídica com Gemini...")
            legal_review = await self.gemini.review(
                current_content,
                context,
                criteria=[
                    "Precisão de citações legais",
                    "Fundamentação jurídica adequada",
                    "Atualização da legislação",
                    "Coerência dos argumentos"
                ]
            )
            reviews.append(legal_review)
            total_tokens += legal_review.metadata.get("tokens_used", 1000)
            total_cost += 0.02  # Custo estimado de revisão
            
            logger.info(f"✅ Revisão jurídica concluída - Score: {legal_review.score}/10, Aprovado: {legal_review.approved}")
            
            # Fase 3: Revisão textual (GPT)
            logger.info("✍️ Fase 3: Revisão textual com GPT...")
            text_review = await self.gpt.review(
                current_content,
                context,
                criteria=[
                    "Gramática e ortografia",
                    "Clareza e objetividade",
                    "Coesão textual",
                    "Estilo adequado"
                ]
            )
            reviews.append(text_review)
            total_tokens += text_review.metadata.get("tokens_used", 1000)
            total_cost += 0.03  # Custo estimado de revisão
            
            logger.info(f"✅ Revisão textual concluída - Score: {text_review.score}/10, Aprovado: {text_review.approved}")
            
            # Fase 4: Verificar consenso e conflitos
            logger.info("🔍 Fase 4: Verificando consenso...")
            consensus = legal_review.approved and text_review.approved
            avg_score = (legal_review.score + text_review.score) / 2
            
            if not consensus:
                conflicts.append(f"Revisores não chegaram a consenso (média: {avg_score:.1f}/10)")
            
            # Fase 5: Aplicar correções (se esforço alto e necessário)
            if effort_level >= 4 and (not consensus or avg_score < 8.0):
                logger.info("🔧 Fase 5: Aplicando correções com Claude...")
                
                correction_prompt = f"""Com base nas revisões abaixo, melhore o documento original:

DOCUMENTO ORIGINAL:
{current_content}

REVISÃO JURÍDICA (Score: {legal_review.score}/10):
{legal_review.suggested_changes}

REVISÃO TEXTUAL (Score: {text_review.score}/10):
{text_review.suggested_changes}

Aplique as correções sugeridas mantendo a essência do documento e gere a versão final aprimorada.
"""
                
                final_response = await self.claude.generate(correction_prompt, context)
                current_content = final_response.content
                total_tokens += final_response.tokens_used
                total_cost += final_response.cost
                
                logger.info("✅ Correções aplicadas - Documento final gerado")
            
            processing_time = time.time() - start_time
            
            logger.info(f"""
🎉 Geração concluída!
   Tempo: {processing_time:.2f}s
   Tokens: {total_tokens:,}
   Custo: R$ {total_cost:.4f}
   Consenso: {'✅' if consensus else '❌'}
   Score médio: {avg_score:.1f}/10
""")
            
            return MultiAgentResult(
                final_content=current_content,
                reviews=reviews,
                consensus=consensus,
                conflicts=conflicts,
                total_tokens=total_tokens,
                total_cost=total_cost,
                processing_time_seconds=processing_time,
                metadata={
                    "effort_level": effort_level,
                    "iterations": 2 if effort_level >= 4 else 1,
                    "agents_used": ["claude", "gemini", "gpt"],
                    "average_score": avg_score
                }
            )
            
        except Exception as e:
            logger.error(f"❌ Erro no orquestrador multi-agente: {e}")
            raise
    
    async def simple_chat(
        self,
        message: str,
        context: Dict[str, Any],
        conversation_history: Optional[List[Dict]] = None
    ) -> AgentResponse:
        """
        Chat simples usando apenas Claude (mais rápido)
        """
        logger.info("💬 Modo chat - Usando Claude")
        
        # Adicionar histórico ao contexto se fornecido
        if conversation_history:
            context["conversation_history"] = conversation_history
        
        return await self.claude.generate(message, context)

