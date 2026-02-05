"""
Web Scraping Service
Importa conteúdo de URLs externas
"""

from typing import Dict, Any, Optional
from urllib.parse import urlparse
import ipaddress

from loguru import logger
import httpx
from bs4 import BeautifulSoup
import re


def _is_url_safe(url: str) -> tuple[bool, str]:
    """
    Valida se a URL é segura para requisição (anti-SSRF).
    Bloqueia IPs privados, loopback, link-local e hostnames internos.
    """
    raw = (url or "").strip()
    if not raw:
        return False, "URL vazia."
    try:
        parsed = urlparse(raw)
    except Exception:
        return False, "URL inválida."

    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False, "URL deve começar com http:// ou https://"

    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False, "Host inválido."

    # Bloquear hostnames internos conhecidos
    blocked_hosts = {"localhost", "metadata.google.internal", "169.254.169.254"}
    if host in blocked_hosts:
        return False, "Host não permitido."

    # Bloquear IPs privados/loopback/link-local/reservados
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False, "Host/IP não permitido."
    except ValueError:
        # host não é IP; verificar se termina com sufixos internos
        if host.endswith(".local") or host.endswith(".internal"):
            return False, "Host não permitido."

    return True, ""


class URLScraperService:
    """Serviço para scraping de URLs"""

    def __init__(self):
        self.timeout = 30.0
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        logger.info("URLScraperService inicializado")

    async def extract_content_from_url(self, url: str) -> Dict[str, Any]:
        """
        Extrai conteúdo de uma URL

        Returns:
            Dicionário com título, texto extraído, metadata
        """
        # Validação anti-SSRF
        safe, reason = _is_url_safe(url)
        if not safe:
            logger.warning(f"URL bloqueada por política SSRF: {url} — {reason}")
            return {"error": reason, "url": url}

        logger.info(f"Importando conteúdo de: {url}")

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self.headers, follow_redirects=True)
                response.raise_for_status()
                
                # Detectar tipo de conteúdo
                content_type = response.headers.get("content-type", "").lower()
                
                if "text/html" in content_type:
                    return await self._extract_html_content(response.text, url)
                elif "application/pdf" in content_type:
                    return {
                        "title": "PDF Document",
                        "content": "[PDF - Download necessário]",
                        "url": url,
                        "type": "pdf",
                        "message": "Para PDFs, faça download e envie diretamente"
                    }
                elif "text/plain" in content_type:
                    return {
                        "title": self._extract_title_from_url(url),
                        "content": response.text,
                        "url": url,
                        "type": "text"
                    }
                else:
                    return {
                        "title": "Tipo não suportado",
                        "content": f"Tipo de conteúdo: {content_type}",
                        "url": url,
                        "type": "unknown",
                        "message": "Tipo de conteúdo não suportado para extração"
                    }
                    
        except httpx.HTTPError as e:
            logger.error(f"Erro HTTP ao acessar {url}: {e}")
            return {
                "error": f"Erro ao acessar URL: {str(e)}",
                "url": url
            }
        except Exception as e:
            logger.error(f"Erro ao processar URL {url}: {e}")
            return {
                "error": f"Erro no processamento: {str(e)}",
                "url": url
            }
    
    async def _extract_html_content(self, html: str, url: str) -> Dict[str, Any]:
        """Extrai conteúdo de HTML usando BeautifulSoup"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Remover scripts, styles, etc
            for element in soup(['script', 'style', 'nav', 'footer', 'header', 'aside']):
                element.decompose()
            
            # Tentar extrair título
            title = ""
            if soup.find('title'):
                title = soup.find('title').text.strip()
            elif soup.find('h1'):
                title = soup.find('h1').text.strip()
            else:
                title = self._extract_title_from_url(url)
            
            # Tentar encontrar conteúdo principal
            main_content = None
            
            # Tentar elementos semânticos comuns
            for selector in ['article', 'main', '[role="main"]', '.content', '.post-content']:
                if isinstance(selector, str) and selector.startswith('.'):
                    main_content = soup.find(class_=selector[1:])
                elif isinstance(selector, str) and selector.startswith('['):
                    # Atributo selector
                    continue
                else:
                    main_content = soup.find(selector)
                    
                if main_content:
                    break
            
            # Se não encontrou conteúdo principal, usar body
            if not main_content:
                main_content = soup.find('body')
            
            # Extrair texto
            if main_content:
                # Obter todos os parágrafos e headings
                text_elements = []
                for tag in main_content.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li']):
                    text = tag.get_text(strip=True)
                    if text and len(text) > 20:  # Filtrar textos muito curtos
                        text_elements.append(text)
                
                content = '\n\n'.join(text_elements)
            else:
                content = soup.get_text(separator='\n', strip=True)
            
            # Limpar texto
            content = self._clean_text(content)
            
            # Extrair metadata
            metadata = {
                "url": url,
                "title": title,
                "source": "web_import"
            }
            
            # Tentar extrair meta tags
            if soup.find('meta', attrs={'name': 'description'}):
                metadata["description"] = soup.find('meta', attrs={'name': 'description'})['content']
            elif soup.find('meta', attrs={'property': 'og:description'}):
                metadata["description"] = soup.find('meta', attrs={'property': 'og:description'})['content']
            
            return {
                "title": title,
                "content": content,
                "metadata": metadata,
                "type": "html",
                "word_count": len(content.split())
            }
            
        except Exception as e:
            logger.error(f"Erro ao extrair HTML: {e}")
            return {
                "error": f"Erro ao extrair conteúdo HTML: {str(e)}",
                "url": url
            }
    
    def _extract_title_from_url(self, url: str) -> str:
        """Gera um título a partir da URL"""
        # Remover protocolo e domínio
        clean = re.sub(r'^https?://(www\.)?', '', url)
        # Remover extensões
        clean = re.sub(r'\.[a-z]+$', '', clean)
        # Substituir caracteres especiais
        clean = re.sub(r'[/_-]', ' ', clean)
        # Capitalizar
        return clean.title()[:100]
    
    def _clean_text(self, text: str) -> str:
        """Limpa e formata o texto extraído"""
        # Remover múltiplas linhas em branco
        text = re.sub(r'\n\s*\n', '\n\n', text)
        # Remover espaços múltiplos
        text = re.sub(r' +', ' ', text)
        # Remover espaços no início/fim de linhas
        lines = [line.strip() for line in text.split('\n')]
        text = '\n'.join(lines)
        
        return text.strip()


# Instância global
url_scraper_service = URLScraperService()
