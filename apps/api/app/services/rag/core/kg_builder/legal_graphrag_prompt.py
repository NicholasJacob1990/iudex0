"""
Strict legal ERExtractionTemplate for neo4j-graphrag SimpleKGPipeline.

This is a strict extraction prompt focused on:
- Extracting explicit relationships from the provided segment (anti-contamination).
- Enforcing canonical naming for core Brazilian legal citations.
- Preventing "hub" noise (e.g., Tribunal directly interpreting articles without a Decision node).

It is inspired by the standalone `neo4j-ingestor/ingest_v2.py` prompt (v2.1).
"""

from __future__ import annotations

try:
    from neo4j_graphrag.generation.prompts import ERExtractionTemplate

    _HAS_GRAPHRAG = True
except Exception:
    _HAS_GRAPHRAG = False

    class ERExtractionTemplate:  # type: ignore[no-redef]
        pass


# Versão compacta (~140 linhas) - 60% menor que a anterior
LEGAL_EXTRACTION_PROMPT_COMPACT = (
    "Extrator de entidades juridicas brasileiras para grafo hierarquico.\n"
    "\n"
    "=== ARQUITETURA (3 camadas + doutrina) ===\n"
    "C1 (Base): Artigo, Lei\n"
    "C2 (Consolidacao): Sumula, Tese, Tema\n"
    "C3 (Precedentes): Decisao, Tribunal\n"
    "Doutrina: fundamentacao teorica\n"
    "Internacional: CaseLaw, Statute, Directive, Regulation, Treaty, InternationalDecision\n"
    "\n"
    "=== RELACOES PRIORIZADAS ===\n"
    "HIERARQUICAS (cross-layer):\n"
    "  Decisao -INTERPRETA/APLICA-> Artigo | Decisao -FIXA_TESE-> Tese\n"
    "  Decisao -JULGA_TEMA-> Tema | Decisao -APLICA_SUMULA-> Sumula\n"
    "  Sumula/Tese -FUNDAMENTA/INTERPRETA-> Artigo\n"
    "  Decisao/Sumula -PROFERIDA_POR-> Tribunal\n"
    "\n"
    "HORIZONTAIS (intra-camada):\n"
    "  Artigo -REMETE_A/COMPLEMENTA/EXCEPCIONA/ESPECIALIZA-> Artigo\n"
    "  Artigo -PERTENCE_A-> Lei\n"
    "  Decisao -CITA/CONFIRMA/SUPERA/DISTINGUE-> Decisao\n"
    "  Lei -REGULAMENTA/REVOGA/ALTERA-> Lei\n"
    "  Lei -PUBLICADA_EM/ENTRA_EM_VIGOR_EM/VIGORA_DESDE/VIGORA_ATE-> DataJuridica\n"
    "  Sumula -CANCELA/SUBSTITUI-> Sumula\n"
    "  Doutrina -REMETE_A/COMPLEMENTA/SUPERA-> Doutrina\n"
    "\n"
    "DOUTRINARIAS:\n"
    "  Decisao/Sumula/Tese -CITA_DOUTRINA/FUNDAMENTA_SE_EM-> Doutrina\n"
    "  Doutrina -INTERPRETA-> Artigo | Doutrina -ANALISA-> Decisao\n"
    "\n"
    "INTERNACIONAIS:\n"
    "  CaseLaw -OVERRULES/DISTINGUISHES/FOLLOWS-> CaseLaw\n"
    "  CaseLaw -INTERPRETA-> Statute | Statute -CODIFIES-> CaseLaw\n"
    "  Lei -TRANSPOSES-> Directive | Lei -RATIFIES-> Treaty\n"
    "  Decisao/Doutrina -CITA-> CaseLaw/Statute/InternationalDecision\n"
    "\n"
    "=== REGRAS ESSENCIAIS ===\n"
    "\n"
    "R0 (SCOPE): Extraia SOMENTE relacoes EXPLICITAS. Evidence obrigatorio (max 160 chars).\n"
    "  - Se nao conseguir citar trecho literal, NAO crie.\n"
    "  - Nao explique, nao resuma, nao argumente.\n"
    "\n"
    "R1 (PROPERTIES): TODA relationship deve ter:\n"
    "  * dimension: \"hierarquica\" | \"horizontal\" | \"remissiva\" | \"doutrinaria\" | \"fatica\"\n"
    "  * evidence: trecho literal (max 160 chars)\n"
    "  * (opcional) date_raw/date_iso: SOMENTE se o trecho explicitar uma data (publicacao, vigencia, revogacao, etc.)\n"
    "  Mapeamento:\n"
    "    remissiva: REMETE_A\n"
    "    hierarquica: PERTENCE_A, INTERPRETA, APLICA*, FIXA_TESE, JULGA_TEMA, FUNDAMENTA, PROFERIDA_POR\n"
    "    horizontal: CITA, CONFIRMA, SUPERA, DISTINGUE, CANCELA, SUBSTITUI, REGULAMENTA, ESPECIALIZA, REVOGA, ALTERA, COMPLEMENTA, EXCEPCIONA\n"
    "    doutrinaria: CITA_DOUTRINA, FUNDAMENTA_SE_EM, ANALISA\n"
    "\n"
    "R2 (NOMES): Use siglas padronizadas:\n"
    "  CF (Constituicao), CC (Codigo Civil), CPC (Codigo Processo Civil),\n"
    "  CTN (Codigo Tributario), CDC (Defesa Consumidor), CP (Codigo Penal),\n"
    "  LEF (Execucao Fiscal), LMS (Mandado Seguranca), CLT (Trabalho)\n"
    '  Formato: "Art. 135 do CTN", "Art. 85, par.3o do CPC"\n'
    "\n"
    "R3 (DECISOES): SOMENTE tipo+numero especifico.\n"
    '  OK: "REsp 1.134.186", "RE 603.191", "ADI 5090"\n'
    '  PROIBIDO: "STJ", "Jurisprudencia do STJ"\n'
    "  LIMITES: max 3 INTERPRETA, max 1 FIXA_TESE, max 1 JULGA_TEMA por Decisao.\n"
    "\n"
    "R4 (REMETE_A): Criar SOMENTE com expressao explicita:\n"
    '  "nos termos do art.", "conforme art.", "c/c art.", "com base no art.",\n'
    '  "combinado com", "previsto no art.", "na forma do art."\n'
    "  NAO criar por co-ocorrencia no mesmo paragrafo.\n"
    "  Sempre criar PERTENCE_A para Artigo -> sua Lei.\n"
    "\n"
    "R5 (SUMULAS/TEMAS):\n"
    '  Formato: "Sumula 435 do STJ", "Tema 796"\n'
    "  Extrair: FUNDAMENTA -> Artigo, PROFERIDA_POR -> Tribunal\n"
    "  Decisao aplica: Decisao -APLICA_SUMULA-> Sumula\n"
    "\n"
    "R6 (DOUTRINA): Nome especifico de autor/obra.\n"
    '  OK: "Nelson Nery Jr.", "Fredie Didier Jr., Curso de Direito Processual"\n'
    '  PROIBIDO: "Doutrina majoritaria", "A doutrina entende"\n'
    "\n"
    "R7 (INTERNACIONAL): SOMENTE quando explicitamente citado.\n"
    '  CaseLaw: "Brown v. Board of Education, 347 U.S. 483 (1954)"\n'
    '  Statute: "Civil Rights Act of 1964"\n'
    '  Directive: "GDPR Directive (EU) 2016/679"\n'
    '  Treaty: "Convencao de Viena (1969)"\n'
    "  Sempre incluir jurisdiction (US, UK, EU).\n"
    "\n"
    "R8 (QUALIDADE):\n"
    "  - Toda relationship DEVE ter dimension + evidence.\n"
    "  - Na duvida, OMITA.\n"
    "  - Tribunal NAO conecta diretamente a Artigo (use Decisao como intermediario).\n"
    "\n"
    "R9 (CADEIA NORMATIVA OBRIGATORIA):\n"
    "  - Todo paragrafo, inciso ou alinea DEVE ter relacao SUBDISPOSITIVO_DE com seu Artigo-pai.\n"
    '    Ex: "par.1o do Art. 150 do CTN" -> par.1o -SUBDISPOSITIVO_DE-> Art. 150 do CTN\n'
    "  - Todo Artigo DEVE ter relacao PERTENCE_A com sua fonte normativa (Lei, Decreto, CF, etc.).\n"
    '    Ex: "Art. 150 do CTN" -> Art. 150 do CTN -PERTENCE_A-> CTN\n'
    '  - Se o chunk menciona "par. 2o" ou "inciso II" sem artigo explicito, INFIRA do contexto.\n'
    '    Se nao for possivel inferir, NAO crie a entidade (evitar orfaos).\n'
    '  - Referencias anaforicas ("o artigo supracitado", "a lei mencionada") devem ser resolvidas\n'
    "    quando o contexto permitir. Se ambiguo, OMITA.\n"
    "  - Fonte normativa deve incluir tipo + numero + ano quando disponivel.\n"
    '    Ex: "Lei 8.112/1990", "LC 116/2003", "Decreto 9.580/2018"\n'
    "\n"
    "FORMATO JSON:\n"
    '{{\"nodes\": [{{\"id\": \"0\", \"label\": \"Artigo\", \"properties\": {{\"name\": \"Art. 135 do CTN\"}}}}],\n'
    '\"relationships\": [{{\"type\": \"REMETE_A\", \"start_node_id\": \"0\", \"end_node_id\": \"1\",\n'
    '\"properties\": {{\"dimension\":\"remissiva\",\"evidence\":\"nos termos do art. 135\"}}}}]}}\n'
    "\n"
    "Tipos permitidos:\n{schema}\n"
    "\nIDs string unicos. Sem backticks. Aspas duplas.\n"
    "\n{examples}\n\nTexto:\n{text}"
)

# Manter prompt original para referência/fallback
STRICT_LEGAL_EXTRACTION_PROMPT = (
    "Voce e um extrator de entidades juridicas brasileiras para grafo de conhecimento hierarquico.\n"
    "\n"
    "TAREFA: Extraia ENTIDADES (nodes) e RELACIONAMENTOS (relationships) do texto abaixo.\n"
    "\n"
    "=== ARQUITETURA DO GRAFO (3 camadas + doutrina + relacoes horizontais) ===\n"
    "CAMADA 1 (Base Normativa): Artigo, Lei\n"
    "CAMADA 2 (Consolidacao): Sumula, Tese, Tema\n"
    "CAMADA 3 (Precedentes): Decisao, Tribunal\n"
    "CAMADA DOUTRINARIA (Fundamentacao Teorica): Doutrina\n"
    "\n"
    "=== RELACOES HIERARQUICAS (cross-layer) - PRIORIDADE MAXIMA ===\n"
    "  Decisao -[INTERPRETA]-> Artigo          (C3->C1: decisao interpreta dispositivo)\n"
    "  Decisao -[FIXA_TESE]-> Tese             (C3->C2: decisao fixa tese juridica)\n"
    "  Decisao -[JULGA_TEMA]-> Tema            (C3->C2: decisao julga tema repetitivo)\n"
    "  Decisao -[APLICA_SUMULA]-> Sumula        (C3->C2: decisao aplica sumula)\n"
    "  Decisao -[APLICA]-> Artigo              (C3->C1: decisao aplica dispositivo)\n"
    "  Decisao -[AFASTA]-> Artigo|Lei          (C3->C1: decisao afasta/desaplica dispositivo)\n"
    "  Sumula -[FUNDAMENTA]-> Artigo            (C2->C1: sumula se fundamenta no artigo)\n"
    "  Sumula -[INTERPRETA]-> Artigo            (C2->C1: sumula interpreta artigo)\n"
    "  Tese -[INTERPRETA]-> Artigo             (C2->C1: tese interpreta artigo)\n"
    "  Decisao -[PROFERIDA_POR]-> Tribunal     (C3->C3)\n"
    "  Sumula -[PROFERIDA_POR]-> Tribunal      (C2->C3)\n"
    "\n"
    "=== RELACOES HORIZONTAIS (intra-camada) - PRIORIDADE ALTA ===\n"
    "  Artigo -[REMETE_A]-> Artigo             (C1<->C1: remissao textual explicita)\n"
    "  Artigo -[COMPLEMENTA]-> Artigo          (C1<->C1)\n"
    "  Artigo -[EXCEPCIONA]-> Artigo           (C1<->C1)\n"
    "  Artigo -[PERTENCE_A]-> Lei              (C1<->C1)\n"
    "  Decisao -[CITA]-> Decisao               (C3<->C3: decisao cita outra como precedente)\n"
    "  Decisao -[CONFIRMA]-> Decisao           (C3<->C3: ratifica entendimento)\n"
    "  Decisao -[SUPERA]-> Decisao             (C3<->C3: overruling)\n"
    "  Decisao -[DISTINGUE]-> Decisao          (C3<->C3: distinguishing)\n"
    "  Sumula -[CANCELA]-> Sumula              (C2<->C2)\n"
    "  Sumula -[SUBSTITUI]-> Sumula            (C2<->C2)\n"
    "  Lei -[REGULAMENTA]-> Lei               (C1<->C1: decreto regulamenta lei)\n"
    "  Lei -[ESPECIALIZA]-> Lei                (C1<->C1: lei especial -> lei geral)\n"
    "  Artigo -[ESPECIALIZA]-> Artigo          (C1<->C1: dispositivo especial -> geral)\n"
    "  NOTA: REGULAMENTA E ESPECIALIZA devem ser extraidas SOMENTE quando explicitamente mencionadas no trecho.\n"
    "    Ex: \"Decreto 10.854/2021 regulamenta a Lei 13.709/2018\" -> REGULAMENTA\n"
    "  Lei -[REVOGA]-> Lei                     (C1<->C1)\n"
    "  Lei -[ALTERA]-> Lei                     (C1<->C1)\n"
    "\n"
    "=== RELACOES HORIZONTAIS EXPANDIDAS - APLICAM-SE A TODOS OS TIPOS ===\n"
    "Estas relacoes tambem podem ocorrer entre entidades do MESMO tipo:\n"
    "  REMETE_A: Sumula->Sumula, Tese->Tese, Decisao->Decisao, Doutrina->Doutrina\n"
    "  COMPLEMENTA: Sumula->Sumula, Tese->Tese, Decisao->Decisao, Doutrina->Doutrina\n"
    "  EXCEPCIONA: Sumula->Sumula, Tese->Tese, Doutrina->Doutrina\n"
    "  ESPECIALIZA: Sumula->Sumula, Doutrina->Doutrina\n"
    "  CITA: Decisao->Sumula/Tese, Sumula->Decisao, Tese->Decisao, Doutrina->Doutrina/Decisao/Sumula/Tese\n"
    "  CONFIRMA: Sumula->Decisao, Tese->Decisao, Doutrina->Decisao\n"
    "  SUPERA: Sumula->Sumula, Tese->Tese, Doutrina->Doutrina\n"
    "\n"
    "=== RELACOES DOUTRINARIAS (fundamentacao teorica) - PRIORIDADE MEDIA ===\n"
    "  Decisao -[CITA_DOUTRINA]-> Doutrina     (decisao cita autor/obra)\n"
    "  Sumula -[FUNDAMENTA_SE_EM]-> Doutrina   (sumula fundamenta-se em doutrina)\n"
    "  Tese -[FUNDAMENTA_SE_EM]-> Doutrina     (tese fundamenta-se em doutrina)\n"
    "  Doutrina -[INTERPRETA]-> Artigo         (doutrina interpreta lei)\n"
    "  Doutrina -[ANALISA]-> Decisao           (doutrina analisa jurisprudencia)\n"
    "\n"
    "=== REGRAS DE EXTRACAO ===\n"
    "\n"
    "REGRA 0 (ESCOPO - ANTI-CONTAMINACAO)\n"
    "- Nao explique, nao resuma, nao argumente. Nao use raciocinio hipotetico.\n"
    "- Extraia SOMENTE relacoes EXPLICITAS neste trecho.\n"
    "- Se voce nao conseguir citar um trecho literal curto como evidence, NAO crie a relacao.\n"
    "- Decisao so FIXA_TESE se a tese for atribuida aquela decisao especifica.\n"
    "- Se um artigo e mencionado, crie PERTENCE_A para sua Lei de origem.\n"
    "\n"
    "REGRA 0.1 (PROPRIEDADES POR RELACAO)\n"
    "Para CADA relationship:\n"
    "  * properties.dimension: \"hierarquica\" | \"horizontal\" | \"remissiva\" | \"doutrinaria\" | \"fatica\" (obrigatorio)\n"
    "  * properties.evidence: trecho literal (max 160 chars) que justifica (obrigatorio)\n"
    "  * NUNCA retorne properties vazio: sempre inclua dimension + evidence.\n"
    "Dimensionamento:\n"
    "  * remissiva: REMETE_A\n"
    "  * hierarquica: PERTENCE_A, INTERPRETA (quando Decisao/Sumula/Tese), APLICA, APLICA_SUMULA, FIXA_TESE, JULGA_TEMA, FUNDAMENTA, PROFERIDA_POR, AFASTA\n"
    "  * horizontal: CITA, CONFIRMA, SUPERA, DISTINGUE, CANCELA, SUBSTITUI, REGULAMENTA, ESPECIALIZA, REVOGA, ALTERA, COMPLEMENTA, EXCEPCIONA\n"
    "  * doutrinaria: CITA_DOUTRINA, FUNDAMENTA_SE_EM, ANALISA (quando Doutrina INTERPRETA Artigo, usar \"hierarquica\")\n"
    "  * fatica: PARTICIPA_DE, REPRESENTA, OCORRE_EM, PARTE_DE, RELATED_TO (entidades faticas)\n"
    "A dimension deve ser determinada pelo TIPO da relacao (nunca chute).\n"
    "\n"
    "CADEIAS-ALVO (4-5 hops) — PRIORIZE relacoes que formam estas cadeias:\n"
    "- 4h: Art1 -REMETE_A-> Art2 <-INTERPRETA- Decisao -FIXA_TESE-> Tese\n"
    "- 4h: Decisao -APLICA_SUMULA-> Sumula -FUNDAMENTA-> Art1 -REMETE_A-> Art2\n"
    "- 4h: Decisao1 -CITA-> Decisao2 -INTERPRETA-> Art -PERTENCE_A-> Lei\n"
    "- 4h: Sumula -FUNDAMENTA-> Art <-INTERPRETA- Decisao -FIXA_TESE-> Tese\n"
    "- 5h: Art1 -REMETE_A-> Art2 <-FUNDAMENTA- Sumula <-APLICA_SUMULA- Decisao -FIXA_TESE-> Tese\n"
    "- 5h: Decisao1 -CITA-> Decisao2 -INTERPRETA-> Art1 -REMETE_A-> Art2 -PERTENCE_A-> Lei\n"
    "Se a relacao nao for explicita, nao crie apenas para completar cadeia.\n"
    "\n"
    "REGRA 1 (NORMALIZACAO DE NOMES - OBRIGATORIA)\n"
    "SEMPRE use estas siglas padronizadas:\n"
    '  "Constituicao Federal"/"CRFB"/"Carta Magna" = CF\n'
    '  "Codigo Civil"/"CC/2002" = CC\n'
    '  "Codigo de Processo Civil"/"CPC/2015" = CPC\n'
    '  "Codigo Tributario Nacional" = CTN\n'
    '  "Codigo de Defesa do Consumidor" = CDC\n'
    '  "Codigo Penal" = CP\n'
    '  "Lei de Execucao Fiscal"/"Lei 6.830/80" = LEF\n'
    '  "Lei de Mandado de Seguranca"/"Lei 12.016/2009" = LMS\n'
    '  "Consolidacao das Leis do Trabalho" = CLT\n'
    'Formato artigos: "Art. [numero] do [SIGLA]"  Ex: "Art. 135 do CTN"\n'
    'Com paragrafos: "Art. 85, par. 3o do CPC"\n'
    'Leis sem sigla: "Art. 6o da Lei 11.101/05"\n'
    "\n"
    "REGRA 2 (DECISOES)\n"
    "SOMENTE com tipo+numero especifico:\n"
    '  OK: "REsp 1.134.186", "RE 603.191", "ADI 5090", "ADPF 347", "AgRg no AREsp 123.456"\n'
    '  PROIBIDO: "STJ", "STF", "Jurisprudencia do STJ", "Informativo 752"\n'
    "LIMITES POR DECISAO: max 3 INTERPRETA, max 1 FIXA_TESE, max 1 JULGA_TEMA.\n"
    "Quando uma Decisao CITA outra: ambas devem ter tipo+numero.\n"
    "\n"
    "REGRA 3 (REMISSOES Art->Art - REMETE_A)\n"
    "Crie SOMENTE com expressao textual de remissao (nao por co-ocorrencia):\n"
    '  "nos termos do art.", "conforme art.", "aplica-se o art.",\n'
    '  "de que trata o art.", "previsto no art.", "c/c art.",\n'
    '  "na forma do art.", "ressalvado o art.", "com base no art.",\n'
    '  "nos moldes do art.", "nos termos do artigo",\n'
    '  "combinado com", "sem prejuizo do art.", "aplicacao conjunta".\n'
    "NAO crie REMETE_A se dois artigos apenas aparecem no mesmo paragrafo/tema.\n"
    "Crie tambem PERTENCE_A para CADA Artigo -> sua Lei de origem.\n"
    "\n"
    "REGRA 4 (SUMULAS)\n"
    '  Formato: "Sumula 435 do STJ", "Sumula Vinculante 28"\n'
    "  Para CADA sumula, extraia:\n"
    "    - FUNDAMENTA -> Artigo(s) que a fundamentam\n"
    "    - PROFERIDA_POR -> Tribunal\n"
    "  Se o texto diz que uma Decisao 'aplica a Sumula X': Decisao -APLICA_SUMULA-> Sumula\n"
    "\n"
    "REGRA 5 (TEMAS E TESES)\n"
    'Temas: SOMENTE com numero: "Tema 796", "Tema 1184".\n'
    "Teses: texto curto (max 100 chars). Sempre conectar Tese -> INTERPRETA -> Artigo.\n"
    "\n"
    "REGRA 6 (TRIBUNAL NAO E HUB)\n"
    "- Nao conecte Tribunal diretamente a Artigo/Lei via INTERPRETA.\n"
    "- Use Decisao como intermediario: (Decisao)-[:PROFERIDA_POR]->(Tribunal) e (Decisao)-[:INTERPRETA]->(Artigo|Lei).\n"
    "\n"
    "REGRA 7 (CITACAO ENTRE DECISOES)\n"
    "Se o texto menciona que uma decisao citou/invocou/baseou-se em outra:\n"
    "  Ex: 'No REsp 1.134.186, o STJ citou o precedente firmado no RE 603.191'\n"
    "  -> REsp 1.134.186 -CITA-> RE 603.191\n"
    "Se o texto diz que uma decisao confirmou/manteve outra: CONFIRMA\n"
    "Se o texto diz que uma decisao superou/mudou entendimento: SUPERA\n"
    "\n"
    "REGRA 8 (DOUTRINA - tipo Doutrina)\n"
    "Extraia citacoes de autores, obras doutrinarias e comentarios juridicos:\n"
    "  Formatos aceitos:\n"
    '    - "Nelson Nery Jr." (autor)\n'
    '    - "Fredie Didier Jr., Curso de Direito Processual Civil" (autor + obra)\n'
    '    - "Daniel Amorim Assumpção Neves" (autor)\n'
    '    - "Pontes de Miranda, Tratado de Direito Privado" (autor + obra)\n'
    '  PROIBIDO:\n'
    '    - "Doutrina majoritaria", "Doutrina dominante", "A doutrina entende" (generico demais)\n'
    "  \n"
    "  Relacoes:\n"
    "    - Se decisao/sumula/tese cita autor/obra: CITA_DOUTRINA ou FUNDAMENTA_SE_EM\n"
    "    - Se autor interpreta lei: Doutrina -INTERPRETA-> Artigo\n"
    "    - Se autor analisa jurisprudencia: Doutrina -ANALISA-> Decisao\n"
    "  \n"
    "  Exemplos:\n"
    '    - "Conforme Nelson Nery Jr., o art. 85 do CPC..." -> Decisao -CITA_DOUTRINA-> "Nelson Nery Jr.", Doutrina -INTERPRETA-> Art. 85 do CPC\n'
    '    - "A Sumula 435 fundamenta-se na licao de Humberto Theodoro Jr." -> Sumula -FUNDAMENTA_SE_EM-> "Humberto Theodoro Jr."\n'
    '    - "Daniel Amorim critica o entendimento do STJ no REsp 1.234.567" -> Doutrina -ANALISA-> REsp 1.234.567\n'
    "\n"
    "REGRA 9 (CADEIA NORMATIVA OBRIGATÓRIA)\n"
    "- Todo parágrafo (§), inciso ou alínea DEVE ter relação SUBDISPOSITIVO_DE com seu Artigo-pai.\n"
    '  Ex: "§ 1º do Art. 150 do CTN" -> § 1º -SUBDISPOSITIVO_DE-> Art. 150 do CTN\n'
    "- Todo Artigo DEVE ter relação PERTENCE_A com sua fonte normativa (Lei, Decreto, CF, etc.).\n"
    '  Ex: "Art. 150 do CTN" -> Art. 150 do CTN -PERTENCE_A-> CTN\n'
    "- Se o chunk menciona '§ 2º' ou 'inciso II' sem artigo explícito, INFIRA do contexto.\n"
    "  Se não for possível inferir, NÃO crie a entidade.\n"
    "- Referências anafóricas ('o artigo supracitado', 'a lei mencionada') devem ser resolvidas.\n"
    "- Fonte normativa deve incluir tipo + número + ano quando disponível.\n"
    "\n"
    "REGRA 10 (ENTIDADES INTERNACIONAIS/MULTILÍNGUES)\n"
    "Extraia referencias a sistemas juridicos estrangeiros quando explicitamente mencionadas:\n"
    "\n"
    "  === COMMON LAW (US, UK, Commonwealth) ===\n"
    "  CaseLaw (precedente judicial):\n"
    '    Formatos: "Brown v. Board of Education, 347 U.S. 483 (1954)"\n'
    '              "Donoghue v. Stevenson [1932] AC 562"\n'
    '              "Roe v. Wade (1973)"\n'
    "    Properties: name, citation, court, year, jurisdiction\n"
    "  \n"
    "  Statute (lei escrita):\n"
    '    Formatos: "Civil Rights Act of 1964"\n'
    '              "Companies Act 2006 (UK)"\n'
    '              "US Code Title 17 (Copyright)"\n'
    "    Properties: name, code, year, jurisdiction\n"
    "  \n"
    "  Relacoes Common Law:\n"
    "    - CaseLaw -OVERRULES-> CaseLaw (precedente superado)\n"
    '      Ex: "Brown overruled Plessy v. Ferguson"\n'
    "    - CaseLaw -DISTINGUISHES-> CaseLaw (distinguishing)\n"
    '      Ex: "Court distinguished the facts from Smith v. Jones"\n'
    "    - CaseLaw -FOLLOWS-> CaseLaw (segue precedente)\n"
    '      Ex: "Following the reasoning in Miranda v. Arizona"\n'
    "    - CaseLaw -INTERPRETA-> Statute\n"
    '      Ex: "Chevron v. NRDC interpreted the Clean Air Act"\n'
    "    - Statute -CODIFIES-> CaseLaw (codifica common law)\n"
    '      Ex: "Statute of Frauds codified common law rules"\n'
    "\n"
    "  === DIREITO EUROPEU (EU Law) ===\n"
    "  Directive (diretiva):\n"
    '    Formatos: "Directive 2016/680 (Data Protection Directive)"\n'
    '              "GDPR Directive (EU) 2016/679"\n'
    "    Properties: name, number, year\n"
    "  \n"
    "  Regulation (regulamento):\n"
    '    Formatos: "Regulation (EC) No 1907/2006 (REACH)"\n'
    '              "EU Regulation 2022/2065 (Digital Services Act)"\n'
    "    Properties: name, number, year\n"
    "  \n"
    "  Relacoes EU:\n"
    "    - Regulation -IMPLEMENTS-> Directive (regulamento implementa diretiva)\n"
    "    - Lei -TRANSPOSES-> Directive (lei nacional transpoe diretiva EU)\n"
    '      Ex: "Lei 13.709/2018 (LGPD) transpoe a GDPR"\n'
    "    - Regulation -HARMONIZES-> Statute (harmonizacao regulatoria)\n"
    "    - Directive -CONFLICTS_WITH-> Lei (conflito normativo)\n"
    "\n"
    "  === DIREITO INTERNACIONAL ===\n"
    "  Treaty (tratado internacional):\n"
    '    Formatos: "Convencao de Viena sobre Direito dos Tratados (1969)"\n'
    '              "Pacto de San Jose da Costa Rica (1969)"\n'
    '              "TRIPS Agreement (1994)"\n'
    "    Properties: name, year, type (bilateral/multilateral)\n"
    "  \n"
    "  InternationalDecision (decisao de corte internacional):\n"
    '    Formatos: "Corte IDH, Caso Gomes Lund (2010)"\n'
    '              "ICJ, Nicaragua v. United States (1986)"\n'
    '              "ECHR, Sunday Times v. UK (1979)"\n'
    "    Properties: name, court, year, case_number\n"
    "  \n"
    "  Relacoes Internacionais:\n"
    "    - Lei -RATIFIES-> Treaty (ratificacao de tratado)\n"
    '      Ex: "Decreto 592/1992 ratifica o Pacto de Direitos Civis e Politicos"\n'
    "    - InternationalDecision -INTERPRETA-> Treaty\n"
    '      Ex: "Corte IDH interpretou o Art. 8 da CADH"\n'
    "    - Decisao -CITA-> InternationalDecision (citacao transnacional)\n"
    '      Ex: "STF citou jurisprudencia da Corte IDH"\n'
    "    - Treaty -HARMONIZES-> Lei (harmonizacao via tratado)\n"
    "\n"
    "  === CITACOES TRANSJURISDICIONAIS ===\n"
    "  Quando decisao brasileira cita precedente estrangeiro:\n"
    "    - Decisao -CITA-> CaseLaw\n"
    '      Ex: "STF citou Brown v. Board no RE 635.659"\n'
    "    - Doutrina -CITA-> CaseLaw / Statute / Directive\n"
    '      Ex: "Barroso analisa o caso Marbury v. Madison"\n'
    "  \n"
    "  IMPORTANTE:\n"
    "    - SOMENTE extraia entidades estrangeiras quando EXPLICITAMENTE citadas\n"
    "    - Sempre inclua property 'jurisdiction' (US, UK, EU, etc.)\n"
    "    - NAO invente citacoes estrangeiras para \"comparacao\" generica\n"
    "    - Evidence deve citar o trecho literal da referencia\n"
    "\n"
    "FORMATO JSON:\n"
    "{{\"nodes\": [{{\"id\": \"0\", \"label\": \"Artigo\", \"properties\": {{\"name\": \"Art. 135 do CTN\"}}}}],\n"
    "\"relationships\": [{{\"type\": \"REMETE_A\", \"start_node_id\": \"0\", \"end_node_id\": \"1\", \"properties\": {{\"dimension\":\"remissiva\",\"evidence\":\"nos termos do art. 135\"}}}}]}}\n"
    "\n"
    "Tipos permitidos:\n{schema}\n"
    "\nIDs string unicos. Sem backticks. Aspas duplas.\n"
    "\n{examples}\n\nTexto:\n{text}"
)


FACTUAL_EXTRACTION_LAYER = (
    "\n\nREGRA 11 (ENTIDADES FATICAS)\n"
    "Alem das entidades juridicas acima, extraia entidades faticas EXPLICITAS:\n"
    "- Pessoa: nome completo de partes, testemunhas, peritos, autores, reus.\n"
    "  Sempre inclua properties.role (autor, reu, testemunha, perito, etc.).\n"
    "  Se houver CPF mencionado, inclua properties.cpf.\n"
    "- Empresa: razao social ou nome fantasia de pessoas juridicas.\n"
    "  Se houver CNPJ mencionado, inclua properties.cnpj.\n"
    "  Se houver tipo (LTDA, SA, ME, EPP, EIRELI), inclua properties.tipo.\n"
    "- Evento: fatos relevantes com data ou contexto temporal.\n"
    "  Audiencias, pericias, citacoes, contratos, acidentes, demissoes.\n"
    "  Sempre inclua properties.data quando mencionada.\n"
    "- ValorMonetario: valores em R$ explicitamente mencionados.\n"
    "- DataJuridica: datas com relevancia processual (publicacao, intimacao, etc.).\n"
    "- Local: comarca, cidade, estado, endereco quando relevante.\n"
    "\n"
    "REGRA 12 (RELACIONAMENTOS FATICOS)\n"
    "Crie relacoes entre entidades faticas e processuais SOMENTE quando explicito:\n"
    "- (Pessoa)-[:PARTICIPA_DE]->(Processo) quando identificada como parte.\n"
    "  Triggers: \"autor\", \"reu\", \"reclamante\", \"reclamado\", \"apelante\", \"apelado\",\n"
    "  \"agravante\", \"agravado\", \"impetrante\", \"impetrado\", \"exequente\", \"executado\".\n"
    "- (Pessoa)-[:PARTICIPA_DE]->(Evento) quando participou do evento.\n"
    "  Triggers: \"presente na audiencia\", \"ouvido como testemunha\", \"perito designado\".\n"
    "- (Empresa)-[:PARTICIPA_DE]->(Processo) quando e parte.\n"
    "- (Actor)-[:REPRESENTA]->(Pessoa|Empresa) quando advogado/representante.\n"
    "  Triggers: \"advogado de\", \"representante legal\", \"procurador\", \"OAB\".\n"
    "- (Evento)-[:OCORRE_EM]->(Local) quando o local e mencionado.\n"
    "- Use RELATED_TO para vinculos explicitos sem tipo exato.\n"
    "Para CADA relationship fatico:\n"
    "  * properties.dimension: \"fatica\" (obrigatorio)\n"
    "  * properties.evidence: trecho literal (max 160 chars) que justifica (obrigatorio)\n"
    "  * Se nao conseguir citar evidence literal, NAO crie a relacao.\n"
    "\n"
    "REGRA 13 (ANTI-CONTAMINACAO FATICA)\n"
    "- NAO invente nomes. Extraia SOMENTE nomes explicitamente escritos.\n"
    "- NAO crie Pessoa para mencoes genericas (\"o autor\", \"a parte\").\n"
    "- Crie Pessoa somente quando houver nome proprio.\n"
    "- Na duvida, OMITA.\n"
)


class StrictLegalExtractionTemplate(ERExtractionTemplate if _HAS_GRAPHRAG else object):  # type: ignore[misc]
    """neo4j-graphrag template for strict legal extraction."""

    def __init__(self, *, include_factual: bool = False) -> None:
        if _HAS_GRAPHRAG:
            super().__init__()
            prompt = LEGAL_EXTRACTION_PROMPT_COMPACT
            if include_factual:
                prompt = prompt.replace(
                    "FORMATO JSON:",
                    FACTUAL_EXTRACTION_LAYER + "\nFORMATO JSON:",
                )
            self.template = prompt
