import os
import yt_dlp

# URL do site onde os vídeos estão hospedados (Necessário para o bypass do Vimeo)
REFERER_URL = "https://www.portalestudandodireito.com.br/"

# Pasta base para os downloads
BASE_OUTPUT_FOLDER = "/Users/nicholasjacob/Documents/Aplicativos/Iudex/Reta_Final_PGM"

# Estrutura de módulos e vídeos
modules = [
    {
        "folder": "Masterclass - Bruno Verzani",
        "videos": [
            ("01_MasterClass_Bruno_Verzani", "https://player.vimeo.com/video/1141404062"),
        ]
    },
    {
        "folder": "Direito do Trabalho e Previdenciário",
        "videos": [
            ("02_Previdenciario_Aula_01_Bloco_01", "https://player.vimeo.com/video/1133625482"),
            ("03_Previdenciario_Aula_01_Bloco_02", "https://player.vimeo.com/video/1133625131"),
            ("04_Previdenciario_Aula_01_Bloco_03", "https://player.vimeo.com/video/1133625920"),
            ("05_Previdenciario_Aula_01_Bloco_04", "https://player.vimeo.com/video/1135362290"),
            ("06_Previdenciario_Aula_01_Bloco_05", "https://player.vimeo.com/video/1135363601"),
            ("07_Processo_Trabalho_Aula_02_Bloco_01", "https://player.vimeo.com/video/1140979658"),
            ("08_Processo_Trabalho_Aula_02_Bloco_02", "https://player.vimeo.com/video/1140979244"),
            ("09_Processo_Trabalho_Aula_02_Bloco_03", "https://player.vimeo.com/video/1140978691"),
            ("10_Processo_Trabalho_Aula_03_Bloco_01", "https://player.vimeo.com/video/1142124684"),
            ("11_Processo_Trabalho_Aula_03_Bloco_02", "https://player.vimeo.com/video/1142124264"),
            ("12_Processo_Trabalho_Aula_03_Bloco_03", "https://player.vimeo.com/video/1142123733"),
        ]
    },
    {
        "folder": "Direito Administrativo",
        "videos": [
            ("13_Administrativo_Aula_01_Bloco_01", "https://player.vimeo.com/video/1136332027"),
            ("14_Administrativo_Aula_01_Bloco_02", "https://player.vimeo.com/video/1136331724"),
            ("15_Administrativo_Aula_01_Bloco_03", "https://player.vimeo.com/video/1136331353"),
            ("16_Administrativo_Aula_01_Bloco_04", "https://player.vimeo.com/video/1136331085"),
            ("17_Administrativo_Aula_02_Bloco_01", "https://player.vimeo.com/video/1142128570"),
            ("18_Administrativo_Aula_02_Bloco_02", "https://player.vimeo.com/video/1142128109"),
            ("19_Administrativo_Aula_02_Bloco_03", "https://player.vimeo.com/video/1142127839"),
            ("20_Administrativo_Aula_02_Bloco_04", "https://player.vimeo.com/video/1142127658"),
            ("21_Administrativo_Aula_02_Bloco_01_Extra", "https://player.vimeo.com/video/1142134356"),
            ("22_Administrativo_Aula_02_Bloco_02_Extra", "https://player.vimeo.com/video/1142134160"),
        ]
    },
    {
        "folder": "Processo Civil",
        "videos": [
            ("23_Processo_Civil_Aula_01_Bloco_01", "https://player.vimeo.com/video/1136911992"),
            ("24_Processo_Civil_Aula_01_Bloco_02", "https://player.vimeo.com/video/1136911858"),
            ("25_Processo_Civil_Aula_01_Bloco_03", "https://player.vimeo.com/video/1136911626"),
            ("26_Processo_Civil_Aula_01_Bloco_04", "https://player.vimeo.com/video/1136911542"),
        ]
    },
    {
        "folder": "Direito Constitucional e Proc. Leg. Municipal",
        "videos": [
            ("27_Constitucional_Aula_01_Bloco_01", "https://player.vimeo.com/video/1137727926"),
            ("28_Constitucional_Aula_01_Bloco_02", "https://player.vimeo.com/video/1137730427"),
            ("29_Constitucional_Aula_01_Bloco_03", "https://player.vimeo.com/video/1137720096"),
            ("30_Constitucional_Aula_01_Bloco_04_Parte1", "https://player.vimeo.com/video/1137724089"),
            ("31_Constitucional_Aula_01_Bloco_05_Parte2", "https://player.vimeo.com/video/1137727757"),
            ("32_Constitucional_Aula_02_Bloco_01", "https://player.vimeo.com/video/1140073535"),
            ("33_Constitucional_Aula_02_Bloco_02", "https://player.vimeo.com/video/1140075759"),
            ("34_Constitucional_Aula_02_Bloco_03", "https://player.vimeo.com/video/1140071498"),
            ("35_Constitucional_Aula_02_Bloco_04_Parte1", "https://player.vimeo.com/video/1140078022"),
            ("36_Constitucional_Aula_02_Bloco_04_Parte2", "https://player.vimeo.com/video/1140079919"),
        ]
    }
]

def check_ffmpeg():
    from shutil import which
    if which("ffmpeg") is None:
        return False
    return True

def download_videos():
    has_ffmpeg = check_ffmpeg()
    
    # Cria pasta base se não existir
    if not os.path.exists(BASE_OUTPUT_FOLDER):
        os.makedirs(BASE_OUTPUT_FOLDER)

    total_videos = sum(len(m['videos']) for m in modules)
    print(f"Iniciando download de {total_videos} aulas em {len(modules)} módulos...")
    print(f"Pasta de destino: {BASE_OUTPUT_FOLDER}")
    
    if has_ffmpeg:
        print("🎥 Modo: Qualidade MÁXIMA (1080p/4K) com fusão de áudio (FFmpeg detectado).")
    else:
        print("⚠️ Modo: Qualidade PADRÃO (720p/Compatível) - FFmpeg não detectado.")
        print("   (Para qualidade máxima, instale o FFmpeg: brew install ffmpeg)")
    print("-" * 50)

    current_video_idx = 0
    for module in modules:
        folder_name = module['folder']
        module_path = os.path.join(BASE_OUTPUT_FOLDER, folder_name)
        
        if not os.path.exists(module_path):
            os.makedirs(module_path)
            
        print(f"\n📂 Módulo: {folder_name}")
        
        for filename, url in module['videos']:
            current_video_idx += 1
            print(f"[{current_video_idx}/{total_videos}] Baixando: {filename}...")
            
            # Seleciona o formato baseado na presença do FFmpeg
            if has_ffmpeg:
                format_str = 'bestvideo+bestaudio/best'
            else:
                format_str = 'best[vcodec!=none][acodec!=none]' # Fallback seguro com áudio

            # Configurações do yt_dlp
            ydl_opts = {
                'format': format_str,
                'merge_output_format': 'mp4' if has_ffmpeg else None,
                'outtmpl': f'{module_path}/{filename}.%(ext)s',
                'http_headers': {
                    'Referer': REFERER_URL,
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                },
                'quiet': False,
                'no_warnings': False,
                'verbose': False, 
            }

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                print(f"✅ Sucesso: {filename}")
            except Exception as e:
                print(f"❌ Erro ao baixar {filename}: {str(e)}")
            
            print("-" * 50)

    print("Processo finalizado!")

if __name__ == "__main__":
    download_videos()
