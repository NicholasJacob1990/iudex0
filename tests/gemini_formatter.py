"""
Gemini 2.5 Flash Formatter - 100% Gemini via OpenRouter
Baseline de economia
"""
import os
import asyncio
from openai import AsyncOpenAI
from colorama import Fore
from base_formatter import BaseFormatter

class GeminiFormatter(BaseFormatter):
    """Formatador usando 100% Gemini 2.5 Flash"""
    
    def __init__(self):
        super().__init__(model_name="Gemini 2.5 Flash")
        
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
                "X-Title": "Vomo Legal Transcriber - Gemini Test"
            }
        )
        
        self.model_id = "google/gemini-2.5-flash"
        
        print(f"{Fore.GREEN}✓ GeminiFormatter inicializado")
    
    async def format_transcription(self, transcription, video_name):
        """Formata transcrição usando 100% Gemini com escrita incremental"""
        self.metrics['start_time'] = asyncio.get_event_loop().time()
        
        print(f"\n{Fore.CYAN}🧠 Formatando com Gemini 2.5 Flash...")
        print(f"   Tamanho: {len(transcription):,} chars")
        
        # Chunking
        chunks = self._smart_chunk_overlapping(transcription, max_size=25000, overlap=3000)
        print(f"   Chunks: {len(chunks)}")
        
        # System prompt
        system_prompt = self._get_system_prompt()
        
        # Arquivo temporário para escrita incremental
        temp_file = f"temp_gemini_{video_name}.md"
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write(f"# {video_name}\n\n")
            
        full_content = f"# {video_name}\n\n"
        
        # Processa chunks sequencialmente e salva em disco
        import gc
        for i, chunk in enumerate(chunks):
            print(f"   [{i+1:02d}/{len(chunks)}] Processando...")
            
            result = await self._format_chunk_async(chunk, i, system_prompt)
            
            # Escreve no disco imediatamente
            with open(temp_file, 'a', encoding='utf-8') as f:
                f.write(result + "\n\n")
            
            # Mantém em memória apenas para retorno final (se couber)
            # Se falhar aqui, pelo menos temos o arquivo
            full_content += result + "\n\n"
            
            # Limpeza forçada
            del result
            gc.collect()
            
        self.metrics['end_time'] = asyncio.get_event_loop().time()
        self.metrics['duration'] = self.metrics['end_time'] - self.metrics['start_time']
        
        print(f"{Fore.GREEN}✓ Formatação concluída em {self.metrics['duration']:.1f}s")
        
        return full_content
    
    async def _format_chunk_async(self, chunk, chunk_idx, system_prompt):
        """Formata um chunk usando Gemini"""
        print(f"   [{chunk_idx+1:02d}] Gemini processando...")
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model_id,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"[PARTE {chunk_idx+1}]\n\n{chunk}"}
                ],
                temperature=0.1,
                extra_body={
                    "transforms": ["middle-out"],
                    "top_p": 0.9
                }
            )
            
            self.metrics['api_calls'] += 1
            self.metrics['tokens_used'] += response.usage.total_tokens
            
            # Atualiza custo
            from test_utils import TestMetrics
            self.metrics['cost_usd'] += TestMetrics.calculate_cost(
                "gemini-2.5-flash",
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
