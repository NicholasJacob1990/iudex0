"""
Test Runner - Orchestrates comparison of all three formatting strategies
Usage: python test_runner.py <transcription_file>
"""
import sys
import os
import asyncio
from pathlib import Path
from colorama import Fore, Style, init

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from gemini_formatter import GeminiFormatter
from claude_formatter import ClaudeFormatter
from hybrid_formatter import HybridFormatter
from test_utils import save_comparison_report

init(autoreset=True)

async def run_formatter(formatter, transcription, video_name, output_dir):
    """
    Roda um formatter e retorna métricas + outputs.
    """
    try:
        print(f"\n{'='*70}")
        print(f"{Fore.BLUE}▶ Testando: {formatter.model_name}")
        print(f"{'='*70}")
        
        # Formata
        formatted_output = await formatter.format_transcription(transcription, video_name)
        
        # Validação Heurística
        print(f"\n{Fore.YELLOW}🔍 Validação heurística...")
        h_passed, h_issues = formatter._validate_preservation_heuristics(transcription, formatted_output)
        
        if h_passed:
            print(f"{Fore.GREEN}   ✓ Passou ({len(h_issues)} issues)")
        else:
            print(f"{Fore.RED}   ✗ Falhou ({len(h_issues)} issues)")
        
        # Salva output
        safe_name = formatter.model_name.replace(" ", "_").replace("/", "-")
        output_file = output_dir / f"output_{safe_name}.md"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(formatted_output)
        
        print(f"{Fore.GREEN}   💾 Salvo: {output_file.name}")
        
        # Gera audit report
        audit_content = formatter._generate_audit_report(video_name, h_issues, [])
        audit_file = output_dir / f"audit_{safe_name}.md"
        
        with open(audit_file, 'w', encoding='utf-8') as f:
            f.write(audit_content)
        
        print(f"{Fore.GREEN}   📋 Audit: {audit_file.name}")
        
        # Retorna dados para comparação
        return {
            "output": formatted_output,
            "tokens": formatter.metrics['tokens_used'],
            "cost": formatter.metrics['cost_usd'],
            "duration": formatter.metrics.get('duration', 0),
            "api_calls": formatter.metrics['api_calls'],
            "heuristic_passed": h_passed,
            "heuristic_issues": h_issues,
            "llm_issues": [],  # Simplificado para teste
            "claude_percentage": formatter.metrics.get('claude_percentage', 0 if 'Gemini' in formatter.model_name else 100)
        }
        
    except Exception as e:
        print(f"{Fore.RED}❌ ERRO em {formatter.model_name}: {e}")
        import traceback
        traceback.print_exc()
        return None

async def main():
    """Main test orchestration"""
    
    if len(sys.argv) < 2:
        print(f"{Fore.RED}❌ Uso: python test_runner.py <arquivo_transcricao.txt>")
        print(f"\n{Fore.YELLOW}Exemplo:")
        print(f"   python test_runner.py ../Aulas_PGM_RJ/04_Ubanistico_constitucional.txt")
        sys.exit(1)
    
    transcription_path = Path(sys.argv[1])
    
    if not transcription_path.exists():
        print(f"{Fore.RED}❌ Arquivo não encontrado: {transcription_path}")
        sys.exit(1)
    
    # Carrega transcrição
    print(f"{Fore.CYAN}📂 Carregando: {transcription_path.name}")
    with open(transcription_path, 'r', encoding='utf-8') as f:
        transcription = f.read()
    
    print(f"   Tamanho: {len(transcription):,} caracteres")
    print(f"   Palavras: {len(transcription.split()):,}")
    
    video_name = transcription_path.stem
    
    # Cria diretório de outputs
    output_dir = Path(__file__).parent / "test_results"
    output_dir.mkdir(exist_ok=True)
    
    print(f"   Outputs: {output_dir}/")
    
    # Inicializa formatters
    print(f"\n{Fore.MAGENTA}{'='*70}")
    print(f"🚀 Inicializando Formatters...")
    print(f"{'='*70}")
    
    formatters = {
        "Gemini 2.5 Flash": GeminiFormatter(),
        "Claude Sonnet 4.5": ClaudeFormatter(),
        "Híbrido": HybridFormatter()
    }
    
    # Roda testes
    results = {}
    
    for name, formatter in formatters.items():
        result = await run_formatter(formatter, transcription, video_name, output_dir)
        if result:
            results[name] = result
        
        # Delay entre testes para evitar rate limits
        if name != list(formatters.keys())[-1]:  # Se não for o último
            print(f"\n{Fore.YELLOW}⏳ Aguardando 10s antes do próximo teste...")
            await asyncio.sleep(10)
    
    # Gera relatório comparativo
    print(f"\n{Fore.MAGENTA}{'='*70}")
    print(f"📊 Gerando Relatório Comparativo...")
    print(f"{'='*70}")
    
    comparison_data = {
        "video_name": video_name,
        "strategies": results
    }
    
    report_path = save_comparison_report(comparison_data, str(output_dir / "comparison_report.md"))
    
    print(f"{Fore.GREEN}✓ Relatório salvo: {Path(report_path).name}")
    
    # Sumário final
    print(f"\n{Fore.CYAN}{'='*70}")
    print(f"📈 RESUMO FINAL")
    print(f"{'='*70}\n")
    
    for name, data in results.items():
        status_emoji = "✅" if data['heuristic_passed'] else "⚠️"
        print(f"{status_emoji} {name:20} | ${data['cost']:.4f} | {data['duration']:.0f}s | {len(data['output']):,} chars")
    
    print(f"\n{Fore.GREEN}{'='*70}")
    print(f"✅ TESTE CONCLUÍDO!")
    print(f"{'='*70}")
    print(f"{Fore.YELLOW}📁 Veja os resultados em: {output_dir}/")
    print(f"   - output_*.md (textos formatados)")
    print(f"   - audit_*.md (relatórios de validação)")
    print(f"   - comparison_report.md (comparação completa)")

if __name__ == "__main__":
    # Verifica .env
    from dotenv import load_dotenv
    load_dotenv(override=True)
    
    if not os.getenv("OPENROUTER_API_KEY"):
        print(f"{Fore.RED}❌ OPENROUTER_API_KEY não configurada!")
        print(f"\n{Fore.YELLOW}Configure primeiro:")
        print(f"   1. Crie conta em: https://openrouter.ai/")
        print(f"   2. Copie sua API key")
        print(f"   3. Crie arquivo .env:")
        print(f"      OPENROUTER_API_KEY=sk-or-v1-...")
        sys.exit(1)
    
    asyncio.run(main())
