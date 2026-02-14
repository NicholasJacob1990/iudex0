from datetime import datetime, timezone
from types import SimpleNamespace

from app.api.endpoints.workflows import _workflow_to_response


def _base_workflow(**overrides):
    now = datetime.now(timezone.utc)
    data = {
        "id": "wf-1",
        "user_id": "user-1",
        "name": "Teste",
        "description": None,
        "graph_json": {"nodes": [], "edges": []},
        "is_active": True,
        "is_template": False,
        "tags": [],
        "embedded_files": [],
        "status": "draft",
        "published_version": None,
        "submitted_at": None,
        "approved_at": None,
        "rejection_reason": None,
        "published_slug": None,
        "published_config": None,
        "category": None,
        "practice_area": None,
        "output_type": None,
        "run_count": 0,
        "created_at": now,
        "updated_at": now,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_workflow_to_response_normalizes_invalid_graph_json_and_lists():
    wf = _base_workflow(
        graph_json=None,
        tags=None,
        embedded_files="invalid",
    )

    response = _workflow_to_response(wf)

    assert response.graph_json == {"nodes": [], "edges": []}
    assert response.tags == []
    assert response.embedded_files == []


def test_workflow_to_response_parses_graph_json_string():
    wf = _base_workflow(
        graph_json='{"nodes":[{"id":"n1"}],"edges":[{"id":"e1"}],"meta":{"v":1}}'
    )

    response = _workflow_to_response(wf)

    assert response.graph_json["nodes"] == [{"id": "n1"}]
    assert response.graph_json["edges"] == [{"id": "e1"}]
    assert response.graph_json["meta"] == {"v": 1}
