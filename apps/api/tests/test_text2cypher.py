"""
Tests for Text2Cypher security layers.

Tests the 3 security layers:
1. Keyword blocklist (reject writes)
2. Tenant filter injection
3. Structural validation
"""

import pytest

from app.services.graph_ask_service import (
    validate_cypher_readonly,
    inject_tenant_filter,
    CypherSecurityError,
)


# =============================================================================
# Layer 1+3: validate_cypher_readonly
# =============================================================================


class TestValidateCypherReadonly:
    """Testa validação de Cypher read-only."""

    def test_valid_match_return(self):
        cypher = "MATCH (n:Entity) RETURN n.name LIMIT 10"
        assert validate_cypher_readonly(cypher) is None

    def test_valid_optional_match(self):
        cypher = "OPTIONAL MATCH (n:Entity)-[:MENTIONS]->(m) RETURN n, m"
        assert validate_cypher_readonly(cypher) is None

    def test_valid_with_clause(self):
        cypher = "WITH 1 AS x MATCH (n) RETURN n LIMIT 5"
        assert validate_cypher_readonly(cypher) is None

    def test_valid_unwind(self):
        cypher = "UNWIND [1,2,3] AS x MATCH (n) WHERE n.id = x RETURN n"
        assert validate_cypher_readonly(cypher) is None

    def test_reject_create(self):
        cypher = "CREATE (n:Entity {name: 'test'}) RETURN n"
        error = validate_cypher_readonly(cypher)
        assert error is not None
        assert "CREATE" in error

    def test_reject_merge(self):
        cypher = "MERGE (n:Entity {name: 'test'}) RETURN n"
        error = validate_cypher_readonly(cypher)
        assert error is not None
        assert "MERGE" in error

    def test_reject_delete(self):
        cypher = "MATCH (n) DELETE n"
        error = validate_cypher_readonly(cypher)
        assert error is not None
        # DELETE detected but no RETURN — both violations caught

    def test_reject_detach_delete(self):
        cypher = "MATCH (n) DETACH DELETE n"
        error = validate_cypher_readonly(cypher)
        assert error is not None

    def test_reject_set(self):
        cypher = "MATCH (n:Entity) SET n.name = 'hack' RETURN n"
        error = validate_cypher_readonly(cypher)
        assert error is not None
        assert "SET" in error

    def test_reject_remove(self):
        cypher = "MATCH (n) REMOVE n.name RETURN n"
        error = validate_cypher_readonly(cypher)
        assert error is not None
        assert "REMOVE" in error

    def test_reject_drop(self):
        cypher = "DROP INDEX ON :Entity(name)"
        error = validate_cypher_readonly(cypher)
        assert error is not None

    def test_reject_call(self):
        cypher = "CALL db.schema.visualization()"
        error = validate_cypher_readonly(cypher)
        assert error is not None

    def test_reject_load_csv(self):
        cypher = "LOAD CSV FROM 'file:///etc/passwd' AS row RETURN row"
        error = validate_cypher_readonly(cypher)
        assert error is not None

    def test_reject_foreach(self):
        cypher = "MATCH (n) FOREACH (x IN [1] | SET n.x = x) RETURN n"
        error = validate_cypher_readonly(cypher)
        assert error is not None

    def test_reject_empty(self):
        error = validate_cypher_readonly("")
        assert error is not None
        assert "vazio" in error.lower()

    def test_reject_no_return(self):
        cypher = "MATCH (n:Entity) WHERE n.name = 'test'"
        error = validate_cypher_readonly(cypher)
        assert error is not None
        assert "RETURN" in error

    def test_reject_starts_with_invalid(self):
        cypher = "EXPLAIN MATCH (n) RETURN n"
        error = validate_cypher_readonly(cypher)
        assert error is not None

    def test_no_false_positive_on_property_names(self):
        """CREATED_AT, SETTINGS etc. should NOT trigger CREATE/SET blocklist."""
        cypher = "MATCH (n:Entity) WHERE n.created_at > '2024-01-01' RETURN n.name"
        # CREATED_AT contains CREATE as substring, but tokenized as CREATED_AT
        error = validate_cypher_readonly(cypher)
        assert error is None


# =============================================================================
# Layer 2: inject_tenant_filter
# =============================================================================


class TestInjectTenantFilter:
    """Testa injeção de filtro tenant_id."""

    def test_inject_into_document_match(self):
        cypher = "MATCH (d:Document)-[:HAS_CHUNK]->(c:Chunk) RETURN d.title"
        result = inject_tenant_filter(cypher, "tenant_123")
        assert "$tenant_id" in result or "tenant_id" in result

    def test_inject_without_document(self):
        """Se query não tem Document, wraps with prefix filter."""
        cypher = "MATCH (e:Entity) RETURN e.name LIMIT 10"
        result = inject_tenant_filter(cypher, "tenant_123")
        assert "Document" in result or "_allowed_docs" in result

    def test_scope_filter(self):
        cypher = "MATCH (d:Document) RETURN d"
        result = inject_tenant_filter(cypher, "tenant_123", scope="private")
        assert "$scope" in result or "scope" in result

    def test_case_id_filter(self):
        cypher = "MATCH (d:Document) RETURN d"
        result = inject_tenant_filter(cypher, "tenant_123", case_id="case_456")
        assert "$case_id" in result or "case_id" in result

    def test_include_global(self):
        cypher = "MATCH (d:Document) RETURN d"
        result = inject_tenant_filter(cypher, "tenant_123", include_global=True)
        assert "global" in result

    def test_sigilo_filter(self):
        cypher = "MATCH (d:Document) RETURN d"
        result = inject_tenant_filter(cypher, "tenant_123")
        assert "sigilo" in result


# =============================================================================
# Integration: combined security
# =============================================================================


class TestText2CypherSecurity:
    """Testa cenários combinados de segurança."""

    def test_legitimate_query_passes(self):
        """Query legítima deve passar todas as validações."""
        cypher = """
        MATCH (e:Entity)<-[:MENTIONS]-(c:Chunk)<-[:HAS_CHUNK]-(d:Document)
        WHERE e.entity_type = 'lei'
          AND (d.tenant_id = $tenant_id OR d.scope = 'global')
        RETURN e.name AS lei, count(c) AS mencoes
        ORDER BY mencoes DESC LIMIT 20
        """
        assert validate_cypher_readonly(cypher) is None

    def test_injection_attempt_blocked(self):
        """Tentativa de injection via UNION + CREATE deve ser bloqueada."""
        cypher = """
        MATCH (n:Entity) RETURN n.name
        UNION
        CREATE (n:Entity {name: 'hacked'}) RETURN n.name
        """
        error = validate_cypher_readonly(cypher)
        assert error is not None

    def test_set_via_subquery_blocked(self):
        """SET dentro de subquery deve ser bloqueado."""
        cypher = """
        MATCH (n:Entity)
        CALL { WITH n SET n.name = 'hacked' }
        RETURN n
        """
        error = validate_cypher_readonly(cypher)
        assert error is not None
