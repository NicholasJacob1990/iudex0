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
    
    prompt = PROMPT_AUDITORIA_FONTES.format(raw=raw_text[:100000], formatted=formatted_text[:100000])
    
    try:
        response = client.models.generate_content(
            model='gemini-3-flash-preview',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,  # Baixa para ser preciso
                max_output_tokens=8000,
                response_mime_type="application/json",  # Força JSON
                thinking_config=types.ThinkingConfig(
                    include_thoughts=False,
                    thinking_level="HIGH"  # Auditoria requer raciocínio profundo
                ),
            )
        )
        
        if response.text:
            import json
            resultado = json.loads(response.text)
            
            # Salvar relatório se path fornecido
            if output_path:
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(resultado, f, ensure_ascii=False, indent=2)
                print(f"✅ Relatório de atribuição salvo: {output_path}")
            
            # Feedback visual
            if resultado.get('aprovado'):
                print(f"✅ Atribuição de fontes: APROVADO (Nota: {resultado.get('nota_consistencia')}/10)")
            else:
                erros = len(resultado.get('erros_criticos', []))
                print(f"⚠️ Atribuição de fontes: REQUER ATENÇÃO (Nota: {resultado.get('nota_consistencia')}/10)")
                print(f"   🔴 {erros} erro(s) crítico(s) de autoria detectado(s)")
            
            return resultado
        
    except Exception as e:
        print(f"❌ Erro na auditoria de fontes: {e}")
        return {
            "aprovado": False,
            "nota_consistencia": 0,
            "erros_criticos": [],
            "erro": str(e)
        }


def gerar_relatorio_markdown(resultado: dict, output_md: str):
    """Gera relatório legível em Markdown para revisão HIL."""
    
    with open(output_md, 'w', encoding='utf-8') as f:
        f.write("# 📚 RELATÓRIO DE AUDITORIA DE FONTES\n\n")
        
        status = "✅ APROVADO" if resultado.get('aprovado') else "⚠️ REQUER REVISÃO"
        nota = resultado.get('nota_consistencia', 0)
        
        f.write(f"**Status:** {status}\n")
        f.write(f"**Nota de Consistência:** {nota}/10\n\n")
        
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
