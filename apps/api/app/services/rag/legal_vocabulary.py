"""
Vocabulário Jurídico Brasileiro para Embeddings Especializados

Contém:
- Dicionário de abreviações jurídicas brasileiras (200+ termos)
- Sinônimos jurídicos agrupados
- Stopwords jurídicas (termos que não agregam significado semântico)
- Regex patterns para identificar citações (leis, jurisprudência, súmulas)
- Hierarquia normativa para ponderação de relevância
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Dict, FrozenSet, List, Pattern, Set, Tuple


# =============================================================================
# Abreviações Jurídicas Brasileiras (200+ termos)
# =============================================================================

LEGAL_ABBREVIATIONS: Dict[str, str] = {
    # --- Legislação e estrutura normativa ---
    "art.": "artigo",
    "arts.": "artigos",
    "inc.": "inciso",
    "incs.": "incisos",
    "§": "parágrafo",
    "§§": "parágrafos",
    "al.": "alínea",
    "als.": "alíneas",
    "cap.": "capítulo",
    "caps.": "capítulos",
    "tít.": "título",
    "títs.": "títulos",
    "sec.": "seção",
    "secs.": "seções",
    "subsec.": "subseção",
    "n.": "número",
    "n.º": "número",
    "nº": "número",
    "n°": "número",

    # --- Tribunais superiores ---
    "STF": "Supremo Tribunal Federal",
    "STJ": "Superior Tribunal de Justiça",
    "TST": "Tribunal Superior do Trabalho",
    "TSE": "Tribunal Superior Eleitoral",
    "STM": "Superior Tribunal Militar",
    "CNJ": "Conselho Nacional de Justiça",
    "CNMP": "Conselho Nacional do Ministério Público",

    # --- Tribunais regionais federais ---
    "TRF": "Tribunal Regional Federal",
    "TRF1": "Tribunal Regional Federal da 1ª Região",
    "TRF2": "Tribunal Regional Federal da 2ª Região",
    "TRF3": "Tribunal Regional Federal da 3ª Região",
    "TRF4": "Tribunal Regional Federal da 4ª Região",
    "TRF5": "Tribunal Regional Federal da 5ª Região",
    "TRF6": "Tribunal Regional Federal da 6ª Região",

    # --- Tribunais de justiça estaduais ---
    "TJSP": "Tribunal de Justiça de São Paulo",
    "TJRJ": "Tribunal de Justiça do Rio de Janeiro",
    "TJMG": "Tribunal de Justiça de Minas Gerais",
    "TJRS": "Tribunal de Justiça do Rio Grande do Sul",
    "TJPR": "Tribunal de Justiça do Paraná",
    "TJSC": "Tribunal de Justiça de Santa Catarina",
    "TJBA": "Tribunal de Justiça da Bahia",
    "TJPE": "Tribunal de Justiça de Pernambuco",
    "TJCE": "Tribunal de Justiça do Ceará",
    "TJDF": "Tribunal de Justiça do Distrito Federal e Territórios",
    "TJDFT": "Tribunal de Justiça do Distrito Federal e Territórios",
    "TJGO": "Tribunal de Justiça de Goiás",
    "TJPA": "Tribunal de Justiça do Pará",
    "TJMA": "Tribunal de Justiça do Maranhão",
    "TJMT": "Tribunal de Justiça de Mato Grosso",
    "TJMS": "Tribunal de Justiça de Mato Grosso do Sul",
    "TJES": "Tribunal de Justiça do Espírito Santo",
    "TJAM": "Tribunal de Justiça do Amazonas",
    "TJAL": "Tribunal de Justiça de Alagoas",
    "TJRN": "Tribunal de Justiça do Rio Grande do Norte",
    "TJPB": "Tribunal de Justiça da Paraíba",
    "TJSE": "Tribunal de Justiça de Sergipe",
    "TJPI": "Tribunal de Justiça do Piauí",
    "TJTO": "Tribunal de Justiça do Tocantins",
    "TJRO": "Tribunal de Justiça de Rondônia",
    "TJAC": "Tribunal de Justiça do Acre",
    "TJAP": "Tribunal de Justiça do Amapá",
    "TJRR": "Tribunal de Justiça de Roraima",

    # --- Tribunais regionais do trabalho ---
    "TRT": "Tribunal Regional do Trabalho",
    "TRT1": "Tribunal Regional do Trabalho da 1ª Região",
    "TRT2": "Tribunal Regional do Trabalho da 2ª Região",
    "TRT3": "Tribunal Regional do Trabalho da 3ª Região",
    "TRT4": "Tribunal Regional do Trabalho da 4ª Região",
    "TRT15": "Tribunal Regional do Trabalho da 15ª Região",

    # --- Tribunais regionais eleitorais ---
    "TRE": "Tribunal Regional Eleitoral",

    # --- Ministério Público ---
    "MP": "Ministério Público",
    "MPF": "Ministério Público Federal",
    "MPE": "Ministério Público Estadual",
    "MPDFT": "Ministério Público do Distrito Federal e Territórios",
    "MPT": "Ministério Público do Trabalho",
    "MPM": "Ministério Público Militar",
    "PGR": "Procuradoria-Geral da República",
    "PGJ": "Procuradoria-Geral de Justiça",
    "AGU": "Advocacia-Geral da União",
    "PGE": "Procuradoria-Geral do Estado",
    "PGM": "Procuradoria-Geral do Município",

    # --- Órgãos e instituições ---
    "OAB": "Ordem dos Advogados do Brasil",
    "DPU": "Defensoria Pública da União",
    "DPE": "Defensoria Pública Estadual",
    "TCU": "Tribunal de Contas da União",
    "TCE": "Tribunal de Contas do Estado",
    "CGU": "Controladoria-Geral da União",
    "CADE": "Conselho Administrativo de Defesa Econômica",
    "INSS": "Instituto Nacional do Seguro Social",
    "INPI": "Instituto Nacional da Propriedade Industrial",
    "IBAMA": "Instituto Brasileiro do Meio Ambiente",
    "ANATEL": "Agência Nacional de Telecomunicações",
    "ANS": "Agência Nacional de Saúde Suplementar",
    "ANVISA": "Agência Nacional de Vigilância Sanitária",
    "ANEEL": "Agência Nacional de Energia Elétrica",
    "ANA": "Agência Nacional de Águas",
    "ANCINE": "Agência Nacional do Cinema",
    "BACEN": "Banco Central do Brasil",
    "CVM": "Comissão de Valores Mobiliários",
    "SUSEP": "Superintendência de Seguros Privados",

    # --- Legislação principal ---
    "CF": "Constituição Federal",
    "CF/88": "Constituição Federal de 1988",
    "CC": "Código Civil",
    "CC/02": "Código Civil de 2002",
    "CC/16": "Código Civil de 1916",
    "CPC": "Código de Processo Civil",
    "CPC/15": "Código de Processo Civil de 2015",
    "CPC/73": "Código de Processo Civil de 1973",
    "CP": "Código Penal",
    "CPP": "Código de Processo Penal",
    "CLT": "Consolidação das Leis do Trabalho",
    "CDC": "Código de Defesa do Consumidor",
    "CTN": "Código Tributário Nacional",
    "ECA": "Estatuto da Criança e do Adolescente",
    "CTB": "Código de Trânsito Brasileiro",
    "LEF": "Lei de Execução Fiscal",
    "LIA": "Lei de Improbidade Administrativa",
    "LINDB": "Lei de Introdução às Normas do Direito Brasileiro",
    "LICC": "Lei de Introdução ao Código Civil",
    "LRF": "Lei de Responsabilidade Fiscal",
    "LEP": "Lei de Execução Penal",
    "LAI": "Lei de Acesso à Informação",
    "LGPD": "Lei Geral de Proteção de Dados",
    "LACP": "Lei da Ação Civil Pública",
    "LAP": "Lei da Ação Popular",
    "LMS": "Lei do Mandado de Segurança",

    # --- Tipos processuais e procedimentos ---
    "RE": "Recurso Extraordinário",
    "REsp": "Recurso Especial",
    "RMS": "Recurso em Mandado de Segurança",
    "RHC": "Recurso em Habeas Corpus",
    "HC": "Habeas Corpus",
    "HD": "Habeas Data",
    "MS": "Mandado de Segurança",
    "MI": "Mandado de Injunção",
    "ADI": "Ação Direta de Inconstitucionalidade",
    "ADC": "Ação Declaratória de Constitucionalidade",
    "ADPF": "Arguição de Descumprimento de Preceito Fundamental",
    "ADO": "Ação Direta de Inconstitucionalidade por Omissão",
    "ACP": "Ação Civil Pública",
    "AP": "Ação Popular",
    "AI": "Agravo de Instrumento",
    "Ag": "Agravo",
    "AgRg": "Agravo Regimental",
    "AgInt": "Agravo Interno",
    "ED": "Embargos de Declaração",
    "EI": "Embargos Infringentes",
    "EDiv": "Embargos de Divergência",
    "RO": "Recurso Ordinário",
    "RR": "Recurso de Revista",
    "AIRR": "Agravo de Instrumento em Recurso de Revista",
    "ROT": "Recurso Ordinário Trabalhista",

    # --- Súmulas ---
    "SV": "Súmula Vinculante",
    "Súm.": "Súmula",

    # --- Termos processuais ---
    "p.u.": "parágrafo único",
    "c/c": "combinado com",
    "s/n": "sem número",
    "v.g.": "verbi gratia",
    "i.e.": "isto é",
    "e.g.": "por exemplo",
    "cf.": "conforme",
    "v.": "vide",
    "ss.": "seguintes",
    "fl.": "folha",
    "fls.": "folhas",
    "p.": "página",
    "pp.": "páginas",
    "vol.": "volume",
    "vols.": "volumes",
    "doc.": "documento",
    "docs.": "documentos",
    "proc.": "processo",
    "procs.": "processos",
    "j.": "julgamento",
    "DJ": "Diário de Justiça",
    "DJe": "Diário de Justiça Eletrônico",
    "DOU": "Diário Oficial da União",
    "DOE": "Diário Oficial do Estado",
    "rel.": "relator",
    "min.": "ministro",
    "des.": "desembargador",

    # --- Pessoas processuais ---
    "réu": "réu",
    "aut.": "autor",

    # --- Termos latinos comuns ---
    "ex officio": "de ofício",
    "ab initio": "desde o início",
    "ad hoc": "para isso",
    "in dubio pro reo": "na dúvida em favor do réu",
    "in limine": "no limiar",
    "inter partes": "entre as partes",
    "erga omnes": "para todos",
    "ex tunc": "desde então (efeito retroativo)",
    "ex nunc": "de agora em diante (efeito prospectivo)",
    "per capita": "por cabeça",
    "pro rata": "proporcionalmente",
    "ultra petita": "além do pedido",
    "extra petita": "fora do pedido",
    "citra petita": "aquém do pedido",
    "reformatio in pejus": "reformar para pior",
    "non bis in idem": "não duas vezes sobre o mesmo",
    "habeas corpus": "habeas corpus",
    "mandamus": "mandado de segurança",
    "stare decisis": "manter a decisão",
    "res judicata": "coisa julgada",
    "litis consortio": "litisconsórcio",
    "amicus curiae": "amigo da corte",
    "fumus boni juris": "fumaça do bom direito",
    "periculum in mora": "perigo na demora",
}


# =============================================================================
# Sinônimos Jurídicos Agrupados
# =============================================================================

LEGAL_SYNONYMS: List[FrozenSet[str]] = [
    # Partes processuais
    frozenset({"réu", "demandado", "requerido", "acusado", "executado", "reclamado", "impetrado"}),
    frozenset({"autor", "demandante", "requerente", "querelante", "exequente", "reclamante", "impetrante"}),
    frozenset({"juiz", "magistrado", "julgador", "togado"}),
    frozenset({"advogado", "patrono", "causídico", "procurador", "defensor"}),
    frozenset({"testemunha", "depoente", "informante"}),
    frozenset({"perito", "expert", "assistente técnico"}),

    # Ações e decisões
    frozenset({"sentença", "decisão", "julgado", "acórdão", "veredicto"}),
    frozenset({"recurso", "apelação", "impugnação", "inconformismo"}),
    frozenset({"petição", "requerimento", "pedido", "postulação", "demanda"}),
    frozenset({"contestação", "defesa", "resposta", "impugnação"}),
    frozenset({"liminar", "tutela de urgência", "tutela antecipada", "medida cautelar", "medida de urgência"}),
    frozenset({"citação", "notificação", "intimação", "comunicação processual"}),
    frozenset({"penhora", "constrição", "bloqueio", "arresto", "sequestro"}),
    frozenset({"prescrição", "decadência", "perda do prazo", "expiração do direito"}),

    # Legislação
    frozenset({"lei", "norma", "legislação", "diploma legal", "dispositivo legal", "preceito"}),
    frozenset({"decreto", "regulamento", "norma regulamentar"}),
    frozenset({"emenda", "alteração", "modificação legislativa"}),
    frozenset({"revogação", "ab-rogação", "derrogação"}),
    frozenset({"jurisprudência", "precedente", "entendimento consolidado", "orientação jurisprudencial"}),
    frozenset({"súmula", "enunciado", "verbete"}),
    frozenset({"doutrina", "entendimento doutrinário", "posição doutrinária", "lição"}),

    # Conceitos jurídicos fundamentais
    frozenset({"dano", "prejuízo", "lesão", "ofensa"}),
    frozenset({"culpa", "negligência", "imprudência", "imperícia"}),
    frozenset({"dolo", "intenção", "vontade deliberada", "animus"}),
    frozenset({"ilícito", "antijurídico", "contrário ao direito", "ilegalidade"}),
    frozenset({"lícito", "legal", "conforme o direito", "legítimo"}),
    frozenset({"obrigação", "dever", "encargo", "ônus"}),
    frozenset({"direito subjetivo", "prerrogativa", "faculdade", "poder jurídico"}),
    frozenset({"contrato", "negócio jurídico", "ajuste", "convenção", "pacto", "avença"}),
    frozenset({"indenização", "reparação", "compensação", "ressarcimento"}),
    frozenset({"responsabilidade", "imputação", "atribuição de consequências"}),

    # Nulidades e vícios
    frozenset({"nulidade", "invalidade", "vício insanável"}),
    frozenset({"anulabilidade", "vício sanável", "nulidade relativa"}),
    frozenset({"coação", "constrangimento", "ameaça", "violência"}),
    frozenset({"fraude", "simulação", "ardil", "artifício"}),

    # Direito público
    frozenset({"administração pública", "poder público", "Estado", "ente público"}),
    frozenset({"licitação", "certame", "processo licitatório", "procedimento licitatório"}),
    frozenset({"servidor público", "agente público", "funcionário público"}),
    frozenset({"improbidade administrativa", "ato ímprobo", "desonestidade administrativa"}),

    # Direito penal
    frozenset({"crime", "delito", "infração penal", "ilícito penal"}),
    frozenset({"pena", "sanção penal", "reprimenda", "punição"}),
    frozenset({"absolvição", "isenção de pena", "impronúncia"}),
    frozenset({"condenação", "pronúncia", "juízo condenatório"}),

    # Direito do trabalho
    frozenset({"empregador", "patrão", "empresa", "tomador de serviços"}),
    frozenset({"empregado", "trabalhador", "funcionário", "colaborador", "obreiro"}),
    frozenset({"rescisão", "demissão", "dispensa", "desligamento", "término do contrato"}),
    frozenset({"salário", "remuneração", "vencimentos", "proventos", "retribuição"}),
]

# Mapa invertido: cada termo aponta para seu grupo de sinonimos
_SYNONYM_INDEX: Dict[str, FrozenSet[str]] = {}
for _group in LEGAL_SYNONYMS:
    for _term in _group:
        _SYNONYM_INDEX[_term.lower()] = _group


def get_synonyms(term: str) -> FrozenSet[str]:
    """Retorna o grupo de sinonimos para um termo juridico, ou frozenset vazio."""
    return _SYNONYM_INDEX.get(term.lower().strip(), frozenset())


def expand_with_synonyms(text: str) -> str:
    """
    Expande um texto adicionando sinonimos juridicos entre parenteses.
    Util para query augmentation.
    """
    words = text.lower().split()
    expanded_parts: List[str] = []
    seen_groups: Set[int] = set()

    for word in words:
        clean = word.strip(".,;:!?()[]\"'")
        group = _SYNONYM_INDEX.get(clean)
        if group and id(group) not in seen_groups:
            seen_groups.add(id(group))
            synonyms = [s for s in group if s != clean]
            if synonyms:
                expanded_parts.append(f"{word} ({', '.join(synonyms[:3])})")
                continue
        expanded_parts.append(word)

    return " ".join(expanded_parts)


# =============================================================================
# Stopwords Jurídicas (termos que nao agregam significado semantico)
# =============================================================================

LEGAL_STOPWORDS: FrozenSet[str] = frozenset({
    # Termos processuais genericos demais
    "referido", "mencionado", "supracitado", "inframencionado",
    "supramencionado", "acima", "abaixo", "supra", "infra",
    "ora", "doravante", "destarte", "outrossim", "ademais",
    "mister", "curial", "cediço", "esposado", "colacionado",
    "alhures", "algures", "nenhures", "preclaro", "insigne",
    "excelso", "colendo", "egrégio", "inclito", "provecto",
    "data venia", "permissa venia", "maxima venia",
    "salvo melhor juízo", "sob pena de",
    # Numeracao processual
    "autos", "presente feito", "presente demanda", "presente ação",
    "presente recurso", "em epígrafe", "em tela",
    # Formulas genericas
    "ante o exposto", "pelo exposto", "diante do exposto",
    "face ao exposto", "por todo o exposto",
    "requer deferimento", "termos em que pede deferimento",
    "nestes termos", "pede deferimento",
    # Conectores rebuscados
    "conquanto", "porquanto", "dessarte", "deveras",
    "decerto", "sobretudo", "mormente", "precipuamente",
    "notadamente", "especialmente", "particularmente",
})


# =============================================================================
# Hierarquia Normativa (para ponderacao de relevancia)
# =============================================================================

class NormativeLevel(IntEnum):
    """Hierarquia normativa brasileira — valores maiores = maior forca."""
    CONSTITUICAO = 100
    EMENDA_CONSTITUCIONAL = 95
    LEI_COMPLEMENTAR = 80
    LEI_ORDINARIA = 70
    MEDIDA_PROVISORIA = 68
    LEI_DELEGADA = 65
    DECRETO_LEGISLATIVO = 60
    RESOLUCAO_SENADO = 58
    DECRETO = 50
    PORTARIA = 40
    INSTRUCAO_NORMATIVA = 35
    RESOLUCAO = 30
    CIRCULAR = 25
    PARECER = 20
    ORDEM_SERVICO = 15
    SUMULA_VINCULANTE = 90
    SUMULA = 55
    JURISPRUDENCIA = 45
    DOUTRINA = 10


NORMATIVE_KEYWORDS: Dict[str, NormativeLevel] = {
    "constituição": NormativeLevel.CONSTITUICAO,
    "constituicao": NormativeLevel.CONSTITUICAO,
    "cf": NormativeLevel.CONSTITUICAO,
    "cf/88": NormativeLevel.CONSTITUICAO,
    "emenda constitucional": NormativeLevel.EMENDA_CONSTITUCIONAL,
    "ec": NormativeLevel.EMENDA_CONSTITUCIONAL,
    "lei complementar": NormativeLevel.LEI_COMPLEMENTAR,
    "lc": NormativeLevel.LEI_COMPLEMENTAR,
    "lei ordinária": NormativeLevel.LEI_ORDINARIA,
    "lei": NormativeLevel.LEI_ORDINARIA,
    "medida provisória": NormativeLevel.MEDIDA_PROVISORIA,
    "mp": NormativeLevel.MEDIDA_PROVISORIA,
    "lei delegada": NormativeLevel.LEI_DELEGADA,
    "decreto legislativo": NormativeLevel.DECRETO_LEGISLATIVO,
    "resolução do senado": NormativeLevel.RESOLUCAO_SENADO,
    "decreto": NormativeLevel.DECRETO,
    "portaria": NormativeLevel.PORTARIA,
    "instrução normativa": NormativeLevel.INSTRUCAO_NORMATIVA,
    "resolução": NormativeLevel.RESOLUCAO,
    "circular": NormativeLevel.CIRCULAR,
    "parecer": NormativeLevel.PARECER,
    "ordem de serviço": NormativeLevel.ORDEM_SERVICO,
    "súmula vinculante": NormativeLevel.SUMULA_VINCULANTE,
    "sv": NormativeLevel.SUMULA_VINCULANTE,
    "súmula": NormativeLevel.SUMULA,
    "jurisprudência": NormativeLevel.JURISPRUDENCIA,
    "precedente": NormativeLevel.JURISPRUDENCIA,
    "doutrina": NormativeLevel.DOUTRINA,
}


def detect_normative_level(text: str) -> NormativeLevel:
    """Detecta o nivel normativo mais alto referenciado em um texto."""
    text_lower = text.lower()
    best = NormativeLevel.DOUTRINA
    for keyword, level in NORMATIVE_KEYWORDS.items():
        if keyword in text_lower and level > best:
            best = level
    return best


# =============================================================================
# Regex Patterns para Citacoes Juridicas
# =============================================================================

@dataclass
class CitationPattern:
    """Pattern compilado com metadata para citacoes juridicas."""
    name: str
    pattern: Pattern[str]
    category: str  # "legislacao", "jurisprudencia", "sumula", "processual"
    description: str


CITATION_PATTERNS: List[CitationPattern] = [
    # --- Legislacao ---
    CitationPattern(
        name="artigo_lei",
        pattern=re.compile(
            r"(?i)\bart(?:igo)?\.?\s*(\d+)(?:\s*,?\s*(?:§|par[áa]grafo)\s*(?:único|\d+))?"
            r"(?:\s*,?\s*(?:inc(?:iso)?\.?\s*[IVXLCDM]+|al(?:ínea)?\.?\s*[a-z]))*",
            re.UNICODE,
        ),
        category="legislacao",
        description="Referência a artigo de lei (art. 5°, § 1°, inciso III)",
    ),
    CitationPattern(
        name="lei_numero",
        pattern=re.compile(
            r"(?i)\blei\s+(?:n\.?º?\s*)?(\d[\d.]*)/(\d{2,4})",
            re.UNICODE,
        ),
        category="legislacao",
        description="Lei numerada (Lei 8.666/93, Lei nº 14.133/2021)",
    ),
    CitationPattern(
        name="lei_complementar",
        pattern=re.compile(
            r"(?i)\blei\s+complementar\s+(?:n\.?º?\s*)?(\d[\d.]*)",
            re.UNICODE,
        ),
        category="legislacao",
        description="Lei Complementar (LC 101/2000)",
    ),
    CitationPattern(
        name="medida_provisoria",
        pattern=re.compile(
            r"(?i)\bmedida\s+provis[oó]ria\s+(?:n\.?º?\s*)?(\d[\d.]*)",
            re.UNICODE,
        ),
        category="legislacao",
        description="Medida Provisória (MP 936/2020)",
    ),
    CitationPattern(
        name="decreto",
        pattern=re.compile(
            r"(?i)\bdecreto\s+(?:n\.?º?\s*)?(\d[\d.]*)/(\d{2,4})",
            re.UNICODE,
        ),
        category="legislacao",
        description="Decreto numerado (Decreto 9.764/2019)",
    ),
    CitationPattern(
        name="codigo_referencia",
        pattern=re.compile(
            r"(?i)\b(C[óo]digo\s+(?:Civil|Penal|de\s+Processo\s+Civil|de\s+Processo\s+Penal"
            r"|de\s+Defesa\s+do\s+Consumidor|Tribut[áa]rio\s+Nacional"
            r"|de\s+Tr[âa]nsito\s+Brasileiro))",
            re.UNICODE,
        ),
        category="legislacao",
        description="Referência a códigos (Código Civil, CPC, etc.)",
    ),
    CitationPattern(
        name="constituicao_artigo",
        pattern=re.compile(
            r"(?i)\b(?:CF|Constitui[çc][ãa]o\s+Federal)(?:/88)?\s*,?\s*art(?:igo)?\.?\s*(\d+)",
            re.UNICODE,
        ),
        category="legislacao",
        description="Referência à Constituição Federal com artigo",
    ),

    # --- Jurisprudencia ---
    CitationPattern(
        name="cnj_number",
        pattern=re.compile(
            r"\b(\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4})\b",
        ),
        category="processual",
        description="Número CNJ de processo (NNNNNNN-DD.AAAA.J.TR.OOOO)",
    ),
    CitationPattern(
        name="recurso_especial",
        pattern=re.compile(
            r"(?i)\bREsp\.?\s+(?:n\.?º?\s*)?(\d[\d.]*)",
            re.UNICODE,
        ),
        category="jurisprudencia",
        description="Recurso Especial (REsp 1.234.567)",
    ),
    CitationPattern(
        name="recurso_extraordinario",
        pattern=re.compile(
            r"(?i)\bRE\s+(?:n\.?º?\s*)?(\d[\d.]*)",
            re.UNICODE,
        ),
        category="jurisprudencia",
        description="Recurso Extraordinário (RE 123.456)",
    ),
    CitationPattern(
        name="habeas_corpus",
        pattern=re.compile(
            r"(?i)\bHC\s+(?:n\.?º?\s*)?(\d[\d.]*)",
            re.UNICODE,
        ),
        category="jurisprudencia",
        description="Habeas Corpus (HC 123.456)",
    ),
    CitationPattern(
        name="adi",
        pattern=re.compile(
            r"(?i)\bADI(?:n)?\s+(?:n\.?º?\s*)?(\d[\d.]*)",
            re.UNICODE,
        ),
        category="jurisprudencia",
        description="Ação Direta de Inconstitucionalidade (ADI 1.234)",
    ),
    CitationPattern(
        name="agravo",
        pattern=re.compile(
            r"(?i)\b(?:AgRg|AgInt|AI|Ag)\s+(?:n[o°]?\s*|no\s+)?(?:REsp|RE|AREsp)?\s*(?:n\.?º?\s*)?(\d[\d.]*)",
            re.UNICODE,
        ),
        category="jurisprudencia",
        description="Agravos diversos (AgRg, AgInt, AI)",
    ),
    CitationPattern(
        name="tribunal_decisao",
        pattern=re.compile(
            r"(?i)\b(STF|STJ|TST|TSE|TRF\d?|TJ[A-Z]{2}|TRT\d{1,2})\s*,?\s*"
            r"(?:[\w\s]+,?\s*)?(?:j\.\s*\d{1,2}[./]\d{1,2}[./]\d{2,4}|"
            r"DJ[e]?\s+\d{1,2}[./]\d{1,2}[./]\d{2,4})",
            re.UNICODE,
        ),
        category="jurisprudencia",
        description="Decisão de tribunal com data de julgamento/publicação",
    ),

    # --- Sumulas ---
    CitationPattern(
        name="sumula_vinculante",
        pattern=re.compile(
            r"(?i)\bs[úu]mula\s+vinculante\s+(?:n\.?º?\s*)?(\d+)",
            re.UNICODE,
        ),
        category="sumula",
        description="Súmula Vinculante (SV 37)",
    ),
    CitationPattern(
        name="sumula_stf",
        pattern=re.compile(
            r"(?i)\bs[úu]mula\s+(?:n\.?º?\s*)?(\d+)\s+(?:do\s+)?STF",
            re.UNICODE,
        ),
        category="sumula",
        description="Súmula do STF (Súmula 473 do STF)",
    ),
    CitationPattern(
        name="sumula_stj",
        pattern=re.compile(
            r"(?i)\bs[úu]mula\s+(?:n\.?º?\s*)?(\d+)\s+(?:do\s+)?STJ",
            re.UNICODE,
        ),
        category="sumula",
        description="Súmula do STJ (Súmula 7 do STJ)",
    ),
    CitationPattern(
        name="sumula_generica",
        pattern=re.compile(
            r"(?i)\bs[úu]mula\s+(?:n\.?º?\s*)?(\d+)",
            re.UNICODE,
        ),
        category="sumula",
        description="Súmula genérica (Súmula 123)",
    ),

    # --- Orientacao Jurisprudencial (OJ) ---
    CitationPattern(
        name="oj_tst",
        pattern=re.compile(
            r"(?i)\bOJ\s+(?:n\.?º?\s*)?(\d+)\s*(?:da\s+)?(?:SDI|SBDI|SDC)?",
            re.UNICODE,
        ),
        category="jurisprudencia",
        description="Orientação Jurisprudencial do TST",
    ),
]


def extract_citations(text: str) -> List[Dict[str, str]]:
    """
    Extrai todas as citações jurídicas de um texto.

    Returns:
        Lista de dicts com: name, category, match, start, end
    """
    results: List[Dict[str, str]] = []
    for cp in CITATION_PATTERNS:
        for match in cp.pattern.finditer(text):
            results.append({
                "name": cp.name,
                "category": cp.category,
                "match": match.group(0),
                "start": str(match.start()),
                "end": str(match.end()),
            })
    # Ordenar por posicao no texto
    results.sort(key=lambda r: int(r["start"]))
    return results


# =============================================================================
# Termos tecnicos que devem ser preservados (nao tokenizados)
# =============================================================================

PRESERVE_TERMS: FrozenSet[str] = frozenset({
    # Principios constitucionais
    "devido processo legal", "ampla defesa", "contraditório",
    "presunção de inocência", "legalidade", "moralidade",
    "impessoalidade", "publicidade", "eficiência",
    "razoabilidade", "proporcionalidade", "segurança jurídica",
    "dignidade da pessoa humana", "boa-fé objetiva",
    "função social do contrato", "função social da propriedade",
    "vedação ao retrocesso", "mínimo existencial",
    "reserva do possível", "proibição do excesso",

    # Institutos processuais
    "tutela antecipada", "tutela de urgência",
    "tutela de evidência", "tutela provisória",
    "coisa julgada", "litispendência", "conexão",
    "continência", "prevenção", "competência absoluta",
    "competência relativa", "suspeição", "impedimento",
    "ônus da prova", "inversão do ônus da prova",
    "prova emprestada", "livre convencimento motivado",

    # Institutos de direito material
    "ato jurídico perfeito", "direito adquirido",
    "responsabilidade objetiva", "responsabilidade subjetiva",
    "teoria do risco", "teoria da culpa",
    "enriquecimento sem causa", "abuso de direito",
    "venire contra factum proprium", "supressio", "surrectio",
    "exceptio non adimpleti contractus",

    # Termos trabalhistas
    "justa causa", "rescisão indireta",
    "verbas rescisórias", "aviso prévio",
    "adicional de insalubridade", "adicional de periculosidade",
    "intervalo intrajornada", "intervalo interjornada",

    # Termos tributarios
    "fato gerador", "base de cálculo",
    "sujeito ativo", "sujeito passivo",
    "substituição tributária", "responsabilidade tributária",
    "imunidade tributária", "isenção tributária",
    "não incidência", "anistia fiscal",

    # Termos administrativos
    "ato vinculado", "ato discricionário",
    "poder de polícia", "serviço público",
    "concessão de serviço público", "permissão de serviço público",
    "parceria público-privada", "consórcio público",
})


# =============================================================================
# Regex de limpeza de ruido processual
# =============================================================================

NOISE_PATTERNS: List[Tuple[Pattern[str], str]] = [
    # Numeracao de paragrafos e itens genericos
    (re.compile(r"^\s*\d+\.\s*$", re.MULTILINE), ""),
    # Linhas de separacao
    (re.compile(r"^[-=_]{3,}\s*$", re.MULTILINE), ""),
    # Cabecalhos de pagina repetitivos
    (re.compile(r"(?i)^(?:poder\s+judiciário|tribunal\s+de\s+justiça).*$", re.MULTILINE), ""),
    # Numeracao de paginas
    (re.compile(r"(?i)^\s*(?:fls?\.?|p[áa]g(?:ina)?\.?)\s*\d+\s*$", re.MULTILINE), ""),
    # Multiplas quebras de linha
    (re.compile(r"\n{3,}"), "\n\n"),
    # Espacos excessivos
    (re.compile(r"[ \t]{2,}"), " "),
]


def clean_legal_noise(text: str) -> str:
    """Remove ruido processual de um texto juridico."""
    result = text
    for pattern, replacement in NOISE_PATTERNS:
        result = pattern.sub(replacement, result)
    return result.strip()
