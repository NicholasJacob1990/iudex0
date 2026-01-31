"""
Context Manager - Gerenciamento de Contexto no Estilo Claude Code

Este módulo implementa compactação inteligente de contexto para manter
conversas longas dentro dos limites de tokens dos modelos.

Estratégia de compactação em 2 passos:
1. Primeiro: limpar tool_results antigos
2. Se ainda precisar: resumir mensagens antigas

Preserva sempre:
- Instruções do sistema (system messages)
- Mensagens recentes
- Decisões tomadas
- Informações críticas do caso
"""

import os
import json
import asyncio
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

logger = logging.getLogger("ContextManager")

# Limites de contexto por modelo
MODEL_CONTEXT_LIMITS = {
    # Claude models
    "claude-4.5-opus": 200_000,
    "claude-4-opus-20250514": 200_000,
    "claude-sonnet-4-20250514": 200_000,
    "claude-3-5-sonnet-20241022": 200_000,
    "claude-3-haiku-20240307": 200_000,

    # OpenAI models
    "gpt-5.2": 400_000,
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "gpt-4-turbo": 128_000,
    "o1": 200_000,
    "o1-mini": 128_000,

    # Gemini models
    "gemini-2.0-flash": 1_000_000,
    "gemini-2.5-pro-preview-06-05": 1_000_000,
    "gemini-2.0-flash-thinking-exp": 1_000_000,

    # Default fallback
    "default": 128_000,
}

# Modelo rápido para resumos
SUMMARY_MODEL = os.getenv("CONTEXT_SUMMARY_MODEL", "claude-3-haiku-20240307")

# Threshold padrão (70% do limite)
DEFAULT_COMPACTION_THRESHOLD = float(os.getenv("CONTEXT_COMPACTION_THRESHOLD", "0.7"))


@dataclass
class ContextWindow:
    """
    Representa o estado atual da janela de contexto.

    Attributes:
        total_tokens: Total de tokens atualmente no contexto
        limit: Limite máximo de tokens do modelo
        threshold: Threshold para trigger de compactação (0.0-1.0)
        usage_percent: Porcentagem atual de uso
        needs_compaction: Se precisa compactar
        messages_count: Número de mensagens no contexto
        tool_results_count: Número de tool_results no contexto
    """
    total_tokens: int = 0
    limit: int = 128_000
    threshold: float = DEFAULT_COMPACTION_THRESHOLD
    usage_percent: float = 0.0
    needs_compaction: bool = False
    messages_count: int = 0
    tool_results_count: int = 0
    last_compaction: Optional[datetime] = None
    compaction_count: int = 0

    def __post_init__(self):
        if self.limit > 0:
            self.usage_percent = (self.total_tokens / self.limit) * 100
            self.needs_compaction = self.usage_percent >= (self.threshold * 100)


class ContextManager:
    """
    Gerenciador de contexto no estilo Claude Code.

    Responsável por:
    - Contar tokens das mensagens
    - Detectar quando contexto está chegando no limite
    - Compactar contexto de forma inteligente
    - Preservar informações críticas

    Usage:
        manager = ContextManager(model_name="claude-4.5-opus")

        # Verificar se precisa compactar
        if manager.should_compact(messages):
            compacted, summary = await manager.compact(messages)
    """

    def __init__(
        self,
        model_name: str = "claude-4.5-opus",
        threshold: float = DEFAULT_COMPACTION_THRESHOLD,
        anthropic_client: Optional[Any] = None,
    ):
        """
        Inicializa o ContextManager.

        Args:
            model_name: Nome do modelo para determinar limite de contexto
            threshold: Threshold para trigger de compactação (0.0-1.0)
            anthropic_client: Cliente Anthropic para geração de resumos
        """
        self.model_name = model_name
        self.threshold = threshold
        self.limit = self._get_model_limit(model_name)
        self._anthropic_client = anthropic_client
        self._tiktoken_encoding = None
        self._last_compaction: Optional[datetime] = None
        self._compaction_count = 0

        logger.info(
            f"ContextManager initialized: model={model_name}, "
            f"limit={self.limit:,}, threshold={threshold:.0%}"
        )

    def _get_model_limit(self, model_name: str) -> int:
        """Retorna o limite de contexto para o modelo."""
        # Busca exata primeiro
        if model_name in MODEL_CONTEXT_LIMITS:
            return MODEL_CONTEXT_LIMITS[model_name]

        # Busca por prefixo
        for key, limit in MODEL_CONTEXT_LIMITS.items():
            if model_name.startswith(key):
                return limit

        return MODEL_CONTEXT_LIMITS["default"]

    def _init_tiktoken(self):
        """Inicializa tiktoken de forma lazy."""
        if self._tiktoken_encoding is not None:
            return

        try:
            import tiktoken
            # cl100k_base é o encoding mais recente, usado por GPT-4 e similar
            # Para Claude, usamos o mesmo pois não há encoding público
            self._tiktoken_encoding = tiktoken.get_encoding("cl100k_base")
            logger.debug("tiktoken initialized with cl100k_base encoding")
        except ImportError:
            logger.warning(
                "tiktoken not available, falling back to character estimation. "
                "Install with: pip install tiktoken"
            )
            self._tiktoken_encoding = None

    def count_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """
        Conta tokens das mensagens.

        Usa tiktoken se disponível, senão fallback para estimativa.

        Args:
            messages: Lista de mensagens no formato OpenAI/Anthropic

        Returns:
            Número total de tokens
        """
        if not messages:
            return 0

        total_text = self._messages_to_text(messages)
        return self._count_text_tokens(total_text)

    def _count_text_tokens(self, text: str) -> int:
        """Conta tokens de um texto."""
        if not text:
            return 0

        self._init_tiktoken()

        if self._tiktoken_encoding:
            try:
                return len(self._tiktoken_encoding.encode(text))
            except Exception as e:
                logger.warning(f"tiktoken encoding failed: {e}")

        # Fallback: ~3.5 chars/token para português jurídico
        return max(0, len(text) // 3)

    def _messages_to_text(self, messages: List[Dict[str, Any]]) -> str:
        """Converte mensagens para texto para contagem de tokens."""
        parts = []

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            # Adiciona role como overhead
            parts.append(f"<{role}>")

            # Content pode ser string ou lista (para multimodal)
            if isinstance(content, str):
                parts.append(content)
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            parts.append(item.get("text", ""))
                        elif item.get("type") == "tool_result":
                            # Tool results podem ser grandes
                            result_content = item.get("content", "")
                            if isinstance(result_content, str):
                                parts.append(result_content)
                            elif isinstance(result_content, list):
                                for rc in result_content:
                                    if isinstance(rc, dict) and rc.get("type") == "text":
                                        parts.append(rc.get("text", ""))
                        elif item.get("type") == "tool_use":
                            # Tool use calls
                            parts.append(json.dumps(item.get("input", {})))
                    elif isinstance(item, str):
                        parts.append(item)

            # Tool calls (formato OpenAI)
            if "tool_calls" in msg:
                for tc in msg.get("tool_calls", []):
                    parts.append(tc.get("function", {}).get("name", ""))
                    parts.append(tc.get("function", {}).get("arguments", ""))

            parts.append(f"</{role}>")

        return "\n".join(parts)

    def get_context_window(self, messages: List[Dict[str, Any]]) -> ContextWindow:
        """
        Retorna o estado atual da janela de contexto.

        Args:
            messages: Lista de mensagens

        Returns:
            ContextWindow com métricas atuais
        """
        total_tokens = self.count_tokens(messages)
        tool_results = self._count_tool_results(messages)

        return ContextWindow(
            total_tokens=total_tokens,
            limit=self.limit,
            threshold=self.threshold,
            messages_count=len(messages),
            tool_results_count=tool_results,
            last_compaction=self._last_compaction,
            compaction_count=self._compaction_count,
        )

    def _count_tool_results(self, messages: List[Dict[str, Any]]) -> int:
        """Conta número de tool_results nas mensagens."""
        count = 0
        for msg in messages:
            if msg.get("role") == "tool":
                count += 1
            content = msg.get("content", [])
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "tool_result":
                        count += 1
        return count

    def should_compact(self, messages: List[Dict[str, Any]]) -> bool:
        """
        Verifica se o contexto deve ser compactado.

        Args:
            messages: Lista de mensagens

        Returns:
            True se uso >= threshold
        """
        window = self.get_context_window(messages)

        if window.needs_compaction:
            logger.info(
                f"Context compaction needed: {window.usage_percent:.1f}% used "
                f"({window.total_tokens:,}/{window.limit:,} tokens)"
            )

        return window.needs_compaction

    async def compact(
        self,
        messages: List[Dict[str, Any]],
        preserve_recent: int = 10,
        preserve_instructions: bool = True,
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        Compacta o contexto das mensagens.

        Estratégia em 2 passos:
        1. Primeiro: limpar tool_results antigos
        2. Se ainda precisar: resumir mensagens antigas

        Args:
            messages: Lista de mensagens
            preserve_recent: Número de mensagens recentes a preservar
            preserve_instructions: Se deve preservar instruções do sistema

        Returns:
            Tuple de (mensagens compactadas, resumo gerado)
        """
        if not messages:
            return messages, ""

        original_tokens = self.count_tokens(messages)
        logger.info(f"Starting compaction: {len(messages)} messages, {original_tokens:,} tokens")

        # Passo 1: Limpar tool_results antigos
        step1_messages = self._clear_old_tool_results(messages, keep_recent=preserve_recent)
        step1_tokens = self.count_tokens(step1_messages)

        logger.info(
            f"Step 1 (clear tool_results): {step1_tokens:,} tokens "
            f"(saved {original_tokens - step1_tokens:,})"
        )

        # Verificar se ainda precisa de mais compactação
        if not self._still_needs_compaction(step1_tokens):
            self._record_compaction()
            return step1_messages, ""

        # Passo 2: Resumir mensagens antigas
        compacted, summary = await self._summarize_old_messages(
            step1_messages,
            preserve_recent=preserve_recent,
            preserve_instructions=preserve_instructions,
        )

        final_tokens = self.count_tokens(compacted)
        logger.info(
            f"Step 2 (summarize): {final_tokens:,} tokens "
            f"(total saved: {original_tokens - final_tokens:,})"
        )

        self._record_compaction()
        return compacted, summary

    def _still_needs_compaction(self, tokens: int) -> bool:
        """Verifica se ainda precisa de mais compactação após step 1."""
        usage = tokens / self.limit
        return usage >= self.threshold

    def _record_compaction(self):
        """Registra que uma compactação foi realizada."""
        self._last_compaction = datetime.utcnow()
        self._compaction_count += 1

    def _clear_old_tool_results(
        self,
        messages: List[Dict[str, Any]],
        keep_recent: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Remove tool_results de mensagens antigas, mantendo apenas um resumo.

        Args:
            messages: Lista de mensagens
            keep_recent: Número de mensagens recentes a preservar intactas

        Returns:
            Lista de mensagens com tool_results antigos limpos
        """
        if len(messages) <= keep_recent:
            return messages

        result = []
        old_messages = messages[:-keep_recent] if keep_recent > 0 else messages
        recent_messages = messages[-keep_recent:] if keep_recent > 0 else []

        for msg in old_messages:
            role = msg.get("role")
            content = msg.get("content")

            # Mensagens de tool (formato OpenAI)
            if role == "tool":
                # Simplificar para apenas indicar que tool foi executada
                tool_call_id = msg.get("tool_call_id", "unknown")
                result.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": "[Tool result truncated for context management]",
                })
                continue

            # Content com tool_result (formato Anthropic)
            if isinstance(content, list):
                new_content = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "tool_result":
                        # Truncar resultado mantendo ID
                        new_content.append({
                            "type": "tool_result",
                            "tool_use_id": item.get("tool_use_id", "unknown"),
                            "content": "[Result truncated for context management]",
                        })
                    else:
                        new_content.append(item)
                result.append({**msg, "content": new_content})
            else:
                result.append(msg)

        # Adicionar mensagens recentes intactas
        result.extend(recent_messages)

        return result

    async def _summarize_old_messages(
        self,
        messages: List[Dict[str, Any]],
        preserve_recent: int = 10,
        preserve_instructions: bool = True,
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        Resume mensagens antigas em um único bloco de contexto.

        Args:
            messages: Lista de mensagens
            preserve_recent: Mensagens recentes a preservar
            preserve_instructions: Se deve preservar system messages

        Returns:
            Tuple de (mensagens compactadas, resumo gerado)
        """
        if len(messages) <= preserve_recent:
            return messages, ""

        # Separar mensagens
        system_messages = []
        old_messages = []
        recent_messages = []

        if preserve_instructions:
            system_messages = [m for m in messages if m.get("role") == "system"]
            non_system = [m for m in messages if m.get("role") != "system"]

            if len(non_system) > preserve_recent:
                old_messages = non_system[:-preserve_recent]
                recent_messages = non_system[-preserve_recent:]
            else:
                recent_messages = non_system
        else:
            if len(messages) > preserve_recent:
                old_messages = messages[:-preserve_recent]
                recent_messages = messages[-preserve_recent:]
            else:
                recent_messages = messages

        # Se não há mensagens antigas para resumir
        if not old_messages:
            return messages, ""

        # Gerar resumo das mensagens antigas
        summary = await self._generate_summary(old_messages)

        # Construir novo contexto
        result = list(system_messages)  # System messages primeiro

        # Adicionar resumo como mensagem de contexto
        if summary:
            result.append({
                "role": "user",
                "content": f"""[RESUMO DO CONTEXTO ANTERIOR]

O seguinte é um resumo das mensagens anteriores desta conversa, compactado para economizar tokens:

{summary}

[FIM DO RESUMO - CONTINUE A PARTIR DAQUI]""",
            })
            result.append({
                "role": "assistant",
                "content": "Entendido. Tenho o contexto do que foi discutido anteriormente. Como posso ajudar?",
            })

        # Adicionar mensagens recentes
        result.extend(recent_messages)

        return result, summary

    async def _generate_summary(self, messages: List[Dict[str, Any]]) -> str:
        """
        Gera um resumo das mensagens usando Claude Haiku (modelo rápido).

        O resumo preserva:
        - Decisões tomadas
        - Informações críticas do caso
        - Contexto necessário para continuar

        Args:
            messages: Lista de mensagens para resumir

        Returns:
            Resumo em texto
        """
        if not messages:
            return ""

        # Montar texto das mensagens para resumo
        messages_text = self._format_messages_for_summary(messages)

        # Prompt para geração do resumo
        summary_prompt = f"""Você é um assistente jurídico resumindo uma conversa anterior.

Gere um resumo CONCISO e ESTRUTURADO da conversa abaixo, preservando:
1. **Decisões tomadas**: O que foi decidido ou acordado
2. **Informações críticas do caso**: Fatos, datas, valores, partes envolvidas
3. **Contexto necessário**: O que é essencial para continuar a conversa
4. **Ações pendentes**: O que ainda precisa ser feito

NÃO inclua:
- Saudações ou formalidades
- Detalhes irrelevantes
- Texto redundante

CONVERSA A RESUMIR:
{messages_text}

RESUMO (em português, máximo 500 palavras):"""

        # Tentar gerar resumo via Anthropic
        summary = await self._call_anthropic_for_summary(summary_prompt)

        if not summary:
            # Fallback: resumo básico extraindo principais pontos
            summary = self._generate_fallback_summary(messages)

        return summary

    def _format_messages_for_summary(self, messages: List[Dict[str, Any]]) -> str:
        """Formata mensagens para o prompt de resumo."""
        parts = []

        for i, msg in enumerate(messages, 1):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            # Normalizar role
            role_display = {
                "user": "Usuário",
                "assistant": "Assistente",
                "system": "Sistema",
                "tool": "Ferramenta",
            }.get(role, role)

            # Extrair texto do content
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                text_parts = []
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            text_parts.append(item.get("text", ""))
                        elif item.get("type") == "tool_result":
                            text_parts.append(f"[Resultado de ferramenta]")
                        elif item.get("type") == "tool_use":
                            text_parts.append(f"[Chamada de ferramenta: {item.get('name', 'unknown')}]")
                    elif isinstance(item, str):
                        text_parts.append(item)
                text = "\n".join(text_parts)
            else:
                text = str(content)

            # Truncar textos muito longos
            if len(text) > 1000:
                text = text[:1000] + "..."

            parts.append(f"[{role_display}]: {text}")

        return "\n\n".join(parts)

    async def _call_anthropic_for_summary(self, prompt: str) -> str:
        """Chama Anthropic API para gerar resumo."""
        # Se cliente foi injetado, usar ele
        if self._anthropic_client:
            try:
                response = await self._anthropic_client.messages.create(
                    model=SUMMARY_MODEL,
                    max_tokens=1024,
                    messages=[{"role": "user", "content": prompt}],
                )
                return response.content[0].text if response.content else ""
            except Exception as e:
                logger.warning(f"Anthropic summary call failed: {e}")
                return ""

        # Tentar importar e criar cliente
        try:
            import anthropic

            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                logger.warning("ANTHROPIC_API_KEY not set, using fallback summary")
                return ""

            client = anthropic.AsyncAnthropic(api_key=api_key)

            response = await client.messages.create(
                model=SUMMARY_MODEL,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )

            return response.content[0].text if response.content else ""

        except ImportError:
            logger.warning("anthropic package not installed, using fallback summary")
            return ""
        except Exception as e:
            logger.warning(f"Failed to generate summary via Anthropic: {e}")
            return ""

    def _generate_fallback_summary(self, messages: List[Dict[str, Any]]) -> str:
        """
        Gera resumo básico sem usar LLM.
        Extrai pontos principais baseado em heurísticas.
        """
        user_points = []
        assistant_points = []

        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")

            if isinstance(content, list):
                text_parts = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text_parts.append(item.get("text", ""))
                content = " ".join(text_parts)

            if not isinstance(content, str):
                continue

            # Extrair primeira sentença ou até 200 chars
            first_sentence = content.split(".")[0][:200]
            if not first_sentence.strip():
                continue

            if role == "user":
                user_points.append(f"- {first_sentence.strip()}")
            elif role == "assistant":
                assistant_points.append(f"- {first_sentence.strip()}")

        # Limitar número de pontos
        user_points = user_points[:5]
        assistant_points = assistant_points[:5]

        parts = []
        if user_points:
            parts.append("**Solicitações do usuário:**")
            parts.extend(user_points)

        if assistant_points:
            parts.append("\n**Respostas do assistente:**")
            parts.extend(assistant_points)

        return "\n".join(parts) if parts else "Conversa anterior resumida."

    def estimate_compaction_savings(
        self,
        messages: List[Dict[str, Any]],
        preserve_recent: int = 10,
    ) -> Dict[str, Any]:
        """
        Estima economia de tokens com compactação.

        Args:
            messages: Lista de mensagens
            preserve_recent: Mensagens recentes a preservar

        Returns:
            Dict com métricas de economia estimada
        """
        current_tokens = self.count_tokens(messages)

        # Simular passo 1 (limpar tool_results)
        step1_messages = self._clear_old_tool_results(messages, keep_recent=preserve_recent)
        step1_tokens = self.count_tokens(step1_messages)

        # Estimar passo 2 (resumo)
        # Assumir que resumo terá ~500 tokens + mensagens recentes
        recent_msgs = messages[-preserve_recent:] if len(messages) > preserve_recent else messages
        recent_tokens = self.count_tokens(recent_msgs)
        estimated_summary_tokens = 500
        estimated_step2_tokens = recent_tokens + estimated_summary_tokens

        return {
            "current_tokens": current_tokens,
            "current_usage_percent": (current_tokens / self.limit) * 100,
            "step1_tokens": step1_tokens,
            "step1_savings": current_tokens - step1_tokens,
            "step1_savings_percent": ((current_tokens - step1_tokens) / current_tokens) * 100 if current_tokens > 0 else 0,
            "estimated_step2_tokens": estimated_step2_tokens,
            "estimated_total_savings": current_tokens - estimated_step2_tokens,
            "estimated_final_usage_percent": (estimated_step2_tokens / self.limit) * 100,
        }


# Singleton para uso global
_context_manager_instance: Optional[ContextManager] = None


def get_context_manager(
    model_name: str = "claude-4.5-opus",
    threshold: float = DEFAULT_COMPACTION_THRESHOLD,
) -> ContextManager:
    """
    Retorna instância singleton do ContextManager.

    Args:
        model_name: Nome do modelo
        threshold: Threshold de compactação

    Returns:
        Instância do ContextManager
    """
    global _context_manager_instance

    if _context_manager_instance is None:
        _context_manager_instance = ContextManager(
            model_name=model_name,
            threshold=threshold,
        )

    return _context_manager_instance
