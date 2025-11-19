"""
Implementações concretas dos agentes de IA
"""

from typing import Dict, List, Any, Optional
import anthropic
import google.generativeai as genai
from openai import AsyncOpenAI
from loguru import logger

from app.core.config import settings
from app.services.ai.base_agent import BaseAgent, AgentResponse, AgentReview


class ClaudeAgent(BaseAgent):
    """
    Agente usando Claude Sonnet 4.5 da Anthropic
    Especializado em: Geração inicial de documentos jurídicos
    """
    
    def __init__(self):
        super().__init__(
            name="Claude (Gerador)",
            role="GENERATOR",
            model=settings.ANTHROPIC_MODEL,
            temperature=settings.ANTHROPIC_TEMPERATURE,
            max_tokens=settings.ANTHROPIC_MAX_TOKENS
        )
        self.client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    
    async def generate(
        self,
        prompt: str,
        context: Dict[str, Any],
        system_prompt: Optional[str] = None
    ) -> AgentResponse:
        """
        Gera documento inicial usando Claude
        """
        logger.info(f"[{self.name}] Gerando documento...")
        
        try:
            # Formatar contexto
            formatted_context = self._format_context(context)
            
            # System prompt padrão para geração
            if not system_prompt:
                system_prompt = """Você é um especialista jurídico brasileiro com ampla experiência 
na elaboração de documentos jurídicos. Sua função é gerar documentos precisos, bem fundamentados 
e tecnicamente corretos, seguindo as normas da ABNT e as boas práticas jurídicas."""
            
            # Construir mensagens
            messages = [
                {
                    "role": "user",
                    "content": f"{formatted_context}\n\n{prompt}"
                }
            ]
            
            # Chamar API da Anthropic
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=system_prompt,
                messages=messages
            )
            
            content = response.content[0].text
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            
            cost = self._calculate_cost(input_tokens, output_tokens)
            
            logger.info(f"[{self.name}] Documento gerado - Tokens: {input_tokens + output_tokens}, Custo: R$ {cost:.4f}")
            
            return AgentResponse(
                content=content,
                tokens_used=input_tokens + output_tokens,
                model=self.model,
                cost=cost,
                metadata={
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens
                }
            )
            
        except Exception as e:
            logger.error(f"[{self.name}] Erro ao gerar documento: {e}")
            raise
    
    async def review(
        self,
        content: str,
        context: Dict[str, Any],
        criteria: List[str]
    ) -> AgentReview:
        """
        Claude pode revisar estrutura e coerência narrativa
        """
        logger.info(f"[{self.name}] Revisando documento...")
        
        try:
            review_prompt = f"""Revise o seguinte documento jurídico de acordo com estes critérios:

{chr(10).join(f'- {c}' for c in criteria)}

DOCUMENTO A REVISAR:
{content}

Forneça:
1. Análise detalhada
2. Sugestões de melhoria
3. Pontuação de 0 a 10
4. Aprovado (sim/não)

Formato da resposta:
ANÁLISE: [sua análise]
SUGESTÕES: [suas sugestões]
PONTUAÇÃO: [0-10]
APROVADO: [SIM/NÃO]
"""
            
            response = await self.generate(review_prompt, context)
            
            # Parse da resposta (simplificado)
            # TODO: Implementar parser mais robusto
            content_lower = response.content.lower()
            approved = "sim" in content_lower.split("aprovado:")[-1][:10]
            
            # Extrair pontuação (simplificado)
            try:
                score_section = content_lower.split("pontuação:")[-1].split("\n")[0]
                score = float(''.join(c for c in score_section if c.isdigit() or c == '.'))
            except:
                score = 7.0
            
            return AgentReview(
                agent_name=self.name,
                original_content=content,
                suggested_changes=response.content,
                comments=[response.content],
                score=score,
                approved=approved
            )
            
        except Exception as e:
            logger.error(f"[{self.name}] Erro ao revisar documento: {e}")
            raise
    
    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Calcula custo do Claude"""
        input_cost = (input_tokens / 1_000_000) * 3.0  # $3 por 1M tokens de input
        output_cost = (output_tokens / 1_000_000) * 15.0  # $15 por 1M tokens de output
        return (input_cost + output_cost) * 5.5  # Converter para R$ (aproximado)


class GeminiAgent(BaseAgent):
    """
    Agente usando Gemini 2.5 Pro do Google
    Especializado em: Revisão de precisão jurídica e verificação de fatos
    """
    
    def __init__(self):
        super().__init__(
            name="Gemini (Revisor Legal)",
            role="LEGAL_REVIEWER",
            model=settings.GOOGLE_MODEL,
            temperature=settings.GOOGLE_TEMPERATURE,
            max_tokens=settings.GOOGLE_MAX_TOKENS
        )
        genai.configure(api_key=settings.GOOGLE_API_KEY)
        self.client = genai.GenerativeModel(self.model)
    
    async def generate(
        self,
        prompt: str,
        context: Dict[str, Any],
        system_prompt: Optional[str] = None
    ) -> AgentResponse:
        """
        Gera conteúdo usando Gemini (usado principalmente para revisão)
        """
        logger.info(f"[{self.name}] Processando...")
        
        try:
            formatted_context = self._format_context(context)
            full_prompt = f"{system_prompt or ''}\n\n{formatted_context}\n\n{prompt}"
            
            response = await self.client.generate_content_async(
                full_prompt,
                generation_config=genai.GenerationConfig(
                    temperature=self.temperature,
                    max_output_tokens=self.max_tokens
                )
            )
            
            content = response.text
            
            # Gemini não fornece uso de tokens diretamente em todas as versões
            # Estimar baseado no conteúdo
            estimated_tokens = len(content.split()) * 1.3
            cost = self._calculate_cost(int(estimated_tokens), int(estimated_tokens))
            
            logger.info(f"[{self.name}] Processamento concluído - Tokens estimados: {estimated_tokens:.0f}")
            
            return AgentResponse(
                content=content,
                tokens_used=int(estimated_tokens),
                model=self.model,
                cost=cost
            )
            
        except Exception as e:
            logger.error(f"[{self.name}] Erro ao processar: {e}")
            raise
    
    async def review(
        self,
        content: str,
        context: Dict[str, Any],
        criteria: List[str]
    ) -> AgentReview:
        """
        Revisão focada em precisão jurídica, citações corretas e fundamentação legal
        """
        logger.info(f"[{self.name}] Revisando precisão jurídica...")
        
        try:
            review_prompt = f"""Você é um revisor jurídico especializado. Analise o documento abaixo focando em:

- Precisão das citações legais e jurisprudenciais
- Correção da fundamentação jurídica
- Aplicabilidade das normas citadas
- Coerência dos argumentos jurídicos
- Atualização da legislação referenciada

DOCUMENTO:
{content}

Forneça uma revisão detalhada apontando:
1. Erros de fundamentação legal
2. Citações incorretas ou desatualizadas
3. Argumentos jurídicos fracos
4. Sugestões de melhoria específicas
5. Pontuação de 0 a 10 para precisão jurídica
6. Aprovado (SIM/NÃO) para seguir para próxima etapa

Use o formato:
ANÁLISE JURÍDICA: [análise]
ERROS ENCONTRADOS: [lista]
SUGESTÕES: [sugestões]
PONTUAÇÃO: [0-10]
APROVADO: [SIM/NÃO]
"""
            
            response = await self.generate(review_prompt, context)
            
            # Parse simplificado
            content_lower = response.content.lower()
            approved = "sim" in content_lower.split("aprovado:")[-1][:10]
            
            try:
                score_section = content_lower.split("pontuação:")[-1].split("\n")[0]
                score = float(''.join(c for c in score_section if c.isdigit() or c == '.'))
            except:
                score = 7.5
            
            return AgentReview(
                agent_name=self.name,
                original_content=content,
                suggested_changes=response.content,
                comments=[response.content],
                score=score,
                approved=approved
            )
            
        except Exception as e:
            logger.error(f"[{self.name}] Erro ao revisar: {e}")
            raise
    
    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Calcula custo do Gemini"""
        input_cost = (input_tokens / 1_000_000) * 1.25  # $1.25 por 1M tokens
        output_cost = (output_tokens / 1_000_000) * 5.0  # $5 por 1M tokens
        return (input_cost + output_cost) * 5.5  # Converter para R$


class GPTAgent(BaseAgent):
    """
    Agente usando GPT-5 da OpenAI
    Especializado em: Revisão textual, gramática e qualidade de escrita
    """
    
    def __init__(self):
        super().__init__(
            name="GPT (Revisor Textual)",
            role="TEXT_REVIEWER",
            model=settings.OPENAI_MODEL,
            temperature=settings.OPENAI_TEMPERATURE,
            max_tokens=settings.OPENAI_MAX_TOKENS
        )
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    
    async def generate(
        self,
        prompt: str,
        context: Dict[str, Any],
        system_prompt: Optional[str] = None
    ) -> AgentResponse:
        """
        Gera conteúdo usando GPT
        """
        logger.info(f"[{self.name}] Processando...")
        
        try:
            formatted_context = self._format_context(context)
            
            if not system_prompt:
                system_prompt = "Você é um revisor textual especializado em documentos jurídicos."
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"{formatted_context}\n\n{prompt}"}
            ]
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
            
            content = response.choices[0].message.content
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens
            total_tokens = response.usage.total_tokens
            
            cost = self._calculate_cost(input_tokens, output_tokens)
            
            logger.info(f"[{self.name}] Processamento concluído - Tokens: {total_tokens}, Custo: R$ {cost:.4f}")
            
            return AgentResponse(
                content=content,
                tokens_used=total_tokens,
                model=self.model,
                cost=cost,
                metadata={
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens
                }
            )
            
        except Exception as e:
            logger.error(f"[{self.name}] Erro ao processar: {e}")
            raise
    
    async def review(
        self,
        content: str,
        context: Dict[str, Any],
        criteria: List[str]
    ) -> AgentReview:
        """
        Revisão focada em qualidade textual, gramática e clareza
        """
        logger.info(f"[{self.name}] Revisando qualidade textual...")
        
        try:
            review_prompt = f"""Você é um revisor textual especializado. Analise o documento jurídico abaixo focando em:

- Gramática e ortografia
- Clareza e objetividade
- Coesão e coerência textual
- Estilo adequado ao gênero jurídico
- Formatação e estrutura
- Uso adequado da linguagem técnica

DOCUMENTO:
{content}

Forneça:
1. Correções gramaticais e ortográficas
2. Sugestões para melhorar clareza
3. Ajustes de estilo
4. Pontuação de 0 a 10 para qualidade textual
5. Aprovado (SIM/NÃO) para publicação

Formato:
ANÁLISE TEXTUAL: [análise]
CORREÇÕES: [lista]
SUGESTÕES DE ESTILO: [sugestões]
PONTUAÇÃO: [0-10]
APROVADO: [SIM/NÃO]
"""
            
            response = await self.generate(review_prompt, context)
            
            # Parse simplificado
            content_lower = response.content.lower()
            approved = "sim" in content_lower.split("aprovado:")[-1][:10]
            
            try:
                score_section = content_lower.split("pontuação:")[-1].split("\n")[0]
                score = float(''.join(c for c in score_section if c.isdigit() or c == '.'))
            except:
                score = 8.0
            
            return AgentReview(
                agent_name=self.name,
                original_content=content,
                suggested_changes=response.content,
                comments=[response.content],
                score=score,
                approved=approved
            )
            
        except Exception as e:
            logger.error(f"[{self.name}] Erro ao revisar: {e}")
            raise
    
    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Calcula custo do GPT"""
        input_cost = (input_tokens / 1_000_000) * 5.0  # $5 por 1M tokens (estimado GPT-5)
        output_cost = (output_tokens / 1_000_000) * 15.0  # $15 por 1M tokens
        return (input_cost + output_cost) * 5.5  # Converter para R$

