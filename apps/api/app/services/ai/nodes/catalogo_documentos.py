"""
catalogo_documentos.py
Catalogo base de templates + checklists para documentos juridicos (BR).

Este catalogo serve como fonte de verdade para:
- estrutura de secoes (outline base)
- regras de numeracao/estilo
- checklist estruturado por genero
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional, Tuple, Union


DocKind = Literal[
    "PLEADING",           # peticoes/manifestacoes das partes
    "APPEAL",             # recursos
    "JUDICIAL_DECISION",  # decisoes/julgados
    "OFFICIAL",           # oficios/comunicacoes oficiais
    "EXTRAJUDICIAL",      # notificacoes extrajudiciais
    "LEGAL_NOTE",         # nota juridica/parecer/memo
    "NOTARIAL",           # escrituras, atas, etc.
    "CONTRACT",           # contratos
]

Numbering = Literal[
    "ROMAN",        # I, II, III...
    "ARABIC",       # 1, 2, 3...
    "CLAUSE",       # CLAUSULA 1, 1.1...
    "NONE",         # sem numeracao rigida
]

Tone = Literal["very_formal", "formal", "neutral", "executive"]
Verbosity = Literal["short", "medium", "long"]
Voice = Literal["first_person", "third_person", "impersonal"]


@dataclass(frozen=True)
class ChecklistItem:
    id: str
    kind: Literal["required", "recommended", "conditional", "forbidden"]
    check: Literal[
        "has_section",
        "has_any_phrase",
        "mentions_any",
        "has_field",
        "forbidden_phrase_any",
        "structure_min_sections",
    ]
    value: Union[str, List[str]]
    note: str = ""


@dataclass(frozen=True)
class TemplateSpec:
    name: str
    doc_kind: DocKind
    doc_subtype: str
    numbering: Numbering = "ROMAN"
    style: Dict[str, object] = field(default_factory=dict)
    sections: List[str] = field(default_factory=list)
    required_fields: List[str] = field(default_factory=list)
    checklist_base: List[ChecklistItem] = field(default_factory=list)
    forbidden_sections: List[str] = field(default_factory=list)


# ---------------------------
# Helpers de construcao
# ---------------------------

def _style(tone: Tone = "formal", verbosity: Verbosity = "medium", voice: Voice = "third_person") -> Dict[str, object]:
    return {"tone": tone, "verbosity": verbosity, "voice": voice, "avoid": ["excessive_adjectives", "fake_citations"]}


def _core_fields_process() -> List[str]:
    return ["processo", "juizo_ou_orgao", "partes", "cidade", "data"]


def _core_fields_office() -> List[str]:
    return ["numero_oficio", "orgao_emitente", "destinatario", "assunto", "referencia", "cidade", "data"]


def _core_fields_notarial() -> List[str]:
    return ["tabelionato", "livro_folha", "cidade", "data", "qualificacao_partes"]


def _ck_required_section(doc: str, section: str) -> ChecklistItem:
    return ChecklistItem(
        id=f"{doc}::sec::{section.lower().replace(' ', '_')}",
        kind="required",
        check="has_section",
        value=section,
        note=f"Deve conter a secao: {section}",
    )


def _ck_required_field(doc: str, fieldname: str) -> ChecklistItem:
    return ChecklistItem(
        id=f"{doc}::field::{fieldname}",
        kind="required",
        check="has_field",
        value=fieldname,
        note=f"Campo obrigatorio: {fieldname}",
    )


def _ck_forbid_phrases(doc: str, phrases: List[str], note: str) -> ChecklistItem:
    return ChecklistItem(
        id=f"{doc}::forbidden::phrases",
        kind="forbidden",
        check="forbidden_phrase_any",
        value=phrases,
        note=note,
    )


# ---------------------------
# Catalogo (curto, mas completo)
# ---------------------------

DOC_CATALOG: Dict[Tuple[DocKind, str], TemplateSpec] = {}


def register(spec: TemplateSpec) -> None:
    DOC_CATALOG[(spec.doc_kind, spec.doc_subtype)] = spec


# ===============
# 1) PETICOES / MANIFESTACOES
# ===============

register(TemplateSpec(
    name="Peticao inicial (CPC) - base",
    doc_kind="PLEADING",
    doc_subtype="PETICAO_INICIAL",
    numbering="ROMAN",
    style=_style("formal", "long", "third_person"),
    sections=[
        "Enderecamento e qualificacao",
        "Sintese fatica",
        "Do direito",
        "Da tutela de urgencia (se aplicavel)",
        "Das provas / documentos",
        "Dos pedidos",
        "Valor da causa (se aplicavel)",
        "Requerimentos finais",
    ],
    required_fields=_core_fields_process(),
    checklist_base=[
        _ck_required_section("pi", "Sintese fatica"),
        _ck_required_section("pi", "Do direito"),
        _ck_required_section("pi", "Dos pedidos"),
        ChecklistItem(
            id="pi::recommended::fundamento_legal",
            kind="recommended",
            check="mentions_any",
            value=["CPC", "art.", "Constituicao", "Codigo Civil"],
            note="Recomendavel citar fundamentos legais pertinentes.",
        ),
        _ck_forbid_phrases(
            "pi",
            ["conforme jurisprudencia pacifica do STJ no REsp XXXXX", "decidiu o STF no RE XXXXX"],
            note="Evitar referencias a julgados sem identificacao verificavel (placeholder 'XXXXX').",
        ),
    ],
))

register(TemplateSpec(
    name="Contestacao (CPC) - base",
    doc_kind="PLEADING",
    doc_subtype="CONTESTACAO",
    numbering="ROMAN",
    style=_style("formal", "long", "third_person"),
    sections=[
        "Enderecamento e identificacao",
        "Preliminares (se houver)",
        "Impugnacao especifica dos fatos",
        "Do merito",
        "Das provas / documentos",
        "Dos pedidos (improcedencia etc.)",
        "Requerimentos finais",
    ],
    required_fields=_core_fields_process(),
    checklist_base=[
        _ck_required_section("contest", "Do merito"),
        _ck_required_section("contest", "Dos pedidos (improcedencia etc.)"),
        ChecklistItem(
            id="contest::recommended::impugnacao_especifica",
            kind="recommended",
            check="mentions_any",
            value=["impugna", "especificamente", "nao corresponde a verdade"],
            note="Recomendavel impugnar fatos de forma especifica.",
        ),
    ],
))

register(TemplateSpec(
    name="Manifestacao / Peticao intermediaria - base",
    doc_kind="PLEADING",
    doc_subtype="MANIFESTACAO",
    numbering="ROMAN",
    style=_style("formal", "medium", "third_person"),
    sections=[
        "Enderecamento e identificacao",
        "Contexto e objetivo da manifestacao",
        "Exposicao objetiva dos fatos pertinentes",
        "Fundamentacao",
        "Pedidos / requerimentos",
    ],
    required_fields=_core_fields_process(),
    checklist_base=[
        _ck_required_section("manif", "Pedidos / requerimentos"),
    ],
))

register(TemplateSpec(
    name="Mandado de Seguranca - base",
    doc_kind="PLEADING",
    doc_subtype="MANDADO_SEGURANCA",
    numbering="ROMAN",
    style=_style("formal", "long", "third_person"),
    sections=[
        "Enderecamento e qualificacao",
        "Cabimento e tempestividade",
        "Fatos e direito liquido e certo",
        "Fundamentacao juridica",
        "Pedido liminar (se aplicavel)",
        "Pedidos",
        "Provas / documentos",
        "Requerimentos finais",
    ],
    required_fields=_core_fields_process(),
    checklist_base=[
        _ck_required_section("ms", "Cabimento e tempestividade"),
        _ck_required_section("ms", "Pedidos"),
    ],
))

register(TemplateSpec(
    name="Habeas Corpus - base",
    doc_kind="PLEADING",
    doc_subtype="HABEAS_CORPUS",
    numbering="ROMAN",
    style=_style("formal", "long", "third_person"),
    sections=[
        "Enderecamento e identificacao",
        "Autoridade coatora e paciente",
        "Sintese fatico-processual",
        "Constrangimento ilegal",
        "Fundamentos juridicos",
        "Pedido liminar (se aplicavel)",
        "Pedido",
        "Provas / documentos",
    ],
    required_fields=_core_fields_process(),
    checklist_base=[
        _ck_required_section("hc", "Constrangimento ilegal"),
        _ck_required_section("hc", "Pedido"),
    ],
))

register(TemplateSpec(
    name="Reclamacao Trabalhista - base",
    doc_kind="PLEADING",
    doc_subtype="RECLAMACAO_TRABALHISTA",
    numbering="ROMAN",
    style=_style("formal", "long", "third_person"),
    sections=[
        "Enderecamento e qualificacao",
        "Resumo do contrato de trabalho",
        "Fatos e fundamentos",
        "Pedidos",
        "Valor da causa",
        "Provas / documentos",
        "Requerimentos finais",
    ],
    required_fields=_core_fields_process(),
    checklist_base=[
        _ck_required_section("rt", "Pedidos"),
        _ck_required_section("rt", "Valor da causa"),
    ],
))

register(TemplateSpec(
    name="Divorcio consensual - base",
    doc_kind="PLEADING",
    doc_subtype="DIVORCIO",
    numbering="ROMAN",
    style=_style("formal", "medium", "third_person"),
    sections=[
        "Enderecamento e qualificacao",
        "Dos fatos",
        "Do acordo e partilha",
        "Dos filhos e alimentos (se aplicavel)",
        "Pedidos",
        "Requerimentos finais",
    ],
    required_fields=_core_fields_process(),
    checklist_base=[
        _ck_required_section("div", "Do acordo e partilha"),
        _ck_required_section("div", "Pedidos"),
    ],
))


# ===============
# 2) RECURSOS (mais comuns)
# ===============

register(TemplateSpec(
    name="Recurso (generico) - base",
    doc_kind="APPEAL",
    doc_subtype="RECURSO",
    numbering="ROMAN",
    style=_style("formal", "long", "third_person"),
    sections=[
        "Enderecamento e identificacao",
        "Tempestividade e preparo",
        "Cabimento e interesse recursal",
        "Sintese do caso e da decisao recorrida",
        "Razoes recursais",
        "Pedidos recursais",
        "Requerimentos finais",
    ],
    required_fields=_core_fields_process() + ["tribunal"],
    checklist_base=[
        _ck_required_section("rec", "Tempestividade e preparo"),
        _ck_required_section("rec", "Razoes recursais"),
        _ck_required_section("rec", "Pedidos recursais"),
    ],
))

register(TemplateSpec(
    name="Apelacao (CPC) - base",
    doc_kind="APPEAL",
    doc_subtype="APELACAO",
    numbering="ROMAN",
    style=_style("formal", "long", "third_person"),
    sections=[
        "Enderecamento e identificacao",
        "Tempestividade e preparo",
        "Cabimento e interesse recursal",
        "Sintese do caso e da sentenca recorrida",
        "Razoes recursais",
        "Pedidos recursais",
        "Requerimentos finais",
    ],
    required_fields=_core_fields_process() + ["tribunal"],
    checklist_base=[
        _ck_required_section("apel", "Tempestividade e preparo"),
        _ck_required_section("apel", "Razoes recursais"),
        _ck_required_section("apel", "Pedidos recursais"),
    ],
))

register(TemplateSpec(
    name="Agravo de instrumento (CPC) - base",
    doc_kind="APPEAL",
    doc_subtype="AGRAVO_INSTRUMENTO",
    numbering="ROMAN",
    style=_style("formal", "long", "third_person"),
    sections=[
        "Enderecamento e identificacao",
        "Tempestividade e preparo",
        "Cabimento (hipotese do art. 1.015 do CPC, quando aplicavel)",
        "Sintese da decisao agravada",
        "Razoes do agravo",
        "Pedido de efeito suspensivo/ativo (se aplicavel)",
        "Pedidos recursais",
        "Pecas obrigatorias e facultativas (rol/anexo)",
    ],
    required_fields=_core_fields_process() + ["tribunal", "decisao_agravada"],
    checklist_base=[
        _ck_required_section("ai", "Sintese da decisao agravada"),
        _ck_required_section("ai", "Pedidos recursais"),
        ChecklistItem(
            id="ai::recommended::efeito_suspensivo",
            kind="recommended",
            check="mentions_any",
            value=["efeito suspensivo", "atribuicao de efeito"],
            note="Se relevante, avaliar pedido de efeito suspensivo/ativo.",
        ),
    ],
))

register(TemplateSpec(
    name="Agravo interno (CPC) - base",
    doc_kind="APPEAL",
    doc_subtype="AGRAVO_INTERNO",
    numbering="ROMAN",
    style=_style("formal", "medium", "third_person"),
    sections=[
        "Enderecamento e identificacao",
        "Tempestividade",
        "Sintese da decisao monocratica agravada",
        "Razoes do agravo interno (impugnacao especifica)",
        "Pedido recursal",
    ],
    required_fields=_core_fields_process() + ["tribunal", "decisao_monocratica"],
    checklist_base=[
        _ck_required_section("aii", "Razoes do agravo interno (impugnacao especifica)"),
        ChecklistItem(
            id="aii::recommended::impugnacao_especifica",
            kind="recommended",
            check="mentions_any",
            value=["impugna", "especificamente", "equivoco", "reconsideracao"],
            note="Recomendavel impugnar de forma especifica os fundamentos da decisao monocratica.",
        ),
    ],
))

register(TemplateSpec(
    name="Embargos de declaracao - base",
    doc_kind="APPEAL",
    doc_subtype="EMBARGOS_DECLARACAO",
    numbering="ROMAN",
    style=_style("formal", "medium", "third_person"),
    sections=[
        "Enderecamento e identificacao",
        "Tempestividade",
        "Cabimento (omissao/contradicao/obscuridade/erro material)",
        "Pontos embargados (trecho + vicio + correcao pretendida)",
        "Pedido",
        "Prequestionamento (se aplicavel)",
    ],
    required_fields=_core_fields_process() + ["decisao_embargada"],
    checklist_base=[
        _ck_required_section("ed", "Cabimento (omissao/contradicao/obscuridade/erro material)"),
        _ck_required_section("ed", "Pontos embargados (trecho + vicio + correcao pretendida)"),
    ],
))

register(TemplateSpec(
    name="Recurso Especial (STJ) - base",
    doc_kind="APPEAL",
    doc_subtype="RESP",
    numbering="ROMAN",
    style=_style("very_formal", "long", "third_person"),
    sections=[
        "Enderecamento e identificacao",
        "Tempestividade e preparo",
        "Cabimento constitucional (art. 105, III)",
        "Questao federal e violacao de lei federal (demonstracao analitica)",
        "Prequestionamento",
        "Divergencia jurisprudencial (se aplicavel)",
        "Pedido",
        "Requerimentos finais",
    ],
    required_fields=_core_fields_process() + ["tribunal_origem", "acordao_recorrido"],
    checklist_base=[
        _ck_required_section("resp", "Cabimento constitucional (art. 105, III)"),
        _ck_required_section("resp", "Prequestionamento"),
        ChecklistItem(
            id="resp::recommended::demonstracao_analitica",
            kind="recommended",
            check="mentions_any",
            value=["demonstrar", "violacao", "art.", "lei federal"],
            note="Recomendavel demonstrar analiticamente a violacao de lei federal.",
        ),
    ],
))

register(TemplateSpec(
    name="Recurso Extraordinario (STF) - base",
    doc_kind="APPEAL",
    doc_subtype="RE",
    numbering="ROMAN",
    style=_style("very_formal", "long", "third_person"),
    sections=[
        "Enderecamento e identificacao",
        "Tempestividade e preparo",
        "Cabimento constitucional (art. 102, III)",
        "Questao constitucional (demonstracao analitica)",
        "Repercussao geral",
        "Prequestionamento",
        "Pedido",
        "Requerimentos finais",
    ],
    required_fields=_core_fields_process() + ["tribunal_origem", "acordao_recorrido"],
    checklist_base=[
        _ck_required_section("re", "Repercussao geral"),
        _ck_required_section("re", "Questao constitucional (demonstracao analitica)"),
    ],
))


# ===============
# 3) DECISOES JUDICIAIS (sentenca, interlocutoria, voto, acordao)
# ===============

register(TemplateSpec(
    name="Decisao interlocutoria - base",
    doc_kind="JUDICIAL_DECISION",
    doc_subtype="INTERLOCUTORIA",
    numbering="ARABIC",
    style=_style("formal", "medium", "impersonal"),
    sections=[
        "Relatorio sintetico (contexto)",
        "Fundamentacao (pontos decididos)",
        "Dispositivo (determinacoes)",
        "Intimacoes e prazos",
    ],
    required_fields=["processo", "juizo_ou_orgao", "data"],
    checklist_base=[
        _ck_required_section("interloc", "Dispositivo (determinacoes)"),
        ChecklistItem(
            id="interloc::forbidden::tom_partes",
            kind="forbidden",
            check="forbidden_phrase_any",
            value=["requer-se", "pede deferimento"],
            note="Evitar linguagem tipica das partes em decisao judicial.",
        ),
    ],
))

register(TemplateSpec(
    name="Sentenca - base",
    doc_kind="JUDICIAL_DECISION",
    doc_subtype="SENTENCA",
    numbering="ARABIC",
    style=_style("formal", "long", "impersonal"),
    sections=[
        "Relatorio",
        "Fundamentacao (preliminares e merito)",
        "Dispositivo",
        "Custas e honorarios (se aplicavel)",
        "Registro e intimacao",
    ],
    required_fields=["processo", "juizo_ou_orgao", "data", "partes"],
    checklist_base=[
        _ck_required_section("sent", "Fundamentacao (preliminares e merito)"),
        _ck_required_section("sent", "Dispositivo"),
        ChecklistItem(
            id="sent::recommended::honorarios",
            kind="recommended",
            check="mentions_any",
            value=["honorarios", "custas", "sucumbencia"],
            note="Quando aplicavel, tratar custas e honorarios.",
        ),
        ChecklistItem(
            id="sent::forbidden::linguagem_pedido",
            kind="forbidden",
            check="forbidden_phrase_any",
            value=["pede deferimento", "requer a Vossa Excelencia"],
            note="Evitar formulas tipicas de peticao em sentenca.",
        ),
    ],
))

register(TemplateSpec(
    name="Voto (Relator) - base",
    doc_kind="JUDICIAL_DECISION",
    doc_subtype="VOTO",
    numbering="ARABIC",
    style=_style("formal", "long", "impersonal"),
    sections=[
        "Relatorio",
        "Voto (fundamentacao)",
        "Conclusao (dou/nego provimento etc.)",
    ],
    required_fields=["processo", "tribunal", "data", "relator"],
    checklist_base=[
        _ck_required_section("voto", "Conclusao (dou/nego provimento etc.)"),
    ],
))

register(TemplateSpec(
    name="Acordao - base",
    doc_kind="JUDICIAL_DECISION",
    doc_subtype="ACORDAO",
    numbering="NONE",
    style=_style("formal", "long", "impersonal"),
    sections=[
        "Ementa",
        "Acordao (resultado do julgamento)",
        "Relatorio",
        "Voto do Relator",
        "Voto(s) / divergencia (se houver)",
        "Dispositivo e proclamacao do resultado",
    ],
    required_fields=["processo", "tribunal", "data", "orgao_julgador"],
    checklist_base=[
        _ck_required_section("acord", "Ementa"),
        _ck_required_section("acord", "Dispositivo e proclamacao do resultado"),
    ],
))


# ===============
# 4) OFICIOS / NOTIFICACOES
# ===============

register(TemplateSpec(
    name="Oficio - base",
    doc_kind="OFFICIAL",
    doc_subtype="OFICIO",
    numbering="NONE",
    style=_style("formal", "short", "impersonal"),
    sections=[
        "Cabecalho (n/ano - orgao emitente)",
        "Destinatario",
        "Assunto e referencia",
        "Corpo (solicitacao/encaminhamento)",
        "Prazo (se houver)",
        "Anexos",
        "Fecho e assinatura",
    ],
    required_fields=_core_fields_office(),
    checklist_base=[
        _ck_required_section("of", "Assunto e referencia"),
        _ck_required_section("of", "Corpo (solicitacao/encaminhamento)"),
    ],
))

register(TemplateSpec(
    name="Notificacao extrajudicial - base",
    doc_kind="EXTRAJUDICIAL",
    doc_subtype="NOTIFICACAO_EXTRAJUDICIAL",
    numbering="ARABIC",
    style=_style("formal", "medium", "third_person"),
    sections=[
        "Identificacao das partes",
        "Exposicao dos fatos",
        "Fundamento (contratual/legal)",
        "Exigencia (obrigacao) e prazo",
        "Consequencias do descumprimento",
        "Forma de resposta e endereco para contato",
        "Fecho e assinatura",
    ],
    required_fields=["notificante", "notificado", "endereco_notificado", "cidade", "data"],
    checklist_base=[
        _ck_required_section("not", "Exigencia (obrigacao) e prazo"),
        _ck_required_section("not", "Consequencias do descumprimento"),
    ],
))


# ===============
# 5) NOTA JURIDICA / PARECER
# ===============

register(TemplateSpec(
    name="Nota juridica / Memorando - base",
    doc_kind="LEGAL_NOTE",
    doc_subtype="NOTA_JURIDICA",
    numbering="ARABIC",
    style=_style("neutral", "medium", "third_person"),
    sections=[
        "Demanda (contexto) e objetivo",
        "Base documental analisada",
        "Enquadramento juridico",
        "Analise (por topicos)",
        "Riscos e alternativas",
        "Conclusao executiva (opiniao)",
        "Recomendacoes e proximos passos",
    ],
    required_fields=["solicitante", "assunto", "cidade", "data"],
    checklist_base=[
        _ck_required_section("nota", "Base documental analisada"),
        _ck_required_section("nota", "Conclusao executiva (opiniao)"),
        ChecklistItem(
            id="nota::forbidden::pedidos_processuais",
            kind="forbidden",
            check="forbidden_phrase_any",
            value=["pede deferimento", "requer a Vossa Excelencia", "valor da causa"],
            note="Evitar formulas processuais tipicas em nota/parecer.",
        ),
    ],
))

register(TemplateSpec(
    name="Nota tecnica - base",
    doc_kind="LEGAL_NOTE",
    doc_subtype="NOTA_TECNICA",
    numbering="ARABIC",
    style=_style("neutral", "medium", "third_person"),
    sections=[
        "Identificacao",
        "Contexto e objetivo",
        "Analise tecnica",
        "Fundamentacao",
        "Conclusao",
        "Recomendacoes",
    ],
    required_fields=["solicitante", "assunto", "cidade", "data"],
    checklist_base=[
        _ck_required_section("nt", "Analise tecnica"),
        _ck_required_section("nt", "Conclusao"),
    ],
))

register(TemplateSpec(
    name="Parecer juridico - base",
    doc_kind="LEGAL_NOTE",
    doc_subtype="PARECER",
    numbering="ARABIC",
    style=_style("formal", "long", "third_person"),
    sections=[
        "Ementa (opcional)",
        "Quesitos / questao apresentada",
        "Fatos relevantes e premissas",
        "Fundamentacao (normas, precedentes, doutrina quando aplicavel)",
        "Analise e resposta aos quesitos",
        "Riscos, limitacoes e alternativas",
        "Conclusao (opiniao)",
    ],
    required_fields=["solicitante", "quesitos", "cidade", "data"],
    checklist_base=[
        _ck_required_section("par", "Quesitos / questao apresentada"),
        _ck_required_section("par", "Conclusao (opiniao)"),
    ],
))


# ===============
# 6) ESCRITURAS / PROCURACOES
# ===============

register(TemplateSpec(
    name="Escritura publica (generica) - base",
    doc_kind="NOTARIAL",
    doc_subtype="ESCRITURA_PUBLICA",
    numbering="NONE",
    style=_style("very_formal", "long", "impersonal"),
    sections=[
        "Abertura (tabelionato, livro/folha, data/local)",
        "Qualificacao das partes",
        "Capacidade e representacao",
        "Declaracoes e vontade das partes",
        "Objeto do ato (descricao detalhada)",
        "Clausulas especificas (condicoes, encargos, etc.)",
        "Tributos, emolumentos e responsabilidades",
        "Leitura, aceitacao e assinaturas",
        "Fe publica",
    ],
    required_fields=_core_fields_notarial() + ["ato_tipo", "objeto"],
    checklist_base=[
        _ck_required_section("esc", "Qualificacao das partes"),
        _ck_required_section("esc", "Objeto do ato (descricao detalhada)"),
        ChecklistItem(
            id="esc::forbidden::inventar_dados",
            kind="forbidden",
            check="forbidden_phrase_any",
            value=["CPF: 000.000.000-00", "CNPJ: 00.000.000/0000-00", "matricula n XXXXX"],
            note="Evitar placeholders que aparentem dados reais; exigir dados fornecidos ou marcar como pendente.",
        ),
    ],
))

register(TemplateSpec(
    name="Procuracao (publica ou particular) - base",
    doc_kind="NOTARIAL",
    doc_subtype="PROCURACAO",
    numbering="ARABIC",
    style=_style("very_formal", "medium", "impersonal"),
    sections=[
        "Identificacao do instrumento",
        "Qualificacao do outorgante",
        "Qualificacao do outorgado",
        "Poderes outorgados (gerais e/ou especificos)",
        "Limites, prazo e condicoes",
        "Substabelecimento (se permitido)",
        "Fecho e assinaturas",
    ],
    required_fields=_core_fields_notarial() + ["outorgante", "outorgado", "poderes"],
    checklist_base=[
        _ck_required_section("proc", "Poderes outorgados (gerais e/ou especificos)"),
        ChecklistItem(
            id="proc::recommended::poderes_especificos",
            kind="recommended",
            check="mentions_any",
            value=["poderes especificos", "alienar", "transigir", "receber e dar quitacao"],
            note="Se necessario, detalhar poderes especificos (alienar, transigir, etc.).",
        ),
    ],
))


# ===============
# 7) CONTRATOS
# ===============

register(TemplateSpec(
    name="Contrato (generico) - base",
    doc_kind="CONTRACT",
    doc_subtype="CONTRATO",
    numbering="CLAUSE",
    style=_style("formal", "medium", "third_person"),
    sections=[
        "Partes",
        "Definicoes",
        "Objeto",
        "Obrigacoes das partes",
        "Preco e forma de pagamento",
        "Prazo e vigencia",
        "Rescisao",
        "Responsabilidade e garantias",
        "Protecao de dados (LGPD)",
        "Foro e solucao de controversias",
        "Disposicoes gerais",
        "Assinaturas e anexos",
    ],
    required_fields=["partes", "objeto", "preco", "prazo", "foro"],
    checklist_base=[
        _ck_required_section("contr", "Objeto"),
        _ck_required_section("contr", "Preco e forma de pagamento"),
        _ck_required_section("contr", "Prazo e vigencia"),
        _ck_required_section("contr", "Foro e solucao de controversias"),
    ],
))


# ---------------------------
# API minima para consumo
# ---------------------------

def get_template(doc_kind: DocKind, doc_subtype: str) -> Optional[TemplateSpec]:
    """Retorna o template base (sistema) para o genero/subtipo."""
    return DOC_CATALOG.get((doc_kind, doc_subtype))


def list_templates(doc_kind: Optional[DocKind] = None) -> List[TemplateSpec]:
    """Lista templates do catalogo; filtra por doc_kind se informado."""
    items = list(DOC_CATALOG.values())
    if doc_kind:
        items = [t for t in items if t.doc_kind == doc_kind]
    return sorted(items, key=lambda t: (t.doc_kind, t.doc_subtype, t.name))


def list_doc_kinds() -> Dict[str, List[str]]:
    mapping: Dict[str, List[str]] = {}
    for (kind, subtype), spec in DOC_CATALOG.items():
        mapping.setdefault(kind, []).append(subtype)
        if spec.doc_subtype not in mapping[kind]:
            mapping[kind].append(spec.doc_subtype)
    for kind in mapping:
        mapping[kind] = sorted(set(mapping[kind]))
    return dict(sorted(mapping.items(), key=lambda item: item[0]))


def _subtype_index() -> Dict[str, DocKind]:
    idx: Dict[str, DocKind] = {}
    for (kind, subtype) in DOC_CATALOG:
        key = (subtype or "").strip().lower()
        if key and key not in idx:
            idx[key] = kind
    return idx


def infer_doc_kind_subtype(document_type: Optional[str]) -> Tuple[Optional[DocKind], Optional[str]]:
    if not document_type:
        return None, None
    normalized = document_type.strip()
    lower = normalized.lower()
    index = _subtype_index()
    if lower in index:
        return index[lower], normalized
    # Allow doc_kind to be passed as document_type
    upper = normalized.upper()
    for kind in DOC_CATALOG.keys():
        if upper == kind[0]:
            return kind[0], None
    return None, normalized


def get_numbering_instruction(numbering: Numbering) -> str:
    if numbering == "ROMAN":
        return "Use numeracao romana (I, II, III...) para secoes principais."
    if numbering == "ARABIC":
        return "Use numeracao arabica (1, 2, 3...) para secoes principais."
    if numbering == "CLAUSE":
        return "Use numeracao por clausulas (CLAUSULA 1, 1.1...)."
    return "Nao force numeracao rigida nas secoes."


def get_structure_hint(doc_kind: Optional[str], doc_subtype: Optional[str]) -> str:
    kind = (doc_kind or "").upper()
    subtype = (doc_subtype or "").upper()
    if kind == "PLEADING":
        return "Ordem logica: fatos -> preliminares -> merito -> pedidos."
    if kind == "APPEAL":
        return "Ordem logica: cabimento/tempestividade -> razoes -> pedidos recursais."
    if kind == "JUDICIAL_DECISION":
        return "Ordem logica: relatorio -> fundamentacao -> dispositivo."
    if kind == "OFFICIAL":
        return "Ordem logica: assunto -> referencia -> corpo -> fecho."
    if kind == "EXTRAJUDICIAL":
        return "Ordem logica: fatos -> fundamento -> exigencia/prazo -> consequencias."
    if kind == "LEGAL_NOTE":
        return "Ordem logica: contexto -> fundamentacao -> conclusao."
    if kind == "NOTARIAL":
        return "Ordem logica: qualificacao -> objeto -> clausulas -> assinaturas."
    if kind == "CONTRACT":
        return "Ordem logica: partes -> objeto -> obrigacoes -> preco -> prazo -> foro."
    if subtype:
        return f"Estruture o documento de forma adequada ao subtipo {subtype}."
    return ""


def _roman(n: int) -> str:
    vals = [
        (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
        (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
        (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
    ]
    result = []
    for val, sym in vals:
        while n >= val:
            result.append(sym)
            n -= val
    return "".join(result) or "I"


def build_default_outline(spec: TemplateSpec) -> List[str]:
    if not spec.sections:
        return []
    outline: List[str] = []
    for idx, title in enumerate(spec.sections, start=1):
        if spec.numbering == "ROMAN":
            prefix = _roman(idx)
            outline.append(f"{prefix} - {title}")
        elif spec.numbering == "ARABIC":
            outline.append(f"{idx}. {title}")
        elif spec.numbering == "CLAUSE":
            outline.append(f"CLAUSULA {idx} - {title}")
        else:
            outline.append(title)
    return outline


def template_spec_to_dict(spec: TemplateSpec) -> Dict[str, object]:
    return {
        "name": spec.name,
        "doc_kind": spec.doc_kind,
        "doc_subtype": spec.doc_subtype,
        "numbering": spec.numbering,
        "style": spec.style,
        "sections": list(spec.sections),
        "required_fields": list(spec.required_fields),
        "forbidden_sections": list(spec.forbidden_sections),
        "checklist_base": [
            {
                "id": item.id,
                "kind": item.kind,
                "check": item.check,
                "value": item.value,
                "note": item.note,
            }
            for item in spec.checklist_base
        ],
    }


def merge_user_template(base: TemplateSpec, user: Dict[str, object]) -> TemplateSpec:
    """
    Merge simples (esqueleto):
    - sections: se user tiver, substitui; senao mantem
    - numbering/style/required_fields: sobrescreve se user trouxer
    - checklist_base: concatena (base + user_items)
    """
    def _coerce_sections(raw: object) -> List[str]:
        output: List[str] = []
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, str):
                    title = item.strip()
                elif isinstance(item, dict):
                    title = str(item.get("title") or item.get("name") or "").strip()
                else:
                    title = ""
                if title:
                    output.append(title)
        elif isinstance(raw, str):
            for line in raw.splitlines():
                title = line.strip()
                if title:
                    output.append(title)
        return output

    def _coerce_fields(raw: object) -> List[str]:
        output: List[str] = []
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, str):
                    name = item.strip()
                elif isinstance(item, dict):
                    name = str(item.get("name") or item.get("field") or "").strip()
                else:
                    name = ""
                if name:
                    output.append(name)
        elif isinstance(raw, str):
            for line in raw.splitlines():
                name = line.strip()
                if name:
                    output.append(name)
        return output

    format_raw = user.get("format")
    if hasattr(format_raw, "model_dump"):
        format_data = format_raw.model_dump()  # type: ignore[assignment]
    else:
        format_data = format_raw if isinstance(format_raw, dict) else {}
    numbering = user.get("numbering") or format_data.get("numbering") or base.numbering
    style = {**base.style}
    for key in ("tone", "verbosity", "voice"):
        val = format_data.get(key)
        if val:
            style[key] = val
    if isinstance(user.get("style"), dict):
        style.update(user.get("style") or {})

    section_list = _coerce_sections(user.get("sections"))
    sections = section_list or list(base.sections)

    field_list = _coerce_fields(user.get("required_fields"))
    required_fields = list(dict.fromkeys(base.required_fields + field_list))

    user_ck: List[ChecklistItem] = []
    checklist_data = user.get("checklist_items") or user.get("checklist") or []
    if isinstance(checklist_data, list):
        for raw in checklist_data:
            if isinstance(raw, ChecklistItem):
                user_ck.append(raw)
                continue
            if not isinstance(raw, dict):
                continue
            kind = raw.get("kind") or raw.get("level") or "required"
            check = raw.get("check") or raw.get("rule") or "has_section"
            value = raw.get("value") if raw.get("value") is not None else ""
            note = raw.get("note") or ""
            item_id = raw.get("id") or f"user_check_{len(user_ck) + 1}"
            try:
                user_ck.append(ChecklistItem(
                    id=str(item_id),
                    kind=kind,
                    check=check,
                    value=value,
                    note=str(note or ""),
                ))
            except Exception:
                continue

    return TemplateSpec(
        name=str(user.get("name") or base.name),
        doc_kind=base.doc_kind,
        doc_subtype=base.doc_subtype,
        numbering=numbering,  # type: ignore[assignment]
        style=style,
        sections=list(sections) if sections else [],
        required_fields=required_fields,
        checklist_base=base.checklist_base + user_ck,
        forbidden_sections=list(user.get("forbidden_sections") or base.forbidden_sections),
    )


def evaluate_structured_checklist(
    document_text: str,
    items: List[ChecklistItem],
) -> Dict[str, List[Dict[str, object]]]:
    """
    Avalia checklist estruturado contra o texto do documento.
    Retorna items com status + listas de missing_critical / missing_noncritical.
    """
    text_lower = (document_text or "").lower()
    results: List[Dict[str, object]] = []

    def _has_phrase_any(values: List[str]) -> bool:
        return any(v.lower() in text_lower for v in values if isinstance(v, str) and v)

    for item in items:
        value = item.value
        status = "present"
        notes = item.note or ""

        if item.check in ("has_section", "has_any_phrase", "mentions_any"):
            values = [value] if isinstance(value, str) else list(value or [])
            if not _has_phrase_any(values):
                status = "missing"
        elif item.check == "has_field":
            # Heuristica simples: campo deve aparecer no texto
            field = str(value) if isinstance(value, str) else ""
            if field and field.lower() not in text_lower:
                status = "missing"
        elif item.check == "forbidden_phrase_any":
            values = [value] if isinstance(value, str) else list(value or [])
            if _has_phrase_any(values):
                status = "missing"
                notes = (notes + " (conteudo proibido detectado)").strip()
        elif item.check == "structure_min_sections":
            try:
                min_sections = int(value) if isinstance(value, (int, str)) else 0
            except (TypeError, ValueError):
                min_sections = 0
            if min_sections and document_text.count("\n## ") < min_sections:
                status = "missing"

        results.append({
            "id": item.id,
            "label": item.id,
            "status": status,
            "critical": item.kind in ("required", "conditional", "forbidden"),
            "evidence": "",
            "notes": notes,
        })

    missing_critical = [r for r in results if r["status"] != "present" and r.get("critical")]
    missing_noncritical = [r for r in results if r["status"] != "present" and not r.get("critical")]
    return {
        "items": results,
        "missing_critical": missing_critical,
        "missing_noncritical": missing_noncritical,
    }
