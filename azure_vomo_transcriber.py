import os
import subprocess
import textwrap
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import AzureOpenAI
from tqdm import tqdm
import time

# ================= CONFIGURAÇÕES AZURE OPENAI =================

INPUT_FOLDER = "Aulas_PGM_RJ"

# Azure OpenAI Configuration
AZURE_OPENAI_ENDPOINT = "https://YOUR_RESOURCE_NAME.openai.azure.com/"
AZURE_OPENAI_API_KEY = "YOUR_AZURE_API_KEY"
AZURE_WHISPER_DEPLOYMENT = "whisper"  # Nome do deployment do Whisper no Azure
AZURE_GPT_DEPLOYMENT = "gpt-4o"  # Nome do deployment do GPT-4o no Azure
AZURE_API_VERSION = "2024-02-01"

# Configuração de chunking paralelo (estilo Vomo AI)
CHUNK_DURATION = 300  # 5 minutos por chunk
MAX_WORKERS = 4  # Chunks simultâneos

SYSTEM_PROMPT = """
VOCÊ É UM REVISOR DE TEXTO JURÍDICO DE ELITE.
SUA MISSÃO: Formatar a transcrição bruta abaixo em um texto de estudo (formato apostila).

REGRAS INEGOCIÁVEIS:
1. INTEGRIDADE TOTAL: Não resuma. Não remova explicações. Mantenha 100% do conteúdo técnico.
2. ESTILO: Transforme a fala coloquial em norma culta. Ajuste concordâncias.
3. VISUAL: Use parágrafos claros. Use **Negrito** para termos jurídicos, leis e princípios.
4. CITAÇÕES: Formate referências a leis corretamente (Ex: "Art. 5º, inciso LV da CF/88").
5. FLUIDEZ: Remova vícios de linguagem (né, tipo, ãhn) que sujem o texto, mas mantenha o raciocínio.

Entrada: Transcrição bruta de fala.
Saída: Texto didático, denso e completo.
"""

# ================= FUNÇÕES =================

def extract_audio(video_path):
    """Extrai áudio otimizado para Whisper"""
    audio_path = os.path.splitext(video_path)[0] + ".mp3"
    if os.path.exists(audio_path):
        return audio_path
    
    print(f"⚡ Extraindo áudio de {os.path.basename(video_path)}...")
    subprocess.run(
        f'ffmpeg -i "{video_path}" -vn -ac 1 -ar 16000 -b:a 64k "{audio_path}" -y -hide_banner -loglevel error',
        shell=True, check=True
    )
    return audio_path

def split_audio_chunks(audio_path, chunk_duration=CHUNK_DURATION):
    """Divide o áudio em chunks para processamento paralelo"""
    base_name = os.path.splitext(audio_path)[0]
    chunk_pattern = f"{base_name}_chunk_%03d.mp3"
    
    # Verifica se já foi dividido
    existing_chunks = []
    i = 0
    while os.path.exists(f"{base_name}_chunk_{i:03d}.mp3"):
        existing_chunks.append(f"{base_name}_chunk_{i:03d}.mp3")
        i += 1
    
    if existing_chunks:
        return existing_chunks
    
    print(f"✂️ Dividindo áudio em chunks de {chunk_duration}s para processamento paralelo...")
    subprocess.run(
        f'ffmpeg -i "{audio_path}" -f segment -segment_time {chunk_duration} -c copy "{chunk_pattern}" -hide_banner -loglevel error',
        shell=True, check=True
    )
    
    chunks = []
    i = 0
    while os.path.exists(f"{base_name}_chunk_{i:03d}.mp3"):
        chunks.append(f"{base_name}_chunk_{i:03d}.mp3")
        i += 1
    
    return chunks

def transcribe_chunk_azure(chunk_path, index, client):
    """Transcreve um chunk usando Azure Whisper"""
    try:
        with open(chunk_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model=AZURE_WHISPER_DEPLOYMENT,
                file=audio_file,
                language="pt"
            )
        return index, transcript.text
    except Exception as e:
        print(f"❌ Erro no chunk {index}: {e}")
        return index, ""

def transcribe_parallel(audio_path, client):
    """Transcrição paralela usando Azure Whisper"""
    print(f"🚀 TRANSCRIÇÃO PARALELA (Azure Whisper)")
    
    chunks = split_audio_chunks(audio_path)
    print(f"   📦 {len(chunks)} chunks criados ({CHUNK_DURATION}s cada)")
    print(f"   ⚡ Processando {MAX_WORKERS} chunks simultaneamente...")
    
    results = [None] * len(chunks)
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(transcribe_chunk_azure, chunk, i, client): i 
            for i, chunk in enumerate(chunks)
        }
        
        with tqdm(total=len(chunks), desc="Chunks Azure") as pbar:
            for future in as_completed(futures):
                index, text = future.result()
                results[index] = text
                pbar.update(1)
    
    full_text = " ".join(results)
    
    # Limpa chunks temporários
    for chunk in chunks:
        if os.path.exists(chunk):
            os.remove(chunk)
    
    return full_text

def format_with_azure_gpt(full_text, client):
    """Formata usando Azure GPT-4o"""
    print(f"🧠 Formatando com Azure {AZURE_GPT_DEPLOYMENT}...")
    
    chunks = textwrap.wrap(full_text, 15000, break_long_words=False, replace_whitespace=False)
    print(f"   Dividido em {len(chunks)} partes")
    
    formatted_chunks = []
    for i, chunk in enumerate(tqdm(chunks, desc="Formatando")):
        try:
            response = client.chat.completions.create(
                model=AZURE_GPT_DEPLOYMENT,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": chunk}
                ],
                temperature=0.2
            )
            formatted_chunks.append(response.choices[0].message.content)
        except Exception as e:
            print(f"Erro na parte {i}: {e}")
            formatted_chunks.append(chunk)
    
    return "\n\n".join(formatted_chunks)

def main():
    if not os.path.exists(INPUT_FOLDER):
        print(f"Pasta {INPUT_FOLDER} não encontrada.")
        return
    
    files = sorted([f for f in os.listdir(INPUT_FOLDER) if f.endswith(('.mp4', '.mkv'))])
    
    # Cliente Azure OpenAI
    client = AzureOpenAI(
        api_key=AZURE_OPENAI_API_KEY,
        api_version=AZURE_API_VERSION,
        azure_endpoint=AZURE_OPENAI_ENDPOINT
    )
    
    print(f"🔥 MODO AZURE OPENAI: Transcrição Paralela Otimizada")
    print(f"   Endpoint: {AZURE_OPENAI_ENDPOINT}")
    print(f"   Workers: {MAX_WORKERS} simultâneos")
    print(f"   Chunk: {CHUNK_DURATION}s por pedaço\n")
    
    for filename in files:
        video_path = os.path.join(INPUT_FOLDER, filename)
        base_name = os.path.splitext(filename)[0]
        final_file = os.path.join(INPUT_FOLDER, f"{base_name}_APOSTILA.md")
        
        if os.path.exists(final_file):
            print(f"⏩ Pulando {filename} (já processado)")
            continue
        
        print(f"\n{'='*60}")
        print(f"🎬 {filename}")
        
        start_time = time.time()
        
        # 1. Extração de áudio
        audio_path = extract_audio(video_path)
        
        # 2. Transcrição paralela Azure
        raw_txt = os.path.join(INPUT_FOLDER, f"{base_name}_RAW.txt")
        if os.path.exists(raw_txt):
            print("   📂 Usando transcrição em cache")
            with open(raw_txt, 'r', encoding='utf-8') as f:
                full_text = f.read()
        else:
            full_text = transcribe_parallel(audio_path, client)
            with open(raw_txt, 'w', encoding='utf-8') as f:
                f.write(full_text)
        
        # 3. Formatação Azure GPT
        final_text = format_with_azure_gpt(full_text, client)
        
        # 4. Salvar
        with open(final_file, 'w', encoding='utf-8') as f:
            f.write(f"# {base_name}\n\n{final_text}")
        
        elapsed = (time.time() - start_time) / 60
        print(f"✨ CONCLUÍDO em {elapsed:.1f} minutos!")
        print(f"   📄 {final_file}")

if __name__ == "__main__":
    main()
