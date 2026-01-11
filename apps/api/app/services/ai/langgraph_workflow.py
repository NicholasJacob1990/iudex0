"""
LangGraph Workflow for Minuta Generation
"""

from typing import TypedDict, List, Dict, Any, Optional, Annotated
import operator
from loguru import logger

from langgraph.graph import StateGraph, END

from app.services.ai.agents import ClaudeAgent, GeminiAgent, GPTAgent
from app.services.legal_prompts import LegalPrompts

class AgentState(TypedDict):
    prompt: str
    context: Dict[str, Any]
    plan: Optional[str]
    draft: Optional[str]
    reviews: List[Dict[str, Any]]
    final_content: Optional[str]
    iteration: int
    max_iterations: int
    model: str

class MinutaWorkflow:
    def __init__(self):
        self.claude = ClaudeAgent()
        self.gemini = GeminiAgent()
        self.gpt = GPTAgent()
        self.prompts = LegalPrompts()
        
        # Initialize graph
        self.workflow = self._create_workflow()

    def _get_agent_for_model(self, model_name: str):
        """Selects the appropriate agent based on model name"""
        if "gemini" in model_name:
            return self.gemini
        elif "gpt" in model_name:
            return self.gpt
        else:
            return self.claude

    async def strategist_node(self, state: AgentState):
        """Analyzes the request and creates a plan"""
        logger.info("🤔 Strategist: Planning document structure...")
        system_prompt = self.prompts.get_system_prompt_generator()
        prompt = f"""
Analise a solicitação e elabore um PLANO/ROTEIRO detalhado para o documento jurídico.

Solicitação do usuário:
{state['prompt']}

Contexto disponível (resumo/metadata):
{state['context']}

Regras:
- Responda em português (pt-BR) e em Markdown.
- Se faltar informação essencial, liste primeiro **Perguntas de Esclarecimento (máx. 10)**.
- Se houver informações suficientes, entregue um **roteiro numerado** com seções, subitens e checklist de documentos/provas.
- Não invente fatos, datas, valores ou números de julgados.

Saída: retorne APENAS o plano/roteiro (sem redigir a peça completa).
"""
        
        # Strategist is always a high-reasoning model (Claude or GPT-4)
        response = await self.claude.generate(prompt, state['context'], system_prompt=system_prompt)
        return {"plan": response.content}

    async def drafter_node(self, state: AgentState):
        """Drafts the document based on the plan"""
        logger.info("✍️ Drafter: Writing content...")
        system_prompt = self.prompts.get_system_prompt_generator()
        prompt = f"""
Redija o DOCUMENTO JURÍDICO completo com base no plano abaixo.

PLANO/ROTEIRO:
{state['plan']}

SOLICITAÇÃO ORIGINAL:
{state['prompt']}

Regras:
- Saída em Markdown, com títulos e numeração coerente.
- Se algum dado essencial estiver ausente, use [[PENDENTE: ...]] e adicione ao final uma seção **Pendências e documentos a obter**.
- Não invente leis/súmulas/julgados. Se não houver base no contexto, evite citar números e marque pendência.

Entregue o texto integral do documento.
"""
        
        # Use selected model for drafting
        agent = self._get_agent_for_model(state['model'])
        response = await agent.generate(prompt, state['context'], system_prompt=system_prompt)
        return {"draft": response.content}

    async def reviewer_node(self, state: AgentState):
        """Reviews the draft"""
        logger.info("⚖️ Reviewer: Analyzing draft...")
        
        # Gemini is great for legal review (large context)
        system_prompt = self.prompts.get_system_prompt_legal_reviewer()
        review_prompt = f"""
Revise tecnicamente a minuta abaixo.

MINUTA:
{state['draft']}

Responda EXCLUSIVAMENTE em JSON válido (sem markdown) no formato:
{{
  "approved": boolean,
  "score": number,
  "comments": ["string"],
  "critical_issues": ["string"],
  "missing_items": ["string"]
}}

Regras:
- Se detectar citação/julgado potencialmente inventado, aponte explicitamente em critical_issues.
- Se detectar placeholders [[PENDENTE: ...]], indique o que precisa ser preenchido em missing_items.
"""
        
        response = await self.gemini.generate(review_prompt, state['context'], system_prompt=system_prompt)
        
        # Mock parsing for now - in production use structured output
        review = {
            "agent": "Reviewer",
            "content": response.content,
            "approved": "approved" in response.content.lower() and "not approved" not in response.content.lower()
        }
        
        return {"reviews": [review]}

    async def finalizer_node(self, state: AgentState):
        """Incorporates feedback and finalizes"""
        logger.info("🏁 Finalizer: Polishing document...")
        system_prompt = self.prompts.get_system_prompt_generator()
        prompt = f"""
Finalize o documento com base na revisão.

RASCUNHO:
{state['draft']}

REVISÃO (JSON ou texto):
{state['reviews'][-1]['content']}

Regras:
- Aplique correções objetivas e preserve a estrutura.
- Não invente fatos/citações; se algo não puder ser validado, mantenha como [[PENDENTE: ...]].
- Retorne APENAS o documento final em Markdown.
"""
        
        agent = self._get_agent_for_model(state['model'])
        response = await agent.generate(prompt, state['context'], system_prompt=system_prompt)
        return {"final_content": response.content}

    def _create_workflow(self):
        workflow = StateGraph(AgentState)
        
        # Add nodes
        workflow.add_node("strategist", self.strategist_node)
        workflow.add_node("drafter", self.drafter_node)
        workflow.add_node("reviewer", self.reviewer_node)
        workflow.add_node("finalizer", self.finalizer_node)
        
        # Define edges
        workflow.set_entry_point("strategist")
        workflow.add_edge("strategist", "drafter")
        workflow.add_edge("drafter", "reviewer")
        
        # Conditional edge based on review
        def should_continue(state: AgentState):
            last_review = state['reviews'][-1]
            # Simple logic: if approved or max iterations reached, go to finalizer
            # Otherwise could loop back to drafter (omitted for simplicity/speed)
            return "finalizer"

        workflow.add_edge("reviewer", "finalizer")
        workflow.add_edge("finalizer", END)
        
        return workflow.compile()

    def _compact_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compacts context to fit within window limits.
        Simple implementation: Summarizes large text fields if needed.
        """
        compacted = context.copy()
        
        # Mock compaction logic
        # In production, this would use an LLM to summarize 'active_items' or large text fields
        if "active_items" in compacted and len(str(compacted["active_items"])) > 10000:
            logger.info("⚠️ Context too large, compacting...")
            # Placeholder for compaction
            compacted["active_items_summary"] = "Summary of active items..."
            # We keep the original for now but in a real scenario we'd replace it or truncate
            
        return compacted

    async def run(self, prompt: str, context: Dict[str, Any], model: str = "claude-4.5-sonnet"):
        """Executes the workflow"""
        
        # Compact context if necessary
        compacted_context = self._compact_context(context)
        
        initial_state = {
            "prompt": prompt,
            "context": compacted_context,
            "plan": None,
            "draft": None,
            "reviews": [],
            "final_content": None,
            "iteration": 0,
            "max_iterations": 1,
            "model": model
        }
        
        result = await self.workflow.ainvoke(initial_state)
        return result
