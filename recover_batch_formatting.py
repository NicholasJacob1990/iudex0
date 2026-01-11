import asyncio
import os
from pathlib import Path
from colorama import init, Fore
from mlx_vomo import VomoMLX

# Initialize colorama
init(autoreset=True)

async def main():
    print(f"{Fore.CYAN}🚑 Iniciando Recuperação de Formatação: Direito Administrativo")
    
    # Initialize Processor
    processor = VomoMLX(model_size="large-v3-turbo")
    
    # Base Directory
    base_dir = Path("/Users/nicholasjacob/Documents/Aplicativos/Iudex/Reta_Final_PGM/Direito Administrativo")
    
    # Input File (RAW Text)
    raw_path = base_dir / "Direito_Administrativo_Aulas_01-03_COMPLETA_RAW.txt"
    
    if not raw_path.exists():
        print(f"{Fore.RED}❌ Arquivo RAW não encontrado: {raw_path}")
        return

    print(f"{Fore.GREEN}✅ Arquivo RAW encontrado: {raw_path.name}")
    
    with open(raw_path, "r", encoding="utf-8") as f:
        unified_text = f.read()
    
    # Define Output Name
    video_name = "Direito_Administrativo_Aulas_01_a_03"
    
    try:
        # Run Formatting
        print(f"\n{Fore.YELLOW}📂 Reiniciando Formatação (Gemini 3 Flash)...")
        formatted_text = await processor.format_transcription_async(
            transcription=unified_text,
            video_name=video_name,
            output_folder=str(base_dir),
            mode="APOSTILA"
        )
        
        # Explicit Save Steps
        print(f"\n{Fore.YELLOW}💾 Salvando arquivos finais...")
        
        # Save MD
        md_path = base_dir / f"{video_name}.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(formatted_text)
        print(f"{Fore.GREEN}✅ Markdown salvo: {md_path.name}")
        
        # Save DOCX
        docx_path = processor.save_as_word(formatted_text, video_name, str(base_dir))
        print(f"{Fore.GREEN}✅ Word salvo: {Path(docx_path).name if docx_path else 'Erro path'}")
        
    except Exception as e:
        print(f"{Fore.RED}❌ Erro na recuperação: {e}")

if __name__ == "__main__":
    asyncio.run(main())
