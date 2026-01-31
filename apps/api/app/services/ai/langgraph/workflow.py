"""
LangGraph Workflow - Wrapper do workflow juridico existente.

Este modulo serve como camada de abstracao sobre o langgraph_legal_workflow.py
existente, permitindo melhorias incrementais sem quebrar o codigo atual.

Integra o legal_workflow_app compilado, fazendo streaming via astream()
com stream_mode="updates" e emitindo SSEEvents padronizados para cada
transicao de node do grafo.
"""

from typing import Dict, Any, AsyncGenerator, Optional
import logging
import time
import traceback

from app.services.ai.shared.sse_protocol import SSEEvent, SSEEventType

logger = logging.getLogger(__name__)


class LangGraphWorkflow:
    """
    Wrapper do workflow LangGraph existente (legal_workflow_app).

    Responsavel por:
    - Abstrair o workflow existente
    - Streaming de SSEEvents via astream(stream_mode="updates")
    - Obter estado final via get_state()
    - Permitir injecao de melhorias (context manager, checkpoints)
    - Padronizar interface de execucao
    """

    def __init__(
        self,
        context_manager: Optional[Any] = None,
        checkpoint_manager: Optional[Any] = None,
    ):
        """
        Inicializa o wrapper do workflow.

        Args:
            context_manager: Gerenciador de contexto (compactacao)
            checkpoint_manager: Gerenciador de checkpoints
        """
        self.context_manager = context_manager
        self.checkpoint_manager = checkpoint_manager
        self._workflow_app = None

    def _get_workflow_app(self):
        """
        Importa e retorna o legal_workflow_app compilado.
        Usa import lazy para evitar circular imports e falhas no startup.
        """
        if self._workflow_app is None:
            from app.services.ai.langgraph_legal_workflow import legal_workflow_app
            self._workflow_app = legal_workflow_app
        return self._workflow_app

    async def execute(
        self,
        input_data: Dict[str, Any],
    ) -> AsyncGenerator[SSEEvent, None]:
        """
        Executa o workflow LangGraph fazendo streaming de SSEEvents.

        Utiliza astream() com stream_mode="updates" para receber
        atualizacoes incrementais de cada node do grafo, emitindo
        NODE_START e NODE_COMPLETE para cada transicao. Ao final,
        obtem o estado completo via get_state() e emite DONE.

        Args:
            input_data: Dados de entrada incluindo:
                - input_text / query: Pergunta/instrucao do usuario
                - job_id: ID do job
                - mode: Modo (chat, minuta, etc.)
                - selected_models: Modelos selecionados
                - case_bundle / case_bundle_text_pack: Dados do caso
                - tese: Tese principal
                - E demais campos do DocumentState

        Yields:
            SSEEvent para cada evento do workflow
        """
        job_id = input_data.get("job_id", "")
        start_time = time.monotonic()

        # Emite evento de inicio do workflow
        yield SSEEvent(
            type=SSEEventType.NODE_START,
            data={
                "node": "workflow",
                "input_keys": list(input_data.keys()),
                "job_id": job_id,
            },
            job_id=job_id,
            phase="langgraph",
            node="workflow",
        )

        try:
            app = self._get_workflow_app()

            # Preparar config para o checkpointer do LangGraph
            # thread_id e necessario para o checkpointer funcionar
            config = {
                "configurable": {
                    "thread_id": job_id or f"workflow-{int(time.time())}",
                }
            }

            # Compactar contexto se context_manager disponivel
            if self.context_manager and input_data.get("input_text"):
                try:
                    input_data = await self._maybe_compact_context(input_data)
                except Exception as compact_err:
                    logger.warning(
                        f"Erro na compactacao de contexto (ignorando): {compact_err}"
                    )

            # Stream com astream(stream_mode="updates")
            # Cada update e um dict {node_name: state_update}
            nodes_executed = []

            async for update in app.astream(
                input_data,
                config=config,
                stream_mode="updates",
            ):
                for node_name, node_output in update.items():
                    nodes_executed.append(node_name)

                    # NODE_START
                    yield SSEEvent(
                        type=SSEEventType.NODE_START,
                        data={
                            "node": node_name,
                            "sequence": len(nodes_executed),
                        },
                        job_id=job_id,
                        phase="langgraph",
                        node=node_name,
                    )

                    # Emitir tokens parciais se o node produziu conteudo
                    partial_content = self._extract_partial_content(
                        node_name, node_output
                    )
                    if partial_content:
                        yield SSEEvent(
                            type=SSEEventType.TOKEN,
                            data={
                                "content": partial_content,
                                "node": node_name,
                            },
                            job_id=job_id,
                            phase="langgraph",
                            node=node_name,
                        )

                    # Emitir outline se o node produziu outline
                    if node_name == "gen_outline" and isinstance(node_output, dict):
                        outline = node_output.get("outline") or node_output.get(
                            "sections_outline"
                        )
                        if outline:
                            yield SSEEvent(
                                type=SSEEventType.OUTLINE,
                                data={"outline": outline},
                                job_id=job_id,
                                phase="langgraph",
                                node=node_name,
                            )

                    # Emitir HIL se o node requer intervencao humana
                    if self._is_hil_node(node_name) and isinstance(node_output, dict):
                        hil_data = node_output.get("hil_payload") or node_output
                        yield SSEEvent(
                            type=SSEEventType.HIL_REQUIRED,
                            data={
                                "node": node_name,
                                "payload": self._safe_serialize(hil_data),
                            },
                            job_id=job_id,
                            phase="langgraph",
                            node=node_name,
                        )

                    # Emitir audit_done se o node e audit
                    if node_name == "audit" and isinstance(node_output, dict):
                        yield SSEEvent(
                            type=SSEEventType.AUDIT_DONE,
                            data={
                                "issues": node_output.get("audit_issues", []),
                                "score": node_output.get("audit_score"),
                            },
                            job_id=job_id,
                            phase="langgraph",
                            node=node_name,
                        )

                    # NODE_COMPLETE
                    yield SSEEvent(
                        type=SSEEventType.NODE_COMPLETE,
                        data={
                            "node": node_name,
                            "sequence": len(nodes_executed),
                            "output_keys": (
                                list(node_output.keys())
                                if isinstance(node_output, dict)
                                else []
                            ),
                        },
                        job_id=job_id,
                        phase="langgraph",
                        node=node_name,
                    )

            # Obter estado final via get_state()
            final_snapshot = app.get_state(config)
            final_state = (
                final_snapshot.values
                if hasattr(final_snapshot, "values")
                else {}
            )

            # Extrair documento final
            final_document = self._extract_final_document(final_state)

            elapsed = time.monotonic() - start_time

            # Criar checkpoint se manager disponivel
            checkpoint_id = ""
            if self.checkpoint_manager:
                try:
                    checkpoint_id = await self.create_checkpoint(final_state)
                except Exception as ckpt_err:
                    logger.warning(f"Erro ao criar checkpoint: {ckpt_err}")

            # Emitir DONE
            yield SSEEvent(
                type=SSEEventType.DONE,
                data={
                    "final_text": final_document,
                    "nodes_executed": nodes_executed,
                    "total_nodes": len(nodes_executed),
                    "elapsed_seconds": round(elapsed, 2),
                    "checkpoint_id": checkpoint_id,
                    "outline": final_state.get("outline", []),
                    "sections_count": len(
                        final_state.get("processed_sections", [])
                    ),
                },
                job_id=job_id,
                phase="langgraph",
                node="workflow",
            )

            # NODE_COMPLETE do workflow inteiro
            yield SSEEvent(
                type=SSEEventType.NODE_COMPLETE,
                data={
                    "node": "workflow",
                    "status": "completed",
                    "nodes_executed": nodes_executed,
                    "elapsed_seconds": round(elapsed, 2),
                },
                job_id=job_id,
                phase="langgraph",
                node="workflow",
            )

        except Exception as e:
            elapsed = time.monotonic() - start_time
            logger.exception("Erro no workflow LangGraph")
            yield SSEEvent(
                type=SSEEventType.ERROR,
                data={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "node": "workflow",
                    "traceback": traceback.format_exc()[-500:],
                    "elapsed_seconds": round(elapsed, 2),
                },
                job_id=job_id,
                phase="langgraph",
                node="workflow",
            )

    def _extract_partial_content(
        self, node_name: str, node_output: Any
    ) -> str:
        """
        Extrai conteudo parcial do output de um node para streaming.

        Procura campos comuns que contenham texto gerado pelo node.
        """
        if not isinstance(node_output, dict):
            return ""

        # Campos que tipicamente contem conteudo textual
        content_keys = [
            "full_document",
            "debate_result",
            "refined_text",
            "section_content",
            "proposal_text",
            "corrections_text",
            "style_refined_text",
            "committee_review",
            "quality_report",
        ]

        for key in content_keys:
            val = node_output.get(key)
            if val and isinstance(val, str) and len(val) > 10:
                # Retornar apenas um preview para nao sobrecarregar o stream
                return val[:200] + ("..." if len(val) > 200 else "")

        return ""

    def _is_hil_node(self, node_name: str) -> bool:
        """Verifica se o node e um ponto de Human-in-the-Loop."""
        hil_nodes = {
            "outline_hil",
            "divergence_hil",
            "section_hil",
            "evaluate_hil",
            "correction_hil",
            "finalize_hil",
        }
        return node_name in hil_nodes

    def _extract_final_document(self, state: Dict[str, Any]) -> str:
        """
        Extrai o documento final do estado do workflow.

        Tenta full_document primeiro, depois concatena sections.
        """
        final_doc = state.get("full_document", "")
        if final_doc:
            return final_doc

        # Fallback: concatenar processed_sections
        sections = state.get("processed_sections", [])
        if sections:
            parts = []
            for s in sections:
                if isinstance(s, dict):
                    parts.append(s.get("content", ""))
                elif isinstance(s, str):
                    parts.append(s)
            return "\n\n".join(p for p in parts if p)

        return ""

    def _safe_serialize(self, data: Any) -> Any:
        """Serializa dados de forma segura para JSON, truncando valores grandes."""
        if isinstance(data, dict):
            result = {}
            for k, v in data.items():
                if isinstance(v, str) and len(v) > 1000:
                    result[k] = v[:1000] + "...[truncado]"
                elif isinstance(v, (dict, list)):
                    result[k] = self._safe_serialize(v)
                else:
                    result[k] = v
            return result
        elif isinstance(data, list):
            return [self._safe_serialize(item) for item in data[:20]]
        return data

    async def _maybe_compact_context(
        self, input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compacta o contexto de entrada se necessario.

        Usa o context_manager para reduzir o tamanho do input
        antes de enviar para o workflow.
        """
        if not self.context_manager:
            return input_data

        input_text = input_data.get("input_text", "")
        if len(input_text) > 50000:  # Compactar apenas textos muito grandes
            compacted = await self.context_manager.compact(input_text)
            input_data["input_text"] = compacted
            logger.info(
                f"Contexto compactado: {len(input_text)} -> {len(compacted)} chars"
            )

        return input_data

    async def create_checkpoint(self, state: Dict[str, Any]) -> str:
        """
        Cria checkpoint do estado atual.

        Args:
            state: Estado atual do workflow

        Returns:
            ID do checkpoint criado
        """
        if self.checkpoint_manager:
            return await self.checkpoint_manager.create(state)
        return ""

    async def restore_checkpoint(self, checkpoint_id: str) -> Dict[str, Any]:
        """
        Restaura estado de um checkpoint.

        Args:
            checkpoint_id: ID do checkpoint

        Returns:
            Estado restaurado
        """
        if self.checkpoint_manager:
            return await self.checkpoint_manager.restore(checkpoint_id)
        return {}
