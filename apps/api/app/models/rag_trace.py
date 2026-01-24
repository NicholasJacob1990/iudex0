from datetime import datetime
import uuid

from sqlalchemy import Column, DateTime, String, JSON

from app.core.database import Base


class RAGTraceEvent(Base):
    __tablename__ = "rag_trace_events"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    request_id = Column(String, index=True, nullable=False)
    event = Column(String, nullable=False)
    user_id = Column(String, index=True)
    tenant_id = Column(String, index=True)
    conversation_id = Column(String, index=True)
    message_id = Column(String, index=True)
    payload = Column(JSON, nullable=False, default=dict)
