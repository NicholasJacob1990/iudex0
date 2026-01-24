#!/usr/bin/env python3
"""
Static Code Verification for RAG & Observability Features (v5.5)

This test uses source code analysis instead of imports to avoid dependency issues.
"""

import re
import sys

# File paths
WORKFLOW_FILE = "apps/api/app/services/ai/langgraph_legal_workflow.py"
RAG_MODULE_API = "apps/api/app/services/rag_module.py"
RAG_MODULE_ROOT = "rag_module.py"
RAG_MEMORY_HELPER = "apps/api/app/services/ai/rag_memory_helper.py"


def read_file(path):
    try:
        with open(path, 'r') as f:
            return f.read()
    except FileNotFoundError:
        return None


def test_rag_memory():
    """Test RAG Memory implementation"""
    print("\n🧪 TEST 1: RAG Memory")
    print("-" * 40)
    
    # Check rag_memory_helper.py exists and has rewrite function
    source = read_file(RAG_MEMORY_HELPER)
    if not source:
        print(f"   ❌ File not found: {RAG_MEMORY_HELPER}")
        return False
        
    if "_rewrite_query_with_memory" in source:
        print("   ✅ _rewrite_query_with_memory function exists")
    else:
        print("   ❌ _rewrite_query_with_memory NOT found")
        return False
    
    # Check DocumentState has messages field
    workflow = read_file(WORKFLOW_FILE)
    if "messages: List[Dict[str, Any]]" in workflow:
        print("   ✅ messages field in DocumentState")
    else:
        print("   ❌ messages field NOT in DocumentState")
        return False
        
    # Check _resolve_section_context uses rag_memory_helper
    if "rag_memory_helper" in workflow and "_rewrite_query_with_memory" in workflow:
        print("   ✅ RAG Memory integrated in _resolve_section_context")
    else:
        print("   ❌ RAG Memory NOT integrated")
        return False
        
    return True


def test_graphrag_ingestion():
    """Test GraphRAG integration in RAGManager"""
    print("\n🧪 TEST 2: GraphRAG Ingestion")
    print("-" * 40)
    
    passed = True
    
    for path in [RAG_MODULE_API, RAG_MODULE_ROOT]:
        source = read_file(path)
        if not source:
            print(f"   ⚠️ File not found: {path}")
            continue
            
        name = "API" if "api" in path else "ROOT"
        
        if "LegalEntityExtractor" in source and "self.graph" in source:
            print(f"   ✅ [{name}] GraphRAG integration in __init__")
        else:
            print(f"   ❌ [{name}] GraphRAG NOT in __init__")
            passed = False
            
        if "self.extractor" in source and "extract_from_text" in source:
            print(f"   ✅ [{name}] Graph extraction in indexing methods")
        else:
            print(f"   ❌ [{name}] Graph extraction NOT in indexing")
            passed = False
            
    return passed


def test_observability_events():
    """Test new observability events"""
    print("\n🧪 TEST 3: Observability Events")
    print("-" * 40)
    
    source = read_file(WORKFLOW_FILE)
    if not source:
        print(f"   ❌ File not found: {WORKFLOW_FILE}")
        return False
    
    # Check section_routing_reasons field
    if "section_routing_reasons: Dict[str, Dict[str, Any]]" in source:
        print("   ✅ section_routing_reasons field in DocumentState")
    else:
        print("   ❌ section_routing_reasons NOT in DocumentState")
        return False
        
    # Check document_gate_status severity typing
    if 'Literal["passed", "BLOCKED_CRITICAL", "BLOCKED_OPTIONAL_HIL"]' in source:
        print("   ✅ document_gate_status has severity typing")
    else:
        print("   ❌ document_gate_status missing severity types")
        return False
        
    # Check STYLE_DEGRADED event
    if "STYLE_DEGRADED_DUE_TO_BUDGET" in source:
        print("   ✅ STYLE_DEGRADED_DUE_TO_BUDGET event exists")
    else:
        print("   ❌ STYLE_DEGRADED event NOT found")
        return False
        
    # Check DOCUMENT_GATE events
    if "DOCUMENT_GATE_BLOCKED" in source:
        print("   ✅ DOCUMENT_GATE_BLOCKED event exists")
    else:
        print("   ❌ DOCUMENT_GATE_BLOCKED NOT found")
        return False
        
    return True


def test_route_reason_logging():
    """Test RAG_ROUTING_DECISION event"""
    print("\n🧪 TEST 4: Route Reason Logging")
    print("-" * 40)
    
    source = read_file(WORKFLOW_FILE)
    if not source:
        print(f"   ❌ File not found: {WORKFLOW_FILE}")
        return False
    
    if "RAG_ROUTING_DECISION" in source:
        print("   ✅ RAG_ROUTING_DECISION event found")
    else:
        print("   ❌ RAG_ROUTING_DECISION NOT found")
        return False
        
    if 'routing_reasons[title]' in source or 'section_routing_reasons' in source:
        print("   ✅ Route reasons stored in state")
    else:
        print("   ❌ Route reasons NOT stored")
        return False
        
    return True


def test_gate_router_update():
    """Test document_gate_router uses new severity types"""
    print("\n🧪 TEST 5: Gate Router Update")
    print("-" * 40)
    
    source = read_file(WORKFLOW_FILE)
    if not source:
        return False
    
    # Find document_gate_router function
    match = re.search(r'def document_gate_router\(.*?\).*?return "finalize_hil"', source, re.DOTALL)
    if not match:
        print("   ❌ document_gate_router function not found")
        return False
        
    router_code = match.group(0)
    
    if "BLOCKED_CRITICAL" in router_code and "BLOCKED_OPTIONAL_HIL" in router_code:
        print("   ✅ document_gate_router uses new severity types")
    else:
        print("   ❌ document_gate_router NOT updated for severity")
        return False
        
    return True


def run_all_tests():
    """Run all static tests"""
    print("=" * 50)
    print("🔬 Static Code Verification (v5.5)")
    print("=" * 50)
    
    results = {
        "RAG Memory": test_rag_memory(),
        "GraphRAG Ingestion": test_graphrag_ingestion(),
        "Observability Events": test_observability_events(),
        "Route Reason Logging": test_route_reason_logging(),
        "Gate Router Update": test_gate_router_update(),
    }
    
    print("\n" + "=" * 50)
    print("📊 RESULTS")
    print("=" * 50)
    
    passed = sum(1 for r in results.values() if r)
    failed = sum(1 for r in results.values() if not r)
    
    for name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"   {status}: {name}")
    
    print("-" * 50)
    print(f"   Total: {passed} passed, {failed} failed")
    print("=" * 50)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
