"""
test_retry_configuration.py - Regression tests for retry configuration

Tests that max_rag_retries and max_research_verifier_attempts are correctly
respected by the LangGraph workflow when using quality profiles.

Run with: pytest tests/test_retry_configuration.py -v
"""
import pytest
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'apps', 'api'))


class TestRetryConfiguration:
    """Tests for retry configuration in quality profiles and workflow."""

    def test_quality_profiles_have_retry_settings(self):
        """Test that all quality profiles include retry configuration."""
        from app.services.ai.quality_profiles import QUALITY_PROFILES
        
        required_keys = [
            "max_research_verifier_attempts",
            "max_rag_retries",
            "rag_retry_expand_scope",
            "style_refine_max_rounds",
            "crag_min_best_score",
            "crag_min_avg_score",
        ]
        
        for profile_name, profile in QUALITY_PROFILES.items():
            for key in required_keys:
                assert key in profile, f"Profile '{profile_name}' missing key '{key}'"

    def test_rigoroso_profile_values(self):
        """Test that 'rigoroso' profile has expected retry values."""
        from app.services.ai.quality_profiles import QUALITY_PROFILES
        
        rigoroso = QUALITY_PROFILES["rigoroso"]
        
        assert rigoroso["max_research_verifier_attempts"] == 2
        assert rigoroso["max_rag_retries"] == 2
        assert rigoroso["rag_retry_expand_scope"] is True
        assert rigoroso["style_refine_max_rounds"] == 3
        assert rigoroso["crag_min_best_score"] == 0.50
        assert rigoroso["crag_min_avg_score"] == 0.40

    def test_auditoria_profile_values(self):
        """Test that 'auditoria' profile has expected retry values."""
        from app.services.ai.quality_profiles import QUALITY_PROFILES
        
        auditoria = QUALITY_PROFILES["auditoria"]
        
        assert auditoria["max_research_verifier_attempts"] == 3
        assert auditoria["max_rag_retries"] == 3
        assert auditoria["rag_retry_expand_scope"] is True
        assert auditoria["style_refine_max_rounds"] == 4
        assert auditoria["crag_min_best_score"] == 0.55
        assert auditoria["crag_min_avg_score"] == 0.45

    def test_rapido_profile_values(self):
        """Test that 'rapido' profile has conservative retry values."""
        from app.services.ai.quality_profiles import QUALITY_PROFILES
        
        rapido = QUALITY_PROFILES["rapido"]
        
        assert rapido["max_research_verifier_attempts"] == 1
        assert rapido["max_rag_retries"] == 1
        assert rapido["rag_retry_expand_scope"] is False
        assert rapido["style_refine_max_rounds"] == 1

    def test_resolve_profile_with_overrides(self):
        """Test that overrides correctly modify profile settings."""
        from app.services.ai.quality_profiles import resolve_quality_profile
        
        # Start with 'rapido' which has max_rag_retries=1
        resolved = resolve_quality_profile("rapido", {
            "max_rag_retries": 5,
            "max_research_verifier_attempts": 3,
        })
        
        assert resolved["max_rag_retries"] == 5
        assert resolved["max_research_verifier_attempts"] == 3
        # Other values should remain from rapido profile
        assert resolved["style_refine_max_rounds"] == 1

    def test_resolve_profile_none_overrides_ignored(self):
        """Test that None overrides don't modify profile settings."""
        from app.services.ai.quality_profiles import resolve_quality_profile
        
        resolved = resolve_quality_profile("rigoroso", {
            "max_rag_retries": None,
            "max_research_verifier_attempts": None,
        })
        
        # Should keep rigoroso values since overrides are None
        assert resolved["max_rag_retries"] == 2
        assert resolved["max_research_verifier_attempts"] == 2

    def test_crag_gate_retrieve_function(self):
        """Test CRAG gate validation logic."""
        from app.services.ai.langgraph_legal_workflow import crag_gate_retrieve
        
        # Empty results should pass through
        result = crag_gate_retrieve([])
        assert result["gate_passed"] is True
        
        # Good results should pass
        good_results = [
            {"score": 0.8},
            {"score": 0.7},
            {"score": 0.6},
        ]
        result = crag_gate_retrieve(good_results, min_best_score=0.5, min_avg_top3_score=0.4)
        assert result["gate_passed"] is True
        assert result["best_score"] == 0.8
        
        # Poor results should fail
        poor_results = [
            {"score": 0.3},
            {"score": 0.2},
            {"score": 0.1},
        ]
        result = crag_gate_retrieve(poor_results, min_best_score=0.5, min_avg_top3_score=0.4)
        assert result["gate_passed"] is False
        assert result["safe_mode"] is True

    def test_profile_escalation(self):
        """Test that retry settings escalate properly across profiles."""
        from app.services.ai.quality_profiles import QUALITY_PROFILES
        
        profiles_order = ["rapido", "padrao", "rigoroso", "auditoria"]
        
        prev_retries = 0
        for profile_name in profiles_order:
            profile = QUALITY_PROFILES[profile_name]
            current_retries = profile["max_rag_retries"] + profile["max_research_verifier_attempts"]
            
            # Each profile should have same or more retries than previous
            assert current_retries >= prev_retries, \
                f"Profile '{profile_name}' has fewer total retries than previous profile"
            
            prev_retries = current_retries


class TestDocumentStateRetryFields:
    """Tests for retry-related fields in DocumentState."""

    def test_document_state_has_retry_fields(self):
        """Test that DocumentState TypedDict includes all retry fields."""
        from app.services.ai.langgraph_legal_workflow import DocumentState
        import typing
        
        # Get annotations from TypedDict
        annotations = typing.get_type_hints(DocumentState)
        
        expected_fields = [
            "max_research_verifier_attempts",
            "max_rag_retries",
            "verification_retry",
            "verification_retry_reason",
            "verifier_attempts",
            "rag_retry_expand_scope",
            "research_retry_progress",
        ]
        
        for field in expected_fields:
            assert field in annotations, f"DocumentState missing field '{field}'"


# =============================================================================
# Run tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
