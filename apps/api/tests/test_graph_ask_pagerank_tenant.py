import pytest

from app.services.graph_ask_service import CYPHER_TEMPLATES, GraphAskService, GraphOperation


def test_ranking_template_is_tenant_scoped_metric():
    template = CYPHER_TEMPLATES["ranking"]
    assert "TenantEntityMetric" in template
    assert "tenant_id: $tenant_id" in template
    assert "metric.pagerank_score" in template


def test_neighbors_template_uses_metric_not_entity_property():
    template = CYPHER_TEMPLATES["neighbors"]
    assert "HAS_TENANT_METRIC" in template
    assert "coalesce(metric.pagerank_score" in template
    assert "coalesce(neighbor.pagerank_score" not in template


def test_prepare_params_sets_ranking_defaults():
    service = GraphAskService()
    params = service._prepare_params(
        operation=GraphOperation.RANKING,
        params={},
        tenant_id="tenant_1",
        scope=None,
        case_id=None,
        include_global=True,
    )
    assert params["limit"] == 20
    assert params["entity_type"] is None
    assert params["tenant_id"] == "tenant_1"


def test_new_semantic_templates_exist():
    assert "legal_chain" in CYPHER_TEMPLATES
    assert "precedent_network" in CYPHER_TEMPLATES
    assert "judge_decisions" in CYPHER_TEMPLATES
    assert "fraud_signals" in CYPHER_TEMPLATES
    assert "process_network" in CYPHER_TEMPLATES
    assert "process_timeline" in CYPHER_TEMPLATES


def test_legal_chain_query_injects_hops_and_relation_types():
    service = GraphAskService()
    template = CYPHER_TEMPLATES["legal_chain"]
    query = service._build_query_text(
        operation=GraphOperation.LEGAL_CHAIN,
        template=template,
        params={"max_hops": 3, "relation_types": ["CITA", "APLICA", "DROP_TABLE"]},
    )
    assert "__MAX_HOPS__" not in query
    assert "__REL_TYPES__" not in query
    assert "CITA|APLICA" in query
    assert "DROP_TABLE" not in query


def test_prepare_params_sets_fraud_defaults():
    service = GraphAskService()
    params = service._prepare_params(
        operation=GraphOperation.FRAUD_SIGNALS,
        params={},
        tenant_id="tenant_1",
        scope=None,
        case_id=None,
        include_global=True,
    )
    assert params["limit"] == 20
    assert params["min_shared_docs"] == 2
