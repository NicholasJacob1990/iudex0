#!/usr/bin/env python3
"""
Script simplificado: apenas transcreve áudios gerando RAW.txt
Sem formatação individual, apenas transcrição pura.
"""

import os
import sys
from pathlib import Path

# Importa apenas a parte de transcrição do mlx_vomo
sys.path.insert(0, '/Users/nicholasjacob/Documents/Aplicativos/Iudex')

try:
    import mlx_whisper
    MLX_AVAILABLE = True
except ImportError:
    MLX_AVAILABLE = False
    print("⚠️ mlx_whisper não disponível")

def transcrever_audio(audio_path):
    """Transcreve áudio usando MLX Whisper e retorna o texto"""
    if not MLX_AVAILABLE:
        print(f"❌ Não é possível transcrever: {audio_path}")
        return None
    
    print(f"🎙️  Transcrevendo: {Path(audio_path).name}")
    
    try:
        result = mlx_whisper.transcribe(
            audio_path,
            path_or_hf_repo="mlx-community/whisper-large-v3-turbo",
            verbose=False
        )
        
        texto = result.get('text', '')
        print(f"   ✅ Transcrição completa: {len(texto)} caracteres")
        return texto
        
    except Exception as e:
        print(f"   ❌ Erro na transcrição: {e}")
        return None

def main():
    # Lista de arquivos em ordem
    arquivos = [
        "/Users/nicholasjacob/Downloads/MediaExtractor/Administrativo Disponível - Direito Adm. Bloco 1 - Parte 1(15 minutos).mp3",
        "/Users/nicholasjacob/Downloads/MediaExtractor/Administrativo Disponível - Direito Adm. Bloco 1 - Parte 2(14 minutos.mp3",
        "/Users/nicholasjacob/Downloads/MediaExtractor/Administrativo Disponível - Direito Adm. Bloco 2 - Parte 1(15 minutos).mp3",
        "/Users/nicholasjacob/Downloads/MediaExtractor/Administrativo Disponível - Direito Adm. Bloco 2 - Parte 2(14 minutos.mp3",
        "/Users/nicholasjacob/Downloads/MediaExtractor/Administrativo Disponível - Direito Adm. Bloco 3 - Parte 1(5 minutos)a.mp3",
        "/Users/nicholasjacob/Downloads/MediaExtractor/Administrativo Disponível - Direito Adm. Bloco 3 - Parte 2(5 minutos)a.mp3",
        "/Users/nicholasjacob/Downloads/MediaExtractor/Administrativo Disponível - Direito Adm. Bloco 3 - Parte 3(5 minutos)a.mp3",
        "/Users/nicholasjacob/Downloads/MediaExtractor/Administrativo Disponível - Direito Adm. Bloco 3 - Parte 4(5 minutos)a.mp3",
        "/Users/nicholasjacob/Downloads/MediaExtractor/Administrativo Disponível - Direito Adm. Bloco 3 - Parte 5(5 minutos)a.mp3",
        "/Users/nicholasjacob/Downloads/MediaExtractor/Administrativo Disponível - Direito Adm. Bloco 3 - Parte 6(4 minutos e.mp3",
        "/Users/nicholasjacob/Downloads/MediaExtractor/Administrativo Disponível - Direito Adm. Bloco 4 - Parte 1(10 minutos).mp3",
        "/Users/nicholasjacob/Downloads/MediaExtractor/Administrativo Disponível - Direito Adm. Bloco 4 - Parte 2(10 minutos).mp3",
        "/Users/nicholasjacob/Downloads/MediaExtractor/Administrativo Disponível - Direito Adm. Bloco 4 - Parte 3(9 minutos e.mp3",
    ]
    
    arquivos_raw = []
    
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("🎙️  TRANSCRIÇÃO SIMPLES - SEM FORMATAÇÃO")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()
    
    # Transcreve cada arquivo
    for i, audio_path in enumerate(arquivos, 1):
        raw_path = audio_path.replace('.mp3', '_RAW.txt')
        
        print(f"📝 Arquivo {i}/{len(arquivos)}")
        
        # Verifica se já existe
        if os.path.exists(raw_path):
            print(f"   ✅ RAW já existe: {Path(raw_path).name}")
            arquivos_raw.append(raw_path)
            continue
        
        # Verifica se o áudio existe
        if not os.path.exists(audio_path):
            print(f"   ❌ Áudio não encontrado: {audio_path}")
            continue
        
        # Transcreve
        texto = transcrever_audio(audio_path)
        
        if texto:
            # Salva RAW
            with open(raw_path, 'w', encoding='utf-8') as f:
                f.write(texto)
            print(f"   💾 RAW salvo: {Path(raw_path).name}")
            arquivos_raw.append(raw_path)
        
        print()
    
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"✅ Transcrições concluídas: {len(arquivos_raw)}/{len(arquivos)}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()
    
    # Consolida os RAW
    output_dir = "/Users/nicholasjacob/Downloads/MediaExtractor/Processados"
    os.makedirs(output_dir, exist_ok=True)
    
    consolidado_path = os.path.join(output_dir, "Direito_Administrativo_CONSOLIDADO_RAW.txt")
    
    print("📚 Consolidando transcrições...")
    
    with open(consolidado_path, 'w', encoding='utf-8') as out:
        for i, raw_path in enumerate(arquivos_raw, 1):
            if not os.path.exists(raw_path):
                continue
                
            out.write(f"\n{'━' * 80}\n")
            out.write(f"BLOCO {i}\n")
            out.write(f"{'━' * 80}\n\n")
            
            with open(raw_path, 'r', encoding='utf-8') as f:
                out.write(f.read())
            
            out.write("\n\n")
    
    print(f"✅ Consolidado criado: {consolidado_path}")
    print()
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("🎨 Agora execute a formatação final:")
    print(f"   python mlx_vomo.py '{consolidado_path}' --mode=FIDELIDADE")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

if __name__ == "__main__":
    main()
