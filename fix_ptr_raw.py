import os
from difflib import SequenceMatcher

RAW_FILE = "/Users/nicholasjacob/Downloads/MediaExtractor/PTR_COMPLETA_RAW.txt"

with open(RAW_FILE, 'r') as f:
    content = f.read()

paras = content.split('\n\n')
large_paras = [p for p in paras if len(p) > 1000]

print(f"Total Large Paragraphs (>1000 chars): {len(large_paras)}")

for i, p in enumerate(large_paras):
    print(f"Large Para {i}: {len(p)} chars. Starts with: {p[:50]}...")

if len(large_paras) >= 2:
    ratio = SequenceMatcher(None, large_paras[0], large_paras[1]).ratio()
    print(f"Similarity LP0 vs LP1: {ratio:.4f}")
    
    if len(large_paras) >= 3:
        ratio2 = SequenceMatcher(None, large_paras[0], large_paras[2]).ratio()
        print(f"Similarity LP0 vs LP2: {ratio2:.4f}")

# Fix Strategy: Keep only unique large paragraphs + headers?
# If LP0 == LP1 == LP2, we just want LP0.
