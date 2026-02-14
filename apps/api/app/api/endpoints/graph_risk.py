"""
Graph Risk API — Fraudes e Auditorias (GraphRAG).

Endpoints:
- POST /graph/risk/scan
- GET  /graph/risk/reports
- GET  /graph/risk/reports/{report_id}
- DELETE /graph/risk/reports/{report_id}
- POST /graph/risk/audit/edge
- POST /graph/risk/audit/chain
"""

from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_org_context, OrgContext
from app.schemas.graph_risk import (
    AuditChainRequest,
    AuditChainResponse,
    AuditEdgeRequest,
    AuditEdgeResponse,
    GraphRiskReportDetail,
    GraphRiskReportListItem,
    RiskScanRequest,
    RiskScanResponse,
)
from app.services.graph_risk_service import get_graph_risk_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/risk/scan", response_model=RiskScanResponse)
async def scan_graph_risk(
    request: RiskScanRequest,
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    service = get_graph_risk_service()
    tenant_id = str(ctx.tenant_id)
    user_id = str(ctx.user.id)
    return await service.scan(tenant_id=tenant_id, user_id=user_id, db=db, request=request)


@router.get("/risk/reports", response_model=List[GraphRiskReportListItem])
async def list_graph_risk_reports(
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
):
    service = get_graph_risk_service()
    tenant_id = str(ctx.tenant_id)
    user_id = str(ctx.user.id)
    rows = await service.list_reports(tenant_id=tenant_id, user_id=user_id, db=db, limit=limit)
    out: List[GraphRiskReportListItem] = []
    for r in rows:
        payload = r.signals or {}
        signals = payload.get("signals") if isinstance(payload, dict) else None
        out.append(
            GraphRiskReportListItem(
                id=r.id,
                created_at=r.created_at.isoformat(),
                expires_at=r.expires_at.isoformat(),
                status=r.status,
                signal_count=len(signals) if isinstance(signals, list) else 0,
                params=r.params or {},
            )
        )
    return out


@router.get("/risk/reports/{report_id}", response_model=GraphRiskReportDetail)
async def get_graph_risk_report(
    report_id: str,
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    service = get_graph_risk_service()
    tenant_id = str(ctx.tenant_id)
    user_id = str(ctx.user.id)
    report = await service.get_report(tenant_id=tenant_id, user_id=user_id, db=db, report_id=report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    payload = report.signals or {}
    signals = payload.get("signals") if isinstance(payload, dict) else []
    return GraphRiskReportDetail(
        id=report.id,
        created_at=report.created_at.isoformat(),
        expires_at=report.expires_at.isoformat(),
        status=report.status,
        params=report.params or {},
        signals=signals or [],
        error=report.error,
    )


@router.delete("/risk/reports/{report_id}")
async def delete_graph_risk_report(
    report_id: str,
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    service = get_graph_risk_service()
    tenant_id = str(ctx.tenant_id)
    user_id = str(ctx.user.id)
    ok = await service.delete_report(tenant_id=tenant_id, user_id=user_id, db=db, report_id=report_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Report not found")
    return {"success": True}


@router.post("/risk/audit/edge", response_model=AuditEdgeResponse)
async def audit_graph_edge(
    request: AuditEdgeRequest,
    ctx: OrgContext = Depends(get_org_context),
):
    service = get_graph_risk_service()
    tenant_id = str(ctx.tenant_id)
    return await service.audit_edge(tenant_id=tenant_id, request=request)


@router.post("/risk/audit/chain", response_model=AuditChainResponse)
async def audit_graph_chain(
    request: AuditChainRequest,
    ctx: OrgContext = Depends(get_org_context),
):
    service = get_graph_risk_service()
    tenant_id = str(ctx.tenant_id)
    return await service.audit_chain(tenant_id=tenant_id, request=request)

