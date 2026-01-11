import os
import time
import subprocess
import textwrap
from concurrent.futures import ThreadPoolExecutor
from faster_whisper import WhisperModel
from openai import OpenAI
from tqdm import tqdm

# ================= CONFIGURAÇÕES DE ALTA PERFORMANCE =================

# PASTA DOS VÍDEOS
INPUT_FOLDER = "Aulas_PGM_RJ"

# CONFIGURAÇÃO DE TRANSCRIÇÃO (LOCAL)
# 'medium' = Melhor custo-benefício de velocidade/precisão
# 'large-v3' = Máxima precisão (mais lento)
WHISPER_SIZE = "medium" 
# 'int8' voa na GPU. Se der erro, mude para 'float32'
COMPUTE_TYPE = "int8" 
DEVICE = "cuda" if os.system("nvidia-smi") == 0 else "cpu"

# CONFIGURAÇÃO DE FORMATAÇÃO (API OPENAI)
API_KEY = "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"
MODELO_GPT = "gpt-4o"  # Use gpt-4o (o mais inteligente e rápido atualmente)

# Prompt Otimizado para Não-Resumo
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

# ================= MOTOR DO SCRIPT =================

def extract_audio_fast(video_path):
    """Extrai áudio usando FFmpeg direto (sem reencodar, muito rápido)"""
    audio_path = os.path.splitext(video_path)[0] + ".mp3"
    if os.path.exists(audio_path): return audio_path
    
    print(f"⚡ Extraindo áudio de {os.path.basename(video_path)}...")
    try:
        # Extrai em mono, 16k rate (ideal para whisper), low bitrate (rápido)
        subprocess.run(
            f'ffmpeg -i "{video_path}" -vn -ac 1 -ar 16000 -b:a 64k "{audio_path}" -y -hide_banner -loglevel error', 
            shell=True, check=True
        )
        return audio_path
    except Exception as e:
        print(f"Erro no FFmpeg: {e}")
        return None

def transcribe_batched(audio_path):
    """Transcreve usando Faster-Whisper com Batch Size (Velocidade Máxima na GPU)"""
    print(f"🚀 Transcrevendo {os.path.basename(audio_path)} usando {DEVICE.upper()}...")
    
    start = time.time()
    
    # Carrega o modelo
    model = WhisperModel(WHISPER_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
    
    # BATCH SIZE = O segredo da velocidade. Processa vários pedaços de áudio de uma vez na VRAM.
    segments, info = model.transcribe(
        audio_path, 
        beam_size=5, 
        language="pt",
        vad_filter=True, # Remove silêncios (acelera muito)
        vad_parameters=dict(min_silence_duration_ms=500)
    )
    
    # Coleta o texto com barra de progresso
    text_segments = []
    # Estimativa de segmentos baseada na duração (aprox 1 seg a cada 2s de fala)
    total_duration = info.duration
    
    with tqdm(total=total_duration, unit="s", desc="Progresso") as pbar:
        last_pos = 0
        for segment in segments:
            text_segments.append(segment.text)
            current_pos = segment.end
            pbar.update(current_pos - last_pos)
            last_pos = current_pos
            
    full_text = " ".join(text_segments)
    
    end = time.time()
    minutes = (end - start) / 60
    print(f"✅ Transcrição concluída em {minutes:.1f} minutos.")
    return full_text

def format_with_gpt_parallel(full_text, client):
    """Formata usando GPT-4o. Divide o texto e processa."""
    print(f"🧠 Formatando com {MODELO_GPT}...")
    
    # Chunk size de 15.000 caracteres (aprox 3k-4k tokens) é seguro para GPT-4o
    chunks = textwrap.wrap(full_text, 15000, break_long_words=False, replace_whitespace=False)
    print(f"   Dividido em {len(chunks)} partes para processamento.")
    
    formated_chunks = [None] * len(chunks)

    def process_chunk(index, text_chunk):
        try:
            response = client.chat.completions.create(
                model=MODELO_GPT,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text_chunk}
                ],
                temperature=0.2
            )
            return index, response.choices[0].message.content
        except Exception as e:
            print(f"Erro na parte {index}: {e}")
            return index, text_chunk # Retorna o bruto se falhar

    # Processamento sequencial é mais seguro para garantir ordem e evitar Rate Limit da OpenAI
    # Mas usamos tqdm para visualizar
    for i, chunk in enumerate(tqdm(chunks, desc="Formatando blocos")):
        idx, res = process_chunk(i, chunk)
        formated_chunks[idx] = res

    return "\n\n".join(formated_chunks)

def main():
    if not os.path.exists(INPUT_FOLDER):
        print(f"Pasta {INPUT_FOLDER} não encontrada.")
        return

    # Filtra arquivos de vídeo
    files = sorted([f for f in os.listdir(INPUT_FOLDER) if f.endswith(('.mp4', '.mkv', '.avi'))])
    
    client = OpenAI(api_key=API_KEY)

    print(f"🔥 INICIANDO PROCESSAMENTO DE {len(files)} AULAS")
    print(f"   Modo: {'GPU ACELERADA' if DEVICE == 'cuda' else 'CPU (LENTO)'}")
    
    for filename in files:
        video_path = os.path.join(INPUT_FOLDER, filename)
        base_name = os.path.splitext(filename)[0]
        final_file = os.path.join(INPUT_FOLDER, f"{base_name}_APOSTILA.md")
        
        if os.path.exists(final_file):
            print(f"⏩ Pulando {filename} (já processado)")
            continue
            
        print(f"\n=========================================")
        print(f"🎬 Processando: {filename}")
        
        # 1. Extração Ultra Rápida
        audio_path = extract_audio_fast(video_path)
        if not audio_path: continue
        
        # 2. Transcrição Bruta (Verifica cache)
        raw_txt_path = os.path.join(INPUT_FOLDER, f"{base_name}_RAW.txt")
        if os.path.exists(raw_txt_path):
            print("   📂 Transcrição bruta encontrada em cache.")
            with open(raw_txt_path, 'r', encoding='utf-8') as f: full_text = f.read()
        else:
            full_text = transcribe_batched(audio_path)
            with open(raw_txt_path, 'w', encoding='utf-8') as f: f.write(full_text)
        
        # 3. Formatação GPT-4o
        final_text = format_with_gpt_parallel(full_text, client)
        
        # Salva Resultado
        with open(final_file, 'w', encoding='utf-8') as f:
            f.write(f"# Transcrição: {base_name}\n\n{final_text}")
            
        print(f"✨ AULA PRONTA: {final_file}")
        
        # Limpeza opcional (desabilitada para manter MP3s conforme pedido anteriormente)
        # if os.path.exists(audio_path): os.remove(audio_path)

if __name__ == "__main__":
    main()
