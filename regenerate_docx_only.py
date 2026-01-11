import os
import sys
from pathlib import Path
from colorama import init, Fore
from mlx_vomo import VomoMLX

# Initialize colorama
init(autoreset=True)

def main():
    print(f"{Fore.CYAN}📄 Regenerando DOCX a partir do Markdown...")
    
    # Initialize Processor (No model needed really, but __init__ runs setup)
    # Using small model just to satisfy init requirements if any
    try:
        processor = VomoMLX(model_size="tiny") 
    except:
        # If init attempts to connect to Vertex and fails (unlikely if credentials set), proceed.
        # VomoMLX __init__ is lightweight.
        pass
        
    # File Paths
    base_dir = Path("/Users/nicholasjacob/Documents/Aplicativos/Iudex/Reta_Final_PGM/Direito Administrativo")
    md_path = base_dir / "Direito_Administrativo_Aulas_01_a_03.md"
    video_name = "Direito_Administrativo_Aulas_01_a_03"
    
    if not md_path.exists():
        print(f"{Fore.RED}❌ Arquivo MD não encontrado: {md_path}")
        return

    print(f"{Fore.GREEN}✅ Arquivo MD encontrado: {md_path.name}")
    
    # Read Markdown
    with open(md_path, "r", encoding="utf-8") as f:
        formatted_text = f.read()
    
    try:
        # Save as Word
        print(f"\n{Fore.YELLOW}💾 Gerando DOCX...")
        output_path = processor.save_as_word(formatted_text, video_name, str(base_dir))
        
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
