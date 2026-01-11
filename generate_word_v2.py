#!/usr/bin/env python3
"""
Generate Word document from the V2 markdown file
"""
import sys
import os
sys.path.insert(0, os.getcwd())

from mlx_vomo import VomoMLX

# Initialize VomoMLX
vomo = VomoMLX()

# Read the V2 markdown
md_file = "/Users/nicholasjacob/Documents/Aplicativos/Iudex/Aulas_PGM_RJ/01_Aula_Inaugural_YouTube_APOSTILA_V2.md"
with open(md_file, 'r', encoding='utf-8') as f:
    md_content = f.read()

print(f"📖 Loaded: {len(md_content)} chars from {md_file}")

# Generate Word document
video_name = "01_Aula_Inaugural_YouTube"
output_folder = "/Users/nicholasjacob/Documents/Aplicativos/Iudex/Aulas_PGM_RJ"
output_file = os.path.join(output_folder, f"{video_name}_APOSTILA_V2.docx")
vomo.save_as_word(md_content, video_name, output_folder)

print(f"\n✅ Word document saved to: {output_file}")
