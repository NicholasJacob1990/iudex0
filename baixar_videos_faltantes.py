#!/usr/bin/env python3
"""
Script para baixar apenas os vídeos faltantes do curso
Total: 8 vídeos (Processo Civil Aula 02 + Civil e Empresarial Aula 03)
"""
import os
import yt_dlp

# URL do site onde os vídeos estão hospedados
REFERER_URL = "https://www.portalestudandodireito.com.br/"

# Pasta base para os downloads
BASE_OUTPUT_FOLDER = "/Users/nicholasjacob/Documents/Aplicativos/Iudex/Reta_Final_PGM"

# Vídeos faltantes
modules = [
    {
        "folder": "Processo Civil",
        "videos": [
            ("27_Processo_Civil_Aula_02_Bloco_01", "https://player.vimeo.com/video/1142759814"),
            ("28_Processo_Civil_Aula_02_Bloco_02", "https://player.vimeo.com/video/1142759612"),
            ("29_Processo_Civil_Aula_02_Bloco_03", "https://player.vimeo.com/video/1142759404"),
            ("30_Processo_Civil_Aula_02_Bloco_04", "https://player.vimeo.com/video/1142758970"),
        ]
    },
    {
        "folder": "Civil e Empresarial",
        "videos": [
            ("37_Civil_Empresarial_Aula_03_Bloco_01", "https://player.vimeo.com/video/1145257813"),
            ("38_Civil_Empresarial_Aula_03_Bloco_02", "https://player.vimeo.com/video/1145253047"),
            ("39_Civil_Empresarial_Aula_03_Bloco_03", "https://player.vimeo.com/video/1145254767"),
            ("40_Civil_Empresarial_Aula_03_Bloco_04", "https://player.vimeo.com/video/1145256277"),
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
    print(f"🎬 Iniciando download de {total_videos} aulas faltantes...")
    print(f"📂 Pasta de destino: {BASE_OUTPUT_FOLDER}")
    
    if has_ffmpeg:
        print("✨ Modo: Qualidade MÁXIMA (1080p/4K) com fusão de áudio (FFmpeg detectado).")
    else:
        print("⚠️  Modo: Qualidade PADRÃO (720p) - FFmpeg não detectado.")
        print("   (Para qualidade máxima, instale: brew install ffmpeg)")
    print("-" * 70)

    current_video_idx = 0
    total_downloaded = 0
    total_skipped = 0
    
    for module in modules:
        folder_name = module['folder']
        module_path = os.path.join(BASE_OUTPUT_FOLDER, folder_name)
        
        # Cria pasta se não existir
        if not os.path.exists(module_path):
            os.makedirs(module_path)
            
        print(f"\n📂 Módulo: {folder_name}")
        
        for filename, url in module['videos']:
            current_video_idx += 1
            output_file = f'{module_path}/{filename}.mp4'
            
            # Verifica se já existe
            if os.path.exists(output_file):
                file_size = os.path.getsize(output_file)
                if file_size > 1000000:  # > 1MB = válido
                    print(f"[{current_video_idx}/{total_videos}] ⏭️  Pulando (já existe): {filename}")
                    total_skipped += 1
                    continue
            
            print(f"[{current_video_idx}/{total_videos}] 📥 Baixando: {filename}...")
            
            # Seleciona formato
            if has_ffmpeg:
                format_str = 'bestvideo+bestaudio/best'
            else:
                format_str = 'best[vcodec!=none][acodec!=none]'

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
                total_downloaded += 1
            except Exception as e:
                print(f"❌ Erro ao baixar {filename}: {str(e)}")
            
            print("-" * 70)

    print(f"\n🎉 Processo finalizado!")
    print(f"   ✅ Baixados: {total_downloaded}")
    print(f"   ⏭️  Pulados (já existiam): {total_skipped}")
    print(f"   📊 Total processado: {total_videos}")

if __name__ == "__main__":
    download_videos()
