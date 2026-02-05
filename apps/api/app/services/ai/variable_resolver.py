"""Variable resolver for @references and {{}} references in workflow prompt templates."""
import re
from typing import Any, Dict, List, Optional

from loguru import logger


class VariableResolver:
    """Resolve variable references in prompt templates.

    Supports two syntaxes:
    - Legacy: @node_id or @node_id.output
    - New:    {{node_id.output}} or {{node_id.sources}}

    Both reference outputs from upstream nodes in the workflow.
    """

    # Legacy @-mention pattern
    AT_PATTERN = re.compile(r'@([\w]+)(?:\.(output|sources|metadata|files))?')

    # New {{node_id.field}} pattern
    BRACE_PATTERN = re.compile(r'\{\{([^}]+)\}\}')

    def _resolve_ref(self, node_id: str, field: str, variables: dict, step_outputs: dict) -> Optional[str]:
        """Resolve a single node_id.field reference against state."""
        # Try direct variable lookup
        key = f"@{node_id}.{field}" if field != "output" else f"@{node_id}"
        if key in variables:
            return str(variables[key])

        # Also try the dotted key for output
        if field == "output" and f"@{node_id}.output" in variables:
            return str(variables[f"@{node_id}.output"])

        # Try step_outputs
        if node_id in step_outputs:
            step = step_outputs[node_id]
            if isinstance(step, dict):
                if field in step:
                    val = step[field]
                    if isinstance(val, list):
                        return "\n".join(str(v) for v in val)
                    return str(val)
                if "output" in step:
                    return str(step["output"])
            else:
                return str(step)

        return None

    def resolve(self, template: str, state: dict) -> str:
        """Replace all variable refs (both @ and {{}}) with actual values from state."""
        variables = state.get("variables", {})
        step_outputs = state.get("step_outputs", {})

        # First pass: resolve {{node_id.field}} references
        def brace_replacer(match: re.Match) -> str:
            ref = match.group(1).strip()
            parts = ref.split(".", 1)
            node_id = parts[0].strip()
            field = parts[1].strip() if len(parts) > 1 else "output"

            result = self._resolve_ref(node_id, field, variables, step_outputs)
            if result is not None:
                return result

            logger.warning(f"[VariableResolver] Unresolved brace reference: {match.group(0)}")
            return f"[Referencia nao encontrada: {ref}]"

        if "{{" in template:
            template = self.BRACE_PATTERN.sub(brace_replacer, template)

        # Second pass: resolve @node_id references (legacy)
        def at_replacer(match: re.Match) -> str:
            node_id = match.group(1)
            field = match.group(2) or "output"

            result = self._resolve_ref(node_id, field, variables, step_outputs)
            if result is not None:
                return result

            logger.warning(f"[VariableResolver] Unresolved variable: {match.group(0)}")
            return match.group(0)  # Leave unresolved

        return self.AT_PATTERN.sub(at_replacer, template)

    def get_available_variables(self, graph_json: dict, up_to_node: str) -> List[str]:
        """Return list of available @variables for a given node position.

        Traverses the graph backwards from the target node to find all
        upstream nodes whose outputs are available.
        """
        nodes = graph_json.get("nodes", [])
        edges = graph_json.get("edges", [])

        # Build reverse adjacency (target -> sources)
        reverse_adj: Dict[str, List[str]] = {}
        for edge in edges:
            tgt = edge.get("target", "")
            src = edge.get("source", "")
            reverse_adj.setdefault(tgt, []).append(src)

        # BFS backwards from up_to_node
        upstream: set[str] = set()
        queue = list(reverse_adj.get(up_to_node, []))
        while queue:
            nid = queue.pop(0)
            if nid in upstream:
                continue
            upstream.add(nid)
            queue.extend(reverse_adj.get(nid, []))

        # Build variable list from upstream nodes
        variables: List[str] = []
        node_types = {n["id"]: n.get("type", "") for n in nodes}
        for nid in upstream:
            ntype = node_types.get(nid, "")
            variables.append(f"@{nid}")
            variables.append(f"@{nid}.output")
            if ntype == "rag_search":
                variables.append(f"@{nid}.sources")
            if ntype == "file_upload":
                variables.append(f"@{nid}.files")

        return sorted(variables)

    def validate_references(self, graph_json: dict) -> List[str]:
        """Check all references (both @ and {{}}) in all nodes resolve to upstream outputs."""
        errors: List[str] = []
        nodes = graph_json.get("nodes", [])

        for node in nodes:
            node_id = node.get("id", "")
            node_data = node.get("data", {})

            # Check prompt field
            prompt = node_data.get("prompt", "")
            if not prompt:
                continue

            available = self.get_available_variables(graph_json, node_id)
            available_ids = {v.split(".")[0].lstrip("@") for v in available}

            # Validate @-syntax references
            at_refs = self.AT_PATTERN.findall(prompt)
            for ref_node_id, ref_field in at_refs:
                if ref_node_id not in available_ids:
                    errors.append(
                        f"Node '{node_id}': @{ref_node_id} references a node "
                        f"that is not upstream"
                    )

            # Validate {{}} -syntax references
            brace_refs = self.BRACE_PATTERN.findall(prompt)
            for ref in brace_refs:
                parts = ref.strip().split(".", 1)
                ref_node_id = parts[0].strip()
                if ref_node_id not in available_ids:
                    errors.append(
                        f"Node '{node_id}': {{{{{ref}}}}} references a node "
                        f"that is not upstream"
                    )

        return errors
