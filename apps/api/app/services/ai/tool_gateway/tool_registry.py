"""
Tool Registry - Unified tool registration for MCP Gateway.

Registers all legal tools from claude_agent/tools with metadata:
- name, description, schema
- policy (allow, ask, deny)
- category (rag, datajud, generation, notification, sensitive)
"""

from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field
from dataclasses import asdict, is_dataclass
from enum import Enum

from loguru import logger


class ToolPolicy(str, Enum):
    ALLOW = "allow"      # Auto-execute
    ASK = "ask"          # Request user approval
    DENY = "deny"        # Block without explicit override


class ToolCategory(str, Enum):
    RAG = "rag"
    DATAJUD = "datajud"
    TRIBUNAIS = "tribunais"
    GENERATION = "generation"
    NOTIFICATION = "notification"
    SENSITIVE = "sensitive"
    DOCUMENT = "document"


@dataclass
class ToolDefinition:
    """Definition of a tool with metadata for MCP Gateway."""

    name: str
    description: str
    input_schema: Dict[str, Any]
    function: Callable
    policy: ToolPolicy = ToolPolicy.ALLOW
    category: ToolCategory = ToolCategory.RAG
    requires_context: bool = True
    version: str = "1.0"
    tags: List[str] = field(default_factory=list)


def _normalize_result(data: Any) -> Any:
    """Convert nested dataclass results into plain JSON-serializable structures."""
    if is_dataclass(data):
        return asdict(data)
    if isinstance(data, list):
        return [_normalize_result(item) for item in data]
    if isinstance(data, tuple):
        return [_normalize_result(item) for item in data]
    if isinstance(data, dict):
        return {str(k): _normalize_result(v) for k, v in data.items()}
    return data


class ToolRegistry:
    """Singleton registry for all legal tools."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools = {}
            cls._instance._initialized = False
        return cls._instance

    def register(self, tool: ToolDefinition) -> None:
        """Register a tool in the registry."""
        self._tools[tool.name] = tool
        logger.debug(f"Registered tool: {tool.name} ({tool.category.value})")

    def unregister(self, name: str) -> bool:
        """Remove a tool from the registry."""
        if name in self._tools:
            del self._tools[name]
            logger.debug(f"Unregistered tool: {name}")
            return True
        return False

    def get(self, name: str) -> Optional[ToolDefinition]:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(
        self,
        category: Optional[ToolCategory] = None,
        policy: Optional[ToolPolicy] = None,
    ) -> List[ToolDefinition]:
        """List tools with optional filtering."""
        tools = list(self._tools.values())
        if category:
            tools = [t for t in tools if t.category == category]
        if policy:
            tools = [t for t in tools if t.policy == policy]
        return tools

    def list_names(self) -> List[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def to_mcp_format(self) -> List[Dict[str, Any]]:
        """Export all tools in MCP format for client consumption."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "inputSchema": t.input_schema,
            }
            for t in self._tools.values()
        ]

    def to_anthropic_format(self) -> List[Dict[str, Any]]:
        """Export tools in Anthropic's tool format for Claude API."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
            }
            for t in self._tools.values()
        ]

    def initialize(self) -> None:
        """Load all tools from claude_agent/tools and unified_tools."""
        if self._initialized:
            logger.debug("Tool registry already initialized")
            return

        logger.info("Initializing tool registry...")

        # 1. Load Claude Agent legal tools
        try:
            from app.services.ai.claude_agent.tools.legal_research import LEGAL_RESEARCH_TOOLS
            from app.services.ai.claude_agent.tools.rag_search import RAG_SEARCH_TOOLS
            from app.services.ai.claude_agent.tools.document_editor import DOCUMENT_EDITOR_TOOLS
            from app.services.ai.claude_agent.tools.citation_verifier import CITATION_VERIFIER_TOOLS

            tool_configs = [
                (RAG_SEARCH_TOOLS, ToolCategory.RAG),
                (LEGAL_RESEARCH_TOOLS, ToolCategory.RAG),
                (CITATION_VERIFIER_TOOLS, ToolCategory.RAG),
                (DOCUMENT_EDITOR_TOOLS, ToolCategory.DOCUMENT),
            ]

            for tools_dict, category in tool_configs:
                for name, config in tools_dict.items():
                    schema = config.get("schema", {})
                    policy_str = config.get("permission_default", "allow")
                    try:
                        policy = ToolPolicy(policy_str)
                    except ValueError:
                        policy = ToolPolicy.ALLOW

                    self.register(ToolDefinition(
                        name=name,
                        description=schema.get("description", ""),
                        input_schema=schema.get("input_schema", {}),
                        function=config["function"],
                        policy=policy,
                        category=category,
                    ))

            logger.info(f"Loaded {len(self._tools)} Claude Agent tools")

        except ImportError as e:
            logger.warning(f"Claude Agent tools not available: {e}")

        # 2. Load unified tools (SDK-adapted, web, MCP)
        try:
            from app.services.ai.shared.unified_tools import ALL_UNIFIED_TOOLS, ToolRiskLevel

            risk_to_policy = {
                ToolRiskLevel.LOW: ToolPolicy.ALLOW,
                ToolRiskLevel.MEDIUM: ToolPolicy.ASK,
                ToolRiskLevel.HIGH: ToolPolicy.DENY,
            }

            category_map = {
                "search": ToolCategory.RAG,
                "document": ToolCategory.DOCUMENT,
                "analysis": ToolCategory.RAG,
                "citation": ToolCategory.RAG,
                "system": ToolCategory.RAG,
            }

            for tool in ALL_UNIFIED_TOOLS:
                if tool.name in self._tools:
                    continue  # Skip duplicates

                cat = category_map.get(tool.category.value.lower(), ToolCategory.RAG)
                policy = risk_to_policy.get(tool.risk_level, ToolPolicy.ALLOW)

                # Create a wrapper function if handler exists
                handler = tool.handler or (lambda **kwargs: {"error": "No handler defined"})

                self.register(ToolDefinition(
                    name=tool.name,
                    description=tool.description,
                    input_schema=tool.parameters,
                    function=handler,
                    policy=policy,
                    category=cat,
                    requires_context=tool.requires_context,
                ))

            logger.info(f"Loaded unified tools, total: {len(self._tools)}")

        except ImportError as e:
            logger.warning(f"Unified tools not available: {e}")

        # 2b. Enable graph tools (ask_graph + graph risk/audit) which may be declared
        # as metadata-only unified tools (handler=None) by default.
        try:
            self._register_graph_tools()
        except Exception as e:
            logger.warning(f"Graph tools not available: {e}")

        # 3. Register DataJud/DJEN tools
        self._register_datajud_tools()

        # 4. Register Tribunais tools
        self._register_tribunais_tools()

        self._initialized = True
        logger.info(f"Tool registry fully initialized with {len(self._tools)} tools")

    def _register_graph_tools(self) -> None:
        """
        Ensure graph tools have real handlers in the tool gateway registry.

        Note: the MCP server injects `tenant_id`, `user_id`, and `case_id` into tool arguments.
        Workflows/tool_call should also pass these via state injection.
        """
        from typing import Any as _Any

        from app.services.graph_ask_service import get_graph_ask_service
        from app.services.graph_risk_service import get_graph_risk_service

        async def ask_graph(
            operation: str = "search",
            params: Optional[Dict[str, _Any]] = None,
            scope: Optional[str] = None,
            include_global: bool = True,
            tenant_id: Optional[str] = None,
            case_id: Optional[str] = None,
            **_: _Any,
        ) -> Dict[str, _Any]:
            if not tenant_id:
                return {
                    "success": False,
                    "operation": operation,
                    "results": [],
                    "error": "tenant_id ausente (bloqueado por segurança)",
                }
            service = get_graph_ask_service()
            res = await service.ask(
                operation=operation,
                params=params or {},
                tenant_id=str(tenant_id),
                scope=scope,
                case_id=case_id,
                include_global=bool(include_global),
            )
            return res.to_dict()

        async def scan_graph_risk(
            tenant_id: Optional[str] = None,
            user_id: Optional[str] = None,
            **kwargs: _Any,
        ) -> Dict[str, _Any]:
            if not tenant_id:
                return {"success": False, "error": "tenant_id ausente (bloqueado por segurança)"}
            if not user_id:
                return {"success": False, "error": "user_id ausente (bloqueado por segurança)"}

            from app.core.database import AsyncSessionLocal
            from app.schemas.graph_risk import RiskScanRequest

            req = RiskScanRequest(**(kwargs or {}))
            service = get_graph_risk_service()
            async with AsyncSessionLocal() as db:
                res = await service.scan(
                    tenant_id=str(tenant_id),
                    user_id=str(user_id),
                    db=db,
                    request=req,
                )
                return res.model_dump()

        async def audit_graph_edge(
            tenant_id: Optional[str] = None,
            **kwargs: _Any,
        ) -> Dict[str, _Any]:
            if not tenant_id:
                return {"success": False, "error": "tenant_id ausente (bloqueado por segurança)"}
            from app.schemas.graph_risk import AuditEdgeRequest
            service = get_graph_risk_service()
            req = AuditEdgeRequest(**(kwargs or {}))
            res = await service.audit_edge(tenant_id=str(tenant_id), request=req)
            return res.model_dump()

        async def audit_graph_chain(
            tenant_id: Optional[str] = None,
            **kwargs: _Any,
        ) -> Dict[str, _Any]:
            if not tenant_id:
                return {"success": False, "error": "tenant_id ausente (bloqueado por segurança)"}
            from app.schemas.graph_risk import AuditChainRequest
            service = get_graph_risk_service()
            req = AuditChainRequest(**(kwargs or {}))
            res = await service.audit_chain(tenant_id=str(tenant_id), request=req)
            return res.model_dump()

        # Override dummy handlers if present
        if "ask_graph" in self._tools:
            self._tools["ask_graph"].function = ask_graph
        if "scan_graph_risk" in self._tools:
            self._tools["scan_graph_risk"].function = scan_graph_risk
        if "audit_graph_edge" in self._tools:
            self._tools["audit_graph_edge"].function = audit_graph_edge
        if "audit_graph_chain" in self._tools:
            self._tools["audit_graph_chain"].function = audit_graph_chain

    def _register_datajud_tools(self) -> None:
        """Register DataJud and DJEN integration tools."""

        async def consultar_processo_datajud(
            numero_processo: str,
            tribunal: Optional[str] = None,
            **kwargs
        ) -> Dict[str, Any]:
            """Consulta processo no DataJud (CNJ)."""
            try:
                from app.services.djen_service import extract_tribunal_from_npu, get_djen_service

                numero = str(numero_processo or "").strip()
                if not numero:
                    return {"error": "numero_processo is required", "success": False}

                tribunal_sigla = (tribunal or "").strip().upper() or extract_tribunal_from_npu(numero)
                if not tribunal_sigla:
                    return {
                        "error": "Tribunal nao identificado pelo NPU. Informe a sigla em 'tribunal'.",
                        "success": False,
                    }

                djen_service = get_djen_service()
                if not djen_service.datajud.api_key:
                    return {"error": "CNJ_API_KEY not configured", "success": False}

                results = await djen_service.fetch_metadata(numero, tribunal_sigla)
                return {
                    "success": True,
                    "results": _normalize_result(results),
                    "total": len(results),
                    "tribunal": tribunal_sigla,
                }
            except Exception as e:
                return {"error": str(e), "success": False}

        async def buscar_publicacoes_djen(
            numero_processo: Optional[str] = None,
            data_inicio: Optional[str] = None,
            data_fim: Optional[str] = None,
            tribunal: Optional[str] = None,
            **kwargs
        ) -> Dict[str, Any]:
            """Busca publicações no Diário de Justiça Eletrônico."""
            try:
                from app.services.djen_service import get_djen_service

                djen_service = get_djen_service()
                results = await djen_service.search_by_process(
                    numero_processo=str(numero_processo or ""),
                    tribunal_sigla=(tribunal or None),
                    data_inicio=data_inicio,
                    data_fim=data_fim,
                    meio=str(kwargs.get("meio", "D")),
                    max_pages=int(kwargs.get("max_pages", 10)),
                )
                return {
                    "success": True,
                    "results": _normalize_result(results),
                    "total": len(results),
                }
            except Exception as e:
                return {"error": str(e), "success": False}

        # DataJud
        self.register(ToolDefinition(
            name="consultar_processo_datajud",
            description="""Consulta metadados de processo no DataJud (CNJ).

Retorna informações como:
- Classe e assuntos
- Partes (autor, réu)
- Movimentações
- Valor da causa
- Órgão julgador

Use para obter contexto completo de um processo.""",
            input_schema={
                "type": "object",
                "properties": {
                    "numero_processo": {
                        "type": "string",
                        "description": "Número CNJ do processo (ex: 0001234-56.2024.8.26.0100)"
                    },
                    "tribunal": {
                        "type": "string",
                        "description": "Sigla do tribunal (opcional, ex: TJSP)"
                    }
                },
                "required": ["numero_processo"]
            },
            function=consultar_processo_datajud,
            policy=ToolPolicy.ALLOW,
            category=ToolCategory.DATAJUD,
        ))

        # DJEN
        self.register(ToolDefinition(
            name="buscar_publicacoes_djen",
            description="""Busca publicações no Diário de Justiça Eletrônico Nacional.

Encontra:
- Intimações
- Despachos publicados
- Decisões
- Sentenças publicadas

Permite filtrar por processo, período e tribunal.""",
            input_schema={
                "type": "object",
                "properties": {
                    "numero_processo": {
                        "type": "string",
                        "description": "Número do processo para filtrar"
                    },
                    "data_inicio": {
                        "type": "string",
                        "format": "date",
                        "description": "Data inicial (YYYY-MM-DD)"
                    },
                    "data_fim": {
                        "type": "string",
                        "format": "date",
                        "description": "Data final (YYYY-MM-DD)"
                    },
                    "tribunal": {
                        "type": "string",
                        "description": "Sigla do tribunal"
                    }
                }
            },
            function=buscar_publicacoes_djen,
            policy=ToolPolicy.ALLOW,
            category=ToolCategory.DATAJUD,
        ))

        logger.info("Registered DataJud/DJEN tools")

    def _register_tribunais_tools(self) -> None:
        """Register Tribunais integration tools (PJe, e-Proc)."""

        async def consultar_processo_pje(
            numero_processo: str,
            tribunal: str,
            **kwargs
        ) -> Dict[str, Any]:
            """Consulta processo no PJe."""
            try:
                from app.services.tribunais_client import TribunaisClient
                client = TribunaisClient()
                return await client.consultar_processo(numero_processo, tribunal, "pje")
            except Exception as e:
                return {"error": str(e), "success": False}

        async def consultar_processo_eproc(
            numero_processo: str,
            tribunal: str,
            **kwargs
        ) -> Dict[str, Any]:
            """Consulta processo no e-Proc."""
            try:
                from app.services.tribunais_client import TribunaisClient
                client = TribunaisClient()
                return await client.consultar_processo(numero_processo, tribunal, "eproc")
            except Exception as e:
                return {"error": str(e), "success": False}

        async def protocolar_documento(
            numero_processo: str,
            tribunal: str,
            tipo_documento: str,
            arquivo_base64: str,
            descricao: str,
            sistema: str = "pje",
            **kwargs
        ) -> Dict[str, Any]:
            """Protocola documento em processo eletrônico."""
            try:
                from app.services.tribunais_client import TribunaisClient
                client = TribunaisClient()
                return await client.protocolar(
                    numero_processo=numero_processo,
                    tribunal=tribunal,
                    tipo_documento=tipo_documento,
                    arquivo_base64=arquivo_base64,
                    descricao=descricao,
                    sistema=sistema,
                )
            except Exception as e:
                return {"error": str(e), "success": False}

        # PJe
        self.register(ToolDefinition(
            name="consultar_processo_pje",
            description="""Consulta processo no sistema PJe (Processo Judicial Eletrônico).

Retorna:
- Dados do processo
- Partes
- Movimentações
- Documentos disponíveis

Requer credenciais configuradas para o tribunal.""",
            input_schema={
                "type": "object",
                "properties": {
                    "numero_processo": {
                        "type": "string",
                        "description": "Número CNJ do processo"
                    },
                    "tribunal": {
                        "type": "string",
                        "description": "Sigla do tribunal (ex: TRF4, TJSP)"
                    }
                },
                "required": ["numero_processo", "tribunal"]
            },
            function=consultar_processo_pje,
            policy=ToolPolicy.ALLOW,
            category=ToolCategory.TRIBUNAIS,
        ))

        # e-Proc
        self.register(ToolDefinition(
            name="consultar_processo_eproc",
            description="""Consulta processo no sistema e-Proc (TRF4, TJPR, TJSC, TJRS).

Retorna dados completos do processo eletrônico.
Requer credenciais configuradas.""",
            input_schema={
                "type": "object",
                "properties": {
                    "numero_processo": {
                        "type": "string",
                        "description": "Número CNJ do processo"
                    },
                    "tribunal": {
                        "type": "string",
                        "description": "Sigla do tribunal (TRF4, TJPR, TJSC, TJRS)"
                    }
                },
                "required": ["numero_processo", "tribunal"]
            },
            function=consultar_processo_eproc,
            policy=ToolPolicy.ALLOW,
            category=ToolCategory.TRIBUNAIS,
        ))

        # Protocolamento (requer aprovação)
        self.register(ToolDefinition(
            name="protocolar_documento",
            description="""Protocola documento em processo judicial eletrônico.

ATENÇÃO: Esta ação é IRREVERSÍVEL. Será solicitada aprovação.

Suporta PJe e e-Proc.
Requer certificado digital ou credenciais.""",
            input_schema={
                "type": "object",
                "properties": {
                    "numero_processo": {
                        "type": "string",
                        "description": "Número CNJ do processo"
                    },
                    "tribunal": {
                        "type": "string",
                        "description": "Sigla do tribunal"
                    },
                    "tipo_documento": {
                        "type": "string",
                        "enum": ["peticao", "procuracao", "substabelecimento", "documento", "outros"],
                        "description": "Tipo do documento"
                    },
                    "arquivo_base64": {
                        "type": "string",
                        "description": "Arquivo PDF em base64"
                    },
                    "descricao": {
                        "type": "string",
                        "description": "Descrição do documento"
                    },
                    "sistema": {
                        "type": "string",
                        "enum": ["pje", "eproc"],
                        "default": "pje"
                    }
                },
                "required": ["numero_processo", "tribunal", "tipo_documento", "arquivo_base64", "descricao"]
            },
            function=protocolar_documento,
            policy=ToolPolicy.ALLOW,  # All tools authorized
            category=ToolCategory.SENSITIVE,
        ))

        logger.info("Registered Tribunais tools (PJe, e-Proc)")

    def reset(self) -> None:
        """Reset the registry (useful for testing)."""
        self._tools = {}
        self._initialized = False
        logger.debug("Tool registry reset")

    @property
    def is_initialized(self) -> bool:
        """Check if the registry has been initialized."""
        return self._initialized

    @property
    def tool_count(self) -> int:
        """Get the number of registered tools."""
        return len(self._tools)


# Global registry
tool_registry = ToolRegistry()
