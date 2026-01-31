"""
ArgumentNeo4j — ArgumentRAG backed by Neo4j.

Migrates the argument graph (Claims, Evidence, Actors, Issues) from
the legacy NetworkX/JSON backend to Neo4j, enabling:
- Unified graph for enrichment + debate
- Multi-tenant security trimming via tenant_id/scope
- Cypher-based traversal for debate context
- Auditable paths between entities and argument structures

Usage:
    from app.services.rag.core.argument_neo4j import get_argument_neo4j

    svc = get_argument_neo4j()
    svc.ingest_arguments(doc_hash, chunks, tenant_id, case_id)
    ctx = svc.get_debate_context(query, results, tenant_id, case_id)
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# HELPERS
# =============================================================================

def _norm(s: str) -> str:
    """Normalize unicode, collapse whitespace."""
    s = unicodedata.normalize("NFKC", s)
    return re.sub(r"\s+", " ", s).strip()


def _lower(s: str) -> str:
    return _norm(s).lower()


def _clip(s: str, maxlen: int = 120) -> str:
    return s[:maxlen] + "..." if len(s) > maxlen else s


def _stable_id(*parts: str) -> str:
    """Deterministic hash-based ID from parts."""
    raw = ":".join(_lower(p) for p in parts if p)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# =============================================================================
# CYPHER QUERIES
# =============================================================================

class ArgumentCypher:
    """Parameterized Cypher queries for argument graph operations."""

    # ---- Schema ----
    SCHEMA_CONSTRAINTS = (
        "CREATE CONSTRAINT arg_claim_id IF NOT EXISTS FOR (c:Claim) REQUIRE c.claim_id IS UNIQUE",
        "CREATE CONSTRAINT arg_evidence_id IF NOT EXISTS FOR (ev:Evidence) REQUIRE ev.evidence_id IS UNIQUE",
        "CREATE CONSTRAINT arg_actor_id IF NOT EXISTS FOR (a:Actor) REQUIRE a.actor_id IS UNIQUE",
        "CREATE CONSTRAINT arg_issue_id IF NOT EXISTS FOR (i:Issue) REQUIRE i.issue_id IS UNIQUE",
    )

    SCHEMA_INDEXES = (
        "CREATE INDEX arg_claim_tenant IF NOT EXISTS FOR (c:Claim) ON (c.tenant_id)",
        "CREATE INDEX arg_claim_case IF NOT EXISTS FOR (c:Claim) ON (c.case_id)",
        "CREATE INDEX arg_claim_type IF NOT EXISTS FOR (c:Claim) ON (c.claim_type)",
        "CREATE INDEX arg_evidence_tenant IF NOT EXISTS FOR (ev:Evidence) ON (ev.tenant_id)",
        "CREATE INDEX arg_evidence_doc IF NOT EXISTS FOR (ev:Evidence) ON (ev.doc_id)",
        "CREATE INDEX arg_actor_tenant IF NOT EXISTS FOR (a:Actor) ON (a.tenant_id)",
        "CREATE INDEX arg_issue_case IF NOT EXISTS FOR (i:Issue) ON (i.case_id)",
    )

    # ---- MERGE nodes ----
    MERGE_CLAIM = """
    MERGE (c:Claim {claim_id: $claim_id})
    ON CREATE SET
        c.text = $text,
        c.claim_type = $claim_type,
        c.polarity = $polarity,
        c.confidence = $confidence,
        c.source_chunk_uid = $source_chunk_uid,
        c.tenant_id = $tenant_id,
        c.case_id = $case_id,
        c.scope = $scope,
        c.created_at = datetime()
    ON MATCH SET
        c.updated_at = datetime()
    RETURN c
    """

    MERGE_EVIDENCE = """
    MERGE (ev:Evidence {evidence_id: $evidence_id})
    ON CREATE SET
        ev.text = $text,
        ev.evidence_type = $evidence_type,
        ev.weight = $weight,
        ev.doc_id = $doc_id,
        ev.chunk_id = $chunk_id,
        ev.source_chunk_uid = $source_chunk_uid,
        ev.tenant_id = $tenant_id,
        ev.scope = $scope,
        ev.title = $title,
        ev.created_at = datetime()
    ON MATCH SET
        ev.updated_at = datetime()
    RETURN ev
    """

    MERGE_ACTOR = """
    MERGE (a:Actor {actor_id: $actor_id})
    ON CREATE SET
        a.name = $name,
        a.role = $role,
        a.tenant_id = $tenant_id,
        a.created_at = datetime()
    ON MATCH SET
        a.updated_at = datetime()
    RETURN a
    """

    MERGE_ISSUE = """
    MERGE (i:Issue {issue_id: $issue_id})
    ON CREATE SET
        i.text = $text,
        i.domain = $domain,
        i.tenant_id = $tenant_id,
        i.case_id = $case_id,
        i.created_at = datetime()
    ON MATCH SET
        i.updated_at = datetime()
    RETURN i
    """

    # ---- Relationships ----
    LINK_CHUNK_CLAIM = """
    MATCH (ch:Chunk {chunk_uid: $chunk_uid})
    MATCH (c:Claim {claim_id: $claim_id})
    MERGE (ch)-[r:CONTAINS_CLAIM]->(c)
    ON CREATE SET r.created_at = datetime()
    RETURN r
    """

    LINK_EVIDENCE_CLAIM = """
    MATCH (ev:Evidence {evidence_id: $evidence_id})
    MATCH (c:Claim {claim_id: $claim_id})
    MERGE (ev)-[r:EVIDENCES]->(c)
    ON CREATE SET
        r.stance = $stance,
        r.weight = $weight,
        r.created_at = datetime()
    ON MATCH SET
        r.weight = $weight,
        r.updated_at = datetime()
    RETURN r
    """

    LINK_ACTOR_CLAIM = """
    MATCH (a:Actor {actor_id: $actor_id})
    MATCH (c:Claim {claim_id: $claim_id})
    MERGE (a)-[r:ARGUES]->(c)
    ON CREATE SET
        r.stance = $stance,
        r.created_at = datetime()
    RETURN r
    """

    LINK_CLAIM_ISSUE = """
    MATCH (c:Claim {claim_id: $claim_id})
    MATCH (i:Issue {issue_id: $issue_id})
    MERGE (c)-[r:RAISES]->(i)
    ON CREATE SET r.created_at = datetime()
    RETURN r
    """

    LINK_CLAIM_SUPPORTS = """
    MATCH (c1:Claim {claim_id: $from_claim_id})
    MATCH (c2:Claim {claim_id: $to_claim_id})
    MERGE (c1)-[r:SUPPORTS]->(c2)
    ON CREATE SET r.weight = $weight, r.created_at = datetime()
    RETURN r
    """

    LINK_CLAIM_OPPOSES = """
    MATCH (c1:Claim {claim_id: $from_claim_id})
    MATCH (c2:Claim {claim_id: $to_claim_id})
    MERGE (c1)-[r:OPPOSES]->(c2)
    ON CREATE SET r.weight = $weight, r.created_at = datetime()
    RETURN r
    """

    LINK_CLAIM_ENTITY = """
    MATCH (c:Claim {claim_id: $claim_id})
    MATCH (e:Entity {entity_id: $entity_id})
    MERGE (c)-[r:CITES]->(e)
    ON CREATE SET r.created_at = datetime()
    RETURN r
    """

    # ---- Queries ----
    FIND_DEBATE_CONTEXT = """
    // Find claims connected to evidence from the given chunk_uids
    MATCH (ev:Evidence)-[r:EVIDENCES]->(c:Claim)
    WHERE ev.doc_id IN $doc_ids
      AND c.tenant_id = $tenant_id
      AND ($case_id IS NULL OR c.case_id = $case_id)

    // Collect supporting and opposing evidence
    WITH c, collect({
        evidence_id: ev.evidence_id,
        text: ev.text,
        stance: r.stance,
        weight: r.weight,
        doc_id: ev.doc_id,
        title: ev.title
    }) AS evidence_list

    // Get actors arguing this claim
    OPTIONAL MATCH (a:Actor)-[ar:ARGUES]->(c)
    WITH c, evidence_list, collect({
        name: a.name,
        role: a.role,
        stance: ar.stance
    }) AS actors

    // Get issues raised by this claim
    OPTIONAL MATCH (c)-[:RAISES]->(i:Issue)
    WITH c, evidence_list, actors, collect(i.text) AS issues

    // Get opposing claims
    OPTIONAL MATCH (opp:Claim)-[:OPPOSES]->(c)
    WHERE opp.tenant_id = $tenant_id

    RETURN c.claim_id AS claim_id,
           c.text AS claim_text,
           c.claim_type AS claim_type,
           c.polarity AS polarity,
           c.confidence AS confidence,
           evidence_list,
           actors,
           issues,
           collect(DISTINCT {
               claim_id: opp.claim_id,
               text: opp.text
           }) AS opposing_claims
    ORDER BY size(evidence_list) DESC
    LIMIT $max_claims
    """

    FIND_ARGUMENT_GRAPH = """
    // Full argument structure for a case
    MATCH (c:Claim)
    WHERE c.tenant_id = $tenant_id
      AND ($case_id IS NULL OR c.case_id = $case_id)

    OPTIONAL MATCH (ev:Evidence)-[er:EVIDENCES]->(c)
    OPTIONAL MATCH (a:Actor)-[ar:ARGUES]->(c)
    OPTIONAL MATCH (c)-[:RAISES]->(i:Issue)
    OPTIONAL MATCH (c)-[:CITES]->(e:Entity)
    OPTIONAL MATCH (c2:Claim)-[opp:OPPOSES]->(c)

    RETURN c, ev, er, a, ar, i, e, c2, opp
    LIMIT 200
    """

    GET_STATS = """
    MATCH (c:Claim {tenant_id: $tenant_id})
    WITH count(c) AS claims
    OPTIONAL MATCH (ev:Evidence {tenant_id: $tenant_id})
    WITH claims, count(ev) AS evidence
    OPTIONAL MATCH (a:Actor {tenant_id: $tenant_id})
    WITH claims, evidence, count(a) AS actors
    OPTIONAL MATCH (i:Issue {tenant_id: $tenant_id})
    RETURN claims, evidence, actors, count(i) AS issues
    """


# =============================================================================
# CONFIG
# =============================================================================

@dataclass
class ArgumentNeo4jConfig:
    """Configuration for the ArgumentNeo4j service."""
    max_claims_per_debate: int = 5
    max_evidence_per_claim: int = 5
    max_actors_per_claim: int = 3
    max_context_chars: int = 5000
    evidence_weight_threshold: float = 0.6
    # Reuse dispute/assert cues from ArgumentPack
    dispute_cues: Tuple[str, ...] = (
        "nega", "negou", "negar", "contesta", "contestou", "impugna", "impugnou",
        "refuta", "refutou", "inveríd", "falso", "não procede", "não se sustenta",
        "não houve", "inexist", "incab", "improced", "contraria", "diverge",
        "no entanto", "todavia", "entretanto",
    )
    assert_cues: Tuple[str, ...] = (
        "afirma", "alega", "sustenta", "relata", "declara", "diz", "indica",
        "demonstra", "evidencia", "mostra", "conclui", "confirma", "aponta",
        "segundo", "de acordo com", "consta", "verifica-se",
    )
    sentence_splitter: re.Pattern = field(
        default_factory=lambda: re.compile(r"(?<=[\.\?!;])\s+|\n+")
    )
    min_claim_len: int = 12
    max_claim_len: int = 260
    max_claims_per_chunk: int = 8


# =============================================================================
# SERVICE
# =============================================================================

class ArgumentNeo4jService:
    """
    ArgumentRAG service backed by Neo4j.

    Provides the same conceptual interface as ArgumentPack but stores
    all argument structures (Claims, Evidence, Actors, Issues) in Neo4j
    with full multi-tenant isolation and Cypher-based traversal.
    """

    def __init__(self, driver=None, database: str = "iudex", config: Optional[ArgumentNeo4jConfig] = None):
        self._driver = driver
        self._database = database
        self.config = config or ArgumentNeo4jConfig()
        self._schema_ensured = False

    def _get_driver(self):
        """Lazy driver initialization."""
        if self._driver is None:
            from app.services.rag.config import get_rag_config
            rag_config = get_rag_config()
            from neo4j import GraphDatabase
            self._driver = GraphDatabase.driver(
                rag_config.neo4j_uri,
                auth=(rag_config.neo4j_user, rag_config.neo4j_password),
            )
            self._database = rag_config.neo4j_database
        return self._driver

    def _ensure_schema(self) -> None:
        """Create constraints and indexes if not already done."""
        if self._schema_ensured:
            return
        try:
            driver = self._get_driver()
            with driver.session(database=self._database) as session:
                for stmt in ArgumentCypher.SCHEMA_CONSTRAINTS:
                    try:
                        session.run(stmt)
                    except Exception as e:
                        logger.debug("Schema constraint skipped: %s (%s)", stmt[:60], e)
                for stmt in ArgumentCypher.SCHEMA_INDEXES:
                    try:
                        session.run(stmt)
                    except Exception as e:
                        logger.debug("Schema index skipped: %s (%s)", stmt[:60], e)
            self._schema_ensured = True
        except Exception as e:
            logger.warning("Could not ensure argument schema: %s", e)

    def _execute_write(self, query: str, params: Dict[str, Any]) -> Optional[Any]:
        """Execute a write query."""
        driver = self._get_driver()
        self._ensure_schema()
        with driver.session(database=self._database) as session:
            result = session.run(query, **params)
            return result.single()

    def _execute_read(self, query: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Execute a read query and return list of records as dicts."""
        driver = self._get_driver()
        with driver.session(database=self._database) as session:
            result = session.run(query, **params)
            return [dict(record) for record in result]

    # -----------------------------------------------------------------
    # Ingest
    # -----------------------------------------------------------------

    def _infer_stance(self, text: str) -> str:
        """Infer stance (asserts/disputes/neutral) from text cues."""
        text_lower = _lower(text)
        for cue in self.config.dispute_cues:
            if cue in text_lower:
                return "disputes"
        for cue in self.config.assert_cues:
            if cue in text_lower:
                return "asserts"
        return "neutral"

    def _extract_claims(self, text: str) -> List[Dict[str, Any]]:
        """Extract claim-like sentences from text (heuristic)."""
        sentences = self.config.sentence_splitter.split(text)
        claims = []
        for s in sentences:
            s = s.strip()
            if len(s) < self.config.min_claim_len or len(s) > self.config.max_claim_len:
                continue
            # Basic heuristic: contains a verb-like pattern
            if re.search(r"\b(é|são|foi|foram|deve|pode|tem|há|houve|estabelece|determina|prevê|dispõe|configura)\b", s, re.I):
                polarity = -1 if any(cue in _lower(s) for cue in self.config.dispute_cues) else 1
                claims.append({
                    "text": _norm(s),
                    "polarity": polarity,
                })
            if len(claims) >= self.config.max_claims_per_chunk:
                break
        return claims

    def ingest_chunk_arguments(
        self,
        text: str,
        *,
        chunk_uid: str,
        doc_id: str,
        doc_hash: str,
        tenant_id: str,
        case_id: Optional[str] = None,
        scope: str = "global",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Ingest argument structures from a single chunk into Neo4j.

        Creates Evidence, Claims, Actors, Issues and their relationships.
        Returns stats dict.
        """
        meta = metadata or {}
        stats = {
            "claims": 0,
            "evidence": 0,
            "actors": 0,
            "issues": 0,
            "relationships": 0,
        }

        try:
            stance = self._infer_stance(text)

            # 1) Evidence node (anchor)
            title = meta.get("title") or meta.get("titulo") or meta.get("filename")
            evidence_id = _stable_id("evidence", doc_id, chunk_uid)
            self._execute_write(ArgumentCypher.MERGE_EVIDENCE, {
                "evidence_id": evidence_id,
                "text": _clip(text, 500),
                "evidence_type": meta.get("source_type", "documento"),
                "weight": 0.9 if stance != "neutral" else 0.6,
                "doc_id": doc_id,
                "chunk_id": chunk_uid,
                "source_chunk_uid": chunk_uid,
                "tenant_id": tenant_id,
                "scope": scope,
                "title": title,
            })
            stats["evidence"] = 1

            # 2) Actor (if available in metadata)
            actor_name = meta.get("actor") or meta.get("ator") or meta.get("parte") or meta.get("author")
            actor_id = None
            if actor_name:
                actor_id = _stable_id("actor", str(actor_name))
                self._execute_write(ArgumentCypher.MERGE_ACTOR, {
                    "actor_id": actor_id,
                    "name": _norm(str(actor_name)),
                    "role": meta.get("role", "parte"),
                    "tenant_id": tenant_id,
                })
                stats["actors"] = 1

            # 3) Extract and create claims
            claims = self._extract_claims(text)
            for c in claims:
                claim_id = _stable_id("claim", c["text"])
                claim_type = "contratese" if c["polarity"] < 0 else "tese"
                self._execute_write(ArgumentCypher.MERGE_CLAIM, {
                    "claim_id": claim_id,
                    "text": c["text"],
                    "claim_type": claim_type,
                    "polarity": c["polarity"],
                    "confidence": 0.7,
                    "source_chunk_uid": chunk_uid,
                    "tenant_id": tenant_id,
                    "case_id": case_id,
                    "scope": scope,
                })
                stats["claims"] += 1

                # Link chunk -> claim
                try:
                    self._execute_write(ArgumentCypher.LINK_CHUNK_CLAIM, {
                        "chunk_uid": chunk_uid,
                        "claim_id": claim_id,
                    })
                    stats["relationships"] += 1
                except Exception:
                    pass

                # Link evidence -> claim
                ev_stance = "contra" if stance == "disputes" else "pro"
                ev_weight = 0.9 if stance != "neutral" else 0.6
                try:
                    self._execute_write(ArgumentCypher.LINK_EVIDENCE_CLAIM, {
                        "evidence_id": evidence_id,
                        "claim_id": claim_id,
                        "stance": ev_stance,
                        "weight": ev_weight,
                    })
                    stats["relationships"] += 1
                except Exception:
                    pass

                # Link actor -> claim
                if actor_id:
                    actor_stance = "disputes" if stance == "disputes" else "asserts"
                    try:
                        self._execute_write(ArgumentCypher.LINK_ACTOR_CLAIM, {
                            "actor_id": actor_id,
                            "claim_id": claim_id,
                            "stance": actor_stance,
                        })
                        stats["relationships"] += 1
                    except Exception:
                        pass

        except Exception as e:
            logger.error("Failed to ingest chunk arguments: %s", e)

        return stats

    def ingest_arguments(
        self,
        doc_hash: str,
        chunks: List[Dict[str, Any]],
        tenant_id: str,
        case_id: Optional[str] = None,
        scope: str = "global",
    ) -> Dict[str, Any]:
        """
        Ingest argument structures from all chunks of a document.

        Args:
            doc_hash: Document hash
            chunks: List of chunk dicts with 'chunk_uid', 'text', optional 'metadata'
            tenant_id: Tenant ID for multi-tenant isolation
            case_id: Optional case ID
            scope: Data scope (global, private, group, local)
        """
        total_stats = {
            "doc_hash": doc_hash,
            "chunks_processed": 0,
            "total_claims": 0,
            "total_evidence": 0,
            "total_actors": 0,
            "total_relationships": 0,
        }

        for chunk in chunks:
            chunk_uid = chunk.get("chunk_uid", "")
            text = chunk.get("text", "")
            if not text or not chunk_uid:
                continue

            stats = self.ingest_chunk_arguments(
                text=text,
                chunk_uid=chunk_uid,
                doc_id=doc_hash,
                doc_hash=doc_hash,
                tenant_id=tenant_id,
                case_id=case_id,
                scope=scope,
                metadata=chunk.get("metadata"),
            )

            total_stats["chunks_processed"] += 1
            total_stats["total_claims"] += stats["claims"]
            total_stats["total_evidence"] += stats["evidence"]
            total_stats["total_actors"] += stats["actors"]
            total_stats["total_relationships"] += stats["relationships"]

        logger.info(
            "Ingested arguments for doc %s: %d claims, %d evidence, %d relationships",
            doc_hash,
            total_stats["total_claims"],
            total_stats["total_evidence"],
            total_stats["total_relationships"],
        )
        return total_stats

    # -----------------------------------------------------------------
    # Query: Debate Context
    # -----------------------------------------------------------------

    def get_debate_context(
        self,
        results: List[Dict[str, Any]],
        tenant_id: str,
        case_id: Optional[str] = None,
        max_claims: int = 5,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Build debate context (pro/contra) from RAG retrieval results.

        Maps results to Evidence nodes via doc_id, then traverses to Claims.
        Returns (formatted_context, stats_dict).
        """
        # Extract doc_ids from results
        doc_ids = set()
        for r in results:
            meta = r.get("metadata", {}) if isinstance(r, dict) else {}
            doc_id = meta.get("doc_id") or meta.get("document_id") or r.get("doc_id")
            if doc_id:
                doc_ids.add(str(doc_id))

        if not doc_ids:
            return "", {
                "results_seen": len(results),
                "doc_ids": 0,
                "claims_found": 0,
                "status": "no_doc_ids",
            }

        try:
            records = self._execute_read(
                ArgumentCypher.FIND_DEBATE_CONTEXT,
                {
                    "doc_ids": list(doc_ids),
                    "tenant_id": tenant_id,
                    "case_id": case_id,
                    "max_claims": max_claims,
                },
            )
        except Exception as e:
            logger.error("Debate context query failed: %s", e)
            return "", {"error": str(e)}

        if not records:
            return "", {
                "results_seen": len(results),
                "doc_ids": len(doc_ids),
                "claims_found": 0,
                "status": "no_claims",
            }

        # Format debate context
        lines = ["### Estrutura Argumentativa (Pró/Contra)\n"]
        for rec in records:
            claim_text = rec.get("claim_text", "?")
            claim_type = rec.get("claim_type", "tese")
            evidence_list = rec.get("evidence_list", [])
            actors = rec.get("actors", [])
            opposing = rec.get("opposing_claims", [])

            pro = [e for e in evidence_list if e.get("stance") == "pro"]
            contra = [e for e in evidence_list if e.get("stance") == "contra"]

            # Status classification
            if not pro and not contra:
                status = "sem evidências"
            elif pro and not contra:
                status = "sustentado"
            elif contra and not pro:
                status = "contestado"
            else:
                status = "inconclusivo"

            lines.append(f"**[{claim_type.upper()}]** {_clip(claim_text, 200)}")
            lines.append(f"  Status: {status}")

            if pro:
                lines.append(f"  A favor ({len(pro)}):")
                for e in pro[:3]:
                    title = e.get("title") or e.get("doc_id", "?")
                    lines.append(f"    - {_clip(str(title), 80)}")

            if contra:
                lines.append(f"  Contra ({len(contra)}):")
                for e in contra[:3]:
                    title = e.get("title") or e.get("doc_id", "?")
                    lines.append(f"    - {_clip(str(title), 80)}")

            if actors:
                valid_actors = [a for a in actors if a.get("name")]
                if valid_actors:
                    names = ", ".join(a["name"] for a in valid_actors[:3])
                    lines.append(f"  Atores: {names}")

            if opposing:
                valid_opp = [o for o in opposing if o.get("text")]
                if valid_opp:
                    lines.append(f"  Contestado por:")
                    for o in valid_opp[:2]:
                        lines.append(f"    - {_clip(o['text'], 100)}")

            lines.append("")

        context = "\n".join(lines)

        # Truncate to max chars
        if len(context) > self.config.max_context_chars:
            context = context[: self.config.max_context_chars] + "\n[... truncado]"

        stats = {
            "results_seen": len(results),
            "doc_ids": len(doc_ids),
            "claims_found": len(records),
            "status": "ok",
        }

        return context, stats

    # -----------------------------------------------------------------
    # Query: Argument Graph (for visualization)
    # -----------------------------------------------------------------

    def get_argument_graph(
        self,
        tenant_id: str,
        case_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get full argument structure for visualization.

        Returns nodes and edges suitable for frontend rendering.
        """
        try:
            records = self._execute_read(
                ArgumentCypher.FIND_ARGUMENT_GRAPH,
                {"tenant_id": tenant_id, "case_id": case_id},
            )
        except Exception as e:
            logger.error("Argument graph query failed: %s", e)
            return {"nodes": [], "edges": [], "error": str(e)}

        nodes = {}
        edges = []

        for rec in records:
            # Claim node
            c = rec.get("c")
            if c:
                cid = c.get("claim_id", "")
                if cid and cid not in nodes:
                    nodes[cid] = {
                        "id": cid,
                        "type": "claim",
                        "label": _clip(c.get("text", "?"), 80),
                        "claim_type": c.get("claim_type", "tese"),
                        "polarity": c.get("polarity", 1),
                    }

            # Evidence node
            ev = rec.get("ev")
            if ev:
                evid = ev.get("evidence_id", "")
                if evid and evid not in nodes:
                    nodes[evid] = {
                        "id": evid,
                        "type": "evidence",
                        "label": _clip(ev.get("title") or ev.get("text", "?"), 60),
                    }
                # Evidence -> Claim edge
                er = rec.get("er")
                if er and c:
                    edges.append({
                        "source": evid,
                        "target": c.get("claim_id", ""),
                        "type": "EVIDENCES",
                        "stance": er.get("stance", "pro"),
                        "weight": er.get("weight", 0.5),
                    })

            # Actor node
            a = rec.get("a")
            if a:
                aid = a.get("actor_id", "")
                if aid and aid not in nodes:
                    nodes[aid] = {
                        "id": aid,
                        "type": "actor",
                        "label": a.get("name", "?"),
                        "role": a.get("role"),
                    }
                ar = rec.get("ar")
                if ar and c:
                    edges.append({
                        "source": aid,
                        "target": c.get("claim_id", ""),
                        "type": "ARGUES",
                        "stance": ar.get("stance", "asserts"),
                    })

            # Issue node
            i = rec.get("i")
            if i:
                iid = i.get("issue_id", "")
                if iid and iid not in nodes:
                    nodes[iid] = {
                        "id": iid,
                        "type": "issue",
                        "label": _clip(i.get("text", "?"), 80),
                    }
                if c:
                    edges.append({
                        "source": c.get("claim_id", ""),
                        "target": iid,
                        "type": "RAISES",
                    })

            # Opposing claim
            c2 = rec.get("c2")
            if c2 and c:
                c2id = c2.get("claim_id", "")
                if c2id and c2id not in nodes:
                    nodes[c2id] = {
                        "id": c2id,
                        "type": "claim",
                        "label": _clip(c2.get("text", "?"), 80),
                        "claim_type": "contratese",
                    }
                edges.append({
                    "source": c2id,
                    "target": c.get("claim_id", ""),
                    "type": "OPPOSES",
                })

        return {
            "nodes": list(nodes.values()),
            "edges": edges,
        }

    # -----------------------------------------------------------------
    # Stats
    # -----------------------------------------------------------------

    def get_stats(self, tenant_id: str) -> Dict[str, int]:
        """Get argument graph statistics for a tenant."""
        try:
            records = self._execute_read(
                ArgumentCypher.GET_STATS,
                {"tenant_id": tenant_id},
            )
            if records:
                return dict(records[0])
        except Exception as e:
            logger.error("Stats query failed: %s", e)
        return {"claims": 0, "evidence": 0, "actors": 0, "issues": 0}

    def health_check(self) -> bool:
        """Check if Neo4j is available."""
        try:
            driver = self._get_driver()
            with driver.session(database=self._database) as session:
                session.run("RETURN 1")
            return True
        except Exception:
            return False

    def close(self) -> None:
        """Close the Neo4j driver."""
        if self._driver:
            self._driver.close()


# =============================================================================
# SINGLETON
# =============================================================================

_instance: Optional[ArgumentNeo4jService] = None
_instance_lock = threading.Lock()


def get_argument_neo4j(
    driver=None,
    database: Optional[str] = None,
    config: Optional[ArgumentNeo4jConfig] = None,
) -> ArgumentNeo4jService:
    """Get or create the singleton ArgumentNeo4jService."""
    global _instance
    if _instance is not None:
        return _instance

    with _instance_lock:
        if _instance is not None:
            return _instance
        _instance = ArgumentNeo4jService(
            driver=driver,
            database=database or "iudex",
            config=config,
        )
        return _instance


def close_argument_neo4j() -> None:
    """Close the singleton instance."""
    global _instance
    with _instance_lock:
        if _instance is not None:
            _instance.close()
            _instance = None
