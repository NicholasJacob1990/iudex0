"""
test_core.py - Unit tests for core components
Run with: pytest tests/test_core.py -v
"""
import pytest
import os
import sys
import tempfile

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# =============================================================================
# JobManager Tests
# =============================================================================

class TestJobManager:
    
    @pytest.fixture
    def job_manager(self):
        """Create a JobManager with a temporary database."""
        from job_manager import JobManager
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        jm = JobManager(db_path=db_path)
        yield jm
        # Cleanup
        os.unlink(db_path)
    
    def test_create_job(self, job_manager):
        """Test job creation returns a valid UUID."""
        job_id = job_manager.create_job({"tema": "Test", "mode": "PARECER"})
        assert job_id is not None
        assert len(job_id) == 36  # UUID format
    
    def test_get_job(self, job_manager):
        """Test retrieving a created job."""
        config = {"tema": "Responsabilidade Civil", "mode": "PARECER"}
        job_id = job_manager.create_job(config)
        
        job = job_manager.get_job(job_id)
        assert job is not None
        assert job["job_id"] == job_id
        assert job["status"] == "pending"
        assert job["config"]["tema"] == "Responsabilidade Civil"
    
    def test_get_nonexistent_job(self, job_manager):
        """Test getting a job that doesn't exist returns None."""
        job = job_manager.get_job("nonexistent-id")
        assert job is None
    
    def test_update_job(self, job_manager):
        """Test updating job status and progress."""
        job_id = job_manager.create_job({"tema": "Test"})
        
        job_manager.update_job(job_id, status="processing", progress=50)
        job = job_manager.get_job(job_id)
        
        assert job["status"] == "processing"
        assert job["progress"] == 50
    
    def test_update_job_result(self, job_manager):
        """Test storing job result."""
        job_id = job_manager.create_job({"tema": "Test"})
        
        result = {"markdown": "# Test Document", "filename": "test.md"}
        job_manager.update_job(job_id, status="done", result=result, progress=100)
        
        job = job_manager.get_job(job_id)
        assert job["status"] == "done"
        assert job["result"]["markdown"] == "# Test Document"
    
    def test_list_jobs(self, job_manager):
        """Test listing recent jobs."""
        # Create 3 jobs
        for i in range(3):
            job_manager.create_job({"tema": f"Test {i}"})
        
        jobs = job_manager.list_jobs(limit=10)
        assert len(jobs) == 3
    
    def test_cleanup_old_jobs(self, job_manager):
        """Test cleanup doesn't delete recent jobs."""
        job_id = job_manager.create_job({"tema": "Recent Job"})
        
        # Cleanup jobs older than 7 days (this job is new)
        deleted = job_manager.cleanup_old_jobs(days=7)
        assert deleted == 0
        
        # Job should still exist
        job = job_manager.get_job(job_id)
        assert job is not None


# =============================================================================
# TextDeduplicator Tests (requires sentence-transformers)
# =============================================================================

class TestTextDeduplicator:
    
    @pytest.fixture
    def deduplicator(self):
        """Get TextDeduplicator instance."""
        try:
            from rag_module import TextDeduplicator
            return TextDeduplicator()
        except ImportError:
            pytest.skip("sentence-transformers not installed")
    
    def test_deduplicate_empty_list(self, deduplicator):
        """Test deduplicate with empty list."""
        result = deduplicator.deduplicate([])
        assert result == []
    
    def test_deduplicate_single_item(self, deduplicator):
        """Test deduplicate with single item."""
        result = deduplicator.deduplicate(["Hello world"])
        assert result == [0]
    
    def test_deduplicate_no_duplicates(self, deduplicator):
        """Test deduplicate with distinct items."""
        texts = [
            "A Lei 8.666/93 regula as licitações públicas.",
            "O Código Civil brasileiro foi promulgado em 2002.",
            "A Constituição Federal estabelece direitos fundamentais."
        ]
        result = deduplicator.deduplicate(texts, threshold=0.90)
        assert len(result) == 3
        assert result == [0, 1, 2]
    
    def test_deduplicate_with_duplicates(self, deduplicator):
        """Test deduplicate identifies similar texts."""
        texts = [
            "A responsabilidade civil do Estado por omissão requer dolo ou culpa.",
            "A responsabilidade civil estatal por conduta omissiva exige dolo ou culpa.",  # Similar
            "O contrato de trabalho pode ser por prazo determinado ou indeterminado."  # Different
        ]
        result = deduplicator.deduplicate(texts, threshold=0.85)
        # Should keep first and third, remove second as duplicate of first
        assert 0 in result
        assert 2 in result
        # Length should be 2 (one duplicate removed)
        assert len(result) == 2


# =============================================================================
# RateLimiter Tests
# =============================================================================

class TestRateLimiter:
    
    @pytest.fixture
    def rate_limiter(self):
        """Create a RateLimiter."""
        from juridico_gemini import RateLimiter
        return RateLimiter(max_requests_per_minute=10)
    
    def test_rate_limiter_allows_requests(self, rate_limiter):
        """Test rate limiter allows requests under limit."""
        # Should not raise or block for a few requests
        for _ in range(5):
            rate_limiter.wait_if_needed()
        assert True  # If we got here, no blocking occurred
    
    @pytest.mark.asyncio
    async def test_rate_limiter_async(self, rate_limiter):
        """Test async rate limiter."""
        await rate_limiter.wait_if_needed_async()
        assert True


# =============================================================================
# Run tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
