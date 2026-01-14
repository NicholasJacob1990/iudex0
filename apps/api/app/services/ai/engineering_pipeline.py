"""
Engineering Pipeline - Agentic Flow

This pipeline implements the "Planner -> Executor -> Reviewer" pattern for
precise engineering tasks.

Pattern:
1. Planner (Gemini 3 Pro): Tactics, Tools, Context Gathering -> Generates Implementation Plan.
2. Executor (GPT-5.2 Codex): Implementation -> Generates Code/Diffs.
3. Reviewer (Claude Opus 4.5): Gatekeeper -> Approves or Rejects with feedback.

If Rejected, loops back to Executor with feedback.
"""

from typing import TypedDict, Literal, Optional, List, Dict, Any
from langgraph.graph import StateGraph, END
from loguru import logger
from jinja2 import Template
import json
import time
import re

from app.services.ai.prompts.engineering_prompts import (
    PROMPT_PLANNER_SYSTEM,
    PROMPT_PLANNER_USER,
    PROMPT_EXECUTOR_SYSTEM,
    PROMPT_EXECUTOR_USER,
    PROMPT_REVIEWER_SYSTEM,
    PROMPT_REVIEWER_USER
)

from app.services.ai.genai_utils import extract_genai_text

# =============================================================================
# STATE DEFINITION
# =============================================================================

class EngineeringState(TypedDict):
    # Input
    user_request: str
    file_context: str  # Content of relevant files
    
    # API Clients
    gemini_client: Any
    gpt_client: Any
    claude_client: Any
    
    # Models
    planner_model: str   # gemini-1.5-pro-latest (simulate v3)
    executor_model: str  # gpt-4o (simulate v5.2)
    reviewer_model: str  # claude-3-opus-20240229 (simulate v4.5)
    
    # Flow Data
    plan_json: Optional[Dict[str, Any]]
    plan_text: Optional[str]
    
    code_diffs: Optional[str]
    
    review_decision: Literal["APPROVE", "REJECT", "PENDING"]
    review_feedback: Optional[str]
    
    iteration_count: int
    max_iterations: int
    
    final_output: Optional[str]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

async def call_gpt_async(client, prompt: str, model: str, system: str = None) -> str:
    from app.services.ai.agent_clients import call_openai_async
    if system:
        prompt = f"{system}\n\n{prompt}"
    try:
        return await call_openai_async(client, prompt, model=model, timeout=120) or ""
    except Exception as e:
        logger.error(f"GPT Executor failed: {e}")
        return f"[Error: {e}]"

async def call_claude_async(client, prompt: str, model: str, system: str = None) -> str:
    from app.services.ai.agent_clients import call_anthropic_async
    if system:
        prompt = f"{system}\n\n{prompt}"
    try:
        return await call_anthropic_async(client, prompt, model=model, timeout=120) or ""
    except Exception as e:
        logger.error(f"Claude Reviewer failed: {e}")
        return f"[Error: {e}]"

def call_gemini_sync(drafter, prompt: str) -> str:
    # Assuming 'drafter' is the Gemini wrapper or client
    # For now, we use the unified client pattern if available, or just standard generate
    try:
        resp = drafter.generate_content(prompt) # Simplified
        return resp.text if resp else ""
    except Exception as e:
        logger.error(f"Gemini Planner failed: {e}")
        return f"[Error: {e}]"


# =============================================================================
# NODES
# =============================================================================

async def planner_node(state: EngineeringState) -> EngineeringState:
    """Gemini 3 Pro: Creates the execution plan."""
    logger.info("🧠 [Planner] Analyzing request...")
    
    system = PROMPT_PLANNER_SYSTEM
    prompt = PROMPT_PLANNER_USER.format(
        user_request=state['user_request'],
        context=state.get('file_context', '(Nenhum contexto de arquivo fornecido)')
    )
    
    # Using Gemini via specific client/wrapper
    # Note: In production we'd use the unified `call_gemini` or similar
    # Here assuming state['gemini_client'] is a configured GenerativeModel or similar
    try:
        # Assuming gemini_client is instance of genai.GenerativeModel
        resp = state['gemini_client'].generate_content(f"{system}\n\n{prompt}")
        plan_text = extract_genai_text(resp)
    except Exception as e:
        logger.error(f"Planner Error: {e}")
        plan_text = str(e)

    # Try parse JSON
    plan_json = {}
    try:
        # Clean markdown
        clean = re.sub(r"```json|```", "", plan_text).strip()
        plan_json = json.loads(clean)
    except:
        logger.warning("Planner output not valid JSON")
    
    return {
        **state,
        "plan_text": plan_text,
        "plan_json": plan_json,
        "review_decision": "PENDING"
    }


async def executor_node(state: EngineeringState) -> EngineeringState:
    """GPT-5.2 Codex: Implements the plan."""
    logger.info(f"🛠️ [Executor] Implementing (Iter: {state['iteration_count']})...")
    
    system = PROMPT_EXECUTOR_SYSTEM
    prompt = PROMPT_EXECUTOR_USER.format(
        plan=state.get('plan_text', ''),
        feedback=state.get('review_feedback', 'Nenhum (primeira tentativa)'),
        file_context=state.get('file_context', ''),
        iteration=state['iteration_count']
    )
    
    code_diffs = await call_gpt_async(
        state['gpt_client'],
        prompt,
        model=state.get('executor_model', 'gpt-4o'), # Fallback to 4o
        system=system
    )
    
    return {
        **state,
        "code_diffs": code_diffs,
        "iteration_count": state['iteration_count'] + 1
    }


async def reviewer_node(state: EngineeringState) -> EngineeringState:
    """Claude Opus 4.5: Reviews code against plan."""
    logger.info("⚖️ [Reviewer] Validating code...")
    
    system = PROMPT_REVIEWER_SYSTEM
    prompt = PROMPT_REVIEWER_USER.format(
        user_request=state['user_request'],
        plan=state.get('plan_text', ''),
        code_diffs=state.get('code_diffs', '')
    )
    
    review_raw = await call_claude_async(
        state['claude_client'],
        prompt,
        model=state.get('reviewer_model', 'claude-3-opus-20240229'),
        system=system
    )
    
    # Parse JSON
    decision = "REJECT"
    feedback = review_raw
    try:
        clean = re.sub(r"```json|```", "", review_raw).strip()
        data = json.loads(clean)
        decision = data.get("decision", "REJECT").upper()
        feedback = data.get("feedback", review_raw)
    except:
        logger.warning("Reviewer output not valid JSON, defaulting to REJECT")
        
    return {
        **state,
        "review_decision": decision,
        "review_feedback": feedback,
        "final_output": state.get("code_diffs") if decision == "APPROVE" else None
    }


# =============================================================================
# CONDITIONAL LOGIC
# =============================================================================

def should_approve(state: EngineeringState) -> Literal["executor", END]:
    """Loop back to executor if rejected, unless max retries reached."""
    if state['review_decision'] == "APPROVE":
        logger.info("✅ [Pipeline] Code APPROVED.")
        return END
    
    if state['iteration_count'] >= state['max_iterations']:
        logger.warning("🛑 [Pipeline] Max iterations reached. Stopping with feedback.")
        return END
        
    logger.info("🔄 [Pipeline] Rejected. Retrying...")
    return "executor"


# =============================================================================
# GRAPH
# =============================================================================

def create_engineering_pipeline() -> StateGraph:
    workflow = StateGraph(EngineeringState)
    
    workflow.add_node("planner", planner_node)
    workflow.add_node("executor", executor_node)
    workflow.add_node("reviewer", reviewer_node)
    
    workflow.set_entry_point("planner")
    workflow.add_edge("planner", "executor")
    workflow.add_edge("executor", "reviewer")
    
    workflow.add_conditional_edges(
        "reviewer",
        should_approve,
        {
            "executor": "executor",
            END: END
        }
    )
    
    return workflow

# Compiled Graph
engineering_pipeline = create_engineering_pipeline().compile()

async def run_engineering_pipeline(
    user_request: str,
    file_context: str,
    gemini_client,
    gpt_client,
    claude_client
) -> Dict[str, Any]:
    """Entry point for the engineering pipeline."""
    
    initial_state = EngineeringState(
        user_request=user_request,
        file_context=file_context,
        gemini_client=gemini_client,
        gpt_client=gpt_client,
        claude_client=claude_client,
        planner_model="gemini-1.5-pro-latest",
        executor_model="gpt-4o",
        reviewer_model="claude-3-opus-20240229",
        plan_json=None,
        plan_text=None,
        code_diffs=None,
        review_decision="PENDING",
        review_feedback=None,
        iteration_count=0,
        max_iterations=3, # Max 3 attempts
        final_output=None
    )
    
    result = await engineering_pipeline.ainvoke(initial_state)
    
    return {
        "final_output": result.get("final_output"),
        "plan": result.get("plan_text"),
        "diffs": result.get("code_diffs"),
        "decision": result.get("review_decision"),
        "feedback": result.get("review_feedback")
    }
