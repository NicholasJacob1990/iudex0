"""
ParallelExecutor - Executa Claude Agent e LangGraph Debate em paralelo.

Estratégia:
1. Agent faz research + draft inicial (autonomamente)
2. Debate models validam/refinam em paralelo
3. Merge com resolução de conflitos (usando LLM como juiz)

Responsável por:
- Executar Claude Agent + LangGraph Debate em paralelo
- Coordenar timeouts e fallbacks
- Coletar resultados de múltiplas fontes
- Fazer merge inteligente com resolução de conflitos via LLM
"""

import asyncio
import os
import re
import json
import time
from typing import List, Dict, Any, AsyncGenerator, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging

from app.services.ai.shared.sse_protocol import (
    SSEEvent,
    SSEEventType,
    create_sse_event,
    token_event,
    thinking_event,
    done_event,
    error_event,
)
from app.services.job_manager import job_manager


def init_vertex_client():
    """Wrapper to allow patching in tests."""
    from app.services.ai.agent_clients import init_vertex_client as _init_vertex_client
    return _init_vertex_client()


async def call_vertex_gemini_async(*args, **kwargs):
    """Wrapper to allow patching in tests."""
    from app.services.ai.agent_clients import call_vertex_gemini_async as _call_vertex_gemini_async
    return await _call_vertex_gemini_async(*args, **kwargs)


def get_api_model_name(model_name: str) -> str:
    """Wrapper to allow patching in tests."""
    from app.services.ai.model_registry import get_api_model_name as _get_api_model_name
    return _get_api_model_name(model_name)

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ParallelResult:
    """
    Resultado do ParallelExecutor com outputs de Agent e Debate.

    Attributes:
        agent_output: Output do Claude Agent (research + draft)
        debate_output: Output do LangGraph Debate
        merged_content: Conteúdo final após merge
        divergences: Lista de divergências detectadas
        conflicts_resolved: Quantidade de conflitos resolvidos
        merge_reasoning: Raciocínio do juiz LLM para o merge
        agent_duration_ms: Tempo de execução do Agent
        debate_duration_ms: Tempo de execução do Debate
        merge_duration_ms: Tempo de execução do merge
        total_duration_ms: Tempo total
        success: Se a execução foi bem-sucedida
        error: Mensagem de erro (se houver)
    """
    agent_output: str = ""
    debate_output: str = ""
    merged_content: str = ""
    divergences: List[Dict[str, Any]] = field(default_factory=list)
    conflicts_resolved: int = 0
    merge_reasoning: str = ""
    agent_duration_ms: int = 0
    debate_duration_ms: int = 0
    merge_duration_ms: int = 0
    total_duration_ms: int = 0
    success: bool = True
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "agent_output": self.agent_output,
            "debate_output": self.debate_output,
            "merged_content": self.merged_content,
            "divergences": self.divergences,
            "conflicts_resolved": self.conflicts_resolved,
            "merge_reasoning": self.merge_reasoning,
            "agent_duration_ms": self.agent_duration_ms,
            "debate_duration_ms": self.debate_duration_ms,
            "merge_duration_ms": self.merge_duration_ms,
            "total_duration_ms": self.total_duration_ms,
            "success": self.success,
            "error": self.error,
        }


@dataclass
class ExecutionContext:
    """
    Contexto de execução para o ParallelExecutor.

    Attributes:
        job_id: ID do job
        prompt: Prompt principal
        rag_context: Contexto RAG (documentos)
        thesis: Tese/objetivo central
        mode: Modo de documento (minuta, parecer, etc.)
        section_title: Título da seção sendo processada
        previous_sections: Seções anteriores processadas
        temperature: Temperatura para LLM calls
    """
    job_id: str
    prompt: str
    rag_context: str = ""
    thesis: str = ""
    mode: str = "minuta"
    section_title: str = ""
    previous_sections: List[str] = field(default_factory=list)
    temperature: float = 0.3


# =============================================================================
# MERGE PROMPTS
# =============================================================================

MERGE_JUDGE_SYSTEM = """Você é um Desembargador Sênior especialista em revisão de documentos jurídicos.
Sua tarefa é analisar duas versões de um texto jurídico e criar uma versão final consolidada.

REGRAS OBRIGATÓRIAS:
1. Identifique as seções/trechos em comum entre as versões
2. Detecte divergências significativas (argumentos diferentes, citações conflitantes)
3. Para cada divergência, decida qual versão está mais correta ou combine o melhor de ambas
4. Preserve TODAS as citações no formato [TIPO - Doc. X, p. Y]
5. NÃO invente fatos, leis ou jurisprudências
6. Mantenha coerência com a tese central
7. Se houver dúvida sobre um fato, marque como [[PENDENTE: verificar no Doc X]]

FORMATO DE RESPOSTA (JSON válido):
{
  "merged_content": "texto final consolidado em markdown",
  "divergences": [
    {
      "topic": "tema da divergência",
      "agent_version": "trecho do agent",
      "debate_version": "trecho do debate",
      "resolution": "como foi resolvido",
      "chosen_source": "agent|debate|combined"
    }
  ],
  "reasoning": "explicação geral das decisões tomadas",
  "quality_assessment": {
    "completeness": 0-10,
    "consistency": 0-10,
    "citations": 0-10
  }
}"""

MERGE_JUDGE_PROMPT = """## CONTEXTO
Tipo de documento: {{ mode }}
Tese/Objetivo: {{ thesis }}
Seção: {{ section_title }}

## VERSÃO DO AGENT (Claude autônomo com tools)
{{ agent_output }}

## VERSÃO DO DEBATE (Multi-modelo consensual)
{{ debate_output }}

## CONTEXTO FACTUAL (RAG - VERDADE ABSOLUTA)
{{ rag_context }}

## INSTRUÇÃO
Analise as duas versões acima e produza uma versão final consolidada.
Identifique divergências e resolva conflitos priorizando:
1. Correção factual (baseada no RAG)
2. Citações completas e verificáveis
3. Coerência argumentativa
4. Qualidade da redação jurídica

Responda APENAS com o JSON especificado, sem markdown code blocks."""


# =============================================================================
# PARALLEL EXECUTOR
# =============================================================================

class ParallelExecutor:
    """
    Executor paralelo que coordena Claude Agent + LangGraph Debate.

    Estratégia:
    1. Agent faz research + draft inicial (autonomamente)
    2. Debate models validam/refinam em paralelo
    3. Merge com resolução de conflitos (usando LLM como juiz)
    """

    DEFAULT_TIMEOUT = 300  # 5 minutos
    DEFAULT_MERGE_MODEL = "gemini-3-flash"  # Modelo para merge/judge

    def __init__(
        self,
        timeout: int = DEFAULT_TIMEOUT,
        fail_fast: bool = False,
        merge_model: Optional[str] = None,
    ):
        """
        Inicializa o executor paralelo.

        Args:
            timeout: Timeout em segundos para execução
            fail_fast: Se True, falha ao primeiro erro
            merge_model: Modelo LLM para fazer o merge final
        """
        self.timeout = timeout
        self.fail_fast = fail_fast
        self.merge_model = merge_model or os.getenv(
            "PARALLEL_MERGE_MODEL",
            self.DEFAULT_MERGE_MODEL
        )
        self._tasks: Dict[str, asyncio.Task] = {}
        self._agent_output: str = ""
        self._debate_output: str = ""
        self._agent_events: List[SSEEvent] = []
        self._debate_events: List[SSEEvent] = []

    async def execute(
        self,
        prompt: str,
        agent_models: List[str],
        debate_models: List[str],
        context: ExecutionContext,
        mode: str = "parallel",
    ) -> AsyncGenerator[SSEEvent, None]:
        """
        Executa Agent e Debate em paralelo, emitindo eventos SSE.

        Args:
            prompt: Prompt principal para geração
            agent_models: Modelos para o Claude Agent (geralmente ["claude-agent"])
            debate_models: Modelos para o LangGraph Debate
            context: Contexto de execução
            mode: Modo de execução ("parallel", "agent_first", "debate_first")

        Yields:
            SSEEvent para cada evento gerado
        """
        start_time = time.time()
        job_id = context.job_id

        # Emite evento de início paralelo
        yield create_sse_event(
            SSEEventType.PARALLEL_START,
            {
                "mode": mode,
                "agent_models": agent_models,
                "debate_models": debate_models,
                "timeout": self.timeout,
            },
            job_id=job_id,
            phase="parallel_start",
        )

        if job_id:
            job_manager.emit_event(
                job_id,
                "parallel_start",
                {
                    "mode": mode,
                    "agent_models": agent_models,
                    "debate_models": debate_models,
                },
                phase="orchestration",
            )

        # Cria queues para eventos
        agent_queue: asyncio.Queue[SSEEvent] = asyncio.Queue()
        debate_queue: asyncio.Queue[SSEEvent] = asyncio.Queue()

        # Inicia execução paralela
        agent_task = asyncio.create_task(
            self._run_agent(prompt, context, agent_queue)
        )
        debate_task = asyncio.create_task(
            self._run_debate(prompt, debate_models, context, debate_queue)
        )

        self._tasks["agent"] = agent_task
        self._tasks["debate"] = debate_task

        # Coleta eventos de ambos em paralelo
        agent_done = False
        debate_done = False

        try:
            while not (agent_done and debate_done):
                # Coleta eventos de ambas as queues com timeout
                done_tasks = set()

                # Verifica agent queue
                if not agent_done:
                    try:
                        event = await asyncio.wait_for(
                            agent_queue.get(),
                            timeout=0.1  # Poll rápido
                        )
                        # Marca source e emite
                        event.agent = "agent"
                        event.data["_source"] = "agent"
                        self._agent_events.append(event)

                        # Acumula output do agent
                        if event.type == SSEEventType.TOKEN:
                            token = event.data.get("token", "")
                            self._agent_output += token

                        yield event

                        # Verifica se agent terminou
                        if event.type == SSEEventType.DONE:
                            agent_done = True
                            self._agent_output = event.data.get("final_text", self._agent_output)
                        elif event.type == SSEEventType.ERROR:
                            if self.fail_fast:
                                raise Exception(f"Agent error: {event.data.get('error')}")
                            agent_done = True

                    except asyncio.TimeoutError:
                        pass
                    except asyncio.CancelledError:
                        agent_done = True

                # Verifica debate queue
                if not debate_done:
                    try:
                        event = await asyncio.wait_for(
                            debate_queue.get(),
                            timeout=0.1
                        )
                        # Marca source e emite
                        event.agent = "debate"
                        event.data["_source"] = "debate"
                        self._debate_events.append(event)

                        # Acumula output do debate
                        if event.type == SSEEventType.TOKEN:
                            token = event.data.get("token", "")
                            self._debate_output += token

                        yield event

                        # Verifica se debate terminou
                        if event.type == SSEEventType.DONE:
                            debate_done = True
                            self._debate_output = event.data.get("final_text", self._debate_output)
                        elif event.type == SSEEventType.ERROR:
                            if self.fail_fast:
                                raise Exception(f"Debate error: {event.data.get('error')}")
                            debate_done = True

                    except asyncio.TimeoutError:
                        pass
                    except asyncio.CancelledError:
                        debate_done = True

                # Verifica timeout global
                elapsed = time.time() - start_time
                if elapsed > self.timeout:
                    logger.warning(f"Timeout global após {elapsed:.1f}s")
                    yield error_event(
                        job_id,
                        f"Timeout após {int(elapsed)}s",
                        error_type="timeout",
                        recoverable=False,
                    )
                    break

        except Exception as e:
            logger.exception("Erro na execução paralela")
            yield error_event(
                job_id,
                str(e),
                error_type="execution_error",
                recoverable=False,
            )
        finally:
            # Cancela tasks pendentes
            for task_name, task in self._tasks.items():
                if not task.done():
                    logger.info(f"Cancelando task: {task_name}")
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            self._tasks.clear()

        # Calcula durações
        agent_duration = int((time.time() - start_time) * 1000)
        debate_duration = agent_duration  # Aproximado (paralelo)

        # Fase de merge
        yield create_sse_event(
            SSEEventType.PARALLEL_START,
            {
                "phase": "merge",
                "agent_output_length": len(self._agent_output),
                "debate_output_length": len(self._debate_output),
            },
            job_id=job_id,
            phase="merge_start",
        )

        # Executa merge
        merge_start = time.time()
        merge_result = await self._merge_results(
            self._agent_output,
            self._debate_output,
            context,
        )
        merge_duration = int((time.time() - merge_start) * 1000)

        # Emite eventos de divergências encontradas
        if merge_result.divergences:
            for div in merge_result.divergences:
                yield create_sse_event(
                    SSEEventType.THINKING,
                    {
                        "type": "divergence",
                        "topic": div.get("topic", ""),
                        "resolution": div.get("resolution", ""),
                        "chosen_source": div.get("chosen_source", ""),
                    },
                    job_id=job_id,
                    phase="merge",
                )

        # Emite resultado final do merge
        total_duration = int((time.time() - start_time) * 1000)

        result = ParallelResult(
            agent_output=self._agent_output,
            debate_output=self._debate_output,
            merged_content=merge_result.merged_content,
            divergences=merge_result.divergences,
            conflicts_resolved=merge_result.conflicts_resolved,
            merge_reasoning=merge_result.merge_reasoning,
            agent_duration_ms=agent_duration,
            debate_duration_ms=debate_duration,
            merge_duration_ms=merge_duration,
            total_duration_ms=total_duration,
            success=merge_result.success,
            error=merge_result.error,
        )

        yield create_sse_event(
            SSEEventType.PARALLEL_COMPLETE,
            {
                "success": result.success,
                "conflicts_resolved": result.conflicts_resolved,
                "total_duration_ms": result.total_duration_ms,
                "divergences_count": len(result.divergences),
            },
            job_id=job_id,
            phase="parallel_complete",
        )

        # Evento done com resultado completo
        yield done_event(
            job_id,
            final_text=result.merged_content,
            metadata={
                "parallel_result": result.to_dict(),
            },
            phase="done",
        )

        if job_id:
            job_manager.emit_event(
                job_id,
                "parallel_complete",
                result.to_dict(),
                phase="orchestration",
            )

    async def _run_agent(
        self,
        prompt: str,
        context: ExecutionContext,
        event_queue: asyncio.Queue[SSEEvent],
    ) -> str:
        """
        Executa o Claude Agent de forma autônoma.

        O Agent usa suas tools para:
        - Pesquisar jurisprudência
        - Consultar legislação
        - Buscar no RAG
        - Gerar draft inicial

        Args:
            prompt: Prompt principal
            context: Contexto de execução
            event_queue: Queue para emitir eventos

        Returns:
            Output final do agent
        """
        job_id = context.job_id
        output = ""

        try:
            # Importa executor do claude_agent (lazy import)
            from app.services.ai.claude_agent.executor import ClaudeAgentExecutor

            executor = ClaudeAgentExecutor(
                job_id=job_id,
                max_iterations=50,
            )

            # Constrói prompt completo com contexto
            full_prompt = f"""## TAREFA
{prompt}

## CONTEXTO FACTUAL (RAG)
{context.rag_context}

## TESE/OBJETIVO
{context.thesis}

## MODO DE DOCUMENTO
{context.mode}

## INSTRUÇÕES
1. Use as tools disponíveis para pesquisar informações relevantes
2. Gere um draft completo e bem fundamentado
3. Cite sempre as fontes no formato [TIPO - Doc. X, p. Y]
4. Marque informações que precisam de verificação como [[PENDENTE: ...]]
"""

            # Emite evento de início do agent
            await event_queue.put(create_sse_event(
                SSEEventType.AGENT_START,
                {"prompt_length": len(full_prompt)},
                job_id=job_id,
                phase="agent",
            ))

            # Executa agent e coleta eventos
            async for event in executor.execute(full_prompt):
                await event_queue.put(event)

                # Acumula output
                if event.type == SSEEventType.TOKEN:
                    output += event.data.get("token", "")
                elif event.type == SSEEventType.DONE:
                    output = event.data.get("final_text", output)

            # Emite evento de conclusão
            await event_queue.put(done_event(
                job_id,
                final_text=output,
                phase="agent",
            ))

        except ImportError:
            # Fallback se ClaudeAgentExecutor não existir ainda
            logger.warning("ClaudeAgentExecutor não disponível, usando fallback")
            output = await self._agent_fallback(prompt, context, event_queue)

        except Exception as e:
            logger.exception("Erro no agent")
            await event_queue.put(error_event(
                job_id,
                str(e),
                error_type="agent_error",
                phase="agent",
            ))

        return output

    async def _agent_fallback(
        self,
        prompt: str,
        context: ExecutionContext,
        event_queue: asyncio.Queue[SSEEvent],
    ) -> str:
        """
        Fallback para quando ClaudeAgentExecutor não está disponível.
        Usa chamada direta ao Claude.
        """
        from app.services.ai.agent_clients import (
            init_anthropic_client,
            call_anthropic_async,
        )

        job_id = context.job_id
        client = init_anthropic_client()

        if not client:
            await event_queue.put(error_event(
                job_id,
                "Cliente Anthropic não disponível",
                error_type="client_error",
            ))
            return ""

        full_prompt = f"""## TAREFA
{prompt}

## CONTEXTO FACTUAL (RAG)
{context.rag_context}

## TESE/OBJETIVO
{context.thesis}

## MODO DE DOCUMENTO
{context.mode}

Gere um texto jurídico completo e bem fundamentado.
Cite sempre as fontes no formato [TIPO - Doc. X, p. Y].
"""

        try:
            result = await call_anthropic_async(
                client,
                full_prompt,
                model="claude-sonnet-4-5",
                max_tokens=8192,
                temperature=context.temperature,
            )

            # Emite tokens simulados
            if result:
                chunk_size = 100
                for i in range(0, len(result), chunk_size):
                    chunk = result[i:i+chunk_size]
                    await event_queue.put(token_event(job_id, chunk, phase="agent"))
                    await asyncio.sleep(0.01)  # Simula streaming

            await event_queue.put(done_event(job_id, final_text=result or "", phase="agent"))
            return result or ""

        except Exception as e:
            logger.exception("Erro no agent fallback")
            await event_queue.put(error_event(job_id, str(e), error_type="agent_fallback_error"))
            return ""

    async def _run_debate(
        self,
        prompt: str,
        models: List[str],
        context: ExecutionContext,
        event_queue: asyncio.Queue[SSEEvent],
    ) -> str:
        """
        Executa o LangGraph Debate com múltiplos modelos.

        Usa o debate_subgraph existente para:
        - R1: Drafts paralelos
        - R2: Cross-critique
        - R3: Revisão
        - R4: Judge merge

        Args:
            prompt: Prompt principal
            models: Lista de modelos para o debate
            context: Contexto de execução
            event_queue: Queue para emitir eventos

        Returns:
            Output final do debate
        """
        job_id = context.job_id
        output = ""

        try:
            from app.services.ai.debate_subgraph import run_debate_for_section
            from app.services.ai.agent_clients import (
                init_openai_client,
                init_anthropic_client,
                get_gemini_client,
            )

            # Inicializa clientes
            gpt_client = init_openai_client()
            claude_client = init_anthropic_client()
            drafter = get_gemini_client()

            # Emite evento de início do debate
            await event_queue.put(create_sse_event(
                SSEEventType.RESEARCH_START,
                {"models": models, "mode": "debate"},
                job_id=job_id,
                phase="debate",
            ))

            # Determina modelos a usar
            gpt_model = "gpt-4o"
            claude_model = "claude-sonnet-4-5"
            judge_model = "gemini-3-flash"

            for m in models:
                if "gpt" in m.lower():
                    gpt_model = m
                elif "claude" in m.lower():
                    claude_model = m
                elif "gemini" in m.lower():
                    judge_model = m

            # Executa debate
            result = await run_debate_for_section(
                section_title=context.section_title or "Seção Principal",
                section_index=0,
                prompt_base=prompt,
                rag_context=context.rag_context,
                thesis=context.thesis,
                mode=context.mode,
                gpt_client=gpt_client,
                claude_client=claude_client,
                drafter=drafter,
                gpt_model=gpt_model,
                claude_model=claude_model,
                judge_model=judge_model,
                temperature=context.temperature,
                previous_sections=context.previous_sections,
                job_id=job_id,
            )

            output = result.get("merged_content", "")

            # Emite tokens do resultado
            if output:
                chunk_size = 100
                for i in range(0, len(output), chunk_size):
                    chunk = output[i:i+chunk_size]
                    await event_queue.put(token_event(job_id, chunk, phase="debate"))
                    await asyncio.sleep(0.01)

            # Emite divergências do debate
            divergencias = result.get("divergencias", "")
            if divergencias:
                await event_queue.put(create_sse_event(
                    SSEEventType.THINKING,
                    {"type": "debate_divergences", "content": divergencias},
                    job_id=job_id,
                    phase="debate",
                ))

            # Emite conclusão
            await event_queue.put(done_event(
                job_id,
                final_text=output,
                metadata={
                    "metrics": result.get("metrics", {}),
                    "drafts": result.get("drafts", {}),
                },
                phase="debate",
            ))

        except Exception as e:
            logger.exception("Erro no debate")
            await event_queue.put(error_event(
                job_id,
                str(e),
                error_type="debate_error",
                phase="debate",
            ))

        return output

    async def _merge_results(
        self,
        agent_output: str,
        debate_output: str,
        context: ExecutionContext,
    ) -> ParallelResult:
        """
        Faz merge dos outputs do Agent e Debate usando LLM como juiz.

        O merge:
        1. Identifica seções em comum
        2. Detecta divergências
        3. Usa juiz (LLM) para resolver conflitos
        4. Retorna documento final + lista de divergências

        Args:
            agent_output: Output do Claude Agent
            debate_output: Output do LangGraph Debate
            context: Contexto de execução

        Returns:
            ParallelResult com merge completo
        """
        from jinja2 import Template

        result = ParallelResult(
            agent_output=agent_output,
            debate_output=debate_output,
        )

        # Se um dos outputs está vazio, usa o outro
        if not agent_output and not debate_output:
            result.error = "Nenhum output gerado"
            result.success = False
            return result

        if not agent_output:
            result.merged_content = debate_output
            result.merge_reasoning = "Usando apenas output do debate (agent vazio)"
            return result

        if not debate_output:
            result.merged_content = agent_output
            result.merge_reasoning = "Usando apenas output do agent (debate vazio)"
            return result

        # Verifica similaridade básica
        similarity = self._calculate_similarity(agent_output, debate_output)

        if similarity > 0.95:
            # Outputs muito similares, usa o do agent (mais recente)
            result.merged_content = agent_output
            result.merge_reasoning = f"Outputs altamente similares ({similarity:.2%}), usando versão do agent"
            return result

        # Faz merge via LLM
        try:
            client = init_vertex_client()
            if not client:
                # Fallback: usa output do agent
                result.merged_content = agent_output
                result.merge_reasoning = "Cliente de merge não disponível, usando output do agent"
                return result

            # Renderiza prompt de merge
            t = Template(MERGE_JUDGE_PROMPT)
            merge_prompt = t.render(
                mode=context.mode,
                thesis=context.thesis,
                section_title=context.section_title or "Documento",
                agent_output=agent_output[:15000],  # Limita tamanho
                debate_output=debate_output[:15000],
                rag_context=context.rag_context[:10000],
            )

            # Chama LLM para merge
            api_model = get_api_model_name(self.merge_model)
            merge_response = await call_vertex_gemini_async(
                client,
                merge_prompt,
                model=api_model,
                max_tokens=8192,
                temperature=0.2,
                system_instruction=MERGE_JUDGE_SYSTEM,
            )

            # Parseia resposta JSON
            parsed = self._parse_merge_response(merge_response)

            if parsed:
                result.merged_content = parsed.get("merged_content", agent_output)
                result.divergences = parsed.get("divergences", [])
                result.conflicts_resolved = len(result.divergences)
                result.merge_reasoning = parsed.get("reasoning", "")
                result.success = True
            else:
                # Fallback se parsing falhar
                result.merged_content = agent_output
                result.merge_reasoning = "Parsing do merge falhou, usando output do agent"

        except Exception as e:
            logger.exception("Erro no merge")
            result.merged_content = agent_output
            result.merge_reasoning = f"Erro no merge ({e}), usando output do agent"

        return result

    def _parse_merge_response(self, response: str) -> Optional[Dict[str, Any]]:
        """
        Parseia resposta JSON do merge judge.

        Args:
            response: Resposta do LLM

        Returns:
            Dict parseado ou None se falhar
        """
        if not response:
            return None

        # Remove markdown code blocks se houver
        text = response.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(json)?", "", text, flags=re.IGNORECASE).strip()
            text = re.sub(r"```$", "", text).strip()

        # Tenta parsear JSON
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Tenta extrair JSON de dentro do texto
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        return None

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """
        Calcula similaridade entre dois textos usando Jaccard.

        Args:
            text1: Primeiro texto
            text2: Segundo texto

        Returns:
            Score entre 0 e 1
        """
        if not text1 or not text2:
            return 0.0

        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 or not words2:
            return 0.0

        intersection = words1.intersection(words2)
        union = words1.union(words2)

        return len(intersection) / len(union) if union else 0.0

    async def _collect_agent_events(
        self,
        task: asyncio.Task,
    ) -> AsyncGenerator[SSEEvent, None]:
        """
        Coleta eventos do agent task.

        Args:
            task: Task do agent

        Yields:
            SSEEvent do agent
        """
        for event in self._agent_events:
            yield event

    async def _collect_debate_events(
        self,
        task: asyncio.Task,
    ) -> AsyncGenerator[SSEEvent, None]:
        """
        Coleta eventos do debate task.

        Args:
            task: Task do debate

        Yields:
            SSEEvent do debate
        """
        for event in self._debate_events:
            yield event

    def cancel_all(self) -> None:
        """Cancela todas as tasks em execução."""
        for task_name, task in self._tasks.items():
            if not task.done():
                logger.info(f"Cancelando task: {task_name}")
                task.cancel()
        self._tasks.clear()


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def run_parallel_execution(
    prompt: str,
    agent_models: List[str],
    debate_models: List[str],
    context: ExecutionContext,
    timeout: int = 300,
) -> ParallelResult:
    """
    Função de conveniência para executar o ParallelExecutor.

    Args:
        prompt: Prompt principal
        agent_models: Modelos para o agent
        debate_models: Modelos para o debate
        context: Contexto de execução
        timeout: Timeout em segundos

    Returns:
        ParallelResult com resultado do merge
    """
    executor = ParallelExecutor(timeout=timeout)

    result = ParallelResult()

    async for event in executor.execute(prompt, agent_models, debate_models, context):
        if event.type == SSEEventType.DONE:
            metadata = event.data.get("metadata", {})
            parallel_result = metadata.get("parallel_result", {})
            if parallel_result:
                result = ParallelResult(**parallel_result)
        elif event.type == SSEEventType.ERROR:
            result.error = event.data.get("error", "Unknown error")
            result.success = False

    return result


def get_vertex_gemini_async():
    """Helper para importar call_vertex_gemini_async."""
    from app.services.ai.agent_clients import call_vertex_gemini_async
    return call_vertex_gemini_async
