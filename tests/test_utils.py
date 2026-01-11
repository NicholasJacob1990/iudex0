"""
Test Utilities - Helper functions for metrics and comparison
"""
import json
import time
from typing import Dict, Any

class TestMetrics:
    """Collects and calculates test metrics"""
    
    # Pricing per 1M tokens (USD)
    PRICING = {
        "gemini-2.5-flash": {"input": 0.15, "output": 0.60},  # $0.30 average
        "claude-sonnet-4.5": {"input": 3.00, "output": 15.00},  # $3.00 average  
        "gpt-5-mini": {"input": 0.15, "output": 0.60},  # $0.30 average
    }
    
    @staticmethod
    def calculate_cost(model_key: str, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost in USD based on token usage"""
        if model_key not in TestMetrics.PRICING:
            return 0.0
        
        pricing = TestMetrics.PRICING[model_key]
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        
        return input_cost + output_cost
    
    @staticmethod
    def format_duration(seconds: float) -> str:
        """Format duration in human-readable format"""
        if seconds < 60:
            return f"{seconds:.1f}s"
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes}m {secs:.0f}s"
    
    @staticmethod
    def compare_outputs(output_a: str, output_b: str) -> Dict[str, Any]:
        """Compare two formatted outputs"""
        return {
            "length_diff": len(output_b) - len(output_a),
            "length_ratio": len(output_b) / max(len(output_a), 1),
            "word_count_a": len(output_a.split()),
            "word_count_b": len(output_b.split()),
        }

def save_comparison_report(results: Dict[str, Any], output_path: str):
    """Generate and save comparison report in Markdown"""
    
    report = f"""# 🔬 Comparação de Estratégias LLM
**Data:** {time.strftime("%Y-%m-%d %H:%M:%S")}
**Transcrição:** {results['video_name']}

## 📊 Métricas Gerais

| Estratégia | Tokens | Custo (USD) | Tempo | Tamanho Saída |
|------------|--------|-------------|-------|---------------|
"""
    
    for strategy_name, data in results['strategies'].items():
        report += f"| **{strategy_name}** | {data['tokens']:,} | ${data['cost']:.4f} | {TestMetrics.format_duration(data['duration'])} | {len(data['output']):,} chars |\n"
    
    report += "\n## 🎯 Qualidade (Validação Heurística)\n\n"
    
    for strategy_name, data in results['strategies'].items():
        report += f"### {strategy_name}\n"
        if data['heuristic_passed']:
            report += "✅ **PASSOU** - Nenhuma anomalia\n\n"
        else:
            report += f"❌ **{len(data['heuristic_issues'])} problemas detectados:**\n"
            for issue in data['heuristic_issues']:
                report += f"- {issue}\n"
            report += "\n"
    
    report += "## 🤖 Validação LLM\n\n"
    
    for strategy_name, data in results['strategies'].items():
        report += f"### {strategy_name}\n"
        if not data['llm_issues']:
            report += "✅ Sem omissões detectadas\n\n"
        else:
            report += f"⚠️ **{len(data['llm_issues'])} omissões:**\n"
            for issue in data['llm_issues'][:5]:  # Top 5
                report += f"- {issue}\n"
            report += "\n"
    
    # Hybrid-specific metrics
    if 'Híbrido' in results['strategies']:
        hybrid_data = results['strategies']['Híbrido']
        if 'claude_percentage' in hybrid_data:
            report += f"\n### Distribuição Híbrida\n"
            report += f"- **Claude:** {hybrid_data['claude_percentage']:.1f}% dos chunks\n"
            report += f"- **Gemini:** {100 - hybrid_data['claude_percentage']:.1f}% dos chunks\n\n"
    
    report += "\n## 💡 Recomendação\n\n"
    
    # Simple recommendation logic
    cheapest = min(results['strategies'].items(), key=lambda x: x[1]['cost'])
    best_quality = min(results['strategies'].items(), key=lambda x: len(x[1]['heuristic_issues']))
    
    report += f"- **Melhor Custo-Benefício:** {cheapest[0]} (${cheapest[1]['cost']:.4f})\n"
    report += f"- **Melhor Qualidade:** {best_quality[0]} ({len(best_quality[1]['heuristic_issues'])} issues)\n"
    
    report += "\n---\n_Relatório gerado automaticamente_\n"
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report)
    
    return output_path
