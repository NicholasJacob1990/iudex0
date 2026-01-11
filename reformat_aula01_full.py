#!/usr/bin/env python3
"""Reformat Aula 01 using the exact logic from mlx_vomo.py"""
import os
import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, os.getcwd())

from mlx_vomo import VomoMLX

def reformat():
    # Initialize VomoMLX (will use CHROMA_OPENAI_API_KEY from env)
    vomo = VomoMLX()
    
    # Paths
    raw_file = "/Users/nicholasjacob/Documents/Aplicativos/Iudex/Aulas_PGM_RJ/01_Aula_Inaugural_YouTube_RAW.txt"
    output_folder = "/Users/nicholasjacob/Documents/Aplicativos/Iudex/Aulas_PGM_RJ"
    video_name = "01_Aula_Inaugural_YouTube"
    
    # Read raw text
    print(f"📖 Reading raw transcription from: {raw_file}")
    with open(raw_file, 'r', encoding='utf-8') as f:
        transcript_text = f.read()
    
    print(f"📊 Raw text size: {len(transcript_text)} characters")
    
    # Format using the original method
    print("🧠 Formatting with VomoMLX.format_transcription (Original Logic)...")
    formatted_text = vomo.format_transcription(transcript_text, video_name, output_folder)
    
    # Save .md file
    md_file = os.path.join(output_folder, f"{video_name}_APOSTILA.md")
    print(f"💾 Saving Markdown to: {md_file}")
    with open(md_file, 'w', encoding='utf-8') as f:
        f.write(f"# {video_name}\n\n{formatted_text}")

    # Save Word doc using the original method
    print("📄 Generating Word document...")
    vomo.save_as_word(formatted_text, video_name, output_folder)
    
    print("✅ Done!")

if __name__ == "__main__":
    reformat()
