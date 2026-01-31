"""
PermissionManager - Sistema de permissões para ferramentas do Claude Agent.

Este módulo implementa um sistema de permissões granular para controlar
quais ferramentas o Claude Agent pode executar automaticamente, quais
precisam de aprovação do usuário, e quais são bloqueadas.

Hierarquia de precedência (mais específico primeiro):
1. session - Regras da sessão atual
2. project - Regras do projeto/caso
3. global - Regras globais do usuário
4. system - Defaults do sistema

Exemplo de uso:
    manager = PermissionManager(
        db=session,
        user_id="user-123",
        session_id="session-456",
        project_id="case-789"
    )

    # Verificar permissão
    decision = await manager.check("edit_document", {"path": "/doc.md"})
    # decision: "allow" | "deny" | "ask"

    # Adicionar regra
    await manager.add_rule(
        tool_name="edit_document",
        mode="allow",
        scope="session"
    )
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from fnmatch import fnmatch
import json
import asyncio
from loguru import logger

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tool_permission import (
    ToolPermission,
    PermissionMode,
    PermissionScope,
)


# Tipo para decisão de permissão
PermissionDecision = Literal["allow", "deny", "ask"]


# ==================== DEFAULTS DO SISTEMA ====================

SYSTEM_DEFAULTS: Dict[str, PermissionDecision] = {
    # Leitura: permitido automaticamente
    "search_jurisprudencia": "allow",
    "search_legislacao": "allow",
    "search_rag": "allow",
    "search_templates": "allow",
    "read_document": "allow",
    "verify_citation": "allow",
    "find_citation_source": "allow",

    # Escrita: pedir aprovação
    "edit_document": "ask",
    "create_section": "ask",
    "write_file": "ask",
    "update_document": "ask",

    # Alto risco: negar por padrão
    "bash": "deny",
    "file_write": "deny",
    "file_delete": "deny",
    "execute_command": "deny",
    "system_command": "deny",
}

# Padrões de tools por categoria (para wildcards)
TOOL_CATEGORIES = {
    "search_*": "allow",      # Todas as buscas
    "read_*": "allow",        # Todas as leituras
    "verify_*": "allow",      # Todas as verificações
    "edit_*": "ask",          # Todas as edições
    "create_*": "ask",        # Todas as criações
    "delete_*": "deny",       # Todas as exclusões
    "execute_*": "deny",      # Todas as execuções
}

# Default para tools não conhecidas
DEFAULT_PERMISSION: PermissionDecision = "ask"


# ==================== DATA CLASSES ====================

@dataclass
class PermissionRule:
    """
    Representa uma regra de permissão.

    Attributes:
        id: ID único da regra (None para regras de sistema)
        tool_name: Nome da ferramenta (pode usar wildcards)
        mode: Modo de permissão (allow/deny/ask)
        scope: Escopo da regra (session/project/global/system)
        pattern: Padrão glob para matching do input
        session_id: ID da sessão (se scope=session)
        project_id: ID do projeto (se scope=project)
        created_at: Data de criação
        is_system: Se é uma regra de sistema (imutável)
    """
    tool_name: str
    mode: PermissionDecision
    scope: str
    id: Optional[str] = None
    pattern: Optional[str] = None
    session_id: Optional[str] = None
    project_id: Optional[str] = None
    created_at: Optional[datetime] = None
    is_system: bool = False

    def matches_tool(self, tool_name: str) -> bool:
        """Verifica se a regra se aplica a uma ferramenta."""
        return fnmatch(tool_name, self.tool_name)

    def matches_input(self, tool_input: Dict[str, Any]) -> bool:
        """Verifica se a regra se aplica ao input fornecido."""
        if not self.pattern:
            return True  # Sem padrão = qualquer input

        # Serializa o input para matching
        input_str = json.dumps(tool_input, default=str)
        return fnmatch(input_str, self.pattern)

    def matches(self, tool_name: str, tool_input: Dict[str, Any]) -> bool:
        """Verifica se a regra se aplica completamente."""
        return self.matches_tool(tool_name) and self.matches_input(tool_input)

    @property
    def priority(self) -> int:
        """
        Retorna a prioridade da regra (menor = maior precedência).

        Ordem de precedência:
        1. session (0)
        2. project (1)
        3. global (2)
        4. system (3)
        """
        scope_priority = {
            "session": 0,
            "project": 1,
            "global": 2,
            "system": 3,
        }
        return scope_priority.get(self.scope, 99)

    def to_dict(self) -> dict:
        """Converte para dicionário."""
        return {
            "id": self.id,
            "tool_name": self.tool_name,
            "mode": self.mode,
            "scope": self.scope,
            "pattern": self.pattern,
            "session_id": self.session_id,
            "project_id": self.project_id,
            "is_system": self.is_system,
        }


@dataclass
class PermissionCheckResult:
    """
    Resultado de uma verificação de permissão.

    Attributes:
        decision: A decisão final (allow/deny/ask)
        matching_rule: A regra que determinou a decisão
        tool_name: Nome da ferramenta verificada
        tool_input: Input fornecido
        checked_at: Timestamp da verificação
    """
    decision: PermissionDecision
    matching_rule: Optional[PermissionRule]
    tool_name: str
    tool_input: Dict[str, Any]
    checked_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def is_allowed(self) -> bool:
        return self.decision == "allow"

    @property
    def is_denied(self) -> bool:
        return self.decision == "deny"

    @property
    def needs_approval(self) -> bool:
        return self.decision == "ask"


# ==================== PERMISSION MANAGER ====================

class PermissionManager:
    """
    Gerenciador de permissões para ferramentas do Claude Agent.

    Este gerenciador implementa:
    - Cache de regras para evitar queries repetidas
    - Hierarquia de precedência de regras
    - Matching de padrões glob para ferramentas e inputs
    - CRUD de regras de permissão

    Usage:
        manager = PermissionManager(db, user_id="user-123")

        # Verificar permissão
        result = await manager.check("edit_document", {"path": "/doc.md"})
        if result.needs_approval:
            # Mostrar modal de aprovação
            pass

        # Adicionar regra persistente
        rule = await manager.add_rule(
            tool_name="edit_document",
            mode="allow",
            scope="session"
        )
    """

    def __init__(
        self,
        db: AsyncSession,
        user_id: str,
        session_id: Optional[str] = None,
        project_id: Optional[str] = None,
        cache_ttl_seconds: int = 60,
    ):
        """
        Inicializa o PermissionManager.

        Args:
            db: Sessão do banco de dados
            user_id: ID do usuário
            session_id: ID da sessão atual (opcional)
            project_id: ID do projeto/caso (opcional)
            cache_ttl_seconds: TTL do cache em segundos
        """
        self.db = db
        self.user_id = user_id
        self.session_id = session_id
        self.project_id = project_id
        self.cache_ttl = cache_ttl_seconds

        # Cache de regras
        self._rules_cache: Optional[List[PermissionRule]] = None
        self._cache_timestamp: Optional[datetime] = None

        # Lock para thread-safety
        self._cache_lock = asyncio.Lock()

        logger.debug(
            f"PermissionManager initialized: user={user_id}, "
            f"session={session_id}, project={project_id}"
        )

    # ==================== PUBLIC METHODS ====================

    async def check(
        self,
        tool_name: str,
        tool_input: Optional[Dict[str, Any]] = None,
    ) -> PermissionCheckResult:
        """
        Verifica a permissão para executar uma ferramenta.

        Args:
            tool_name: Nome da ferramenta
            tool_input: Parâmetros da ferramenta (opcional)

        Returns:
            PermissionCheckResult com a decisão e regra aplicada

        Example:
            result = await manager.check("edit_document", {"path": "/doc.md"})
            if result.is_allowed:
                # Executa a ferramenta
                pass
            elif result.needs_approval:
                # Mostra modal de aprovação
                pass
            else:
                # Bloqueia execução
                pass
        """
        tool_input = tool_input or {}

        # Carrega regras (com cache)
        rules = await self._get_rules()

        # Encontra a regra mais específica que se aplica
        matching_rule = self._find_matching_rule(rules, tool_name, tool_input)

        # Se encontrou regra, usa a decisão dela
        if matching_rule:
            decision = matching_rule.mode
            logger.debug(
                f"Permission check: tool={tool_name}, decision={decision}, "
                f"rule={matching_rule.tool_name} (scope={matching_rule.scope})"
            )
        else:
            # Fallback para default
            decision = DEFAULT_PERMISSION
            logger.debug(
                f"Permission check: tool={tool_name}, decision={decision} (default)"
            )

        return PermissionCheckResult(
            decision=decision,
            matching_rule=matching_rule,
            tool_name=tool_name,
            tool_input=tool_input,
        )

    async def add_rule(
        self,
        tool_name: str,
        mode: PermissionDecision,
        scope: str = "session",
        pattern: Optional[str] = None,
        description: Optional[str] = None,
    ) -> PermissionRule:
        """
        Adiciona uma nova regra de permissão.

        Args:
            tool_name: Nome da ferramenta (pode usar wildcards)
            mode: Modo de permissão (allow/deny/ask)
            scope: Escopo da regra (session/project/global)
            pattern: Padrão glob para matching do input
            description: Descrição opcional da regra

        Returns:
            PermissionRule criada

        Example:
            # Permitir todas as edições nesta sessão
            rule = await manager.add_rule(
                tool_name="edit_*",
                mode="allow",
                scope="session"
            )
        """
        # Valida scope
        scope_enum = PermissionScope(scope)
        mode_enum = PermissionMode(mode)

        # Determina session_id e project_id baseado no scope
        rule_session_id = self.session_id if scope == "session" else None
        rule_project_id = self.project_id if scope == "project" else None

        # Cria o modelo de banco
        db_permission = ToolPermission(
            user_id=self.user_id,
            tool_name=tool_name,
            pattern=pattern,
            mode=mode_enum,
            scope=scope_enum,
            session_id=rule_session_id,
            project_id=rule_project_id,
            description=description,
            created_by="user",
        )

        self.db.add(db_permission)
        await self.db.flush()

        # Invalida cache
        await self._invalidate_cache()

        # Cria e retorna a regra
        rule = PermissionRule(
            id=db_permission.id,
            tool_name=tool_name,
            mode=mode,
            scope=scope,
            pattern=pattern,
            session_id=rule_session_id,
            project_id=rule_project_id,
            created_at=db_permission.created_at,
            is_system=False,
        )

        logger.info(
            f"Permission rule added: tool={tool_name}, mode={mode}, "
            f"scope={scope}, id={db_permission.id}"
        )

        return rule

    async def remove_rule(self, rule_id: str) -> bool:
        """
        Remove uma regra de permissão.

        Args:
            rule_id: ID da regra a remover

        Returns:
            True se removida, False se não encontrada
        """
        stmt = select(ToolPermission).where(
            and_(
                ToolPermission.id == rule_id,
                ToolPermission.user_id == self.user_id,
            )
        )
        result = await self.db.execute(stmt)
        permission = result.scalar_one_or_none()

        if not permission:
            logger.warning(f"Permission rule not found: {rule_id}")
            return False

        await self.db.delete(permission)
        await self._invalidate_cache()

        logger.info(f"Permission rule removed: {rule_id}")
        return True

    async def get_rules(
        self,
        tool_name: Optional[str] = None,
        scope: Optional[str] = None,
    ) -> List[PermissionRule]:
        """
        Lista regras de permissão do usuário.

        Args:
            tool_name: Filtrar por nome de ferramenta
            scope: Filtrar por escopo

        Returns:
            Lista de PermissionRule
        """
        rules = await self._get_rules()

        # Filtra se necessário
        if tool_name:
            rules = [r for r in rules if r.tool_name == tool_name or r.matches_tool(tool_name)]
        if scope:
            rules = [r for r in rules if r.scope == scope]

        return rules

    async def clear_session_rules(self) -> int:
        """
        Remove todas as regras de sessão.

        Returns:
            Número de regras removidas
        """
        if not self.session_id:
            return 0

        stmt = select(ToolPermission).where(
            and_(
                ToolPermission.user_id == self.user_id,
                ToolPermission.scope == PermissionScope.SESSION,
                ToolPermission.session_id == self.session_id,
            )
        )
        result = await self.db.execute(stmt)
        permissions = result.scalars().all()

        count = len(permissions)
        for p in permissions:
            await self.db.delete(p)

        await self._invalidate_cache()

        logger.info(f"Cleared {count} session rules for session {self.session_id}")
        return count

    async def allow_once(
        self,
        tool_name: str,
        pattern: Optional[str] = None,
    ) -> PermissionRule:
        """
        Permite uma ferramenta apenas para esta sessão.

        Shortcut para add_rule com scope=session e mode=allow.

        Args:
            tool_name: Nome da ferramenta
            pattern: Padrão opcional para o input

        Returns:
            PermissionRule criada
        """
        return await self.add_rule(
            tool_name=tool_name,
            mode="allow",
            scope="session",
            pattern=pattern,
            description="Allowed once for this session",
        )

    async def allow_always(
        self,
        tool_name: str,
        pattern: Optional[str] = None,
    ) -> PermissionRule:
        """
        Permite uma ferramenta permanentemente.

        Shortcut para add_rule com scope=global e mode=allow.

        Args:
            tool_name: Nome da ferramenta
            pattern: Padrão opcional para o input

        Returns:
            PermissionRule criada
        """
        return await self.add_rule(
            tool_name=tool_name,
            mode="allow",
            scope="global",
            pattern=pattern,
            description="Always allowed",
        )

    async def deny_always(
        self,
        tool_name: str,
        pattern: Optional[str] = None,
    ) -> PermissionRule:
        """
        Bloqueia uma ferramenta permanentemente.

        Args:
            tool_name: Nome da ferramenta
            pattern: Padrão opcional para o input

        Returns:
            PermissionRule criada
        """
        return await self.add_rule(
            tool_name=tool_name,
            mode="deny",
            scope="global",
            pattern=pattern,
            description="Always denied",
        )

    # ==================== PRIVATE METHODS ====================

    async def _get_rules(self) -> List[PermissionRule]:
        """
        Obtém todas as regras aplicáveis (com cache).

        Returns:
            Lista de PermissionRule ordenada por prioridade
        """
        async with self._cache_lock:
            # Verifica cache
            if self._is_cache_valid():
                return self._rules_cache

            # Carrega do banco + sistema
            rules = await self._load_rules()

            # Atualiza cache
            self._rules_cache = rules
            self._cache_timestamp = datetime.utcnow()

            return rules

    def _is_cache_valid(self) -> bool:
        """Verifica se o cache ainda é válido."""
        if self._rules_cache is None or self._cache_timestamp is None:
            return False

        age = (datetime.utcnow() - self._cache_timestamp).total_seconds()
        return age < self.cache_ttl

    async def _invalidate_cache(self) -> None:
        """Invalida o cache de regras."""
        async with self._cache_lock:
            self._rules_cache = None
            self._cache_timestamp = None

    async def _load_rules(self) -> List[PermissionRule]:
        """
        Carrega regras do banco e combina com defaults do sistema.

        Returns:
            Lista de PermissionRule ordenada por prioridade
        """
        rules: List[PermissionRule] = []

        # 1. Carrega regras do banco de dados
        db_rules = await self._load_db_rules()
        rules.extend(db_rules)

        # 2. Adiciona defaults do sistema
        system_rules = self._get_system_rules()
        rules.extend(system_rules)

        # 3. Ordena por prioridade (menor primeiro)
        rules.sort(key=lambda r: r.priority)

        logger.debug(
            f"Loaded {len(db_rules)} DB rules + {len(system_rules)} system rules"
        )

        return rules

    async def _load_db_rules(self) -> List[PermissionRule]:
        """Carrega regras do banco de dados."""
        # Constrói query com filtros de escopo
        conditions = [ToolPermission.user_id == self.user_id]

        # Adiciona condições baseadas nos IDs disponíveis
        scope_conditions = [
            ToolPermission.scope == PermissionScope.GLOBAL,
        ]

        if self.session_id:
            scope_conditions.append(
                and_(
                    ToolPermission.scope == PermissionScope.SESSION,
                    ToolPermission.session_id == self.session_id,
                )
            )

        if self.project_id:
            scope_conditions.append(
                and_(
                    ToolPermission.scope == PermissionScope.PROJECT,
                    ToolPermission.project_id == self.project_id,
                )
            )

        conditions.append(or_(*scope_conditions))

        stmt = select(ToolPermission).where(and_(*conditions))
        result = await self.db.execute(stmt)
        db_permissions = result.scalars().all()

        # Converte para PermissionRule
        rules = []
        for p in db_permissions:
            rule = PermissionRule(
                id=p.id,
                tool_name=p.tool_name,
                mode=p.mode.value,
                scope=p.scope.value,
                pattern=p.pattern,
                session_id=p.session_id,
                project_id=p.project_id,
                created_at=p.created_at,
                is_system=False,
            )
            rules.append(rule)

        return rules

    def _get_system_rules(self) -> List[PermissionRule]:
        """Retorna regras padrão do sistema."""
        rules = []

        # Regras específicas por ferramenta
        for tool_name, mode in SYSTEM_DEFAULTS.items():
            rule = PermissionRule(
                tool_name=tool_name,
                mode=mode,
                scope="system",
                is_system=True,
            )
            rules.append(rule)

        # Regras por categoria (wildcards)
        for pattern, mode in TOOL_CATEGORIES.items():
            rule = PermissionRule(
                tool_name=pattern,
                mode=mode,
                scope="system",
                is_system=True,
            )
            rules.append(rule)

        return rules

    def _find_matching_rule(
        self,
        rules: List[PermissionRule],
        tool_name: str,
        tool_input: Dict[str, Any],
    ) -> Optional[PermissionRule]:
        """
        Encontra a regra mais específica que se aplica.

        A lógica de matching segue esta ordem:
        1. Primeiro verifica por escopo (session > project > global > system)
        2. Dentro do mesmo escopo, prefere regras com pattern específico
        3. Dentro do mesmo escopo sem pattern, prefere nome exato vs wildcard

        Args:
            rules: Lista de regras ordenadas por prioridade
            tool_name: Nome da ferramenta
            tool_input: Input da ferramenta

        Returns:
            PermissionRule mais específica ou None
        """
        # Regras já estão ordenadas por prioridade (scope)
        # Agrupa por prioridade para fazer matching correto
        rules_by_priority: Dict[int, List[PermissionRule]] = {}
        for rule in rules:
            priority = rule.priority
            if priority not in rules_by_priority:
                rules_by_priority[priority] = []
            rules_by_priority[priority].append(rule)

        # Verifica em ordem de prioridade
        for priority in sorted(rules_by_priority.keys()):
            scope_rules = rules_by_priority[priority]

            # Dentro do scope, procura pela regra mais específica
            best_match = self._find_best_match_in_scope(
                scope_rules, tool_name, tool_input
            )

            if best_match:
                return best_match

        return None

    def _find_best_match_in_scope(
        self,
        rules: List[PermissionRule],
        tool_name: str,
        tool_input: Dict[str, Any],
    ) -> Optional[PermissionRule]:
        """
        Encontra a melhor regra dentro de um escopo.

        Prioridade dentro do escopo:
        1. Nome exato + pattern específico
        2. Nome exato + sem pattern
        3. Wildcard + pattern específico
        4. Wildcard + sem pattern
        """
        exact_with_pattern: Optional[PermissionRule] = None
        exact_without_pattern: Optional[PermissionRule] = None
        wildcard_with_pattern: Optional[PermissionRule] = None
        wildcard_without_pattern: Optional[PermissionRule] = None

        for rule in rules:
            # Verifica se a regra se aplica
            if not rule.matches(tool_name, tool_input):
                continue

            is_exact = rule.tool_name == tool_name
            has_pattern = rule.pattern is not None

            if is_exact and has_pattern and not exact_with_pattern:
                exact_with_pattern = rule
            elif is_exact and not has_pattern and not exact_without_pattern:
                exact_without_pattern = rule
            elif not is_exact and has_pattern and not wildcard_with_pattern:
                wildcard_with_pattern = rule
            elif not is_exact and not has_pattern and not wildcard_without_pattern:
                wildcard_without_pattern = rule

        # Retorna na ordem de especificidade
        return (
            exact_with_pattern or
            exact_without_pattern or
            wildcard_with_pattern or
            wildcard_without_pattern
        )

    def _matches_rule(
        self,
        rule: PermissionRule,
        tool_name: str,
        tool_input: Dict[str, Any],
    ) -> bool:
        """
        Verifica se uma regra se aplica a uma ferramenta e input.

        Args:
            rule: Regra a verificar
            tool_name: Nome da ferramenta
            tool_input: Input da ferramenta

        Returns:
            True se a regra se aplica
        """
        return rule.matches(tool_name, tool_input)


# ==================== UTILITY FUNCTIONS ====================

def get_default_permission(tool_name: str) -> PermissionDecision:
    """
    Retorna a permissão padrão para uma ferramenta.

    Útil para verificações rápidas sem instanciar o manager.

    Args:
        tool_name: Nome da ferramenta

    Returns:
        Permissão padrão (allow/deny/ask)
    """
    # Verifica defaults específicos
    if tool_name in SYSTEM_DEFAULTS:
        return SYSTEM_DEFAULTS[tool_name]

    # Verifica categorias por wildcard
    for pattern, mode in TOOL_CATEGORIES.items():
        if fnmatch(tool_name, pattern):
            return mode

    return DEFAULT_PERMISSION


def is_high_risk_tool(tool_name: str) -> bool:
    """
    Verifica se uma ferramenta é de alto risco.

    Args:
        tool_name: Nome da ferramenta

    Returns:
        True se a ferramenta é de alto risco
    """
    high_risk_patterns = ["bash", "execute_*", "delete_*", "file_delete", "system_*"]

    for pattern in high_risk_patterns:
        if fnmatch(tool_name, pattern):
            return True

    return False


def is_read_only_tool(tool_name: str) -> bool:
    """
    Verifica se uma ferramenta é apenas de leitura.

    Args:
        tool_name: Nome da ferramenta

    Returns:
        True se a ferramenta é read-only
    """
    read_only_patterns = ["search_*", "read_*", "verify_*", "find_*", "list_*", "get_*"]

    for pattern in read_only_patterns:
        if fnmatch(tool_name, pattern):
            return True

    return False
