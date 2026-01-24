from datetime import datetime
import uuid

from sqlalchemy import Column, DateTime, Integer, String, JSON

from app.core.database import Base


class RAGIngestionEvent(Base):
    __tablename__ = "rag_ingestion_events"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    scope = Column(String, index=True, nullable=False)
    scope_id = Column(String, index=True)
    tenant_id = Column(String, index=True)
    group_id = Column(String, index=True)
    collection = Column(String, index=True, nullable=False)
    source_type = Column(String, index=True, nullable=False)
    doc_hash = Column(String, index=True)
    doc_version = Column(Integer)
    chunk_count = Column(Integer)
    skipped_count = Column(Integer)
    status = Column(String, index=True, nullable=False)
    error = Column(String)
    metadata_json = Column("metadata", JSON, nullable=False, default=dict)
