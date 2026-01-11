import os
import subprocess
import textwrap
from faster_whisper import WhisperModel
from openai import OpenAI
from tqdm import tqdm
import time

# ================= CONFIGURAÇÕES =================

INPUT_FOLDER = "Aulas_PGM_RJ"

# Faster-Whisper Local (Otimizado)
WHISPER_MODEL = "medium"  # medium = bom balanço velocidade/qualidade
COMPUTE_TYPE = "int8"     # int8 = muito mais rápido
DEVICE = "cpu"            # Mac usa CPU

# OpenAI para formatação (mantém qualidade premium)
API_KEY = "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"
MODELO_GPT = "gpt-4o"

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

def transcribe_local_optimized(audio_path):
    """Transcreve localmente com Faster-Whisper + VAD"""
    print(f"🚀 Transcrevendo com Faster-Whisper LOCAL")
    print(f"   Modelo: {WHISPER_MODEL} | Device: {DEVICE} | Compute: {COMPUTE_TYPE}")
    
    start = time.time()
    
    # Carrega modelo otimizado
    model = WhisperModel(WHISPER_MODEL, device=DEVICE, compute_type=COMPUTE_TYPE)
    
    # Transcreve com VAD (pula silêncios = muito mais rápido!)
    segments, info = model.transcribe(
        audio_path,
        beam_size=5,
        language="pt",
        vad_filter=True,  # CRUCIAL: pula silêncios
        vad_parameters=dict(min_silence_duration_ms=500)
    )
    
    print(f"   Idioma: {info.language} (confiança: {info.language_probability:.2f})")
    print(f"   Duração: {info.duration:.1f}s")
    
    # Coleta texto com progresso
    text_segments = []
    with tqdm(total=int(info.duration), unit="s", desc="Transcrevendo") as pbar:
        last_pos = 0
        for segment in segments:
            text_segments.append(segment.text)
            current_pos = int(segment.end)
            pbar.update(current_pos - last_pos)
            last_pos = current_pos
    
    full_text = " ".join(text_segments)
    
    elapsed = (time.time() - start) / 60
    print(f"   ✅ Concluído em {elapsed:.1f} minutos")
    
    return full_text

def format_with_gpt(full_text, client):
    """Formata usando GPT-4o"""
    print(f"🧠 Formatando com {MODELO_GPT}...")
    
    chunks = textwrap.wrap(full_text, 15000, break_long_words=False, replace_whitespace=False)
    print(f"   Dividido em {len(chunks)} partes")
    
    formatted_chunks = []
    for i, chunk in enumerate(tqdm(chunks, desc="Formatando")):
        try:
            response = client.chat.completions.create(
                model=MODELO_GPT,
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
    client = OpenAI(api_key=API_KEY)
    
    print(f"🔥 MODO: Faster-Whisper LOCAL + GPT-4o")
    print(f"   Sem custos de transcrição!")
    print(f"   Processamento 100% offline\n")
    
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
        
        # 2. Transcrição local (cache check)
        raw_txt = os.path.join(INPUT_FOLDER, f"{base_name}_RAW.txt")
        if os.path.exists(raw_txt):
            print("   📂 Usando transcrição em cache")
            with open(raw_txt, 'r', encoding='utf-8') as f:
                full_text = f.read()
        else:
            full_text = transcribe_local_optimized(audio_path)
            with open(raw_txt, 'w', encoding='utf-8') as f:
                f.write(full_text)
        
        # 3. Formatação GPT
        final_text = format_with_gpt(full_text, client)
        
        # 4. Salvar
        with open(final_file, 'w', encoding='utf-8') as f:
            f.write(f"# {base_name}\n\n{final_text}")
        
        elapsed = (time.time() - start_time) / 60
        print(f"✨ CONCLUÍDO em {elapsed:.1f} minutos!")
        print(f"   📄 {final_file}")

if __name__ == "__main__":
    main()
