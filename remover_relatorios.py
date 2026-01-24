#!/usr/bin/env python3
"""
Remove comentários HTML de relatórios de auditoria dos arquivos markdown
"""

import re
import os
from pathlib import Path

def remover_comentarios_relatorio(arquivo):
    """Remove todos os comentários HTML <!-- RELATÓRIO: ... --> do arquivo"""
    
    print(f"📄 Processando: {Path(arquivo).name}")
    
    with open(arquivo, 'r', encoding='utf-8') as f:
        conteudo = f.read()
    
    # Conta quantos comentários existem
    comentarios_antes = conteudo.count('<!-- RELATÓRIO:')
    
    # Remove comentários HTML multi-linha que começam com <!-- RELATÓRIO:
    # Padrão: <!-- RELATÓRIO: ... --> (pode ter múltiplas linhas)
    conteudo_limpo = re.sub(
        r'<!--\s*RELATÓRIO:.*?-->',
        '',
        conteudo,
        flags=re.DOTALL | re.MULTILINE
    )
    
    # Remove linhas vazias duplicadas resultantes
    conteudo_limpo = re.sub(r'\n{3,}', '\n\n', conteudo_limpo)
    
    # Conta quantos foram removidos
    comentarios_depois = conteudo_limpo.count('<!-- RELATÓRIO:')
    removidos = comentarios_antes - comentarios_depois
    
    if removidos > 0:
        # Salva o arquivo limpo
        with open(arquivo, 'w', encoding='utf-8') as f:
            f.write(conteudo_limpo)
        
        print(f"   ✅ {removidos} comentário(s) de relatório removido(s)")
        return True
    else:
        print(f"   ℹ️  Nenhum comentário de relatório encontrado")
        return False

def processar_diretorio(diretorio):
    """Processa todos os arquivos .md no diretório"""
    
    arquivos_processados = 0
    arquivos_alterados = 0
    
    for arquivo in Path(diretorio).glob("*.md"):
        arquivos_processados += 1
        if remover_comentarios_relatorio(str(arquivo)):
            arquivos_alterados += 1
    
    print()
    print(f"📊 Resumo:")
    print(f"   Total de arquivos .md processados: {arquivos_processados}")
    print(f"   Arquivos alterados: {arquivos_alterados}")

if __name__ == "__main__":
    # Processa o diretório de saída
    diretorio = "/Users/nicholasjacob/Downloads/MediaExtractor/Processados"
    
    print("🧹 Removendo comentários de relatório das apostilas...")
    print()
    
    if os.path.exists(diretorio):
        processar_diretorio(diretorio)
    else:
        print(f"❌ Diretório não encontrado: {diretorio}")
    
    print()
    print("✨ Concluído!")
