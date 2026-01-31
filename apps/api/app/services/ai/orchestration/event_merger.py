"""
EventMerger - Merge SSE de múltiplas fontes.

Responsável por:
- Combinar eventos de múltiplos executors
- Resolver conflitos entre outputs
- Manter ordem temporal dos eventos
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
import logging

from app.services.ai.shared.sse_protocol import SSEEvent, SSEEventType

logger = logging.getLogger(__name__)


@dataclass
class MergedResult:
    """Resultado merged de múltiplos executors."""
    primary_content: str
    secondary_contents: Dict[str, str]
    conflicts: List[Dict[str, Any]]
    resolution: Optional[str] = None
    merged_at: datetime = field(default_factory=datetime.utcnow)


class EventMerger:
    """
    Combina eventos de múltiplos executors em um stream unificado.
    """

    def __init__(self):
        """Inicializa o merger."""
        self._buffers: Dict[str, List[SSEEvent]] = {}
        self._contents: Dict[str, str] = {}

    def add_event(self, executor_id: str, event: SSEEvent) -> Optional[SSEEvent]:
        """
        Adiciona evento de um executor ao buffer.

        Args:
            executor_id: ID do executor que gerou o evento
            event: Evento SSE

        Returns:
            Evento processado ou None se deve ser bufferizado
        """
        # Inicializa buffer se necessário
        if executor_id not in self._buffers:
            self._buffers[executor_id] = []
            self._contents[executor_id] = ""

        # Bufferiza tokens para merge posterior
        if event.type == SSEEventType.TOKEN:
            self._contents[executor_id] += event.data.get("content", "")
            # Repassa token com metadata do executor
            event.data["_executor_id"] = executor_id
            return event

        # Outros eventos passam direto com metadata
        event.data["_executor_id"] = executor_id
        self._buffers[executor_id].append(event)
        return event

    def merge_contents(
        self,
        primary_executor: str,
        conflict_resolution: str = "primary"
    ) -> MergedResult:
        """
        Merge conteúdos de todos os executors.

        Args:
            primary_executor: ID do executor primário
            conflict_resolution: Estratégia de resolução ("primary", "consensus", "llm")

        Returns:
            MergedResult com conteúdos combinados
        """
        primary_content = self._contents.get(primary_executor, "")
        secondary_contents = {
            k: v for k, v in self._contents.items()
            if k != primary_executor
        }

        # Detecta conflitos básicos (diferenças significativas)
        conflicts = self._detect_conflicts(primary_content, secondary_contents)

        resolution = None
        if conflicts and conflict_resolution == "primary":
            resolution = f"Usando conteúdo do executor primário: {primary_executor}"

        return MergedResult(
            primary_content=primary_content,
            secondary_contents=secondary_contents,
            conflicts=conflicts,
            resolution=resolution
        )

    def _detect_conflicts(
        self,
        primary: str,
        secondaries: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        """
        Detecta conflitos entre conteúdos.

        Args:
            primary: Conteúdo primário
            secondaries: Conteúdos secundários

        Returns:
            Lista de conflitos detectados
        """
        conflicts = []

        for executor_id, content in secondaries.items():
            # Calcula similaridade básica (pode ser melhorado com NLP)
            similarity = self._calculate_similarity(primary, content)

            if similarity < 0.7:  # Threshold de conflito
                conflicts.append({
                    "executor_id": executor_id,
                    "similarity": similarity,
                    "type": "content_divergence",
                    "preview_primary": primary[:200] if primary else "",
                    "preview_secondary": content[:200] if content else ""
                })

        return conflicts

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """
        Calcula similaridade básica entre dois textos.

        Args:
            text1: Primeiro texto
            text2: Segundo texto

        Returns:
            Score de similaridade entre 0 e 1
        """
        if not text1 or not text2:
            return 0.0

        # Similaridade básica por Jaccard de palavras
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 or not words2:
            return 0.0

        intersection = words1.intersection(words2)
        union = words1.union(words2)

        return len(intersection) / len(union) if union else 0.0

    def clear(self) -> None:
        """Limpa todos os buffers."""
        self._buffers.clear()
        self._contents.clear()

    def get_all_events(self, executor_id: str) -> List[SSEEvent]:
        """
        Retorna todos os eventos bufferizados de um executor.

        Args:
            executor_id: ID do executor

        Returns:
            Lista de eventos
        """
        return self._buffers.get(executor_id, [])
