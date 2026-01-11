# 🛠️ Guia de Implementação Técnica - Backend Iudex

Este documento contém **código pronto para usar** para as implementações pendentes.

---

## 📁 1. Extração de Texto de ODT

### Arquivo: `apps/api/app/services/document_processor.py`

```python
async def extract_text_from_odt(file_path: str) -> str:
    """
    Extrai texto de arquivos ODT (OpenDocument Text)
    
    Args:
        file_path: Caminho do arquivo ODT
        
    Returns:
        Texto extraído do documento
    """
    try:
        from odf import text, teletype
        from odf.opendocument import load
        
        # Carregar documento
        doc = load(file_path)
        
        # Extrair todos os parágrafos
        all_paras = doc.getElementsByType(text.P)
        extracted_text = "\n".join([teletype.extractText(p) for p in all_paras])
        
        # Extrair tabelas também
        from odf import table
        all_tables = doc.getElementsByType(table.Table)
        for tbl in all_tables:
            rows = tbl.getElementsByType(table.TableRow)
            for row in rows:
                cells = row.getElementsByType(table.TableCell)
                cell_texts = [teletype.extractText(cell) for cell in cells]
                extracted_text += "\n" + " | ".join(cell_texts)
        
        return extracted_text.strip()
        
    except Exception as e:
        logger.error(f"Erro ao extrair texto de ODT: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao processar arquivo ODT: {str(e)}"
        )
```

### Integração no endpoint de upload

**Arquivo:** `apps/api/app/api/endpoints/documents.py`

Substituir linhas 152-155 por:

```python
elif doc_type == DocumentType.ODT:
    extracted_text = await extract_text_from_odt(file_path)
    document.doc_metadata = {
        **document.doc_metadata, 
        "extraction_completed": True,
        "extraction_method": "odfpy"
    }
```

### Instalação

```bash
pip install odfpy
```

---

## 📦 2. Descompactação de Arquivos ZIP

### Arquivo: `apps/api/app/services/document_processor.py`

```python
async def extract_text_from_zip(file_path: str) -> tuple[str, list[dict]]:
    """
    Descompacta arquivo ZIP e extrai texto de todos os documentos internos
    
    Args:
        file_path: Caminho do arquivo ZIP
        
    Returns:
        Tuple com (texto concatenado, lista de metadados dos arquivos)
    """
    import zipfile
    import tempfile
    from pathlib import Path
    
    try:
        extracted_texts = []
        file_metadata = []
        
        with zipfile.ZipFile(file_path, 'r') as zip_ref:
            # Listar arquivos em ordem
            file_list = sorted(zip_ref.namelist())
            
            # Criar diretório temporário para extração
            with tempfile.TemporaryDirectory() as temp_dir:
                for file_name in file_list:
                    # Ignorar diretórios e arquivos ocultos
                    if file_name.endswith('/') or file_name.startswith('.'):
                        continue
                    
                    # Extrair arquivo
                    extracted_path = zip_ref.extract(file_name, temp_dir)
                    file_ext = Path(file_name).suffix.lower()
                    
                    # Processar baseado na extensão
                    text = None
                    extraction_method = None
                    
                    try:
                        if file_ext == '.pdf':
                            text = await extract_text_from_pdf(extracted_path)
                            extraction_method = 'pdf'
                        elif file_ext in ['.docx', '.doc']:
                            text = await extract_text_from_docx(extracted_path)
                            extraction_method = 'docx'
                        elif file_ext == '.odt':
                            text = await extract_text_from_odt(extracted_path)
                            extraction_method = 'odt'
                        elif file_ext == '.txt':
                            with open(extracted_path, 'r', encoding='utf-8') as f:
                                text = f.read()
                            extraction_method = 'txt'
                        elif file_ext in ['.jpg', '.jpeg', '.png']:
                            text = await extract_text_from_image(extracted_path)
                            extraction_method = 'ocr'
                        
                        if text:
                            extracted_texts.append(f"\n{'='*60}\n")
                            extracted_texts.append(f"Arquivo: {file_name}\n")
                            extracted_texts.append(f"{'='*60}\n\n")
                            extracted_texts.append(text)
                            
                            file_metadata.append({
                                "filename": file_name,
                                "extraction_method": extraction_method,
                                "text_length": len(text),
                                "success": True
                            })
                        else:
                            logger.warning(f"Tipo de arquivo não suportado no ZIP: {file_name}")
                            file_metadata.append({
                                "filename": file_name,
                                "success": False,
                                "reason": "Tipo não suportado"
                            })
                    
                    except Exception as e:
                        logger.error(f"Erro ao processar {file_name} do ZIP: {e}")
                        file_metadata.append({
                            "filename": file_name,
                            "success": False,
                            "reason": str(e)
                        })
        
        combined_text = "\n".join(extracted_texts)
        return combined_text, file_metadata
        
    except zipfile.BadZipFile:
        raise HTTPException(
            status_code=400,
            detail="Arquivo ZIP corrompido ou inválido"
        )
    except Exception as e:
        logger.error(f"Erro ao processar ZIP: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao processar arquivo ZIP: {str(e)}"
        )
```

### Integração no endpoint de upload

**Arquivo:** `apps/api/app/api/endpoints/documents.py`

Substituir linhas 161-164 por:

```python
elif doc_type == DocumentType.ZIP:
    extracted_text, zip_metadata = await extract_text_from_zip(file_path)
    document.doc_metadata = {
        **document.doc_metadata,
        "extraction_completed": True,
        "extraction_method": "zip",
        "files_processed": zip_metadata,
        "total_files": len(zip_metadata),
        "successful_files": sum(1 for f in zip_metadata if f.get("success"))
    }
```

---

## 🔍 3. OCR Completo para PDFs Digitalizados

### Arquivo: `apps/api/app/services/document_processor.py`

```python
async def extract_text_from_pdf_with_ocr(
    file_path: str, 
    language: str = 'por',
    force_ocr: bool = False
) -> tuple[str, dict]:
    """
    Extrai texto de PDF, aplicando OCR automaticamente em páginas digitalizadas
    
    Args:
        file_path: Caminho do arquivo PDF
        language: Idioma para OCR (padrão: português)
        force_ocr: Se True, força OCR em todas as páginas
        
    Returns:
        Tuple com (texto extraído, metadados do OCR)
    """
    import pytesseract
    from pdf2image import convert_from_path
    from PIL import Image, ImageEnhance
    import pdfplumber
    
    ocr_metadata = {
        "total_pages": 0,
        "ocr_pages": [],
        "text_pages": [],
        "extraction_method": "mixed"
    }
    
    try:
        extracted_text = []
        
        # Primeiro, tentar extração normal
        with pdfplumber.open(file_path) as pdf:
            ocr_metadata["total_pages"] = len(pdf.pages)
            
            for page_num, page in enumerate(pdf.pages, start=1):
                # Tentar extrair texto nativo
                page_text = page.extract_text() or ""
                
                # Verificar se precisa de OCR
                needs_ocr = (
                    force_ocr or 
                    len(page_text.strip()) < 50 or  # Muito pouco texto
                    page_text.count('�') > 5  # Caracteres corrompidos
                )
                
                if needs_ocr:
                    logger.info(f"Aplicando OCR na página {page_num}/{ocr_metadata['total_pages']}")
                    
                    # Converter página para imagem
                    images = convert_from_path(
                        file_path,
                        first_page=page_num,
                        last_page=page_num,
                        dpi=300
                    )
                    
                    if images:
                        image = images[0]
                        
                        # Pré-processamento da imagem
                        image = image.convert('L')  # Grayscale
                        
                        # Aumentar contraste
                        enhancer = ImageEnhance.Contrast(image)
                        image = enhancer.enhance(2.0)
                        
                        # Aplicar OCR
                        ocr_text = pytesseract.image_to_string(
                            image,
                            lang=language,
                            config='--psm 1 --oem 3'
                        )
                        
                        page_text = ocr_text
                        ocr_metadata["ocr_pages"].append(page_num)
                else:
                    ocr_metadata["text_pages"].append(page_num)
                
                # Adicionar ao texto final
                extracted_text.append(f"\n--- Página {page_num} ---\n")
                extracted_text.append(page_text)
        
        combined_text = "\n".join(extracted_text)
        
        # Atualizar metadados
        if ocr_metadata["ocr_pages"]:
            ocr_metadata["extraction_method"] = "ocr" if force_ocr else "mixed"
        else:
            ocr_metadata["extraction_method"] = "text"
        
        return combined_text, ocr_metadata
        
    except Exception as e:
        logger.error(f"Erro ao processar PDF com OCR: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao processar PDF: {str(e)}"
        )
```

### Integração no endpoint de upload

**Arquivo:** `apps/api/app/api/endpoints/documents.py`

Substituir linhas 145-151 por:

```python
if doc_type == DocumentType.PDF:
    extracted_text, ocr_metadata = await extract_text_from_pdf_with_ocr(file_path)
    document.doc_metadata = {
        **document.doc_metadata,
        **ocr_metadata,
        "extraction_completed": True
    }
```

### Instalação

```bash
# macOS
brew install tesseract tesseract-lang poppler

# Ubuntu/Debian
sudo apt-get install tesseract-ocr tesseract-ocr-por poppler-utils

# Python
pip install pytesseract pdf2image pillow pdfplumber
```

---

## 🎤 4. Transcrição de Áudio/Vídeo com Whisper

### Arquivo: `apps/api/app/services/document_processor.py`

```python
async def transcribe_audio_video(
    file_path: str,
    language: str = 'pt',
    identify_speakers: bool = False
) -> dict:
    """
    Transcreve áudio ou vídeo usando OpenAI Whisper
    
    Args:
        file_path: Caminho do arquivo de áudio/vídeo
        language: Código do idioma (pt, en, es, etc.)
        identify_speakers: Se True, tenta identificar diferentes falantes
        
    Returns:
        Dict com transcrição e metadados
    """
    import whisper
    from pydub import AudioSegment
    import tempfile
    from pathlib import Path
    
    try:
        # Carregar modelo Whisper (use 'base' para velocidade, 'large' para qualidade)
        logger.info("Carregando modelo Whisper...")
        model = whisper.load_model("base")
        
        # Converter para WAV se necessário
        file_ext = Path(file_path).suffix.lower()
        temp_wav = None
        
        if file_ext not in ['.wav', '.mp3']:
            logger.info(f"Convertendo {file_ext} para WAV...")
            audio = AudioSegment.from_file(file_path)
            
            # Criar arquivo temporário
            with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_file:
                temp_wav = temp_file.name
                audio.export(temp_wav, format="wav")
                audio_path = temp_wav
        else:
            audio_path = file_path
        
        # Transcrever
        logger.info("Transcrevendo áudio...")
        result = model.transcribe(
            audio_path,
            language=language,
            verbose=False,
            word_timestamps=True
        )
        
        # Formatar resultado
        transcription = {
            "text": result["text"],
            "language": result["language"],
            "duration": result.get("duration"),
            "segments": []
        }
        
        # Processar segmentos com timestamps
        for segment in result["segments"]:
            transcription["segments"].append({
                "start": segment["start"],
                "end": segment["end"],
                "text": segment["text"].strip()
            })
        
        # Diarização de falantes (opcional - requer pyannote.audio)
        if identify_speakers:
            try:
                from pyannote.audio import Pipeline
                
                # Carregar pipeline de diarização
                pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization")
                
                # Aplicar diarização
                diarization = pipeline(audio_path)
                
                # Adicionar informação de falantes aos segmentos
                # (implementação simplificada)
                transcription["speakers"] = []
                for turn, _, speaker in diarization.itertracks(yield_label=True):
                    transcription["speakers"].append({
                        "speaker": speaker,
                        "start": turn.start,
                        "end": turn.end
                    })
                    
            except Exception as e:
                logger.warning(f"Diarização de falantes falhou: {e}")
                transcription["speakers"] = None
        
        # Limpar arquivo temporário
        if temp_wav:
            Path(temp_wav).unlink(missing_ok=True)
        
        return transcription
        
    except Exception as e:
        logger.error(f"Erro ao transcrever áudio: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao transcrever áudio: {str(e)}"
        )
```

### Integração no endpoint

**Arquivo:** `apps/api/app/api/endpoints/documents.py`

Atualizar função `transcribe_audio()` (linha 437-455):

```python
@router.post("/{document_id}/transcribe")
async def transcribe_audio(
    document_id: str,
    identify_speakers: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Transcrever áudio/vídeo
    """
    # Buscar documento
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.user_id == current_user.id
        )
    )
    document = result.scalars().first()
    
    if not document:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    
    # Verificar se é áudio/vídeo
    if document.doc_type not in [DocumentType.AUDIO, DocumentType.VIDEO]:
        raise HTTPException(
            status_code=400,
            detail="Documento não é áudio ou vídeo"
        )
    
    # Transcrever
    transcription = await transcribe_audio_video(
        document.file_path,
        language='pt',
        identify_speakers=identify_speakers
    )
    
    # Atualizar documento
    document.content = transcription["text"]
    document.doc_metadata = {
        **document.doc_metadata,
        "transcription": transcription,
        "transcription_completed": True
    }
    
    await db.commit()
    
    return {
        "message": "Transcrição concluída",
        "document_id": document_id,
        "transcription": transcription
    }
```

### Instalação

```bash
# Sistema
brew install ffmpeg  # macOS
sudo apt-get install ffmpeg  # Ubuntu

# Python
pip install openai-whisper pydub

# Opcional (diarização)
pip install pyannote.audio
```

---

## 🌐 5. Scraping de URLs Melhorado

### Arquivo: `apps/api/app/services/url_scraper_service.py`

Melhorar o serviço existente:

```python
async def scrape_url_advanced(
    url: str,
    use_javascript: bool = False
) -> dict:
    """
    Scraping avançado de URLs com suporte a JavaScript
    
    Args:
        url: URL para fazer scraping
        use_javascript: Se True, usa Playwright para páginas com JS
        
    Returns:
        Dict com conteúdo e metadados
    """
    import httpx
    from bs4 import BeautifulSoup
    from readability import Document as ReadabilityDocument
    
    try:
        if use_javascript:
            # Usar Playwright para páginas com JavaScript
            from playwright.async_api import async_playwright
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                
                await page.goto(url, wait_until='networkidle')
                html_content = await page.content()
                
                await browser.close()
        else:
            # Usar httpx para páginas estáticas (mais rápido)
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(
                    url,
                    headers={
                        'User-Agent': 'Mozilla/5.0 (compatible; IudexBot/1.0)'
                    },
                    timeout=30.0
                )
                response.raise_for_status()
                html_content = response.text
        
        # Extrair conteúdo principal com Readability
        doc = ReadabilityDocument(html_content)
        
        # Parse com BeautifulSoup
        soup = BeautifulSoup(doc.summary(), 'html.parser')
        
        # Remover elementos indesejados
        for tag in soup(['script', 'style', 'nav', 'footer', 'aside']):
            tag.decompose()
        
        # Extrair texto limpo
        text = soup.get_text(separator='\n', strip=True)
        
        # Metadados
        title = doc.title()
        
        # Extrair links importantes
        links = []
        for a in soup.find_all('a', href=True):
            link_text = a.get_text(strip=True)
            link_url = a['href']
            if link_text and link_url.startswith('http'):
                links.append({"text": link_text, "url": link_url})
        
        return {
            "url": url,
            "title": title,
            "content": text,
            "links": links[:20],  # Limitar a 20 links
            "word_count": len(text.split()),
            "char_count": len(text)
        }
        
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Erro ao acessar URL: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Erro ao fazer scraping de {url}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao processar URL: {str(e)}"
        )
```

### Instalação

```bash
# Básico
pip install httpx beautifulsoup4 readability-lxml

# Avançado (JavaScript)
pip install playwright
playwright install chromium
```

---

## 🔎 6. Busca de Jurisprudência Real

### Opção 1: API do STJ (Não Oficial)

```python
async def search_stj_jurisprudence(query: str, limit: int = 10) -> list[dict]:
    """
    Busca jurisprudência no STJ
    
    Note: Esta é uma implementação de exemplo usando scraping.
    Idealmente, use uma API oficial quando disponível.
    """
    import httpx
    from bs4 import BeautifulSoup
    
    try:
        async with httpx.AsyncClient() as client:
            # URL de busca do STJ
            search_url = "https://scon.stj.jus.br/SCON/pesquisar.jsp"
            
            # Parâmetros de busca
            params = {
                "b": "ACOR",  # Acórdãos
                "livre": query,
                "p": "true"
            }
            
            response = await client.post(search_url, data=params, timeout=30.0)
            response.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extrair resultados (adaptado à estrutura do site)
            results = []
            for item in soup.find_all('div', class_='resultado-item', limit=limit):
                # Extrair informações
                title_elem = item.find('span', class_='titulo')
                ementa_elem = item.find('div', class_='ementa')
                processo_elem = item.find('span', class_='processo')
                
                if title_elem and ementa_elem:
                    results.append({
                        "id": f"stj-{len(results)+1}",
                        "court": "STJ",
                        "title": title_elem.get_text(strip=True),
                        "summary": ementa_elem.get_text(strip=True)[:500],
                        "processNumber": processo_elem.get_text(strip=True) if processo_elem else "N/A",
                        "date": "2024",  # Extrair data real se disponível
                        "tags": []
                    })
            
            return results
            
    except Exception as e:
        logger.error(f"Erro ao buscar no STJ: {e}")
        return []
```

### Opção 2: Usar JurisAPI (Serviço Pago)

```python
async def search_jurisprudence_jurisapi(
    query: str,
    court: str = None,
    limit: int = 10
) -> list[dict]:
    """
    Busca jurisprudência usando JurisAPI (exemplo)
    
    Requer configuração de API key no .env:
    JURISAPI_KEY=sua_chave_aqui
    """
    import httpx
    from app.core.config import settings
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.jurisapi.com/v1/jurisprudence/search",
                headers={
                    "Authorization": f"Bearer {settings.JURISAPI_KEY}"
                },
                params={
                    "q": query,
                    "court": court,
                    "limit": limit
                },
                timeout=30.0
            )
            response.raise_for_status()
            
            data = response.json()
            return data.get("results", [])
            
    except Exception as e:
        logger.error(f"Erro ao buscar jurisprudência: {e}")
        return []
```

---

## 🏛️ 7. Busca de Legislação Real

### Arquivo: `apps/api/app/services/legislation_service.py`

```python
async def search_legislation_planalto(query: str, limit: int = 10) -> list[dict]:
    """
    Busca legislação no Planalto usando Lexml
    """
    import httpx
    from bs4 import BeautifulSoup
    
    try:
        # API Lexml
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://www.lexml.gov.br/busca/api",
                params={
                    "q": query,
                    "formato": "json",
                    "limite": limit
                },
                timeout=30.0
            )
            response.raise_for_status()
            
            data = response.json()
            
            results = []
            for item in data.get("documentos", []):
                results.append({
                    "id": item.get("id"),
                    "title": item.get("titulo"),
                    "excerpt": item.get("ementa", "")[:300],
                    "status": item.get("situacao", "Vigente"),
                    "updated_at": item.get("data_publicacao"),
                    "url": item.get("url")
                })
            
            return results
            
    except Exception as e:
        logger.error(f"Erro ao buscar legislação: {e}")
        return []
```

---

## 🌐 8. Busca Web Real com SerpAPI

### Arquivo: `apps/api/app/services/web_search_service.py`

```python
async def search_web_serpapi(query: str, limit: int = 10) -> list[dict]:
    """
    Busca web usando SerpAPI
    
    Requer: SERPAPI_KEY no .env
    """
    import httpx
    from app.core.config import settings
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://serpapi.com/search",
                params={
                    "api_key": settings.SERPAPI_KEY,
                    "q": query,
                    "num": limit,
                    "hl": "pt-br",
                    "gl": "br"
                },
                timeout=30.0
            )
            response.raise_for_status()
            
            data = response.json()
            
            results = []
            for item in data.get("organic_results", []):
                results.append({
                    "id": f"web-{len(results)+1}",
                    "title": item.get("title"),
                    "url": item.get("link"),
                    "snippet": item.get("snippet")
                })
            
            return results
            
    except Exception as e:
        logger.error(f"Erro ao buscar na web: {e}")
        return []
```

---

## 📦 Instalação Completa de Dependências

```bash
# Processamento de documentos
pip install odfpy                      # ODT
pip install pytesseract pdf2image pillow pdfplumber  # OCR
pip install openai-whisper pydub       # Transcrição

# Scraping e busca
pip install httpx beautifulsoup4 readability-lxml
pip install playwright                 # Opcional (JavaScript)

# Sistema (macOS)
brew install tesseract tesseract-lang poppler ffmpeg

# Sistema (Ubuntu/Debian)
sudo apt-get install tesseract-ocr tesseract-ocr-por poppler-utils ffmpeg

# Opcional: Playwright
playwright install chromium
```

---

## ✅ Checklist de Integração

Após implementar cada funcionalidade:

- [ ] Código adicionado ao arquivo correto
- [ ] Imports atualizados
- [ ] Endpoint atualizado para usar nova função
- [ ] Testes manuais realizados
- [ ] Logs adicionados
- [ ] Tratamento de erros implementado
- [ ] Documentação atualizada
- [ ] Commit realizado

---

**Última atualização:** 23 de novembro de 2025  
**Versão:** 1.0  
**Autor:** Antigravity AI
