import os
import time
from faster_whisper import WhisperModel
from openai import OpenAI
import textwrap

# --- CONFIGURAÇÕES ---
PASTA_VIDEOS = "Aulas_PGM_RJ"
MODELO_WHISPER = "medium"  # 'medium' é um bom balanço entre velocidade e qualidade
COMPUTE_TYPE = "int8"      # Quantização para maior velocidade
DEVICE = "cpu"             # Mac sem NVIDIA usa CPU

# Configuração GPT
USAR_API_PARA_FORMATAR = True
MODELO_GPT = "gpt-4o-mini"
API_KEY = "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"

PROMPT_SISTEMA = """
ATENÇÃO: Você é um FORMATADOR JURÍDICO.
1. NÃO RESUMA. Mantenha a integralidade do conteúdo.
2. Corrija português e pontuação.
3. Use <b>Negrito</b> em termos técnicos.
4. Formate como apostila de estudos.
"""

def extrair_audio(video_path):
    audio_path = video_path.rsplit('.', 1)[0] + ".mp3"
    if not os.path.exists(audio_path):
        print(f"🎵 Extraindo áudio...")
        os.system(f'ffmpeg -i "{video_path}" -vn -ab 64k -ac 1 -ar 16000 -y "{audio_path}" -loglevel error')
    return audio_path

def transcrever_local(audio_path):
    print(f"🚀 Transcrevendo com Faster-Whisper LOCAL ({DEVICE} / {COMPUTE_TYPE})...")
    
    model = WhisperModel(MODELO_WHISPER, device=DEVICE, compute_type=COMPUTE_TYPE)
    segments, info = model.transcribe(audio_path, beam_size=5, language="pt")
    
    texto_completo = []
    print(f"   Idioma detectado: '{info.language}' (confiança: {info.language_probability:.2f})")
    
    start_time = time.time()
    for i, segment in enumerate(segments):
        if i % 100 == 0:
            tempo_decorrido = time.time() - start_time
            print(f"   ⏱️ Progresso: {time.strftime('%H:%M:%S', time.gmtime(segment.end))} ({tempo_decorrido:.0f}s)")
        texto_completo.append(segment.text)
        
    return " ".join(texto_completo)

def formatar_com_gpt(texto_bruto, client):
    print(f"🧠 Refinando com {MODELO_GPT}...")
    tamanho_chunk = 15000
    chunks = textwrap.wrap(texto_bruto, tamanho_chunk, break_long_words=False, replace_whitespace=False)
    texto_final = ""

    for i, chunk in enumerate(chunks):
        print(f"   🔄 Formatando parte {i+1}/{len(chunks)}...")
        try:
            response = client.chat.completions.create(
                model=MODELO_GPT,
                messages=[
                    {"role": "system", "content": PROMPT_SISTEMA},
                    {"role": "user", "content": f"PARTE {i+1}:\n\n{chunk}"}
                ],
                temperature=0.2
            )
            texto_final += response.choices[0].message.content + "\n\n"
        except Exception as e:
            print(f"❌ Erro GPT: {e}")
            texto_final += chunk + "\n"
            
    return texto_final

def main():
    print(f"⚡ MODO LOCAL: Faster-Whisper ({DEVICE}) + GPT-4o-mini")
    client = OpenAI(api_key=API_KEY) if USAR_API_PARA_FORMATAR else None
    
    arquivos = sorted([f for f in os.listdir(PASTA_VIDEOS) if f.endswith(('.mp4', '.mkv'))])
    
    for arquivo in arquivos:
        full_path = os.path.join(PASTA_VIDEOS, arquivo)
        nome_base = arquivo.rsplit('.', 1)[0]
        saida = os.path.join(PASTA_VIDEOS, f"{nome_base}_FINAL.md")
        
        if os.path.exists(saida): 
            print(f"⏩ Pulando {arquivo}, transcrição já existe.")
            continue
        
        print(f"\n🎬 {arquivo}")
        
        # 1. Áudio
        audio = extrair_audio(full_path)
        
        # 2. Transcrição
        bruto_path = os.path.join(PASTA_VIDEOS, f"{nome_base}_BRUTO.txt")
        if os.path.exists(bruto_path):
            print("   📂 Usando transcrição bruta existente.")
            with open(bruto_path, 'r', encoding='utf-8') as f: 
                texto_bruto = f.read()
        else:
            texto_bruto = transcrever_local(audio)
            with open(bruto_path, 'w', encoding='utf-8') as f: 
                f.write(texto_bruto)
            
        # 3. GPT
        if client:
            final = formatar_com_gpt(texto_bruto, client)
            with open(saida, 'w', encoding='utf-8') as f: 
                f.write(final)
            
        print(f"✅ Concluído: {arquivo}")

if __name__ == "__main__":
    main()
