def test_graph_risk_schemas_importable():
    from app.schemas.graph_risk import RiskScanRequest, AuditEdgeRequest

    _ = RiskScanRequest()
    _ = AuditEdgeRequest(source_id="a", target_id="b")


def test_graph_risk_service_importable():
    from app.services.graph_risk_service import GraphRiskService

    _ = GraphRiskService()

