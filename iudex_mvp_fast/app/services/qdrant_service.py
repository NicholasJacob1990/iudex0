
from __future__ import annotations

from typing import Any, Dict, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm


class QdrantService:
    def __init__(self, url: str):
        self.client = QdrantClient(url=url)

    def ensure_collection(self, name: str, vector_size: int) -> None:
        if self.client.collection_exists(name):
            return
        self.client.create_collection(
            collection_name=name,
            vectors_config=qm.VectorParams(size=vector_size, distance=qm.Distance.COSINE),
        )

    def upsert(self, collection: str, point_id: str, vector: List[float], payload: Dict[str, Any]) -> None:
        self.client.upsert(collection_name=collection, points=[qm.PointStruct(id=point_id, vector=vector, payload=payload)])

    def search(self, collection: str, vector: List[float], query_filter: Optional[qm.Filter], limit: int) -> List[Dict[str, Any]]:
        res = self.client.query_points(
            collection_name=collection,
            query=vector,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        out = []
        for p in res.points:
            payload = p.payload or {}
            out.append(
                {
                    "chunk_uid": payload.get("chunk_uid") or str(p.id),
                    "score": float(p.score or 0.0),
                    "text": payload.get("text", ""),
                    "metadata": {k: v for k, v in payload.items() if k != "text"},
                    "engine": "qdrant",
                }
            )
        return out

    @staticmethod
    def build_filter(
        *,
        tenant_id: str,
        group_ids: Optional[List[str]],
        include_global: bool,
        include_private: bool,
        include_group: bool,
        include_local: bool,
        case_id: Optional[str],
        user_id: Optional[str],
    ) -> qm.Filter:
        should: List[qm.Condition] = []

        if include_global:
            should.append(qm.FieldCondition(key="scope", match=qm.MatchValue(value="global")))

        if include_private:
            should.append(
                qm.Filter(
                    must=[
                        qm.FieldCondition(key="scope", match=qm.MatchValue(value="private")),
                        qm.FieldCondition(key="tenant_id", match=qm.MatchValue(value=tenant_id)),
                    ]
                )
            )

        if include_group and group_ids:
            should.append(
                qm.Filter(
                    must=[
                        qm.FieldCondition(key="scope", match=qm.MatchValue(value="group")),
                        qm.FieldCondition(key="group_ids", match=qm.MatchAny(any=group_ids)),
                    ]
                )
            )

        if include_local and case_id:
            should.append(
                qm.Filter(
                    must=[
                        qm.FieldCondition(key="scope", match=qm.MatchValue(value="local")),
                        qm.FieldCondition(key="tenant_id", match=qm.MatchValue(value=tenant_id)),
                        qm.FieldCondition(key="case_id", match=qm.MatchValue(value=case_id)),
                    ]
                )
            )

        base = qm.Filter(should=should, min_should=1)

        if user_id:
            sigilo = qm.Filter(
                should=[
                    qm.FieldCondition(key="sigilo", match=qm.MatchValue(value="publico")),
                    qm.FieldCondition(key="allowed_users", match=qm.MatchAny(any=[user_id])),
                ],
                min_should=1,
            )
        else:
            sigilo = qm.Filter(must=[qm.FieldCondition(key="sigilo", match=qm.MatchValue(value="publico"))])

        return qm.Filter(must=[base, sigilo])

    def delete_local_older_than(self, collection: str, cutoff_epoch: int) -> None:
        flt = qm.Filter(
            must=[
                qm.FieldCondition(key="scope", match=qm.MatchValue(value="local")),
                qm.FieldCondition(key="uploaded_at", range=qm.Range(lt=cutoff_epoch)),
            ]
        )
        self.client.delete(collection_name=collection, points_selector=qm.FilterSelector(filter=flt), wait=True)
