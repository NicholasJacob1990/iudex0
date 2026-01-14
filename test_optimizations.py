#!/usr/bin/env python3
"""
Script de teste rápido para validar otimizações Fase 1 + 2.2
Uso: python test_optimizations.py <audio_ou_video>
"""

import os
import sys
import time
from pathlib import Path
import pytest

def test_quick():
    """Teste rápido das otimizações implementadas"""

    if "PYTEST_CURRENT_TEST" in os.environ:
        pytest.skip("Teste requer arquivo de áudio e dependências externas.")

    if len(sys.argv) < 2:
        print("❌ Uso: python test_optimizations.py <audio_ou_video>")
        print("\nExemplo:")
        print("  python test_optimizations.py aula_teste.mp3")
        sys.exit(1)
    
    input_file = sys.argv[1]
    
    if not Path(input_file).exists():
        print(f"❌ Arquivo não encontrado: {input_file}")
        sys.exit(1)
    
    print("="*70)
    print("🧪 TESTE DE VALIDAÇÃO - OTIMIZAÇÕES FASE 1 + 2.2")
    print("="*70)
    print(f"\n📁 Arquivo: {input_file}")
    
    # Importar VomoMLX
    try:
        from mlx_vomo import VomoMLX
    except ImportError as e:
        print(f"❌ Erro ao importar mlx_vomo: {e}")
        sys.exit(1)
    
    # Verificar intervaltree
    try:
        from intervaltree import IntervalTree
        print("✅ intervaltree instalado - usando otimização O(log n)")
        has_intervaltree = True
    except ImportError:
        print("⚠️ intervaltree NÃO instalado - usando fallback O(n)")
        has_intervaltree = False
    
    # Verificar mlx_whisper
    try:
        import mlx_whisper
        print("✅ mlx_whisper disponível")
    except ImportError:
        print("❌ mlx_whisper não instalado")
        sys.exit(1)
    
    print("\n" + "="*70)
    print("🚀 INICIANDO TRANSCRIÇÃO COM OTIMIZAÇÕES")
    print("="*70)
    print("\n✨ Otimizações ativas:")
    print("  • Batching: chunk_length=30, batch_size=8 (3-5x speedup)")
    print("  • Precisão: temperature=0.0, beam_size=5 (+2-3% accuracy)")
    print(f"  • IntervalTree: {'SIM' if has_intervaltree else 'NÃO'} (10-20x alinhamento)")
    
    # Inicializar VomoMLX
    vomo = VomoMLX(model_size="large-v3-turbo")
    
    # Otimizar áudio
    print("\n⚡ Otimizando áudio...")
    audio_path = vomo.optimize_audio(input_file)
    
    # Timing da transcrição
    print("\n🎙️ Transcrevendo...")
    start_time = time.time()
    
    try:
        transcript = vomo.transcribe(audio_path)
        elapsed = time.time() - start_time
        
        print(f"\n✅ TRANSCRIÇÃO CONCLUÍDA EM {elapsed:.1f}s")
        
        # Estatísticas básicas
        lines = transcript.split('\n')
        speakers = [l for l in lines if l.strip().startswith('SPEAKER')]
        
        print("\n📊 ESTATÍSTICAS:")
        print(f"  • Tempo total: {elapsed:.1f}s")
        print(f"  • Linhas geradas: {len(lines)}")
        print(f"  • Speakers detectados: {len(set(speakers))}")
        
        # Amostra do resultado
        print("\n📝 AMOSTRA (primeiras 500 chars):")
        print("-" * 70)
        print(transcript[:500])
        print("-" * 70)
        
        # Salvar resultado
        output_file = Path(input_file).stem + "_OTIMIZADO.txt"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(transcript)
        
        print(f"\n💾 Resultado salvo em: {output_file}")
        
        print("\n" + "="*70)
        print("✅ TESTE CONCLUÍDO COM SUCESSO!")
        print("="*70)
        
    except Exception as e:
        print(f"\n❌ ERRO durante transcrição: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    test_quick()
