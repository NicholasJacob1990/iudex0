"""
Nodes do LangGraph Workflow

Cada node representa uma etapa do workflow de geração de documentos:
- outline: Geração de estrutura/outline
- research: Pesquisa jurídica
- debate: Debate multi-modelo
- audit: Auditoria e verificação
"""

from .claude_agent_node import ClaudeAgentNode
from .parallel_agents_node import ParallelAgentsNode

__all__ = ["ClaudeAgentNode", "ParallelAgentsNode"]
