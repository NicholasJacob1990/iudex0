#!/usr/bin/env python3
"""Formata diretamente a transcrição da Aula 01 que já foi inserida"""
import os
from openai import OpenAI
from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from tqdm import tqdm

# Ler transcrição
raw_file = "/Users/nicholasjacob/Documents/Aplicativos/Iudex/Aulas_PGM_RJ/01_Aula_Inaugural_YouTube_RAW.txt"
with open(raw_file, 'r', encoding='utf-8') as f:
    transcript_text = f.read()

print(f"📝 Transcrição carregada: {len(transcript_text)} caracteres")

# Inicializar cliente OpenAI (usa CHROMA_OPENAI_API_KEY do ambiente)
api_key = os.getenv("CHROMA_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("API key não encontrada! Configure OPENAI_API_KEY ou CHROMA_OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

# Dividir em chunks (copiei a lógica do mlx_vomo.py)
def smart_chunk(text, max_size):
    if len(text) <= max_size:
        return [text]
    
    chunks = []
    current_pos = 0
    
    while current_pos < len(text):
        if current_pos + max_size >= len(text):
            chunks.append(text[current_pos:])
            break
            
        chunk_end = current_pos + max_size
        
        for separator in ['\n\n', '\n', '. ', ' ']:
            last_sep = text.rfind(separator, current_pos, chunk_end)
            if last_sep != -1:
                chunk_end = last_sep + len(separator)
                break
        
        chunks.append(text[current_pos:chunk_end])
        current_pos = chunk_end
    
    return chunks

chunks = smart_chunk(transcript_text, 40000)
print(f"   Dividido em {len(chunks)} partes")

# System prompt (copiado do mlx_vomo.py)
system_prompt = """# PAPEL
Você é um especialista em Direito Administrativo e redação jurídica, atuando como revisor sênior de material didático para concursos de Procuradoria Municipal/Estadual (PGM/PGE).

# MISSÃO
Transformar a transcrição bruta de uma videoaula em uma **Apostila de Estudo** clara, didática e fiel ao conteúdo original, mantendo TODO o conhecimento técnico-jurídico.

# ESTRUTURA OBRIGATÓRIA DO DOCUMENTO

## Cabeçalho da Apostila (APENAS NO PRIMEIRO CHUNK)

[INSTRUÇÕES COMPLETAS DE FORMATAÇÃO - ver mlx_vomo.py linha 111-477]

# REGRA DE OURO: Se o professor falou, você DEVE incluir. NUNCA omita nada."""

formatted_chunks = []

print("🧠 Formatando com GPT-5-mini...")
for i, chunk in enumerate(tqdm(chunks, desc="Formatando")):
    is_first = (i == 0)
    
    user_content = f"""{"[PRIMEIRA PARTE - CRIE O CABEÇALHO COMPLETO: Summary, Key Takeaways, Action Items]" if is_first else "[CONTINUAÇÃO - SEM CABEÇALHO]"}

{chunk}"""
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        timeout=180
    )
    
    formatted_chunks.append(response.choices[0].message.content)

formatted_text = "\n\n".join(formatted_chunks)

# Salvar .md
md_file = "/Users/nicholasjacob/Documents/Aplicativos/Iudex/Aulas_PGM_RJ/01_Aula_Inaugural_YouTube_APOSTILA.md"
with open(md_file, 'w', encoding='utf-8') as f:
    f.write(f"# 01_Aula_Inaugural_YouTube\n\n{formatted_text}")

print(f"\n✅ Apostila formatada salva em: {md_file}")
print(f"📊 Tamanho: {len(formatted_text)} caracteres")
