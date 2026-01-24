# legal_pack.py
# Pack do domínio jurídico: doutrina + jurisprudência + normas.
# Ideia: core genérico chama:
#   pack.seed_from_metadata(chunk.metadata)
#   pack.extract_candidates(text)
#   pack.extract_relations(text, source_node_id)

from __future__ import annotations

import re
import unicodedata
import hashlib
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


# ----------------------------
# Helpers
# ----------------------------

def _norm(s: str) -> str:
    s = (s or "").strip()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _slug(s: str, max_len: int = 60) -> str:
    s = _norm(s).lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s[:max_len] if len(s) > max_len else s


def _stable_id(*parts: str) -> str:
    # id curto e estável (bom para não estourar node_id)
    raw = "|".join(_norm(p) for p in parts if p)
    h = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return h


# ----------------------------
# Schema do domínio
# ----------------------------

@dataclass(frozen=True)
class LegalSchema:
    # tipos de nó
    ENTITY_TYPES: Tuple[str, ...] = (
        "lei", "artigo", "sumula",
        "jurisprudencia",     # precedente/acórdão/decisão (classe+numero+tribunal)
        "tema", "tese",       # tema repetitivo/RG/IRDR + tese
        "autor", "obra",      # doutrina: autor e obra
        "conceito",           # opcional: conceitos dogmáticos (boa-fé, culpa, etc.)
    )

    # tipos de aresta (relação)
    RELATION_TYPES: Tuple[str, ...] = (
        "possui",             # lei -> artigo
        "cita",               # doc -> alvo citado
        "aplica",             # jurisprudência -> súmula/lei/artigo/tese
        "interpreta",         # jurisprudência/doutrina -> artigo/lei
        "fixa_tese",          # jurisprudência -> tese
        "vincula",            # tema/súmula -> tese
        "relacionada",        # tese <-> tese
        "distingue",          # jurisprudência -> jurisprudência/tese
        "supera",             # jurisprudência -> jurisprudência/tese
        "comenta",            # obra/doutrina -> lei/artigo/jurisprudência
        "defende",            # obra/autor -> tese/conceito
        "critica",            # obra/autor -> tese/conceito/juris
    )


SCHEMA = LegalSchema()


# ----------------------------
# Extractor (texto -> entidades/relacoes)
# ----------------------------

class LegalExtractor:
    """
    Extrator focado em PT-BR (padrões comuns).
    Importante: doutrina via regex é ruidosa; o melhor é usar metadados do chunk.
    """

    # NORMA
    PAT_LEI = re.compile(
        r"(?:Lei|Decreto|MP|Medida\s+Provis[oó]ria|LC|Lei\s+Complementar|Decreto-?Lei)\s*n?[º°]?\s*"
        r"([\d.]+)(?:/|\s+de\s+)(\d{2,4})",
        re.IGNORECASE
    )

    PAT_ARTIGO = re.compile(
        r"(?:Art|Artigo)\.?\s*(\d+)[º°]?"
        r"(?:\s*,?\s*§\s*(\d+)[º°]?)?",
        re.IGNORECASE
    )

    PAT_SUMULA = re.compile(
        r"S[úu]mula\s+(?:Vinculante\s+)?n?[º°]?\s*(\d+)\s*(?:do\s+)?(STF|STJ|TST|TSE|STM|STJ)?",
        re.IGNORECASE
    )

    # JURISPRUDÊNCIA (classes mais comuns + variações)
    PAT_JURIS = re.compile(
        r"\b(REsp|AREsp|RE|AgRg|AgInt|EDcl|ADI|ADC|ADPF|HC|MS|RMS|RO|AI|AP|Rcl)\s*"
        r"(?:n?[º°]?\s*)?([\d.]+)(?:/([A-Z]{2}))?\b",
        re.IGNORECASE
    )

    # TEMA / TESE
    PAT_TEMA = re.compile(r"\bTema\s*(?:n?[º°]?\s*)?(\d{1,5})\b", re.IGNORECASE)
    PAT_TESE_LABEL = re.compile(r"\b(Tese)\b\s*[:\-]\s*(.{20,200})", re.IGNORECASE)

    # DOUTRINA (heurística de referência bibliográfica ABNT-ish)
    # Ex.: "SILVA, José Afonso da. Curso de Direito Constitucional Positivo. 2023."
    PAT_REF_DOUTRINA = re.compile(
        r"\b([A-ZÁÀÂÃÉÈÊÍÌÎÓÒÔÕÚÙÛÇ]{3,})(?:,\s*([A-ZÁÀÂÃÉÈÊÍÌÎÓÒÔÕÚÙÛÇ][^.\n]{2,60}))?\.\s+([^.\n]{6,120})\.\s+(\d{4})\b",
        re.UNICODE
    )

    def extract_candidates(self, text: str) -> List[Tuple[str, str, str, Dict[str, Any]]]:
        """
        Retorna lista: (entity_type, entity_id, name, metadata)
        """
        t = text or ""
        out: List[Tuple[str, str, str, Dict[str, Any]]] = []

        # Leis / atos normativos
        for m in self.PAT_LEI.finditer(t):
            num = m.group(1).replace(".", "")
            ano_raw = m.group(2)
            # normaliza ano 2 dígitos (ex: 93 -> 1993) se você quiser:
            ano = int(ano_raw) if len(ano_raw) == 4 else (1900 + int(ano_raw))
            eid = f"{num}_{ano}"
            out.append(("lei", eid, f"Lei {num}/{ano}", {"numero": num, "ano": ano}))

        # Súmulas
        for m in self.PAT_SUMULA.finditer(t):
            num = m.group(1)
            trib = (m.group(2) or "STJ").upper()
            eid = f"{trib}_{num}"
            out.append(("sumula", eid, f"Súmula {num} {trib}", {"numero": num, "tribunal": trib}))

        # Jurisprudência
        for m in self.PAT_JURIS.finditer(t):
            classe = m.group(1).upper()
            num = m.group(2).replace(".", "")
            uf = (m.group(3) or "").upper()
            eid = f"{classe}_{num}_{uf}" if uf else f"{classe}_{num}"
            name = f"{classe} {num}" + (f"/{uf}" if uf else "")
            out.append(("jurisprudencia", eid, name, {"classe": classe, "numero": num, "uf": uf}))

        # Artigos (sem amarrar a uma lei específica — isso você pode inferir por metadados do chunk)
        for m in self.PAT_ARTIGO.finditer(t):
            art = m.group(1)
            par = m.group(2) or ""
            eid = f"art_{art}" + (f"_p{par}" if par else "")
            name = f"Art. {art}" + (f", § {par}" if par else "")
            out.append(("artigo", eid, name, {"artigo": art, "paragrafo": par}))

        # Tema
        for m in self.PAT_TEMA.finditer(t):
            num = m.group(1)
            eid = f"{num}"
            out.append(("tema", eid, f"Tema {num}", {"numero": num}))

        # Tese (heurística: “Tese: ...”)
        for m in self.PAT_TESE_LABEL.finditer(t):
            thesis = _norm(m.group(2))
            eid = _stable_id(thesis)
            out.append(("tese", eid, f"Tese: {thesis[:80]}", {"texto": thesis}))

        # Doutrina (heurística ABNT-ish; use com cautela)
        for m in self.PAT_REF_DOUTRINA.finditer(t):
            sobrenome = _norm(m.group(1))
            prenomes = _norm(m.group(2) or "")
            titulo = _norm(m.group(3))
            ano = int(m.group(4))
            autor_nome = f"{sobrenome}" + (f", {prenomes}" if prenomes else "")
            autor_id = _stable_id("autor", autor_nome)
            obra_id = _stable_id("obra", autor_nome, titulo, str(ano))

            out.append(("autor", autor_id, autor_nome, {"sobrenome": sobrenome, "prenomes": prenomes}))
            out.append(("obra", obra_id, titulo, {"autor": autor_nome, "ano": ano}))

        return out

    def extract_relations(
        self,
        text: str,
        source_node_id: str,
        created_or_matched_node_ids: Iterable[str],
    ) -> List[Tuple[str, str, str, Dict[str, Any]]]:
        """
        Retorna: (source_node_id, target_node_id, relation_type, metadata)
        Por padrão: tudo que aparece no texto vira 'cita' a partir do source.
        Regras mais específicas podem ser adicionadas (aplica/interpreta/fixa_tese etc.).
        """
        rels: List[Tuple[str, str, str, Dict[str, Any]]] = []
        for target in created_or_matched_node_ids:
            if target != source_node_id:
                rels.append((source_node_id, target, "cita", {}))
        return rels


# ----------------------------
# Seeds via METADADOS (doutrina/juris fica MUITO melhor aqui)
# ----------------------------

def seed_from_metadata(meta: Dict[str, Any]) -> List[Tuple[str, str, str, Dict[str, Any]]]:
    """
    Converte metadados de chunk em entidades “fortes” (pouco ruído).
    Recomendação: ao inserir chunks no seu vetor, inclua metadados padronizados.

    Exemplos:
      # Jurisprudência
      {
        "source_type": "jurisprudencia",
        "tribunal": "STJ",
        "classe": "REsp",
        "numero": "1234567",
        "uf": "SP",
        "relator": "Fulano",
        "data_julg": "2022-08-10",
        "orgao": "2ª Turma",
        "tema": "1061",        # opcional
        "tese": "...."         # opcional
      }

      # Doutrina
      {
        "source_type": "doutrina",
        "autor": "José Afonso da Silva",
        "obra": "Curso de Direito Constitucional Positivo",
        "ano": 2023,
        "edicao": "44",
        "capitulo": "Direitos Fundamentais",
        "secao": "....",
        "pag_ini": 123,
        "pag_fim": 130
      }
    """
    meta = meta or {}
    st = (meta.get("source_type") or meta.get("tipo") or "").lower().strip()
    out: List[Tuple[str, str, str, Dict[str, Any]]] = []

    if st in {"jurisprudencia", "jurisprudência", "acordao", "acórdão", "decisao", "decisão"}:
        tribunal = (meta.get("tribunal") or "").upper()
        classe = (meta.get("classe") or meta.get("tipo") or "").upper()
        numero = re.sub(r"\D", "", str(meta.get("numero") or ""))
        uf = (meta.get("uf") or "").upper()

        if classe and numero:
            eid = _stable_id("juris", tribunal, classe, numero, uf)
            name = f"{classe} {numero}" + (f"/{uf}" if uf else "")
            out.append(("jurisprudencia", eid, name, {
                "tribunal": tribunal,
                "classe": classe,
                "numero": numero,
                "uf": uf,
                "relator": meta.get("relator"),
                "data_julg": meta.get("data_julg"),
                "orgao": meta.get("orgao"),
            }))

        # Tema e tese, se vierem prontos
        if meta.get("tema"):
            tema_num = str(meta["tema"]).strip()
            out.append(("tema", tema_num, f"Tema {tema_num}", {"numero": tema_num, "tribunal": tribunal}))
        if meta.get("tese"):
            thesis = _norm(str(meta["tese"]))
            tid = _stable_id(thesis)
            out.append(("tese", tid, f"Tese: {thesis[:80]}", {"texto": thesis, "tribunal": tribunal}))

    if st in {"doutrina", "livro", "artigo_doutrinario", "artigo"}:
        autor = _norm(str(meta.get("autor") or ""))
        obra = _norm(str(meta.get("obra") or meta.get("titulo") or ""))
        ano = meta.get("ano")

        if autor:
            aid = _stable_id("autor", autor)
            out.append(("autor", aid, autor, {}))
        if obra:
            oid = _stable_id("obra", autor, obra, str(ano or ""))
            md = {"autor": autor}
            if ano:
                md["ano"] = int(ano) if str(ano).isdigit() else ano
            for k in ("edicao", "capitulo", "secao", "pag_ini", "pag_fim", "editora"):
                if meta.get(k) is not None:
                    md[k] = meta.get(k)
            out.append(("obra", oid, obra, md))

    return out


# ----------------------------
# Relações “fortes” via METADADOS
# ----------------------------

def strong_relations_from_metadata(
    meta: Dict[str, Any],
    source_node_id: str,
    resolved_node_ids: Dict[Tuple[str, str], str],
) -> List[Tuple[str, str, str, Dict[str, Any]]]:
    """
    resolved_node_ids: mapa (entity_type, entity_id) -> node_id real no grafo
    """
    meta = meta or {}
    st = (meta.get("source_type") or meta.get("tipo") or "").lower().strip()
    rels: List[Tuple[str, str, str, Dict[str, Any]]] = []

    # Se um chunk de jurisprudência trouxer "tema"/"tese", cria relações mais específicas
    if st in {"jurisprudencia", "jurisprudência", "acordao", "acórdão", "decisao", "decisão"}:
        tribunal = (meta.get("tribunal") or "").upper()

        if meta.get("tema"):
            tema_num = str(meta["tema"]).strip()
            tema_node = resolved_node_ids.get(("tema", tema_num))
            # se o seu grafo tiver nós de tema, dá para vincular com tese depois
            if tema_node:
                rels.append((source_node_id, tema_node, "cita", {"via": "metadata"}))

        if meta.get("tese"):
            thesis = _norm(str(meta["tese"]))
            tid = _stable_id(thesis)
            tese_node = resolved_node_ids.get(("tese", tid))
            if tese_node:
                rels.append((source_node_id, tese_node, "fixa_tese", {"tribunal": tribunal, "via": "metadata"}))

    # Doutrina defendendo/criticando uma tese/conceito (se você anotar isso nos metadados)
    if st in {"doutrina", "livro", "artigo_doutrinario", "artigo"}:
        stance = (meta.get("stance") or "").lower().strip()  # "defende" | "critica" | etc.
        alvo_tese = meta.get("tese_alvo")
        if stance in {"defende", "critica"} and alvo_tese:
            tid = _stable_id(_norm(str(alvo_tese)))
            tese_node = resolved_node_ids.get(("tese", tid))
            if tese_node:
                rels.append((source_node_id, tese_node, stance, {"via": "metadata"}))

    return rels


# ----------------------------
# Objeto pack (convenção)
# ----------------------------

@dataclass(frozen=True)
class LegalPack:
    name: str = "legal"
    schema: LegalSchema = SCHEMA
    extractor: LegalExtractor = LegalExtractor()

    def extract_candidates(self, text: str):
        return self.extractor.extract_candidates(text)

    def extract_relations(self, text: str, source_node_id: str, created_or_matched_node_ids: Iterable[str]):
        return self.extractor.extract_relations(text, source_node_id, created_or_matched_node_ids)

    def seed_from_metadata(self, meta: Dict[str, Any]):
        return seed_from_metadata(meta)

    def strong_relations_from_metadata(
        self,
        meta: Dict[str, Any],
        source_node_id: str,
        resolved_node_ids: Dict[Tuple[str, str], str],
    ):
        return strong_relations_from_metadata(meta, source_node_id, resolved_node_ids)


LEGAL_PACK = LegalPack()
