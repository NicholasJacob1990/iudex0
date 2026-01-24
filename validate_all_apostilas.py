import os
import sys
import glob
from pathlib import Path
from mlx_vomo import VomoMLX
import json

# Setup
MEDIA_DIR = "/Users/nicholasjacob/Downloads/MediaExtractor"
OUTPUT_REPORT = os.path.join(MEDIA_DIR, "CONSOLIDATED_VALIDATION_REPORT.md")

print(f"Starting validation in {MEDIA_DIR}...")

# Initialize Vomo
vomo = VomoMLX()

# Findings
results = []

# Find pairs
raw_files = glob.glob(os.path.join(MEDIA_DIR, "*_COMPLETA_RAW.txt"))

for raw_file in raw_files:
    # Expected apostila file
    stem = Path(raw_file).stem # e.g. PUMA_COMPLETA_RAW
    apostila_file = os.path.join(MEDIA_DIR, f"{stem}_APOSTILA.md")
    
    if not os.path.exists(apostila_file):
        print(f"Skipping {stem}: Apostila not found.")
        continue
        
    print(f"\nValidating {stem}...")
    
    try:
        # Read contents
        with open(raw_file, 'r', encoding='utf-8') as f:
            raw_text = f.read()
        
        with open(apostila_file, 'r', encoding='utf-8') as f:
            formatted_text = f.read()
            
        # Run validation
        # validate_completeness_full(self, raw_transcript, formatted_text, video_name, global_structure=None)
        validation_result = vomo.validate_fidelity_primary(
            raw_text,
            formatted_text,
            stem,
            modo="APOSTILA",
            include_sources=False,
        )
        
        # Parse result (it's likely a JSON string or dict, depending on implementation)
        # Based on logs: "✅ Validação Full-Context APROVADA (Nota: 10/10)"
        # and it returns validation_result object.
        
        # Let's inspect the result structure
        score = validation_result.get('nota', 0)
        feedback = validation_result.get('observacoes', 'No feedback provided.')
        omissions = validation_result.get('omissoes', [])
        
        print(f"  Score: {score}/10")
        
        results.append({
            'subject': stem.replace('_COMPLETA_RAW', ''),
            'score': score,
            'feedback': feedback,
            'omissions': omissions
        })
        
    except Exception as e:
        print(f"Error validating {stem}: {e}")
        results.append({
            'subject': stem.replace('_COMPLETA_RAW', ''),
            'score': 0,
            'feedback': f"VALIDATION ERROR: {str(e)}",
            'omissions': []
        })

# Generate Report
print(f"\nGenerating Report at {OUTPUT_REPORT}...")

with open(OUTPUT_REPORT, 'w', encoding='utf-8') as f:
    f.write("# Relatório de Validação de Apostilas\n\n")
    f.write(f"**Data:** {os.popen('date').read().strip()}\n")
    f.write(f"**Total Analisado:** {len(results)}\n\n")
    
    f.write("## Resumo Geral\n")
    f.write("| Disciplina | Nota de Fidelidade | Status |\n")
    f.write("| :--- | :---: | :--- |\n")
    
    for res in results:
        status = "✅ Aprovado" if res['score'] >= 8 else "⚠️ Revisar"
        if res['score'] < 6:
            status = "❌ Crítico"
        f.write(f"| {res['subject']} | {res['score']}/10 | {status} |\n")
        
    f.write("\n## Detalhes por Disciplina\n")
    
    for res in results:
        f.write(f"\n### {res['subject']}\n")
        f.write(f"**Nota:** {res['score']}/10\n\n")
        f.write(f"**Feedback:**\n{res['feedback']}\n\n")
        
        if res['omissions']:
            f.write("**Omissões Detectadas:**\n")
            for om in res['omissions']:
                f.write(f"- {om}\n")
        else:
            f.write("*Nenhuma omissão crítica detectada.*\n")
            
print("Validation Complete!")
