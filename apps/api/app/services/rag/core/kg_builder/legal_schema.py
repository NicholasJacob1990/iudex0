"""
Legal Schema — Entity types, relationship types, and patterns for Brazilian legal domain.

Compatível com neo4j-graphrag v1.13+ (GraphSchema, NodeType, RelationshipType, Pattern).
Usado pelo SimpleKGPipeline e também exportável como dict para uso direto.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


# =============================================================================
# NODE TYPES (dict format — para uso legado e referência)
# =============================================================================

LEGAL_NODE_TYPES: List[Dict[str, Any]] = [
    # Core legal entities (regex-extractable)
    {
        "label": "Lei",
        "description": "Lei, Decreto, MP, LC, Portaria, Resolução (legislação brasileira)",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
            {"name": "numero", "type": "STRING"},
            {"name": "ano", "type": "STRING"},
            {"name": "tipo", "type": "STRING"},
        ],
    },
    {
        "label": "Artigo",
        "description": "Artigo de lei, com parágrafo e inciso opcionais",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
            {"name": "artigo", "type": "STRING"},
            {"name": "paragrafo", "type": "STRING"},
            {"name": "inciso", "type": "STRING"},
        ],
    },
    {
        "label": "Sumula",
        "description": "Súmula (vinculante ou não) de tribunal superior",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
            {"name": "numero", "type": "STRING"},
            {"name": "tribunal", "type": "STRING"},
        ],
    },
    {
        "label": "Tribunal",
        "description": "Tribunal (STF, STJ, TST, TRF, TJ, TRT)",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
            {"name": "sigla", "type": "STRING"},
        ],
    },
    {
        "label": "Processo",
        "description": "Processo judicial (número CNJ)",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
            {"name": "numero_cnj", "type": "STRING"},
        ],
    },
    {
        "label": "Tema",
        "description": "Tema de repercussão geral (STF/STJ)",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
            {"name": "numero", "type": "STRING"},
            {"name": "tribunal", "type": "STRING"},
        ],
    },
    {
        "label": "Decisao",
        "description": "Decisão judicial específica (REsp, RE, ADI, ADPF, etc.)",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
            {"name": "tipo", "type": "STRING"},
            {"name": "numero", "type": "STRING"},
            {"name": "tribunal", "type": "STRING"},
        ],
    },
    {
        "label": "Tese",
        "description": "Tese firmada/fixada em julgamento",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
            {"name": "numero", "type": "STRING"},
        ],
    },
    {
        "label": "Doutrina",
        "description": "Citação doutrinária: autor, obra, comentário ou entendimento doutrinário",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
            {"name": "autor", "type": "STRING"},
            {"name": "obra", "type": "STRING"},
        ],
    },
    # International/Multilingual entities
    {
        "label": "CaseLaw",
        "description": "Precedente judicial (Common Law: US, UK, Commonwealth, etc.)",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
            {"name": "citation", "type": "STRING"},
            {"name": "court", "type": "STRING"},
            {"name": "year", "type": "STRING"},
            {"name": "jurisdiction", "type": "STRING"},
        ],
    },
    {
        "label": "Statute",
        "description": "Lei/Estatuto (Common Law: Act, Statute, Code)",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
            {"name": "year", "type": "STRING"},
            {"name": "jurisdiction", "type": "STRING"},
        ],
    },
    {
        "label": "Regulation",
        "description": "Regulamento/Norma administrativa (US: CFR, UK: SI, EU: Regulation)",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
            {"name": "numero", "type": "STRING"},
            {"name": "jurisdiction", "type": "STRING"},
        ],
    },
    {
        "label": "Directive",
        "description": "Diretiva da União Europeia",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
            {"name": "numero", "type": "STRING"},
            {"name": "year", "type": "STRING"},
        ],
    },
    {
        "label": "Treaty",
        "description": "Tratado internacional, convenção ou acordo multilateral",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
            {"name": "year", "type": "STRING"},
            {"name": "parties", "type": "STRING"},
        ],
    },
    {
        "label": "InternationalDecision",
        "description": "Decisão de corte internacional (ICJ, ECHR, ICC, etc.)",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
            {"name": "court", "type": "STRING"},
            {"name": "year", "type": "STRING"},
        ],
    },
    # ArgumentRAG entities (LLM-extractable)
    {
        "label": "Claim",
        "description": "Tese ou contratese jurídica, alegação ou proposição",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
            {"name": "claim_type", "type": "STRING"},
            {"name": "polarity", "type": "INTEGER"},
        ],
    },
    {
        "label": "Evidence",
        "description": "Evidência documental, jurisprudencial ou doutrinária",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
            {"name": "evidence_type", "type": "STRING"},
            {"name": "weight", "type": "FLOAT"},
        ],
    },
    {
        "label": "Actor",
        "description": "Parte, advogado, juiz, relator ou outro ator processual",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
            {"name": "role", "type": "STRING"},
        ],
    },
    {
        "label": "Issue",
        "description": "Questão jurídica controvertida",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
            {"name": "domain", "type": "STRING"},
        ],
    },
    # Semantic entities (LLM-extractable)
    {
        "label": "SemanticEntity",
        "description": "Conceito, princípio, instituto ou tese jurídica extraída por LLM",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
            {"name": "category", "type": "STRING"},
        ],
    },
    {
        "label": "Instituto",
        "description": "Instituto jurídico (ex: 'desconsideração da personalidade jurídica', 'prescrição intercorrente')",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
            {"name": "category", "type": "STRING"},
        ],
    },
    # GLiNER-extractable entities (zero-shot NER)
    {
        "label": "OrgaoPublico",
        "description": "Órgão público, autarquia, ministério ou entidade governamental",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
            {"name": "tipo", "type": "STRING"},
        ],
    },
    {
        "label": "Prazo",
        "description": "Prazo processual ou administrativo",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
        ],
    },
    {
        "label": "ValorMonetario",
        "description": "Valor monetário mencionado em contexto jurídico",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
        ],
    },
    {
        "label": "DataJuridica",
        "description": "Data relevante em contexto jurídico (publicação, vigência, etc.)",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
        ],
    },
    {
        "label": "Local",
        "description": "Local, comarca, estado ou município em contexto jurídico",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
            {"name": "tipo", "type": "STRING"},
        ],
    },
    # Factual entities
    {
        "label": "Pessoa",
        "description": "Pessoa física: parte, réu, autor, testemunha, perito",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
            {"name": "role", "type": "STRING"},
            {"name": "cpf", "type": "STRING"},
        ],
    },
    {
        "label": "Empresa",
        "description": "Pessoa jurídica: empresa, associação, fundação, ente público",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
            {"name": "cnpj", "type": "STRING"},
            {"name": "tipo", "type": "STRING"},
        ],
    },
    {
        "label": "Evento",
        "description": "Evento processual ou fático: audiência, perícia, citação, contrato, acidente",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
            {"name": "data", "type": "STRING"},
            {"name": "tipo", "type": "STRING"},
        ],
    },
    # GDS-generated nodes
    {
        "label": "Community",
        "description": "Cluster de entidades relacionadas detectado por Leiden (GDS)",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
            {"name": "summary", "type": "STRING"},
            {"name": "size", "type": "INTEGER"},
            {"name": "level", "type": "INTEGER"},
        ],
    },
]


# =============================================================================
# RELATIONSHIP TYPES
# =============================================================================

LEGAL_RELATIONSHIP_TYPES: List[Dict[str, Any]] = [
    # Core graph relationships
    {"label": "MENTIONS", "description": "Chunk menciona entidade"},
    {"label": "RELATED_TO", "description": "Relação genérica entre entidades"},
    {"label": "CITA", "description": "Entidade cita outra (ex: acórdão cita lei)"},
    {"label": "APLICA", "description": "Entidade aplica outra (ex: tribunal aplica súmula)"},
    {"label": "REVOGA", "description": "Entidade revoga outra (ex: lei nova revoga antiga)"},
    {"label": "ALTERA", "description": "Entidade altera outra"},
    # Temporal/legal lifecycle relationships (when explicitly stated)
    {"label": "PUBLICADA_EM", "description": "Norma/decisão é publicada em determinada data"},
    {"label": "ENTRA_EM_VIGOR_EM", "description": "Norma entra em vigor em determinada data"},
    {"label": "VIGORA_DESDE", "description": "Norma vigora a partir de determinada data"},
    {"label": "VIGORA_ATE", "description": "Norma vigora até determinada data (ou perde vigência)"},
    {"label": "FUNDAMENTA", "description": "Entidade fundamenta decisão"},
    {"label": "INTERPRETA", "description": "Entidade interpreta outra"},
    {"label": "PERTENCE_A", "description": "Artigo/dispositivo pertence a uma lei"},
    {"label": "SUBDISPOSITIVO_DE", "description": "Subdispositivo (parágrafo/inciso) pertence ao artigo-pai (inferência determinística)"},
    {"label": "REMETE_A", "description": "Remissão direta entre dispositivos legais"},
    {"label": "CO_MENCIONA", "description": "Co-menções entre dispositivos (relacionamento candidato/inferido)"},
    {"label": "COMPLEMENTA", "description": "Dispositivo/lei complementa outro (complementação normativa)"},
    {"label": "EXCEPCIONA", "description": "Dispositivo/lei excepciona outro"},
    {"label": "REGULAMENTA", "description": "Lei/dispositivo regulamenta tema/instituto"},
    {"label": "ESPECIALIZA", "description": "Norma/dispositivo especial prevalece ou especifica norma/dispositivo geral"},
    {"label": "PROFERIDA_POR", "description": "Decisão/Súmula proferida por Tribunal"},
    {"label": "FIXA_TESE", "description": "Decisão fixa tese jurídica"},
    {"label": "JULGA_TEMA", "description": "Decisão julga tema de repercussão/repetitivo"},
    {"label": "VINCULA", "description": "Súmula/Tese vincula entendimento"},
    {"label": "CONFIRMA", "description": "Decisão confirma outra (ratifica entendimento)"},
    {"label": "SUPERA", "description": "Decisão supera outra (overruling / superação de entendimento)"},
    {"label": "DISTINGUE", "description": "Decisão distingue outra (distinguishing)"},
    {"label": "CANCELA", "description": "Súmula cancela outra"},
    {"label": "SUBSTITUI", "description": "Súmula substitui outra"},
    # Doutrina relationships
    {"label": "CITA_DOUTRINA", "description": "Decisão/Súmula/Tese cita doutrina (autor/obra)"},
    {"label": "FUNDAMENTA_SE_EM", "description": "Decisão/Súmula/Tese fundamenta-se em doutrina"},
    {"label": "ANALISA", "description": "Doutrina analisa jurisprudência/súmula/tese"},
    # International/Multilingual relationships
    {"label": "OVERRULES", "description": "Case law overrules precedent (Common Law overruling)"},
    {"label": "DISTINGUISHES", "description": "Case law distinguishes from precedent (Common Law distinguishing)"},
    {"label": "FOLLOWS", "description": "Case law follows binding precedent (stare decisis)"},
    {"label": "CODIFIES", "description": "Statute codifies case law into legislation"},
    {"label": "TRANSPOSES", "description": "Lei transpõe diretiva europeia (EU transposition)"},
    {"label": "IMPLEMENTS", "description": "Regulation implements directive or treaty"},
    {"label": "HARMONIZES", "description": "Harmonização com tratado/direito internacional"},
    {"label": "CONFLICTS_WITH", "description": "Conflito entre normas de jurisdições diferentes"},
    {"label": "RATIFIES", "description": "Estado ratifica tratado internacional"},
    # ArgumentRAG relationships
    {"label": "SUPPORTS", "description": "Claim ou Evidence suporta outra Claim"},
    {"label": "OPPOSES", "description": "Claim ou Evidence contesta outra Claim"},
    {"label": "EVIDENCES", "description": "Evidence fundamenta Claim"},
    {"label": "ARGUES", "description": "Actor argumenta Claim"},
    {"label": "RAISES", "description": "Claim levanta Issue"},
    {"label": "CITES", "description": "Claim ou Evidence cita Entity"},
    {"label": "CONTAINS_CLAIM", "description": "Chunk contém Claim"},
    # v2 parity: dedicated relationship types
    {"label": "APLICA_SUMULA", "description": "Decisão aplica súmula (dedicado, não genérico APLICA)"},
    {"label": "AFASTA", "description": "Decisão afasta/desaplica dispositivo legal"},
    {"label": "ESTABELECE_TESE", "description": "Decisão estabelece tese (leading case)"},
    # Factual relationships
    {"label": "PARTICIPA_DE", "description": "Pessoa/Empresa participa de Processo/Evento"},
    {"label": "IDENTIFICADO_POR", "description": "Pessoa identificada por CPF, Empresa por CNPJ"},
    {"label": "OCORRE_EM", "description": "Evento ocorre em Local ou DataJuridica"},
    {"label": "REPRESENTA", "description": "Advogado/Actor representa Pessoa/Empresa"},
    {"label": "PARTE_DE", "description": "Pessoa/Empresa é parte em Processo"},
    # GDS community relationships
    {"label": "BELONGS_TO", "description": "Entidade pertence a Community (Leiden)"},
]

# Default relationship properties expected by extraction prompts + downstream QA.
# Keep these permissive (STRING) to avoid over-constraining ingestion.
_DEFAULT_REL_PROPERTIES: List[Dict[str, Any]] = [
    {"name": "dimension", "type": "STRING", "required": False},
    {"name": "evidence", "type": "STRING", "required": False},
    {"name": "weight", "type": "FLOAT", "required": False},
    # Temporal normalization (best-effort, extracted only when explicit)
    {"name": "date_raw", "type": "STRING", "required": False},
    {"name": "date_iso", "type": "STRING", "required": False},
    {"name": "valid_from", "type": "STRING", "required": False},
    {"name": "valid_to", "type": "STRING", "required": False},
]

for _rt in LEGAL_RELATIONSHIP_TYPES:
    if isinstance(_rt, dict):
        _rt.setdefault("properties", _DEFAULT_REL_PROPERTIES)


# =============================================================================
# PATTERNS (allowed triplets)
# =============================================================================

LEGAL_PATTERNS: List[Tuple[str, str, str]] = [
    # Core legal relationships
    ("Lei", "CITA", "Lei"),
    ("Lei", "REVOGA", "Lei"),
    ("Lei", "ALTERA", "Lei"),
    ("Lei", "PUBLICADA_EM", "DataJuridica"),
    ("Lei", "ENTRA_EM_VIGOR_EM", "DataJuridica"),
    ("Lei", "VIGORA_DESDE", "DataJuridica"),
    ("Lei", "VIGORA_ATE", "DataJuridica"),
    ("Lei", "REGULAMENTA", "Tema"),
    ("Lei", "REGULAMENTA", "Lei"),
    ("Lei", "EXCEPCIONA", "Lei"),
    ("Lei", "COMPLEMENTA", "Lei"),
    ("Lei", "ESPECIALIZA", "Lei"),
    ("Artigo", "PERTENCE_A", "Lei"),
    ("Artigo", "SUBDISPOSITIVO_DE", "Artigo"),
    ("Artigo", "REMETE_A", "Artigo"),
    ("Artigo", "CO_MENCIONA", "Artigo"),
    ("Artigo", "EXCEPCIONA", "Artigo"),
    ("Artigo", "COMPLEMENTA", "Artigo"),
    ("Artigo", "ESPECIALIZA", "Artigo"),
    ("Artigo", "REGULAMENTA", "Tema"),
    ("Artigo", "RELATED_TO", "Lei"),
    ("Decisao", "PROFERIDA_POR", "Tribunal"),
    ("Decisao", "INTERPRETA", "Artigo"),
    ("Decisao", "INTERPRETA", "Lei"),
    ("Decisao", "APLICA", "Artigo"),
    ("Decisao", "APLICA", "Lei"),
    ("Decisao", "APLICA", "Sumula"),
    ("Decisao", "FIXA_TESE", "Tese"),
    ("Decisao", "JULGA_TEMA", "Tema"),
    ("Decisao", "CITA", "Decisao"),
    ("Decisao", "CONFIRMA", "Decisao"),
    ("Decisao", "SUPERA", "Decisao"),
    ("Decisao", "DISTINGUE", "Decisao"),
    ("Sumula", "PROFERIDA_POR", "Tribunal"),
    ("Sumula", "INTERPRETA", "Artigo"),
    ("Sumula", "INTERPRETA", "Lei"),
    ("Sumula", "FUNDAMENTA", "Artigo"),
    ("Sumula", "FUNDAMENTA", "Lei"),
    ("Sumula", "VINCULA", "Tema"),
    ("Sumula", "CANCELA", "Sumula"),
    ("Sumula", "SUBSTITUI", "Sumula"),
    ("Tese", "INTERPRETA", "Artigo"),
    ("Tese", "INTERPRETA", "Lei"),
    ("Tese", "VINCULA", "Tema"),
    ("Sumula", "FUNDAMENTA", "Claim"),
    ("Tribunal", "APLICA", "Sumula"),
    ("Tribunal", "APLICA", "Lei"),
    ("Processo", "RELATED_TO", "Tribunal"),
    ("Tema", "RELATED_TO", "Tribunal"),
    # ArgumentRAG patterns
    ("Claim", "SUPPORTS", "Claim"),
    ("Claim", "OPPOSES", "Claim"),
    ("Evidence", "EVIDENCES", "Claim"),
    ("Actor", "ARGUES", "Claim"),
    ("Claim", "RAISES", "Issue"),
    ("Claim", "CITES", "Lei"),
    ("Claim", "CITES", "Sumula"),
    ("Claim", "CITES", "Artigo"),
    ("Evidence", "CITES", "Lei"),
    ("Evidence", "CITES", "Sumula"),
    # Semantic relationships
    ("SemanticEntity", "RELATED_TO", "SemanticEntity"),
    ("SemanticEntity", "RELATED_TO", "Lei"),
    ("SemanticEntity", "RELATED_TO", "Sumula"),
    # GLiNER entity relationships
    ("OrgaoPublico", "RELATED_TO", "Lei"),
    ("OrgaoPublico", "RELATED_TO", "Processo"),
    ("Local", "RELATED_TO", "Tribunal"),
    ("Local", "RELATED_TO", "Processo"),
    # v2 parity: dedicated APLICA_SUMULA + AFASTA + ESTABELECE_TESE patterns
    ("Decisao", "APLICA_SUMULA", "Sumula"),
    ("Decisao", "AFASTA", "Artigo"),
    ("Decisao", "AFASTA", "Lei"),
    ("Decisao", "ESTABELECE_TESE", "Tese"),
    ("Artigo", "REGULAMENTA", "Instituto"),
    ("Tese", "SUBSTITUI", "Tese"),
    # Expanded horizontal relationships (apply to all relevant entities)
    ("Sumula", "REMETE_A", "Sumula"),
    ("Tese", "REMETE_A", "Tese"),
    ("Decisao", "REMETE_A", "Decisao"),
    ("Lei", "REMETE_A", "Lei"),
    ("Sumula", "COMPLEMENTA", "Sumula"),
    ("Tese", "COMPLEMENTA", "Tese"),
    ("Decisao", "COMPLEMENTA", "Decisao"),
    ("Sumula", "EXCEPCIONA", "Sumula"),
    ("Tese", "EXCEPCIONA", "Tese"),
    ("Sumula", "ESPECIALIZA", "Sumula"),
    ("Sumula", "SUPERA", "Sumula"),
    ("Tese", "SUPERA", "Tese"),
    ("Decisao", "CITA", "Sumula"),
    ("Decisao", "CITA", "Tese"),
    ("Sumula", "CITA", "Decisao"),
    ("Tese", "CITA", "Decisao"),
    ("Sumula", "CONFIRMA", "Decisao"),
    ("Tese", "CONFIRMA", "Decisao"),
    # Doutrina patterns (fundamentação teórica)
    ("Decisao", "CITA_DOUTRINA", "Doutrina"),
    ("Sumula", "CITA_DOUTRINA", "Doutrina"),
    ("Tese", "CITA_DOUTRINA", "Doutrina"),
    ("Decisao", "FUNDAMENTA_SE_EM", "Doutrina"),
    ("Sumula", "FUNDAMENTA_SE_EM", "Doutrina"),
    ("Tese", "FUNDAMENTA_SE_EM", "Doutrina"),
    ("Doutrina", "INTERPRETA", "Artigo"),
    ("Doutrina", "INTERPRETA", "Lei"),
    ("Doutrina", "ANALISA", "Decisao"),
    ("Doutrina", "ANALISA", "Sumula"),
    ("Doutrina", "ANALISA", "Tese"),
    # Doutrina horizontal (autores citam/criticam outros)
    ("Doutrina", "CITA", "Doutrina"),
    ("Doutrina", "REMETE_A", "Doutrina"),
    ("Doutrina", "COMPLEMENTA", "Doutrina"),
    ("Doutrina", "EXCEPCIONA", "Doutrina"),
    ("Doutrina", "SUPERA", "Doutrina"),
    ("Doutrina", "ESPECIALIZA", "Doutrina"),
    ("Doutrina", "CONFIRMA", "Decisao"),
    # ========== INTERNATIONAL/MULTILINGUAL PATTERNS ==========
    # Common Law (US, UK, Commonwealth) - CaseLaw patterns
    ("CaseLaw", "OVERRULES", "CaseLaw"),
    ("CaseLaw", "DISTINGUISHES", "CaseLaw"),
    ("CaseLaw", "FOLLOWS", "CaseLaw"),
    ("CaseLaw", "CITA", "CaseLaw"),
    ("CaseLaw", "CONFIRMA", "CaseLaw"),
    ("CaseLaw", "REMETE_A", "CaseLaw"),
    ("CaseLaw", "INTERPRETA", "Statute"),
    ("CaseLaw", "APLICA", "Statute"),
    ("Statute", "CODIFIES", "CaseLaw"),
    ("Statute", "REMETE_A", "Statute"),
    ("Statute", "COMPLEMENTA", "Statute"),
    ("Statute", "EXCEPCIONA", "Statute"),
    ("Statute", "REVOGA", "Statute"),
    ("Statute", "ALTERA", "Statute"),
    ("Statute", "PUBLICADA_EM", "DataJuridica"),
    ("Statute", "ENTRA_EM_VIGOR_EM", "DataJuridica"),
    ("Statute", "VIGORA_DESDE", "DataJuridica"),
    ("Statute", "VIGORA_ATE", "DataJuridica"),
    # Regulations
    ("Regulation", "IMPLEMENTS", "Statute"),
    ("Regulation", "IMPLEMENTS", "Directive"),
    ("Regulation", "IMPLEMENTS", "Treaty"),
    ("CaseLaw", "INTERPRETA", "Regulation"),
    # EU Law - Directives and Regulations
    ("Directive", "REMETE_A", "Directive"),
    ("Directive", "COMPLEMENTA", "Directive"),
    ("Directive", "ESPECIALIZA", "Directive"),
    ("Lei", "TRANSPOSES", "Directive"),
    ("Statute", "TRANSPOSES", "Directive"),
    ("Regulation", "TRANSPOSES", "Directive"),
    # International Law - Treaties
    ("Treaty", "REMETE_A", "Treaty"),
    ("Treaty", "COMPLEMENTA", "Treaty"),
    ("Treaty", "SUPERA", "Treaty"),
    ("Lei", "RATIFIES", "Treaty"),
    ("Statute", "RATIFIES", "Treaty"),
    ("Lei", "HARMONIZES", "Treaty"),
    ("Statute", "HARMONIZES", "Treaty"),
    ("InternationalDecision", "INTERPRETA", "Treaty"),
    ("InternationalDecision", "APLICA", "Treaty"),
    ("InternationalDecision", "CITA", "InternationalDecision"),
    # Cross-jurisdictional citations
    ("Decisao", "CITA", "CaseLaw"),
    ("CaseLaw", "CITA", "Decisao"),
    ("Decisao", "CITA", "InternationalDecision"),
    ("CaseLaw", "CITA", "InternationalDecision"),
    ("Decisao", "CITA", "Statute"),
    ("CaseLaw", "CITA", "Lei"),
    ("Decisao", "CITA", "Treaty"),
    ("CaseLaw", "CITA", "Treaty"),
    ("Sumula", "CITA", "CaseLaw"),
    ("Tese", "CITA", "CaseLaw"),
    # Conflicts between jurisdictions
    ("Lei", "CONFLICTS_WITH", "Statute"),
    ("Lei", "CONFLICTS_WITH", "Directive"),
    ("Lei", "CONFLICTS_WITH", "Treaty"),
    ("Statute", "CONFLICTS_WITH", "Treaty"),
    ("Decisao", "CONFLICTS_WITH", "CaseLaw"),
    # Harmonization
    ("Lei", "HARMONIZES", "Statute"),
    ("Lei", "HARMONIZES", "Directive"),
    ("Statute", "HARMONIZES", "Directive"),
    # Doutrina com entidades internacionais
    ("Doutrina", "INTERPRETA", "Statute"),
    ("Doutrina", "INTERPRETA", "Treaty"),
    ("Doutrina", "ANALISA", "CaseLaw"),
    ("Doutrina", "ANALISA", "InternationalDecision"),
    ("Doutrina", "CITA", "CaseLaw"),
    ("CaseLaw", "CITA_DOUTRINA", "Doutrina"),
    ("Statute", "FUNDAMENTA_SE_EM", "Doutrina"),
    # Factual patterns
    ("Pessoa", "PARTICIPA_DE", "Processo"),
    ("Pessoa", "PARTICIPA_DE", "Evento"),
    ("Pessoa", "PARTE_DE", "Processo"),
    ("Empresa", "PARTICIPA_DE", "Processo"),
    ("Empresa", "PARTICIPA_DE", "Evento"),
    ("Empresa", "PARTE_DE", "Processo"),
    ("Actor", "REPRESENTA", "Pessoa"),
    ("Actor", "REPRESENTA", "Empresa"),
    ("Evento", "OCORRE_EM", "Local"),
    ("Evento", "RELATED_TO", "Processo"),
    ("Evento", "RELATED_TO", "DataJuridica"),
    ("Pessoa", "RELATED_TO", "Empresa"),
    ("Pessoa", "RELATED_TO", "ValorMonetario"),
    ("Empresa", "RELATED_TO", "ValorMonetario"),
    ("OrgaoPublico", "RELATED_TO", "Evento"),
    ("DataJuridica", "RELATED_TO", "Evento"),
    ("DataJuridica", "RELATED_TO", "Processo"),
    ("ValorMonetario", "RELATED_TO", "Processo"),
]


# =============================================================================
# SCHEMA BUILDER — neo4j-graphrag GraphSchema
# =============================================================================

def normalize_schema_mode(schema_mode: Optional[str]) -> str:
    """
    Normalize schema strategy mode.

    Supported:
    - ontology: strict predefined ontology (default)
    - auto: allow automatic discovery of additional labels/rels/patterns
    - hybrid: predefined ontology + automatic discovery

    Note on naming:
    The upstream docs sometimes refer to discovery modes with different labels
    (e.g. "EXTRACTED"/"FREE"). In Iudex:
    - ontology ~= strict/predefined (additional_* flags disabled)
    - auto ~= extracted/discovery enabled (additional_* flags enabled)
    - hybrid ~= predefined + discovery enabled (plus optional second-pass in pipeline)
    """
    mode = str(schema_mode or "ontology").strip().lower()
    if mode not in {"ontology", "auto", "hybrid"}:
        return "ontology"
    return mode


def _schema_additional_flags(schema_mode: str) -> Dict[str, bool]:
    """
    Return GraphSchema additional_* flags based on mode.

    We use a permissive strategy for auto/hybrid by enabling additional
    node/relationship/pattern discovery while preserving the legal ontology.
    """
    mode = normalize_schema_mode(schema_mode)
    if mode in {"auto", "hybrid"}:
        return {
            "additional_node_types": True,
            "additional_relationship_types": True,
            "additional_patterns": True,
        }
    return {
        "additional_node_types": False,
        "additional_relationship_types": False,
        "additional_patterns": False,
    }


def build_graphrag_schema(schema_mode: str = "ontology"):
    """
    Constrói GraphSchema usando tipos nativos do neo4j-graphrag.

    Retorna instância de GraphSchema compatível com SimpleKGPipeline(schema=...).
    """
    from neo4j_graphrag.experimental.components.schema import (
        GraphSchema,
        NodeType,
        Pattern,
        PropertyType,
        RelationshipType,
    )

    node_types = []
    for nt in LEGAL_NODE_TYPES:
        props = [
            PropertyType(name=p["name"], type=p["type"])
            for p in nt["properties"]
        ]
        node_types.append(NodeType(
            label=nt["label"],
            description=nt.get("description", ""),
            properties=props,
        ))

    rel_types = []
    for rt in LEGAL_RELATIONSHIP_TYPES:
        # Keep relationship property schema permissive. The extractor prompt enforces
        # `dimension` + `evidence` when possible, and we may enrich temporal fields
        # (date_raw/date_iso) in post-processing.
        rel_props = [
            PropertyType(name="dimension", type="STRING"),
            PropertyType(name="evidence", type="STRING"),
            PropertyType(name="weight", type="FLOAT"),
            PropertyType(name="date_raw", type="STRING"),
            PropertyType(name="date_iso", type="STRING"),
            PropertyType(name="valid_from", type="STRING"),
            PropertyType(name="valid_to", type="STRING"),
        ]
        rel_types.append(RelationshipType(
            label=rt["label"],
            description=rt.get("description", ""),
            properties=rel_props,
        ))

    patterns = [
        Pattern(source=src, relationship=rel, target=tgt)
        for src, rel, tgt in LEGAL_PATTERNS
    ]

    flags = _schema_additional_flags(schema_mode)

    return GraphSchema(
        node_types=node_types,
        relationship_types=rel_types,
        patterns=patterns,
        additional_node_types=flags["additional_node_types"],
        additional_relationship_types=flags["additional_relationship_types"],
        additional_patterns=flags["additional_patterns"],
    )


def build_legal_schema(schema_mode: str = "ontology") -> Dict[str, Any]:
    """
    Build a schema dict compatible with SimpleKGPipeline (formato legado).

    Tenta retornar GraphSchema nativo; se neo4j-graphrag não estiver disponível,
    retorna dict.
    """
    try:
        return build_graphrag_schema(schema_mode=schema_mode)
    except ImportError:
        flags = _schema_additional_flags(schema_mode)
        return {
            "node_types": LEGAL_NODE_TYPES,
            "relationship_types": LEGAL_RELATIONSHIP_TYPES,
            "patterns": LEGAL_PATTERNS,
            "additional_node_types": flags["additional_node_types"],
            "additional_relationship_types": flags["additional_relationship_types"],
            "additional_patterns": flags["additional_patterns"],
        }


def get_all_node_types(include_discovered: bool = True) -> List[Dict[str, Any]]:
    """Return LEGAL_NODE_TYPES + dynamically discovered types from the whitelist.

    If include_discovered=True, checks HYBRID_LABELS_BY_ENTITY_TYPE for any
    labels not already covered by LEGAL_NODE_TYPES and adds them as minimal
    node type dicts with just {label, description, properties: [{name: "name"}]}.
    """
    base_labels = {nt["label"] for nt in LEGAL_NODE_TYPES}
    result = list(LEGAL_NODE_TYPES)

    if include_discovered:
        from app.services.rag.core.graph_hybrid import HYBRID_LABELS_BY_ENTITY_TYPE
        for _key, label in HYBRID_LABELS_BY_ENTITY_TYPE.items():
            if label not in base_labels:
                result.append({
                    "label": label,
                    "description": f"Tipo descoberto automaticamente: {label}",
                    "properties": [{"name": "name", "type": "STRING", "required": True}],
                })
                base_labels.add(label)

    return result


def get_schema_description() -> str:
    """
    Gera descrição textual do schema para prompts de LLM (usado pelo Text2Cypher).

    Formato:
        Node labels: Lei(name, numero, ano), Artigo(name, artigo, paragrafo), ...
        Relationships: (Lei)-[:CITA]->(Lei), (Artigo)-[:RELATED_TO]->(Lei), ...
    """
    node_parts = []
    for nt in LEGAL_NODE_TYPES:
        props = ", ".join(p["name"] for p in nt["properties"])
        node_parts.append(f"{nt['label']}({props})")

    rel_parts = []
    for src, rel, tgt in LEGAL_PATTERNS:
        rel_parts.append(f"(:{src})-[:{rel}]->(:{tgt})")

    return (
        "Node labels: " + ", ".join(node_parts) + "\n"
        "Structural nodes: Document(doc_hash, tenant_id, scope, case_id, title, source_type, sigilo), "
        "Chunk(chunk_uid, doc_hash, chunk_index, text_preview)\n"
        "Structural relationships: (:Document)-[:HAS_CHUNK]->(:Chunk), "
        "(:Chunk)-[:MENTIONS]->(:Entity), (:Chunk)-[:NEXT]->(:Chunk)\n"
        "Domain relationships: " + ", ".join(rel_parts)
    )
