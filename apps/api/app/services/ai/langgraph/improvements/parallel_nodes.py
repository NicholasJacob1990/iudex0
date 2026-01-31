"""
Parallel Nodes - Execute multiple LangGraph nodes concurrently.
"""
import asyncio
from typing import Any, Callable, Dict, List, Optional
from loguru import logger


async def run_nodes_parallel(
    nodes: List[Callable],
    state: Dict[str, Any],
    timeout: float = 120.0,
) -> List[Dict[str, Any]]:
    """Execute multiple node functions in parallel with timeout."""
    async def _run_node(node_fn: Callable, s: Dict[str, Any]) -> Dict[str, Any]:
        try:
            if asyncio.iscoroutinefunction(node_fn):
                return await node_fn(s)
            return node_fn(s)
        except Exception as e:
            logger.error(f"Node {node_fn.__name__} failed: {e}")
            return {"error": str(e), "node": node_fn.__name__}

    tasks = [_run_node(n, state.copy()) for n in nodes]
    try:
        results = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=False),
            timeout=timeout,
        )
        return list(results)
    except asyncio.TimeoutError:
        logger.error(f"Parallel execution timed out after {timeout}s")
        return [{"error": "timeout", "node": n.__name__} for n in nodes]


async def fan_out(
    state: Dict[str, Any],
    configs: List[Dict[str, Any]],
) -> List[asyncio.Task]:
    """Create tasks for parallel execution with different configs."""
    tasks = []
    for cfg in configs:
        fn = cfg.get("function")
        if fn:
            merged = {**state, **cfg.get("overrides", {})}
            task = asyncio.create_task(_safe_call(fn, merged))
            tasks.append(task)
    return tasks


async def _safe_call(fn: Callable, state: Dict[str, Any]) -> Dict[str, Any]:
    try:
        if asyncio.iscoroutinefunction(fn):
            return await fn(state)
        return fn(state)
    except Exception as e:
        return {"error": str(e)}


def fan_in(
    results: List[Dict[str, Any]],
    strategy: str = "merge",
) -> Dict[str, Any]:
    """Merge parallel results into a single state dict."""
    if strategy == "merge":
        merged = {}
        for r in results:
            if isinstance(r, dict) and "error" not in r:
                merged.update(r)
        return merged
    elif strategy == "best":
        valid = [r for r in results if isinstance(r, dict) and "error" not in r]
        return valid[0] if valid else {"error": "all_failed"}
    elif strategy == "all":
        return {"parallel_results": results}
    return {"error": f"unknown strategy: {strategy}"}
