#!/usr/bin/env python3
"""
Script para separar apenas o conteúdo de Processo Civil de transcrições que misturam disciplinas.
Usa LLM para identificar e extrair apenas os trechos relevantes.
"""
import os
from openai import AsyncOpenAI
import asyncio

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = """Você é um especialista em identificar conteúdo de Processo Civil em transcrições de aulas.

Sua tarefa é:
1. Ler a transcrição fornecida
2. Identificar APENAS os trechos que tratam de Processo Civil
3. Ignorar completamente trechos de outras disciplinas (Processo do Trabalho, Administrativo, etc.)
4. Retornar APENAS o texto de Processo Civil, preservando exatamente como estava

REGRAS CRÍTICAS:
- NÃO resuma, NÃO parafraseie
- Preserve o texto original EXATAMENTE como está
- Se houver dúvida se um trecho é Processo Civil, INCLUA
- Mantenha sequência cronológica
- Sinalize transições: "[[INÍCIO PROCESSO CIVIL]]" e "[[FIM PROCESSO CIVIL]]"
"""

async def extract_processo_civil(text: str, chunk_size: int = 8000) -> str:
    """Extrai apenas conteúdo de Processo Civil"""
    
    # Dividir em chunks se necessário
    if len(text) <= chunk_size:
        chunks = [text]
    else:
        chunks = []
        for i in range(0, len(text), chunk_size - 500):  # overlap de 500 chars
            chunks.append(text[i:i + chunk_size])
    
    print(f"📚 Processando {len(chunks)} chunks...")
    
    extracted_parts = []
    
    for idx, chunk in enumerate(chunks, 1):
        print(f"   Processando chunk {idx}/{len(chunks)}...")
        
        response = await client.chat.completions.create(
            model="gpt-5-mini-2025-08-07",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Extraia APENAS o conteúdo de Processo Civil deste trecho:\n\n{chunk}"}
            ]
        )
        
        extracted = response.choices[0].message.content
        extracted_parts.append(extracted)
    
    # Juntar partes
    full_text = "\n\n".join(extracted_parts)
    
    # Limpar marcadores duplicados
    full_text = full_text.replace("[[FIM PROCESSO CIVIL]]\n\n[[INÍCIO PROCESSO CIVIL]]", "\n\n")
    
    return full_text

async def main():
    import sys
    
    if len(sys.argv) != 3:
        print("Uso: python3 extract_processo_civil.py <input.txt> <output.txt>")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    
    print(f"🔍 Lendo {input_file}...")
    with open(input_file, 'r', encoding='utf-8') as f:
        text = f.read()
    
    print(f"📊 Tamanho original: {len(text)} caracteres")
    
    print("🎯 Extraindo apenas conteúdo de Processo Civil...")
    extracted = await extract_processo_civil(text)
    
    print(f"📊 Tamanho extraído: {len(extracted)} caracteres ({100*len(extracted)/len(text):.1f}%)")
    
    print(f"💾 Salvando em {output_file}...")
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(extracted)
    
    print("✅ Concluído!")

if __name__ == "__main__":
    asyncio.run(main())
