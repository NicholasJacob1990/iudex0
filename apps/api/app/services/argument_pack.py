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
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


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

        # tenta encontrar claims por partes relevantes
        tokens = [t for t in re.split(r"\W+", q) if len(t) >= 4]
        tokens = tokens[:6]  # limita

        # varre nós do grafo (barato o suficiente para grafo médio)
        for node_id, data in graph.graph.nodes(data=True):
            name = _lower(data.get("name", ""))
            et = data.get("entity_type", "")

            if et in (ArgumentEntityType.CLAIM.value, ArgumentEntityType.ISSUE.value):
                if any(tok in name for tok in tokens) or q in name:
                    seeds.add(node_id)
            if len(seeds) >= max_seeds:
                break

        # fallback genérico
        if not seeds:
            matches = graph.find_entities(name_contains=query)
            seeds.update(matches[:max_seeds])

        return seeds

    # -------------------------
    # Contexto “pró/contra”
    # -------------------------

    def build_debate_context(self, graph, seed_nodes: Set[str], hops: int = 2) -> str:
        """
        Constrói um contexto orientado a contraditório:
        - Para cada claim seed, lista:
          * quem afirma/quem contesta (ASSERTS/DISPUTES)
          * evidências que sustentam/contradizem (SUPPORTS/CONTRADICTS)
        """
        if not seed_nodes:
            return ""

        lines: List[str] = []
        lines.append("### 🧩 CONTEXTO DE PROVA E CONTRADITÓRIO (ARGUMENT GRAPH)\n")

        # Só arestas relevantes para debate
        rel_filter = [
            ArgumentRelationType.ASSERTS,
            ArgumentRelationType.DISPUTES,
            ArgumentRelationType.SUPPORTS,
            ArgumentRelationType.CONTRADICTS,
            ArgumentRelationType.ABOUT,
            ArgumentRelationType.REFUTES,
            ArgumentRelationType.DEPENDS_ON,
        ]

        # expande seeds
        expanded: Set[str] = set()
        for s in seed_nodes:
            sub = graph.query_related(s, hops=hops, relation_filter=rel_filter)
            for node in sub.get("nodes", []):
                node_id = node.get("node_id")
                if node_id:
                    expanded.add(node_id)

        # foca em claims
        claim_nodes = [n for n in expanded if graph.graph.nodes[n].get("entity_type") == ArgumentEntityType.CLAIM.value]
        claim_nodes = claim_nodes[:12]

        def _name(n: str) -> str:
            return graph.graph.nodes[n].get("name") or n

        for cn in claim_nodes:
            cdata = graph.graph.nodes[cn]
            lines.append(f"**CLAIM:** {_name(cn)}")
            if cdata.get("polarity") in (-1, "-1"):
                lines.append("- Polaridade (heurística): negativa/contesta")
            elif cdata.get("polarity") in (1, "1"):
                lines.append("- Polaridade (heurística): positiva/afirma")

            # quem afirma / contesta
            asserters = []
            disputers = []
            supporters = []
            contradictors = []

            for u, v, ed in graph.graph.in_edges(cn, data=True):
                r = ed.get("relation")
                if r == ArgumentRelationType.ASSERTS.value:
                    asserters.append(u)
                elif r == ArgumentRelationType.DISPUTES.value:
                    disputers.append(u)
                elif r == ArgumentRelationType.SUPPORTS.value:
                    supporters.append(u)
                elif r == ArgumentRelationType.CONTRADICTS.value:
                    contradictors.append(u)

            if asserters:
                lines.append("  - **Quem afirma:** " + "; ".join(_clip(_name(a), 80) for a in asserters[:5]))
            if disputers:
                lines.append("  - **Quem contesta:** " + "; ".join(_clip(_name(a), 80) for a in disputers[:5]))

            if supporters:
                lines.append("  - **Evidências a favor:** " + "; ".join(_clip(_name(e), 90) for e in supporters[:6]))
            if contradictors:
                lines.append("  - **Evidências contra:** " + "; ".join(_clip(_name(e), 90) for e in contradictors[:6]))

            lines.append("")  # espaçamento

        return "\n".join(lines).strip() + "\n"

    def build_debate_context_from_query(self, graph, query: str, hops: int = 2) -> str:
        seeds = self.resolve_query_seeds(graph, query)
        return self.build_debate_context(graph, seeds, hops=hops)


# Singleton padrão
ARGUMENT_PACK = ArgumentPack()
