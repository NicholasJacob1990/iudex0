import os
import sys
import subprocess
import glob
from pathlib import Path

# Base directory for the scripts
SCRIPT_DIR = "/Users/nicholasjacob/Documents/Aplicativos/Iudex"
os.chdir(SCRIPT_DIR)

# List of files provided by the user
files = [
    '/Users/nicholasjacob/Downloads/MediaExtractor/PUMA - Aula 06.mp4',
    '/Users/nicholasjacob/Downloads/MediaExtractor/PUMA - Aula 04.mp4',
    '/Users/nicholasjacob/Downloads/MediaExtractor/PUMA - Aula 01.mp4',
    '/Users/nicholasjacob/Downloads/MediaExtractor/PTR - Aula 3 - Procuradoria Tributária (Andrea Veloso).mp4',
    '/Users/nicholasjacob/Downloads/MediaExtractor/PTR - Aula 2 - Procuradoria Tributária (Andrea Veloso).mp4',
    '/Users/nicholasjacob/Downloads/MediaExtractor/PTR - Aula 1 - Procuradoria Tributária (Andrea Veloso).mp4',
    '/Users/nicholasjacob/Downloads/MediaExtractor/PSE - Bloco 03.mp4',
    '/Users/nicholasjacob/Downloads/MediaExtractor/PSE - Bloco 02.mp4',
    '/Users/nicholasjacob/Downloads/MediaExtractor/PSE - Bloco 01.mp4',
    '/Users/nicholasjacob/Downloads/MediaExtractor/PPE e PTA - Procuradoria Trabalhista (Giovanna Porchéra).mp4',
    '/Users/nicholasjacob/Downloads/MediaExtractor/PPE e PTA - Procuradoria de Pessoal (Giovanna Porchéra).mp4',
    '/Users/nicholasjacob/Downloads/MediaExtractor/Aula 07 - PDA.mp4',
    '/Users/nicholasjacob/Downloads/MediaExtractor/Aula 06 - PDA.mp4',
    '/Users/nicholasjacob/Downloads/MediaExtractor/Aula 05 - PDA.mp4',
    '/Users/nicholasjacob/Downloads/MediaExtractor/Aula 04 - PDA.mp4',
    '/Users/nicholasjacob/Downloads/MediaExtractor/Aula 03 - PDA.mp4',
    '/Users/nicholasjacob/Downloads/MediaExtractor/Aula 02 - PDA.mp4',
    '/Users/nicholasjacob/Downloads/MediaExtractor/Aula 01 - PDA.mp4',
    '/Users/nicholasjacob/Downloads/MediaExtractor/Aula 02 - PAS.mp4',
    '/Users/nicholasjacob/Downloads/MediaExtractor/Aula 03 - PAS.mp4',
    '/Users/nicholasjacob/Downloads/MediaExtractor/Aula 01 - PAS.mp4',
    '/Users/nicholasjacob/Downloads/MediaExtractor/PADM - Consultivo PGM - Aula 03.mp4',
    '/Users/nicholasjacob/Downloads/MediaExtractor/PADM - Consultivo PGM - Aula 02.mp4',
    '/Users/nicholasjacob/Downloads/MediaExtractor/PADM - Consultivo PGM - Aula 01.mp4'
]

# Define Groups
groups = {
    'PUMA': [],
    'PTR': [],
    'PSE': [],
    'PPE_PTA': [],
    'PDA': [],
    'PAS': [],
    'PADM': []
}

for f in files:
    name = os.path.basename(f)
    if 'PUMA' in name:
        groups['PUMA'].append(f)
    elif 'PTR' in name:
        groups['PTR'].append(f)
    elif 'PSE' in name:
        groups['PSE'].append(f)
    elif 'PPE e PTA' in name:
        groups['PPE_PTA'].append(f)
    elif 'PDA' in name:
        groups['PDA'].append(f)
    elif 'PAS' in name:
        groups['PAS'].append(f)
    elif 'PADM' in name:
        groups['PADM'].append(f)

# Sort files within each group to ensure correct order
for key in groups:
    groups[key].sort()

# Processing Loop
for subject, group_files in groups.items():
    if not group_files:
        continue
    
    print(f"\n{'='*50}")
    print(f"Processing Group: {subject}")
    print(f"{'='*50}")

    transcriptions = []
    
    # 1. Transcribe each file (or get existing RAW)
    for video_path in group_files:
        folder = os.path.dirname(video_path)
        stem = Path(video_path).stem
        raw_path = os.path.join(folder, f"{stem}_RAW.txt")
        
        if not os.path.exists(raw_path):
            print(f"Transcribing: {stem}...")
            # Using --skip-formatting to just get the RAW transcript
            # Using mlx_vomo.py
            cmd = [sys.executable, "mlx_vomo.py", video_path, "--skip-formatting"]
            try:
                subprocess.run(cmd, check=True)
            except subprocess.CalledProcessError as e:
                print(f"Error processing {video_path}: {e}")
                continue
        else:
            print(f"Found existing RAW: {stem}")
        
        # Read content
        if os.path.exists(raw_path):
            with open(raw_path, 'r', encoding='utf-8') as f:
                content = f.read()
                transcriptions.append(f"# {stem}\n\n{content}")
        else:
            print(f"ERROR: Could not find RAW file for {stem}")
    
    # 2. Concatenate
    if not transcriptions:
        print(f"No transcriptions found for {subject}")
        continue
        
    full_text = "\n\n".join(transcriptions)
    # Output file for the consolidated raw text
    output_folder = os.path.dirname(group_files[0])
    concatenated_raw_path = os.path.join(output_folder, f"{subject}_COMPLETA_RAW.txt")
    
    with open(concatenated_raw_path, 'w', encoding='utf-8') as f:
        f.write(full_text)
    
    print(f"Concatenated RAW saved to: {concatenated_raw_path}")
    
    # 3. Format into Apostila
    print(f"Formatting Apostila for {subject}...")
    
    # Using mlx_vomo.py on the text file with mode=APOSTILA
    cmd_format = [sys.executable, "mlx_vomo.py", concatenated_raw_path, "--mode=APOSTILA"]
    try:
        subprocess.run(cmd_format, check=True)
        print(f"Finished {subject}")
    except subprocess.CalledProcessError as e:
        print(f"Error formatting {subject}: {e}")

print("\nBatch Processing Complete!")
