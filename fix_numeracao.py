#!/usr/bin/env python3
"""
Script para corrigir numeração de títulos H2 no arquivo markdown
"""

import re
import sys

def renumerar_h2(arquivo):
    """Renumera todos os títulos H2 sequencialmente"""
    
    with open(arquivo, 'r', encoding='utf-8') as f:
        conteudo = f.read()
    
    linhas = conteudo.split('\n')
    contador_h2 = 0
    novas_linhas = []
    
    for linha in linhas:
        # Verifica se é um título H2
        if linha.startswith('## '):
            contador_h2 += 1
            
            # Remove numeração existente se houver
            # Padrão: ## 1. Título ou ## Título
            match = re.match(r'^##\s+(\d+\.\s+)?(.+)$', linha)
            if match:
                titulo_sem_numero = match.group(2)
                nova_linha = f"## {contador_h2}. {titulo_sem_numero}"
                novas_linhas.append(nova_linha)
                print(f"✓ H2 #{contador_h2}: {titulo_sem_numero[:60]}...")
            else:
                novas_linhas.append(linha)
        else:
            novas_linhas.append(linha)
    
    # Salva o arquivo corrigido
    novo_conteudo = '\n'.join(novas_linhas)
    
    with open(arquivo, 'w', encoding='utf-8') as f:
        f.write(novo_conteudo)
    
    print(f"\n✅ Arquivo atualizado: {arquivo}")
    print(f"📊 Total de títulos H2 renumerados: {contador_h2}")

if __name__ == "__main__":
    arquivo = "/Users/nicholasjacob/Downloads/MediaExtractor/Processados/Direito_Administrativo_CONSOLIDADO_RAW_FIDELIDADE.md"
    
    print("🔧 Corrigindo numeração de títulos H2...")
    print()
    
    renumerar_h2(arquivo)
