"""
Configurações e fixtures para testes
"""

import pytest
import pytest_asyncio
import asyncio
from typing import Generator, AsyncGenerator
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.database import Base, get_db
from app.models.user import User, UserRole, UserPlan, AccountType
from app.core.security import get_password_hash


# URL do banco de teste (SQLite em memória compartilhada)
TEST_DATABASE_URL = "sqlite+aiosqlite:///file::memory:?cache=shared"


@pytest_asyncio.fixture(scope="session")
def event_loop() -> Generator:
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db_engine():
    """Create test database engine"""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False, "uri": True},
        poolclass=StaticPool,
    )
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create test database session"""
    async_session = async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    async with async_session() as session:
        yield session


@pytest.fixture(scope="function")
def client(db_session: AsyncSession) -> TestClient:
    """Create test client with database dependency override"""
    
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    with TestClient(app) as test_client:
        yield test_client
    
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create test user"""
    user = User(
        id="test-user-123",
        email="test@example.com",
        hashed_password=get_password_hash("Test@123"),
        name="Test User",
        role=UserRole.USER,
        plan=UserPlan.FREE,
        account_type=AccountType.INDIVIDUAL,
        oab="123456",
        oab_state="SP",
        is_active=True,
        is_verified=True,
    )
    
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    
    return user


@pytest_asyncio.fixture
async def test_admin_user(db_session: AsyncSession) -> User:
    """Create test admin user"""
    user = User(
        id="test-admin-123",
        email="admin@example.com",
        hashed_password=get_password_hash("Admin@123"),
        name="Admin User",
        role=UserRole.ADMIN,
        plan=UserPlan.ENTERPRISE,
        account_type=AccountType.INSTITUTIONAL,
        institution_name="Test Law Firm",
        cnpj="12345678000190",
        is_active=True,
        is_verified=True,
    )
    
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    
    return user


@pytest.fixture
def auth_headers(client: TestClient, test_user: User) -> dict:
    """Get authentication headers for test user"""
    response = client.post(
        "/api/auth/login",
        json={
            "email": "test@example.com",
            "password": "Test@123"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    token = data["access_token"]
    
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_auth_headers(client: TestClient, test_admin_user: User) -> dict:
    """Get authentication headers for admin user"""
    response = client.post(
        "/api/auth/login",
        json={
            "email": "admin@example.com",
            "password": "Admin@123"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    token = data["access_token"]
    
    return {"Authorization": f"Bearer {token}"}
