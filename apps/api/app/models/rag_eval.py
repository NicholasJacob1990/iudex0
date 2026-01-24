from datetime import datetime
import uuid

from sqlalchemy import Column, DateTime, Float, String, JSON

from app.core.database import Base


class RAGEvalMetric(Base):
    __tablename__ = "rag_eval_metrics"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    dataset = Column(String, nullable=False)
    context_precision = Column(Float)
    context_recall = Column(Float)
    faithfulness = Column(Float)
    answer_relevancy = Column(Float)
    metrics = Column(JSON, nullable=False, default=dict)
