import os
import re
import hashlib

FILE = "/Users/nicholasjacob/Downloads/MediaExtractor/PTR_COMPLETA_RAW_APOSTILA.md"

def normalize(text):
    return re.sub(r'\s+', ' ', text.lower().strip())

with open(FILE, 'r') as f:
    content = f.read()

# Check headers
headers = re.findall(r'^## .*', content, re.MULTILINE)
print(f"Total Headers: {len(headers)}")
for h in headers[:10]:
    print(h)

# Check paragraphs
paras = content.split('\n\n')
hashes = []
dupes = 0
for p in paras:
    if len(p) < 50: continue
    h = hashlib.md5(normalize(p).encode()).hexdigest()[:6]
    if h in hashes:
        dupes += 1
    hashes.append(h)

print(f"\nTotal Paras (>50 chars): {len(paras)}")
print(f"Duplicates found: {dupes}")
