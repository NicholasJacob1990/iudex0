import asyncio
import os
from pathlib import Path
from colorama import init, Fore
from mlx_vomo import VomoMLX

# Initialize colorama
init(autoreset=True)

async def main():
    print(f"{Fore.CYAN}🚀 Iniciando Processamento em Lote: Direito Administrativo")
    
    # Initialize Processor
    processor = VomoMLX(model_size="large-v3-turbo")
    
    # Base Directory
    base_dir = Path("/Users/nicholasjacob/Documents/Aplicativos/Iudex/Reta_Final_PGM/Direito Administrativo")
    
    # Ordered List of Videos
    videos = [
        # Aula 01
        base_dir / "13_Administrativo_Aula_01_Bloco_01.mp4",
        base_dir / "14_Administrativo_Aula_01_Bloco_02.mp4",
        base_dir / "15_Administrativo_Aula_01_Bloco_03.mp4",
        base_dir / "16_Administrativo_Aula_01_Bloco_04.mp4",
        # Aula 02
        base_dir / "17_Administrativo_Aula_02_Bloco_01.mp4",
        base_dir / "18_Administrativo_Aula_02_Bloco_02.mp4",
        base_dir / "19_Administrativo_Aula_02_Bloco_03.mp4",
        base_dir / "20_Administrativo_Aula_02_Bloco_04.mp4",
        # Aula 03 (Subfolder)
        base_dir / "Aula 03/PED 3.1.mkv",
        base_dir / "Aula 03/PED 3.2.mkv",
        base_dir / "Aula 03/PED 3.3.mkv",
        base_dir / "Aula 03/PED 3.4.mkv"
    ]
    
    full_transcription_parts = []
    
    # 1. Transcription Phase
    print(f"\n{Fore.YELLOW}📂 FASE 1: Transcrição em Lote ({len(videos)} arquivos)")
    
    for i, video_path in enumerate(videos):
        if not video_path.exists():
            print(f"{Fore.RED}❌ Arquivo não encontrado: {video_path}")
            continue
            
        print(f"\n{Fore.BLUE}▶️  Processando [{i+1}/{len(videos)}]: {video_path.name}")
        
        try:
            # Optimize Audio
            audio_path = processor.optimize_audio(str(video_path))
            
            # Transcribe
            transcript = processor.transcribe(audio_path)
            
            # Tag and Store
            header = f"\n\n<!-- INÍCIO DO VÍDEO: {video_path.name} -->\n\n"
            full_transcription_parts.append(header + transcript)
            
        except Exception as e:
            print(f"{Fore.RED}❌ Erro ao processar {video_path.name}: {e}")
    
    # 2. Unification Phase
    print(f"\n{Fore.YELLOW}📂 FASE 2: Unificação do Texto")
    unified_text = "".join(full_transcription_parts)
    
    # Save Raw Unified Text
    raw_output_path = base_dir / "Direito_Administrativo_Aulas_01-03_COMPLETA_RAW.txt"
    with open(raw_output_path, "w", encoding="utf-8") as f:
        f.write(unified_text)
    print(f"{Fore.GREEN}✅ Texto unificado salvo em: {raw_output_path.name}")
    
    # 3. Formatting Phase
    print(f"\n{Fore.YELLOW}📂 FASE 3: Formatação e Geração de Apostila (Gemini 3 Flash)")
    
    try:
        await processor.format_transcription_async(
            transcription=unified_text,
            video_name="Direito_Administrativo_Aulas_01_a_03", # Output base name
            output_folder=str(base_dir),
            mode="APOSTILA"
        )
    except Exception as e:
        print(f"{Fore.RED}❌ Erro na formatação final: {e}")

if __name__ == "__main__":
    asyncio.run(main())
