# ✅ Checklist de Implementação - Backend Iudex

## 🔴 CRÍTICO - Implementar Primeiro (1-2 semanas)

### Busca de Jurisprudência Real
- [ ] Pesquisar APIs disponíveis dos tribunais
  - [ ] STF - https://portal.stf.jus.br/
  - [ ] STJ - API não oficial ou scraping
  - [ ] TRFs, TJs - APIs estaduais
- [ ] Implementar em `jurisprudence_service.py`
- [ ] Conectar ao endpoint `/api/knowledge/jurisprudence/search`
- [ ] Testar busca real vs. mock
- [ ] Remover dados mockados de `knowledge.py`
- [ ] **OU** adicionar avisos claros de demonstração

**Risco:** ALTO - Usuários podem citar precedentes inexistentes

---

### Busca de Legislação Real
- [ ] Integrar com Planalto (leis federais)
- [ ] Integrar com Lexml (https://www.lexml.gov.br/)
- [ ] Implementar em `legislation_service.py`
- [ ] Conectar ao endpoint `/api/knowledge/legislation/search`
- [ ] Testar busca real
- [ ] Remover dados mockados de `knowledge.py`

**Risco:** MÉDIO - Legislação desatualizada

---

### OCR Completo para PDFs
- [ ] Instalar dependências:
  ```bash
  brew install tesseract tesseract-lang
  pip install pytesseract pdf2image pillow
  ```
- [ ] Implementar `extract_text_from_pdf_with_ocr()` em `document_processor.py`
- [ ] Testar com PDFs digitalizados
- [ ] Atualizar endpoint de upload para usar nova função
- [ ] Verificar performance (pode ser lento)

**Arquivo:** `apps/api/app/services/document_processor.py`

---

## ⚠️ ALTA PRIORIDADE - Implementar em Seguida (2-3 semanas)

### Extração de Texto de ODT
- [ ] Instalar: `pip install odfpy`
- [ ] Implementar `extract_text_from_odt()` em `document_processor.py`
- [ ] Adicionar ao processamento em `documents.py` linha 152-155
- [ ] Testar com arquivos ODT reais

**Tempo estimado:** 1-2 dias

---

### Descompactação de ZIP
- [ ] Implementar `extract_text_from_zip()` em `document_processor.py`
- [ ] Processar recursivamente cada arquivo interno
- [ ] Adicionar ao processamento em `documents.py` linha 161-164
- [ ] Testar com ZIPs contendo múltiplos arquivos
- [ ] Manter ordem original dos arquivos

**Tempo estimado:** 2-3 dias

---

### Transcrição de Áudio/Vídeo
- [ ] Instalar dependências:
  ```bash
  brew install ffmpeg
  pip install openai-whisper pydub
  ```
- [ ] Implementar `transcribe_audio_video()` em `document_processor.py`
- [ ] Conectar ao endpoint `POST /documents/{id}/transcribe`
- [ ] Testar com MP3, WAV, MP4, WebM
- [ ] Adicionar opção de idioma (português por padrão)
- [ ] Implementar diarização (identificação de falantes) - opcional

**Arquivo:** `apps/api/app/api/endpoints/documents.py` linha 437-455  
**Tempo estimado:** 3-4 dias

---

### Melhorar Scraping de URLs
- [ ] Testar serviço existente `url_scraper_service.py`
- [ ] Adicionar suporte a JavaScript (Playwright)
- [ ] Implementar extração inteligente de conteúdo
- [ ] Remover elementos indesejados (ads, menus)
- [ ] Conectar melhor ao endpoint `POST /documents/from-url`

**Tempo estimado:** 2-3 dias

---

## 🟡 MÉDIA PRIORIDADE - Features Avançadas (2-3 semanas)

### Busca Web Real
- [ ] Escolher provedor:
  - [ ] SerpAPI (mais fácil) - https://serpapi.com/
  - [ ] Google Custom Search API
  - [ ] Tavily AI (otimizado para IA)
- [ ] Obter API key
- [ ] Implementar em `web_search_service.py`
- [ ] Conectar ao endpoint `/api/knowledge/web/search`
- [ ] Remover dados mockados

**Tempo estimado:** 3-4 dias

---

### Sistema de Grupos
- [ ] Criar modelo `Group` no banco de dados
- [ ] Implementar CRUD de grupos em `library.py`
- [ ] Adicionar relação muitos-para-muitos `User ↔ Group`
- [ ] Implementar compartilhamento com grupos
- [ ] Adicionar permissões (admin, editor, viewer)
- [ ] Testar compartilhamento multi-nível

**Tempo estimado:** 5-7 dias

---

### Geração de Diagramas
- [ ] Verificar serviço existente `diagram_service.py`
- [ ] Conectar ao endpoint
- [ ] Testar geração com Mermaid.js
- [ ] Exportar para PNG/SVG
- [ ] Adicionar ao frontend

**Tempo estimado:** 2-3 dias

---

## 🟢 BAIXA PRIORIDADE - Features Premium (Backlog)

### Geração de Podcasts (TTS)
- [ ] Escolher provedor TTS:
  - [ ] OpenAI TTS (gpt-4o-audio-preview)
  - [ ] ElevenLabs (melhor qualidade)
  - [ ] Google Cloud TTS
- [ ] Implementar em `podcast_service.py`
- [ ] Gerar script do podcast com IA
- [ ] Converter texto para áudio
- [ ] Adicionar música/transições (opcional)
- [ ] Salvar arquivo MP3
- [ ] Conectar ao endpoint `POST /documents/{id}/podcast`

**Tempo estimado:** 5-7 dias  
**Custo:** Alto (APIs TTS cobram por caractere)

---

### Integrações CNJ/DJEN
- [ ] Pesquisar API CNJ disponível
- [ ] Implementar busca de metadados de processos
- [ ] Integrar com DJEN para comunicações
- [ ] Criar endpoint específico
- [ ] Adicionar ao frontend

**Tempo estimado:** 7-10 dias

---

## 📋 Tarefas Gerais de Manutenção

### Documentação
- [ ] Atualizar README.md com funcionalidades reais
- [ ] Documentar APIs externas usadas
- [ ] Criar guia de instalação de dependências
- [ ] Atualizar manual.md para refletir estado real

### Testes
- [ ] Escrever testes unitários para novas funcionalidades
- [ ] Testar upload de todos os formatos de arquivo
- [ ] Testar OCR com diferentes qualidades de PDF
- [ ] Testar transcrição com diferentes formatos de áudio
- [ ] Testar buscas reais (quando implementadas)

### Performance
- [ ] Otimizar processamento de arquivos grandes
- [ ] Implementar cache para buscas frequentes
- [ ] Adicionar rate limiting nas APIs externas
- [ ] Monitorar uso de memória do Tesseract/Whisper

### Segurança
- [ ] Validar todos os uploads de arquivo
- [ ] Sanitizar URLs antes de fazer scraping
- [ ] Implementar limites de tamanho de arquivo
- [ ] Proteger contra injeção de código em templates

---

## 📊 Progresso Atual

### ✅ Completo (60%)
- [x] Sistema de autenticação
- [x] Upload de documentos
- [x] Extração de texto (PDF, DOCX)
- [x] OCR para imagens
- [x] Sistema Multi-Agente IA
- [x] Geração de minutas
- [x] Editor de documentos
- [x] Exportação (DOCX, HTML, TXT)
- [x] Biblioteca (CRUD)
- [x] Bibliotecários (CRUD)
- [x] Chat com IA
- [x] Templates DOCX
- [x] Assinatura digital
- [x] Compartilhamento via link

### ⚠️ Parcial (25%)
- [ ] OCR para PDFs (detecta mas não processa)
- [ ] Transcrição (endpoint existe mas não funciona)
- [ ] Extração de ODT (upload aceito mas não extrai)
- [ ] Descompactação de ZIP (upload aceito mas não descompacta)
- [ ] Scraping de URLs (básico, precisa melhorias)
- [ ] Sistema de grupos (compartilhamento individual funciona)
- [ ] Geração de diagramas (serviço existe mas não conectado)

### 🔴 Mockado/Ausente (15%)
- [ ] Busca de jurisprudência (retorna dados fixos)
- [ ] Busca de legislação (retorna dados fixos)
- [ ] Busca web (retorna dados fixos)
- [ ] Geração de podcasts TTS (retorna URL fictícia)
- [ ] Integrações CNJ/DJEN (não existe)

---

## 🎯 Definição de "Pronto"

### Para cada funcionalidade, considerar pronto quando:
- [ ] Código implementado e funcionando
- [ ] Testes escritos e passando
- [ ] Documentação atualizada
- [ ] Testado manualmente
- [ ] Integrado ao frontend (quando aplicável)
- [ ] Deploy em staging testado
- [ ] Aprovado pelo Product Owner

---

## 📞 Contatos e Recursos

### APIs e Serviços
- **SerpAPI:** https://serpapi.com/
- **Lexml:** https://www.lexml.gov.br/
- **OpenAI:** https://platform.openai.com/
- **Tesseract:** https://github.com/tesseract-ocr/tesseract
- **Whisper:** https://github.com/openai/whisper

### Comunidades
- Python Brasil
- FastAPI Discord
- r/Python

---

**Última atualização:** 23 de novembro de 2025  
**Versão:** 1.0
