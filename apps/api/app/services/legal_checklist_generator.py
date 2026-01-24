"""
Legal Checklist Generator

Extrai e gera checklist de dispositivos legais, súmulas, teses e precedentes
vinculantes ao final de apostilas jurídicas transcritas.

Baseado no Art. 927 do CPC - Precedentes Vinculantes:
- Decisões do STF em controle concentrado (ADI, ADC, ADPF)
- Súmulas vinculantes (STF)
- Acórdãos em IAC (Incidente de Assunção de Competência)
- Acórdãos em IRDR (Incidente de Resolução de Demandas Repetitivas)
- Recursos Extraordinário e Especial Repetitivos (STF/STJ)
- Súmulas do STF (matéria constitucional) e STJ (infraconstitucional)
- Orientações do plenário ou órgão especial
"""

import re
from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
from loguru import logger


class PrecedentCategory(str, Enum):
    """Categorias de precedentes conforme Art. 927 CPC."""
    CONTROLE_CONCENTRADO = "controle_concentrado"  # ADI, ADC, ADPF
    SUMULA_VINCULANTE = "sumula_vinculante"
    IAC = "iac"  # Incidente de Assunção de Competência
    IRDR = "irdr"  # Incidente de Resolução de Demandas Repetitivas
    RECURSO_REPETITIVO = "recurso_repetitivo"  # RE/REsp Repetitivos, Temas
    SUMULA_STF = "sumula_stf"
    SUMULA_STJ = "sumula_stj"
    SUMULA_TST = "sumula_tst"
    SUMULA_TSE = "sumula_tse"
    OJ_TST = "oj_tst"  # Orientações Jurisprudenciais
    ORIENTACAO_PLENARIO = "orientacao_plenario"

    # Dispositivos legais
    CONSTITUICAO = "constituicao"
    EMENDA_CONSTITUCIONAL = "emenda_constitucional"
    ADCT = "adct"  # Atos das Disposições Constitucionais Transitórias
    LEI_FEDERAL = "lei_federal"
    LEI_COMPLEMENTAR = "lei_complementar"
    DECRETO = "decreto"
    DECRETO_LEI = "decreto_lei"
    MEDIDA_PROVISORIA = "medida_provisoria"
    CODIGO = "codigo"
    ESTATUTO = "estatuto"
    RESOLUCAO = "resolucao"
    PORTARIA = "portaria"
    INSTRUCAO_NORMATIVA = "instrucao_normativa"
    ENUNCIADO = "enunciado"
    TRATADO = "tratado"


@dataclass
class LegalReference:
    """Uma referência legal extraída do texto."""
    category: PrecedentCategory
    identifier: str  # Ex: "ADI 4.277", "Súmula Vinculante 13", "Lei 8.666/93"
    number: str  # Número principal
    description: Optional[str] = None  # Descrição/ementa se disponível
    article: Optional[str] = None  # Artigo específico se mencionado
    court: Optional[str] = None  # Tribunal (STF, STJ, TJ, etc.)
    year: Optional[str] = None
    context: Optional[str] = None  # Trecho onde aparece
    count: int = 1  # Quantas vezes aparece


@dataclass
class LegalChecklist:
    """Checklist completo de referências legais."""
    # Precedentes vinculantes (Art. 927 CPC)
    controle_concentrado: List[LegalReference] = field(default_factory=list)
    sumulas_vinculantes: List[LegalReference] = field(default_factory=list)
    iac: List[LegalReference] = field(default_factory=list)
    irdr: List[LegalReference] = field(default_factory=list)
    recursos_repetitivos: List[LegalReference] = field(default_factory=list)
    temas_repetitivos: List[LegalReference] = field(default_factory=list)
    sumulas_stf: List[LegalReference] = field(default_factory=list)
    sumulas_stj: List[LegalReference] = field(default_factory=list)
    sumulas_tst: List[LegalReference] = field(default_factory=list)
    sumulas_tse: List[LegalReference] = field(default_factory=list)
    ojs_tst: List[LegalReference] = field(default_factory=list)

    # Dispositivos legais - Constituição
    constituicao: List[LegalReference] = field(default_factory=list)
    emendas_constitucionais: List[LegalReference] = field(default_factory=list)
    adct: List[LegalReference] = field(default_factory=list)

    # Dispositivos legais - Legislação infraconstitucional
    leis_federais: List[LegalReference] = field(default_factory=list)
    leis_complementares: List[LegalReference] = field(default_factory=list)
    decretos: List[LegalReference] = field(default_factory=list)
    decretos_lei: List[LegalReference] = field(default_factory=list)
    medidas_provisorias: List[LegalReference] = field(default_factory=list)
    codigos: List[LegalReference] = field(default_factory=list)
    estatutos: List[LegalReference] = field(default_factory=list)

    # Atos normativos infralegais
    resolucoes: List[LegalReference] = field(default_factory=list)
    portarias: List[LegalReference] = field(default_factory=list)
    instrucoes_normativas: List[LegalReference] = field(default_factory=list)

    # Enunciados e orientações
    enunciados: List[LegalReference] = field(default_factory=list)

    # Tratados internacionais
    tratados: List[LegalReference] = field(default_factory=list)

    # Outros julgados relevantes
    outros_julgados: List[LegalReference] = field(default_factory=list)

    # Metadata
    total_references: int = 0
    document_name: str = ""


class LegalChecklistGenerator:
    """
    Extrai referências legais de texto e gera checklist formatado.
    """

    # =========================================================================
    # REGEX PATTERNS
    # =========================================================================

    # Controle concentrado de constitucionalidade
    PATTERNS_CONTROLE_CONCENTRADO = [
        # ADI - Ação Direta de Inconstitucionalidade
        r'\bADI\s*(?:n[º°]?\s*)?([\d.,]+)(?:\s*/\s*([A-Z]{2}))?',
        r'[Aa]ção\s+[Dd]ireta\s+(?:de\s+)?[Ii]nconstitucionalidade\s*(?:n[º°]?\s*)?([\d.,]+)',
        # ADC - Ação Declaratória de Constitucionalidade
        r'\bADC\s*(?:n[º°]?\s*)?([\d.,]+)',
        r'[Aa]ção\s+[Dd]eclaratória\s+(?:de\s+)?[Cc]onstitucionalidade\s*(?:n[º°]?\s*)?([\d.,]+)',
        # ADPF - Arguição de Descumprimento de Preceito Fundamental
        r'\bADPF\s*(?:n[º°]?\s*)?([\d.,]+)',
        r'[Aa]rguição\s+(?:de\s+)?[Dd]escumprimento\s+(?:de\s+)?[Pp]receito\s+[Ff]undamental\s*(?:n[º°]?\s*)?([\d.,]+)',
        # ADO - Ação Direta de Inconstitucionalidade por Omissão (note: \b to avoid matching "EnunciadO")
        r'\bADO\s+(?:n[º°]?\s*)?([\d.,]+)',
        r'[Aa]ção\s+[Dd]ireta\s+(?:de\s+)?[Ii]nconstitucionalidade\s+(?:por\s+)?[Oo]miss[ãa]o\s*(?:n[º°]?\s*)?([\d.,]+)',
    ]

    # Súmulas
    PATTERNS_SUMULA_VINCULANTE = [
        r'[Ss]úmula\s+[Vv]inculante\s*(?:n[º°]?\s*)?([\d]+)',
        r'SV\s*(?:n[º°]?\s*)?([\d]+)',
    ]

    PATTERNS_SUMULA_STF = [
        r'[Ss]úmula\s*(?:n[º°]?\s*)?([\d]+)\s*(?:do\s+)?STF',
        r'STF\s*[,-]?\s*[Ss]úmula\s*(?:n[º°]?\s*)?([\d]+)',
    ]

    PATTERNS_SUMULA_STJ = [
        r'[Ss]úmula\s*(?:n[º°]?\s*)?([\d]+)\s*(?:do\s+)?STJ',
        r'STJ\s*[,-]?\s*[Ss]úmula\s*(?:n[º°]?\s*)?([\d]+)',
    ]

    PATTERNS_SUMULA_TST = [
        r'[Ss]úmula\s*(?:n[º°]?\s*)?([\d]+)\s*(?:do\s+)?TST',
        r'TST\s*[,-]?\s*[Ss]úmula\s*(?:n[º°]?\s*)?([\d]+)',
    ]

    PATTERNS_SUMULA_TSE = [
        r'[Ss]úmula\s*(?:n[º°]?\s*)?([\d]+)\s*(?:do\s+)?TSE',
        r'TSE\s*[,-]?\s*[Ss]úmula\s*(?:n[º°]?\s*)?([\d]+)',
    ]

    PATTERNS_OJ_TST = [
        r'OJ\s*(?:n[º°]?\s*)?([\d]+)(?:\s*(?:da\s+)?(?:SDI|SBDI)[-\s]?(?:1|2|I|II)?)?',
        r'[Oo]rienta[çc][ãa]o\s+[Jj]urisprudencial\s*(?:n[º°]?\s*)?([\d]+)',
    ]

    # Recursos repetitivos e temas
    PATTERNS_RECURSO_REPETITIVO = [
        # RE - Recurso Extraordinário (não capturar ARE)
        r'(?<![A-Za-z])RE\s*(?:n[º°]?\s*)?([\d.,]+)(?:\s*/\s*([A-Z]{2}))?(?:\s*[-–]\s*RG)?',
        r'[Rr]ecurso\s+[Ee]xtraordinário\s*(?:n[º°]?\s*)?([\d.,]+)',
        # REsp - Recurso Especial (não capturar AREsp ou EREsp)
        r'(?<![A-Za-z])REsp\s*(?:n[º°]?\s*)?([\d.,]+)(?:\s*/\s*([A-Z]{2}))?',
        r'[Rr]ecurso\s+[Ee]special\s*(?:n[º°]?\s*)?([\d.,]+)',
    ]

    PATTERNS_TEMA = [
        r'[Tt]ema\s*(?:n[º°]?\s*)?([\d]+)(?:\s*(?:do\s+)?(?:STF|STJ))?',
        r'[Tt]ema\s+(?:de\s+)?[Rr]epercussão\s+[Gg]eral\s*(?:n[º°]?\s*)?([\d]+)',
        r'[Rr]epercussão\s+[Gg]eral\s*(?:n[º°]?\s*)?([\d]+)',
    ]

    # IAC e IRDR
    PATTERNS_IAC = [
        r'IAC\s*(?:n[º°]?\s*)?([\d.,]+)',
        r'[Ii]ncidente\s+(?:de\s+)?[Aa]ssunção\s+(?:de\s+)?[Cc]ompetência\s*(?:n[º°]?\s*)?([\d.,]+)',
    ]

    PATTERNS_IRDR = [
        r'IRDR\s*(?:n[º°]?\s*)?([\d.,]+)',
        r'[Ii]ncidente\s+(?:de\s+)?[Rr]esolução\s+(?:de\s+)?[Dd]emandas\s+[Rr]epetitivas\s*(?:n[º°]?\s*)?([\d.,]+)',
    ]

    # Outros recursos/julgados (ordem importa: padrões mais específicos primeiro)
    PATTERNS_JULGADOS = [
        # Recursos em (RHC, RMS) - antes de HC, MS
        r'\bRHC\s*(?:n[º°]?\s*)?([\d.,]+)(?:\s*/\s*([A-Z]{2}))?',  # Recurso em Habeas Corpus
        r'\bRMS\s*(?:n[º°]?\s*)?([\d.,]+)(?:\s*/\s*([A-Z]{2}))?',  # Recurso em Mandado de Segurança
        # Agravos em recursos (ARE, AREsp) - antes de RE, REsp
        r'\bAREsp\s*(?:n[º°]?\s*)?([\d.,]+)(?:\s*/\s*([A-Z]{2}))?',  # Agravo em Recurso Especial
        r'\bARE\s*(?:n[º°]?\s*)?([\d.,]+)(?:\s*/\s*([A-Z]{2}))?',  # Agravo em Recurso Extraordinário
        # Embargos de Divergência (EREsp, ERE)
        r'\bEREsp\s*(?:n[º°]?\s*)?([\d.,]+)(?:\s*/\s*([A-Z]{2}))?',  # Embargos de Divergência em REsp
        r'\bERE\s*(?:n[º°]?\s*)?([\d.,]+)(?:\s*/\s*([A-Z]{2}))?',  # Embargos de Divergência em RE
        # Habeas Corpus e Habeas Data (depois de RHC)
        r'(?<![A-Za-z])HC\s*(?:n[º°]?\s*)?([\d.,]+)(?:\s*/\s*([A-Z]{2}))?',  # Habeas Corpus
        r'\bHD\s*(?:n[º°]?\s*)?([\d.,]+)(?:\s*/\s*([A-Z]{2}))?',  # Habeas Data
        # Mandado de Segurança e Injunção (depois de RMS)
        r'(?<![A-Za-z])MS\s*(?:n[º°]?\s*)?([\d.,]+)(?:\s*/\s*([A-Z]{2}))?',  # Mandado de Segurança
        r'\bMI\s*(?:n[º°]?\s*)?([\d.,]+)(?:\s*/\s*([A-Z]{2}))?',  # Mandado de Injunção
        # Agravos
        r'\bAgRg\s*(?:n[º°]?\s*)?([\d.,]+)',  # Agravo Regimental
        r'\bAgInt\s*(?:n[º°]?\s*)?([\d.,]+)',  # Agravo Interno
        # Embargos de Declaração
        r'\bEDcl\s*(?:n[º°]?\s*)?([\d.,]+)',  # Embargos de Declaração
        r'(?<![A-Za-z])ED\s*(?:n[º°]?\s*)?([\d.,]+)',  # ED (forma curta, não capturar de EDcl)
        # Outros
        r'\bRcl\s*(?:n[º°]?\s*)?([\d.,]+)(?:\s*/\s*([A-Z]{2}))?',  # Reclamação
        r'\bAC\s*(?:n[º°]?\s*)?([\d.,]+)(?:\s*/\s*([A-Z]{2}))?',  # Ação Cautelar
        r'\bPet\s*(?:n[º°]?\s*)?([\d.,]+)(?:\s*/\s*([A-Z]{2}))?',  # Petição
        r'\bInq\s*(?:n[º°]?\s*)?([\d.,]+)(?:\s*/\s*([A-Z]{2}))?',  # Inquérito
        r'\bAP\s*(?:n[º°]?\s*)?([\d.,]+)(?:\s*/\s*([A-Z]{2}))?',  # Ação Penal
        r'\bSS\s*(?:n[º°]?\s*)?([\d.,]+)(?:\s*/\s*([A-Z]{2}))?',  # Suspensão de Segurança
        r'\bSL\s*(?:n[º°]?\s*)?([\d.,]+)(?:\s*/\s*([A-Z]{2}))?',  # Suspensão de Liminar
    ]

    # Dispositivos legais - Constituição
    PATTERNS_CONSTITUICAO = [
        # "art. 5º da CF", "art. 5º, § 2º, da CF/88", "artigo 37 da Constituição Federal"
        r'[Aa]rt(?:igo)?\.?\s*([\d]+)[º°]?(?:[,\s]+(?:§|par[aá]grafo\.?|par\.?\s*[uú]n\.?)\s*(?:único|[\d]+[º°]?))?(?:[,\s]+(?:inc(?:iso)?\.?\s*)?[IVXLCDM]+)?(?:[,\s]+(?:al(?:[ií]nea)?\.?\s*)?[a-z])?[,\s]+d[oa]\s+(?:CF(?:/88)?|[Cc]onstituição(?:\s+[Ff]ederal)?)',
        # "CF, art. 5º" ou "CF/88, art. 37"
        r'CF(?:/88)?\s*[,:\s]+[Aa]rt(?:igo)?\.?\s*([\d]+)[º°]?',
        # "art. 5º, CF" (artigo antes, CF depois sem "da")
        r'[Aa]rt(?:igo)?\.?\s*([\d]+)[º°]?\s*,\s*CF(?:/88)?(?!\w)',
    ]

    PATTERNS_EMENDA_CONSTITUCIONAL = [
        r'[Ee]menda\s+[Cc]onstitucional\s*(?:n[º°]?\s*)?([\d]+)(?:\s*/\s*(\d{2,4}))?',
        r'\bEC\s*(?:n[º°]?\s*)?([\d]+)(?:\s*/\s*(\d{2,4}))?',
    ]

    PATTERNS_ADCT = [
        r'ADCT\s*[,-]?\s*[Aa]rt(?:igo)?\.?\s*([\d]+)[º°]?',
        r'[Aa]rt(?:igo)?\.?\s*([\d]+)[º°]?\s*(?:,?\s*)?(?:do\s+)?ADCT',
        r'[Aa]tos?\s+(?:das?\s+)?[Dd]isposi[çc][õo]es?\s+[Cc]onstitucionais?\s+[Tt]ransit[óo]rias?\s*[,-]?\s*[Aa]rt(?:igo)?\.?\s*([\d]+)[º°]?',
    ]

    # Legislação infraconstitucional
    PATTERNS_LEI = [
        r'[Ll]ei\s*(?:[Ff]ederal\s*)?(?:n[º°]?\s*)?([\d.,]+)(?:\s*/\s*(\d{2,4}))?',
    ]

    PATTERNS_LEI_COMPLEMENTAR = [
        r'[Ll]ei\s+[Cc]omplementar\s*(?:n[º°]?\s*)?([\d.,]+)(?:\s*/\s*(\d{2,4}))?',
        r'LC\s*(?:n[º°]?\s*)?([\d.,]+)(?:\s*/\s*(\d{2,4}))?',
    ]

    PATTERNS_DECRETO = [
        r'[Dd]ecreto(?:\s+[Ff]ederal)?\s*(?:n[º°]?\s*)?([\d.,]+)(?:\s*/\s*(\d{2,4}))?',
    ]

    PATTERNS_DECRETO_LEI = [
        r'[Dd]ecreto[-\s][Ll]ei\s*(?:n[º°]?\s*)?([\d.,]+)(?:\s*/\s*(\d{2,4}))?',
        r'DL\s*(?:n[º°]?\s*)?([\d.,]+)(?:\s*/\s*(\d{2,4}))?',
    ]

    PATTERNS_MP = [
        r'[Mm]edida\s+[Pp]rovisória\s*(?:n[º°]?\s*)?([\d.,]+)(?:\s*/\s*(\d{2,4}))?',
        r'MP\s*(?:n[º°]?\s*)?([\d.,]+)(?:\s*/\s*(\d{2,4}))?',
    ]

    PATTERNS_ESTATUTO = [
        r'[Ee]statuto\s+(?:da\s+)?[Cc]riança\s+e\s+(?:do\s+)?[Aa]dolescente',
        r'[Ee]statuto\s+(?:do\s+)?[Ii]doso',
        r'[Ee]statuto\s+(?:da\s+)?[Cc]idade',
        r'[Ee]statuto\s+(?:da\s+)?[Tt]erra',
        r'[Ee]statuto\s+(?:do\s+)?[Dd]esarmamento',
        r'[Ee]statuto\s+(?:da\s+)?[Aa]dvocacia',
        r'[Ee]statuto\s+(?:da\s+)?[Oo]AB',
        r'[Ee]statuto\s+(?:do\s+)?[Ee]strangeiro',
        r'[Ee]statuto\s+(?:do\s+)?[Rr]efugiado',
        r'[Ee]statuto\s+(?:da\s+)?[Ii]gualdade\s+[Rr]acial',
        r'[Ee]statuto\s+(?:da\s+)?[Pp]essoa\s+(?:com\s+)?[Dd]eficiência',
        r'[Ee]statuto\s+(?:da\s+)?[Jj]uventude',
    ]

    # Atos normativos infralegais
    PATTERNS_RESOLUCAO = [
        r'[Rr]esolu[çc][ãa]o\s*(?:n[º°]?\s*)?([\d.,]+)(?:\s*/\s*(\d{2,4}))?(?:\s*(?:do\s+)?(?:CNJ|CNMP|TSE|CFM|CFC|CONAMA|ANVISA|BACEN|CVM))?',
        r'(?:CNJ|CNMP|TSE)\s*[,-]?\s*[Rr]esolu[çc][ãa]o\s*(?:n[º°]?\s*)?([\d.,]+)',
    ]

    PATTERNS_PORTARIA = [
        r'[Pp]ortaria\s*(?:n[º°]?\s*)?([\d.,]+)(?:\s*/\s*(\d{2,4}))?',
    ]

    PATTERNS_INSTRUCAO_NORMATIVA = [
        r'[Ii]nstru[çc][ãa]o\s+[Nn]ormativa\s*(?:n[º°]?\s*)?([\d.,]+)(?:\s*/\s*(\d{2,4}))?',
        # IN seguida de órgão e número: "IN RFB 1.500/2014"
        r'\bIN\s+(?:RFB|SRF|INSS|IBAMA|ANVISA|CAIXA)\s*(?:n[º°]?\s*)?([\d.,]+)(?:\s*/\s*(\d{2,4}))?',
        # IN seguida direto de número: "IN 1.500/2014"
        r'\bIN\s*(?:n[º°]?\s*)?([\d.,]+)(?:\s*/\s*(\d{2,4}))?',
    ]

    # Enunciados
    PATTERNS_ENUNCIADO = [
        r'[Ee]nunciado\s*(?:n[º°]?\s*)?([\d]+)(?:\s*(?:do\s+|da\s+)?(?:CJF|FONAJE|TST))?',
        r'[Ee]nunciado\s*(?:n[º°]?\s*)?([\d]+)\s*(?:da\s+)?(?:\d+[ªº]?\s*)?[Jj]ornada',
        r'(?:CJF|FONAJE)\s*[,-]?\s*[Ee]nunciado\s*(?:n[º°]?\s*)?([\d]+)',
    ]

    # Tratados internacionais
    PATTERNS_TRATADO = [
        r'[Cc]onven[çc][ãa]o\s+(?:de\s+)?(?:Viena|Genebra|Haia|Nova\s+York|Montego\s+Bay)',
        r'[Cc]onven[çc][ãa]o\s+[Aa]mericana\s+(?:de\s+|sobre\s+)?[Dd]ireitos\s+[Hh]umanos',
        r'[Pp]acto\s+(?:de\s+)?[Ss][ãa]o\s+[Jj]os[ée]\s+(?:da\s+)?[Cc]osta\s+[Rr]ica',
        r'[Cc]onven[çc][ãa]o\s+(?:n[º°]?\s*)?([\d]+)\s*(?:da\s+)?OIT',
        r'[Tt]ratado\s+(?:de\s+)?(?:Roma|Lisboa|Maastricht|Assun[çc][ãa]o)',
        r'[Dd]eclara[çc][ãa]o\s+[Uu]niversal\s+(?:dos\s+)?[Dd]ireitos\s+[Hh]umanos',
        r'PIDCP|PIDESC',  # Pactos Internacionais
        r'[Cc]onven[çc][ãa]o\s+(?:sobre\s+)?[Dd]ireitos\s+(?:da\s+)?[Cc]rian[çc]a',
        r'[Ee]statuto\s+(?:de\s+)?Roma',
    ]

    PATTERNS_CODIGO = [
        r'[Cc]ódigo\s+[Cc]ivil(?:\s+de\s+(\d{4}))?',
        r'[Cc]ódigo\s+[Pp]enal(?:\s+de\s+(\d{4}))?',
        r'[Cc]ódigo\s+(?:de\s+)?[Pp]rocesso\s+[Cc]ivil(?:\s+de\s+(\d{4}))?',
        r'[Cc]ódigo\s+(?:de\s+)?[Pp]rocesso\s+[Pp]enal(?:\s+de\s+(\d{4}))?',
        r'[Cc]ódigo\s+[Tt]ributário\s+[Nn]acional',
        r'[Cc]ódigo\s+(?:de\s+)?[Dd]efesa\s+(?:do\s+)?[Cc]onsumidor',
        r'[Cc]ódigo\s+(?:de\s+)?[Tt]r[âa]nsito\s+[Bb]rasileiro',
        r'[Cc]ódigo\s+[Ee]leitoral',
        r'[Cc]ódigo\s+[Cc]omercial',
        r'[Cc]ódigo\s+[Ff]lorestal',
        r'[Cc]ódigo\s+(?:de\s+)?[Mm]inera[çc][ãa]o',
        r'[Cc]ódigo\s+(?:de\s+)?[Áa]guas',
        r'[Cc]ódigo\s+[Bb]rasileiro\s+(?:de\s+)?[Aa]eron[áa]utica',
        r'CLT',
        r'CPC(?:/\d{4})?',
        r'CPP',
        r'CC(?:/\d{4})?',
        r'CP\b',
        r'CTN',
        r'CDC',
        r'CTB',  # Código de Trânsito Brasileiro
        r'ECA',
        r'LINDB',  # Lei de Introdução às Normas do Direito Brasileiro
    ]

    # =========================================================================
    # MAIN METHODS
    # =========================================================================

    def extract_references(self, content: str, document_name: str = "") -> LegalChecklist:
        """
        Extrai todas as referências legais do conteúdo.
        """
        logger.info(f"📜 Extraindo referências legais de: {document_name or 'documento'}")

        checklist = LegalChecklist(document_name=document_name)

        # =====================================================================
        # PRECEDENTES VINCULANTES (Art. 927 CPC)
        # =====================================================================

        # I - Controle concentrado de constitucionalidade
        checklist.controle_concentrado = self._extract_pattern_group(
            content, self.PATTERNS_CONTROLE_CONCENTRADO, PrecedentCategory.CONTROLE_CONCENTRADO
        )

        # II - Súmulas vinculantes
        checklist.sumulas_vinculantes = self._extract_pattern_group(
            content, self.PATTERNS_SUMULA_VINCULANTE, PrecedentCategory.SUMULA_VINCULANTE
        )

        # III - IAC
        checklist.iac = self._extract_pattern_group(
            content, self.PATTERNS_IAC, PrecedentCategory.IAC
        )

        # IV - IRDR
        checklist.irdr = self._extract_pattern_group(
            content, self.PATTERNS_IRDR, PrecedentCategory.IRDR
        )

        # V - Recursos repetitivos e temas
        checklist.recursos_repetitivos = self._extract_pattern_group(
            content, self.PATTERNS_RECURSO_REPETITIVO, PrecedentCategory.RECURSO_REPETITIVO
        )
        checklist.temas_repetitivos = self._extract_pattern_group(
            content, self.PATTERNS_TEMA, PrecedentCategory.RECURSO_REPETITIVO
        )

        # VI - Súmulas dos tribunais superiores
        checklist.sumulas_stf = self._extract_pattern_group(
            content, self.PATTERNS_SUMULA_STF, PrecedentCategory.SUMULA_STF
        )
        checklist.sumulas_stj = self._extract_pattern_group(
            content, self.PATTERNS_SUMULA_STJ, PrecedentCategory.SUMULA_STJ
        )
        checklist.sumulas_tst = self._extract_pattern_group(
            content, self.PATTERNS_SUMULA_TST, PrecedentCategory.SUMULA_TST
        )
        checklist.sumulas_tse = self._extract_pattern_group(
            content, self.PATTERNS_SUMULA_TSE, PrecedentCategory.SUMULA_TSE
        )

        # Orientações Jurisprudenciais (TST)
        checklist.ojs_tst = self._extract_pattern_group(
            content, self.PATTERNS_OJ_TST, PrecedentCategory.OJ_TST
        )

        # =====================================================================
        # DISPOSITIVOS LEGAIS - CONSTITUIÇÃO
        # =====================================================================

        checklist.constituicao = self._extract_pattern_group(
            content, self.PATTERNS_CONSTITUICAO, PrecedentCategory.CONSTITUICAO
        )
        checklist.emendas_constitucionais = self._extract_pattern_group(
            content, self.PATTERNS_EMENDA_CONSTITUCIONAL, PrecedentCategory.EMENDA_CONSTITUCIONAL
        )
        checklist.adct = self._extract_pattern_group(
            content, self.PATTERNS_ADCT, PrecedentCategory.ADCT
        )

        # =====================================================================
        # DISPOSITIVOS LEGAIS - LEGISLAÇÃO INFRACONSTITUCIONAL
        # =====================================================================

        checklist.codigos = self._extract_codigos(content)
        checklist.estatutos = self._extract_estatutos(content)

        checklist.leis_complementares = self._extract_pattern_group(
            content, self.PATTERNS_LEI_COMPLEMENTAR, PrecedentCategory.LEI_COMPLEMENTAR
        )
        checklist.leis_federais = self._extract_pattern_group(
            content, self.PATTERNS_LEI, PrecedentCategory.LEI_FEDERAL
        )
        checklist.decretos_lei = self._extract_pattern_group(
            content, self.PATTERNS_DECRETO_LEI, PrecedentCategory.DECRETO_LEI
        )
        checklist.decretos = self._extract_pattern_group(
            content, self.PATTERNS_DECRETO, PrecedentCategory.DECRETO
        )
        checklist.medidas_provisorias = self._extract_pattern_group(
            content, self.PATTERNS_MP, PrecedentCategory.MEDIDA_PROVISORIA
        )

        # =====================================================================
        # ATOS NORMATIVOS INFRALEGAIS
        # =====================================================================

        checklist.resolucoes = self._extract_pattern_group(
            content, self.PATTERNS_RESOLUCAO, PrecedentCategory.RESOLUCAO
        )
        checklist.portarias = self._extract_pattern_group(
            content, self.PATTERNS_PORTARIA, PrecedentCategory.PORTARIA
        )
        checklist.instrucoes_normativas = self._extract_pattern_group(
            content, self.PATTERNS_INSTRUCAO_NORMATIVA, PrecedentCategory.INSTRUCAO_NORMATIVA
        )

        # =====================================================================
        # ENUNCIADOS E ORIENTAÇÕES
        # =====================================================================

        checklist.enunciados = self._extract_pattern_group(
            content, self.PATTERNS_ENUNCIADO, PrecedentCategory.ENUNCIADO
        )

        # =====================================================================
        # TRATADOS INTERNACIONAIS
        # =====================================================================

        checklist.tratados = self._extract_tratados(content)

        # =====================================================================
        # OUTROS JULGADOS RELEVANTES
        # =====================================================================

        checklist.outros_julgados = self._extract_pattern_group(
            content, self.PATTERNS_JULGADOS, PrecedentCategory.ORIENTACAO_PLENARIO
        )

        # =====================================================================
        # CALCULAR TOTAL
        # =====================================================================

        checklist.total_references = (
            # Precedentes vinculantes
            len(checklist.controle_concentrado) +
            len(checklist.sumulas_vinculantes) +
            len(checklist.iac) +
            len(checklist.irdr) +
            len(checklist.recursos_repetitivos) +
            len(checklist.temas_repetitivos) +
            len(checklist.sumulas_stf) +
            len(checklist.sumulas_stj) +
            len(checklist.sumulas_tst) +
            len(checklist.sumulas_tse) +
            len(checklist.ojs_tst) +
            # Constituição
            len(checklist.constituicao) +
            len(checklist.emendas_constitucionais) +
            len(checklist.adct) +
            # Legislação infraconstitucional
            len(checklist.codigos) +
            len(checklist.estatutos) +
            len(checklist.leis_complementares) +
            len(checklist.leis_federais) +
            len(checklist.decretos_lei) +
            len(checklist.decretos) +
            len(checklist.medidas_provisorias) +
            # Atos infralegais
            len(checklist.resolucoes) +
            len(checklist.portarias) +
            len(checklist.instrucoes_normativas) +
            # Enunciados
            len(checklist.enunciados) +
            # Tratados
            len(checklist.tratados) +
            # Outros
            len(checklist.outros_julgados)
        )

        logger.info(f"   Total de referências extraídas: {checklist.total_references}")

        return checklist

    def generate_markdown_checklist(
        self,
        checklist: LegalChecklist,
        include_counts: bool = True,
        include_empty_sections: bool = False,
    ) -> str:
        """
        Gera checklist formatado em Markdown.
        """
        sections = []

        # Header
        sections.append("---")
        sections.append("")
        sections.append("## 📋 CHECKLIST DE REFERÊNCIAS LEGAIS")
        sections.append("")
        sections.append(f"*Total de referências: {checklist.total_references}*")
        sections.append("")

        # =====================================================================
        # PRECEDENTES VINCULANTES (Art. 927 CPC)
        # =====================================================================
        sections.append("### ⚖️ PRECEDENTES VINCULANTES (Art. 927, CPC)")
        sections.append("")

        # I - Controle concentrado
        if checklist.controle_concentrado or include_empty_sections:
            sections.append("#### I. Decisões em Controle Concentrado de Constitucionalidade (STF)")
            sections.append("*ADI, ADC, ADPF, ADO*")
            sections.append("")
            if checklist.controle_concentrado:
                for ref in sorted(checklist.controle_concentrado, key=lambda x: x.identifier):
                    count_str = f" ({ref.count}x)" if include_counts and ref.count > 1 else ""
                    sections.append(f"- [ ] {ref.identifier}{count_str}")
            else:
                sections.append("- *Nenhuma referência encontrada*")
            sections.append("")

        # II - Súmulas vinculantes
        if checklist.sumulas_vinculantes or include_empty_sections:
            sections.append("#### II. Súmulas Vinculantes (STF)")
            sections.append("")
            if checklist.sumulas_vinculantes:
                for ref in sorted(checklist.sumulas_vinculantes, key=lambda x: int(re.sub(r'\D', '', x.number) or 0)):
                    count_str = f" ({ref.count}x)" if include_counts and ref.count > 1 else ""
                    sections.append(f"- [ ] {ref.identifier}{count_str}")
            else:
                sections.append("- *Nenhuma referência encontrada*")
            sections.append("")

        # III - IAC
        if checklist.iac or include_empty_sections:
            sections.append("#### III. Incidentes de Assunção de Competência (IAC)")
            sections.append("")
            if checklist.iac:
                for ref in sorted(checklist.iac, key=lambda x: x.identifier):
                    count_str = f" ({ref.count}x)" if include_counts and ref.count > 1 else ""
                    sections.append(f"- [ ] {ref.identifier}{count_str}")
            else:
                sections.append("- *Nenhuma referência encontrada*")
            sections.append("")

        # IV - IRDR
        if checklist.irdr or include_empty_sections:
            sections.append("#### IV. Incidentes de Resolução de Demandas Repetitivas (IRDR)")
            sections.append("")
            if checklist.irdr:
                for ref in sorted(checklist.irdr, key=lambda x: x.identifier):
                    count_str = f" ({ref.count}x)" if include_counts and ref.count > 1 else ""
                    sections.append(f"- [ ] {ref.identifier}{count_str}")
            else:
                sections.append("- *Nenhuma referência encontrada*")
            sections.append("")

        # V - Recursos Repetitivos
        if checklist.recursos_repetitivos or checklist.temas_repetitivos or include_empty_sections:
            sections.append("#### V. Recursos Extraordinário e Especial Repetitivos")
            sections.append("")

            if checklist.temas_repetitivos:
                sections.append("**Temas de Repercussão Geral / Repetitivos:**")
                for ref in sorted(checklist.temas_repetitivos, key=lambda x: int(re.sub(r'\D', '', x.number) or 0)):
                    count_str = f" ({ref.count}x)" if include_counts and ref.count > 1 else ""
                    sections.append(f"- [ ] {ref.identifier}{count_str}")
                sections.append("")

            if checklist.recursos_repetitivos:
                sections.append("**Recursos Repetitivos:**")
                for ref in sorted(checklist.recursos_repetitivos, key=lambda x: x.identifier):
                    count_str = f" ({ref.count}x)" if include_counts and ref.count > 1 else ""
                    sections.append(f"- [ ] {ref.identifier}{count_str}")
                sections.append("")

            if not checklist.recursos_repetitivos and not checklist.temas_repetitivos:
                sections.append("- *Nenhuma referência encontrada*")
                sections.append("")

        # VI - Súmulas dos Tribunais Superiores
        has_sumulas = (checklist.sumulas_stf or checklist.sumulas_stj or
                       checklist.sumulas_tst or checklist.sumulas_tse or checklist.ojs_tst)
        if has_sumulas or include_empty_sections:
            sections.append("#### VI. Súmulas e Orientações dos Tribunais Superiores")
            sections.append("")

            if checklist.sumulas_stf:
                sections.append("**Súmulas do STF (matéria constitucional):**")
                for ref in sorted(checklist.sumulas_stf, key=lambda x: int(re.sub(r'\D', '', x.number) or 0)):
                    count_str = f" ({ref.count}x)" if include_counts and ref.count > 1 else ""
                    sections.append(f"- [ ] {ref.identifier}{count_str}")
                sections.append("")

            if checklist.sumulas_stj:
                sections.append("**Súmulas do STJ (matéria infraconstitucional):**")
                for ref in sorted(checklist.sumulas_stj, key=lambda x: int(re.sub(r'\D', '', x.number) or 0)):
                    count_str = f" ({ref.count}x)" if include_counts and ref.count > 1 else ""
                    sections.append(f"- [ ] {ref.identifier}{count_str}")
                sections.append("")

            if checklist.sumulas_tst:
                sections.append("**Súmulas do TST (matéria trabalhista):**")
                for ref in sorted(checklist.sumulas_tst, key=lambda x: int(re.sub(r'\D', '', x.number) or 0)):
                    count_str = f" ({ref.count}x)" if include_counts and ref.count > 1 else ""
                    sections.append(f"- [ ] {ref.identifier}{count_str}")
                sections.append("")

            if checklist.ojs_tst:
                sections.append("**Orientações Jurisprudenciais do TST:**")
                for ref in sorted(checklist.ojs_tst, key=lambda x: int(re.sub(r'\D', '', x.number) or 0)):
                    count_str = f" ({ref.count}x)" if include_counts and ref.count > 1 else ""
                    sections.append(f"- [ ] {ref.identifier}{count_str}")
                sections.append("")

            if checklist.sumulas_tse:
                sections.append("**Súmulas do TSE (matéria eleitoral):**")
                for ref in sorted(checklist.sumulas_tse, key=lambda x: int(re.sub(r'\D', '', x.number) or 0)):
                    count_str = f" ({ref.count}x)" if include_counts and ref.count > 1 else ""
                    sections.append(f"- [ ] {ref.identifier}{count_str}")
                sections.append("")

        # =====================================================================
        # DISPOSITIVOS LEGAIS - CONSTITUIÇÃO
        # =====================================================================
        sections.append("### 📖 DISPOSITIVOS CONSTITUCIONAIS")
        sections.append("")

        # Emendas Constitucionais
        if checklist.emendas_constitucionais or include_empty_sections:
            sections.append("#### Emendas Constitucionais")
            sections.append("")
            if checklist.emendas_constitucionais:
                for ref in sorted(checklist.emendas_constitucionais, key=lambda x: int(re.sub(r'\D', '', x.number) or 0)):
                    count_str = f" ({ref.count}x)" if include_counts and ref.count > 1 else ""
                    sections.append(f"- [ ] {ref.identifier}{count_str}")
            else:
                sections.append("- *Nenhuma referência encontrada*")
            sections.append("")

        # Constituição Federal
        if checklist.constituicao or include_empty_sections:
            sections.append("#### Artigos da Constituição Federal")
            sections.append("")
            if checklist.constituicao:
                for ref in sorted(checklist.constituicao, key=lambda x: int(re.sub(r'\D', '', x.number) or 0)):
                    count_str = f" ({ref.count}x)" if include_counts and ref.count > 1 else ""
                    sections.append(f"- [ ] {ref.identifier}{count_str}")
            else:
                sections.append("- *Nenhuma referência encontrada*")
            sections.append("")

        # ADCT
        if checklist.adct or include_empty_sections:
            sections.append("#### ADCT (Atos das Disposições Constitucionais Transitórias)")
            sections.append("")
            if checklist.adct:
                for ref in sorted(checklist.adct, key=lambda x: int(re.sub(r'\D', '', x.number) or 0)):
                    count_str = f" ({ref.count}x)" if include_counts and ref.count > 1 else ""
                    sections.append(f"- [ ] {ref.identifier}{count_str}")
            else:
                sections.append("- *Nenhuma referência encontrada*")
            sections.append("")

        # =====================================================================
        # DISPOSITIVOS LEGAIS - LEGISLAÇÃO INFRACONSTITUCIONAL
        # =====================================================================
        sections.append("### 📚 LEGISLAÇÃO INFRACONSTITUCIONAL")
        sections.append("")

        # Códigos
        if checklist.codigos or include_empty_sections:
            sections.append("#### Códigos")
            sections.append("")
            if checklist.codigos:
                for ref in sorted(checklist.codigos, key=lambda x: x.identifier):
                    count_str = f" ({ref.count}x)" if include_counts and ref.count > 1 else ""
                    sections.append(f"- [ ] {ref.identifier}{count_str}")
            else:
                sections.append("- *Nenhuma referência encontrada*")
            sections.append("")

        # Estatutos
        if checklist.estatutos or include_empty_sections:
            sections.append("#### Estatutos")
            sections.append("")
            if checklist.estatutos:
                for ref in sorted(checklist.estatutos, key=lambda x: x.identifier):
                    count_str = f" ({ref.count}x)" if include_counts and ref.count > 1 else ""
                    sections.append(f"- [ ] {ref.identifier}{count_str}")
            else:
                sections.append("- *Nenhuma referência encontrada*")
            sections.append("")

        # Leis Complementares
        if checklist.leis_complementares or include_empty_sections:
            sections.append("#### Leis Complementares")
            sections.append("")
            if checklist.leis_complementares:
                for ref in sorted(checklist.leis_complementares, key=lambda x: x.identifier):
                    count_str = f" ({ref.count}x)" if include_counts and ref.count > 1 else ""
                    sections.append(f"- [ ] {ref.identifier}{count_str}")
            else:
                sections.append("- *Nenhuma referência encontrada*")
            sections.append("")

        # Leis Federais
        if checklist.leis_federais or include_empty_sections:
            sections.append("#### Leis Federais")
            sections.append("")
            if checklist.leis_federais:
                for ref in sorted(checklist.leis_federais, key=lambda x: x.identifier):
                    count_str = f" ({ref.count}x)" if include_counts and ref.count > 1 else ""
                    sections.append(f"- [ ] {ref.identifier}{count_str}")
            else:
                sections.append("- *Nenhuma referência encontrada*")
            sections.append("")

        # Decretos-Lei
        if checklist.decretos_lei or include_empty_sections:
            sections.append("#### Decretos-Lei")
            sections.append("")
            if checklist.decretos_lei:
                for ref in sorted(checklist.decretos_lei, key=lambda x: x.identifier):
                    count_str = f" ({ref.count}x)" if include_counts and ref.count > 1 else ""
                    sections.append(f"- [ ] {ref.identifier}{count_str}")
            else:
                sections.append("- *Nenhuma referência encontrada*")
            sections.append("")

        # Decretos
        if checklist.decretos or include_empty_sections:
            sections.append("#### Decretos")
            sections.append("")
            if checklist.decretos:
                for ref in sorted(checklist.decretos, key=lambda x: x.identifier):
                    count_str = f" ({ref.count}x)" if include_counts and ref.count > 1 else ""
                    sections.append(f"- [ ] {ref.identifier}{count_str}")
            else:
                sections.append("- *Nenhuma referência encontrada*")
            sections.append("")

        # Medidas Provisórias
        if checklist.medidas_provisorias or include_empty_sections:
            sections.append("#### Medidas Provisórias")
            sections.append("")
            if checklist.medidas_provisorias:
                for ref in sorted(checklist.medidas_provisorias, key=lambda x: x.identifier):
                    count_str = f" ({ref.count}x)" if include_counts and ref.count > 1 else ""
                    sections.append(f"- [ ] {ref.identifier}{count_str}")
            else:
                sections.append("- *Nenhuma referência encontrada*")
            sections.append("")

        # =====================================================================
        # ATOS NORMATIVOS INFRALEGAIS
        # =====================================================================
        has_infralegais = checklist.resolucoes or checklist.portarias or checklist.instrucoes_normativas
        if has_infralegais or include_empty_sections:
            sections.append("### 📝 ATOS NORMATIVOS INFRALEGAIS")
            sections.append("")

            if checklist.resolucoes:
                sections.append("#### Resoluções")
                sections.append("")
                for ref in sorted(checklist.resolucoes, key=lambda x: x.identifier):
                    count_str = f" ({ref.count}x)" if include_counts and ref.count > 1 else ""
                    sections.append(f"- [ ] {ref.identifier}{count_str}")
                sections.append("")

            if checklist.instrucoes_normativas:
                sections.append("#### Instruções Normativas")
                sections.append("")
                for ref in sorted(checklist.instrucoes_normativas, key=lambda x: x.identifier):
                    count_str = f" ({ref.count}x)" if include_counts and ref.count > 1 else ""
                    sections.append(f"- [ ] {ref.identifier}{count_str}")
                sections.append("")

            if checklist.portarias:
                sections.append("#### Portarias")
                sections.append("")
                for ref in sorted(checklist.portarias, key=lambda x: x.identifier):
                    count_str = f" ({ref.count}x)" if include_counts and ref.count > 1 else ""
                    sections.append(f"- [ ] {ref.identifier}{count_str}")
                sections.append("")

        # =====================================================================
        # ENUNCIADOS
        # =====================================================================
        if checklist.enunciados or include_empty_sections:
            sections.append("### 📌 ENUNCIADOS E ORIENTAÇÕES")
            sections.append("*CJF, FONAJE, Jornadas de Direito*")
            sections.append("")
            if checklist.enunciados:
                for ref in sorted(checklist.enunciados, key=lambda x: int(re.sub(r'\D', '', x.number) or 0)):
                    count_str = f" ({ref.count}x)" if include_counts and ref.count > 1 else ""
                    sections.append(f"- [ ] {ref.identifier}{count_str}")
            else:
                sections.append("- *Nenhuma referência encontrada*")
            sections.append("")

        # =====================================================================
        # TRATADOS INTERNACIONAIS
        # =====================================================================
        if checklist.tratados or include_empty_sections:
            sections.append("### 🌐 TRATADOS E CONVENÇÕES INTERNACIONAIS")
            sections.append("")
            if checklist.tratados:
                for ref in sorted(checklist.tratados, key=lambda x: x.identifier):
                    count_str = f" ({ref.count}x)" if include_counts and ref.count > 1 else ""
                    sections.append(f"- [ ] {ref.identifier}{count_str}")
            else:
                sections.append("- *Nenhuma referência encontrada*")
            sections.append("")

        # =====================================================================
        # OUTROS JULGADOS RELEVANTES
        # =====================================================================
        if checklist.outros_julgados or include_empty_sections:
            sections.append("### 📑 OUTROS JULGADOS RELEVANTES")
            sections.append("*HC, MS, MI, RMS, AgRg, ED, Rcl*")
            sections.append("")
            if checklist.outros_julgados:
                for ref in sorted(checklist.outros_julgados, key=lambda x: x.identifier):
                    count_str = f" ({ref.count}x)" if include_counts and ref.count > 1 else ""
                    sections.append(f"- [ ] {ref.identifier}{count_str}")
            else:
                sections.append("- *Nenhuma referência encontrada*")
            sections.append("")

        # Footer
        sections.append("---")
        sections.append("")
        sections.append("*Checklist gerado automaticamente pelo Iudex. Verifique a atualização e vigência dos dispositivos.*")
        sections.append("")

        return "\n".join(sections)

    def append_checklist_to_content(
        self,
        content: str,
        document_name: str = "",
        include_counts: bool = True,
    ) -> Tuple[str, LegalChecklist]:
        """
        Extrai referências e adiciona checklist ao final do conteúdo.
        Retorna (conteúdo com checklist, checklist extraído).
        """
        checklist = self.extract_references(content, document_name)
        markdown = self.generate_markdown_checklist(checklist, include_counts)

        return content + "\n\n" + markdown, checklist

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _extract_pattern_group(
        self,
        content: str,
        patterns: List[str],
        category: PrecedentCategory,
    ) -> List[LegalReference]:
        """
        Extrai referências usando um grupo de patterns.
        """
        references: Dict[str, LegalReference] = {}

        for pattern in patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                # Extrair número principal (primeiro grupo de captura)
                groups = match.groups()
                number = groups[0] if groups else match.group(0)
                number = self._normalize_number(number)

                # Extrair estado/UF se disponível
                state = groups[1] if len(groups) > 1 and groups[1] else None

                # Criar identificador único
                identifier = self._build_identifier(category, number, state, match.group(0))

                # Extrair contexto
                start = max(0, match.start() - 50)
                end = min(len(content), match.end() + 50)
                context = content[start:end].strip()

                if identifier in references:
                    references[identifier].count += 1
                else:
                    references[identifier] = LegalReference(
                        category=category,
                        identifier=identifier,
                        number=number,
                        court=state,
                        context=context,
                    )

        return list(references.values())

    def _extract_codigos(self, content: str) -> List[LegalReference]:
        """
        Extrai referências a códigos (tratamento especial).
        """
        codigos_map = {
            'CC': 'Código Civil (CC)',
            'CP': 'Código Penal (CP)',
            'CPC': 'Código de Processo Civil (CPC)',
            'CPP': 'Código de Processo Penal (CPP)',
            'CTN': 'Código Tributário Nacional (CTN)',
            'CDC': 'Código de Defesa do Consumidor (CDC)',
            'CTB': 'Código de Trânsito Brasileiro (CTB)',
            'CLT': 'Consolidação das Leis do Trabalho (CLT)',
            'ECA': 'Estatuto da Criança e do Adolescente (ECA)',
            'LINDB': 'Lei de Introdução às Normas do Direito Brasileiro (LINDB)',
            'ELEITORAL': 'Código Eleitoral',
            'COMERCIAL': 'Código Comercial',
            'FLORESTAL': 'Código Florestal',
            'MINERAÇÃO': 'Código de Mineração',
            'ÁGUAS': 'Código de Águas',
            'AERONÁUTICA': 'Código Brasileiro de Aeronáutica',
        }

        references: Dict[str, LegalReference] = {}

        for pattern in self.PATTERNS_CODIGO:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                matched = match.group(0).strip()
                matched_upper = matched.upper()

                # Normalizar sigla
                sigla = matched_upper.split('/')[0].strip()

                # Tentar identificar o código
                identifier = None
                key_found = None

                for key, name in codigos_map.items():
                    # Verificar sigla direta
                    if key in sigla:
                        identifier = name
                        key_found = key
                        break
                    # Verificar nome por extenso
                    name_upper = name.upper()
                    if any(word in matched_upper for word in name_upper.split() if len(word) > 3):
                        identifier = name
                        key_found = key
                        break

                # Fallback para padrões específicos
                if not identifier:
                    if 'TRÂNSITO' in matched_upper or 'TRANSITO' in matched_upper:
                        identifier = codigos_map['CTB']
                        key_found = 'CTB'
                    elif 'ELEITORAL' in matched_upper:
                        identifier = codigos_map['ELEITORAL']
                        key_found = 'ELEITORAL'
                    elif 'FLORESTAL' in matched_upper:
                        identifier = codigos_map['FLORESTAL']
                        key_found = 'FLORESTAL'
                    elif 'LINDB' in matched_upper or 'INTRODUÇÃO' in matched_upper:
                        identifier = codigos_map['LINDB']
                        key_found = 'LINDB'

                if identifier:
                    if identifier in references:
                        references[identifier].count += 1
                    else:
                        references[identifier] = LegalReference(
                            category=PrecedentCategory.CODIGO,
                            identifier=identifier,
                            number=key_found or matched,
                        )

        return list(references.values())

    def _extract_estatutos(self, content: str) -> List[LegalReference]:
        """
        Extrai referências a estatutos (tratamento especial).
        """
        estatutos_map = {
            'criança': 'Estatuto da Criança e do Adolescente (ECA)',
            'adolescente': 'Estatuto da Criança e do Adolescente (ECA)',
            'idoso': 'Estatuto do Idoso',
            'cidade': 'Estatuto da Cidade',
            'terra': 'Estatuto da Terra',
            'desarmamento': 'Estatuto do Desarmamento',
            'advocacia': 'Estatuto da Advocacia (EAOAB)',
            'oab': 'Estatuto da Advocacia (EAOAB)',
            'estrangeiro': 'Estatuto do Estrangeiro',
            'refugiado': 'Estatuto do Refugiado',
            'igualdade racial': 'Estatuto da Igualdade Racial',
            'pessoa com deficiência': 'Estatuto da Pessoa com Deficiência',
            'deficiência': 'Estatuto da Pessoa com Deficiência',
            'juventude': 'Estatuto da Juventude',
        }

        references: Dict[str, LegalReference] = {}

        for pattern in self.PATTERNS_ESTATUTO:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                matched = match.group(0).strip().lower()

                for key, identifier in estatutos_map.items():
                    if key in matched:
                        if identifier in references:
                            references[identifier].count += 1
                        else:
                            references[identifier] = LegalReference(
                                category=PrecedentCategory.ESTATUTO,
                                identifier=identifier,
                                number=key,
                            )
                        break

        return list(references.values())

    def _extract_tratados(self, content: str) -> List[LegalReference]:
        """
        Extrai referências a tratados internacionais (tratamento especial).
        """
        tratados_map = {
            'viena': 'Convenção de Viena',
            'genebra': 'Convenção de Genebra',
            'haia': 'Convenção da Haia',
            'nova york': 'Convenção de Nova York',
            'montego bay': 'Convenção de Montego Bay',
            'americana': 'Convenção Americana de Direitos Humanos',
            'são josé': 'Pacto de São José da Costa Rica',
            'costa rica': 'Pacto de São José da Costa Rica',
            'oit': 'Convenção da OIT',
            'roma': 'Estatuto de Roma / Tratado de Roma',
            'lisboa': 'Tratado de Lisboa',
            'maastricht': 'Tratado de Maastricht',
            'assunção': 'Tratado de Assunção (Mercosul)',
            'declaração universal': 'Declaração Universal dos Direitos Humanos',
            'pidcp': 'Pacto Internacional dos Direitos Civis e Políticos',
            'pidesc': 'Pacto Internacional dos Direitos Econômicos, Sociais e Culturais',
            'direitos da criança': 'Convenção sobre os Direitos da Criança',
        }

        references: Dict[str, LegalReference] = {}

        for pattern in self.PATTERNS_TRATADO:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                matched = match.group(0).strip().lower()

                for key, identifier in tratados_map.items():
                    if key in matched:
                        if identifier in references:
                            references[identifier].count += 1
                        else:
                            references[identifier] = LegalReference(
                                category=PrecedentCategory.TRATADO,
                                identifier=identifier,
                                number=key,
                            )
                        break

        return list(references.values())

    def _normalize_number(self, number: str) -> str:
        """
        Normaliza número removendo pontos e espaços.
        """
        if not number:
            return ""
        return re.sub(r'[.\s]', '', str(number))

    def _build_identifier(
        self,
        category: PrecedentCategory,
        number: str,
        state: Optional[str],
        original: str,
    ) -> str:
        """
        Constrói identificador legível para a referência.
        """
        prefixes = {
            PrecedentCategory.CONTROLE_CONCENTRADO: self._get_adi_prefix(original),
            PrecedentCategory.SUMULA_VINCULANTE: "Súmula Vinculante",
            PrecedentCategory.SUMULA_STF: "Súmula STF",
            PrecedentCategory.SUMULA_STJ: "Súmula STJ",
            PrecedentCategory.SUMULA_TST: "Súmula TST",
            PrecedentCategory.SUMULA_TSE: "Súmula TSE",
            PrecedentCategory.OJ_TST: "OJ",
            PrecedentCategory.IAC: "IAC",
            PrecedentCategory.IRDR: "IRDR",
            PrecedentCategory.RECURSO_REPETITIVO: self._get_recurso_prefix(original),
            PrecedentCategory.CONSTITUICAO: "CF, Art.",
            PrecedentCategory.EMENDA_CONSTITUCIONAL: "EC",
            PrecedentCategory.ADCT: "ADCT, Art.",
            PrecedentCategory.LEI_FEDERAL: "Lei",
            PrecedentCategory.LEI_COMPLEMENTAR: "LC",
            PrecedentCategory.DECRETO: "Decreto",
            PrecedentCategory.DECRETO_LEI: "Decreto-Lei",
            PrecedentCategory.MEDIDA_PROVISORIA: "MP",
            PrecedentCategory.RESOLUCAO: "Resolução",
            PrecedentCategory.PORTARIA: "Portaria",
            PrecedentCategory.INSTRUCAO_NORMATIVA: "IN",
            PrecedentCategory.ENUNCIADO: "Enunciado",
            PrecedentCategory.ORIENTACAO_PLENARIO: self._get_julgado_prefix(original),
        }

        prefix = prefixes.get(category, "")

        # Formatar número
        formatted_number = self._format_number(number)

        if state:
            return f"{prefix} {formatted_number}/{state}"
        return f"{prefix} {formatted_number}"

    def _get_julgado_prefix(self, original: str) -> str:
        """Determina o prefixo correto para julgados diversos."""
        upper = original.upper()
        julgados_map = {
            'ARESP': 'AREsp',
            'ARE': 'ARE',
            'ERESP': 'EREsp',
            'ERE': 'ERE',
            'AGINT': 'AgInt',
            'AGRG': 'AgRg',
            'EDCL': 'EDcl',
            'RHC': 'RHC',
            'RMS': 'RMS',
            'HC': 'HC',
            'HD': 'HD',
            'MS': 'MS',
            'MI': 'MI',
            'RCL': 'Rcl',
            'PET': 'Pet',
            'INQ': 'Inq',
            'AC': 'AC',
            'AP': 'AP',
            'SS': 'SS',
            'SL': 'SL',
            'ED': 'ED',
        }
        for key, prefix in julgados_map.items():
            if key in upper:
                return prefix
        return ""

    def _get_adi_prefix(self, original: str) -> str:
        """Determina o prefixo correto para ações de controle concentrado."""
        upper = original.upper()
        if 'ADPF' in upper:
            return 'ADPF'
        elif 'ADC' in upper:
            return 'ADC'
        elif 'ADO' in upper:
            return 'ADO'
        else:
            return 'ADI'

    def _get_recurso_prefix(self, original: str) -> str:
        """Determina o prefixo correto para recursos."""
        upper = original.upper()
        if 'RESP' in upper or 'RECURSO ESPECIAL' in upper:
            return 'REsp'
        elif 'TEMA' in upper:
            return 'Tema'
        else:
            return 'RE'

    def _format_number(self, number: str) -> str:
        """Formata número com pontos para legibilidade."""
        number = re.sub(r'\D', '', str(number))
        if len(number) > 3:
            # Adicionar pontos a cada 3 dígitos da direita
            reversed_num = number[::-1]
            chunks = [reversed_num[i:i+3] for i in range(0, len(reversed_num), 3)]
            return '.'.join(chunks)[::-1]
        return number

    # =========================================================================
    # HEARING/MEETING CHECKLIST METHODS
    # =========================================================================

    def _format_timestamp(self, seconds: Optional[float]) -> str:
        """Formata timestamp em segundos para HH:MM:SS."""
        if seconds is None:
            return ""
        total = int(max(0, seconds))
        hours = total // 3600
        minutes = (total % 3600) // 60
        secs = total % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def _get_speaker_label(self, segment: Dict, speakers: List[Dict]) -> str:
        """Obtém o label do falante para um segmento."""
        speaker_id = segment.get("speaker_id")
        speaker_label = segment.get("speaker_label", "")

        # Try to find speaker name from speakers list
        if speaker_id:
            for sp in speakers:
                if sp.get("speaker_id") == speaker_id:
                    name = sp.get("name") or sp.get("label")
                    if name:
                        return name

        # Fallback to segment's speaker_label
        if speaker_label:
            return speaker_label

        return "Falante Desconhecido"

    def generate_hearing_checklist(
        self,
        segments: List[Dict[str, Any]],
        speakers: List[Dict[str, Any]],
        formatted_content: Optional[str] = None,
        document_name: str = "hearing",
        include_timeline: bool = True,
        group_by_speaker: bool = True,
    ) -> Dict[str, Any]:
        """
        Extrai referências legais de audiência/reunião com atribuição ao falante.

        Args:
            segments: Lista de segmentos da transcrição
            speakers: Lista de falantes
            formatted_content: Texto formatado (opcional)
            document_name: Nome do documento
            include_timeline: Incluir timeline das referências
            group_by_speaker: Agrupar por falante

        Returns:
            {
                "document_name": str,
                "total_references": int,
                "by_speaker": {
                    "Juiz Dr. Silva": [refs...],
                    "Advogado Defesa": [refs...],
                },
                "by_category": {
                    "legislacao": [...],
                    "jurisprudencia": [...],
                },
                "timeline": [
                    {"timestamp": "00:05:23", "speaker": "Juiz", "ref": "Art. 212 CPP", ...}
                ],
                "checklist_markdown": str
            }
        """
        logger.info(f"📜 Extraindo referências de audiência: {document_name}")

        by_speaker: Dict[str, List[Dict]] = {}
        by_category: Dict[str, List[Dict]] = {}
        timeline: List[Dict] = []
        all_refs_set: Set[str] = set()  # To count unique references

        # Process each segment
        for segment in segments:
            text = segment.get("text", "")
            if not text.strip():
                continue

            speaker_label = self._get_speaker_label(segment, speakers)
            timestamp_seconds = segment.get("start")
            timestamp_str = self._format_timestamp(timestamp_seconds)
            segment_id = segment.get("id", "")

            # Extract references from this segment
            segment_checklist = self.extract_references(text, "")

            # Process extracted references
            ref_lists = [
                ("controle_concentrado", segment_checklist.controle_concentrado),
                ("sumulas_vinculantes", segment_checklist.sumulas_vinculantes),
                ("sumulas_stf", segment_checklist.sumulas_stf),
                ("sumulas_stj", segment_checklist.sumulas_stj),
                ("sumulas_tst", segment_checklist.sumulas_tst),
                ("sumulas_tse", segment_checklist.sumulas_tse),
                ("ojs_tst", segment_checklist.ojs_tst),
                ("iac", segment_checklist.iac),
                ("irdr", segment_checklist.irdr),
                ("recursos_repetitivos", segment_checklist.recursos_repetitivos),
                ("temas_repetitivos", segment_checklist.temas_repetitivos),
                ("constituicao", segment_checklist.constituicao),
                ("emendas_constitucionais", segment_checklist.emendas_constitucionais),
                ("adct", segment_checklist.adct),
                ("leis_federais", segment_checklist.leis_federais),
                ("leis_complementares", segment_checklist.leis_complementares),
                ("decretos", segment_checklist.decretos),
                ("decretos_lei", segment_checklist.decretos_lei),
                ("medidas_provisorias", segment_checklist.medidas_provisorias),
                ("codigos", segment_checklist.codigos),
                ("estatutos", segment_checklist.estatutos),
                ("resolucoes", segment_checklist.resolucoes),
                ("portarias", segment_checklist.portarias),
                ("instrucoes_normativas", segment_checklist.instrucoes_normativas),
                ("enunciados", segment_checklist.enunciados),
                ("tratados", segment_checklist.tratados),
                ("outros_julgados", segment_checklist.outros_julgados),
            ]

            for category_name, refs in ref_lists:
                for ref in refs:
                    ref_data = {
                        "identifier": ref.identifier,
                        "category": category_name,
                        "timestamp": timestamp_str,
                        "segment_id": segment_id,
                        "context": text[:150] + "..." if len(text) > 150 else text,
                        "speaker": speaker_label,
                    }

                    all_refs_set.add(ref.identifier)

                    # Add to by_speaker
                    if speaker_label not in by_speaker:
                        by_speaker[speaker_label] = []
                    # Avoid duplicates per speaker
                    existing_ids = {r["identifier"] for r in by_speaker[speaker_label]}
                    if ref.identifier not in existing_ids:
                        by_speaker[speaker_label].append(ref_data)

                    # Add to by_category
                    if category_name not in by_category:
                        by_category[category_name] = []
                    # Avoid duplicates per category
                    existing_ids = {r["identifier"] for r in by_category[category_name]}
                    if ref.identifier not in existing_ids:
                        by_category[category_name].append(ref_data)

                    # Add to timeline
                    if include_timeline and timestamp_str:
                        timeline.append({
                            "timestamp": timestamp_str,
                            "timestamp_seconds": timestamp_seconds,
                            "speaker": speaker_label,
                            "ref": ref.identifier,
                            "category": category_name,
                            "segment_id": segment_id,
                        })

        # Sort timeline by timestamp
        timeline.sort(key=lambda x: x.get("timestamp_seconds") or 0)

        # Generate markdown
        checklist_markdown = self._generate_hearing_checklist_markdown(
            by_speaker=by_speaker,
            by_category=by_category,
            timeline=timeline if include_timeline else [],
            document_name=document_name,
            total_refs=len(all_refs_set),
            group_by_speaker=group_by_speaker,
        )

        logger.info(f"   Total de referências únicas: {len(all_refs_set)}")

        return {
            "document_name": document_name,
            "total_references": len(all_refs_set),
            "by_speaker": by_speaker,
            "by_category": by_category,
            "timeline": timeline,
            "checklist_markdown": checklist_markdown,
        }

    def _generate_hearing_checklist_markdown(
        self,
        by_speaker: Dict[str, List[Dict]],
        by_category: Dict[str, List[Dict]],
        timeline: List[Dict],
        document_name: str,
        total_refs: int,
        group_by_speaker: bool = True,
    ) -> str:
        """Gera markdown do checklist de audiência."""
        sections = []

        # Header
        sections.append("---")
        sections.append("")
        sections.append("## 📋 CHECKLIST DE REFERÊNCIAS LEGAIS - AUDIÊNCIA")
        sections.append("")
        sections.append(f"*Documento: {document_name}*")
        sections.append(f"*Total de referências únicas: {total_refs}*")
        sections.append("")

        # By Speaker section
        if group_by_speaker and by_speaker:
            sections.append("### 👤 REFERÊNCIAS POR FALANTE")
            sections.append("")

            for speaker, refs in sorted(by_speaker.items()):
                if not refs:
                    continue
                sections.append(f"#### {speaker}")
                sections.append("")
                for ref in refs:
                    timestamp = ref.get("timestamp", "")
                    ts_str = f" [{timestamp}]" if timestamp else ""
                    sections.append(f"- [ ] {ref['identifier']}{ts_str}")
                sections.append("")

        # By Category section
        if by_category:
            sections.append("### 📚 REFERÊNCIAS POR CATEGORIA")
            sections.append("")

            category_labels = {
                "controle_concentrado": "Controle Concentrado (ADI, ADC, ADPF)",
                "sumulas_vinculantes": "Súmulas Vinculantes",
                "sumulas_stf": "Súmulas STF",
                "sumulas_stj": "Súmulas STJ",
                "sumulas_tst": "Súmulas TST",
                "sumulas_tse": "Súmulas TSE",
                "ojs_tst": "Orientações Jurisprudenciais TST",
                "iac": "Incidentes de Assunção de Competência (IAC)",
                "irdr": "Incidentes de Resolução de Demandas Repetitivas (IRDR)",
                "recursos_repetitivos": "Recursos Repetitivos",
                "temas_repetitivos": "Temas de Repercussão Geral",
                "constituicao": "Constituição Federal",
                "emendas_constitucionais": "Emendas Constitucionais",
                "adct": "ADCT",
                "leis_federais": "Leis Federais",
                "leis_complementares": "Leis Complementares",
                "decretos": "Decretos",
                "decretos_lei": "Decretos-Lei",
                "medidas_provisorias": "Medidas Provisórias",
                "codigos": "Códigos",
                "estatutos": "Estatutos",
                "resolucoes": "Resoluções",
                "portarias": "Portarias",
                "instrucoes_normativas": "Instruções Normativas",
                "enunciados": "Enunciados",
                "tratados": "Tratados Internacionais",
                "outros_julgados": "Outros Julgados",
            }

            for category, refs in sorted(by_category.items()):
                if not refs:
                    continue
                label = category_labels.get(category, category)
                sections.append(f"#### {label}")
                sections.append("")
                for ref in refs:
                    speaker = ref.get("speaker", "")
                    sp_str = f" — *{speaker}*" if speaker else ""
                    sections.append(f"- [ ] {ref['identifier']}{sp_str}")
                sections.append("")

        # Timeline section
        if timeline:
            sections.append("### ⏱️ TIMELINE DE MENÇÕES")
            sections.append("")
            sections.append("| Timestamp | Falante | Referência |")
            sections.append("| :--- | :--- | :--- |")
            for entry in timeline[:50]:  # Limit to 50 entries
                ts = entry.get("timestamp", "")
                speaker = entry.get("speaker", "")
                ref = entry.get("ref", "")
                sections.append(f"| {ts} | {speaker} | {ref} |")
            if len(timeline) > 50:
                sections.append(f"| ... | *{len(timeline) - 50} mais* | ... |")
            sections.append("")

        # Footer
        sections.append("---")
        sections.append("")
        sections.append("*Checklist gerado automaticamente pelo Iudex para audiências/reuniões.*")
        sections.append("")

        return "\n".join(sections)


# Singleton
legal_checklist_generator = LegalChecklistGenerator()
