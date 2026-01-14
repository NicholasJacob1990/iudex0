import asyncio
import sys
import os
from unittest.mock import MagicMock, AsyncMock

# Add project root to path
# Mock Env Vars for Settings Validation
os.environ["SECRET_KEY"] = "test_secret"
os.environ["DATABASE_URL"] = "sqlite:///test.db"
os.environ["JWT_SECRET_KEY"] = "test_jwt"
os.environ["GOOGLE_API_KEY"] = "test_google_key"
os.environ["OPENAI_API_KEY"] = "test_openai_key"
os.environ["ANTHROPIC_API_KEY"] = "test_anthropic_key"

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../apps/api")))


from app.services.ai.engineering_pipeline import run_engineering_pipeline

async def test_pipeline():
    print("🚀 Starting Engineering Pipeline Test...")
    
    # Mock Clients
    gemini_client = MagicMock()
    gemini_client.generate_content.return_value.text = """
    ```json
    {
        "understanding": "Refactor the authentication module",
        "files_to_touch": ["auth.py"],
        "steps": [{"step": 1, "action": "Add JWT support"}]
    }
    ```
    """
    
    gpt_client = MagicMock()
    # GPT Executor returns code diffs
    # We need to mock call_openai_async which is imported inside the module
    # But since we pass the client, the function uses it.
    # Actually checking engineering_pipeline.py, it imports call_openai_async.
    # So we need to mock that function in the module or assume client works.
    # The code calls: await call_openai_async(client, ...)
    # If we want to mock the result, we should mock call_openai_async.
    
    claude_client = MagicMock()
    
    # We will mock the helper functions in engineering_pipeline
    import app.services.ai.engineering_pipeline as pipeline_module
    
    pipeline_module.call_gpt_async = AsyncMock(return_value="```python\n# New Auth Code\n```")
    pipeline_module.call_claude_async = AsyncMock(side_effect=[
        # First review: Reject
        '{"decision": "REJECT", "feedback": "Fix syntax error"}',
        # Second review: Approve
        '{"decision": "APPROVE", "feedback": "LGTM"}'
    ])
    
    user_request = "Add JWT support to auth.py"
    file_context = "def login(): pass"
    
    result = await run_engineering_pipeline(
        user_request,
        file_context,
        gemini_client,
        gpt_client,
        claude_client
    )
    
    print("\n✅ Pipeline Finished!")
    print(f"Plan: {result.get('plan')}")
    print(f"Diffs: {result.get('diffs')}")
    print(f"Final Decision: {result.get('decision')}")
    print(f"Feedback: {result.get('feedback')}")
    
    assert result.get('decision') == "APPROVE"
    assert "New Auth Code" in result.get('diffs')

if __name__ == "__main__":
    asyncio.run(test_pipeline())
