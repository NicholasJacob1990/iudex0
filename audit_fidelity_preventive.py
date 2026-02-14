#!/usr/bin/env python3
"""
audit_fidelity_preventive.py - Auditoria Preventiva de Fidelidade (v1.0)

Detecta TODOS os tipos de problemas de fidelidade ANTES da geração final.
Não se restringe apenas a autoria - verifica omissões, distorções, compressão, etc.
"""

import os
import re
import json
import math
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from google import genai
from google.genai import types
try:
    from audit_sources import auditar_atribuicao_fontes
    SOURCES_AUDIT_AVAILABLE = True
except ImportError:
    auditar_atribuicao_fontes = None
    SOURCES_AUDIT_AVAILABLE = False

MAX_CHARS_PER_CHUNK = int(os.getenv("FIDELITY_AUDIT_MAX_CHARS", "100000"))
CHUNK_OVERLAP_CHARS = int(os.getenv("FIDELITY_AUDIT_CHUNK_OVERLAP", "4000"))
MAX_LIST_ITEMS = int(os.getenv("FIDELITY_AUDIT_MAX_ITEMS", "200"))
GEMINI_HTTP_TIMEOUT_MS = int(os.getenv("IUDEx_GEMINI_TIMEOUT_MS", "600000"))
PARALLEL_AUDIT_WORKERS = int(os.getenv("IUDEX_PARALLEL_AUDIT", "3"))
DEFAULT_AUDIT_MODEL = os.getenv("IUDEX_PREVENTIVE_AUDIT_MODEL", "gemini-3-flash-preview").strip() or "gemini-3-flash-preview"
CHUNK_CONTEXT_UTILIZATION = float(os.getenv("IUDEX_PREVENTIVE_AUDIT_CONTEXT_UTILIZATION", "0.82"))
PROMPT_CHAR_RESERVE = int(os.getenv("IUDEX_PREVENTIVE_AUDIT_PROMPT_CHAR_RESERVE", "22000"))

MODEL_CONTEXT_TOKENS = {
    "gemini-3-pro": 2_000_000,
    "gemini-3-pro-preview": 2_000_000,
    "gemini-2.0-pro": 2_000_000,
    "gemini-1.5-pro": 2_000_000,
    "gemini-3-flash": 1_000_000,
    "gemini-3-flash-preview": 1_000_000,
    "gemini-2.5-pro": 1_000_000,
    "gemini-2.5-flash": 1_000_000,
    "gemini-2.0-flash": 1_000_000,
    "gemini-2.0-flash-thinking": 1_000_000,
    "gemini-1.5-flash": 1_000_000,
}


def _normalize_model_name(model: str | None) -> str:
    normalized = (model or DEFAULT_AUDIT_MODEL).strip().lower()
    aliases = {
        "gemini": "gemini-3-flash-preview",
        "gemini-flash": "gemini-3-flash-preview",
        "gemini-3-flash": "gemini-3-flash-preview",
    }
    return aliases.get(normalized, normalized)


def _get_model_context_tokens(model: str) -> int:
    normalized = _normalize_model_name(model)
    if normalized in MODEL_CONTEXT_TOKENS:
        return MODEL_CONTEXT_TOKENS[normalized]
    for candidate, tokens in MODEL_CONTEXT_TOKENS.items():
        if candidate in normalized:
            return tokens
    return 1_000_000


def _estimate_effective_chunk_config(raw_text: str, formatted_text: str, model: str) -> tuple[int, int]:
    """
    Estimate chunk size/overlap to exploit model context while keeping headroom
    for prompt instructions and JSON output.
    """
    context_tokens = _get_model_context_tokens(model)
    # Conservative conversion: ~4 chars/token.
    max_context_chars = int(context_tokens * 4 * CHUNK_CONTEXT_UTILIZATION)
    available_for_payload = max(40_000, max_context_chars - PROMPT_CHAR_RESERVE)
    # Prompt includes RAW + formatted chunk, so divide by 2.
    adaptive_max_chars = max(60_000, min(MAX_CHARS_PER_CHUNK, available_for_payload // 2))
    adaptive_overlap = min(CHUNK_OVERLAP_CHARS, max(1_000, adaptive_max_chars // 12))

    # If the document fits comfortably, use a single full chunk.
    pair_len = len(raw_text) + len(formatted_text)
    if pair_len <= available_for_payload:
        adaptive_max_chars = max(len(raw_text), 1)
        adaptive_overlap = 0

    return adaptive_max_chars, adaptive_overlap


def _call_gemini_with_retry(
    client,
    prompt: str,
    config,
    max_retries: int = 5,
    *,
    model_name: str | None = None,
) -> str:
    """
    Chama Gemini com backoff exponencial para lidar com 429 RESOURCE_EXHAUSTED.

    Args:
        client: Cliente Gemini
        prompt: Prompt a enviar
        config: Configuração do GenerateContentConfig
        max_retries: Número máximo de tentativas

    Returns:
        Texto da resposta

    Raises:
        Exception: Se todas as tentativas falharem
    """
    last_error = None
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=_normalize_model_name(model_name),
                contents=prompt,
                config=config
            )
            return response.text or ""
        except Exception as e:
            last_error = e
            error_str = str(e).lower()
            # Check if it's a rate limit error (429)
            if "429" in str(e) or "resource_exhausted" in error_str or "quota" in error_str:
                # Exponential backoff: 4s, 8s, 16s, 32s, 64s + jitter
                wait_time = (2 ** (attempt + 2)) + random.uniform(0, 2)
                print(f"    ⏳ Rate limit (429), aguardando {wait_time:.1f}s antes de retry {attempt + 1}/{max_retries}...")
                time.sleep(wait_time)
            else:
                # For other errors, shorter wait
                wait_time = 2 + random.uniform(0, 1)
                print(f"    ⚠️ Erro Gemini: {str(e)[:100]}, retry {attempt + 1}/{max_retries} em {wait_time:.1f}s...")
                time.sleep(wait_time)

    raise last_error or Exception("Todas as tentativas falharam")

APOSTILA_MIN_RETENTION = 0.70
FIDELIDADE_MIN_RETENTION = 0.95
FIDELIDADE_MAX_RETENTION = 1.15

GRAVIDADE_ORDEM = {
    "BAIXA": 0,
    "MÉDIA": 1,
    "ALTA": 2,
    "CRÍTICA": 3,
}

PROMPT_AUDITORIA_FIDELIDADE_PREVENTIVA = """
# AUDITORIA PREVENTIVA DE FIDELIDADE (v1.0)

Você é um auditor sênior especializado em validação de transcrições jurídicas formatadas.

## CONTEXTO
Este documento foi gerado a partir de uma transcrição de aula jurídica.
Você está fazendo a auditoria ANTES da geração do documento final (DOCX).
É sua última chance de detectar problemas CRÍTICOS.

## MÉTRICAS REAIS DO DOCUMENTO (JÁ CALCULADAS - USE ESTES VALORES)
{metricas_info}

**IMPORTANTE:** As métricas acima foram calculadas de forma determinística pelo sistema.
NÃO invente ou estime outros valores. Use EXATAMENTE estes números nas suas observações.

## CONTEXTO DO TRECHO
{chunk_info}

## SUA MISSÃO
Compare a TRANSCRIÇÃO RAW (original) com o TEXTO FORMATADO e identifique:

### 1. 🔴 OMISSÕES CRÍTICAS (GRAVIDADE ALTA)
Informações que estavam no RAW mas foram EXCLUÍDAS no formatado:

**Considere omissão crítica:**
- ❌ Leis, artigos, incisos específicos (ex: Art. 150, VI, "c" → omitido)
- ❌ Súmulas (ex: Súmula 730 STF → omitida)
- ❌ Temas de repercussão geral (ex: Tema 254 → omitido)
- ❌ Casos práticos mencionados (ex: CEDAE Saúde → omitido)
- ❌ Nomes de examinadores/autores (ex: Felipe Silvestre → omitido)
- ❌ Datas importantes (ex: Emenda Constitucional 18/1965 → omitida)
- ❌ Exemplos numéricos (ex: alíquota 2% → omitida)
- ❌ Conceitos jurídicos fundamentais
- ❌ Posicionamentos doutrinários/jurisprudenciais

**NÃO considere omissão:**
- ✅ Hesitações ("né", "então", "olha")
- ✅ Repetições verbais do professor
- ✅ Conversas paralelas ou logística da aula
- ✅ Muletas de linguagem oral

**EXEMPLO DE OMISSÃO CRÍTICA:**
```
RAW: "A súmula 730 do STF prevê que..."
FORMATADO: "A jurisprudência prevê que..."
❌ OMISSÃO: Número da súmula perdido
```

---

### 2. 🔴 DISTORÇÕES (GRAVIDADE ALTA)
Informações que foram ALTERADAS mudando o sentido jurídico:

**Tipos de distorção:**
- ❌ Troca de nomes (Felipe → Gustavo)
- ❌ Inversão de posicionamento ("defende X" → "critica X")
- ❌ Alteração de números (alíquota 2% → 5%)
- ❌ Mudança de datas (2021 → 2024)
- ❌ Troca de órgãos/tribunais (STF → STJ)
- ❌ Atribuição incorreta de autoria de teses

**EXEMPLO DE DISTORÇÃO:**
```
RAW: "O examinador Felipe Silvestre defende a taxatividade da lista"
FORMATADO: "O procurador Gustavo da Gama defende a taxatividade da lista"
❌ DISTORÇÃO: Autoria da tese trocada
```

---

### 3. ⚠️ COMPRESSÃO EXCESSIVA (GRAVIDADE MÉDIA)
Quando o texto formatado está MUITO menor que o RAW, perdendo contexto:

**Indicadores de problema:**
- Taxa de compressão < 70% (formatado com menos de 70% do tamanho do RAW)
- Múltiplos exemplos condensados em um único parágrafo
- Explicações detalhadas substituídas por frases genéricas
- Casos práticos resumidos demais perdendo detalhes

**Análise esperada:**
- Se RAW tem 10.000 palavras e formatado tem 3.000 (30%), verificar se houve perda excessiva
- Modo APOSTILA: aceitável ≥ 70% de retenção (compressão moderada, sem perda de exemplos)
- Modo FIDELIDADE: aceitável 95-115% (mínima compressão)

---

### 4. ⚠️ INCONSISTÊNCIAS ESTRUTURAIS (GRAVIDADE MÉDIA)
Problemas na organização que não refletem o RAW:

- Tópicos fora de ordem cronológica da aula
- Seções duplicadas ou repetidas
- Títulos que não correspondem ao conteúdo
- Quebras lógicas de raciocínio

---

### 5. ⚠️ PROBLEMAS DE CONTEXTO (GRAVIDADE MÉDIA)
Perda de conexão entre ideias:

- Referências a "isso" ou "aquilo" sem antecedente claro
- Transições bruscas entre tópicos
- Pronomes ambíguos ("ele", "o autor") sem identificação

---

### 6. ⚠️ ALUCINAÇÕES (GRAVIDADE ALTA)
Informações que NÃO estavam no RAW mas aparecem no formatado:

**CUIDADO:**
- Para leis recentes (2024-2026), marque como "⚠️ VERIFICAR" (não como erro)
- Só marque como alucinação se tiver CERTEZA que não está no RAW

---

## REGRAS DE ANÁLISE

✅ **LIBERDADES PERMITIDAS:**
- Reordenação de informações (desde que não perca contexto)
- Paráfrase (desde que mantenha o sentido jurídico)
- Síntese de explicações longas (desde que preserve conceitos-chave)
- Limpeza de linguagem oral ("né", "então")

❌ **ERROS CRÍTICOS:**
- Omitir dispositivos legais específicos
- Trocar nomes de pessoas/órgãos/tribunais
- Alterar números, datas, valores
- Atribuir teses ao autor errado
- Perder casos práticos importantes

---

## FORMATO DE RESPOSTA (JSON)

Retorne APENAS JSON válido (sem markdown, sem comentários):

{{
  "aprovado": true/false,
  "nota_fidelidade": 0-10,
  "gravidade_geral": "BAIXA|MÉDIA|ALTA|CRÍTICA",
  "taxa_compressao_estimada": 0.0-1.0,
  
  "omissoes_criticas": [
    {{
      "tipo": "lei|sumula|caso_pratico|conceito|autor",
      "gravidade": "ALTA|MÉDIA|BAIXA",
      "veredito": "CONFIRMADO|SUSPEITO",
      "trecho_raw": "trecho original onde constava",
      "localizacao_formatado": "onde deveria estar no formatado",
      "impacto": "descrição do impacto jurídico/didático"
    }}
  ],
  
  "distorcoes": [
    {{
      "tipo": "troca_nome|inversao_posicionamento|alteracao_numero|troca_data",
      "gravidade": "ALTA|MÉDIA",
      "veredito": "CONFIRMADO|SUSPEITO",
      "trecho_raw": "informação original",
      "trecho_formatado": "informação distorcida",
      "correcao": "como deve ser"
    }}
  ],
  
  "problemas_estruturais": [
    {{
      "tipo": "duplicacao|ordem_errada|titulo_inconsistente",
      "localizacao": "onde está o problema",
      "descricao": "detalhes"
    }}
  ],
  
  "problemas_contexto": [
    {{
      "tipo": "referencia_ambigua|transicao_brusca|pronome_ambiguo",
      "localizacao": "onde está",
      "sugestao": "como melhorar"
    }}
  ],
  
  "alucinacoes": [
    {{
      "trecho_formatado": "informação que não estava no RAW",
      "confianca": "ALTA|MÉDIA|BAIXA",
      "veredito": "CONFIRMADO|SUSPEITO",
      "acao_sugerida": "remover|verificar|investigar"
    }}
  ],
  
  "metricas": {{
    "palavras_raw": 0,
    "palavras_formatado": 0,
    "taxa_retencao": 0.0,
    "dispositivos_legais_raw": 0,
    "dispositivos_legais_formatado": 0,
    "taxa_preservacao_dispositivos": 0.0
  }},

  "observacoes_gerais": "IMPORTANTE: Use APENAS os valores da seção MÉTRICAS REAIS DO DOCUMENTO. Se taxa > 100%, mencione EXPANSÃO (não compressão). Exemplo: 'Taxa de retenção de 108.1% indica expansão de 8.1%'. NÃO invente números.",
  
  "recomendacao_hil": {{
    "pausar_para_revisao": true/false,
    "motivo": "descrição se pausar=true",
    "areas_criticas": ["lista de áreas que precisam atenção"]
  }}
}}

---

## ANÁLISE AUTOMÁTICA DE MÉTRICAS

**IMPORTANTE:** As métricas do documento JÁ FORAM CALCULADAS pelo sistema e estão na seção "MÉTRICAS REAIS DO DOCUMENTO" acima.
NÃO calcule novamente. NÃO invente números. USE EXATAMENTE os valores fornecidos.

1. **Taxa de Retenção (já calculada acima):**
   - Se < 70%: Compressão (texto ficou menor que o original)
   - Se = 100%: Tamanho igual ao original
   - Se > 100%: Expansão (texto ficou maior que o original)

   Interpretação:
   - Taxa 108% = EXPANSÃO de 8% (texto formatado é 8% MAIOR que o RAW)
   - Taxa 70% = COMPRESSÃO de 30% (texto formatado é 30% menor que o RAW)
   - Taxa 95% = COMPRESSÃO de 5% (texto formatado é 5% menor que o RAW)

2. **Nas observações_gerais:**
   - SEMPRE cite os valores EXATOS fornecidos na seção de métricas
   - Se taxa > 100%: mencione que houve EXPANSÃO (não compressão)
   - Se taxa < 100%: mencione que houve COMPRESSÃO
   - NUNCA invente porcentagens ou números diferentes dos fornecidos

3. **Nomes de Pessoas:**
   Extrair do RAW: nomes de examinadores, autores, procuradores
   Verificar no FORMATADO: mesmos nomes aparecem corretamente?
   Marcar como distorção qualquer troca.

---

<transcricao_raw>
{raw}
</transcricao_raw>

<texto_formatado>
{formatted}
</texto_formatado>
"""

def _chunk_bounds(total_len: int, max_chars: int, overlap: int):
    if total_len <= 0:
        return [(0, 0)]
    if total_len <= max_chars:
        return [(0, total_len)]
    step = max_chars - overlap
    if step <= 0:
        step = max_chars
    bounds = []
    start = 0
    while start < total_len:
        end = min(total_len, start + max_chars)
        bounds.append((start, end))
        if end >= total_len:
            break
        start = end - overlap
    return bounds


def _map_chunk(raw_start: int, raw_end: int, raw_len: int, fmt_len: int):
    if raw_len <= 0 or fmt_len <= 0:
        return 0, fmt_len
    fmt_start = int(math.floor((raw_start / raw_len) * fmt_len))
    fmt_end = int(math.ceil((raw_end / raw_len) * fmt_len))
    fmt_start = max(0, min(fmt_start, fmt_len))
    fmt_end = max(fmt_start, min(fmt_end, fmt_len))
    return fmt_start, fmt_end


def _build_chunk_pairs(
    raw_text: str,
    formatted_text: str,
    *,
    max_chars: int = MAX_CHARS_PER_CHUNK,
    overlap_chars: int = CHUNK_OVERLAP_CHARS,
):
    raw_len = len(raw_text)
    fmt_len = len(formatted_text)
    bounds = _chunk_bounds(raw_len, max_chars, overlap_chars)
    chunks = []
    for idx, (r_start, r_end) in enumerate(bounds, 1):
        f_start, f_end = _map_chunk(r_start, r_end, raw_len, fmt_len)
        chunks.append({
            "index": idx,
            "raw_start": r_start,
            "raw_end": r_end,
            "fmt_start": f_start,
            "fmt_end": f_end,
            "raw": raw_text[r_start:r_end],
            "formatted": formatted_text[f_start:f_end],
        })
    return chunks


def _safe_json_parse(text: str):
    if not text:
        return None
    raw = text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    match = re.search(r'```(?:json)?\s*([\s\S]*?)```', raw)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass
    brace_start = raw.find('{')
    brace_end = raw.rfind('}')
    if brace_start != -1 and brace_end > brace_start:
        try:
            return json.loads(raw[brace_start:brace_end + 1])
        except json.JSONDecodeError:
            pass
    return None


def _normalize_gravidade(value: str):
    if not isinstance(value, str):
        return "BAIXA"
    upper = value.strip().upper()
    if upper in GRAVIDADE_ORDEM:
        return upper
    return "BAIXA"


def _dedup_items(items, keys):
    if not isinstance(items, list):
        return []
    seen = set()
    deduped = []
    for item in items:
        if not isinstance(item, dict):
            item = {"descricao": str(item)}
        parts = []
        for key in keys:
            parts.append(str(item.get(key, "")).strip().lower())
        sig = "|".join(parts)
        if sig in seen:
            continue
        seen.add(sig)
        deduped.append(item)
        if len(deduped) >= MAX_LIST_ITEMS:
            break
    return deduped


def _summarize_item(item: dict, fallback_keys):
    if not isinstance(item, dict):
        return str(item)
    parts = []
    item_type = item.get("tipo")
    if item_type:
        parts.append(str(item_type))
    for key in fallback_keys:
        value = item.get(key)
        if value:
            parts.append(str(value))
            break
    summary = " - ".join(parts).strip()
    if len(summary) > 240:
        summary = summary[:240] + "..."
    return summary or json.dumps(item, ensure_ascii=False)[:240]


def _extract_dispositivos(text: str):
    if not text:
        return set()
    pattern = re.compile(
        r"\b("
        r"(?:art\.?\s*\d+[º°]?(?:\s*,?\s*inciso\s+[IVXLC]+)?)|"
        r"(?:artigo\s*\d+[º°]?)|"
        r"(?:lei\s*(?:complementar\s*)?n?º?\s*\d+(?:[./]\d+)?)|"
        r"(?:s[úu]mula\s+\d+)|"
        r"(?:tema\s+\d+)|"
        r"(?:(?:re|are|adpf|dpf|adi|adc|hc|ms|rms)\s*\d{1,7})"
        r")\b",
        re.IGNORECASE
    )
    found = set()
    for match in pattern.findall(text):
        found.add(match.strip().lower())
    return found


def _build_compat_report(resultado: dict):
    if not isinstance(resultado, dict):
        return {}
    omissoes = resultado.get("omissoes_criticas", []) or []
    distorcoes = resultado.get("distorcoes", []) or []
    estruturais = resultado.get("problemas_estruturais", []) or []
    compat = {
        "aprovado": resultado.get("aprovado", True),
        "nota": resultado.get("nota_fidelidade", resultado.get("nota", 0)),
        "nota_fidelidade": resultado.get("nota_fidelidade", resultado.get("nota", 0)),
        "omissoes": [_summarize_item(item, ["impacto", "trecho_raw", "localizacao_formatado"]) for item in omissoes],
        "omissoes_graves": [_summarize_item(item, ["impacto", "trecho_raw", "localizacao_formatado"]) for item in omissoes],
        "distorcoes": [_summarize_item(item, ["trecho_raw", "trecho_formatado", "correcao"]) for item in distorcoes],
        "problemas_estrutura": [_summarize_item(item, ["descricao", "localizacao"]) for item in estruturais],
        "observacoes": resultado.get("observacoes_gerais", resultado.get("observacoes", "")),
        "source": "audit_fidelity_preventive",
    }
    return compat


def _filter_chunk_boundary_false_positives(
    raw_text: str,
    formatted_text: str,
    estruturais: list,
    contexto: list,
):
    """
    Remove falsos positivos comuns gerados por limites de chunk:
    - "o texto termina/continua" inferido por fim de trecho, não por fim real do documento.
    - referência a um título N quando existem títulos posteriores no formatado.
    """
    if not formatted_text:
        return estruturais, contexto

    # Collect existing H2 numbers in formatted markdown like "## 43."
    heading_nums: list[int] = []
    for m in re.finditer(r"^##\s+(\d+)\.", formatted_text, flags=re.MULTILINE):
        try:
            heading_nums.append(int(m.group(1)))
        except Exception:
            continue
    max_heading = max(heading_nums) if heading_nums else None

    def _mentions_end(text: str) -> bool:
        t = (text or "").lower()
        return any(tok in t for tok in ("termina", "final do documento", "continua no próximo", "continua no proximo"))

    def _extract_quoted_snippet(text: str) -> str | None:
        if not text:
            return None
        # Prefer single quotes, then double quotes
        for pat in (r"'([^']{6,300})'", r"\"([^\"]{6,300})\""):
            m = re.search(pat, text)
            if m:
                return m.group(1)
        return None

    def _is_truncation_false_positive(item: dict) -> bool:
        """
        Detect common LLM false positives where it thinks the document ends mid-word
        just because a chunk ended (e.g. "... pa" but the full text contains "paciente").
        """
        if not isinstance(item, dict):
            return False
        item_type = str(item.get("tipo") or "").lower()
        if item_type != "truncamento":
            return False
        desc = str(item.get("descricao") or "")
        snippet = _extract_quoted_snippet(desc)
        if not snippet:
            return False

        # If the snippet ends with ellipsis, test whether the full formatted text continues it.
        normalized = snippet.replace("…", "...")
        if "..." not in normalized:
            return False
        prefix = normalized.split("...", 1)[0].rstrip()
        if len(prefix) < 6:
            return False

        # If the document truly ends truncated, the full formatted text should end with this prefix (or very near it).
        tail = (formatted_text or "")[-600:].rstrip()
        if tail.lower().endswith(prefix.lower()):
            return False

        # If we find a match where the next char is alphanumeric, it's almost certainly just a chunk boundary.
        try:
            for m in re.finditer(re.escape(prefix), formatted_text, flags=re.IGNORECASE):
                end = m.end()
                if end < len(formatted_text) and formatted_text[end].isalnum():
                    return True
        except re.error:
            return False
        return False

    def _extract_heading_number(text: str) -> int | None:
        if not text:
            return None
        m = re.search(r"(?:t[ií]tulo|se[cç][aã]o)\s+'?\"?(\d+)(?:\.)?", text, flags=re.IGNORECASE)
        if not m:
            m = re.search(r"##\s+(\d+)\.", text)
        if not m:
            return None
        try:
            return int(m.group(1))
        except Exception:
            return None

    filtered_estruturais = []
    for item in (estruturais or []):
        if not isinstance(item, dict):
            filtered_estruturais.append(item)
            continue
        descricao = str(item.get("descricao") or "")
        if _is_truncation_false_positive(item):
            continue
        num = _extract_heading_number(descricao)
        if _mentions_end(descricao) and num is not None and max_heading is not None and max_heading > num:
            # There are later headings, so it doesn't "end" at this heading.
            continue
        filtered_estruturais.append(item)

    filtered_contexto = []
    for item in (contexto or []):
        if not isinstance(item, dict):
            filtered_contexto.append(item)
            continue
        sugestao = str(item.get("sugestao") or "")
        num = _extract_heading_number(sugestao) or _extract_heading_number(str(item.get("localizacao") or ""))
        if _mentions_end(sugestao) and num is not None and max_heading is not None and max_heading > num:
            # Suggestion about "continue/end" is likely chunk-boundary noise when later headings exist.
            continue
        filtered_contexto.append(item)

    return filtered_estruturais, filtered_contexto


def _filter_ref_based_omission_false_positives(
    dispositivos_raw: set,
    dispositivos_fmt: set,
    omissoes: list,
):
    """
    Remove falsos positivos clássicos de omissão gerados pelo LLM:
    - Omissões de "Lei/Súmula/Tema/RE/ADPF..." que não aparecem no RAW (alucinação).
    - Itens marcados como omissão quando o dispositivo já está presente no formatado.
    """
    if not isinstance(omissoes, list):
        return []
    out = []
    for item in omissoes:
        if not isinstance(item, dict):
            out.append(item)
            continue
        trecho_raw = str(item.get("trecho_raw") or "")
        refs = _extract_dispositivos(trecho_raw)
        if refs:
            if not any(ref in dispositivos_raw for ref in refs):
                # If the referenced device isn't in the RAW at all, this is almost certainly hallucinated.
                continue
            if any(ref in dispositivos_fmt for ref in refs):
                # Already present in formatted; not an omission.
                continue
            item["veredito"] = "CONFIRMADO"
        out.append(item)
        if len(out) >= MAX_LIST_ITEMS:
            break
    return out


def _extract_names_from_text(text: str) -> set:
    """
    Extrai nomes próprios de um texto (sequências de 2+ palavras capitalizadas).
    """
    if not text:
        return set()
    names = set()
    # Padrão: 2+ palavras começando com maiúscula (ex: "Nelson Rosenwald", "Gustavo Tepedino")
    pattern = re.compile(r'\b([A-ZÁÀÂÃÉÈÊÍÏÓÔÕÖÚÇ][a-záàâãéèêíïóôõöúç]+(?:\s+[A-ZÁÀÂÃÉÈÊÍÏÓÔÕÖÚÇ][a-záàâãéèêíïóôõöúç]+)+)\b')
    for match in pattern.findall(text):
        name = match.strip()
        # Ignorar nomes muito curtos ou genéricos
        if len(name) > 6 and len(name.split()) >= 2:
            names.add(name.lower())
    return names


def _filter_hallucination_false_positives(
    raw_text: str,
    alucinacoes: list,
) -> list:
    """
    Remove falsos positivos de alucinações:
    - Quando o LLM reporta um nome como alucinação mas o nome existe no RAW completo
      (apenas não estava no chunk correspondente).

    Args:
        raw_text: Texto RAW completo (não apenas o chunk)
        alucinacoes: Lista de alucinações reportadas pelo LLM

    Returns:
        Lista filtrada de alucinações reais
    """
    if not isinstance(alucinacoes, list) or not raw_text:
        return alucinacoes or []

    raw_lower = raw_text.lower()
    raw_names = _extract_names_from_text(raw_text)

    out = []
    for item in alucinacoes:
        if not isinstance(item, dict):
            out.append(item)
            continue

        trecho = str(item.get("trecho_formatado") or "")
        if not trecho:
            out.append(item)
            continue

        # Extrair nomes do trecho reportado como alucinação
        trecho_names = _extract_names_from_text(trecho)

        # Se todos os nomes do trecho existem no RAW, é falso positivo
        if trecho_names:
            all_names_in_raw = all(name in raw_names or name in raw_lower for name in trecho_names)
            if all_names_in_raw:
                # O nome existe no RAW - falso positivo por chunk boundary
                continue

        # Verificação adicional: o trecho inteiro ou partes significativas estão no RAW?
        trecho_lower = trecho.lower().strip()
        if len(trecho_lower) > 10:
            # Se o trecho exato existe no RAW, é falso positivo
            if trecho_lower in raw_lower:
                continue
            # Verificar partes do trecho (palavras-chave)
            keywords = [w for w in trecho_lower.split() if len(w) > 4]
            if keywords:
                keywords_found = sum(1 for kw in keywords if kw in raw_lower)
                if keywords_found / len(keywords) >= 0.7:
                    # 70%+ das palavras-chave estão no RAW - provável falso positivo
                    item["confianca"] = "BAIXA"
                    item["veredito"] = "SUSPEITO"

        out.append(item)
        if len(out) >= MAX_LIST_ITEMS:
            break

    return out


def auditar_fidelidade_preventiva(
    client,
    raw_text: str,
    formatted_text: str,
    doc_name: str,
    output_path: str = None,
    modo: str = "APOSTILA",
    include_sources: bool = True,
    audit_model: str | None = None,
):
    """
    Auditoria preventiva completa de fidelidade.
    
    Detecta:
    - Omissões críticas (leis, súmulas, casos, conceitos)
    - Distorções (trocas de nomes, números, datas)
    - Compressão excessiva
    - Problemas estruturais
    - Perda de contexto
    - Alucinações
    
    Args:
        client: Cliente Gemini
        raw_text: Transcrição bruta original
        formatted_text: Texto formatado/apostila
        doc_name: Nome do documento
        output_path: Caminho para salvar JSON (opcional)
        modo: APOSTILA ou FIDELIDADE (afeta thresholds)
        include_sources: Se True, integra auditoria de fontes/autoria
    
    Returns:
        dict: Resultado completo da auditoria
    """
    modo = (modo or "APOSTILA").upper()
    include_sources = bool(include_sources)

    print(f"\n{'='*80}")
    print("🔬 AUDITORIA PREVENTIVA DE FIDELIDADE (v1.0)")
    print(f"{'='*80}")
    print(f"📄 Documento: {doc_name}")
    print(f"🎯 Modo: {modo}")
    print(f"📊 Analisando RAW ({len(raw_text):,} chars) vs Formatado ({len(formatted_text):,} chars)")

    # Calcular taxa de compressão prévia
    palavras_raw = len(raw_text.split())
    palavras_fmt = len(formatted_text.split())
    taxa_compressao = palavras_fmt / palavras_raw if palavras_raw > 0 else 0

    print(f"   Taxa de compressão: {taxa_compressao*100:.1f}%")

    if modo == "FIDELIDADE":
        if taxa_compressao < FIDELIDADE_MIN_RETENTION or taxa_compressao > FIDELIDADE_MAX_RETENTION:
            print(f"   ⚠️ ALERTA: Em modo FIDELIDADE, esperado 95-115% (encontrado {taxa_compressao*100:.1f}%)")
    elif modo == "APOSTILA" and taxa_compressao < APOSTILA_MIN_RETENTION:
        print(f"   ⚠️ ALERTA: Compressão muito agressiva ({taxa_compressao*100:.1f}%)")

    dispositivos_raw = _extract_dispositivos(raw_text)
    dispositivos_fmt = _extract_dispositivos(formatted_text)
    taxa_preservacao = (len(dispositivos_fmt) / len(dispositivos_raw)) if dispositivos_raw else 1.0

    audit_model_name = _normalize_model_name(audit_model)
    adaptive_chunk_chars, adaptive_overlap_chars = _estimate_effective_chunk_config(
        raw_text,
        formatted_text,
        audit_model_name,
    )
    chunks = _build_chunk_pairs(
        raw_text,
        formatted_text,
        max_chars=adaptive_chunk_chars,
        overlap_chars=adaptive_overlap_chars,
    )
    print(
        f"   🔪 Chunks: {len(chunks)} (max {adaptive_chunk_chars:,} chars, "
        f"overlap {adaptive_overlap_chars:,}, model {audit_model_name})"
    )

    resultados = []
    chunk_word_counts = []

    # Preparar string de métricas para incluir no prompt
    # Importante: Informar claramente se houve expansão ou compressão
    if taxa_compressao > 1.0:
        tipo_variacao = f"EXPANSÃO de {(taxa_compressao - 1.0) * 100:.1f}% (texto formatado é MAIOR que o RAW)"
    elif taxa_compressao < 1.0:
        tipo_variacao = f"COMPRESSÃO de {(1.0 - taxa_compressao) * 100:.1f}% (texto formatado é menor que o RAW)"
    else:
        tipo_variacao = "TAMANHO IGUAL (sem variação)"

    metricas_info = f"""
- **Modo:** {modo}
- **Palavras no RAW (original):** {palavras_raw:,}
- **Palavras no Formatado:** {palavras_fmt:,}
- **Taxa de Retenção:** {taxa_compressao * 100:.1f}% → {tipo_variacao}
- **Dispositivos Legais no RAW:** {len(dispositivos_raw)}
- **Dispositivos Legais no Formatado:** {len(dispositivos_fmt)}
- **Taxa de Preservação de Dispositivos:** {taxa_preservacao * 100:.1f}%
"""

    print("\n🤖 Executando análise via LLM...")

    def _process_audit_chunk(chunk: dict, total_chunks: int, metricas_info_str: str) -> tuple:
        """Processa um único chunk de auditoria. Retorna (index, parsed, word_count)."""
        is_last_chunk = chunk["index"] == total_chunks
        chunk_info = (
            f"Trecho {chunk['index']} de {total_chunks} "
            f"(RAW {chunk['raw_start']:,}-{chunk['raw_end']:,}, "
            f"FMT {chunk['fmt_start']:,}-{chunk['fmt_end']:,}). "
            f"{'Este é o ÚLTIMO trecho.' if is_last_chunk else 'Este NÃO é o final do documento.'} "
            "Avalie apenas este trecho e NÃO conclua que o documento terminou apenas porque o trecho acabou."
        )
        prompt = PROMPT_AUDITORIA_FIDELIDADE_PREVENTIVA.format(
            raw=chunk["raw"],
            formatted=chunk["formatted"],
            chunk_info=chunk_info,
            metricas_info=metricas_info_str,
        )

        config = types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=16000,
            response_mime_type="application/json",
            http_options=types.HttpOptions(timeout=GEMINI_HTTP_TIMEOUT_MS),
            thinking_config=types.ThinkingConfig(
                include_thoughts=False,
                thinking_level="HIGH"
            ),
        )
        response_text = _call_gemini_with_retry(
            client,
            prompt,
            config,
            model_name=audit_model_name,
        )

        parsed = _safe_json_parse(response_text)
        if not isinstance(parsed, dict):
            parsed = {
                "aprovado": False,
                "nota_fidelidade": 0,
                "gravidade_geral": "CRÍTICA",
                "erro": "JSON inválido para trecho",
            }
        parsed["_chunk_index"] = chunk["index"]
        # Attach chunk index to child items
        for key in ("omissoes_criticas", "distorcoes", "problemas_estruturais", "problemas_contexto", "alucinacoes"):
            items = parsed.get(key)
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        item.setdefault("_chunk_index", chunk["index"])

        word_count = len(chunk["raw"].split())
        return (chunk["index"], parsed, word_count)

    # Processar chunks em paralelo usando ThreadPoolExecutor
    total_chunks = len(chunks)
    try:
        if total_chunks <= 1 or PARALLEL_AUDIT_WORKERS <= 1:
            # Modo sequencial para poucos chunks
            for chunk in chunks:
                idx, parsed, wc = _process_audit_chunk(chunk, total_chunks, metricas_info)
                resultados.append(parsed)
                chunk_word_counts.append(wc)
                print(f"   ✅ Chunk {idx}/{total_chunks} processado")
        else:
            # Modo paralelo
            print(f"   🚀 Processando {total_chunks} chunks em paralelo (max {PARALLEL_AUDIT_WORKERS} workers)...")
            with ThreadPoolExecutor(max_workers=PARALLEL_AUDIT_WORKERS) as executor:
                futures = {
                    executor.submit(_process_audit_chunk, chunk, total_chunks, metricas_info): chunk["index"]
                    for chunk in chunks
                }
                results_map = {}
                for future in as_completed(futures):
                    chunk_idx = futures[future]
                    try:
                        idx, parsed, wc = future.result()
                        results_map[idx] = (parsed, wc)
                        print(f"   ✅ Chunk {idx}/{total_chunks} concluído")
                    except Exception as e:
                        print(f"   ❌ Erro no chunk {chunk_idx}: {e}")
                        results_map[chunk_idx] = ({
                            "aprovado": False,
                            "nota_fidelidade": 0,
                            "gravidade_geral": "CRÍTICA",
                            "erro": str(e),
                            "_chunk_index": chunk_idx,
                        }, 0)

            # Ordenar resultados por índice
            for i in range(1, total_chunks + 1):
                parsed, wc = results_map.get(i, ({}, 0))
                resultados.append(parsed)
                chunk_word_counts.append(wc)

        aprovado = True
        gravidade = "BAIXA"
        nota_soma = 0.0
        nota_peso = 0.0
        omissoes = []
        distorcoes = []
        estruturais = []
        contexto = []
        alucinacoes = []
        observacoes = []
        recom_pausar = False
        recom_motivos = []
        areas_criticas = []

        for idx, result in enumerate(resultados):
            aprovado = aprovado and bool(result.get("aprovado", True))
            grav_chunk = _normalize_gravidade(result.get("gravidade_geral", "BAIXA"))
            if GRAVIDADE_ORDEM.get(grav_chunk, 0) > GRAVIDADE_ORDEM.get(gravidade, 0):
                gravidade = grav_chunk

            nota = result.get("nota_fidelidade")
            if isinstance(nota, (int, float)):
                peso = chunk_word_counts[idx] if idx < len(chunk_word_counts) else 1
                nota_soma += float(nota) * peso
                nota_peso += peso

            omissoes.extend(result.get("omissoes_criticas", []) or [])
            distorcoes.extend(result.get("distorcoes", []) or [])
            estruturais.extend(result.get("problemas_estruturais", []) or [])
            contexto.extend(result.get("problemas_contexto", []) or [])
            alucinacoes.extend(result.get("alucinacoes", []) or [])
            obs = result.get("observacoes_gerais")
            if obs:
                observacoes.append(str(obs).strip())

            recom = result.get("recomendacao_hil") or {}
            if recom.get("pausar_para_revisao"):
                recom_pausar = True
                motivo = recom.get("motivo")
                if motivo:
                    recom_motivos.append(motivo)
                areas = recom.get("areas_criticas", [])
                if isinstance(areas, list):
                    for area in areas:
                        if area not in areas_criticas:
                            areas_criticas.append(area)

        nota_final = (nota_soma / nota_peso) if nota_peso else 0.0

        resultado = {
            "aprovado": aprovado,
            "nota_fidelidade": round(nota_final, 2),
            "gravidade_geral": gravidade,
            "taxa_compressao_estimada": round(taxa_compressao, 4),
            "omissoes_criticas": _dedup_items(omissoes, ["tipo", "trecho_raw", "localizacao_formatado", "impacto"]),
            "distorcoes": _dedup_items(distorcoes, ["tipo", "trecho_raw", "trecho_formatado", "correcao"]),
            "problemas_estruturais": _dedup_items(estruturais, ["tipo", "localizacao", "descricao"]),
            "problemas_contexto": _dedup_items(contexto, ["tipo", "localizacao", "sugestao"]),
            "alucinacoes": _dedup_items(alucinacoes, ["trecho_formatado", "acao_sugerida", "confianca"]),
            "metricas": {
                "palavras_raw": palavras_raw,
                "palavras_formatado": palavras_fmt,
                "taxa_retencao": round(taxa_compressao, 4),
                "dispositivos_legais_raw": len(dispositivos_raw),
                "dispositivos_legais_formatado": len(dispositivos_fmt),
                "taxa_preservacao_dispositivos": round(taxa_preservacao, 4),
            },
            "observacoes_gerais": " / ".join([o for o in observacoes if o])[:2000],
            "recomendacao_hil": {
                "pausar_para_revisao": bool(recom_pausar),
                "motivo": " / ".join(dict.fromkeys(recom_motivos))[:500],
                "areas_criticas": areas_criticas,
            },
            "chunks": {
                "total": len(chunks),
                "max_chars": adaptive_chunk_chars,
                "overlap_chars": adaptive_overlap_chars,
                "model": audit_model_name,
                "context_tokens": _get_model_context_tokens(audit_model_name),
            },
        }

        # Filter known chunk-boundary false positives before sources audit and invariants.
        filtered_estruturais, filtered_contexto = _filter_chunk_boundary_false_positives(
            raw_text,
            formatted_text,
            resultado.get("problemas_estruturais") or [],
            resultado.get("problemas_contexto") or [],
        )
        resultado["problemas_estruturais"] = filtered_estruturais
        resultado["problemas_contexto"] = filtered_contexto

        # Filter hallucinated/duplicate omissions by deterministic device extraction.
        resultado["omissoes_criticas"] = _filter_ref_based_omission_false_positives(
            dispositivos_raw,
            dispositivos_fmt,
            resultado.get("omissoes_criticas") or [],
        )

        # Filter hallucination false positives (names/content that exist in full RAW but not in chunk).
        resultado["alucinacoes"] = _filter_hallucination_false_positives(
            raw_text,
            resultado.get("alucinacoes") or [],
        )

        def _normalize_result_invariants(out: dict) -> dict:
            """
            Normalize/repair inconsistent outcomes from the LLM.

            We consider the audit "passable" when:
              - No critical lists are populated (omissions/distortions/hallucinations)
              - No HIL pause recommendation
              - Sources audit (when present) is approved
              - Retention is within acceptable thresholds for the chosen mode
            """
            metricas = out.get("metricas") or {}
            taxa_retencao = float(metricas.get("taxa_retencao") or 0.0)
            omissoes_n = len(out.get("omissoes_criticas") or [])
            distorcoes_n = len(out.get("distorcoes") or [])
            alucinacoes_n = len(out.get("alucinacoes") or [])
            estruturais_n = len(out.get("problemas_estruturais") or [])
            contexto_n = len(out.get("problemas_contexto") or [])
            recom = out.get("recomendacao_hil") or {}
            pausar = bool(recom.get("pausar_para_revisao"))

            fontes_ok = True
            fontes = out.get("auditoria_fontes")
            if isinstance(fontes, dict) and "aprovado" in fontes:
                fontes_ok = bool(fontes.get("aprovado"))

            if modo == "FIDELIDADE":
                retention_ok = (FIDELIDADE_MIN_RETENTION <= taxa_retencao <= FIDELIDADE_MAX_RETENTION)
            else:
                retention_ok = (taxa_retencao >= APOSTILA_MIN_RETENTION)

            no_critical = (omissoes_n == 0 and distorcoes_n == 0 and alucinacoes_n == 0)
            no_other = (estruturais_n == 0 and contexto_n == 0)
            should_pass = no_critical and not pausar and fontes_ok and retention_ok

            if should_pass:
                # Promote status to approved and ensure score matches the absence of issues.
                base_score = 9.2 if modo == "FIDELIDADE" else 8.8
                try:
                    current = float(out.get("nota_fidelidade") or 0.0)
                except Exception:
                    current = 0.0
                out["aprovado"] = True
                out["gravidade_geral"] = "BAIXA"
                out["nota_fidelidade"] = round(max(current, base_score), 2)
                # Keep report consistent: if there are no issues, clear any leftover generic motive.
                if isinstance(recom, dict):
                    recom["pausar_para_revisao"] = False
                    recom["motivo"] = ""
                    recom["areas_criticas"] = recom.get("areas_criticas") or []
                    out["recomendacao_hil"] = recom
                return out

            # If we have critical findings but status says approved, downgrade.
            if not no_critical and bool(out.get("aprovado", False)):
                out["aprovado"] = False
                if _normalize_gravidade(out.get("gravidade_geral", "BAIXA")) == "BAIXA":
                    out["gravidade_geral"] = "ALTA"
            return out

        # Auditoria de fontes (integrada, opcional)
        if include_sources and SOURCES_AUDIT_AVAILABLE and auditar_atribuicao_fontes:
            fontes_result = auditar_atribuicao_fontes(
                client,
                raw_text,
                formatted_text,
                doc_name,
                output_path=None,
            )
            resultado["auditoria_fontes"] = fontes_result

            erros_criticos = (fontes_result or {}).get("erros_criticos", []) or []
            if erros_criticos:
                recom = resultado.get("recomendacao_hil") or {}
                recom["pausar_para_revisao"] = True
                motivo = recom.get("motivo")
                if motivo:
                    recom["motivo"] = f"{motivo} / Erros críticos de autoria"
                else:
                    recom["motivo"] = "Erros críticos de autoria detectados"
                areas = recom.get("areas_criticas")
                if not isinstance(areas, list):
                    areas = []
                if "autoria" not in areas:
                    areas.append("autoria")
                recom["areas_criticas"] = areas
                resultado["recomendacao_hil"] = recom

        resultado = _normalize_result_invariants(resultado)
        resultado["compat_fidelidade"] = _build_compat_report(resultado)

        # Salvar se path fornecido
        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(resultado, f, ensure_ascii=False, indent=2)
            print(f"\n✅ Relatório JSON salvo: {output_path}")

        # Feedback visual
        print(f"\n{'='*80}")
        print("📋 RESULTADO DA AUDITORIA")
        print(f"{'='*80}")

        if aprovado:
            print(f"✅ STATUS: APROVADO")
        else:
            print(f"⚠️ STATUS: REQUER REVISÃO")

        print(f"📊 Nota de Fidelidade: {nota_final:.1f}/10")
        print(f"🎚️  Gravidade Geral: {gravidade}")

        # Contadores
        omissoes_count = len(resultado.get('omissoes_criticas', []))
        distorcoes_count = len(resultado.get('distorcoes', []))
        estruturais_count = len(resultado.get('problemas_estruturais', []))
        contexto_count = len(resultado.get('problemas_contexto', []))
        alucinacoes_count = len(resultado.get('alucinacoes', []))

        print(f"\n📌 Problemas Detectados:")
        if omissoes_count > 0:
            print(f"   🔴 {omissoes_count} omissão(ões) crítica(s)")
        if distorcoes_count > 0:
            print(f"   🔴 {distorcoes_count} distorção(ões)")
        if estruturais_count > 0:
            print(f"   ⚠️  {estruturais_count} problema(s) estrutural(is)")
        if contexto_count > 0:
            print(f"   ⚠️  {contexto_count} problema(s) de contexto")
        if alucinacoes_count > 0:
            print(f"   🔴 {alucinacoes_count} possível(is) alucinação(ões)")

        if omissoes_count == 0 and distorcoes_count == 0 and alucinacoes_count == 0:
            print(f"   ✅ Nenhum problema crítico detectado!")

        # Recomendação HIL
        recom_hil = resultado.get('recomendacao_hil', {})
        if recom_hil.get('pausar_para_revisao'):
            print(f"\n🛑 RECOMENDAÇÃO: PAUSAR PARA REVISÃO HIL")
            print(f"   Motivo: {recom_hil.get('motivo', 'Problemas críticos detectados')}")
            areas = recom_hil.get('areas_criticas', [])
            if areas:
                print(f"   Áreas críticas: {', '.join(areas)}")

        print(f"{'='*80}\n")

        return resultado

    except Exception as e:
        print(f"❌ Erro na auditoria: {e}")
        palavras_raw = len(raw_text.split()) if raw_text else 0
        palavras_fmt = len(formatted_text.split()) if formatted_text else 0
        taxa_retencao = (palavras_fmt / palavras_raw) if palavras_raw > 0 else 0
        fallback = {
            "aprovado": False,
            "nota_fidelidade": 0,
            "gravidade_geral": "CRÍTICA",
            "erro": str(e),
            "omissoes_criticas": [],
            "distorcoes": [],
            "problemas_estruturais": [],
            "problemas_contexto": [],
            "alucinacoes": [],
            "metricas": {
                "palavras_raw": palavras_raw,
                "palavras_formatado": palavras_fmt,
                "taxa_retencao": round(taxa_retencao, 4),
                "dispositivos_legais_raw": 0,
                "dispositivos_legais_formatado": 0,
                "taxa_preservacao_dispositivos": 0,
            },
            "observacoes_gerais": "Falha ao gerar auditoria preventiva.",
            "recomendacao_hil": {
                "pausar_para_revisao": True,
                "motivo": f"Falha ao gerar auditoria preventiva: {e}",
                "areas_criticas": ["auditoria_preventiva"],
            },
            "source": "audit_fidelity_preventive",
        }
        fallback["compat_fidelidade"] = _build_compat_report(fallback)
        if output_path:
            try:
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(fallback, f, ensure_ascii=False, indent=2)
                print(f"\n⚠️ Relatório JSON (fallback) salvo: {output_path}")
            except Exception as write_error:
                print(f"⚠️ Falha ao salvar relatório JSON (fallback): {write_error}")
        return fallback


def gerar_relatorio_markdown_completo(resultado: dict, output_md: str, doc_name: str):
    """Gera relatório markdown detalhado para revisão HIL."""

    def _to_float(value, default: float = 0.0) -> float:
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            return float(value)
        if isinstance(value, str):
            raw = value.strip()
            # Accept "0.0/10", "0,0", "7.5", etc.
            m = re.search(r"([0-9]+(?:[.,][0-9]+)?)", raw)
            if m:
                try:
                    return float(m.group(1).replace(",", "."))
                except Exception:
                    return default
        return default

    def _as_dict(item, *, kind: str) -> dict:
        if isinstance(item, dict):
            return item
        # Keep string/list/etc readable without crashing .get()
        return {"tipo": kind, "descricao": str(item)}

    with open(output_md, 'w', encoding='utf-8') as f:
        f.write(f"# 🔬 AUDITORIA PREVENTIVA DE FIDELIDADE: {doc_name}\n\n")
        
        # Status geral
        status = "✅ APROVADO" if resultado.get('aprovado') else "⚠️ REQUER REVISÃO"
        nota = _to_float(resultado.get('nota_fidelidade', 0), 0.0)
        gravidade = resultado.get('gravidade_geral', 'N/A')
        
        f.write(f"**Status:** {status}\n")
        f.write(f"**Nota de Fidelidade:** {nota:.1f}/10\n")
        f.write(f"**Gravidade Geral:** {gravidade}\n\n")

        # Erro (quando presente)
        erro = resultado.get("erro")
        if erro:
            f.write("## ❌ Erro\n\n")
            f.write(f"{str(erro).strip()}\n\n")
        
        # Métricas
        metricas = resultado.get('metricas', {})
        if metricas:
            f.write("## 📊 Métricas\n\n")
            f.write(f"- **Palavras RAW:** {metricas.get('palavras_raw', 0):,}\n")
            f.write(f"- **Palavras Formatado:** {metricas.get('palavras_formatado', 0):,}\n")
            f.write(f"- **Taxa de Retenção:** {metricas.get('taxa_retencao', 0)*100:.1f}%\n")
            
            if metricas.get('dispositivos_legais_raw'):
                f.write(f"- **Dispositivos Legais RAW:** {metricas['dispositivos_legais_raw']}\n")
                f.write(f"- **Dispositivos Legais Formatado:** {metricas['dispositivos_legais_formatado']}\n")
                f.write(f"- **Taxa Preservação:** {metricas.get('taxa_preservacao_dispositivos', 0)*100:.1f}%\n")
            
            f.write("\n")
        
        # Omissões Críticas
        omissoes = resultado.get('omissoes_criticas', [])
        if omissoes:
            f.write(f"## 🔴 OMISSÕES CRÍTICAS ({len(omissoes)})\n\n")
            for i, om in enumerate(omissoes, 1):
                om = _as_dict(om, kind="omissao")
                f.write(f"### {i}. {str(om.get('tipo') or 'Omissão').upper()}\n\n")
                if om.get("gravidade"):
                    f.write(f"**Gravidade:** {om.get('gravidade')}\n\n")
                
                trecho_raw = om.get('trecho_raw') or om.get("raw") or ""
                if trecho_raw:
                    f.write(f"**Estava no RAW:**\n```\n{str(trecho_raw)[:300]}\n```\n\n")
                
                if om.get('localizacao_formatado'):
                    f.write(f"**Onde deveria estar:** {om['localizacao_formatado']}\n\n")
                
                impacto = om.get('impacto') or om.get("descricao") or ""
                if impacto:
                    f.write(f"**Impacto:** {str(impacto)}\n\n")
                
                f.write("---\n\n")
        
        # Distorções
        distorcoes = resultado.get('distorcoes', [])
        if distorcoes:
            f.write(f"## 🔴 DISTORÇÕES ({len(distorcoes)})\n\n")
            for i, dist in enumerate(distorcoes, 1):
                dist = _as_dict(dist, kind="distorcao")
                f.write(f"### {i}. {str(dist.get('tipo') or 'Distorção').upper()}\n\n")
                if dist.get("gravidade"):
                    f.write(f"**Gravidade:** {dist.get('gravidade')}\n\n")
                
                if dist.get('trecho_raw'):
                    f.write(f"**RAW (Correto):**\n```\n{dist['trecho_raw'][:200]}\n```\n\n")
                
                if dist.get('trecho_formatado'):
                    f.write(f"**Formatado (Errado):**\n```\n{dist['trecho_formatado'][:200]}\n```\n\n")
                
                if dist.get('correcao'):
                    f.write(f"**Correção:** {dist['correcao']}\n\n")
                
                f.write("---\n\n")

        # Auditoria de Fontes (Integrada)
        fontes = resultado.get("auditoria_fontes")
        if fontes:
            status_fontes = "✅ APROVADO" if fontes.get("aprovado") else "⚠️ REQUER REVISÃO"
            nota_fontes = fontes.get("nota_consistencia", 0)
            f.write("## 📚 AUDITORIA DE FONTES (INTEGRADA)\n\n")
            f.write(f"**Status:** {status_fontes}\n")
            f.write(f"**Nota de Consistência:** {nota_fontes}/10\n\n")

            erros_fontes = fontes.get("erros_criticos", [])
            if erros_fontes:
                f.write(f"### 🔴 Erros Críticos de Autoria ({len(erros_fontes)})\n\n")
                for erro in erros_fontes:
                    erro = _as_dict(erro, kind="erro_autoria")
                    f.write(f"- **{erro.get('tipo', 'troca_autoria')}** ({erro.get('localizacao', 'N/A')}): ")
                    trecho = erro.get("trecho_formatado") or erro.get("trecho_raw") or erro.get("descricao") or ""
                    f.write(f"{trecho[:180]}\n")
                f.write("\n")

            ambiguidades = fontes.get("ambiguidades", [])
            if ambiguidades:
                f.write(f"### ⚠️ Ambiguidades ({len(ambiguidades)})\n\n")
                for amb in ambiguidades:
                    amb = _as_dict(amb, kind="ambiguidade")
                    f.write(f"- {amb.get('localizacao', 'N/A')}: {amb.get('problema') or amb.get('descricao') or ''}\n")
                f.write("\n")

            obs_fontes = fontes.get("observacoes") or fontes.get("erro")
            if obs_fontes:
                f.write(f"**Observações:** {obs_fontes}\n\n")
        
        # Problemas Estruturais
        estruturais = resultado.get('problemas_estruturais', [])
        if estruturais:
            f.write(f"## ⚠️ PROBLEMAS ESTRUTURAIS ({len(estruturais)})\n\n")
            for prob in estruturais:
                prob = _as_dict(prob, kind="estrutural")
                tipo = prob.get('tipo', 'problema')
                loc = prob.get('localizacao', 'N/A')
                desc = prob.get('descricao') or prob.get("descricao") or prob.get("localizacao") or ""
                f.write(f"- **{tipo}** ({loc}): {desc}\n")
            f.write("\n")
        
        # Problemas de Contexto
        contexto = resultado.get('problemas_contexto', [])
        if contexto:
            f.write(f"## ⚠️ PROBLEMAS DE CONTEXTO ({len(contexto)})\n\n")
            for prob in contexto:
                prob = _as_dict(prob, kind="contexto")
                tipo = prob.get('tipo', 'problema')
                loc = prob.get('localizacao', 'N/A')
                sug = prob.get('sugestao') or prob.get("descricao") or ""
                f.write(f"- **{tipo}** ({loc}): {sug}\n")
            f.write("\n")
        
        # Alucinações
        alucinacoes = resultado.get('alucinacoes', [])
        if alucinacoes:
            f.write(f"## 🔴 POSSÍVEIS ALUCINAÇÕES ({len(alucinacoes)})\n\n")
            for aluc in alucinacoes:
                aluc = _as_dict(aluc, kind="alucinacao")
                trecho = aluc.get('trecho_formatado', '') or aluc.get("descricao", "")
                conf = aluc.get('confianca', 'MÉDIA')
                acao = aluc.get('acao_sugerida', 'verificar')
                f.write(f"- **Confiança {conf}**: {trecho[:150]}...\n")
                f.write(f"  *Ação:* {acao}\n\n")
        
        # Observações
        obs = resultado.get('observacoes_gerais')
        if obs:
            f.write(f"## 💬 Observações Gerais\n\n{obs}\n\n")
        
        # Recomendação HIL
        recom = resultado.get('recomendacao_hil', {})
        if recom:
            f.write("## 🎯 RECOMENDAÇÃO HIL\n\n")
            pausar = recom.get('pausar_para_revisao', False)
            if pausar:
                f.write(f"**⏸️  PAUSAR PARA REVISÃO HUMANA**\n\n")
                f.write(f"**Motivo:** {recom.get('motivo', 'Problemas críticos detectados')}\n\n")
                
                areas = recom.get('areas_criticas', [])
                if areas:
                    f.write("**Áreas Críticas:**\n")
                    for area in areas:
                        f.write(f"- {area}\n")
            else:
                f.write("**✅ Pode prosseguir** (sem problemas críticos)\n")
    
    print(f"📄 Relatório markdown salvo: {output_md}")


if __name__ == "__main__":
    import sys
    import logging
    
    logging.basicConfig(level=logging.INFO)
    
    if len(sys.argv) < 3:
        print("Uso: python audit_fidelity_preventive.py <raw.txt> <formatted.md> [modo]")
        print("  modo: APOSTILA (padrão) ou FIDELIDADE")
        sys.exit(1)
    
    raw_path = sys.argv[1]
    formatted_path = sys.argv[2]
    modo = sys.argv[3].upper() if len(sys.argv) > 3 else "APOSTILA"
    
    # Configuração Gemini
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "gen-lang-client-0727883752")
    client = genai.Client(vertexai=True, project=project_id, location="global")
    
    with open(raw_path, 'r', encoding='utf-8') as f:
        raw = f.read()
    
    with open(formatted_path, 'r', encoding='utf-8') as f:
        formatted = f.read()
    
    doc_name = os.path.basename(formatted_path).replace('.md', '').replace('.txt', '')
    json_output = f"{doc_name}_AUDITORIA_FIDELIDADE.json"
    md_output = f"{doc_name}_AUDITORIA_FIDELIDADE.md"
    
    resultado = auditar_fidelidade_preventiva(
        client, raw, formatted, doc_name, json_output, modo
    )
    
    gerar_relatorio_markdown_completo(resultado, md_output, doc_name)
