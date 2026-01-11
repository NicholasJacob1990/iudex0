"""
Testes para autenticação
"""

import pytest
from fastapi.testclient import TestClient
from app.models.user import User


def test_register_individual_user(client: TestClient):
    """Teste de registro de usuário individual"""
    response = client.post(
        "/api/auth/register",
        json={
            "email": "newuser@example.com",
            "password": "NewUser@123",
            "name": "New User",
            "account_type": "INDIVIDUAL",
            "oab": "654321",
            "oab_state": "RJ",
            "cpf": "12345678900"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "newuser@example.com"
    assert data["user"]["name"] == "New User"


def test_register_institutional_user(client: TestClient):
    """Teste de registro de usuário institucional"""
    response = client.post(
        "/api/auth/register",
        json={
            "email": "lawfirm@example.com",
            "password": "LawFirm@123",
            "name": "Law Firm User",
            "account_type": "INSTITUTIONAL",
            "institution_name": "Test Law Firm",
            "cnpj": "12345678000190",
            "position": "Partner",
            "team_size": 10
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["user"]["email"] == "lawfirm@example.com"
    assert data["user"]["institution_name"] == "Test Law Firm"


def test_register_duplicate_email(client: TestClient, test_user: User):
    """Teste de registro com email duplicado"""
    response = client.post(
        "/api/auth/register",
        json={
            "email": "test@example.com",  # Email já existe
            "password": "Test@123",
            "name": "Duplicate User",
            "account_type": "INDIVIDUAL"
        }
    )
    
    assert response.status_code == 400
    assert "já cadastrado" in response.json()["detail"]


def test_login_success(client: TestClient, test_user: User):
    """Teste de login bem-sucedido"""
    response = client.post(
        "/api/auth/login",
        json={
            "email": "test@example.com",
            "password": "Test@123"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["user"]["email"] == "test@example.com"


def test_login_wrong_password(client: TestClient, test_user: User):
    """Teste de login com senha incorreta"""
    response = client.post(
        "/api/auth/login",
        json={
            "email": "test@example.com",
            "password": "WrongPassword@123"
        }
    )
    
    assert response.status_code == 401
    assert "incorretos" in response.json()["detail"]


def test_login_nonexistent_user(client: TestClient):
    """Teste de login com usuário inexistente"""
    response = client.post(
        "/api/auth/login",
        json={
            "email": "nonexistent@example.com",
            "password": "Password@123"
        }
    )
    
    assert response.status_code == 401


def test_get_current_user(client: TestClient, auth_headers: dict):
    """Teste de obtenção do usuário atual"""
    response = client.get(
        "/api/auth/me",
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["email"] == "test@example.com"
    assert data["name"] == "Test User"


def test_get_current_user_unauthorized(client: TestClient):
    """Teste de obtenção do usuário sem autenticação"""
    response = client.get("/api/auth/me")
    
    assert response.status_code == 401


def test_logout(client: TestClient, auth_headers: dict):
    """Teste de logout"""
    response = client.post(
        "/api/auth/logout",
        headers=auth_headers
    )
    
    assert response.status_code == 200
    assert "sucesso" in response.json()["message"]

