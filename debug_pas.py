import os
from difflib import SequenceMatcher

# PAS (Processo Administrativo Sancionador presumably, or similar)
RAW_FILE = "/Users/nicholasjacob/Downloads/MediaExtractor/PAS_COMPLETA_RAW.txt"

if not os.path.exists(RAW_FILE):
    print("PAS file not found.")
    exit()

with open(RAW_FILE, 'r') as f:
    content = f.read()

paras = content.split('\n\n')
# Filter generic short lines
large_paras = [p for p in paras if len(p) > 1000]

print(f"Total Large Paragraphs in PAS: {len(large_paras)}")

for i, p in enumerate(large_paras):
    print(f"Para {i}: {len(p)} chars. Start: {p[:50]}...")

if len(large_paras) >= 2:
    ratio = SequenceMatcher(None, large_paras[0], large_paras[1]).ratio()
    print(f"Sim P0 vs P1: {ratio:.4f}")

if len(large_paras) >= 3:
    ratio = SequenceMatcher(None, large_paras[1], large_paras[2]).ratio()
    print(f"Sim P1 vs P2: {ratio:.4f}")
