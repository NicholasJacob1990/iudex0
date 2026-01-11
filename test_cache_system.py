#!/usr/bin/env python3
"""
Teste do Sistema de Cache - format_only.py v0.3
Verifica se o cache está funcionando corretamente
"""

import os
import time
import json
from pathlib import Path
from colorama import Fore, init

init(autoreset=True)

def test_cache_system():
    """Testa o sistema de cache integrado"""
    
    print(f"{Fore.CYAN}{'='*60}")
    print(f"{Fore.CYAN}🧪 TESTE DO SISTEMA DE CACHE")
    print(f"{Fore.CYAN}{'='*60}\n")
    
    # Arquivo de teste
    test_file = "/Users/nicholasjacob/Documents/Aplicativos/Iudex/Aulas_PGM_RJ/Urban.txt"
    
    if not os.path.exists(test_file):
        print(f"{Fore.RED}❌ Arquivo de teste não encontrado: {test_file}")
        print(f"{Fore.YELLOW}💡 Crie um arquivo Urban.txt ou ajuste o caminho no script")
        return False
    
    # Caminhos de cache esperados
    cache_formatted = test_file.replace('.txt', '_CACHE_FORMATTED.json')
    cache_summary = test_file.replace('.txt', '_CACHE_SUMMARY.json')
    
    # Teste 1: Verificar se caches existem
    print(f"{Fore.YELLOW}📋 Teste 1: Verificando existência de caches...")
    
    if os.path.exists(cache_formatted):
        print(f"{Fore.GREEN}   ✅ Cache FORMATTED encontrado")
        
        # Valida estrutura
        try:
            with open(cache_formatted, 'r') as f:
                data = json.load(f)
            
            required_fields = ['formatted_text', 'timestamp', 'version', 'original_file', 'model']
            missing = [f for f in required_fields if f not in data]
            
            if missing:
                print(f"{Fore.RED}      ❌ Campos faltando: {missing}")
            else:
                print(f"{Fore.GREEN}      ✅ Todos os campos obrigatórios presentes")
                print(f"{Fore.CYAN}         - Timestamp: {data['timestamp']}")
                print(f"{Fore.CYAN}         - Versão: {data['version']}")
                print(f"{Fore.CYAN}         - Modelo: {data['model']}")
                print(f"{Fore.CYAN}         - Tamanho: {len(data['formatted_text'])} caracteres")
        
        except json.JSONDecodeError:
            print(f"{Fore.RED}      ❌ Cache corrompido (JSON inválido)")
        except Exception as e:
            print(f"{Fore.RED}      ❌ Erro ao validar: {e}")
    else:
        print(f"{Fore.YELLOW}   ⚠️  Cache FORMATTED não encontrado")
        print(f"{Fore.CYAN}      💡 Execute: python format_only.py Urban.txt")
    
    print()
    
    if os.path.exists(cache_summary):
        print(f"{Fore.GREEN}   ✅ Cache SUMMARY encontrado")
        
        try:
            with open(cache_summary, 'r') as f:
                data = json.load(f)
            
            print(f"{Fore.CYAN}         - Timestamp: {data.get('timestamp', 'N/A')}")
            print(f"{Fore.CYAN}         - Tamanho: {len(data.get('formatted_text', ''))} caracteres")
        
        except Exception as e:
            print(f"{Fore.RED}      ❌ Erro ao validar: {e}")
    else:
        print(f"{Fore.YELLOW}   ⚠️  Cache SUMMARY não encontrado")
    
    print()
    
    # Teste 2: Comparar timestamps de arquivo vs cache
    print(f"{Fore.YELLOW}📋 Teste 2: Verificando atualidade do cache...")
    
    if os.path.exists(cache_formatted) and os.path.exists(test_file):
        file_mtime = os.path.getmtime(test_file)
        cache_mtime = os.path.getmtime(cache_formatted)
        
        file_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(file_mtime))
        cache_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(cache_mtime))
        
        print(f"{Fore.CYAN}   📄 Arquivo original modificado: {file_time}")
        print(f"{Fore.CYAN}   💾 Cache criado em: {cache_time}")
        
        if cache_mtime < file_mtime:
            print(f"{Fore.RED}   ⚠️  ATENÇÃO: Cache desatualizado!")
            print(f"{Fore.YELLOW}      💡 Execute novamente para atualizar o cache")
        else:
            print(f"{Fore.GREEN}   ✅ Cache está atualizado")
    
    print()
    
    # Teste 3: Teste de performance (simulado)
    print(f"{Fore.YELLOW}📋 Teste 3: Estimativa de economia de tempo...")
    
    if os.path.exists(cache_formatted):
        with open(cache_formatted, 'r') as f:
            data = json.load(f)
        
        text_length = len(data['formatted_text'])
        
        # Estimativas (baseadas em experiência)
        estimated_processing_time = (text_length / 1000) * 2  # ~2s por 1k chars
        estimated_cache_load_time = 0.5  # Menos de 1 segundo
        
        time_saved = estimated_processing_time - estimated_cache_load_time
        percentage_saved = (time_saved / estimated_processing_time) * 100
        
        print(f"{Fore.CYAN}   📊 Tamanho do texto: {text_length:,} caracteres")
        print(f"{Fore.CYAN}   ⏱️  Tempo estimado SEM cache: {estimated_processing_time:.1f}s")
        print(f"{Fore.CYAN}   ⚡ Tempo estimado COM cache: {estimated_cache_load_time:.1f}s")
        print(f"{Fore.GREEN}   💰 Economia estimada: {time_saved:.1f}s ({percentage_saved:.0f}%)")
    
    print()
    
    # Resultado final
    print(f"{Fore.CYAN}{'='*60}")
    
    both_exist = os.path.exists(cache_formatted) and os.path.exists(cache_summary)
    
    if both_exist:
        print(f"{Fore.GREEN}✅ TESTE COMPLETO: Sistema de cache operacional")
        print(f"{Fore.GREEN}   Ambos os caches (FORMATTED e SUMMARY) foram encontrados")
        return True
    else:
        print(f"{Fore.YELLOW}⚠️  TESTE PARCIAL: Nem todos os caches existem")
        print(f"{Fore.CYAN}   Execute 'python format_only.py Urban.txt' para criar os caches")
        return False

if __name__ == "__main__":
    success = test_cache_system()
    exit(0 if success else 1)
