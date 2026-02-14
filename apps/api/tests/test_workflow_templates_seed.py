import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.workflow import Workflow
from app.scripts import seed_workflow_templates as seeder
from app.services.ai.workflow_compiler import LANGGRAPH_AVAILABLE, WorkflowCompiler, validate_graph


@pytest.mark.asyncio
async def test_seed_workflow_templates_inserts_all(
    db_engine,
    db_session: AsyncSession,
    test_admin_user,
    monkeypatch,
):
    # seed_workflow_templates.py uses AsyncSessionLocal (global settings DB). Patch it
    # to point to the per-test engine so we don't touch any local dev DB.
    test_sessionmaker = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    monkeypatch.setattr(seeder, "AsyncSessionLocal", test_sessionmaker)

    result = await seeder.seed(seed_user_id=str(test_admin_user.id))
    assert result["inserted"] == result["total"]
    assert result["skipped"] == 0
    assert result["total"] == len(seeder.TEMPLATES)

    # Ensure templates exist and have the expected flags.
    count_stmt = (
        select(func.count())
        .select_from(Workflow)
        .where(
            Workflow.is_template.is_(True),
            Workflow.is_active.is_(True),
            Workflow.status == "published",
        )
    )
    count = (await db_session.execute(count_stmt)).scalar_one()
    assert count == result["total"]


@pytest.mark.asyncio
async def test_seed_workflow_templates_is_idempotent(db_engine, test_admin_user, monkeypatch):
    test_sessionmaker = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    monkeypatch.setattr(seeder, "AsyncSessionLocal", test_sessionmaker)

    first = await seeder.seed(seed_user_id=str(test_admin_user.id))
    second = await seeder.seed(seed_user_id=str(test_admin_user.id))

    assert first["total"] == len(seeder.TEMPLATES)
    assert second["total"] == first["total"]
    assert second["inserted"] == 0
    assert second["skipped"] == second["total"]


@pytest.mark.asyncio
async def test_seeded_templates_have_valid_graph_json(
    db_engine,
    db_session: AsyncSession,
    test_admin_user,
    monkeypatch,
):
    test_sessionmaker = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    monkeypatch.setattr(seeder, "AsyncSessionLocal", test_sessionmaker)

    await seeder.seed(seed_user_id=str(test_admin_user.id))

    stmt = select(Workflow).where(Workflow.is_template.is_(True))
    workflows = (await db_session.execute(stmt)).scalars().all()
    assert workflows, "Expected seeded workflow templates to exist"

    for wf in workflows:
        errors = validate_graph(wf.graph_json)
        assert not errors, f"Template '{wf.name}' has invalid graph: {errors}"


@pytest.mark.asyncio
async def test_seeded_templates_compile_with_langgraph(
    db_engine,
    db_session: AsyncSession,
    test_admin_user,
    monkeypatch,
):
    if not LANGGRAPH_AVAILABLE:
        pytest.skip("langgraph not available in environment")

    test_sessionmaker = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    monkeypatch.setattr(seeder, "AsyncSessionLocal", test_sessionmaker)

    await seeder.seed(seed_user_id=str(test_admin_user.id))

    stmt = select(Workflow).where(Workflow.is_template.is_(True))
    workflows = (await db_session.execute(stmt)).scalars().all()
    assert workflows, "Expected seeded workflow templates to exist"

    compiler = WorkflowCompiler()
    for wf in workflows:
        try:
            _ = compiler.compile(wf.graph_json)
        except Exception as exc:
            raise AssertionError(
                f"Template '{wf.name}' failed to compile with LangGraph: {type(exc).__name__}: {exc}"
            ) from exc
