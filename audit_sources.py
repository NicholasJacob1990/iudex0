#!/usr/bin/env python3
"""
audit_sources.py - Source Attribution Auditor (v1.0)

Detecta problemas de atribuição de autoria ANTES da formatação final.
Foco em cursos "focados na banca" onde atribuição correta é crítica.
"""

import os
import re
from google import genai
from google.genai import types

MAX_CHARS_PER_CHUNK = int(os.getenv("SOURCES_AUDIT_MAX_CHARS", "80000"))
CHUNK_OVERLAP_CHARS = int(os.getenv("SOURCES_AUDIT_CHUNK_OVERLAP", "2000"))
GEMINI_HTTP_TIMEOUT_MS = int(os.getenv("IUDEx_GEMINI_TIMEOUT_MS", "600000"))

PROMPT_AUDITORIA_FONTES = """
# AUDITORIA DE ATRIBUIÇÃO DE FONTES (v1.0)

Você é um auditor especializado em **consistência de fontes acadêmicas**.

## CONTEXTO
Este é um curso preparatório focado em "conhecer a banca examinadora".
É CRÍTICO que as opiniões, teses e posicionamentos sejam atribuídos aos autores/examinadores CORRETOS.

## SUA TAREFA
Analise o texto formatado comparando com a transcrição RAW e identifique:

### 1. 🔴 ERROS DE ATRIBUIÇÃO (CRÍTICO)
- Teses atribuídas ao autor/examinador errado
- Citações de artigos atribuídas à pessoa incorreta
- Confusão entre "o professor disse" vs "o autor X afirma"
- Mistura de opiniões de diferentes examinadores

**EXEMPLO DE ERRO:**
```
RAW: "O examinador Felipe Silvestre, em seu artigo, defende que..."
FORMATADO: "O procurador Gustavo da Gama defende que..."
❌ ERRO: Tese de Felipe atribuída a Gustavo
```

### 2. ⚠️ AMBIGUIDADE DE FONTE
- Uso de "o examinador" quando há múltiplos examinadores
- "O autor" sem especificar qual autor
- Pronomes que geram dúvida sobre quem está falando

### 3. 📚 INCONSISTÊNCIA BIBLIOGRÁFICA
- Artigo mencionado no RAW mas autor não citado no formatado
- Nome do examinador mudado (ex: "Felipe" → "Gustavo")
- Casos práticos atribuídos ao examinador errado

## REGRAS DE ANÁLISE
✅ NÃO marque como erro se:
   - A ordem das informações mudou (mas o autor está correto)
   - Houve paráfrase mantendo a autoria correta
   
❌ MARQUE como erro se:
   - A autoria foi TROCADA ou OMITIDA
   - Um caso/exemplo foi atribuído ao autor errado
   - Há confusão entre múltiplos examinadores/autores

## IMPORTANTE (anti-falso-positivo)
- Você está vendo APENAS UM TRECHO do documento (RAW e formatado), não o documento inteiro.
- NÃO conclua que "o RAW não contém X" ou "o professor não mencionou X" se isso apenas não aparece neste trecho.
- Só registre um erro crítico quando houver evidência explícita no RAW deste trecho e evidência explícita no FORMATADO deste trecho.
- Se houver suspeita mas sem evidência completa neste trecho, registre em "ambiguidades" (não como erro crítico).

## FORMATO DE RESPOSTA (JSON)

Retorne APENAS o JSON (sem markdown):

{{
  "aprovado": true/false,
  "nota_consistencia": 0-10,
  "erros_criticos": [
    {{
      "tipo": "troca_autoria",
      "localizacao": "Seção X, parágrafo Y",
      "trecho_formatado": "Gustavo da Gama defende...",
      "trecho_raw": "Felipe Silvestre defende...",
      "gravidade": "ALTA",
      "correcao_sugerida": "Atribuir corretamente a Felipe Silvestre"
    }}
  ],
  "ambiguidades": [
    {{
      "localizacao": "Seção Z",
      "problema": "Uso de 'o examinador' sem especificar qual",
      "sugestao": "Especificar nome completo"
    }}
  ],
  "observacoes": "Comentários gerais sobre consistência de fontes"
}}

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


def _map_formatted_chunk_to_raw(fmt_start: int, fmt_end: int, fmt_len: int, raw_len: int):
    if fmt_len <= 0 or raw_len <= 0:
        return 0, raw_len
    raw_start = int((fmt_start / fmt_len) * raw_len)
    raw_end = int((fmt_end / fmt_len) * raw_len)
    raw_start = max(0, min(raw_start, raw_len))
    raw_end = max(raw_start, min(raw_end, raw_len))
    return raw_start, raw_end


def _safe_json_parse(text: str):
    if not text:
        return None
    raw = text.strip()
    try:
        import json
        return json.loads(raw)
    except Exception:
        pass
    match = re.search(r'```(?:json)?\s*([\s\S]*?)```', raw)
    if match:
        try:
            import json
            return json.loads(match.group(1).strip())
        except Exception:
            pass
    brace_start = raw.find('{')
    brace_end = raw.rfind('}')
    if brace_start != -1 and brace_end > brace_start:
        try:
            import json
            return json.loads(raw[brace_start:brace_end + 1])
        except Exception:
            pass
    return None


def _dedup_dict_items(items: list, keys: list[str], limit: int = 200):
    if not isinstance(items, list):
        return []
    seen = set()
    out = []
    for item in items:
        if not isinstance(item, dict):
            item = {"texto": str(item)}
        sig_parts = []
        for k in keys:
            sig_parts.append(str(item.get(k, "")).strip().lower())
        sig = "|".join(sig_parts)
        if sig in seen:
            continue
        seen.add(sig)
        out.append(item)
        if len(out) >= limit:
            break
    return out


def _extract_ref_candidates(text: str) -> list[str]:
    if not text:
        return []
    candidates: list[str] = []
    patterns = [
        r"\b(?:ADPF|DPF)\s*\d{1,5}\b",
        r"\bRE\s*\d{1,7}\b",
        r"\bADI\s*\d{1,7}\b",
        r"\bTema\s*\d{1,5}\b",
        r"\bS[úu]mula\s*\d{1,5}\b",
        r"\bLei\s*(?:Complementar\s*)?(?:n[º°]?\s*)?\d{1,6}(?:[./]\d{2,4})?\b",
    ]
    for pat in patterns:
        for m in re.finditer(pat, text, flags=re.IGNORECASE):
            candidates.append(m.group(0).strip())
    normalized: list[str] = []
    for c in candidates:
        c2 = re.sub(r"\s+", " ", c).strip()
        if c2 and c2 not in normalized:
            normalized.append(c2)
    return normalized[:12]


def _ref_exists_in_raw(ref: str, raw_text: str) -> bool:
    if not ref or not raw_text:
        return False
    digits = re.sub(r"\D+", "", ref)
    if digits:
        sep = r"[\s\./-]*"
        fuzzy = sep.join(list(digits))
        try:
            if re.search(rf"(?<!\d){fuzzy}(?!\d)", raw_text, flags=re.IGNORECASE):
                return True
        except re.error:
            pass
    try:
        return bool(re.search(re.escape(ref), raw_text, flags=re.IGNORECASE))
    except re.error:
        return False


def auditar_atribuicao_fontes(client, raw_text: str, formatted_text: str, doc_name: str, output_path: str = None):
    """
    Audita consistência de atribuição de fontes/autoria.
    
    Args:
        client: Cliente Gemini
        raw_text: Transcrição bruta original
        formatted_text: Texto formatado/apostila
        doc_name: Nome do documento (para contexto)
        output_path: Caminho para salvar relatório (opcional)
    
    Returns:
        dict: Resultado da auditoria com erros encontrados
    """
    print("🔍 Auditando atribuição de fontes e autoria...")

    raw_len = len(raw_text or "")
    fmt_len = len(formatted_text or "")
    if raw_len == 0 or fmt_len == 0:
        return {
            "aprovado": False,
            "nota_consistencia": 0,
            "erros_criticos": [],
            "ambiguidades": [],
            "erro": "RAW/formatado vazio",
        }

    bounds = _chunk_bounds(fmt_len, MAX_CHARS_PER_CHUNK, CHUNK_OVERLAP_CHARS)
    resultados: list[dict] = []
    parse_failures = 0
    chunk_errors = 0

    try:
        for idx, (f_start, f_end) in enumerate(bounds, 1):
            r_start, r_end = _map_formatted_chunk_to_raw(f_start, f_end, fmt_len, raw_len)
            raw_chunk = raw_text[r_start:r_end]
            fmt_chunk = formatted_text[f_start:f_end]
            chunk_info = (
                f"Trecho {idx} de {len(bounds)} "
                f"(FMT {f_start:,}-{f_end:,}, RAW {r_start:,}-{r_end:,}). "
                f"{'Este é o ÚLTIMO trecho.' if idx == len(bounds) else 'Este NÃO é o final do documento.'}"
            )

            prompt = PROMPT_AUDITORIA_FONTES.format(raw=raw_chunk, formatted=fmt_chunk) + f"\n\n<chunk_info>{chunk_info}</chunk_info>\n"

            response = client.models.generate_content(
                model='gemini-3-flash-preview',
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,  # Baixa para ser preciso
                    max_output_tokens=8000,
                    response_mime_type="application/json",  # Força JSON
                    http_options=types.HttpOptions(timeout=GEMINI_HTTP_TIMEOUT_MS),
                    thinking_config=types.ThinkingConfig(
                        include_thoughts=False,
                        thinking_level="HIGH"
                    ),
                )
            )

            parsed = _safe_json_parse(response.text or "")
            if not isinstance(parsed, dict):
                parse_failures += 1
                parsed = {
                    "aprovado": True,
                    "nota_consistencia": None,
                    "erros_criticos": [],
                    "ambiguidades": [
                        {
                            "localizacao": f"Trecho {idx}/{len(bounds)}",
                            "problema": "Resposta inválida da auditoria de fontes.",
                            "sugestao": "Reexecutar auditoria de fontes para obter nota consolidada.",
                        }
                    ],
                    "erro": "JSON inválido",
                }
            parsed["_chunk_index"] = idx
            if parsed.get("erro"):
                chunk_errors += 1
            resultados.append(parsed)

        # Merge results
        aprovado = True
        nota_soma = 0.0
        nota_peso = 0.0
        erros_criticos: list[dict] = []
        ambiguidades: list[dict] = []
        observacoes: list[str] = []

        for res in resultados:
            aprovado = aprovado and bool(res.get("aprovado", True))
            nota = res.get("nota_consistencia")
            if isinstance(nota, (int, float)):
                nota_soma += float(nota)
                nota_peso += 1.0
            for item in (res.get("erros_criticos") or []):
                if isinstance(item, dict):
                    item.setdefault("_chunk_index", res.get("_chunk_index"))
                erros_criticos.append(item)
            for item in (res.get("ambiguidades") or []):
                if isinstance(item, dict):
                    item.setdefault("_chunk_index", res.get("_chunk_index"))
                ambiguidades.append(item)
            obs = res.get("observacoes")
            if obs:
                observacoes.append(str(obs).strip())

        # Filter common false positive pattern: "RAW não contém ..." when the ref exists somewhere in the full RAW.
        filtered_erros: list[dict] = []
        for erro in erros_criticos:
            if not isinstance(erro, dict):
                continue
            trecho_raw = str(erro.get("trecho_raw") or "")
            trecho_fmt = str(erro.get("trecho_formatado") or "")
            raw_lower = trecho_raw.lower()
            if any(token in raw_lower for token in ("não contém", "nao contém", "não menciona", "nao menciona")):
                refs = _extract_ref_candidates(trecho_fmt)
                if refs and any(_ref_exists_in_raw(ref, raw_text) for ref in refs):
                    ambiguidades.append({
                        "localizacao": erro.get("localizacao") or "—",
                        "problema": "Possível falso positivo: referência aparece no RAW em outro trecho.",
                        "sugestao": "Revisar manualmente ou regerar auditoria de fontes.",
                        "_chunk_index": erro.get("_chunk_index"),
                    })
                    continue
            filtered_erros.append(erro)

        erros_criticos = _dedup_dict_items(filtered_erros, ["tipo", "localizacao", "trecho_formatado", "trecho_raw"])
        ambiguidades = _dedup_dict_items(ambiguidades, ["localizacao", "problema", "sugestao"])

        nota_final = (nota_soma / nota_peso) if nota_peso else None
        score_missing = nota_final is None or (
            isinstance(nota_final, (int, float)) and float(nota_final) <= 0
        )
        inconclusivo = (
            len(erros_criticos) == 0
            and len(ambiguidades) == 0
            and score_missing
        ) or (
            len(erros_criticos) == 0
            and (parse_failures > 0 or chunk_errors > 0)
            and score_missing
        )
        observacoes_str = " / ".join([o for o in observacoes if o])[:1500]
        if inconclusivo and not observacoes_str:
            observacoes_str = (
                "Auditoria de fontes inconclusiva (sem erros críticos detectados, "
                "mas sem sinal suficiente para nota confiável)."
            )
        resultado = {
            "aprovado": (True if inconclusivo else (bool(aprovado) and len(erros_criticos) == 0)),
            "nota_consistencia": (None if inconclusivo else round(float(nota_final or 0.0), 1)),
            "erros_criticos": erros_criticos,
            "ambiguidades": ambiguidades,
            "observacoes": observacoes_str,
            "inconclusivo": inconclusivo,
            "chunks": {
                "total": len(bounds),
                "max_chars": MAX_CHARS_PER_CHUNK,
                "overlap_chars": CHUNK_OVERLAP_CHARS,
            },
        }

        if output_path:
            import json
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(resultado, f, ensure_ascii=False, indent=2)
            print(f"✅ Relatório de atribuição salvo: {output_path}")

        if resultado.get("inconclusivo"):
            print("ℹ️ Atribuição de fontes: INCONCLUSIVA (não bloqueante)")
        elif resultado.get('aprovado'):
            print(f"✅ Atribuição de fontes: APROVADO (Nota: {resultado.get('nota_consistencia')}/10)")
        else:
            erros = len(resultado.get('erros_criticos', []))
            print(f"⚠️ Atribuição de fontes: REQUER ATENÇÃO (Nota: {resultado.get('nota_consistencia')}/10)")
            print(f"   🔴 {erros} erro(s) crítico(s) de autoria detectado(s)")

        return resultado
        
    except Exception as e:
        print(f"❌ Erro na auditoria de fontes: {e}")
        return {
            "aprovado": True,
            "nota_consistencia": None,
            "erros_criticos": [],
            "ambiguidades": [
                {
                    "localizacao": "global",
                    "problema": "Auditoria de fontes indisponível nesta execução.",
                    "sugestao": "Reexecutar quando a API estiver estável.",
                }
            ],
            "observacoes": f"Auditoria de fontes indisponível: {e}",
            "inconclusivo": True,
            "erro": str(e),
        }


def gerar_relatorio_markdown(resultado: dict, output_md: str):
    """Gera relatório legível em Markdown para revisão HIL."""
    
    with open(output_md, 'w', encoding='utf-8') as f:
        f.write("# 📚 RELATÓRIO DE AUDITORIA DE FONTES\n\n")
        
        if resultado.get("inconclusivo"):
            status = "ℹ️ INCONCLUSIVO (NÃO BLOQUEANTE)"
        else:
            status = "✅ APROVADO" if resultado.get("aprovado") else "⚠️ REQUER REVISÃO"
        nota = resultado.get("nota_consistencia")
        nota_display = f"{nota}/10" if isinstance(nota, (int, float)) else "—"
        
        f.write(f"**Status:** {status}\n")
        f.write(f"**Nota de Consistência:** {nota_display}\n\n")
        
        erros = resultado.get('erros_criticos', [])
        if erros:
            f.write(f"## 🔴 ERROS CRÍTICOS DE ATRIBUIÇÃO ({len(erros)})\n\n")
            for i, erro in enumerate(erros, 1):
                f.write(f"### {i}. {erro.get('tipo', 'Erro de Atribuição')}\n\n")
                f.write(f"**Localização:** {erro.get('localizacao')}\n\n")
                f.write(f"**Gravidade:** {erro.get('gravidade')}\n\n")
                
                if erro.get('trecho_raw'):
                    f.write(f"**RAW (Original):**\n```\n{erro['trecho_raw']}\n```\n\n")
                
                if erro.get('trecho_formatado'):
                    f.write(f"**Formatado (Com Erro):**\n```\n{erro['trecho_formatado']}\n```\n\n")
                
                if erro.get('correcao_sugerida'):
                    f.write(f"**Correção Sugerida:** {erro['correcao_sugerida']}\n\n")
                
                f.write("---\n\n")
        
        ambiguidades = resultado.get('ambiguidades', [])
        if ambiguidades:
            f.write(f"## ⚠️ AMBIGUIDADES ({len(ambiguidades)})\n\n")
            for amb in ambiguidades:
                f.write(f"- **{amb.get('localizacao')}**: {amb.get('problema')}\n")
                f.write(f"  *Sugestão:* {amb.get('sugestao')}\n\n")
        
        obs = resultado.get('observacoes')
        if obs:
            f.write(f"## 💬 Observações Gerais\n\n{obs}\n")
    
    print(f"📄 Relatório markdown salvo: {output_md}")


if __name__ == "__main__":
    import sys
    import logging
    
    logging.basicConfig(level=logging.INFO)
    
    if len(sys.argv) < 3:
        print("Uso: python audit_sources.py <raw.txt> <formatted.md>")
        sys.exit(1)
    
    raw_path = sys.argv[1]
    formatted_path = sys.argv[2]
    
    # Configuração básica Gemini
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "gen-lang-client-0727883752")
    client = genai.Client(vertexai=True, project=project_id, location="global")
    
    with open(raw_path, 'r', encoding='utf-8') as f:
        raw = f.read()
    
    with open(formatted_path, 'r', encoding='utf-8') as f:
        formatted = f.read()
    
    doc_name = os.path.basename(formatted_path).replace('.md', '')
    json_output = f"{doc_name}_AUDITORIA_FONTES.json"
    md_output = f"{doc_name}_AUDITORIA_FONTES.md"
    
    resultado = auditar_atribuicao_fontes(client, raw, formatted, doc_name, json_output)
    gerar_relatorio_markdown(resultado, md_output)
