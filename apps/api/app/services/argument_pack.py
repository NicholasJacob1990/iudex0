"""
argument_pack.py

Pack genérico (domínio-agnóstico) para "fatos/alegações (claims), prova (evidence) e contraditório (pro/contra)"
no seu GraphRAG.

✅ Funciona bem quando você:
- armazena chunks com metadados mínimos (actor, source_type, stance, doc_id/chunk_id etc.)
- quer responder perguntas trazendo "os dois lados" (o que sustenta vs o que contradiz/impugna)

Integra com o seu rag_graph.py porque:
- seu grafo grava entity_type e relation como strings no NetworkX (entity_type=...value / relation=...value)
- seus filtros (query_related / find_entities) comparam com .value

Como usar (exemplo rápido):

from rag_graph import create_knowledge_graph
from argument_pack import ARGUMENT_PACK

kg = create_knowledge_graph("kg.json")   # é "LegalKnowledgeGraph", mas serve como grafo genérico
for chunk in chunks:
    ARGUMENT_PACK.ingest_chunk(
        graph=kg,
        text=chunk["text"],
        metadata=chunk.get("metadata", {}),
    )

# Depois, para montar contexto “pró/contra” a partir de uma pergunta:
ctx = ARGUMENT_PACK.build_debate_context_from_query(kg, "O erro 500 depende do payload > 1MB?", hops=2)

"""

from __future__ import annotations

import re
import hashlib
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Union


# =============================================================================
# Enums (tipos de nós e relações) — independentes do domínio
# =============================================================================

class ArgumentEntityType(Enum):
    ACTOR = "actor"           # quem afirma/contesta: parte, autor, equipe, órgão, "paper X"
    CLAIM = "claim"           # alegação/proposição: "X aconteceu", "Y causa Z"
    ISSUE = "issue"           # ponto controvertido / pergunta a decidir
    EVIDENCE = "evidence"     # evidência: documento, log, laudo, dataset, print, email
    FACT = "fact"             # opcional: ocorrência/observação estruturada (tempo/local etc.)
    SOURCE = "source"         # opcional: fonte (sistema, jornal, repositório) separada de ACTOR


class ArgumentRelationType(Enum):
    ASSERTS = "asserts"           # actor/source -> claim
    DISPUTES = "disputes"         # actor/source -> claim (impugna/nega)
    SUPPORTS = "supports"         # evidence -> claim (sustenta)
    CONTRADICTS = "contradicts"   # evidence -> claim (contraria)
    REFUTES = "refutes"           # claim -> claim (refuta outra)
    DEPENDS_ON = "depends_on"     # claim -> claim (depende de premissa)
    ABOUT = "about"               # issue -> claim/ fact (questão sobre)
    MENTIONS = "mentions"         # source/evidence -> actor/claim/etc (menção neutra)
    SAME_AS = "same_as"           # claim -> claim (deduplicação/cluster)
    QUALIFIES = "qualifies"       # claim -> claim (qualificação: "em regra", "exceto")


# =============================================================================
# Config
# =============================================================================

@dataclass
class ArgumentPackConfig:
    """
    Você pode ajustar o comportamento sem reescrever o pack.
    """
    language: str = "pt"  # "pt" ou "en" (padrões mistos também funcionam)
    min_claim_len: int = 12
    max_claim_len: int = 260
    max_claims_per_chunk: int = 8
    include_neutral_mentions: bool = False  # cria arestas MENTIONS por padrão?

    # limiar simples para "sinais de contraditório" (nega/impugna)
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

    issue_cues: Tuple[str, ...] = (
        "questão", "ponto controvertido", "controvérsia", "issue", "question",
        "discute-se", "debate-se", "define-se", "se", "whether",
    )

    evidence_cues: Tuple[str, ...] = (
        "laudo", "relatório", "log", "registro", "print", "screenshot", "exame",
        "e-mail", "email", "anexo", "análise", "dataset", "planilha", "comprovante",
        "nota fiscal", "nf", "boletim", "protocolo", "ticket", "chamado",
    )

    # padrões para extrair evidências "identificáveis"
    evidence_id_patterns: Tuple[re.Pattern, ...] = field(default_factory=lambda: (
        re.compile(r"\b(ticket|chamado|incidente|case)\s*#?\s*([A-Za-z0-9\-_.]{3,})\b", re.I),
        re.compile(r"\b(log\s*id|trace\s*id|request\s*id)\s*[:#]?\s*([A-Za-z0-9\-_.]{6,})\b", re.I),
        re.compile(r"\b([A-Za-z0-9_\-]{3,}\.(?:pdf|png|jpg|jpeg|csv|xlsx|docx|txt|json|xml))\b", re.I),
    ))

    # separador de frases (simples, mas funciona bem o suficiente)
    sentence_splitter: re.Pattern = re.compile(r"(?<=[\.\?!;])\s+|\n+")


# =============================================================================
# Normalização / IDs estáveis
# =============================================================================

def _norm(s: str) -> str:
    s = (s or "").strip()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"\s+", " ", s)
    return s.strip()

def _sha12(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:12]

def _stable_id(*parts: str) -> str:
    raw = "|".join(_norm(p) for p in parts if p is not None)
    return _sha12(raw)

def _clip(s: str, n: int) -> str:
    s = s or ""
    return s if len(s) <= n else s[: n - 1] + "…"

def _lower(s: str) -> str:
    return _norm(s).lower()


# =============================================================================
# Extractor
# =============================================================================

class ArgumentExtractor:
    """
    Extrator heurístico (sem dependência de LLM).
    - Excelente para iniciar (MVP)
    - Depois você pode substituir/encapsular por um extrator LLM mantendo a mesma interface.

    Retorna candidatos (entidades) e sugere relações.
    """

    DATE_PAT = re.compile(
        r"\b(\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2})\b"
    )
    TIME_PAT = re.compile(r"\b(\d{1,2}:\d{2})\b")

    def __init__(self, config: Optional[ArgumentPackConfig] = None):
        self.cfg = config or ArgumentPackConfig()

    # -------------------------
    # Metadados -> seeds fortes
    # -------------------------

    def seed_from_metadata(self, meta: Dict[str, Any]) -> List[Tuple[ArgumentEntityType, str, str, Dict[str, Any]]]:
        meta = meta or {}
        seeds: List[Tuple[ArgumentEntityType, str, str, Dict[str, Any]]] = []

        actor = meta.get("actor") or meta.get("ator") or meta.get("parte") or meta.get("author") or meta.get("speaker")
        if actor:
            actor = _norm(str(actor))
            aid = _stable_id("actor", actor)
            seeds.append((ArgumentEntityType.ACTOR, aid, actor, {"raw": actor}))

        # “Fonte” (sistema/origem) opcional
        source = meta.get("source") or meta.get("origem") or meta.get("system")
        if source:
            source = _norm(str(source))
            sid = _stable_id("source", source)
            seeds.append((ArgumentEntityType.SOURCE, sid, source, {"raw": source}))

        # Evidência/documento identificado
        doc_id = meta.get("doc_id") or meta.get("document_id") or meta.get("id")
        chunk_id = meta.get("chunk_id") or meta.get("chunk") or meta.get("segment_id")
        title = meta.get("title") or meta.get("titulo") or meta.get("filename") or meta.get("file_name")

        if doc_id or chunk_id or title:
            key = f"{doc_id or ''}:{chunk_id or ''}:{title or ''}"
            eid = _stable_id("evidence", key)
            name = _norm(str(title)) if title else f"Evidência {doc_id or chunk_id or eid}"
            md = {
                "doc_id": doc_id,
                "chunk_id": chunk_id,
                "title": title,
                "source_type": meta.get("source_type") or meta.get("tipo"),
                "url": meta.get("url"),
            }
            seeds.append((ArgumentEntityType.EVIDENCE, eid, name, md))

        # Issue explícita (ótimo quando já vem estruturado)
        issue = meta.get("issue") or meta.get("questao") or meta.get("ponto_controvertido")
        if issue:
            if isinstance(issue, list):
                issue_list = issue
            else:
                issue_list = [issue]
            for it in issue_list:
                it = _norm(str(it))
                iid = _stable_id("issue", it)
                seeds.append((ArgumentEntityType.ISSUE, iid, f"Issue: {_clip(it, 90)}", {"text": it}))

        # Claim explícita (se você já tem isso no pipeline)
        claim = meta.get("claim") or meta.get("alegacao") or meta.get("proposicao")
        if claim:
            if isinstance(claim, list):
                claim_list = claim
            else:
                claim_list = [claim]
            for ct in claim_list:
                ct = _norm(str(ct))
                cid = _stable_id("claim", ct)
                seeds.append((ArgumentEntityType.CLAIM, cid, _clip(ct, 110), {"text": ct, "from": "metadata"}))

        return seeds

    # -------------------------
    # Texto -> entidades
    # -------------------------

    def extract_issues(self, text: str) -> List[str]:
        t = _norm(text)
        issues: List[str] = []

        # 1) perguntas explícitas
        for part in re.split(r"\n+", t):
            if "?" in part and len(part) >= 10:
                issues.append(_norm(part))

        # 2) cues
        lt = _lower(t)
        for cue in self.cfg.issue_cues:
            if cue in lt:
                # pega uma janela ao redor do cue
                idx = lt.find(cue)
                snippet = t[max(0, idx - 80) : min(len(t), idx + 180)]
                if len(_norm(snippet)) >= 12:
                    issues.append(_norm(snippet))

        # dedup
        seen = set()
        out = []
        for i in issues:
            key = _lower(i)
            if key not in seen:
                seen.add(key)
                out.append(i)
        return out[:6]

    def _looks_like_claim(self, sent: str) -> bool:
        s = _norm(sent)
        if len(s) < self.cfg.min_claim_len:
            return False
        if len(s) > self.cfg.max_claim_len:
            return True  # frases longas às vezes são claims; vamos cortar depois

        ls = _lower(s)
        # Evita "títulos" muito genéricos
        if len(ls.split()) < 3:
            return False

        # Sinais positivos
        if any(cue in ls for cue in self.cfg.assert_cues):
            return True
        # Sinais de disputa (a frase pode ser uma negativa/impugnação)
        if any(cue in ls for cue in self.cfg.dispute_cues):
            return True

        # Frases declarativas com verbo de ligação frequentemente viram claim
        if re.search(r"\b(e|foi|era|são|está|estavam|ocorre|ocorreu|causa|causou)\b", ls):
            return True

        return False

    def extract_claims(self, text: str) -> List[Dict[str, Any]]:
        t = _norm(text)
        parts = [p.strip() for p in self.cfg.sentence_splitter.split(t) if p.strip()]

        claims: List[Dict[str, Any]] = []
        for p in parts:
            if not self._looks_like_claim(p):
                continue

            s = _norm(p)
            s = _clip(s, self.cfg.max_claim_len)

            ls = _lower(s)
            polarity = -1 if any(cue in ls for cue in self.cfg.dispute_cues) else +1

            dates = self.DATE_PAT.findall(s)
            times = self.TIME_PAT.findall(s)

            claims.append({
                "text": s,
                "polarity": polarity,
                "dates": dates,
                "times": times,
            })

            if len(claims) >= self.cfg.max_claims_per_chunk:
                break

        # dedup (por texto normalizado)
        seen = set()
        out = []
        for c in claims:
            key = _lower(c["text"])
            if key not in seen:
                seen.add(key)
                out.append(c)

        return out

    def extract_evidence_mentions(self, text: str) -> List[Dict[str, Any]]:
        t = _norm(text)
        lt = _lower(t)
        mentions: List[Dict[str, Any]] = []

        # 1) “cues” gerais (sem ID específico)
        for cue in self.cfg.evidence_cues:
            if cue in lt:
                mentions.append({"kind": "cue", "value": cue})

        # 2) IDs/padrões
        for pat in self.cfg.evidence_id_patterns:
            for m in pat.finditer(t):
                label = m.group(1) if m.lastindex and m.lastindex >= 1 else "evidence"
                val = m.group(2) if m.lastindex and m.lastindex >= 2 else m.group(0)
                mentions.append({"kind": "id", "label": _norm(label), "value": _norm(val)})

        # dedup
        seen = set()
        out = []
        for x in mentions:
            key = (x.get("kind"), _lower(str(x.get("label", ""))), _lower(str(x.get("value", ""))))
            if key not in seen:
                seen.add(key)
                out.append(x)

        return out[:8]

    def infer_stance(self, meta: Dict[str, Any], text: str) -> str:
        """
        Retorna: "asserts" | "disputes" | "neutral"
        Prioriza metadados; fallback para heurística no texto.
        """
        meta = meta or {}
        stance = meta.get("stance") or meta.get("posicao") or meta.get("posição") or meta.get("tipo_ato") or meta.get("role")
        if stance:
            s = _lower(str(stance))
            if any(w in s for w in ("dispute", "contest", "impugn", "refut", "nega", "contesta", "impugna")):
                return "disputes"
            if any(w in s for w in ("assert", "claim", "alega", "afirma", "sustenta", "relata", "report")):
                return "asserts"

        lt = _lower(text)
        if any(cue in lt for cue in self.cfg.dispute_cues):
            return "disputes"
        if any(cue in lt for cue in self.cfg.assert_cues):
            return "asserts"

        return "neutral"


# =============================================================================
# Pack (integração com o seu grafo)
# =============================================================================

@dataclass
class ArgumentPack:
    config: ArgumentPackConfig = field(default_factory=ArgumentPackConfig)
    extractor: ArgumentExtractor = field(init=False)

    def __post_init__(self):
        self.extractor = ArgumentExtractor(self.config)

    # -------------------------
    # Nós utilitários
    # -------------------------

    def ensure_actor_node(self, graph, actor_name: str) -> str:
        actor_name = _norm(actor_name)
        aid = _stable_id("actor", actor_name)
        # node_id no seu grafo é f"{type}:{id}"
        node_id = f"{ArgumentEntityType.ACTOR.value}:{aid}"
        if node_id in graph.graph.nodes:
            return node_id
        return graph.add_entity(ArgumentEntityType.ACTOR, aid, actor_name, {})

    def ensure_evidence_node(self, graph, text: str, meta: Dict[str, Any]) -> str:
        meta = meta or {}
        # tenta metadados; senão usa hash do conteúdo
        doc_id = meta.get("doc_id") or meta.get("document_id") or meta.get("id")
        chunk_id = meta.get("chunk_id") or meta.get("chunk") or meta.get("segment_id")
        title = meta.get("title") or meta.get("titulo") or meta.get("filename") or meta.get("file_name")
        url = meta.get("url")

        key = f"{doc_id or ''}:{chunk_id or ''}:{title or ''}:{url or ''}"
        if key.strip(":") == "":
            key = _clip(_norm(text), 240)

        eid = _stable_id("evidence", key)
        name = _norm(str(title)) if title else f"Evidência {eid}"
        md = {
            "doc_id": doc_id,
            "chunk_id": chunk_id,
            "title": title,
            "url": url,
            "source_type": meta.get("source_type") or meta.get("tipo"),
        }

        node_id = f"{ArgumentEntityType.EVIDENCE.value}:{eid}"
        if node_id in graph.graph.nodes:
            return node_id
        return graph.add_entity(ArgumentEntityType.EVIDENCE, eid, name, md)

    def ensure_issue_node(self, graph, issue_text: str) -> str:
        it = _norm(issue_text)
        iid = _stable_id("issue", it)
        node_id = f"{ArgumentEntityType.ISSUE.value}:{iid}"
        if node_id in graph.graph.nodes:
            return node_id
        return graph.add_entity(ArgumentEntityType.ISSUE, iid, f"Issue: {_clip(it, 110)}", {"text": it})

    def ensure_claim_node(self, graph, claim_text: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        ct = _norm(claim_text)
        cid = _stable_id("claim", ct)
        node_id = f"{ArgumentEntityType.CLAIM.value}:{cid}"
        if node_id in graph.graph.nodes:
            return node_id
        md = {"text": ct}
        if metadata:
            md.update(metadata)
        return graph.add_entity(ArgumentEntityType.CLAIM, cid, _clip(ct, 120), md)

    # -------------------------
    # Ingestão de chunk
    # -------------------------

    def ingest_chunk(self, graph, text: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Cria nós e relações de "debate" a partir de um chunk.
        Retorna um relatório (ids criados/encontrados).
        """
        meta = metadata or {}
        report: Dict[str, Any] = {"actors": [], "claims": [], "issues": [], "evidence": None, "edges": 0}

        stance = self.extractor.infer_stance(meta, text)

        # 1) evidence node (âncora)
        ev_node = self.ensure_evidence_node(graph, text, meta)
        report["evidence"] = ev_node

        # 2) actor (se houver)
        actor_name = meta.get("actor") or meta.get("ator") or meta.get("parte") or meta.get("author") or meta.get("speaker")
        actor_node = None
        if actor_name:
            actor_node = self.ensure_actor_node(graph, str(actor_name))
            report["actors"].append(actor_node)

            # liga evidence -> actor (opcional / neutro)
            if self.config.include_neutral_mentions:
                if graph.add_relationship(ev_node, actor_node, ArgumentRelationType.MENTIONS, weight=0.3, metadata={"via": "metadata"}):
                    report["edges"] += 1

        # 3) issues
        for it in self.extractor.extract_issues(text):
            issue_node = self.ensure_issue_node(graph, it)
            report["issues"].append(issue_node)
            if graph.add_relationship(issue_node, ev_node, ArgumentRelationType.MENTIONS, weight=0.2, metadata={"via": "text"}):
                report["edges"] += 1

        # 4) claims
        claims = self.extractor.extract_claims(text)
        for c in claims:
            cmeta = {
                "polarity": c.get("polarity", +1),
                "dates": c.get("dates", []),
                "times": c.get("times", []),
                "from": "text",
            }
            claim_node = self.ensure_claim_node(graph, c["text"], cmeta)
            report["claims"].append(claim_node)

            # 4.1) actor -> asserts/disputes -> claim
            if actor_node:
                rel = ArgumentRelationType.DISPUTES if stance == "disputes" else ArgumentRelationType.ASSERTS
                if graph.add_relationship(actor_node, claim_node, rel, weight=1.0, metadata={"via": "chunk"}):
                    report["edges"] += 1

            # 4.2) evidence -> supports/contradicts -> claim
            # Heurística:
            # - se stance=disputes: por padrão a evidência (o chunk) é "contraditória" (nega algo)
            # - senão: suporta o claim extraído daquele chunk
            ev_rel = ArgumentRelationType.CONTRADICTS if stance == "disputes" else ArgumentRelationType.SUPPORTS
            w = 0.9 if stance != "neutral" else 0.6
            if graph.add_relationship(ev_node, claim_node, ev_rel, weight=w, metadata={"via": "text", "stance": stance}):
                report["edges"] += 1

            # 4.3) issue -> about -> claim (se houver alguma issue no chunk)
            for issue_node in report["issues"]:
                if graph.add_relationship(issue_node, claim_node, ArgumentRelationType.ABOUT, weight=0.7, metadata={"via": "cooccur"}):
                    report["edges"] += 1

        # 5) evidências mencionadas (IDs / arquivos / tickets) como "evidence" secundária
        for m in self.extractor.extract_evidence_mentions(text):
            if m.get("kind") == "id":
                label = m.get("label", "evidence")
                val = m.get("value", "")
                ev2_id = _stable_id("evidence_mention", label, val)
                ev2_name = f"{label}: {val}"
                ev2_node = f"{ArgumentEntityType.EVIDENCE.value}:{ev2_id}"
                if ev2_node not in graph.graph.nodes:
                    ev2_node = graph.add_entity(
                        ArgumentEntityType.EVIDENCE,
                        ev2_id,
                        _clip(ev2_name, 120),
                        {"label": label, "value": val, "from": "mention"}
                    )
                if graph.add_relationship(ev_node, ev2_node, ArgumentRelationType.MENTIONS, weight=0.4, metadata={"via": "evidence_id"}):
                    report["edges"] += 1

        return report

    # -------------------------
    # Busca de seeds a partir de consulta
    # -------------------------

    def resolve_query_seeds(self, graph, query: str, max_seeds: int = 10) -> Set[str]:
        """
        Resolve seeds simples:
        - tenta achar CLAIM/ISSUE contendo termos relevantes
        - fallback: qualquer entidade cujo nome contenha a query
        """
        q = _lower(query)
        seeds: Set[str] = set()

        # Evita varrer o grafo inteiro em queries muito curtas/ruidosas.
        if len(q) < 4:
            return seeds

        # tenta encontrar claims por partes relevantes
        tokens = [t for t in re.split(r"\W+", q) if len(t) >= 4]
        tokens = tokens[:6]  # limita

        # Se não temos tokens relevantes, aplica apenas fallback de substring (sem duplicar varredura).
        if not tokens:
            for node_id, data in graph.graph.nodes(data=True):
                name = _lower(data.get("name", ""))
                if q and q in name:
                    seeds.add(node_id)
                    if len(seeds) >= max_seeds:
                        break
            return seeds

        fallback_hits: List[str] = []

        # varre nós do grafo (barato o suficiente para grafo médio)
        for node_id, data in graph.graph.nodes(data=True):
            name = _lower(data.get("name", ""))
            et = data.get("entity_type", "")

            if et in (ArgumentEntityType.CLAIM.value, ArgumentEntityType.ISSUE.value):
                if any(tok in name for tok in tokens) or (q and q in name):
                    seeds.add(node_id)
                    if len(seeds) >= max_seeds:
                        break
            elif q and q in name and len(fallback_hits) < max_seeds:
                # Fallback genérico (qualquer entidade cujo nome contenha a query).
                # Mantemos como "backup" sem chamar find_entities (evita segunda varredura).
                fallback_hits.append(node_id)

        if not seeds and fallback_hits:
            seeds.update(fallback_hits[:max_seeds])

        return seeds

    def _build_evidence_index(self, graph) -> Tuple[Dict[Tuple[str, str], str], Dict[str, List[str]]]:
        """
        Indexa nós de evidência por (doc_id, chunk_id) e por doc_id.
        Ajuda a resolver resultados do RAG -> nós no grafo sem criar/ingerir dados em query-time.
        """
        by_doc_chunk: Dict[Tuple[str, str], str] = {}
        by_doc: Dict[str, List[str]] = {}
        for node_id, data in graph.graph.nodes(data=True):
            if data.get("entity_type") != ArgumentEntityType.EVIDENCE.value:
                continue
            doc_id = data.get("doc_id")
            if doc_id is None:
                continue
            doc_key = str(doc_id).strip()
            if not doc_key:
                continue
            chunk_id = data.get("chunk_id")
            if chunk_id is not None and str(chunk_id).strip():
                by_doc_chunk[(doc_key, str(chunk_id).strip())] = node_id
            by_doc.setdefault(doc_key, []).append(node_id)
        return by_doc_chunk, by_doc

    def _result_meta(self, result: Dict[str, Any]) -> Dict[str, Any]:
        meta = result.get("metadata") if isinstance(result, dict) else None
        return meta if isinstance(meta, dict) else {}

    def _resolve_evidence_node_from_result(
        self,
        graph,
        result: Dict[str, Any],
        *,
        evidence_by_doc_chunk: Dict[Tuple[str, str], str],
        evidence_by_doc: Dict[str, List[str]],
    ) -> Optional[str]:
        meta = self._result_meta(result)
        doc_id = meta.get("doc_id") or meta.get("document_id") or meta.get("id") or result.get("doc_id")
        chunk_id = meta.get("chunk_id") or meta.get("chunk") or meta.get("segment_id") or result.get("chunk_id")

        doc_key = str(doc_id).strip() if doc_id is not None else ""
        chunk_key = str(chunk_id).strip() if chunk_id is not None else ""
        if doc_key and chunk_key:
            hit = evidence_by_doc_chunk.get((doc_key, chunk_key))
            if hit:
                return hit
        if doc_key:
            candidates = evidence_by_doc.get(doc_key) or []
            if candidates:
                # Ambíguo sem chunk_id; escolhe o primeiro (normalmente único).
                return candidates[0]
        return None

    def resolve_result_claim_seeds(
        self,
        graph,
        results: List[Dict[str, Any]],
        *,
        max_results: int = 12,
        max_seeds: int = 12,
    ) -> Tuple[Set[str], Dict[str, Any]]:
        """
        Resolve seeds de CLAIM a partir dos resultados recuperados (RAG):
        - mapeia cada resultado para um nó de evidência (por doc_id/chunk_id)
        - coleta CLAIMs conectadas via SUPPORTS/CONTRADICTS
        """
        results = results or []
        max_results = int(max_results or 0)
        max_seeds = int(max_seeds or 0)
        if max_results <= 0:
            max_results = 12
        if max_seeds <= 0:
            max_seeds = 12

        by_doc_chunk, by_doc = self._build_evidence_index(graph)
        evidence_nodes: List[str] = []
        for item in results[:max_results]:
            ev = self._resolve_evidence_node_from_result(
                graph,
                item,
                evidence_by_doc_chunk=by_doc_chunk,
                evidence_by_doc=by_doc,
            )
            if ev and ev not in evidence_nodes:
                evidence_nodes.append(ev)

        claim_seeds: Set[str] = set()
        rels = {
            ArgumentRelationType.SUPPORTS.value,
            ArgumentRelationType.CONTRADICTS.value,
        }
        for ev in evidence_nodes:
            for _u, v, ed in graph.graph.out_edges(ev, data=True):
                if ed.get("relation") not in rels:
                    continue
                if graph.graph.nodes[v].get("entity_type") != ArgumentEntityType.CLAIM.value:
                    continue
                claim_seeds.add(v)
                if len(claim_seeds) >= max_seeds:
                    break
            if len(claim_seeds) >= max_seeds:
                break

        stats = {
            "results_seen": min(len(results), max_results),
            "evidence_nodes": len(evidence_nodes),
            "seed_nodes": len(claim_seeds),
            "max_results": int(max_results),
            "max_seeds": int(max_seeds),
        }
        return claim_seeds, stats

    # -------------------------
    # Contexto “pró/contra”
    # -------------------------

    # ----------------------------
    # Debate builder (produção)
    # ----------------------------

    def _status_from_counts(self, supports_n: int, contradicts_n: int) -> str:
        """
        Classificação simples do status probatório de uma CLAIM:
          - no_evidence: não há evidências a favor nem contra (acima do limiar)
          - supported: há evidências a favor e nenhuma contra (acima do limiar)
          - not_confirmed: há evidências contra e nenhuma a favor (acima do limiar)
          - inconclusive: há evidências a favor e contra (acima do limiar)
        """
        if supports_n <= 0 and contradicts_n <= 0:
            return "no_evidence"
        if supports_n > 0 and contradicts_n <= 0:
            return "supported"
        if supports_n <= 0 and contradicts_n > 0:
            return "not_confirmed"
        return "inconclusive"

    def build_debate_bundle(
        self,
        graph,
        seed_nodes: Set[str],
        hops: int = 2,
        *,
        max_claims: int = 3,
        max_support: int = 3,
        max_contra: int = 3,
        max_actors: int = 2,
        max_issues: int = 2,
        max_chars: Optional[int] = 8000,
        evidence_weight_threshold: float = 0.6,
        risk_mode: str = "high",
    ) -> Dict[str, Any]:
        """
        Retorna um bundle estruturado do debate (pró/contra), ideal para auditoria/logs.

        Importante:
        - Assume o grafo do `rag_graph.py` (NetworkX), onde `query_related` retorna um dict
          com `nodes: [{node_id,...}]` e `edges: [...]`.
        """
        max_claims = int(max_claims or 0) or 3
        max_support = int(max_support or 0) or 3
        max_contra = int(max_contra or 0) or 3
        max_actors = int(max_actors or 0) or 2
        max_issues = int(max_issues or 0) or 2

        if not seed_nodes:
            return {
                "params": {"hops": int(hops or 0)},
                "claims": [],
                "overall": {"abstained": True, "status": "no_seeds", "reason": "no_seed_nodes"},
                "stats": {"seed_nodes": 0, "expanded_nodes": 0, "claim_nodes": 0},
            }

        rel_filter = [
            ArgumentRelationType.ASSERTS,
            ArgumentRelationType.DISPUTES,
            ArgumentRelationType.SUPPORTS,
            ArgumentRelationType.CONTRADICTS,
            ArgumentRelationType.ABOUT,
            ArgumentRelationType.REFUTES,
            ArgumentRelationType.DEPENDS_ON,
        ]

        def _node(n: str) -> Dict[str, Any]:
            if getattr(graph, "graph", None) is None:
                return {}
            try:
                return graph.graph.nodes.get(n, {})  # type: ignore[attr-defined]
            except Exception:
                return {}

        def _node_name(n: str) -> str:
            return _node(n).get("name") or n

        def _claim_text(n: str) -> str:
            nd = _node(n)
            return (nd.get("text") or nd.get("name") or n).strip()

        def _issue_text(n: str) -> str:
            nd = _node(n)
            return (nd.get("text") or nd.get("name") or n).strip()

        def _edge_weight(ed: Dict[str, Any]) -> float:
            try:
                return float(ed.get("weight", 1.0))
            except Exception:
                return 1.0

        def _actor_payload(n: str) -> Dict[str, Any]:
            return {"actor_id": n, "name": _clip(_node_name(n), 120)}

        def _issue_payload(n: str) -> Dict[str, Any]:
            return {"issue_id": n, "text": _clip(_issue_text(n), 220)}

        def _evidence_payload(n: str, weight: float) -> Dict[str, Any]:
            nd = _node(n)
            return {
                "evidence_id": n,
                "doc_id": nd.get("doc_id"),
                "chunk_id": nd.get("chunk_id"),
                "title": _clip((nd.get("title") or nd.get("name") or n), 220),
                "url": nd.get("url"),
                "weight": float(weight),
            }

        expanded: Set[str] = set()
        edges_seen = 0
        for s in seed_nodes:
            try:
                sub = graph.query_related(s, hops=hops, relation_filter=rel_filter)
            except Exception:
                continue
            if isinstance(sub, dict):
                edges_seen += len(sub.get("edges", []) or [])
                for node in sub.get("nodes", []) or []:
                    node_id = node.get("node_id") if isinstance(node, dict) else None
                    if node_id:
                        expanded.add(node_id)

        claim_nodes = [
            n
            for n in expanded
            if _node(n).get("entity_type") == ArgumentEntityType.CLAIM.value
        ]

        def _claim_score(cn: str) -> float:
            if getattr(graph, "graph", None) is None:
                return 0.0
            s_sum = 0.0
            c_sum = 0.0
            s_n = 0
            c_n = 0
            try:
                for u, _v, ed in graph.graph.in_edges(cn, data=True):  # type: ignore[attr-defined]
                    r = ed.get("relation")
                    w = _edge_weight(ed)
                    if r == ArgumentRelationType.SUPPORTS.value:
                        s_sum += w
                        s_n += 1
                    elif r == ArgumentRelationType.CONTRADICTS.value:
                        c_sum += w
                        c_n += 1
            except Exception:
                return 0.0
            return (s_sum + c_sum) + 0.05 * (s_n + c_n)

        claim_nodes_sorted = sorted(claim_nodes, key=_claim_score, reverse=True)[:max_claims]

        claims_out: List[Dict[str, Any]] = []
        for cn in claim_nodes_sorted:
            asserters: List[Tuple[str, float]] = []
            disputers: List[Tuple[str, float]] = []
            supports: List[Tuple[str, float]] = []
            contradicts: List[Tuple[str, float]] = []
            issues: List[Tuple[str, float]] = []

            if getattr(graph, "graph", None) is None:
                continue
            try:
                for u, _v, ed in graph.graph.in_edges(cn, data=True):  # type: ignore[attr-defined]
                    r = ed.get("relation")
                    w = _edge_weight(ed)
                    if r == ArgumentRelationType.ASSERTS.value:
                        asserters.append((u, w))
                    elif r == ArgumentRelationType.DISPUTES.value:
                        disputers.append((u, w))
                    elif r == ArgumentRelationType.SUPPORTS.value:
                        supports.append((u, w))
                    elif r == ArgumentRelationType.CONTRADICTS.value:
                        contradicts.append((u, w))
                    elif r == ArgumentRelationType.ABOUT.value:
                        issues.append((u, w))
            except Exception:
                continue

            asserters = sorted(asserters, key=lambda t: t[1], reverse=True)[:max_actors]
            disputers = sorted(disputers, key=lambda t: t[1], reverse=True)[:max_actors]
            supports = sorted(supports, key=lambda t: t[1], reverse=True)[:max_support]
            contradicts = sorted(contradicts, key=lambda t: t[1], reverse=True)[:max_contra]
            issues = sorted(issues, key=lambda t: t[1], reverse=True)[:max_issues]

            supports_n = sum(1 for _n, w in supports if w >= evidence_weight_threshold)
            contradicts_n = sum(1 for _n, w in contradicts if w >= evidence_weight_threshold)
            status = self._status_from_counts(supports_n, contradicts_n)

            claims_out.append(
                {
                    "claim_id": cn,
                    "text": _clip(_claim_text(cn), 350),
                    "issues": [_issue_payload(i) for i, _w in issues],
                    "asserters": [_actor_payload(a) for a, _w in asserters],
                    "disputers": [_actor_payload(a) for a, _w in disputers],
                    "supports": [_evidence_payload(e, w) for e, w in supports],
                    "contradicts": [_evidence_payload(e, w) for e, w in contradicts],
                    "counts": {"supports": supports_n, "contradicts": contradicts_n},
                    "status": status,
                    "score": float(_claim_score(cn)),
                }
            )

        claims_out.sort(key=lambda c: float(c.get("score") or 0.0), reverse=True)

        overall = {"abstained": True, "status": "no_claims", "reason": "no_claims"}
        if claims_out:
            top_status = claims_out[0].get("status")
            if risk_mode in ("high", "strict"):
                abstained = top_status in ("no_evidence", "inconclusive")
            else:
                abstained = top_status == "no_evidence"

            reason_map = {
                "no_evidence": "insufficient_evidence",
                "supported": "supported_by_evidence",
                "not_confirmed": "evidence_contradicts",
                "inconclusive": "conflicting_evidence",
            }
            overall = {
                "abstained": bool(abstained),
                "status": top_status,
                "reason": reason_map.get(str(top_status), "unknown"),
            }

        return {
            "params": {
                "hops": int(hops or 0),
                "max_claims": max_claims,
                "max_support": max_support,
                "max_contra": max_contra,
                "max_actors": max_actors,
                "max_issues": max_issues,
                "max_chars": max_chars,
                "evidence_weight_threshold": float(evidence_weight_threshold),
                "risk_mode": risk_mode,
            },
            "claims": claims_out,
            "overall": overall,
            "stats": {
                "seed_nodes": len(seed_nodes),
                "expanded_nodes": len(expanded),
                "edges_seen": int(edges_seen),
                "claim_nodes": len(claim_nodes_sorted),
            },
        }

    def format_debate_bundle(self, bundle: Dict[str, Any], *, max_chars: Optional[int] = 8000) -> str:
        """
        Formata o bundle pró/contra em texto curto e auditável.
        """
        if not bundle or not bundle.get("claims"):
            return (
                "### 🧩 CONTEXTO DE PROVA E CONTRADITÓRIO (ARGUMENT GRAPH)\n\n"
                "- Sem claims relevantes encontradas no grafo.\n"
            )

        status_pt = {
            "no_evidence": "Sem evidência suficiente (no conjunto recuperado)",
            "supported": "Suportado por evidências (provisório)",
            "not_confirmed": "Não confirmado (evidências contrárias predominam)",
            "inconclusive": "Inconclusivo (evidências conflitantes)",
        }

        def fmt_ev(ev: Dict[str, Any]) -> str:
            title = ev.get("title") or ""
            w = ev.get("weight", 1.0)
            doc_id = ev.get("doc_id")
            chunk_id = ev.get("chunk_id")
            parts = []
            if doc_id is not None and str(doc_id).strip() != "":
                parts.append(f"doc_id={doc_id}")
            if chunk_id is not None and str(chunk_id).strip() != "":
                parts.append(f"chunk_id={chunk_id}")
            ref = ", ".join(parts) if parts else (ev.get("evidence_id") or "")
            return f"{_clip(str(title), 120)} ({ref}) (w={float(w):.2f})"

        lines: List[str] = []
        lines.append("### 🧩 CONTEXTO DE PROVA E CONTRADITÓRIO (ARGUMENT GRAPH)\n")

        for c in bundle.get("claims", [])[: bundle.get("params", {}).get("max_claims", 3)]:
            c_text = c.get("text", "")
            lines.append(f"**CLAIM:** {c_text}")

            st = c.get("status", "no_evidence")
            lines.append(f"- **Status:** {status_pt.get(st, st)}")

            issues = c.get("issues") or []
            if issues:
                lines.append("- **Issue:** " + "; ".join(_clip(x.get("text", ""), 160) for x in issues[:2]))

            asserters = c.get("asserters") or []
            disputers = c.get("disputers") or []
            if asserters:
                lines.append("- **Quem afirma:** " + "; ".join(_clip(a.get("name", ""), 80) for a in asserters))
            if disputers:
                lines.append("- **Quem contesta:** " + "; ".join(_clip(a.get("name", ""), 80) for a in disputers))

            sup = c.get("supports") or []
            con = c.get("contradicts") or []
            if sup:
                lines.append("- **Evidências a favor:** " + "; ".join(fmt_ev(ev) for ev in sup))
            if con:
                lines.append("- **Evidências contra:** " + "; ".join(fmt_ev(ev) for ev in con))

            if st == "no_evidence":
                lines.append("- **Próximo passo sugerido:** localizar documentos/logs primários que confirmem ou refutem a claim.")
            elif st == "inconclusive":
                lines.append("- **Próximo passo sugerido:** buscar evidência decisiva (fonte primária) para resolver o conflito.")
            lines.append("")

        overall = bundle.get("overall") or {}
        if overall.get("abstained"):
            lines.append(f"⚠️ **Conclusão conservadora:** {status_pt.get(overall.get('status'), overall.get('status'))}.")
            lines.append("⚠️ **Nota:** em modo de risco alto, evite afirmar como fato sem lastro suficiente.\n")

        txt = "\n".join(lines).strip() + "\n"
        if max_chars is not None and len(txt) > max_chars:
            return txt[: max_chars - 1].rstrip() + "…\n"
        return txt

    def _build_debate_context_internal(self, graph, seed_nodes: Set[str], hops: int = 2) -> Tuple[str, Dict[str, Any]]:
        """
        Mantém a API usada pelos chamadores atuais (texto + stats),
        mas implementa o "modo produção" (limites, status, packing).
        """
        bundle = self.build_debate_bundle(graph, seed_nodes, hops=hops)
        text = self.format_debate_bundle(bundle, max_chars=bundle.get("params", {}).get("max_chars"))
        stats = dict(bundle.get("stats") or {})
        stats["hops"] = int(hops or 0)
        return text if seed_nodes else "", stats

    def build_debate_context(
        self,
        graph,
        seed_nodes: Set[str],
        hops: int = 2,
        *,
        max_claims: int = 3,
        max_support: int = 3,
        max_contra: int = 3,
        max_actors: int = 2,
        max_issues: int = 2,
        max_chars: Optional[int] = 8000,
        evidence_weight_threshold: float = 0.6,
        risk_mode: str = "high",
        return_structured: bool = False,
    ) -> Union[str, Tuple[str, Dict[str, Any]]]:
        bundle = self.build_debate_bundle(
            graph,
            seed_nodes,
            hops=hops,
            max_claims=max_claims,
            max_support=max_support,
            max_contra=max_contra,
            max_actors=max_actors,
            max_issues=max_issues,
            max_chars=max_chars,
            evidence_weight_threshold=evidence_weight_threshold,
            risk_mode=risk_mode,
        )
        text = self.format_debate_bundle(bundle, max_chars=max_chars)
        return (text, bundle) if return_structured else text

    def build_debate_context_with_stats(
        self,
        graph,
        seed_nodes: Set[str],
        hops: int = 2,
    ) -> Tuple[str, Dict[str, Any]]:
        return self._build_debate_context_internal(graph, seed_nodes, hops=hops)

    def build_debate_context_from_query(
        self,
        graph,
        query: str,
        hops: int = 2,
        *,
        max_claims: int = 3,
        max_support: int = 3,
        max_contra: int = 3,
        max_actors: int = 2,
        max_issues: int = 2,
        max_chars: Optional[int] = 8000,
        evidence_weight_threshold: float = 0.6,
        risk_mode: str = "high",
        return_structured: bool = False,
    ) -> Union[str, Tuple[str, Dict[str, Any]]]:
        seeds = self.resolve_query_seeds(graph, query)
        return self.build_debate_context(
            graph,
            seeds,
            hops=hops,
            max_claims=max_claims,
            max_support=max_support,
            max_contra=max_contra,
            max_actors=max_actors,
            max_issues=max_issues,
            max_chars=max_chars,
            evidence_weight_threshold=evidence_weight_threshold,
            risk_mode=risk_mode,
            return_structured=return_structured,
        )

    def build_debate_context_from_query_with_stats(
        self,
        graph,
        query: str,
        hops: int = 2,
        max_seeds: int = 10,
    ) -> Tuple[str, Dict[str, Any]]:
        seeds = self.resolve_query_seeds(graph, query, max_seeds=max_seeds)
        ctx, stats = self._build_debate_context_internal(graph, seeds, hops=hops)
        stats = dict(stats or {})
        stats["max_seeds"] = int(max_seeds or 0)
        return ctx, stats

    def build_debate_context_from_results_with_stats(
        self,
        graph,
        results: List[Dict[str, Any]],
        *,
        hops: int = 2,
        max_results: int = 12,
        max_seeds: int = 12,
    ) -> Tuple[str, Dict[str, Any]]:
        claim_seeds, seed_stats = self.resolve_result_claim_seeds(
            graph,
            results,
            max_results=max_results,
            max_seeds=max_seeds,
        )
        ctx, stats = self._build_debate_context_internal(graph, claim_seeds, hops=hops)
        merged = dict(seed_stats or {})
        if isinstance(stats, dict):
            merged.update(stats)
        return ctx, merged


# Singleton padrão
ARGUMENT_PACK = ArgumentPack()
