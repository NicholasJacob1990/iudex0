#!/usr/bin/env python3
"""Script temporário para formatar apenas a Aula 01"""
import os
import sys
from openai import OpenAI
from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH

# Adiciona o diretório ao path para importar o mlx_vomo
sys.path.insert(0, '/Users/nicholasjacob/Documents/Aplicativos/Iudex')

def format_and_save():
    """Formata o conteúdo bruto da Aula 01"""
    
    # Ler transcrição bruta
    raw_file = "/Users/nicholasjacob/Documents/Aplicativos/Iudex/Aulas_PGM_RJ/01_Aula_Inaugural_YouTube_APOSTILA.md"
    with open(raw_file, 'r', encoding='utf-8') as f:
        raw_text = f.read()
    
    print(f"📝 Transcrição carregada: {len(raw_text)} caracteres")
    
    # Importar classe do mlx_vomo
    from mlx_vomo import VomoTranscriber
    
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    vomo = VomoTranscriber(client)
    
    # Formatar com GPT-5-mini
    print("🧠 Formatando com GPT-5-mini...")
    formatted_text = vomo.format_transcription(raw_text, "01_Aula_Inaugural_YouTube", "/Users/nicholasjacob/Documents/Aplicativos/Iudex/Aulas_PGM_RJ")
    
    print("✅ Formatação concluída!")
    
    # Salvar .md formatado
    md_file = "/Users/nicholasjacob/Documents/Aplicativos/Iudex/Aulas_PGM_RJ/01_Aula_Inaugural_YouTube_APOSTILA_FORMATTED.md"
    with open(md_file, 'w', encoding='utf-8') as f:
        f.write(f"# 01_Aula_Inaugural_YouTube\n\n{formatted_text}")
    
    print(f"📄 Salvo: {md_file}")
    
    # Gerar Word
    docx_file = vomo.save_as_word(formatted_text, "01_Aula_Inaugural_YouTube", "/Users/nicholasjacob/Documents/Aplicativos/Iudex/Aulas_PGM_RJ")
    print(f"📄 Word gerado: {docx_file}")

if __name__ == "__main__":
    format_and_save()
