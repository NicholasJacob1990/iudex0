#!/usr/bin/env python3
"""
Benchmark para comparar performance de transcrição
Fase 2: Testes Experimentais - Lightning-Whisper-MLX vs MLX-Whisper

Métricas:
- RTF (Real-Time Factor)
- Preservação de referências legais
- Taxa de alucinações
"""

import time
import re
import json
from pathlib import Path
from typing import Dict, List
import os
import sys

# Tentar importar mlx_whisper
try:
    import mlx_whisper
    HAS_MLX = True
except ImportError:
    HAS_MLX = False
    print("⚠️ mlx_whisper não instalado")

# Tentar importar lightning_whisper_mlx
try:
    from lightning_whisper_mlx import LightningWhisperMLX
    HAS_LIGHTNING = True
except ImportError:
    HAS_LIGHTNING = False
    print("⚠️ lightning-whisper-mlx não instalado (pip install lightning-whisper-mlx)")


class TranscriptionBenchmark:
    """Benchmark comparativo de bibliotecas Whisper"""
    
    def __init__(self, audio_path: str, model_size: str = "large-v3-turbo"):
        self.audio_path = audio_path
        self.model_size = model_size
        
        if not Path(audio_path).exists():
            raise FileNotFoundError(f"Áudio não encontrado: {audio_path}")
        
        # Obter duração do áudio (via ffprobe)
        self.audio_duration = self._get_audio_duration()
    
    def _get_audio_duration(self) -> float:
        """Obtém duração do áudio em segundos usando ffprobe"""
        import subprocess
        try:
            cmd = [
                'ffprobe', '-v', 'error', '-show_entries',
                'format=duration', '-of', 'json', self.audio_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            data = json.loads(result.stdout)
            return float(data['format']['duration'])
        except Exception as e:
            print(f"⚠️ Erro ao obter duração: {e}")
            return 0.0
    
    def test_mlx_whisper_baseline(self) -> Dict:
        """Baseline: MLX-Whisper SEM batching (código antigo)"""
        if not HAS_MLX:
            return None
        
        print("\n🔬 Testando MLX-Whisper BASELINE (sem batching)...")
        start = time.time()
        
        try:
            result = mlx_whisper.transcribe(
                self.audio_path,
                path_or_hf_repo=f"mlx-community/whisper-{self.model_size}",
                language="pt",
                word_timestamps=True,
                fp16=True,
                no_speech_threshold=0.6,
                logprob_threshold=-1.0,
                compression_ratio_threshold=2.4,
                condition_on_previous_text=True,
                suppress_tokens=[-1],
                verbose=False
            )
            
            elapsed = time.time() - start
            rtf = elapsed / self.audio_duration if self.audio_duration > 0 else 0
            
            text = result.get('text', '') if isinstance(result, dict) else str(result)
            
            print(f"   ✅ Concluído em {elapsed:.1f}s (RTF: {rtf:.2f}x)")
            
            return {
                'library': 'mlx_whisper_baseline',
                'elapsed_time': elapsed,
                'rtf': rtf,
                'text': text,
                'success': True
            }
        except Exception as e:
            print(f"   ❌ Erro: {e}")
            return {'library': 'mlx_whisper_baseline', 'success': False, 'error': str(e)}
    
    def test_mlx_whisper_batched(self) -> Dict:
        """MLX-Whisper COM batching (Fase 1.1)"""
        if not HAS_MLX:
            return None
        
        print("\n🔬 Testando MLX-Whisper BATCHED (Fase 1.1)...")
        start = time.time()
        
        try:
            result = mlx_whisper.transcribe(
                self.audio_path,
                path_or_hf_repo=f"mlx-community/whisper-{self.model_size}",
                language="pt",
                
                # FASE 1.1: Batching
                chunk_length=30,
                batch_size=8,
                
                # FASE 1.2: Precisão
                temperature=0.0,
                beam_size=5,
                initial_prompt="Esta é uma transcrição de aula jurídica em português brasileiro.",
                
                # Parâmetros existentes
                word_timestamps=True,
                fp16=True,
                no_speech_threshold=0.6,
                logprob_threshold=-1.0,
                compression_ratio_threshold=2.4,
                condition_on_previous_text=True,
                suppress_tokens=[-1],
                verbose=False
            )
            
            elapsed = time.time() - start
            rtf = elapsed / self.audio_duration if self.audio_duration > 0 else 0
            
            text = result.get('text', '') if isinstance(result, dict) else str(result)
            
            print(f"   ✅ Concluído em {elapsed:.1f}s (RTF: {rtf:.2f}x)")
            
            return {
                'library': 'mlx_whisper_batched',
                'elapsed_time': elapsed,
                'rtf': rtf,
                'text': text,
                'success': True
            }
        except Exception as e:
            print(f"   ❌ Erro: {e}")
            return {'library': 'mlx_whisper_batched', 'success': False, 'error': str(e)}
    
    def test_lightning_whisper_mlx(self) -> Dict:
        """Lightning-Whisper-MLX (4x speedup claim)"""
        if not HAS_LIGHTNING:
            print("\n⚠️ Lightning-Whisper-MLX não disponível")
            return None
        
        print("\n🔬 Testando Lightning-Whisper-MLX...")
        start = time.time()
        
        try:
            model = LightningWhisperMLX(
                model=self.model_size,
                batch_size=12,
                quant=None
            )
            
            result = model.transcribe(self.audio_path)
            
            elapsed = time.time() - start
            rtf = elapsed / self.audio_duration if self.audio_duration > 0 else 0
            
            text = result.get('text', '') if isinstance(result, dict) else str(result)
            
            print(f"   ✅ Concluído em {elapsed:.1f}s (RTF: {rtf:.2f}x)")
            
            return {
                'library': 'lightning_whisper_mlx',
                'elapsed_time': elapsed,
                'rtf': rtf,
                'text': text,
                'success': True
            }
        except Exception as e:
            print(f"   ❌ Erro: {e}")
            return {'library': 'lightning_whisper_mlx', 'success': False, 'error': str(e)}
    
    def compute_metrics(self, result: Dict) -> Dict:
        """Calcula métricas jurídicas específicas"""
        if not result or not result.get('success'):
            return None
        
        text = result['text']
        
        # Taxa de preservação de artigos de lei
        legal_refs = re.findall(r'Art\.?\s*\d+', text, re.IGNORECASE)
        
        # Taxa de preservação de súmulas
        sumulas = re.findall(r'Súmula\s*\d+', text, re.IGNORECASE)
        
        # Taxa de preservação de leis
        leis = re.findall(r'Lei\s*n?º?\s*\d+', text, re.IGNORECASE)
        
        # Detecção de alucinações (padrões repetitivos)
        paragraphs = text.split('\n\n')
        hallucinations = 0
        for i in range(len(paragraphs) - 1):
            if paragraphs[i] and paragraphs[i] == paragraphs[i+1]:
                hallucinations += 1
        
        return {
            'library': result['library'],
            'elapsed_time': result['elapsed_time'],
            'rtf': result['rtf'],
            'legal_refs_count': len(legal_refs),
            'sumulas_count': len(sumulas),
            'leis_count': len(leis),
            'hallucination_count': hallucinations,
            'text_length': len(text)
        }
    
    def run_all_tests(self) -> List[Dict]:
        """Executa todos os testes disponíveis"""
        print(f"\n{'='*60}")
        print(f"📊 BENCHMARK DE TRANSCRIÇÃO")
        print(f"{'='*60}")
        print(f"Áudio: {self.audio_path}")
        print(f"Duração: {self.audio_duration:.1f}s ({self.audio_duration/60:.1f} min)")
        print(f"Modelo: {self.model_size}")
        print(f"{'='*60}")
        
        results = []
        
        # Teste 1: Baseline (sem batching)
        baseline = self.test_mlx_whisper_baseline()
        if baseline:
            results.append(self.compute_metrics(baseline))
        
        # Teste 2: Batched (Fase 1)
        batched = self.test_mlx_whisper_batched()
        if batched:
            results.append(self.compute_metrics(batched))
        
        # Teste 3: Lightning
        lightning = self.test_lightning_whisper_mlx()
        if lightning:
            results.append(self.compute_metrics(lightning))
        
        return results
    
    def print_comparison(self, results: List[Dict]):
        """Imprime comparação detalhada"""
        print(f"\n{'='*60}")
        print(f"📈 RESULTADOS COMPARATIVOS")
        print(f"{'='*60}\n")
        
        if not results:
            print("❌ Nenhum resultado válido")
            return
        
        # Tabela de velocidade
        print("⚡ VELOCIDADE:")
        print(f"{'Biblioteca':<30} {'Tempo':<12} {'RTF':<10} {'Ganho':<10}")
        print("-" * 62)
        
        baseline_time = None
        for r in results:
            if r['library'] == 'mlx_whisper_baseline':
                baseline_time = r['elapsed_time']
                break
        
        for r in results:
            speedup = ""
            if baseline_time and r['elapsed_time'] > 0:
                speedup = f"{baseline_time / r['elapsed_time']:.2f}x"
            
            print(f"{r['library']:<30} {r['elapsed_time']:>8.1f}s   {r['rtf']:>6.2f}x   {speedup:<10}")
        
        # Tabela de precisão jurídica
        print(f"\n📚 PRECISÃO JURÍDICA:")
        print(f"{'Biblioteca':<30} {'Artigos':<10} {'Súmulas':<10} {'Leis':<10}")
        print("-" * 60)
        
        for r in results:
            print(f"{r['library']:<30} {r['legal_refs_count']:>6}     {r['sumulas_count']:>6}     {r['leis_count']:>6}")
        
        # Tabela de qualidade
        print(f"\n✨ QUALIDADE:")
        print(f"{'Biblioteca':<30} {'Alucinações':<15} {'Texto (chars)':<15}")
        print("-" * 60)
        
        for r in results:
            print(f"{r['library']:<30} {r['hallucination_count']:>10}      {r['text_length']:>10}")
        
        print(f"\n{'='*60}\n")
    
    def should_migrate_to_lightning(self, results: List[Dict]) -> bool:
        """Decisão automatizada: migrar para Lightning?"""
        baseline = None
        lightning = None
        
        for r in results:
            if r['library'] == 'mlx_whisper_batched':
                baseline = r
            elif r['library'] == 'lightning_whisper_mlx':
                lightning = r
        
        if not baseline or not lightning:
            return False
        
        # Critérios objetivos
        criteria = {
            'speed': lightning['rtf'] <= baseline['rtf'] * 0.5,  # 2x mais rápido
            'legal_refs': lightning['legal_refs_count'] >= baseline['legal_refs_count'] * 0.95,  # 95% preservação
            'quality': lightning['hallucination_count'] <= baseline['hallucination_count'] * 1.1  # Max 10% mais alucinações
        }
        
        print("\n🎯 DECISÃO DE MIGRAÇÃO:")
        print(f"  ✓ Velocidade (≥2x): {'SIM ✅' if criteria['speed'] else 'NÃO ❌'}")
        print(f"  ✓ Refs legais (≥95%): {'SIM ✅' if criteria['legal_refs'] else 'NÃO ❌'}")
        print(f"  ✓ Qualidade: {'SIM ✅' if criteria['quality'] else 'NÃO ❌'}")
        
        migrate = all(criteria.values())
        print(f"\n{'✅ RECOMENDADO migrar para Lightning' if migrate else '❌ MANTER MLX-Whisper com batching'}\n")
        
        return migrate


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Benchmark de transcrição Whisper")
    parser.add_argument('audio', help="Caminho do áudio de teste")
    parser.add_argument('--model', default='large-v3-turbo', help="Modelo Whisper")
    parser.add_argument('--runs', type=int, default=1, help="Número de execuções")
    
    args = parser.parse_args()
    
    benchmark = TranscriptionBenchmark(args.audio, args.model)
    
    all_results = []
    for run in range(args.runs):
        if args.runs > 1:
            print(f"\n{'='*60}")
            print(f"RUN {run + 1}/{args.runs}")
            print(f"{'='*60}")
        
        results = benchmark.run_all_tests()
        all_results.extend(results)
    
    # Média dos resultados se múltiplos runs
    if args.runs > 1:
        # Agregar por biblioteca
        aggregated = {}
        for r in all_results:
            lib = r['library']
            if lib not in aggregated:
                aggregated[lib] = {'count': 0, **{k: 0 for k in r.keys() if k != 'library'}}
            
            aggregated[lib]['count'] += 1
            for k, v in r.items():
                if k != 'library' and isinstance(v, (int, float)):
                    aggregated[lib][k] += v
        
        # Calcular médias
        final_results = []
        for lib, data in aggregated.items():
            count = data['count']
            final_results.append({
                'library': lib,
                **{k: v / count for k, v in data.items() if k not in ['library', 'count']}
            })
        
        benchmark.print_comparison(final_results)
        benchmark.should_migrate_to_lightning(final_results)
    else:
        benchmark.print_comparison(results)
        benchmark.should_migrate_to_lightning(results)


if __name__ == "__main__":
    main()
