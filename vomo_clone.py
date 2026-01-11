import os
import time
import subprocess
from faster_whisper import WhisperModel
from openai import OpenAI
from colorama import Fore, Style, init
from tqdm import tqdm

# Inicializa cores para o terminal
init(autoreset=True)

class VomoClone:
    def __init__(self, model_size="large-v3-turbo", device="cpu", compute_type="int8"):
        """
        Inicializa o motor de transcrição.
        Para Mac M1/M2/M3: device='cpu' com compute_type='int8' é extremamente eficiente no CTranslate2.
        """
        print(f"{Fore.CYAN}🚀 Inicializando motor Whisper ({model_size})...")
        self.model = WhisperModel(model_size, device=device, compute_type=compute_type)
        
        # Cliente LLM
        api_key = os.getenv("OPENAI_API_KEY") or "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"
        self.llm_client = OpenAI(api_key=api_key)

    def optimize_audio(self, file_path):
        """
        Pré-processamento usando ffmpeg direto (16kHz, mono).
        """
        print(f"{Fore.YELLOW}⚡ Otimizando áudio para processamento...")
        
        # Se já existe MP3, usa ele direto
        mp3_path = file_path.replace('.mp4', '.mp3').replace('.mkv', '.mp3')
        if os.path.exists(mp3_path):
            print(f"   📂 Usando MP3 existente")
            return mp3_path
        
        # Caso contrário, extrai otimizado
        output_path = f"temp_optimized_{os.path.basename(file_path)}.wav"
        if os.path.exists(output_path):
            return output_path
        
        subprocess.run(
            f'ffmpeg -i "{file_path}" -vn -ac 1 -ar 16000 "{output_path}" -y -hide_banner -loglevel error',
            shell=True, check=True
        )
        return output_path

    def transcribe(self, audio_path):
        """
        Realiza a transcrição com VAD (filtro de voz) ativado para velocidade.
        """
        print(f"{Fore.GREEN}🎙️  Iniciando transcrição (VAD Ativado)...")
        start_time = time.time()

        # vad_filter=True pula os silêncios, acelerando drasticamente a transcrição
        segments, info = self.model.transcribe(
            audio_path, 
            beam_size=5, 
            language="pt",
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500)
        )

        full_text = []
        print(f"   Detectado idioma '{info.language}' com probabilidade de {info.language_probability:.2f}")
        print(f"   Duração: {info.duration:.1f}s")

        # Processa segmentos com barra de progresso
        with tqdm(total=int(info.duration), unit="s", desc="Transcrevendo") as pbar:
            last_pos = 0
            for segment in segments:
                full_text.append(segment.text)
                current_pos = int(segment.end)
                pbar.update(current_pos - last_pos)
                last_pos = current_pos

        elapsed = time.time() - start_time
        print(f"{Fore.GREEN}✅ Transcrição concluída em {elapsed / 60:.1f} minutos.")
        
        return " ".join(full_text)

    def format_transcription(self, transcript_text, video_name):
        """
        Formata a transcrição usando o prompt detalhado fornecido pelo usuário.
        """
        print(f"{Fore.MAGENTA}🧠 Formatando transcrição com GPT-4o...")
        
        # Divide em chunks para processar textos grandes
        import textwrap
        max_chars = 12000  # Tamanho seguro para GPT-4o
        chunks = textwrap.wrap(transcript_text, max_chars, break_long_words=False, replace_whitespace=False)
        
        print(f"   Dividido em {len(chunks)} partes para processamento")
        
        formatted_chunks = []
        
        system_prompt = """Você é um especialista em revisão de transcrições. Sua tarefa é revisar a transcrição fornecida de uma aula, corrigindo erros gramaticais e de pontuação, melhorando a formatação para facilitar a leitura, e mantendo o conteúdo original. Não resuma, não parafraseie e não adicione informações que não estejam na transcrição original. Siga estas diretrizes:

-Corrija erros gramaticais, ortográficos e de pontuação, tornando o texto gramaticalmente correto e claro.
-Mantenha todo o conteúdo original, incluindo ideias, exemplos, explicações, pausas, hesitações e ideias incompletas, fazendo o uso apropriado de aspas, parênteses e colchetes. Não resuma, não omita informações nem altere o significado.
-Melhore a formatação para facilitar a leitura.
-Mantenha todo o conteúdo original, mas corrija erros da linguagem coloquial para torná-la mais clara e legível.
-Ajuste a linguagem coloquial para um português padrão, mantendo o significado original.
-Preserve a sequência exata das falas e ideias apresentadas.
-Utilize formatação e estrutura com parágrafos bem definidos, facilitando a leitura e compreensão, para melhorar a legibilidade, seguindo o fluxo natural do discurso. Evite parágrafos longos.
-Reproduza fielmente as informações, apenas melhorando a clareza e a legibilidade.
-Utilize conectivos necessários para tornar o texto mais fluido. Aplique a pontuação devida para deixar o texto coeso e coerente.
-Corrija vícios de linguagem, como repetições desnecessárias, uso excessivo de advérbios, linguagem vaga ou imprecisa, gírias, expressões redundantes, e outros erros que afetem a clareza e a eficácia da comunicação, sem alterar o significado do texto.
-Identifique e rotule os diferentes falantes, se existentes, organizando suas falas de forma clara.
-Se conveniente, divida a aula em tópicos para melhor organização e visualização do conteúdo
-Enumere os tópicos e subtópicos, use negrito quando mais apropriado
-Seja didático sem perder detalhes e conteúdo
-**Ao final de cada tópico/capítulo, sintetize/resume o assunto de forma esquematizada, preferencialmente por tabela**

Por favor, forneça a versão revisada da transcrição, seguindo estritamente as diretrizes acima. Lembre-se: o objetivo é manter o conteúdo fiel ao original, melhorando apenas a clareza e legibilidade."""

        for i, chunk in enumerate(tqdm(chunks, desc="Formatando")):
            part_info = f" (Parte {i+1}/{len(chunks)})" if len(chunks) > 1 else ""
            
            user_prompt = f"""Aqui está a transcrição{part_info} da aula "{video_name}" para você revisar:

<transcrição>
{chunk}
</transcrição>"""

            try:
                response = self.llm_client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.2
                )
                formatted_chunks.append(response.choices[0].message.content)
            except Exception as e:
                print(f"{Fore.RED}   Erro na parte {i+1}: {e}")
                formatted_chunks.append(chunk)  # Fallback: retorna o original
        
        return "\n\n".join(formatted_chunks)

# --- Execução em Lote ---
def process_all_videos(folder="Aulas_PGM_RJ"):
    """Processa todos os vídeos MP4 na pasta"""
    import glob
    
    vomo = VomoClone(model_size="large-v3-turbo")
    
    videos = sorted(glob.glob(os.path.join(folder, "*.mp4")))
    print(f"\n{Fore.CYAN}{'='*60}")
    print(f"{Fore.CYAN}🎬 Encontrados {len(videos)} vídeos para processar")
    print(f"{Fore.CYAN}{'='*60}\n")
    
    for video_path in videos:
        video_name = os.path.basename(video_path).replace(".mp4", "")
        final_file = os.path.join(folder, f"{video_name}_APOSTILA.md")
        
        # Pula se já processado
        if os.path.exists(final_file):
            print(f"{Fore.YELLOW}⏩ Pulando {video_name} (já processado)")
            continue
        
        print(f"\n{Fore.CYAN}{'='*60}")
        print(f"{Fore.CYAN}🎬 Processando: {video_name}")
        print(f"{Fore.CYAN}{'='*60}\n")
        
        try:
            # 1. Otimiza áudio
            optimized_file = vomo.optimize_audio(video_path)
            
            # 2. Transcreve (verifica cache)
            raw_txt = os.path.join(folder, f"{video_name}_RAW.txt")
            if os.path.exists(raw_txt):
                print(f"{Fore.YELLOW}   📂 Usando transcrição em cache")
                with open(raw_txt, "r", encoding="utf-8") as f:
                    transcription = f.read()
            else:
                transcription = vomo.transcribe(optimized_file)
                with open(raw_txt, "w", encoding="utf-8") as f:
                    f.write(transcription)
            
            # 3. Formata com GPT-4o
            formatted_text = vomo.format_transcription(transcription, video_name)
            
            # 4. Salva apostila completa
            apostila = f"""# {video_name}

{formatted_text}
"""
            with open(final_file, "w", encoding="utf-8") as f:
                f.write(apostila)
            
            print(f"\n{Fore.GREEN}✨ CONCLUÍDO: {final_file}")
            
            # Limpeza
            if os.path.exists(optimized_file):
                os.remove(optimized_file)
                
        except Exception as e:
            print(f"{Fore.RED}❌ Erro ao processar {video_name}: {e}")
            continue

if __name__ == "__main__":
    process_all_videos()
