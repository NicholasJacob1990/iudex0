
from __future__ import annotations

from typing import Any, Dict, List


def _rrf(rank: int, k: int = 60) -> float:
    return 1.0 / (k + rank)


class RetrievalOrchestrator:
    def merge_results(
        self,
        lexical: List[Dict[str, Any]],
        vector: List[Dict[str, Any]],
        top_k: int = 10,
        k_rrf: int = 60,
        w_lex: float = 0.5,
        w_vec: float = 0.5,
    ) -> List[Dict[str, Any]]:
        merged: Dict[str, Dict[str, Any]] = {}

        lex_rank = {r["chunk_uid"]: i + 1 for i, r in enumerate(lexical)}
        vec_rank = {r["chunk_uid"]: i + 1 for i, r in enumerate(vector)}

        # union keys
        all_uids = set(lex_rank.keys()) | set(vec_rank.keys())

        for uid in all_uids:
            # pick representative text/metadata
            rep = None
            for r in lexical:
                if r["chunk_uid"] == uid:
                    rep = r
                    break
            if not rep:
                for r in vector:
                    if r["chunk_uid"] == uid:
                        rep = r
                        break
            rep = rep or {"text": "", "metadata": {}}

            item = {
                "chunk_uid": uid,
                "text": rep.get("text", ""),
                "metadata": rep.get("metadata", {}) or {},
                "sources": [],
            }
            if uid in lex_rank:
                item["sources"].append("lexical")
            if uid in vec_rank:
                item["sources"].append("vector")

            score = 0.0
            if uid in lex_rank:
                score += w_lex * _rrf(lex_rank[uid], k_rrf)
            if uid in vec_rank:
                score += w_vec * _rrf(vec_rank[uid], k_rrf)
            item["final_score"] = score
            merged[uid] = item

        out = sorted(merged.values(), key=lambda x: x["final_score"], reverse=True)
        return out[:top_k]
