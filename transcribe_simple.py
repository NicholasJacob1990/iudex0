#!/usr/bin/env python3
"""
Script para transcrever arquivos de áudio usando MLX Whisper
"""
import mlx_whisper
import sys

def transcribe_audio(audio_path, output_path):
    """Transcreve áudio usando MLX Whisper"""
    print(f"🎤 Transcrevendo: {audio_path}")
    
    # Transcrever
    result = mlx_whisper.transcribe(
        audio_path,
        path_or_hf_repo="mlx-community/whisper-large-v3-turbo",
        verbose=True
    )
    
    # Salvar
    text = result['text']
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(text)
    
    print(f"✅ Salvo em: {output_path}")
    print(f"📊 Caracteres: {len(text)}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Uso: python3 transcribe_simple.py <audio> <output>")
        sys.exit(1)
    
    transcribe_audio(sys.argv[1], sys.argv[2])
