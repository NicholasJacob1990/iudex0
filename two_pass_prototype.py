#!/usr/bin/env python3
"""
Two-Pass Formatting Prototype

Pass 1: Format all content without headers, detect discipline boundaries
Pass 2: Generate complete headers for each discipline based on full content
"""
import os
import sys
import re
from openai import OpenAI
from tqdm import tqdm

# Add current directory to path
sys.path.insert(0, os.getcwd())

def smart_chunk(text, max_size=40000):
    """Divide texto respeitando parágrafos"""
    if len(text) <= max_size:
        return [text]
    
    paragraphs = text.split('\n\n')
    chunks = []
    current = ""
    
    for para in paragraphs:
        if len(current) + len(para) + 2 <= max_size:
            current += para + "\n\n"
        else:
            if current:
                chunks.append(current.strip())
            
            if len(para) > max_size:
                sentences = para.replace('? ', '?|').replace('! ', '!|').replace('. ', '.|').split('|')
                temp = ""
                for sent in sentences:
                    if len(temp) + len(sent) + 1 <= max_size:
                        temp += sent + " "
                    else:
                        if temp:
                            chunks.append(temp.strip())
                        temp = sent + " "
                current = temp
            else:
                current = para + "\n\n"
    
    if current:
        chunks.append(current.strip())
    
    return chunks

def detect_discipline_transition_via_llm(client, chunk_text):
    """Ask LLM if there is a major discipline change in this chunk"""
    prompt = """Analise o texto abaixo e identifique se há uma MUDANÇA DE PROFESSOR ou APRESENTADOR.

    IMPORTANTE: Retorne TRANSITION apenas se houver menção explícita de um NOVO PROFESSOR assumindo a palavra.
    
    Exemplos que devem retornar TRANSITION:
    - "Agora vamos receber a professora Beatriz"
    - "Professor Bruno vai falar agora"
    - "Passando a palavra para o professor X"
    - Apresentação formal de um novo docente
    
    Exemplos que NÃO devem retornar TRANSITION:
    - "Agora vamos falar de Direito Administrativo" (mesmo professor mudando de tópico)
    - "Passando para o próximo tema"
    - Mudanças de assunto dentro da mesma fala
    
    Se houver mudança de PROFESSOR, retorne o nome do professor e sua disciplina:
    [TRANSITION: Prof. [Nome] - [Disciplina]]
    
    Se NÃO houver mudança de professor (apenas mudança de tópico), retorne:
    NO_TRANSITION
    
    Texto para análise:
    """
    
    # Analyze first 15K and last 5K of chunk to catch transitions anywhere
    if len(chunk_text) > 20000:
        analysis_text = chunk_text[:15000] + "\n\n[...]\n\n" + chunk_text[-5000:]
    else:
        analysis_text = chunk_text
    
    prompt = prompt + analysis_text
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Você é um detector de tópicos jurídicos."},
            {"role": "user", "content": prompt}
        ],
        temperature=0
    )
    
    content = response.choices[0].message.content.strip()
    if "[TRANSITION:" in content:
        return content.split(":")[1].strip().replace("]", "")
    return None

def format_chunk_content_only(client, chunk, chunk_idx, system_prompt_base):
    """Format chunk content WITHOUT headers"""
    # ... existing logic ...

    user_content = f"""[CHUNK {chunk_idx + 1}]
    
    INSTRUÇÃO: Formate o conteúdo abaixo mantendo 100% das informações.
    - NÃO faça resumos.
    - NÃO omita exemplos ou histórias.
    - NÃO gere cabeçalhos (Summary/Key Takeaways) - apenas o conteúdo formatado.
    
    TEXTO:
    {chunk}"""
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt_base},
            {"role": "user", "content": user_content}
        ],
        timeout=180
    )
    
    return response.choices[0].message.content

def generate_discipline_header(client, discipline_name, full_discipline_content):
    """Generate complete Summary/Key Takeaways/Action Items for entire discipline"""
    # Truncate if too long (keep first 20K + last 10K)
    if len(full_discipline_content) > 30000:
        content_sample = full_discipline_content[:20000] + "\n\n[...]\n\n" + full_discipline_content[-10000:]
    else:
        content_sample = full_discipline_content
    
    header_prompt = f"""Analise TODO o conteúdo abaixo sobre {discipline_name} e gere APENAS:

## Summary
(Parágrafo único de 5-8 linhas resumindo TODA a disciplina, incluindo todos os tópicos principais abordados)

## Key Takeaways
(Liste 5-10 pontos-chave extraídos de TODO o conteúdo da disciplina)

## Action Items
(Liste 5-10 tarefas de estudo baseadas em TODO o conteúdo da disciplina)

---

CONTEÚDO COMPLETO:
{content_sample}"""
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Você é um especialista em criar resumos executivos de material jurídico para concursos."},
            {"role": "user", "content": header_prompt}
        ],
        timeout=180
    )
    
    return response.choices[0].message.content

def two_pass_format():
    """Main two-pass formatting logic"""
    # Load API key
    api_key = os.getenv("CHROMA_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("API key not found")
    
    client = OpenAI(api_key=api_key)
    
    # Load raw transcription
    raw_file = "/Users/nicholasjacob/Documents/Aplicativos/Iudex/Aulas_PGM_RJ/01_Aula_Inaugural_YouTube_RAW.txt"
    with open(raw_file, 'r', encoding='utf-8') as f:
        transcript_text = f.read()
    
    print(f"📖 Loaded: {len(transcript_text)} chars")
    
    # Chunk
    chunks = smart_chunk(transcript_text, 40000)
    print(f"📦 Chunked into {len(chunks)} parts")
    
    # PASS 1: Format content + detect boundaries
    print("\n🔄 PASS 1: Formatting content and detecting disciplines...")
    formatted_chunks = []
    discipline_boundaries = []  # [(chunk_idx, discipline_name), ...]
    
    system_prompt = """# PAPEL
Você é um especialista em Direito Administrativo e redação jurídica, atuando como revisor sênior de material didático para concursos de Procuradoria Municipal/Estadual (PGM/PGE).

# MISSÃO
Transformar a transcrição bruta de uma videoaula em uma **Apostila de Estudo** clara, didática e fiel ao conteúdo original, mantendo TODO o conhecimento técnico-jurídico.

# DIRETRIZES DE REVISÃO

## 1. PRESERVAÇÃO INTEGRAL DE CONTEÚDO (PRIORIDADE ABSOLUTA)

⚠️ **REGRA DE OURO: Se o professor falou, você DEVE incluir. NUNCA omita nada.**

### O QUE PRESERVAR (100% do conteúdo):

✅ **TODO conteúdo técnico-jurídico:**
- Artigos de lei, súmulas, jurisprudências (com números e anos)
- Autores citados (SEMPRE com nome completo)
- Teorias, correntes doutrinárias, divergências
- Definições técnicas e conceitos (mesmo que pareçam básicos)

✅ **TODOS os exemplos e casos:**
- Exemplos práticos de aplicação
- Casos concretos (reais ou hipotéticos)
- Histórias ilustrativas e anedotas do professor
- Exemplos locais e regionais
- Situações do dia-a-dia mencionadas

✅ **TODO contexto e background:**
- Datas, eventos históricos, marcos temporais
- Evolução legislativa (antes/depois de mudanças)
- Conjuntura política e econômica atual
- Notícias e fatos recentes mencionados

✅ **TODAS as observações do professor:**
- Dicas de prova ("cai muito", "atenção", "pegadinha")
- Macetes e mnemônicos
- Analogias e comparações didáticas
- Críticas a leis, práticas ou instituições
- Opiniões e posicionamentos pessoais
- Especulações e "apostas" sobre tendências futuras
- Sugestões de estudo complementar

✅ **TODAS as nuances argumentativas:**
- Estratégias para responder questões
- Argumentos defensivos quando não souber a resposta
- Diferentes formas de abordar o mesmo tema
- Ressalvas e exceções às regras gerais
- Pontos polêmicos ou controversos

### ❌ NUNCA faça isso:
- ❌ Pensar "isso é óbvio" e omitir
- ❌ Pensar "isso é só uma história" e cortar
- ❌ Pensar "isso é opinião pessoal" e remover
- ❌ Pensar "isso é especulação" e ignorar
- ❌ Pensar "isso é exemplo local" e descartar
- ❌ Resumir exemplos longos em frases genéricas
- ❌ Substituir casos concretos por conceitos abstratos
- ❌ Cortar detalhes para "economizar espaço"

## 2. Limpeza de Linguagem (SEM perder conteúdo)
✅ REMOVA:
- Vícios de preenchimento: "né", "tipo assim", "sabe"
- Repetições acidentais
- Falsos inícios

❌ PRESERVE:
- Repetições intencionais para ênfase
- Todos os exemplos, casos concretos e analogias

## 3. Estrutura e Formatação
- Use hierarquia numerada (## 1., ### 1.1)
- Prefira PROSA CONTÍNUA para explicações
- Use BULLETS apenas para listas curtas
- Mantenha a ordem cronológica da aula
"""
    
    for i, chunk in enumerate(tqdm(chunks, desc="Pass 1")):
        # Detect discipline transition via LLM
        disc = detect_discipline_transition_via_llm(client, chunk)
        if disc:
            discipline_boundaries.append((i, disc))
            print(f"\n   ✅ Detected: {disc} at chunk {i+1}")
        
        # Format content
        formatted = format_chunk_content_only(client, chunk, i, system_prompt)
        formatted_chunks.append(formatted)
    
    # Group by discipline
    print(f"\n📚 Detected {len(discipline_boundaries)} disciplines")
    
    if not discipline_boundaries:
        # No disciplines detected, treat as single discipline
        discipline_boundaries = [(0, "Aula Completa")]
    
    # Add end boundary
    discipline_boundaries.append((len(chunks), "END"))
    
    disciples = []
    for i in range(len(discipline_boundaries) - 1):
        start_idx, disc_name = discipline_boundaries[i]
        end_idx, _ = discipline_boundaries[i + 1]
        
        # Collect all formatted chunks for this discipline
        disc_content = "\n\n".join(formatted_chunks[start_idx:end_idx])
        disciples.append((disc_name, disc_content, start_idx))

    # Merge adjacent same-discipline segments
    merged_disciples = []
    if disciples:
        current_name, current_content, current_start = disciples[0]
        
        for next_name, next_content, next_start in disciples[1:]:
            # Normalize names for comparison (ignore case/accents roughly)
            if next_name.lower().strip() in current_name.lower().strip() or current_name.lower().strip() in next_name.lower().strip():
                # Same discipline, merge content
                current_content += "\n\n" + next_content
            else:
                # Different, push current and start new
                merged_disciples.append((current_name, current_content, current_start))
                current_name, current_content, current_start = next_name, next_content, next_start
        
        merged_disciples.append((current_name, current_content, current_start))
    
    # PASS 2: Generate complete headers
    print("\n🎯 PASS 2: Generating complete discipline headers...")
    final_sections = []
    
    for disc_name, disc_content, start_idx in tqdm(merged_disciples, desc="Pass 2"):
        print(f"\n   📝 Generating header for: {disc_name}")
        header = generate_discipline_header(client, disc_name, disc_content)
        
        final_sections.append(f"# {disc_name}\n\n{header}\n\n---\n\n{disc_content}")
    
    # Combine
    final_output = "\n\n".join(final_sections)
    
    # Save
    output_file = "/Users/nicholasjacob/Documents/Aplicativos/Iudex/Aulas_PGM_RJ/01_Aula_Inaugural_YouTube_APOSTILA_V2.md"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(final_output)
    
    print(f"\n✅ Saved to: {output_file}")
    print(f"📊 Output size: {len(final_output)} chars")
    print(f"📚 Disciplines: {len(disciples)}")

if __name__ == "__main__":
    two_pass_format()
