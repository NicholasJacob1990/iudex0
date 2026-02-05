"""
BNP (Banco Nacional de Precedentes) MCP Server
Connects to the Pangea/BNP REST API via OAuth2 to search
qualified precedents (recursos repetitivos, repercussao geral, sumulas, etc.)

Environment variables:
  BNP_API_URL - Base URL (default: https://bnp-sempj.cloud.pje.jus.br)
  BNP_SSO_URL - SSO token URL (default: https://sso.cloud.pje.jus.br/auth/realms/pje/protocol/openid-connect/token)
  BNP_CLIENT_ID - OAuth2 client ID
  BNP_CLIENT_SECRET - OAuth2 client secret
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class BNPClient:
    """Client for the BNP/Pangea REST API with OAuth2 authentication."""

    def __init__(self) -> None:
        self.api_url = os.getenv(
            "BNP_API_URL", "https://bnp-sempj.cloud.pje.jus.br"
        )
        self.sso_url = os.getenv(
            "BNP_SSO_URL",
            "https://sso.cloud.pje.jus.br/auth/realms/pje/protocol/openid-connect/token",
        )
        self.client_id = os.getenv("BNP_CLIENT_ID", "")
        self.client_secret = os.getenv("BNP_CLIENT_SECRET", "")
        self._token: Optional[str] = None
        self._token_expires: float = 0

    async def _get_token(self) -> str:
        """Get or refresh OAuth2 access token."""
        if self._token and time.time() < self._token_expires - 30:
            return self._token

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                self.sso_url,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "client_credentials",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            data = resp.json()
            self._token = data["access_token"]
            self._token_expires = time.time() + data.get("expires_in", 300)
            return self._token

    async def _request(
        self, method: str, path: str, params: Optional[dict] = None
    ) -> dict:
        """Make authenticated request to BNP API."""
        token = await self._get_token()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.request(
                method,
                f"{self.api_url}{path}",
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            return resp.json()

    async def search_recursos_repetitivos(
        self,
        query: Optional[str] = None,
        page: int = 1,
        size: int = 10,
    ) -> dict:
        """Search recursos repetitivos (STJ/TST)."""
        params: Dict[str, Any] = {"pageNumber": page, "pageSize": size}
        if query:
            params["query"] = query
        return await self._request("GET", "/v1/recurso-repetitivo", params)

    async def search_repercussao_geral(
        self,
        query: Optional[str] = None,
        page: int = 1,
        size: int = 10,
    ) -> dict:
        """Search repercussao geral (STF)."""
        params: Dict[str, Any] = {"pageNumber": page, "pageSize": size}
        if query:
            params["query"] = query
        return await self._request("GET", "/v1/repercussao-geral", params)

    async def search_precedentes(
        self,
        query: Optional[str] = None,
        tipo: Optional[str] = None,
        tribunal: Optional[str] = None,
        page: int = 1,
        size: int = 10,
    ) -> dict:
        """Search all types of precedents."""
        params: Dict[str, Any] = {"pageNumber": page, "pageSize": size}
        if query:
            params["query"] = query
        if tribunal:
            params["idOrgao"] = tribunal

        # Route to specific endpoint based on type
        if tipo == "recurso_repetitivo":
            return await self._request("GET", "/v1/recurso-repetitivo", params)
        elif tipo == "repercussao_geral":
            return await self._request("GET", "/v1/repercussao-geral", params)
        else:
            # Search both and merge
            results: Dict[str, Any] = {"items": [], "total": 0}
            try:
                rr = await self._request(
                    "GET", "/v1/recurso-repetitivo", params
                )
                if isinstance(rr, dict):
                    items = rr.get(
                        "content", rr.get("items", rr.get("data", []))
                    )
                    if isinstance(items, list):
                        for item in items:
                            item["_tipo"] = "recurso_repetitivo"
                        results["items"].extend(items)
            except Exception as e:
                logger.warning(f"[BNP] recurso-repetitivo search error: {e}")

            try:
                rg = await self._request(
                    "GET", "/v1/repercussao-geral", params
                )
                if isinstance(rg, dict):
                    items = rg.get(
                        "content", rg.get("items", rg.get("data", []))
                    )
                    if isinstance(items, list):
                        for item in items:
                            item["_tipo"] = "repercussao_geral"
                        results["items"].extend(items)
            except Exception as e:
                logger.warning(f"[BNP] repercussao-geral search error: {e}")

            results["total"] = len(results["items"])
            return results


class BNPMCPServer:
    """
    MCP Server that exposes BNP/Pangea tools via JSON-RPC.
    Can be used as an internal MCP server within Iudex or as a standalone service.
    """

    def __init__(self) -> None:
        self.client = BNPClient()
        self.tools = self._define_tools()

    def _define_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "bnp_search_precedentes",
                "description": (
                    "Busca precedentes qualificados no Banco Nacional de Precedentes (BNP). "
                    "Inclui recursos repetitivos (STJ/TST), repercussao geral (STF), "
                    "sumulas e orientacoes jurisprudenciais."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Texto de busca (tema, numero, palavras-chave)",
                        },
                        "tipo": {
                            "type": "string",
                            "enum": [
                                "recurso_repetitivo",
                                "repercussao_geral",
                                "todos",
                            ],
                            "description": "Tipo de precedente (default: todos)",
                        },
                        "tribunal": {
                            "type": "string",
                            "description": "ID do orgao/tribunal (opcional)",
                        },
                        "page": {
                            "type": "integer",
                            "description": "Pagina (default: 1)",
                        },
                        "size": {
                            "type": "integer",
                            "description": "Itens por pagina (default: 10)",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "bnp_search_recursos_repetitivos",
                "description": "Busca especificamente recursos repetitivos (STJ e TST) no BNP.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Texto de busca",
                        },
                        "page": {"type": "integer"},
                        "size": {"type": "integer"},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "bnp_search_repercussao_geral",
                "description": "Busca especificamente temas de repercussao geral (STF) no BNP.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Texto de busca",
                        },
                        "page": {"type": "integer"},
                        "size": {"type": "integer"},
                    },
                    "required": ["query"],
                },
            },
        ]

    async def handle_request(
        self, method: str, params: Optional[dict] = None
    ) -> dict:
        """Handle JSON-RPC request."""
        if method in ("initialize", "ping"):
            return {
                "serverInfo": {
                    "name": "bnp-mcp-server",
                    "version": "1.0.0",
                    "description": "Banco Nacional de Precedentes (BNP/Pangea) MCP Server",
                },
                "capabilities": {"tools": {}},
            }

        if method in ("tools/list", "tools.list"):
            return {"tools": self.tools}

        if method in ("tools/call", "tools.call"):
            tool_name = (params or {}).get("name", "")
            arguments = (params or {}).get("arguments", {})
            return await self._call_tool(tool_name, arguments)

        return {"error": {"code": -32601, "message": f"Method not found: {method}"}}

    async def _call_tool(self, name: str, args: dict) -> dict:
        """Execute a tool and return results."""
        try:
            if name == "bnp_search_precedentes":
                result = await self.client.search_precedentes(
                    query=args.get("query"),
                    tipo=args.get("tipo", "todos"),
                    tribunal=args.get("tribunal"),
                    page=args.get("page", 1),
                    size=args.get("size", 10),
                )
            elif name == "bnp_search_recursos_repetitivos":
                result = await self.client.search_recursos_repetitivos(
                    query=args.get("query"),
                    page=args.get("page", 1),
                    size=args.get("size", 10),
                )
            elif name == "bnp_search_repercussao_geral":
                result = await self.client.search_repercussao_geral(
                    query=args.get("query"),
                    page=args.get("page", 1),
                    size=args.get("size", 10),
                )
            else:
                return {
                    "content": [
                        {"type": "text", "text": f"Tool not found: {name}"}
                    ],
                    "isError": True,
                }

            # Format result
            formatted = self._format_result(result, name)
            return {"content": [{"type": "text", "text": formatted}]}

        except httpx.HTTPStatusError as e:
            error_msg = (
                f"BNP API error: {e.response.status_code} - "
                f"{e.response.text[:200]}"
            )
            logger.error(f"[BNP MCP] {error_msg}")
            return {
                "content": [{"type": "text", "text": error_msg}],
                "isError": True,
            }
        except Exception as e:
            logger.error(f"[BNP MCP] Tool {name} error: {e}")
            return {
                "content": [{"type": "text", "text": f"Error: {str(e)}"}],
                "isError": True,
            }

    def _format_result(self, data: dict, tool_name: str) -> str:
        """Format API response into readable text."""
        items = data.get("content", data.get("items", data.get("data", [])))
        if not isinstance(items, list):
            return json.dumps(data, ensure_ascii=False, indent=2)[:3000]

        lines = [f"### Resultados BNP ({len(items)} encontrados)\n"]
        for i, item in enumerate(items[:15]):
            if isinstance(item, dict):
                titulo = item.get(
                    "titulo",
                    item.get("tema", item.get("descricao", f"Precedente #{i + 1}")),
                )
                tipo = item.get(
                    "_tipo", item.get("tipo", item.get("especie", ""))
                )
                tribunal = item.get("tribunal", item.get("orgao", ""))
                numero = item.get("numero", item.get("id", ""))
                tese = item.get(
                    "tese",
                    item.get("teseJuridica", item.get("ementa", "")),
                )
                situacao = item.get("situacao", item.get("status", ""))

                lines.append(f"**{i + 1}. {titulo}**")
                if numero:
                    lines.append(f"   Numero: {numero}")
                if tipo:
                    lines.append(f"   Tipo: {tipo}")
                if tribunal:
                    lines.append(f"   Tribunal: {tribunal}")
                if situacao:
                    lines.append(f"   Situacao: {situacao}")
                if tese:
                    lines.append(f"   Tese: {tese[:300]}")
                lines.append("")
            else:
                lines.append(f"- {str(item)[:200]}")

        return "\n".join(lines)
