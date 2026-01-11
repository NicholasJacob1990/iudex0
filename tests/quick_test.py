#!/usr/bin/env python3
"""Quick test - Gemini only"""
import sys
import asyncio
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(override=True)

sys.path.insert(0, str(Path(__file__).parent))
from gemini_formatter import GeminiFormatter

async def main():
    # Carrega amostra
    with open('test_small.txt', 'r') as f:
        text = f.read()
    
    print(f"📊 Teste Gemini - {len(text):,} chars\n")
    
    # Formata
    formatter = GeminiFormatter()
    result = await formatter.format_transcription(text, 'test_small')
    
    # Salva
    Path('test_results').mkdir(exist_ok=True)
    output_file = Path('test_results/gemini_quick_test.md')
    output_file.write_text(result, encoding='utf-8')
    
    # Resumo
    print(f"\n{'='*60}")
    print(f"✅ TESTE COMPLETO")
    print(f"{'='*60}")
    print(f"Tokens: {formatter.metrics['tokens_used']:,}")
    print(f"Custo: ${formatter.metrics['cost_usd']:.4f}")
    print(f"Tempo: {formatter.metrics['duration']:.1f}s")
    print(f"Output: {len(result):,} chars")
    print(f"Arquivo: {output_file}")
    
if __name__ == '__main__':
    asyncio.run(main())
