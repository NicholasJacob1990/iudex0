"""
Claude Sonnet 4.5 Formatter - 100% Claude via OpenRouter
Baseline de qualidade
"""
import os
import asyncio
from openai import AsyncOpenAI
from colorama import Fore
from base_formatter import BaseFormatter

class ClaudeFormatter(BaseFormatter):
    """Formatador usando 100% Claude Sonnet 4.5"""
    
    def __init__(self):
        super().__init__(model_name="Claude Sonnet 4.5")
        
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
                "X-Title": "Vomo Legal Transcriber - Claude Test"
            }
        )
        
        self.model_id = "anthropic/claude-sonnet-4.5"
        
        print(f"{Fore.GREEN}✓ ClaudeFormatter inicializado")
    
    async def format_transcription(self, transcription, video_name):
        """Formata transcrição usando 100% Claude com escrita incremental"""
        self.metrics['start_time'] = asyncio.get_event_loop().time()
        
        print(f"\n{Fore.CYAN}🧠 Formatando com Claude Sonnet 4.5...")
        print(f"   Tamanho: {len(transcription):,} chars")
        
        # Chunking
        chunks = self._smart_chunk_overlapping(transcription, max_size=25000, overlap=3000)
        print(f"   Chunks: {len(chunks)}")
        
        # System prompt
        system_prompt = self._get_system_prompt()
        
        # Arquivo temporário
        temp_file = f"temp_claude_{video_name}.md"
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write(f"# {video_name}\n\n")
            
        full_content = f"# {video_name}\n\n"
        
        # Processa chunks sequencialmente
        import gc
        for i, chunk in enumerate(chunks):
            print(f"   [{i+1:02d}/{len(chunks)}] Processando...")
            
            result = await self._format_chunk_async(chunk, i, system_prompt)
            
            with open(temp_file, 'a', encoding='utf-8') as f:
                f.write(result + "\n\n")
            
            full_content += result + "\n\n"
            
            del result
            gc.collect()
            
        self.metrics['end_time'] = asyncio.get_event_loop().time()
        self.metrics['duration'] = self.metrics['end_time'] - self.metrics['start_time']
        
        print(f"{Fore.GREEN}✓ Formatação concluída em {self.metrics['duration']:.1f}s")
        
        return full_content
    
    async def _format_chunk_async(self, chunk, chunk_idx, system_prompt):
        """Formata um chunk usando Claude"""
        print(f"   [{chunk_idx+1:02d}] Claude processando...")
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model_id,
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
                "claude-sonnet-4.5",
                response.usage.prompt_tokens,
                response.usage.completion_tokens
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            print(f"{Fore.RED}❌ Erro no chunk {chunk_idx}: {e}")
            return f"[ERRO NO PROCESSAMENTO DO CHUNK {chunk_idx}]"
    
    def _get_system_prompt(self):
        """Retorna o system prompt completo do format_only.py"""
        from prompts import get_complete_system_prompt
        return get_complete_system_prompt()
