"""
Testes para endpoints de templates legais.
"""

from fastapi.testclient import TestClient


def test_list_legal_templates(client: TestClient, auth_headers: dict):
    """Lista templates legais predefinidos."""
    response = client.get("/api/templates/legal/", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    templates = data.get("templates", [])

    assert data.get("total", 0) >= 1
    assert any(item.get("id") == "peticao_inicial_civel" for item in templates)


def test_import_legal_template_creates_library_item(client: TestClient, auth_headers: dict):
    """Importa template legal e cria LibraryItem do usuario."""
    response = client.post(
        "/api/templates/legal/parecer_juridico/import",
        headers=auth_headers,
        json={"name": "Parecer Importado"}
    )

    assert response.status_code == 201
    data = response.json()

    assert data["name"] == "Parecer Importado"
    template_id = data["id"]

    detail = client.get(
        f"/api/templates/{template_id}",
        headers=auth_headers
    )
    assert detail.status_code == 200
    detail_data = detail.json()

    description = detail_data.get("description") or ""
    assert "<!-- IUDX_TEMPLATE_V1" in description
    assert "{{consulente}}" in description
    assert "imported:legal_template_library" in (detail_data.get("tags") or [])

    duplicate = client.post(
        "/api/templates/legal/parecer_juridico/import",
        headers=auth_headers,
        json={"name": "Parecer Importado"}
    )
    assert duplicate.status_code == 409
