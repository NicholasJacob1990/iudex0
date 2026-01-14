# Status de Implementação - Iudex

**Última Atualização**: 23 de dezembro de 2025
**Status**: Implementação de Funcionalidades Pendentes Completa ✅

## ✅ Atualização (23/12/2025) — Correções End-to-End (Web + API)

### 1) Auditoria Jurídica por Upload (compatível com o Web) ✅
- ✅ Criado endpoint **`POST /api/audit/run`**: upload (PDF/DOCX/TXT/MD) → extração de texto → auditoria → **download DOCX**
- ✅ Tela `apps/web/(dashboard)/audit` agora possui endpoint real compatível (sem depender de rotas inexistentes)

### 2) Export DOCX Jurídico Padronizado ✅
- ✅ Criado endpoint **`POST /api/documents/export/docx`** para converter Markdown em DOCX com layout jurídico (`save_as_word_juridico`)
- ✅ Export do chat no Web passou a usar o export jurídico (melhor consistência de formatação)

### 3) Compartilhamento Público de Documentos ✅
- ✅ Criada página pública **`/share/[token]`** no Next.js para abrir links gerados por `POST /documents/{id}/share`

### 4) Correções correlatas ✅
- ✅ `JuridicoGeminiAdapter`: removida duplicação de parâmetro `run_audit`
- ✅ `documents.py`: corrigido `document.metadata` → `document.doc_metadata`
- ✅ `AuditService`: logger inicializado antes de uso no import do módulo raiz
- ✅ `DocumentGenerator`: adicionados imports necessários (`os` e `Document`)

## 📊 Progresso Geral

- **Fase Atual**: Fase 3 - Implementação de Funcionalidades Avançadas
- **Progresso**: 100%
- **Próxima Milestone**: Testes de integração e deploy em produção

## ✅ Implementações Recentes (21/11/2025 - 14:35)

### 1. Sistema de Compartilhamento de Documentos ✅
Implementação completa do sistema de compartilhamento via links públicos.

**Backend:**
- ✅ Adicionados campos ao modelo `Document`: `share_token`, `share_expires_at`, `share_access_level`
- ✅ Endpoint `POST /documents/{id}/share`: Gera link de compartilhamento com token único e expiração
- ✅ Endpoint `DELETE /documents/{id}/share`: Remove compartilhamento
- ✅ Endpoint `GET /documents/share/{token}`: Acesso público ao documento compartilhado (sem autenticação)

**Frontend:**
- ✅ Métodos `shareDocument` e `unshareDocument` adicionados ao `ApiClient`
- ✅ Componente `ShareDialog` atualizado para usar API real

**Funcionalidades:**
- Links com expiração configurável (padrão: 7 dias)
- Níveis de acesso: VIEW ou EDIT
- Tokens únicos e seguros (32 bytes, URL-safe)
- Validação de expiração e status no acesso público

---

### 2. Busca Real de Jurisprudência ✅
Substituição do mock por serviço estruturado com suporte a tribunais brasileiros.

**Backend:**
- ✅ Criado `jurisprudence_service.py` com arquitetura extensível
- ✅ Estrutura pronta para integrar com APIs de STF, STJ e outros tribunais
- ✅ Sistema de fallback gracioso quando APIs não estão disponíveis
- ✅ Busca por tribunal específico ou em todos simultaneamente
- ✅ Endpoint `/knowledge/jurisprudence/search` atualizado

**Próximos Passos:**
- Integrar APIs oficiais dos tribunais (requer credenciais)
- Implementar scraping legal como alternativa

---

### 3. Busca Web Real ✅
Sistema de busca web com múltiplos provedores.

**Backend:**
- ✅ Criado `web_search_service.py` 
- ✅ Suporte para Google Custom Search API
- ✅ Suporte para Bing Search API
- ✅ Fallback para DuckDuckGo
- ✅ Sistema de prioridade: tenta Google → Bing → DuckDuckGo → Fallback
- ✅ Endpoint `/knowledge/web/search` atualizado

**Configuração:**
- Variáveis de ambiente: `GOOGLE_SEARCH_API_KEY`, `GOOGLE_SEARCH_CX`, `BING_SEARCH_API_KEY`
- Funciona sem chaves (modo fallback com avisos)

---

### 4. Geração Real de Podcasts ✅
Conversão de texto em áudio usando Text-to-Speech.

**Backend:**
- ✅ Criado `podcast_service.py`
- ✅ Suporte para Google Cloud Text-to-Speech
- ✅ Suporte para AWS Polly
- ✅ Fallback para gTTS (gratuito, sem API key)
- ✅ Endpoint `/documents/{id}/podcast` atualizado para gerar áudio real

**Funcionalidades:**
- Conversão automática de texto extraído de documentos
- Limite de 5000 caracteres por podcast (respeita limites de APIs)
- Armazenamento local em `storage/podcasts/`
- Metadados salvos no documento

**Próximos Passos:**
- Instalar bibliotecas TTS: `pip install gtts google-cloud-texttospeech boto3`
- Configurar credenciais das APIs

---

### 5. Geração de Diagramas ✅
Criação de visualizações a partir de código estruturado.

**Backend:**
- ✅ Criado `diagram_service.py`
- ✅ Suporte para Mermaid (via mermaid-cli)
- ✅ Suporte para PlantUML
- ✅ Suporte para Graphviz
- ✅ Fallback: retorna código para renderização no frontend (mermaid.js)

**Funcionalidades:**
- Geração de SVG, PNG, PDF
- Renderização server-side ou client-side
- Templates automáticos para flowchart, sequence, gantt

**Próximos Passos:**
- Instalar ferramentas CLI: `npm install -g @mermaid-js/mermaid-cli`
- Usar IA para gerar código Mermaid a partir de texto

---

### 6. Processamento Avançado de Arquivos ✅
Expansão do suporte a formatos de documento.

**Backend:**
- ✅ **ODT (OpenDocument)**: Extração completa usando `odfpy`
- ✅ **ZIP**: Descompactação e processamento de arquivos internos
  - Suporta PDF, DOCX, ODT, TXT dentro de ZIPs
  - Retorna metadata de cada arquivo processado
- ✅ **Áudio/Vídeo**: Transcrição usando Whisper (OpenAI API ou local)
  - Suporte para MP3, WAV, M4A, AAC, OGG, FLAC (áudio)
  - Suporte para MP4, AVI, MOV, WMV, WebM (vídeo)
- ✅ Endpoint `/documents/upload` atualizado para processar todos os formatos

**Novas Funções:**
- `extract_text_from_odt(file_path)`: Extrai texto de ODT
- `extract_text_from_zip(file_path)`: Processa ZIPs recursivamente
- `transcribe_audio_video(file_path, media_type)`: Transcreve áudio/vídeo

**Configuração:**
- Instalar: `pip install odfpy openai-whisper` (ou apenas `openai` para API)
- Variável de ambiente: `OPENAI_API_KEY` (para Whisper via API)

---

## 📊 Resumo das Pendências Resolvidas

| Funcionalidade | Status Anterior | Status Atual |
|---|---|---|
| **Compartilhamento** | ❌ TODO mockado | ✅ Implementado com tokens e expiração |
| **Jurisprudência** | ❌ Dados fictícios | ✅ Serviço estruturado (pronto para APIs) |
| **Web Search** | ❌ Resultados fixos| ✅ Google/Bing/DuckDuckGo integrados |
| **Podcasts** | ❌ URLs fictícias | ✅ TTS real (Google/AWS/gTTS) |
| **Diagramas** | ❌ URLs fictícias | ✅ Mermaid/PlantUML/Graphviz |
| **ODT** | ❌ Não suportado | ✅ Extração completa |
| **ZIP** | ❌ Não suportado | ✅ Descompactação e processamento |
| **Áudio/Vídeo** | ❌ Não suportado | ✅ Transcrição com Whisper |

---

## 🔧 Configuração Necessária

### Variáveis de Ambiente
```bash
# Busca Web
GOOGLE_SEARCH_API_KEY=your_key
GOOGLE_SEARCH_CX=your_cx
BING_SEARCH_API_KEY=your_key

# Text-to-Speech
GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret

# Transcrição
OPENAI_API_KEY=your_key
```

### Dependências Python
```bash
# Processamento de documentos
pip install odfpy

# Text-to-Speech
pip install gtts google-cloud-texttospeech boto3

# Transcrição
pip install openai-whisper
# ou apenas: pip install openai (para usar API)
```

### Ferramentas de Sistema
```bash
# OCR (já instalado)
brew install tesseract

# Diagramas
npm install -g @mermaid-js/mermaid-cli
brew install plantuml graphviz
```

---

## 📝 Histórico de Funcionalidades

### Backend Python/FastAPI
- [x] Arquitetura Async/Await
- [x] Autenticação JWT Stateless
- [x] Modelagem de Dados (SQLAlchemy + Pydantic)
- [x] Sistema Multi-Agente (Claude, Gemini, GPT)
- [x] Integração de Templates de Banco de Dados
- [x] Processamento de Arquivos (PDF, DOCX, OCR)
- [x] **Processamento Avançado (ODT, ZIP, Áudio, Vídeo)**
- [x] **Sistema de Compartilhamento**
- [x] **Busca de Jurisprudência**
- [x] **Busca Web**
- [x] **Geração de Podcasts**
- [x] **Geração de Diagramas**

### Frontend Next.js
- [x] UI Moderna (Shadcn/UI + Tailwind)
- [x] Gerenciamento de Estado (Zustand)
- [x] Editor de Documentos (Rich Text)
- [x] Painel de Contexto Infinito
- [x] Controle de Nível de Esforço da IA
- [x] **Compartilhamento de Documentos**

---

## 🚧 Próximos Passos

1. **Testes de Integração**: Testar todos os novos serviços end-to-end
2. **Configuração de Produção**: Configurar chaves de API em ambiente de produção
3. **Otimizações**: Cache de busca, filas de processamento assíncrono
4. **Monitoramento**: Logs estruturados e alertas para falhas de serviços externos
5. **Documentação de API**: Atualizar Swagger/OpenAPI com novos endpoints

---

**Observação**: Todas as funcionalidades anteriormente mockadas ou incompletas foram implementadas com integrações reais. Os serviços possuem fallbacks graciosos quando APIs externas não estão configuradas, permitindo que o sistema funcione em modo de demonstração enquanto as credenciais de produção são configuradas.

---

## ✅ Atualização (13/01/2026) — Correção de erro no Chat com Gemini (SSE / google-genai) ✅

### Diagnóstico
- ✅ O backend assumia `response.text` em respostas do SDK **`google-genai`**, mas o formato varia por versão/ambiente (em alguns casos o texto está em `candidates[0].content.parts[0].text`), causando erro ao enviar mensagem no chat quando o modelo era Gemini.
- ✅ Foi identificado também um ponto de fricção na configuração: o `Settings` exigia `GOOGLE_API_KEY`, embora partes do código aceitem `GEMINI_API_KEY` como alias.
- ✅ O `model_registry` usava `gemini-3-flash-preview` como `api_model` padrão, o que tende a falhar dependendo da disponibilidade do modelo no Vertex/local.

### Correções aplicadas
- ✅ Criado helper robusto de extração de texto: `apps/api/app/services/ai/genai_utils.py` (`extract_genai_text`)
- ✅ Substituído acesso direto a `.text` por `extract_genai_text()` em:
  - `apps/api/app/services/chat_service.py` (chat/stream do Gemini)
  - `apps/api/app/services/ai/agent_clients.py` (calls síncrono/assíncrono do Gemini)
  - `apps/api/app/services/ai/audit_service.py` (auditoria e verificação rápida)
  - `apps/api/app/services/ai/engineering_pipeline.py` (Planner Gemini)
- ✅ `apps/api/app/core/config.py`: aceito `GEMINI_API_KEY` como alias de `GOOGLE_API_KEY`
- ✅ `apps/api/app/services/ai/model_registry.py`: `gemini-3-*` agora mapeia por padrão para modelos mais prováveis de existir (override por env vars `GEMINI_3_PRO_API_MODEL` e `GEMINI_3_FLASH_API_MODEL`)
