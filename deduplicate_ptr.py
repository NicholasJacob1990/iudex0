import os

RAW_FILE = "/Users/nicholasjacob/Downloads/MediaExtractor/PTR_COMPLETA_RAW.txt"
BACKUP_FILE = RAW_FILE.replace(".txt", "_BACKUP.txt")

# Read content
with open(RAW_FILE, 'r') as f:
    content = f.read()

# Backup
with open(BACKUP_FILE, 'w') as f:
    f.write(content)

paras = content.split('\n\n')
large_paras = [p for p in paras if len(p) > 1000]

print(f"Found {len(large_paras)} large paragraphs.")

if len(large_paras) >= 3:
    # LP0 is Lesson 1
    # LP1 is Lesson 2
    # LP2 is Lesson 1 (Duplicate)
    
    # We want LP0 and LP1.
    final_content = large_paras[0] + "\n\n" + large_paras[1]
    
    with open(RAW_FILE, 'w') as f:
        f.write(final_content)
    
    print(f"✅ Deduplicated PTR RAW. Kept 2 lessons. Removed duplicate Lesson 3.")
else:
    print("⚠️ Something wrong. Did not find 3 large chunks.")
