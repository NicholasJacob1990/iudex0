
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional

from opensearchpy import OpenSearch


class OpenSearchService:
    def __init__(self, url: str, username: str, password: str):
        self.client = OpenSearch(
            hosts=[url],
            http_auth=(username, password),
            use_ssl=url.startswith("https"),
            verify_certs=False,   # demo certs for local dev
            ssl_show_warn=False,
        )

    def ensure_index(self, index: str) -> None:
        if self.client.indices.exists(index=index):
            return
        body = {
            "settings": {"index": {"number_of_shards": 1, "number_of_replicas": 0}},
            "mappings": {
                "properties": {
                    "chunk_uid": {"type": "keyword"},
                    "dataset": {"type": "keyword"},
                    "scope": {"type": "keyword"},
                    "tenant_id": {"type": "keyword"},
                    "case_id": {"type": "keyword"},
                    "group_ids": {"type": "keyword"},
                    "allowed_users": {"type": "keyword"},
                    "sigilo": {"type": "keyword"},
                    "doc_id": {"type": "keyword"},
                    "doc_hash": {"type": "keyword"},
                    "doc_version": {"type": "keyword"},
                    "chunk_index": {"type": "integer"},
                    "page": {"type": "integer"},
                    "uploaded_at": {"type": "date"},
                    "text": {"type": "text"},
                }
            },
        }
        self.client.indices.create(index=index, body=body)

    def index_chunk(self, index: str, doc_id: str, doc: Dict[str, Any]) -> None:
        self.client.index(index=index, id=doc_id, body=doc, refresh=False)

    def refresh(self, index: str) -> None:
        self.client.indices.refresh(index=index)

    def search_lexical(self, indices: List[str], query: str, filter_query: Dict[str, Any], size: int) -> List[Dict[str, Any]]:
        body = {
            "size": size,
            "_source": True,
            "query": {"bool": {"must": [{"match": {"text": {"query": query}}}], "filter": [filter_query]}},
        }
        resp = self.client.search(index=",".join(indices), body=body)
        hits = resp.get("hits", {}).get("hits", [])
        out = []
        for h in hits:
            src = h.get("_source", {}) or {}
            out.append(
                {
                    "chunk_uid": src.get("chunk_uid") or h.get("_id"),
                    "score": float(h.get("_score") or 0.0),
                    "text": src.get("text", ""),
                    "metadata": {k: v for k, v in src.items() if k != "text"},
                    "engine": "opensearch",
                }
            )
        return out

    def delete_local_older_than(self, index: str, cutoff: dt.datetime) -> None:
        body = {"query": {"range": {"uploaded_at": {"lt": cutoff.isoformat()}}}}
        self.client.delete_by_query(index=index, body=body, conflicts="proceed", refresh=True)

    @staticmethod
    def build_scope_filter(
        *,
        tenant_id: str,
        group_ids: Optional[List[str]],
        include_global: bool,
        include_private: bool,
        include_group: bool,
        include_local: bool,
        case_id: Optional[str],
        user_id: Optional[str],
    ) -> Dict[str, Any]:
        should = []

        if include_global:
            should.append({"term": {"scope": "global"}})

        if include_private:
            should.append({"bool": {"must": [{"term": {"scope": "private"}}, {"term": {"tenant_id": tenant_id}}]}})

        if include_group and group_ids:
            should.append({"bool": {"must": [{"term": {"scope": "group"}}, {"terms": {"group_ids": group_ids}}]}})

        if include_local and case_id:
            should.append(
                {
                    "bool": {
                        "must": [
                            {"term": {"scope": "local"}},
                            {"term": {"tenant_id": tenant_id}},
                            {"term": {"case_id": case_id}},
                        ]
                    }
                }
            )

        base = {"bool": {"should": should, "minimum_should_match": 1}}

        # MVP sigilo policy:
        # If user_id given: allow public OR allowed_users contains user_id.
        # Else: only public.
        if user_id:
            sigilo_filter = {
                "bool": {
                    "should": [{"term": {"sigilo": "publico"}}, {"terms": {"allowed_users": [user_id]}}],
                    "minimum_should_match": 1,
                }
            }
        else:
            sigilo_filter = {"term": {"sigilo": "publico"}}

        return {"bool": {"must": [base, sigilo_filter]}}
