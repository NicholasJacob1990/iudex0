import os
import subprocess
from concurrent.futures import ThreadPoolExecutor

PASTA_VIDEOS = "Aulas_PGM_RJ"

def extrair_audio_simples(video_file):
    video_path = os.path.join(PASTA_VIDEOS, video_file)
    audio_path = os.path.join(PASTA_VIDEOS, video_file.rsplit('.', 1)[0] + ".mp3")
    
    if os.path.exists(audio_path):
        print(f"✅ Já existe: {audio_path}")
        return

    print(f"🎵 Extraindo: {video_file}...")
    try:
        # Extração rápida com ffmpeg
        cmd = [
            'ffmpeg', '-i', video_path, '-vn', 
            '-ab', '128k', '-ar', '44100', '-y', 
            audio_path, '-loglevel', 'error'
        ]
        subprocess.run(cmd, check=True)
        print(f"✨ Concluído: {video_file}")
    except Exception as e:
        print(f"❌ Erro em {video_file}: {e}")

def main():
    print("🚀 Iniciando extração em massa de MP3...")
    arquivos = [f for f in os.listdir(PASTA_VIDEOS) if f.endswith(('.mp4', '.mkv'))]
    
    # Usa 4 threads para extrair em paralelo (ajuste conforme CPU)
    with ThreadPoolExecutor(max_workers=4) as executor:
        executor.map(extrair_audio_simples, arquivos)
        
    print("🏁 Todas as extrações finalizadas!")

if __name__ == "__main__":
    main()
