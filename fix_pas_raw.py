import os

RAW_FILE = "/Users/nicholasjacob/Downloads/MediaExtractor/PAS_COMPLETA_RAW.txt"
BACKUP_FILE = RAW_FILE.replace(".txt", "_BACKUP.txt")

with open(RAW_FILE, 'r') as f:
    content = f.read()

# Backup
with open(BACKUP_FILE, 'w') as f:
    f.write(content)

paras = content.split('\n\n')
large_paras = [p for p in paras if len(p) > 1000]

if len(large_paras) >= 3:
    # Keep P0 and P1. Discard P2.
    final_content = large_paras[0] + "\n\n" + large_paras[1]
    
    with open(RAW_FILE, 'w') as f:
        f.write(final_content)
    
    print("✅ Deduplicated PAS RAW. Kept P0, P1. Removed P2 (duplicate).")
else:
    print("⚠️  Skipping PAS fix - distinct structure found.")
