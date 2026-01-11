"""
Hybrid Formatter - Intelig SmartRouting: Gemini + Claude
Otimização de custo-qualidade
"""
import os
import re
import asyncio
from openai import AsyncOpenAI
from colorama import Fore
from base_formatter import BaseFormatter

class HybridFormatter(BaseFormatter):
    """Formatador híbrido: Gemini para conteúdo simples, Claude para crítico"""
    
    def __init__(self):
        super().__init__(model_name="Híbrido (Gemini + Claude)")
        
        from dotenv import load_dotenv
        load_dotenv(override=True)
        
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError(f"{Fore.RED}❌ OPENROUTER_API_KEY não configurada")
        
        self.client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            default_headers={
                "HTTP-Referer": "https://github.com/vomo-app",
                "X-Title": "Vomo Legal Transcriber - Hybrid Test"
            }
        )
        
        self.MODEL_GEMINI = "google/gemini-2.5-flash"
        self.MODEL_CLAUDE = "anthropic/claude-sonnet-4.5"
        
        self.metrics['claude_chunks'] = 0
        self.metrics['gemini_chunks'] = 0
        
        print(f"{Fore.GREEN}✓ HybridFormatter inicializado")
    
    async def format_transcription(self, transcription, video_name):
        """Formata transcrição usando estratégia Híbrida com escrita incremental"""
        self.metrics['start_time'] = asyncio.get_event_loop().time()
        
        print(f"\n{Fore.CYAN}🧠 Formatando com Estratégia Híbrida...")
        print(f"   Tamanho: {len(transcription):,} chars")
        
        # Chunking
        chunks = self._smart_chunk_overlapping(transcription, max_size=25000, overlap=3000)
        print(f"   Chunks: {len(chunks)}")
        
        # System prompt
        system_prompt = self._get_system_prompt()
        
        # Arquivo temporário
        temp_file = f"temp_hybrid_{video_name}.md"
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write(f"# {video_name}\n\n")
            
        full_content = f"# {video_name}\n\n"
        
        # Processa chunks sequencialmente
        import gc
        for i, chunk in enumerate(chunks):
            print(f"   [{i+1:02d}/{len(chunks)}] Processando...")
            
            # Roteamento inteligente
            result = await self._format_chunk_smart(chunk, i, system_prompt)
            
            with open(temp_file, 'a', encoding='utf-8') as f:
                f.write(result + "\n\n")
            
            full_content += result + "\n\n"
            
            del result
            gc.collect()
            
        # Calcula % Claude
        total_chunks = self.metrics['claude_chunks'] + self.metrics['gemini_chunks']
        if total_chunks > 0:
            self.metrics['claude_percentage'] = (self.metrics['claude_chunks'] / total_chunks) * 100
            
        self.metrics['end_time'] = asyncio.get_event_loop().time()
        self.metrics['duration'] = self.metrics['end_time'] - self.metrics['start_time']
        
        print(f"{Fore.GREEN}✓ Formatação concluída em {self.metrics['duration']:.1f}s")
        print(f"   Distribuição: {self.metrics['claude_chunks']} Claude | {self.metrics['gemini_chunks']} Gemini")
        
        return full_content
    
    async def _format_chunk_smart(self, chunk, chunk_idx, system_prompt):
        """Decide qual modelo usar baseado na críticidade do chunk"""
        
        # Calcula scores
        criticality_score = self._calculate_criticality(chunk)
        is_narrative = self._is_narrative(chunk)
        
        # Decisão de roteamento
        if criticality_score >= 20:
            model = self.MODEL_CLAUDE
            reason = "CRÍTICO (leis/dicas)"
            color = Fore.MAGENTA
            self.metrics['claude_chunks'] += 1
            model_key = "claude-sonnet-4.5"
        elif is_narrative:
            model = self.MODEL_CLAUDE
            reason = "NARRATIVO (fluidez)"
            color = Fore.MAGENTA
            self.metrics['claude_chunks'] += 1
            model_key = "claude-sonnet-4.5"
        else:
            model = self.MODEL_GEMINI
            reason = "EXPOSITIVO"
            color = Fore.CYAN
            self.metrics['gemini_chunks'] += 1
            model_key = "gemini-2.5-flash"
        
        print(f"{color}   [{chunk_idx+1:02d}] {model.split('/')[-1]:<25} | {reason}")
        
        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"[PARTE {chunk_idx+1}]\n\n{chunk}"}
                ],
                temperature=0.1,
                extra_body={
                    "top_p": 0.9
                }
            )
            
            self.metrics['api_calls'] += 1
            self.metrics['tokens_used'] += response.usage.total_tokens
            
            # Atualiza custo
            from test_utils import TestMetrics
            self.metrics['cost_usd'] += TestMetrics.calculate_cost(
                model_key,
                response.usage.prompt_tokens,
                response.usage.completion_tokens
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            print(f"{Fore.RED}❌ Erro no chunk {chunk_idx}: {e}")
            return f"[ERRO NO PROCESSAMENTO DO CHUNK {chunk_idx}]"
    
    async def _format_chunk_async(self, chunk, chunk_idx, system_prompt):
        """Wrapper para compatibilidade com BaseFormatter"""
        return await self._format_chunk_smart(chunk, chunk_idx, system_prompt)
    
    def _calculate_criticality(self, text):
        """
        Calcula score de criticidade (0-100).
        Quanto maior, mais importante usar Claude.
        """
        score = 0
        
        # Padrões críticos
        critical_patterns = [
            (r'Art\.\s*\d+', 5),                    # Artigo de lei
            (r'Lei nº\s*[\d.]+', 5),                # Legislação
            (r'Súmula\s+\d+', 8),                   # Jurisprudência
            (r'STF|STJ|TST|TSE', 6),                # Tribunais
            (r'CF/\d{2}', 4),                       # Constituição
            (r'divergência|corrente|entendimento', 3),  # Doutrina complexa
            (r'cai muito|atenção|pegadinha|importante', 7),  # Dicas de prova
            (r'exceção|regra|ressalva', 2),         # Nuances técnicas
            (r'professor\s+[A-Z]', 2),              # Autores
        ]
        
        for pattern, weight in critical_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            score += len(matches) * weight
        
        return min(score, 100)  # Cap at 100
    
    def _is_narrative(self, text):
        """
        Detecta se chunk é narrativo (exemplos, histórias).
        Narrativas precisam de escrita natural = Claude.
        """
        narrative_markers = [
            r'exemplo|vamos imaginar|caso|história',
            r'contextualizando|na prática|imagine',
            r'professor conta|relato|experiência',
            r'vou contar|aconteceu|situação',
            r'por exemplo|como no caso',
        ]
        
        score = 0
        for pattern in narrative_markers:
            score += len(re.findall(pattern, text, re.IGNORECASE))
        
        # Chunk é narrativo se tiver 3+ marcadores
        return score >= 3
    
    def _get_system_prompt(self):
        """Retorna o system prompt completo do format_only.py"""
        from prompts import get_complete_system_prompt
        return get_complete_system_prompt()
