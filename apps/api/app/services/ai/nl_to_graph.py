"""
NL-to-Graph Parser — Converts natural language descriptions into React Flow graphs.

Part of "Words to Workflows" (P2 #11 Harvey AI parity).
Takes a plain-text workflow description and uses an LLM to generate a valid
React Flow graph JSON that can be loaded directly into the Workflow Builder.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

from loguru import logger

from app.services.ai.model_registry import get_model_config, get_api_model_name
from app.services.ai.workflow_compiler import validate_graph, VALID_NODE_TYPES


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """Você é um assistente especializado em criar workflows jurídicos visuais.

Dado uma descrição em linguagem natural, gere um grafo React Flow válido em JSON.

## Tipos de nó disponíveis:

- **user_input**: Coleta texto/arquivos do usuário. Config: {input_type: "text"|"file"|"both", collects: "input", optional: false, placeholder: "..."}
- **file_upload**: Upload de arquivo. Config: {collects: "file"}
- **selection**: Apresenta opções ao usuário. Config: {collects: "selection", options: ["opt1", "opt2"]}
- **condition**: Ramificação condicional. Config: {condition_field: "selection", branches: {"opt1": "node_id_1", "opt2": "node_id_2"}}
- **prompt**: Chamada LLM com template. Config: {model: "claude-4.5-sonnet", prompt: "Instruções para a IA..."}
- **rag_search**: Busca na base de conhecimento. Config: {limit: 10, sources: []}
- **human_review**: Pausa para revisão humana. Config: {instructions: "Revise e aprove o conteúdo."}
- **tool_call**: Executa ferramenta externa. Config: {tool_name: "nome_da_tool"}
- **output**: Monta resposta final. Config: {sections: [], show_all: true}

## Regras:

1. Retorne SOMENTE JSON válido, sem markdown, sem ```json
2. O JSON deve ter exatamente duas chaves: "nodes" e "edges"
3. Cada node: {id: string, type: string (um dos tipos acima), position: {x: number, y: number}, data: {label: string, ...config}}
4. Cada edge: {id: string, source: string, target: string}
5. IDs de nós devem ser descritivos (ex: "input_1", "prompt_analise", "output_final")
6. Posicione os nós verticalmente (y incrementando ~150px) e centralize horizontalmente (x ~250)
7. Para ramificações, espalhe horizontalmente (x variando ~200px entre branches)
8. Todo workflow deve começar com user_input ou file_upload e terminar com output
9. Conecte todos os nós com edges formando um grafo dirigido acíclico (DAG)
10. Use português brasileiro nos labels e prompts
11. Escreva prompts detalhados e úteis para os nós do tipo "prompt"
"""


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class NLToGraphParser:
    """Converts natural language workflow descriptions into React Flow graph JSON."""

    async def parse(
        self,
        description: str,
        model: str = "claude",
        max_retries: int = 2,
    ) -> Dict[str, Any]:
        """
        Parse a natural language description into a React Flow graph.

        Args:
            description: The workflow description in natural language.
            model: Which LLM family to use ("claude", "openai", "gemini").
            max_retries: Number of retries on validation failure.

        Returns:
            Dict with "nodes" and "edges" arrays.

        Raises:
            ValueError: If the generated graph fails validation after retries.
        """
        logger.info(f"[NLToGraph] Parsing description ({len(description)} chars) with model={model}")

        raw_json = await self._call_llm(description, model)
        graph = self._extract_json(raw_json)

        # Validate and retry if needed
        for attempt in range(max_retries + 1):
            errors = validate_graph(graph)
            if not errors:
                logger.info(
                    f"[NLToGraph] Generated valid graph: "
                    f"{len(graph.get('nodes', []))} nodes, "
                    f"{len(graph.get('edges', []))} edges"
                )
                return graph

            if attempt < max_retries:
                logger.warning(
                    f"[NLToGraph] Validation errors (attempt {attempt + 1}): {errors}. Retrying..."
                )
                fix_prompt = (
                    f"O grafo gerado tem os seguintes erros de validação:\n"
                    f"{chr(10).join(f'- {e}' for e in errors)}\n\n"
                    f"Tipos de nó válidos: {sorted(VALID_NODE_TYPES)}\n\n"
                    f"Corrija o JSON e retorne SOMENTE o JSON corrigido.\n\n"
                    f"JSON original:\n{json.dumps(graph, ensure_ascii=False, indent=2)}"
                )
                raw_json = await self._call_llm(fix_prompt, model)
                graph = self._extract_json(raw_json)

        raise ValueError(
            f"Falha ao gerar grafo válido após {max_retries + 1} tentativas. "
            f"Erros: {errors}"
        )

    async def _call_llm(self, user_message: str, model: str) -> str:
        """Call the LLM and return the raw text response."""
        model_family = model.lower().strip()

        if model_family in ("claude", "anthropic"):
            return await self._call_anthropic(user_message)
        elif model_family in ("openai", "gpt"):
            return await self._call_openai(user_message)
        elif model_family in ("gemini", "google"):
            return await self._call_gemini(user_message)
        else:
            # Default to Anthropic
            return await self._call_anthropic(user_message)

    async def _call_anthropic(self, user_message: str) -> str:
        """Call Anthropic Claude API."""
        try:
            import anthropic
        except ImportError:
            raise ImportError("anthropic package not installed")

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")

        client = anthropic.AsyncAnthropic(api_key=api_key)
        api_model = get_api_model_name("claude-4.5-sonnet") or "claude-sonnet-4-5"

        response = await client.messages.create(
            model=api_model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        return response.content[0].text

    async def _call_openai(self, user_message: str) -> str:
        """Call OpenAI API."""
        try:
            import openai
        except ImportError:
            raise ImportError("openai package not installed")

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set")

        client = openai.AsyncOpenAI(api_key=api_key)
        api_model = get_api_model_name("gpt-5") or "gpt-4o"

        response = await client.chat.completions.create(
            model=api_model,
            max_tokens=4096,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
        )

        return response.choices[0].message.content or ""

    async def _call_gemini(self, user_message: str) -> str:
        """Call Google Gemini API."""
        try:
            from google import genai
        except ImportError:
            raise ImportError("google-genai package not installed")

        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY or GOOGLE_API_KEY not set")

        client = genai.Client(api_key=api_key)
        api_model = get_api_model_name("gemini-3-flash") or "gemini-3-flash-preview"

        response = await client.aio.models.generate_content(
            model=api_model,
            contents=f"{SYSTEM_PROMPT}\n\n---\n\n{user_message}",
        )

        return response.text or ""

    def _extract_json(self, raw_text: str) -> Dict[str, Any]:
        """Extract JSON from LLM response, handling markdown code blocks."""
        text = raw_text.strip()

        # Remove markdown code blocks if present
        if text.startswith("```"):
            # Remove first line (```json or ```)
            lines = text.split("\n")
            lines = lines[1:]
            # Remove last ``` if present
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON object in the text
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    parsed = json.loads(text[start:end])
                except json.JSONDecodeError as e:
                    raise ValueError(f"Não foi possível extrair JSON da resposta: {e}")
            else:
                raise ValueError("Resposta do LLM não contém JSON válido")

        # Ensure structure
        if "nodes" not in parsed:
            parsed["nodes"] = []
        if "edges" not in parsed:
            parsed["edges"] = []

        return parsed
