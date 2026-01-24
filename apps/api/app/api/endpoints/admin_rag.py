"""
Admin endpoints para políticas de acesso ao RAG e dashboard simples.
"""

from typing import List, Optional, Tuple
import html as html_lib
import json
import os
import glob
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User, UserRole
from app.models.rag_policy import RAGAccessPolicy
from app.models.rag_ingestion import RAGIngestionEvent
from app.services.rag_policy import upsert_rag_policy
from app.services.rag_module import create_rag_manager


router = APIRouter()


def _require_admin(user: User) -> None:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Acesso restrito ao administrador.")


class RAGPolicyPayload(BaseModel):
    tenant_id: str = Field(..., min_length=1)
    user_id: Optional[str] = None
    allow_global: bool = False
    allow_groups: bool = False
    group_ids: List[str] = Field(default_factory=list)


class RAGPolicyResponse(BaseModel):
    id: str
    tenant_id: str
    user_id: Optional[str]
    allow_global: bool
    allow_groups: bool
    group_ids: List[str]


def _escape(value: Optional[str]) -> str:
    return html_lib.escape(str(value or ""))


def _parse_collection_name(name: str) -> Tuple[str, str, str]:
    if name.startswith("global__"):
        return "global", "-", name.split("__", 1)[1]
    if name.startswith("group_") and "__" in name:
        prefix, source = name.split("__", 1)
        scope_id = prefix.replace("group_", "", 1)
        return "group", scope_id, source
    if name.startswith("tenant_") and "__" in name:
        prefix, source = name.split("__", 1)
        scope_id = prefix.replace("tenant_", "", 1)
        return "private", scope_id, source
    return "private", "-", name


def _render_ingestion_chart(day_counts: List[Tuple[str, int]]) -> str:
    if not day_counts:
        return "<p>Sem dados de ingestão para o período.</p>"

    width = 720
    height = 200
    padding = 28
    gap = 6
    max_count = max((count for _, count in day_counts), default=1) or 1
    n = len(day_counts)
    bar_width = max(4.0, (width - 2 * padding - gap * (n - 1)) / max(n, 1))

    bars = []
    labels = []
    for idx, (day, count) in enumerate(day_counts):
        x = padding + idx * (bar_width + gap)
        bar_height = int((height - 2 * padding) * (count / max_count))
        y = height - padding - bar_height
        label = day[5:] if len(day) >= 7 else day
        bars.append(
            f'<rect x="{x:.1f}" y="{y}" width="{bar_width:.1f}" height="{bar_height}" '
            f'fill="#4c7cf3"><title>{day}: {count}</title></rect>'
        )
        labels.append(
            f'<text x="{x + bar_width / 2:.1f}" y="{height - 8}" text-anchor="middle" '
            f'font-size="10" fill="#555">{label}</text>'
        )

    axis = (
        f'<line x1="{padding}" y1="{height - padding}" x2="{width - padding}" '
        f'y2="{height - padding}" stroke="#999" stroke-width="1" />'
    )
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        f"{axis}{''.join(bars)}{''.join(labels)}"
        "</svg>"
    )


@router.get("/admin/rag", response_class=HTMLResponse)
async def admin_rag_dashboard(
    scope: Optional[str] = None,
    tenant_id: Optional[str] = None,
    group_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    scope_filter = scope or ""
    result = await db.execute(select(RAGAccessPolicy))
    policies = result.scalars().all()
    if tenant_id:
        policies = [p for p in policies if p.tenant_id == tenant_id]

    policy_rows = []
    for policy in policies:
        policy_rows.append(
            "<tr>"
            f"<td>{_escape(policy.tenant_id)}</td>"
            f"<td>{_escape(policy.user_id) or '-'}</td>"
            f"<td>{'sim' if policy.allow_global else 'nao'}</td>"
            f"<td>{'sim' if policy.allow_groups else 'nao'}</td>"
            f"<td>{_escape(', '.join(policy.group_ids or []))}</td>"
            f"<td>{_escape(policy.id)}</td>"
            "</tr>"
        )
    policy_table = "\n".join(policy_rows) if policy_rows else "<tr><td colspan='6'>Sem políticas cadastradas.</td></tr>"

    ingestion_limit = int(os.getenv("RAG_ADMIN_INGESTION_LIMIT", "2000"))
    ingestion_chart_days = int(os.getenv("RAG_ADMIN_INGESTION_DAYS", "14"))
    ingestion_chart_limit = int(os.getenv("RAG_ADMIN_INGESTION_CHART_LIMIT", "10000"))
    ingestion_latest = {}
    ingestion_filters = []
    if scope_filter:
        ingestion_filters.append(RAGIngestionEvent.scope == scope_filter)
    if tenant_id:
        ingestion_filters.append(RAGIngestionEvent.tenant_id == tenant_id)
    if group_id:
        ingestion_filters.append(RAGIngestionEvent.group_id == group_id)
    try:
        stmt = select(RAGIngestionEvent)
        if ingestion_filters:
            stmt = stmt.where(and_(*ingestion_filters))
        stmt = stmt.order_by(RAGIngestionEvent.created_at.desc()).limit(ingestion_limit)
        result = await db.execute(stmt)
        ingestion_events = result.scalars().all()
        for event in ingestion_events:
            if event.collection not in ingestion_latest:
                ingestion_latest[event.collection] = event
    except Exception:
        ingestion_latest = {}

    day_counts: List[Tuple[str, int]] = []
    try:
        start_dt = datetime.utcnow() - timedelta(days=ingestion_chart_days - 1)
        stmt = select(RAGIngestionEvent.created_at)
        if ingestion_filters:
            stmt = stmt.where(and_(*ingestion_filters))
        stmt = stmt.where(RAGIngestionEvent.created_at >= start_dt)
        stmt = stmt.order_by(RAGIngestionEvent.created_at.desc()).limit(ingestion_chart_limit)
        result = await db.execute(stmt)
        events = result.scalars().all()
        counts = {}
        for created_at in events:
            day_key = created_at.date().isoformat()
            counts[day_key] = counts.get(day_key, 0) + 1
        day_list = [
            (start_dt.date() + timedelta(days=idx)).isoformat()
            for idx in range(ingestion_chart_days)
        ]
        day_counts = [(day, counts.get(day, 0)) for day in day_list]
    except Exception:
        day_counts = []

    collection_rows = []
    graph_rows = []
    try:
        rag_manager = create_rag_manager()
        collections = []
        try:
            for item in rag_manager.client.list_collections():
                name = getattr(item, "name", None) or item.get("name")
                if name:
                    collections.append(name)
        except Exception:
            collections = list(rag_manager.collections.keys())

        sample_limit = int(os.getenv("RAG_ADMIN_COLLECTION_SAMPLE", "50"))
        for name in sorted(set(collections)):
            collection = rag_manager._get_collection(name)
            try:
                count = collection.count()
            except Exception:
                count = "?"

            last_ingested = ""
            status_label = "-"
            status_detail = "-"
            event = ingestion_latest.get(name)
            if event:
                last_ingested = event.created_at.isoformat() if event.created_at else ""
                status_label = event.status or "-"
                chunk_count = event.chunk_count or 0
                skipped_count = event.skipped_count or 0
                status_detail = f"{chunk_count} chunks; {skipped_count} duplicados"
                if event.error:
                    trimmed_error = str(event.error)
                    if len(trimmed_error) > 160:
                        trimmed_error = trimmed_error[:157] + "..."
                    status_detail = f"{status_detail}; erro: {trimmed_error}"
            else:
                try:
                    result = collection.get(include=["metadatas"], limit=sample_limit)
                    metadatas = result.get("metadatas") or []
                    if metadatas:
                        ingested_values = [
                            m.get("ingested_at")
                            for m in metadatas
                            if isinstance(m, dict) and m.get("ingested_at")
                        ]
                        if ingested_values:
                            last_ingested = max(ingested_values)
                except Exception:
                    last_ingested = ""

            col_scope, scope_id, source = _parse_collection_name(name)
            if scope_filter and col_scope != scope_filter:
                continue
            if tenant_id and col_scope == "private" and scope_id != tenant_id:
                continue
            if group_id and col_scope == "group" and scope_id != group_id:
                continue
            collection_rows.append(
                "<tr>"
                f"<td>{_escape(col_scope)}</td>"
                f"<td>{_escape(scope_id)}</td>"
                f"<td>{_escape(source)}</td>"
                f"<td>{_escape(name)}</td>"
                f"<td>{_escape(count)}</td>"
                f"<td>{_escape(last_ingested) or '-'}</td>"
                f"<td>{_escape(status_label)}</td>"
                f"<td>{_escape(status_detail)}</td>"
                "</tr>"
            )
    except Exception:
        collection_rows.append("<tr><td colspan='8'>Erro ao carregar coleções.</td></tr>")

    try:
        base_dir = os.path.dirname(os.path.dirname(__file__))
        graph_root = os.path.join(base_dir, "services", "graph_db")
        legacy_path = os.path.join(graph_root, "legal_knowledge_graph.json")
        graph_files = []
        if os.path.exists(legacy_path):
            graph_files.append(legacy_path)
        graph_files.extend(glob.glob(os.path.join(graph_root, "scopes", "knowledge_graph_*.json")))
        for path in sorted(set(graph_files)):
            key = os.path.basename(path).replace("knowledge_graph_", "").replace(".json", "")
            graph_scope = "private"
            scope_id = "-"
            if key == "global":
                graph_scope = "global"
            elif key.startswith("group_"):
                graph_scope = "group"
                scope_id = key.replace("group_", "", 1) or "-"
            elif key.startswith("private_"):
                graph_scope = "private"
                scope_id = key.replace("private_", "", 1) or "-"
            if scope_filter and graph_scope != scope_filter:
                continue
            if tenant_id and graph_scope == "private" and scope_id != tenant_id:
                continue
            if group_id and graph_scope == "group" and scope_id != group_id:
                continue
            data = {}
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
            meta = data.get("metadata", {}) if isinstance(data, dict) else {}
            node_count = meta.get("node_count") or len(data.get("nodes", []))
            edge_count = meta.get("edge_count") or len(data.get("edges", []))
            saved_at = meta.get("saved_at") or ""
            graph_rows.append(
                "<tr>"
                f"<td>{_escape(graph_scope)}</td>"
                f"<td>{_escape(scope_id)}</td>"
                f"<td>{_escape(os.path.basename(path))}</td>"
                f"<td>{_escape(node_count)}</td>"
                f"<td>{_escape(edge_count)}</td>"
                f"<td>{_escape(saved_at) or '-'}</td>"
                "</tr>"
            )
    except Exception:
        graph_rows.append("<tr><td colspan='6'>Erro ao carregar grafos.</td></tr>")

    html = """
    <!doctype html>
    <html>
      <head>
        <meta charset="utf-8" />
        <title>RAG Admin</title>
        <style>
          body { font-family: Arial, sans-serif; margin: 24px; color: #222; }
          h1 { margin-bottom: 8px; }
          .card { border: 1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 16px; }
          .filters { display: flex; gap: 12px; flex-wrap: wrap; align-items: flex-end; }
          .filters label { margin-top: 0; min-width: 160px; }
          .filters input, .filters select { width: 100%; }
          table { border-collapse: collapse; width: 100%; }
          th, td { border: 1px solid #e0e0e0; padding: 8px; text-align: left; font-size: 13px; }
          th { background: #f5f5f5; }
          label { display: block; margin-top: 8px; }
          input, textarea { width: 100%; padding: 8px; margin-top: 4px; }
          button { margin-top: 12px; padding: 8px 12px; }
          code { background: #f3f3f3; padding: 2px 4px; border-radius: 4px; }
        </style>
      </head>
      <body>
        <h1>RAG Admin</h1>
        <p>Gerencie escopos <code>private/group/global</code> via políticas.</p>
        <div class="card">
          <h2>Filtros</h2>
          <form method="get" action="/api/admin/rag">
            <div class="filters">
              <label>Escopo
                <select name="scope">
                  <option value="">Todos</option>
                  <option value="private" {{SCOPE_PRIVATE}}>private</option>
                  <option value="group" {{SCOPE_GROUP}}>group</option>
                  <option value="global" {{SCOPE_GLOBAL}}>global</option>
                </select>
              </label>
              <label>Tenant ID
                <input name="tenant_id" value="{{TENANT_FILTER}}" />
              </label>
              <label>Group ID
                <input name="group_id" value="{{GROUP_FILTER}}" />
              </label>
              <button type="submit">Aplicar</button>
              <a href="/api/admin/rag">Limpar</a>
            </div>
          </form>
        </div>
        <div class="card">
          <h2>Criar/Atualizar Política</h2>
          <form method="post" action="/api/admin/rag/policies/form">
            <label>Tenant ID
              <input name="tenant_id" required />
            </label>
            <label>User ID (opcional)
              <input name="user_id" />
            </label>
            <label>Allow Global
              <input name="allow_global" type="checkbox" />
            </label>
            <label>Allow Groups
              <input name="allow_groups" type="checkbox" />
            </label>
            <label>Group IDs (separados por vírgula)
              <textarea name="group_ids" rows="2"></textarea>
            </label>
            <button type="submit">Salvar</button>
          </form>
        </div>
        <div class="card">
          <h2>Políticas</h2>
          <table>
            <thead>
              <tr>
                <th>Tenant</th>
                <th>User</th>
                <th>Global</th>
                <th>Groups</th>
                <th>Group IDs</th>
                <th>Policy ID</th>
              </tr>
            </thead>
            <tbody>
              {{POLICY_ROWS}}
            </tbody>
          </table>
        </div>
        <div class="card">
          <h2>Ingestões por dia</h2>
          {{INGESTION_CHART}}
        </div>
        <div class="card">
          <h2>Coleções por escopo</h2>
          <table>
            <thead>
              <tr>
                <th>Escopo</th>
                <th>Scope ID</th>
                <th>Fonte</th>
                <th>Coleção</th>
                <th>Docs</th>
                <th>Última ingestão</th>
                <th>Status</th>
                <th>Detalhes</th>
              </tr>
            </thead>
            <tbody>
              {{COLLECTION_ROWS}}
            </tbody>
          </table>
        </div>
        <div class="card">
          <h2>Gráficos por escopo</h2>
          <table>
            <thead>
              <tr>
                <th>Escopo</th>
                <th>Scope ID</th>
                <th>Arquivo</th>
                <th>Nós</th>
                <th>Arestas</th>
                <th>Atualizado</th>
              </tr>
            </thead>
            <tbody>
              {{GRAPH_ROWS}}
            </tbody>
          </table>
        </div>
      </body>
    </html>
    """
    html = html.replace("{{POLICY_ROWS}}", policy_table)
    html = html.replace("{{COLLECTION_ROWS}}", "\n".join(collection_rows))
    html = html.replace("{{GRAPH_ROWS}}", "\n".join(graph_rows))
    html = html.replace("{{INGESTION_CHART}}", _render_ingestion_chart(day_counts))
    html = html.replace("{{TENANT_FILTER}}", _escape(tenant_id) if tenant_id else "")
    html = html.replace("{{GROUP_FILTER}}", _escape(group_id) if group_id else "")
    html = html.replace("{{SCOPE_PRIVATE}}", "selected" if scope_filter == "private" else "")
    html = html.replace("{{SCOPE_GROUP}}", "selected" if scope_filter == "group" else "")
    html = html.replace("{{SCOPE_GLOBAL}}", "selected" if scope_filter == "global" else "")
    return HTMLResponse(content=html)


@router.get("/admin/rag/policies", response_model=List[RAGPolicyResponse])
async def list_rag_policies(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    result = await db.execute(select(RAGAccessPolicy))
    policies = result.scalars().all()
    return [
        RAGPolicyResponse(
            id=p.id,
            tenant_id=p.tenant_id,
            user_id=p.user_id,
            allow_global=p.allow_global,
            allow_groups=p.allow_groups,
            group_ids=p.group_ids or [],
        )
        for p in policies
    ]


@router.post("/admin/rag/policies", response_model=RAGPolicyResponse)
async def upsert_rag_policy_endpoint(
    payload: RAGPolicyPayload,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    policy = await upsert_rag_policy(
        db,
        tenant_id=payload.tenant_id,
        user_id=payload.user_id,
        allow_global=payload.allow_global,
        allow_groups=payload.allow_groups,
        group_ids=[g.strip() for g in payload.group_ids if g.strip()],
    )
    return RAGPolicyResponse(
        id=policy.id,
        tenant_id=policy.tenant_id,
        user_id=policy.user_id,
        allow_global=policy.allow_global,
        allow_groups=policy.allow_groups,
        group_ids=policy.group_ids or [],
    )


@router.post("/admin/rag/policies/form", response_model=RAGPolicyResponse)
async def upsert_rag_policy_form(
    tenant_id: str = Form(...),
    user_id: Optional[str] = Form(None),
    allow_global: Optional[bool] = Form(False),
    allow_groups: Optional[bool] = Form(False),
    group_ids: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    groups = [g.strip() for g in (group_ids or "").split(",") if g.strip()]
    policy = await upsert_rag_policy(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        allow_global=bool(allow_global),
        allow_groups=bool(allow_groups),
        group_ids=groups,
    )
    return RAGPolicyResponse(
        id=policy.id,
        tenant_id=policy.tenant_id,
        user_id=policy.user_id,
        allow_global=policy.allow_global,
        allow_groups=policy.allow_groups,
        group_ids=policy.group_ids or [],
    )


@router.delete("/admin/rag/policies/{policy_id}")
async def delete_rag_policy(
    policy_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    result = await db.execute(select(RAGAccessPolicy).where(RAGAccessPolicy.id == policy_id))
    policy = result.scalars().first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    await db.delete(policy)
    await db.commit()
    return {"status": "ok"}
