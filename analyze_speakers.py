import re
from collections import Counter

def analyze_speakers(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    speaker_pattern = re.compile(r'^SPEAKER \d+$')
    
    current_speaker = None
    speaker_blocks = []
    current_block_start = 0
    current_block_content_length = 0
    
    for i, line in enumerate(lines):
        line = line.strip()
        if speaker_pattern.match(line):
            if current_speaker:
                speaker_blocks.append({
                    'speaker': current_speaker,
                    'start_line': current_block_start,
                    'end_line': i - 1,
                    'content_length': current_block_content_length
                })
            
            current_speaker = line
            current_block_start = i
            current_block_content_length = 0
        else:
            current_block_content_length += len(line)
            
    # Add last block
    if current_speaker:
        speaker_blocks.append({
            'speaker': current_speaker,
            'start_line': current_block_start,
            'end_line': len(lines) - 1,
            'content_length': current_block_content_length
        })

    print(f"{'SPEAKER':<15} | {'START':<6} | {'END':<6} | {'LENGTH (chars)':<15}")
    print("-" * 50)
    
    # Merge consecutive blocks of the same speaker
    merged_blocks = []
    if speaker_blocks:
        current = speaker_blocks[0]
        for next_block in speaker_blocks[1:]:
            if next_block['speaker'] == current['speaker']:
                current['end_line'] = next_block['end_line']
                current['content_length'] += next_block['content_length']
            else:
                merged_blocks.append(current)
                current = next_block
        merged_blocks.append(current)

    with open("speaker_analysis.txt", "w") as f:
        f.write(f"{'SPEAKER':<15} | {'START':<6} | {'END':<6} | {'LENGTH (chars)':<15}\n")
        f.write("-" * 50 + "\n")
        for block in merged_blocks:
            f.write(f"{block['speaker']:<15} | {block['start_line']:<6} | {block['end_line']:<6} | {block['content_length']:<15}\n")
            
    print("Analysis saved to speaker_analysis.txt")

if __name__ == "__main__":
    analyze_speakers("/Users/nicholasjacob/Documents/Aplicativos/Iudex/Aulas_PGM_RJ/01_Aula_Inaugural_YouTube_RAW.txt")
