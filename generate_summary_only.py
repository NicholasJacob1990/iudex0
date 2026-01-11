import os
import asyncio
from format_only import VomoFormatter
from colorama import Fore, init

init(autoreset=True)

def main():
    # Caminho do arquivo fonte (MD é melhor que DOCX para leitura)
    source_file = "/Users/nicholasjacob/Documents/Aplicativos/Iudex/Reta_Final_PGM/Direito do Trabalho e Previdenciário/Previdenciario_Aula_01_APOSTILA_COMPLETA.md"
    
    if not os.path.exists(source_file):
        print(f"{Fore.RED}❌ Arquivo não encontrado: {source_file}")
        return

    print(f"{Fore.CYAN}🚀 Iniciando geração de resumo para: {os.path.basename(source_file)}")
    
    # Lê o conteúdo
    with open(source_file, 'r', encoding='utf-8') as f:
        full_text = f.read()
    
    # Inicializa formatador
    formatter = VomoFormatter()
    
    # Gera resumo
    summary_text = formatter.generate_summary_version(full_text)
    
    # Define caminhos de saída
    folder = os.path.dirname(source_file)
    base_name = "Previdenciario_Aula_01"
    
    output_md = os.path.join(folder, f"{base_name}_RESUMO_V2.md")
    
    # Salva MD
    with open(output_md, 'w', encoding='utf-8') as f:
        f.write(summary_text)
    print(f"{Fore.GREEN}📝 MD Resumo salvo: {output_md}")
    
    # Salva DOCX
    docx_path = formatter.save_as_word(summary_text, f"{base_name}_RESUMO_V2", folder)
    print(f"{Fore.GREEN}📄 Word Resumo salvo: {docx_path}")

if __name__ == "__main__":
    main()
