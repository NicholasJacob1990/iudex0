"""
Serviço de geração de podcasts
Converte texto em áudio usando Text-to-Speech
"""

import os
import uuid
from typing import Optional
from loguru import logger
import asyncio


class PodcastService:
    """
    Serviço para gerar podcasts (áudio) a partir de texto
    
    Suporta:
    - Google Cloud Text-to-Speech (se configurado)
    - AWS Polly (se configurado)
    - gTTS (fallback free)
    - ElevenLabs (se configurado)
    """
    
    def __init__(self, storage_path: str = "storage/podcasts"):
        self.storage_path = storage_path
        os.makedirs(storage_path, exist_ok=True)
        
        # Verificar APIs disponíveis
        self.google_credentials = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        self.aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
        self.elevenlabs_api_key = os.getenv("ELEVENLABS_API_KEY")
    
    async def generate_podcast(
        self,
        text: str,
        voice: str = "pt-BR-Standard-A",
        title: Optional[str] = None
    ) -> dict:
        """
        Gerar podcast a partir de texto
        
        Args:
            text: Texto para converter em áudio
            voice: Voz a usar (depende do provider)
            title: Título do podcast
            
        Returns:
            Dict com url, duration, etc.
        """
        try:
            # Gerar ID único
            podcast_id = str(uuid.uuid4())
            filename = f"{podcast_id}.mp3"
            filepath = os.path.join(self.storage_path, filename)
            
            # Tentar gerar com serviços disponíveis
            success = False
            
            if self.google_credentials:
                success = await self._generate_with_google(text, filepath, voice)
            
            if not success and self.aws_access_key:
                success = await self._generate_with_aws(text, filepath, voice)
            
            if not success and self.elevenlabs_api_key:
                success = await self._generate_with_elevenlabs(text, filepath, voice)
            
            if not success:
                # Usar gTTS como fallback (free)
                success = await self._generate_with_gtts(text, filepath)
            
            if success:
                return {
                    "id": podcast_id,
                    "title": title or "Podcast Gerado",
                    "url": f"/podcasts/{filename}",
                    "filepath": filepath,
                    "status": "ready"
                }
            else:
                # Se tudo falhar, retornar URL de demonstração
                logger.warning("Todas as tentativas de TTS falharam, usando placeholder")
                return {
                    "id": podcast_id,
                    "title": title or "Podcast (Demonstração)",
                    "url": f"/podcasts/demo-{podcast_id}.mp3",
                    "status": "demo",
                    "message": "Configure chaves de API para gerar podcasts reais"
                }
                
        except Exception as e:
            logger.error(f"Erro ao gerar podcast: {e}")
            return {
                "error": str(e),
                "status": "error"
            }
    
    async def _generate_with_google(
        self,
        text: str,
        filepath: str,
        voice: str
    ) -> bool:
        """
        Gerar com Google Cloud Text-to-Speech
        """
        try:
            from google.cloud import texttospeech
            
            client = texttospeech.TextToSpeechClient()
            
            synthesis_input = texttospeech.SynthesisInput(text=text)
            voice_params = texttospeech.VoiceSelectionParams(
                language_code="pt-BR",
                name=voice
            )
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3
            )
            
            response = client.synthesize_speech(
                input=synthesis_input,
                voice=voice_params,
                audio_config=audio_config
            )
            
            with open(filepath, "wb") as out:
                out.write(response.audio_content)
            
            logger.info(f"Podcast gerado com Google TTS: {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"Erro ao gerar com Google TTS: {e}")
            return False
    
    async def _generate_with_aws(
        self,
        text: str,
        filepath: str,
        voice: str
    ) -> bool:
        """
        Gerar com AWS Polly
        """
        try:
            import boto3
            
            polly = boto3.client('polly')
            
            response = polly.synthesize_speech(
                Text=text,
                OutputFormat='mp3',
                VoiceId='Camila',  # Voz em português brasileiro
                LanguageCode='pt-BR'
            )
            
            with open(filepath, 'wb') as out:
                out.write(response['AudioStream'].read())
            
            logger.info(f"Podcast gerado com AWS Polly: {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"Erro ao gerar com AWS Polly: {e}")
            return False
    
    async def _generate_with_elevenlabs(
        self,
        text: str,
        filepath: str,
        voice: str
    ) -> bool:
        """
        Gerar com ElevenLabs
        """
        try:
            # TODO: Implementar integração com ElevenLabs
            logger.info("ElevenLabs ainda não implementado")
            return False
            
        except Exception as e:
            logger.error(f"Erro ao gerar com ElevenLabs: {e}")
            return False
    
    async def _generate_with_gtts(self, text: str, filepath: str) -> bool:
        """
        Gerar com gTTS (Google Text-to-Speech free)
        """
        try:
            from gtts import gTTS
            
            # Executar em thread separada para não bloquear
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: gTTS(text=text, lang='pt-br', slow=False).save(filepath)
            )
            
            logger.info(f"Podcast gerado com gTTS: {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"Erro ao gerar com gTTS: {e}")
            return False


# Instância global
podcast_service = PodcastService()
