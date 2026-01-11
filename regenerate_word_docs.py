import os
import sys
import glob
from pathlib import Path
from mlx_vomo import VomoMLX

# Base directory
MEDIA_DIR = "/Users/nicholasjacob/Downloads/MediaExtractor"

# Find all Apostila Markdown files
md_files = glob.glob(os.path.join(MEDIA_DIR, "*_APOSTILA.md"))

print(f"Found {len(md_files)} markdown apostilas to convert.")

vomo = VomoMLX()

for md_file in md_files:
    print(f"Converting: {os.path.basename(md_file)}...")
    try:
        with open(md_file, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Get video name from filename (remove _APOSTILA.md)
        video_name = Path(md_file).stem.replace('_APOSTILA', '')
        output_folder = os.path.dirname(md_file)
        
        vomo.save_as_word(content, video_name, output_folder)
        print("Done.")
    except Exception as e:
        print(f"Error converting {md_file}: {e}")

print("Batch conversion complete.")
