"""
Prompts especializados para o PlaybookService.

Todos os prompts são em português brasileiro (pt-BR) e utilizam
terminologia jurídica adequada ao direito contratual brasileiro.
"""


# ---------------------------------------------------------------------------
# 1. CLAUSE_EXTRACTION_PROMPT
#    Extrai e identifica cláusulas de um contrato
# ---------------------------------------------------------------------------

CLAUSE_EXTRACTION_PROMPT = """Você é um advogado especialista em direito contratual brasileiro.

Analise o texto do contrato abaixo e extraia TODAS as cláusulas relevantes.

Para cada cláusula identificada, retorne um JSON com a seguinte estrutura:
```json
[
  {{
    "clause_type": "<tipo da cláusula>",
    "title": "<título ou identificação da cláusula no contrato>",
    "location": "<referência: Cláusula X, Seção Y, Parágrafo Z>",
    "text": "<texto integral da cláusula>"
  }}
]
```

Tipos de cláusula comuns (use estes nomes quando aplicável):
- foro (cláusula de foro/jurisdição)
- multa (penalidades, multas contratuais)
- rescisao (rescisão, término, distrato)
- confidencialidade (NDA, sigilo)
- indenizacao (indenização, responsabilidade)
- sla (nível de serviço, disponibilidade)
- propriedade_intelectual (PI, direitos autorais)
- vigencia (prazo, duração, renovação)
- pagamento (condições de pagamento, reajuste)
- garantia (garantias, warranties)
- limitacao_responsabilidade (cap de responsabilidade)
- forca_maior (force majeure)
- cessao (cessão, transferência)
- nao_concorrencia (não-competição)
- nao_solicitacao (non-solicitation)
- protecao_dados (LGPD, privacidade)
- anticorrupcao (compliance, anticorrupção)
- auditoria (direito de auditoria)
- subcontratacao (subcontratação, terceirização)
- exclusividade (exclusividade)

Se uma cláusula não se encaixa nos tipos acima, use um nome descritivo em snake_case.

IMPORTANTE:
- Extraia o texto COMPLETO de cada cláusula, sem resumir
- Identifique TODAS as cláusulas, mesmo que pareçam secundárias
- Mantenha a numeração/referência original do contrato

## CONTRATO:
{contract_text}

Responda APENAS com o JSON, sem texto adicional."""


# ---------------------------------------------------------------------------
# 2. CLAUSE_ANALYSIS_PROMPT
#    Analisa uma cláusula contra uma regra do playbook
# ---------------------------------------------------------------------------

CLAUSE_ANALYSIS_PROMPT = """Você é um advogado sênior especialista em revisão contratual.

Analise a cláusula abaixo contra a regra do playbook e classifique-a.

## REGRA DO PLAYBOOK
- **Nome**: {rule_name}
- **Tipo de Cláusula**: {clause_type}
- **Descrição**: {rule_description}
- **Posição Preferida**: {preferred_position}
- **Posições Alternativas Aceitáveis**: {fallback_positions}
- **Posições Rejeitadas/Inaceitáveis**: {rejected_positions}
- **Severidade**: {severity}
- **Notas de Orientação**: {guidance_notes}

## CLÁUSULA DO CONTRATO
- **Localização**: {clause_location}
- **Texto**: {clause_text}

## PERSPECTIVA DA ANÁLISE
{party_perspective_section}

## CONTEXTO ADICIONAL DO CONTRATO
{contract_context}

## INSTRUÇÕES DE ANÁLISE

Compare a cláusula com as posições definidas na regra e classifique:

1. **compliant** — A cláusula está alinhada com a posição preferida ou uma alternativa aceitável
2. **needs_review** — A cláusula tem elementos preocupantes, mas não é claramente inaceitável; requer análise humana
3. **non_compliant** — A cláusula contém posições rejeitadas ou é significativamente divergente da posição preferida
4. **not_found** — A cláusula não foi encontrada no contrato (use apenas se o texto estiver vazio)

Considere:
- Termos juridicamente equivalentes (sinônimos jurídicos)
- Diferenças substanciais vs. meramente redacionais
- Implicações práticas e riscos
- Contexto do contrato como um todo

Responda em JSON:
```json
{{
  "classification": "<compliant|needs_review|non_compliant|not_found>",
  "confidence": <float 0.0 a 1.0>,
  "explanation": "<explicação detalhada em português da classificação, com referências específicas ao texto da cláusula e da regra>",
  "comment": "<comentário curto (2-3 frases) explicando POR QUE esta cláusula foi sinalizada e o que a alteração sugerida alcançaria em termos práticos/de risco para o cliente>",
  "key_concerns": ["<preocupação 1>", "<preocupação 2>"],
  "matching_position": "<preferred|fallback|rejected|none>"
}}
```

Responda APENAS com o JSON, sem texto adicional."""


# ---------------------------------------------------------------------------
# 3. REDLINE_GENERATION_PROMPT
#    Gera texto sugerido para substituir cláusula não-conforme
# ---------------------------------------------------------------------------

REDLINE_GENERATION_PROMPT = """Você é um advogado redator especialista em contratos brasileiros.

Gere uma versão revisada (redline) da cláusula abaixo, alinhando-a com a posição preferida do playbook.

## CLÁUSULA ORIGINAL
{original_clause}

## REGRA DO PLAYBOOK
- **Tipo**: {clause_type}
- **Posição Preferida**: {preferred_position}
- **Posições Alternativas**: {fallback_positions}
- **Severidade**: {severity}
- **Notas de Orientação**: {guidance_notes}

## PROBLEMAS IDENTIFICADOS
{explanation}

## INSTRUÇÕES DE REDAÇÃO

1. **Mantenha** a estrutura e numeração original da cláusula quando possível
2. **Preserve** termos técnicos e definições já usados no contrato
3. **Alinhe** o conteúdo com a posição preferida do playbook
4. **Seja pragmático** — sugira linguagem que seria razoavelmente aceita por ambas as partes
5. **Use** terminologia jurídica brasileira adequada
6. **Não invente** termos ou condições que não estejam na regra
7. **Mantenha** o mesmo nível de formalidade do contrato original

Responda em JSON:
```json
{{
  "suggested_text": "<texto revisado da cláusula>",
  "changes_summary": "<resumo das alterações feitas>",
  "negotiation_notes": "<notas para negociação — pontos que a contraparte pode resistir>"
}}
```

Responda APENAS com o JSON, sem texto adicional."""


# ---------------------------------------------------------------------------
# 4. PLAYBOOK_GENERATION_PROMPT
#    Gera regras de playbook a partir de múltiplos contratos
# ---------------------------------------------------------------------------

PLAYBOOK_GENERATION_PROMPT = """Você é um advogado sênior com 20+ anos de experiência em revisão contratual no Brasil.

Analise os contratos abaixo e gere um conjunto de regras (playbook) para revisão de contratos na área de **{area}**.

## CONTRATOS PARA ANÁLISE
{contracts_text}

## INSTRUÇÕES

Para cada tipo de cláusula identificado nos contratos:

1. **Identifique** o tipo de cláusula (foro, multa, rescisão, etc.)
2. **Determine a posição preferida** — a linguagem mais favorável encontrada ou recomendada
3. **Liste alternativas aceitáveis** — variações que ainda são aceitáveis
4. **Identifique posições rejeitadas** — termos que devem ser evitados ou alterados
5. **Defina a severidade** — low, medium, high, critical
6. **Adicione notas de orientação** — contexto para o revisor

Considere:
- Práticas de mercado na área de {area}
- Legislação brasileira aplicável (CC, CDC, CLT, LGPD, etc.)
- Jurisprudência predominante
- Riscos práticos para cada posição

Responda em JSON:
```json
[
  {{
    "clause_type": "<tipo em snake_case>",
    "rule_name": "<nome descritivo da regra>",
    "description": "<descrição da regra e sua importância>",
    "preferred_position": "<texto da posição preferida/ideal>",
    "fallback_positions": ["<alternativa 1>", "<alternativa 2>"],
    "rejected_positions": ["<posição rejeitada 1>", "<posição rejeitada 2>"],
    "action_on_reject": "<redline|flag|block|suggest>",
    "severity": "<low|medium|high|critical>",
    "guidance_notes": "<notas contextuais para o revisor>"
  }}
]
```

IMPORTANTE:
- Gere regras para TODOS os tipos de cláusula relevantes identificados
- Base suas regras nos padrões observados nos contratos fornecidos
- Priorize cláusulas de risco elevado
- Use português brasileiro (pt-BR)
- Mínimo de 5 regras, máximo de 30

Responda APENAS com o JSON, sem texto adicional."""


# ---------------------------------------------------------------------------
# 5. PLAYBOOK_SUMMARY_PROMPT
#    Gera resumo executivo da análise
# ---------------------------------------------------------------------------

PLAYBOOK_SUMMARY_PROMPT = """Você é um advogado sênior preparando um resumo executivo de revisão contratual.

Gere um resumo executivo claro e acionável da análise de contrato abaixo.

## DADOS DA ANÁLISE
- **Playbook**: {playbook_name}
- **Total de Regras**: {total_rules}
- **Conformes**: {compliant}
- **Precisam Revisão**: {needs_review}
- **Não-Conformes**: {non_compliant}
- **Não Encontradas**: {not_found}
- **Score de Risco**: {risk_score}/100

## DETALHES POR CLÁUSULA
{clause_details}

## INSTRUÇÕES

Redija um resumo executivo em português que contenha:

1. **Avaliação Geral** — Uma frase sobre o estado geral do contrato
2. **Pontos Críticos** — Cláusulas não-conformes de severidade alta/crítica (se houver)
3. **Pontos de Atenção** — Cláusulas que precisam revisão
4. **Pontos Positivos** — Cláusulas já alinhadas com as melhores práticas
5. **Cláusulas Ausentes** — Cláusulas importantes não encontradas
6. **Recomendação** — Ação recomendada (aprovar, revisar, renegociar, rejeitar)

Formato: texto corrido, máximo 500 palavras, linguagem profissional mas acessível.
Não use JSON nesta resposta — apenas texto em português.
"""


# ---------------------------------------------------------------------------
# 6. PLAYBOOK_FOR_AGENT_PROMPT
#    Template para injetar regras de playbook no system prompt do agente
#    Usado na página /minuta quando o usuário seleciona um playbook
# ---------------------------------------------------------------------------

PLAYBOOK_FOR_AGENT_PROMPT = """
## PLAYBOOK DE REVISÃO CONTRATUAL: {playbook_name}
{party_perspective_section}

Ao revisar este contrato, aplique as seguintes regras obrigatoriamente.
Para cada cláusula relevante, classifique como: ✅ Conforme | ⚠️ Revisar | ❌ Não-conforme | ❓ Não encontrada

{rules_section}

### INSTRUÇÕES DE APLICAÇÃO:
1. Analise CADA cláusula do contrato contra as regras acima
2. Sinalize IMEDIATAMENTE cláusulas não-conformes de severidade alta/crítica
3. Para cláusulas não-conformes, sugira redação alternativa baseada na posição preferida
4. Se uma cláusula esperada não estiver presente no contrato, sinalize como ausente
5. Ao final, forneça uma avaliação geral do risco contratual
"""

# ---------------------------------------------------------------------------
# 7. PLAYBOOK_IMPORT_PROMPT
#    Extrai regras de playbook de um documento existente (PDF/DOCX)
# ---------------------------------------------------------------------------

PLAYBOOK_IMPORT_PROMPT = """Voce e um advogado senior especialista em revisao contratual no Brasil.

Analise o documento abaixo, que contem um playbook ou manual de revisao de contratos,
e extraia TODAS as regras de revisao nele contidas.

## DOCUMENTO
{document_text}

## INSTRUCOES

Para cada regra de revisao identificada no documento:

1. **Identifique** o tipo de clausula (foro, multa, rescisao, sla, confidencialidade, etc.)
2. **Extraia a posicao preferida** — a linguagem considerada ideal ou obrigatoria
3. **Liste alternativas aceitaveis** — posicoes que sao toleraveis
4. **Identifique posicoes rejeitadas** — termos que devem ser evitados ou alterados
5. **Defina a severidade** — low, medium, high, critical
6. **Extraia notas de orientacao** — contexto, justificativas ou instrucoes ao revisor
7. **Determine a acao** — redline, flag, block ou suggest

Considere:
- Regras podem estar em formato de checklist, tabela, paragrafos ou topicos
- Extraia regras implicitas (ex: "jamais aceitar..." implica posicao rejeitada)
- Use os nomes de clausula padrao quando possivel (foro, multa, rescisao, sla, etc.)
- Se o documento nao parecer um playbook, extraia regras das clausulas e padroes observados

Responda em JSON:
```json
[
  {{
    "clause_type": "<tipo em snake_case>",
    "rule_name": "<nome descritivo da regra>",
    "description": "<descricao da regra>",
    "preferred_position": "<posicao preferida>",
    "fallback_positions": ["<alternativa 1>", "<alternativa 2>"],
    "rejected_positions": ["<posicao rejeitada 1>"],
    "action_on_reject": "<redline|flag|block|suggest>",
    "severity": "<low|medium|high|critical>",
    "guidance_notes": "<notas para o revisor>"
  }}
]
```

IMPORTANTE:
- Extraia o MAXIMO de regras possivel
- Minimo de 3 regras, maximo de 50
- Use portugues brasileiro (pt-BR)
- Responda APENAS com o JSON, sem texto adicional.
"""


# ---------------------------------------------------------------------------
# 8. WINNING_LANGUAGE_EXTRACTION_PROMPT
#    Extrai "linguagem vencedora" de contratos já negociados com sucesso.
#    Foco: identificar cláusulas que foram aceitas por ambas as partes,
#    determinando posições preferidas e padrões de negociação.
# ---------------------------------------------------------------------------

WINNING_LANGUAGE_EXTRACTION_PROMPT = """Você é um advogado sênior com 20+ anos de experiência em revisão contratual no Brasil.

Os contratos abaixo representam **contratos já negociados e assinados com sucesso** — ou seja, contêm "linguagem vencedora" (winning language) que foi aceita por todas as partes.

Sua tarefa é analisar estes contratos e extrair as **posições contratuais vencedoras** para criar um playbook de revisão na área de **{area}**.

## CONTRATOS (LINGUAGEM VENCEDORA)
{contracts_text}

## INSTRUÇÕES DE EXTRAÇÃO

Para cada tipo de cláusula identificado nos contratos:

1. **Identifique** o tipo de cláusula (foro, multa, rescisão, confidencialidade, SLA, etc.)
2. **Extraia a linguagem vencedora** — o texto exato ou parafrasado da cláusula como aparece nos contratos assinados. Esta é a **posição preferida** (standard position)
3. **Identifique variações aceitáveis** — se diferentes contratos têm redações ligeiramente diferentes para a mesma cláusula, liste as variações como **posições alternativas** (fallback positions)
4. **Determine posições a evitar** — com base na linguagem aceita, infira quais posições seriam **rejeitadas** (o oposto do que foi aceito, termos ausentes propositalmente, etc.)
5. **Classifique a importância**:
   - **critical** — cláusulas essenciais presentes em TODOS os contratos (ex: foro, confidencialidade, indenização)
   - **high** — cláusulas presentes na maioria dos contratos com linguagem consistente
   - **medium** — cláusulas com variações entre contratos
   - **low** — cláusulas presentes em apenas alguns contratos
6. **Gere notas de orientação** — explique POR QUE esta linguagem foi escolhida, qual o benefício estratégico, e dicas de negociação

Considere:
- Padrões RECORRENTES entre os contratos (linguagem que se repete = posição consolidada)
- Termos técnicos e definições padronizadas
- Prazos, valores e limites que formam padrão
- Legislação brasileira aplicável (CC, CDC, CLT, LGPD, Marco Civil, etc.)
- Práticas de mercado na área de {area}

Responda em JSON:
```json
[
  {{
    "clause_type": "<tipo em snake_case>",
    "rule_name": "<nome descritivo da regra>",
    "description": "<por que esta linguagem é considerada 'vencedora' — contexto estratégico>",
    "preferred_position": "<texto da linguagem vencedora extraída dos contratos>",
    "fallback_positions": ["<variação aceitável 1>", "<variação aceitável 2>"],
    "rejected_positions": ["<posição a evitar 1>", "<posição a evitar 2>"],
    "action_on_reject": "<redline|flag|block|suggest>",
    "severity": "<low|medium|high|critical>",
    "guidance_notes": "<notas estratégicas: por que esta linguagem funciona, pontos de negociação, riscos de alterar>"
  }}
]
```

IMPORTANTE:
- Foque em EXTRAIR a linguagem REAL dos contratos, não inventar
- Priorize cláusulas que aparecem em MÚLTIPLOS contratos (padrão consolidado)
- A posição preferida deve ser o mais próxima possível do texto original dos contratos
- Mínimo de 5 regras, máximo de 30
- Use português brasileiro (pt-BR)
- Responda APENAS com o JSON, sem texto adicional."""


PLAYBOOK_RULE_TEMPLATE = """
### Regra: {rule_name} [{severity}]
- **Tipo**: {clause_type}
- **Posição Preferida**: {preferred_position}
- **Alternativas Aceitáveis**: {fallback_positions}
- **Posições Rejeitadas**: {rejected_positions}
- **Ação se Rejeitada**: {action_on_reject}
{guidance_notes_section}
"""
