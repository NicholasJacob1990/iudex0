from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.services.ai.rag_helpers import _call_llm
from app.services.ai.json_utils import extract_first_json_object


@dataclass(frozen=True)
class DatasetSpec:
    name: str
    description: str
    locale: str
    sources: List[str]


class DatasetRegistry:
    def __init__(self) -> None:
        self._datasets = [
            DatasetSpec(
                name="lei",
                description="Leis, decretos, portarias e normas vigentes.",
                locale="pt-br",
                sources=["lei"],
            ),
            DatasetSpec(
                name="juris",
                description="Jurisprudencia, sumulas, precedentes e acordaos.",
                locale="pt-br",
                sources=["juris"],
            ),
            DatasetSpec(
                name="pecas_modelo",
                description="Modelos de pecas, estruturas e estilos processuais.",
                locale="pt-br",
                sources=["pecas_modelo"],
            ),
            DatasetSpec(
                name="doutrina",
                description="Doutrina, livros, artigos academicos e comentarios de autores.",
                locale="pt-br",
                sources=["doutrina"],
            ),
            DatasetSpec(
                name="sei",
                description="Documentos internos do processo (SEI) e fatos do caso.",
                locale="pt-br",
                sources=["sei"],
            ),
        ]

    def list(self) -> List[DatasetSpec]:
        return list(self._datasets)

    def get_sources(self, dataset_names: List[str]) -> List[str]:
        sources: List[str] = []
        for dataset in self._datasets:
            if dataset.name in dataset_names:
                sources.extend(dataset.sources)
        return list(dict.fromkeys(sources))


class AgenticRAGRouter:
    def __init__(self, registry: Optional[DatasetRegistry] = None) -> None:
        self.registry = registry or DatasetRegistry()

    async def route(
        self,
        query: str,
        history: Optional[List[dict]] = None,
        summary_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        datasets = self.registry.list()
        dataset_lines = "\n".join(
            f"- {d.name}: {d.description} (locale={d.locale})"
            for d in datasets
        )
        history_block = self._compact_history(history or [])
        summary_block = (summary_text or "").strip()
        prompt = (
            "You are an AgenticRAG router. Pick the best datasets for the query.\n"
            "Return JSON only with fields: datasets (list), locale, query.\n"
            "Translate the query to the selected locale if needed.\n\n"
            f"Datasets:\n{dataset_lines}\n\n"
            f"Summary:\n{summary_block or 'none'}\n\n"
            f"History:\n{history_block or 'none'}\n\n"
            f"Query:\n{query}\n\n"
            "JSON:"
        )
        response = await _call_llm(prompt, max_tokens=220, temperature=0.2)
        data = self._extract_json(response)
        if not isinstance(data, dict):
            return {}
        return data

    def _extract_json(self, text: str) -> Dict[str, Any]:
        return extract_first_json_object(text)

    def _compact_history(self, history: List[dict], max_items: int = 6, max_chars: int = 1200) -> str:
        if not history:
            return ""
        selected = history[-max_items:]
        lines = []
        total = 0
        for item in selected:
            role = item.get("role", "user")
            content = (item.get("content") or "").strip()
            if not content:
                continue
            remaining = max_chars - total
            if remaining <= 0:
                break
            snippet = content[:remaining]
            lines.append(f"{role}: {snippet}")
            total += len(snippet)
        return "\n".join(lines)
