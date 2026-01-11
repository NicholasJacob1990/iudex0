#!/usr/bin/env python3
"""
Processamento RÁPIDO - sem validação zero-omission
"""
import os, sys, asyncio
from pathlib import Path
from colorama import Fore, init
init(autoreset=True)

# Importa a classe
from format_only import VomoFormatter

def process_fast(file_path):
    """Processa sem validação rigorosa"""
    video_name = Path(file_path).stem
    folder = os.path.dirname(file_path) or '.'
    
    print(f"{Fore.CYAN}🚀 MODO RÁPIDO (sem validação zero-omission)")
    print(f"{Fore.CYAN}📄 Processando: {video_name}\n")
    
    formatter = VomoFormatter()
    
    with open(file_path, 'r', encoding='utf-8') as f:
        text = f.read()
    
    # Cache check
    cache_file = formatter._get_cache_path(file_path, "FORMATTED")
    cached = formatter._load_cache(cache_file)
    
    if cached:
        print(f"{Fore.GREEN}⚡ Cache encontrado!")
        formatted = cached['formatted_text']
    else:
        print(f"{Fore.YELLOW}🔄 Processando (modo rápido)...")
        # Processa DIRETO sem validação
        formatted = asyncio.run(formatter.process_full_text_async(text))
        
        # Renumeração
        print(f"{Fore.CYAN}🔢 Renumerando...")
        formatted = formatter._renumber_topics(formatted)
        
        # Salva cache
        formatter._save_cache(cache_file, formatted, file_path)
    
    # Salva arquivos
    md_file = os.path.join(folder, f"{video_name}_APOSTILA_COMPLETA.md")
    with open(md_file, 'w', encoding='utf-8') as f:
        f.write(f"# {video_name}\n\n{formatted}")
    
    docx_file = formatter.save_as_word(formatted, f"{video_name}_COMPLETA", folder)
    
    print(f"\n{Fore.GREEN}✅ CONCLUÍDO!")
    print(f"{Fore.GREEN}   MD: {md_file}")
    print(f"{Fore.GREEN}   DOCX: {docx_file}")

if __name__ == "__main__":
    process_fast(sys.argv[1] if len(sys.argv) > 1 else "prev.txt")
