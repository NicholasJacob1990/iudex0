#!/usr/bin/env python3
"""
Batch Processor para Vídeos Sequenciais
Detecta e agrupa vídeos sequenciais da mesma disciplina/aula e processa como uma única transcrição
"""

import os
import re
import asyncio
from pathlib import Path
from collections import defaultdict
from colorama import Fore, init
from mlx_vomo import VomoMLX

init(autoreset=True)


def group_sequential_videos(directory):
    """
    Escaneia um diretório e agrupa vídeos sequenciais por disciplina e aula
    
    Padrão esperado: {Disciplina}_Aula_{N}_Bloco_{M}.mp4
    Ex: Previdenciario_Aula_01_Bloco_01.mp4
    
    Returns:
        dict: {group_key: [lista de paths ordenados]}
    """
    print(f"{Fore.CYAN}📁 Escaneando diretório: {directory}")
    
    # Padrão: captura Disciplina, número da Aula, número do Bloco
    pattern = re.compile(r'^(\d+)_([^_]+(?:_[^_]+)*)_Aula_(\d+)_Bloco_(\d+)\.mp4$', re.IGNORECASE)
    
    groups = defaultdict(list)
    
    for filename in sorted(os.listdir(directory)):
        if not filename.endswith('.mp4'):
            continue
            
        match = pattern.match(filename)
        if match:
            order_num = match.group(1)  # Número da ordem (ex: 02, 03, 04...)
            discipline = match.group(2)  # Nome da disciplina
            aula_num = match.group(3)    # Número da aula
            bloco_num = match.group(4)   # Número do bloco
            
            # Chave de agrupamento: disciplina + número da aula
            group_key = f"{discipline}_Aula_{aula_num}"
            
            file_path = os.path.join(directory, filename)
            groups[group_key].append((int(bloco_num), file_path))
    
    # Ordena cada grupo por número do bloco
    sorted_groups = {}
    for key, videos in groups.items():
        sorted_videos = [path for _, path in sorted(videos, key=lambda x: x[0])]
        sorted_groups[key] = sorted_videos
    
    return sorted_groups


def process_video_group(group_name, video_paths, output_folder):
    """
    Processa um grupo de vídeos sequenciais como uma única transcrição
    """
    print(f"\n{Fore.CYAN}{'='*60}")
    print(f"{Fore.CYAN}🎬 Processando: {group_name}")
    print(f"{Fore.CYAN}   Blocos: {len(video_paths)}")
    for i, path in enumerate(video_paths, 1):
        print(f"{Fore.CYAN}   [{i}] {Path(path).name}")
    print(f"{Fore.CYAN}{'='*60}\n")
    
    try:
        vomo = VomoMLX(model_size="large-v3-turbo")
    except ValueError as e:
        print(e)
        return
    
    optimized_file = None
    
    try:
        # Concatena os áudios de todos os vídeos do grupo
        optimized_file = vomo.optimize_and_concatenate_audios(video_paths)
        
        # Verifica se já existe cache de transcrição
        raw_txt = os.path.join(output_folder, f"{group_name}_RAW.txt")
        if os.path.exists(raw_txt):
            print(f"{Fore.YELLOW}   📂 Cache de transcrição encontrado")
            with open(raw_txt, "r", encoding="utf-8") as f:
                transcription = f.read()
        else:
            transcription = vomo.transcribe(optimized_file)
            with open(raw_txt, "w", encoding="utf-8") as f:
                f.write(transcription)
        
        # =============================================================
        # ETAPA 1: VERSÃO COMPLETA
        # =============================================================
        print(f"\n{Fore.BLUE}{'='*60}")
        print(f"{Fore.BLUE}ETAPA 1: VERSÃO COMPLETA")
        print(f"{Fore.BLUE}{'='*60}")
        
        # Executa formatação assíncrona (já inclui validação)
        formatted_text = asyncio.run(vomo.format_transcription(transcription, group_name, output_folder))
        
        # Salva MD Completo
        output_md = os.path.join(output_folder, f"{group_name}_APOSTILA_COMPLETA.md")
        with open(output_md, 'w', encoding='utf-8') as f:
            f.write(f"# {group_name}\n\n{formatted_text}")
        print(f"{Fore.GREEN}📝 MD Completo salvo: {output_md}")
        
        # Salva Word Completo
        docx_completo = vomo.save_as_word(formatted_text, f"{group_name}_COMPLETA", output_folder)
        print(f"{Fore.GREEN}📄 Word Completo salvo: {docx_completo}")
        
        # =============================================================
        # ETAPA 2: VERSÃO RESUMIDA
        # =============================================================
        print(f"\n{Fore.BLUE}{'='*60}")
        print(f"{Fore.BLUE}ETAPA 2: VERSÃO RESUMIDA")
        print(f"{Fore.BLUE}{'='*60}")
        
        summary_text = vomo.generate_summary_version(formatted_text)
        
        # Salva MD Resumido
        output_md_summary = os.path.join(output_folder, f"{group_name}_RESUMO.md")
        with open(output_md_summary, 'w', encoding='utf-8') as f:
            f.write(summary_text)
        print(f"{Fore.GREEN}📝 MD Resumo salvo: {output_md_summary}")
        
        # Salva Word Resumido
        docx_resumo = vomo.save_as_word(summary_text, f"{group_name}_RESUMO", output_folder)
        print(f"{Fore.GREEN}📄 Word Resumo salvo: {docx_resumo}")
        
        # =============================================================
        # SUCESSO FINAL
        # =============================================================
        print(f"\n{Fore.GREEN}{'='*60}")
        print(f"{Fore.GREEN}✨ SUCESSO! Apostila Completa + Resumo gerados.")
        print(f"{Fore.GREEN}📄 Completa: {docx_completo}")
        print(f"{Fore.GREEN}📄 Resumo: {docx_resumo}")
        print(f"{Fore.GREEN}{'='*60}")
        
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}⚠️  Interrompido pelo usuário")
        
    except Exception as e:
        print(f"{Fore.RED}❌ Erro: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        if optimized_file and optimized_file.startswith("temp_") and os.path.exists(optimized_file):
            try:
                os.remove(optimized_file)
            except:
                pass


def main():
    """
    Função principal - processa todos os grupos de vídeos sequenciais em um diretório
    """
    import sys
    
    if len(sys.argv) < 2:
        print(f"{Fore.RED}Uso: python batch_processor.py <diretório_com_vídeos>")
        print(f"{Fore.YELLOW}Exemplo: python batch_processor.py ./Reta_Final_PGM/Direito\\ Administrativo")
        sys.exit(1)
    
    input_dir = sys.argv[1]
    
    if not os.path.isdir(input_dir):
        print(f"{Fore.RED}❌ Diretório não encontrado: {input_dir}")
        sys.exit(1)
    
    # Agrupa vídeos sequenciais
    groups = group_sequential_videos(input_dir)
    
    if not groups:
        print(f"{Fore.YELLOW}⚠️  Nenhum vídeo sequencial encontrado no padrão esperado")
        print(f"{Fore.YELLOW}   Padrão: {{Num}}_{{Disciplina}}_Aula_{{N}}_Bloco_{{M}}.mp4")
        sys.exit(0)
    
    print(f"\n{Fore.GREEN}✅ Encontrados {len(groups)} grupos de vídeos sequenciais:")
    for group_name, videos in groups.items():
        print(f"   {Fore.CYAN}• {group_name}: {len(videos)} blocos")
    
    print(f"\n{Fore.YELLOW}{'='*60}")
    print(f"{Fore.YELLOW}Iniciando processamento em lote...")
    print(f"{Fore.YELLOW}{'='*60}\n")
    
    # Processa cada grupo
    for group_name, video_paths in groups.items():
        process_video_group(group_name, video_paths, input_dir)


if __name__ == "__main__":
    main()
