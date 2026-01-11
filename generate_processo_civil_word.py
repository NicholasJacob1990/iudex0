import os
import sys
from pathlib import Path
from colorama import init, Fore
from mlx_vomo import VomoMLX

# Initialize colorama
init(autoreset=True)

def main():
    print(f"{Fore.CYAN}📄 Gerando DOCX para PROCESSO CIVIL...")
    
    # Initialize Processor
    try:
        # VomoMLX init might need model_size, we use tiny for speed/satisfaction
        processor = VomoMLX(model_size="tiny") 
    except Exception as e:
        print(f"{Fore.YELLOW}⚠️ Aviso ao inicializar processador: {e}")
        # We try to proceed as save_as_word is mostly logic-based
        pass
        
    # File Paths
    md_path = Path("/Users/nicholasjacob/Documents/Aplicativos/Iudex/Reta_Final_PGM/Processo Civil/Processo_Civil_Aulas_01_02_03_COMPLETA_RAW_APOSTILA.md")
    video_name = "Processo_Civil_Aulas_01_02_03_COMPLETA_RAW"
    output_dir = md_path.parent
    
    if not md_path.exists():
        print(f"{Fore.RED}❌ Arquivo MD não encontrado: {md_path}")
        return

    print(f"{Fore.GREEN}✅ Arquivo MD encontrado: {md_path.name}")
    
    # Read Markdown
    with open(md_path, "r", encoding="utf-8") as f:
        formatted_text = f.read()
    
    try:
        # Save as Word
        print(f"\n{Fore.YELLOW}💾 Gerando DOCX com formatação profissional (1cm indent, 1.5 spacing, justified)...")
        output_path = processor.save_as_word(formatted_text, video_name, str(output_dir))
        
        if output_path:
            print(f"{Fore.GREEN}✅ Sucesso! Arquivo salvo em: {output_path}")
        else:
             print(f"{Fore.RED}❌ Falha ao salvar arquivo (retorno vazio).")
             
    except Exception as e:
        print(f"{Fore.RED}❌ Erro durante a geração: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
