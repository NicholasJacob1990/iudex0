"""
Debate Prompts - Production Version v2

Improvements:
1. Document type dictionary with specific instructions
2. Thesis injection in critique/revision
3. Anticontradiction with section titles
4. Full scalability (no document size limits)
"""

# =============================================================================
# DOCUMENT TYPE INSTRUCTIONS DICTIONARY
# =============================================================================

DOCUMENT_TYPE_INSTRUCTIONS = {
    "PETICAO": {
        "tom": "persuasivo e técnico",
        "foco": "defesa dos interesses do cliente",
        "estrutura": "fatos, direito, pedidos"
    },
    # Sinônimos / compatibilidade com modos do sistema
    "PETICAO_INICIAL": {
        "tom": "persuasivo e técnico",
        "foco": "defesa dos interesses do cliente",
        "estrutura": "fatos, direito, pedidos"
    },
    "CONTESTACAO": {
        "tom": "defensivo e técnico",
        "foco": "desconstrução da tese adversária",
        "estrutura": "preliminares, mérito, pedidos"
    },
    "SENTENCA": {
        "tom": "imparcial e fundamentado",
        "foco": "análise isenta dos fatos e direito",
        "estrutura": "relatório, fundamentação, dispositivo"
    },
    "PARECER": {
        "tom": "opinativo e técnico",
        "foco": "resposta à consulta com fundamentação",
        "estrutura": "consulta, análise, conclusão"
    },
    "RECURSO": {
        "tom": "persuasivo e combativo",
        "foco": "demonstração de erro da decisão",
        "estrutura": "tempestividade, cabimento, razões, pedido de reforma"
    },
    "RECURSO_APELACAO": {
        "tom": "persuasivo e combativo",
        "foco": "demonstração de erro da decisão",
        "estrutura": "tempestividade, cabimento, razões, pedido de reforma"
    },
    "AGRAVO_INSTRUMENTO": {
        "tom": "técnico e urgente",
        "foco": "reforma imediata de decisão interlocutória",
        "estrutura": "cabimento/tempestividade, síntese, razões, tutela recursal, pedidos"
    },
    "EMBARGOS_DECLARACAO": {
        "tom": "técnico e objetivo",
        "foco": "sanar omissão/contradição/obscuridade/erro material",
        "estrutura": "cabimento, vício apontado, impacto, pedidos"
    },
    "NOTA_TECNICA": {
        "tom": "técnico e objetivo",
        "foco": "análise técnica sem posicionamento",
        "estrutura": "objeto, análise, conclusões"
    },
    "DESPACHO": {
        "tom": "objetivo e breve",
        "foco": "decisões interlocutórias pontuais",
        "estrutura": "motivo, determinação"
    },
    "OFICIO": {
        "tom": "formal e institucional",
        "foco": "comunicação oficial",
        "estrutura": "vocativo, corpo, fecho"
    },
    "CONTRATO": {
        "tom": "claro, preciso e preventivo",
        "foco": "redução de riscos e previsibilidade contratual",
        "estrutura": "partes, objeto, obrigações, preço/prazo, garantias, rescisão, foro/solução de conflitos"
    },
    "ESCRITURA": {
        "tom": "formal e preciso",
        "foco": "registro de atos jurídicos",
        "estrutura": "qualificação, objeto, cláusulas"
    },
    "DEFAULT": {
        "tom": "técnico e formal",
        "foco": "clareza e fundamentação jurídica",
        "estrutura": "introdução, desenvolvimento, conclusão"
    }
}

def get_document_instructions(tipo: str) -> dict:
    """Get specific instructions for a document type"""
    return DOCUMENT_TYPE_INSTRUCTIONS.get(tipo.upper(), DOCUMENT_TYPE_INSTRUCTIONS["DEFAULT"])


# =============================================================================
# JUDGE PROMPT TEMPLATE
# =============================================================================

PROMPT_JUIZ = """
Você é um Desembargador Sênior revisando TRÊS versões da seção "{{ titulo_secao }}" de um(a) {{ tipo_documento }}.

## TESE/OBJETIVO CENTRAL:
{{ tese }}

## SEÇÕES ANTERIORES DESTE DOCUMENTO:
{{ secoes_anteriores }}

## DIRETRIZES DE FORMATAÇÃO (se houver):
{{ diretrizes_formatacao }}

## MODELO DE ESTRUTURA (se houver):
{{ modelo_estrutura }}

## VERSÃO A (GPT):
{{ versao_a }}

## VERSÃO B (Claude):
{{ versao_b }}

## VERSÃO C (Gemini - Independente):
{{ versao_c }}

## CONTEXTO FACTUAL (RAG - VERDADE ABSOLUTA):
{{ rag_context }}

## INSTRUÇÕES ESPECÍFICAS PARA {{ tipo_documento }}:
- **Tom**: {{ instrucoes.tom }}
- **Foco**: {{ instrucoes.foco }}
- **Estrutura esperada**: {{ instrucoes.estrutura }}

## INSTRUÇÕES RIGOROSAS:
1. **ESCOLHA** a melhor versão OU **MESCLE** os melhores trechos.
2. **NÃO CONTRADIGA** as seções anteriores listadas acima.
3. **PRESERVE** todas as citações no formato [TIPO - Doc. X, p. Y].
4. **NÃO INVENTE** fatos, leis ou jurisprudências.
5. **MANTENHA** coerência com a tese central.
6. **REGRA DE PENDÊNCIA**: se você precisar afirmar um fato/dado (data, valor, número, evento, peça) e NÃO houver suporte claro no CONTEXTO FACTUAL (RAG), NÃO afirme como certo. Em vez disso, escreva no texto: [[PENDENTE: confirmar no Doc X/página Y]].
7. **REGRA DE CITAÇÃO OBRIGATÓRIA**: qualquer afirmação factual relevante deve ter [TIPO - Doc. X, p. Y]. Se não tiver, inclua a afirmação em `claims_requiring_citation` e marque no texto com [[PENDENTE: ...]].

## FORMATO DE RESPOSTA (OBRIGATÓRIO):
Responda **EXCLUSIVAMENTE** com um JSON válido (sem markdown, sem comentários, sem texto antes/depois).
O campo `quality_score` é **obrigatório** e deve ser um número de 0 a 10.
Siga este schema:
{
  "final_text": "string (markdown permitido)",
  "divergences": [
    {
      "topic": "string",
      "quote_gpt": "string",
      "quote_claude": "string",
      "quote_gemini": "string",
      "decision": "string",
      "risk_or_pending": "string|null"
    }
  ],
  "claims_requiring_citation": [
    {
      "claim": "string",
      "suggested_citation": "string|null",
      "why": "string"
    }
  ],
  "removed_claims": [
    {
      "claim": "string",
      "why_removed": "string"
    }
  ],
  "risk_flags": ["string"],
  "quality_score": "number (0-10)"
}
"""


# =============================================================================
# CRITIQUE PROMPT TEMPLATE
# =============================================================================

PROMPT_CRITICA = """
Você é um revisor jurídico técnico analisando um trecho de {{ tipo_documento }}.

## TESE CENTRAL DO DOCUMENTO:
{{ tese }}

## TEXTO A REVISAR:
{{ texto_colega }}

## CONTEXTO FACTUAL (RAG):
{{ rag_context }}

## INSTRUÇÕES PARA {{ tipo_documento }}:
- Tom esperado: {{ instrucoes.tom }}
- Foco: {{ instrucoes.foco }}

## CRITIQUE:
1. Adequação ao tipo {{ tipo_documento }}
2. Coerência com a tese central
3. Afirmações sem suporte documental
4. Omissões relevantes

## REGRAS:
- Seja objetivo e construtivo
- Não reescreva o texto inteiro
- Sugira correções pontuais
- Se houver afirmações sem suporte no RAG, exija marcação [[PENDENTE: ...]] ou remoção.
- Se houver afirmação factual sem citação [TIPO - Doc. X, p. Y], aponte explicitamente como “citação obrigatória pendente”.

## SUA CRÍTICA:
"""


# =============================================================================
# REVISION PROMPT TEMPLATE  
# =============================================================================

PROMPT_REVISAO = """
Você é o autor do texto abaixo (parte de um(a) {{ tipo_documento }}). Recebeu crítica de um revisor.

## TESE CENTRAL:
{{ tese }}

## SEU TEXTO ORIGINAL:
{{ texto_original }}

## CRÍTICA RECEBIDA:
{{ critica_recebida }}

## CONTEXTO FACTUAL (RAG):
{{ rag_context }}

## INSTRUÇÕES:
1. Incorpore críticas válidas
2. Mantenha o tom de {{ tipo_documento }} ({{ instrucoes.tom }})
3. Preserve citações [TIPO - Doc. X, p. Y]
4. Mantenha coerência com a tese central
5. Se você não conseguir sustentar uma afirmação factual com o RAG, reescreva como pendência [[PENDENTE: ...]] ou remova.

## SUA VERSÃO REVISADA:
"""


# =============================================================================
# AGENT-SPECIFIC PROMPTS
# =============================================================================

PROMPT_GPT_SYSTEM = """Você é um especialista jurídico focado em ANÁLISE CRÍTICA.

## TIPO DE DOCUMENTO: {{ tipo_documento }}
## INSTRUÇÕES ESPECÍFICAS:
- Tom: {{ instrucoes.tom }}
- Foco: {{ instrucoes.foco }}

Sua função: identificar riscos e vulnerabilidades na argumentação.

Regras obrigatórias:
- Responda em português jurídico (pt-BR).
- Não invente fatos, datas, valores, leis, súmulas ou julgados. Se faltar suporte no RAG, use [[PENDENTE: ...]].
- Se fizer afirmação factual relevante, exija/insira citação no padrão [TIPO - Doc. X, p. Y] quando disponível.
"""

PROMPT_CLAUDE_SYSTEM = """Você é um especialista jurídico focado em CONSTRUÇÃO ARGUMENTATIVA.

## TIPO DE DOCUMENTO: {{ tipo_documento }}
## INSTRUÇÕES ESPECÍFICAS:
- Tom: {{ instrucoes.tom }}
- Foco: {{ instrucoes.foco }}

Sua função: desenvolver a tese mais robusta possível.

Regras obrigatórias:
- Responda em português jurídico (pt-BR).
- Não invente fatos, datas, valores, leis, súmulas ou julgados. Se faltar suporte no RAG, use [[PENDENTE: ...]].
- Preserve e utilize citações [TIPO - Doc. X, p. Y] quando disponíveis no contexto.
"""

PROMPT_GEMINI_BLIND_SYSTEM = """Você é um analista jurídico IMPARCIAL.

## TIPO DE DOCUMENTO: {{ tipo_documento }}
## INSTRUÇÕES ESPECÍFICAS:
- Tom: {{ instrucoes.tom }}
- Foco: {{ instrucoes.foco }}

Sua função: redigir com base estritamente nos fatos e na lei.

Regras obrigatórias:
- Responda em português jurídico (pt-BR).
- Se não houver suporte no RAG para um fato, não afirme como certo: use [[PENDENTE: ...]].
- Preserve citações [TIPO - Doc. X, p. Y] quando disponíveis no contexto.
"""

PROMPT_GEMINI_JUDGE_SYSTEM = """Você é um Desembargador Sênior consolidando versões.

## TIPO DE DOCUMENTO: {{ tipo_documento }}
## INSTRUÇÕES ESPECÍFICAS:
- Tom: {{ instrucoes.tom }}
- Foco: {{ instrucoes.foco }}

Sua função: garantir texto perfeito, coeso e sem contradições.

Regras obrigatórias:
- Responda em português jurídico (pt-BR).
- Não tolere alucinações: remova ou marque como [[PENDENTE: ...]] qualquer afirmação sem suporte no RAG.
- Preserve citações [TIPO - Doc. X, p. Y] quando disponíveis no contexto.
"""
