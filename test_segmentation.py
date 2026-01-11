import re

def segment_by_speaker(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    speaker_pattern = re.compile(r'^SPEAKER \d+$')
    
    segments = []
    current_speaker = None
    current_content = []
    
    for line in lines:
        line = line.strip()
        if speaker_pattern.match(line):
            # New speaker detected
            if current_speaker:
                # Save previous segment
                segments.append({
                    'speaker': current_speaker,
                    'content': "\n".join(current_content)
                })
            
            current_speaker = line
            current_content = []
        else:
            if current_speaker:
                current_content.append(line)
            # If no speaker yet (start of file), ignore or treat as preamble
            
    # Add last segment
    if current_speaker:
        segments.append({
            'speaker': current_speaker,
            'content': "\n".join(current_content)
        })
        
    # Step 1: Merge consecutive blocks of the same speaker
    merged_same_speaker = []
    if segments:
        current_seg = segments[0]
        for next_seg in segments[1:]:
            if next_seg['speaker'] == current_seg['speaker']:
                current_seg['content'] += "\n" + next_seg['content']
            else:
                merged_same_speaker.append(current_seg)
                current_seg = next_seg
        merged_same_speaker.append(current_seg)
        
    # Step 2: Merge small segments (< 1000 chars) into the previous one (Noise filtering)
    filtered_segments = []
    if merged_same_speaker:
        current_seg = merged_same_speaker[0]
        for next_seg in merged_same_speaker[1:]:
            if len(next_seg['content']) < 1000:
                # Append content to current segment
                current_seg['content'] += "\n" + next_seg['content']
            else:
                filtered_segments.append(current_seg)
                current_seg = next_seg
        filtered_segments.append(current_seg)
        
    # Step 3: Merge consecutive blocks of the same speaker AGAIN (after noise removal)
    final_segments = []
    if filtered_segments:
        current_seg = filtered_segments[0]
        for next_seg in filtered_segments[1:]:
            if next_seg['speaker'] == current_seg['speaker']:
                current_seg['content'] += "\n" + next_seg['content']
            else:
                final_segments.append(current_seg)
                current_seg = next_seg
        final_segments.append(current_seg)
        
    return final_segments

def test_segmentation():
    file_path = "/Users/nicholasjacob/Documents/Aplicativos/Iudex/Aulas_PGM_RJ/01_Aula_Inaugural_YouTube_RAW.txt"
    segments = segment_by_speaker(file_path)
    
    print(f"Found {len(segments)} major segments:")
    for i, seg in enumerate(segments):
        print(f"Segment {i+1}: {seg['speaker']} - Length: {len(seg['content'])} chars")
        print(f"Start: {seg['content'][:100]}...")
        print("-" * 50)

if __name__ == "__main__":
    test_segmentation()
