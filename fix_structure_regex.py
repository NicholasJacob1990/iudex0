import re
import sys

def fix_structure(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    lines = content.split('\n')
    new_lines = []
    
    current_area = "Geral"
    seen_questions = set() # (Area, Questão Num)
    
    # Regex padrões
    re_area = re.compile(r'^#\s+\d+\.\s+(.+)', re.IGNORECASE)
    re_questao = re.compile(r'Questão\s+(\d+)', re.IGNORECASE)
    re_header = re.compile(r'^(#{2,4})\s+(.+)')
    
    # Buffer para guardar o conteúdo da seção atual
    buffer_content = []
    ignoring_section = False
    
    print("🔧 Iniciando reestruturação regex...")
    
    cleaned_lines = []
    
    # Passada 1: Identificar Áreas e Questões
    for line in lines:
        # Detecta Área (H1)
        match_area = re_area.match(line)
        if match_area:
            current_area = match_area.group(1).strip()
            # Reset seen questions se mudar de área macro (opcional, mas bom pra evitar mistura)
            # Mas cuidado: as vezes a area muda mas volta. 
            # Melhor chave composta: (Area, Questao)
            cleaned_lines.append(line)
            continue
            
        # Detecta Header (H2, H3...)
        match_header = re_header.match(line)
        if match_header:
            nivel = match_header.group(1)
            titulo = match_header.group(2).strip()
            
            # Verifica se é questão
            match_q = re_questao.search(titulo)
            if match_q:
                num_q = match_q.group(1)
                key = (current_area, num_q)
                
                # Deduplicação
                if key in seen_questions:
                    print(f"   🗑️  Removendo duplicata: {titulo} (Em {current_area})")
                    ignoring_section = True 
                    continue
                else:
                    seen_questions.add(key)
                    ignoring_section = False
                    # Normalizar título (opcional)
                    cleaned_lines.append(line)
            else:
                # Header normal (não questão)
                if ignoring_section and nivel == '##': 
                    # Se era uma seção ignorada (duplicata de H2), e agora veio outro H2, paramos de ignorar
                    ignoring_section = False
                    cleaned_lines.append(line)
                elif not ignoring_section:
                    cleaned_lines.append(line)
        else:
            # Conteúdo normal
            if not ignoring_section:
                cleaned_lines.append(line)

    # Passada 2: Limpar numeração quebrada e metadados
    final_lines = []
    toc_counter = 0
    
    for line in cleaned_lines:
        # Remove metadata
        if "[TIPO:" in line: continue
        
        # Remove numeração duplicada no início (ex: "1. 1. Título")
        line = re.sub(r'^(#{1,4})\s+\d+(\.\d+)*\.?\s*', r'\1 ', line)
        
        final_lines.append(line)
        
    output_content = '\n'.join(final_lines)
    
    output_path = file_path.replace('.md', '_FIXED.md')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(output_content)
        
    print(f"✅ Arquivo corrigido salvo em: {output_path}")

if __name__ == "__main__":
    fix_structure("aula_audio_RAW_APOSTILA.md")
