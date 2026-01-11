# Iudex API - Setup & Deployment Guide

## Quick Start

### 1. Install Dependencies

```bash
cd apps/api
./scripts/install_dependencies.sh
```

This script will install:
- Python packages (FastAPI, SQLAlchemy, AI libraries, etc.)
- Tesseract OCR (for image text extraction)
- FFmpeg (for audio/video processing)
- Optional: Graphviz, PlantUML, Mermaid CLI (for diagrams)

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and add your API keys:

**Minimum Required:**
```bash
SECRET_KEY=<generate with: openssl rand -hex 32>
DATABASE_URL=sqlite+aiosqlite:///./iudex.db
```

**For Production Features:**
```bash
# AI Providers (at least one)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=AIza...

# Search (optional but recommended)
GOOGLE_SEARCH_API_KEY=...
GOOGLE_SEARCH_CX=...
BING_SEARCH_API_KEY=...

# Text-to-Speech (optional)
GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
```

### 3. Initialize Database

```bash
python scripts/migrate_database.py
```

This will:
- Create all required tables
- Add sharing columns to documents table
- Set up indexes

### 4. Run the Server

**Development:**
```bash
uvicorn app.main:app --reload --port 8000
```

**Production:**
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## API Keys Setup Guide

### OpenAI (Recommended for AI & Transcription)
1. Go to https://platform.openai.com/api-keys
2. Create new API key
3. Add to `.env`: `OPENAI_API_KEY=sk-...`
4. Enables: GPT models, Whisper transcription

### Anthropic Claude
1. Go to https://console.anthropic.com/
2. Get API key from settings
3. Add to `.env`: `ANTHROPIC_API_KEY=sk-ant-...`

### Google Gemini
1. Go to https://makersuite.google.com/app/apikey
2. Create API key
3. Add to `.env`: `GOOGLE_API_KEY=AIza...`

### Google Custom Search (Web Search)
1. Go to https://console.cloud.google.com/
2. Enable "Custom Search API"
3. Create credentials (API key)
4. Create Custom Search Engine at https://programmablesearchengine.google.com/
5. Add to `.env`:
   ```bash
   GOOGLE_SEARCH_API_KEY=...
   GOOGLE_SEARCH_CX=...  # Your search engine ID
   ```

### Bing Search API
1. Go to https://www.microsoft.com/en-us/bing/apis/bing-web-search-api
2. Subscribe to Bing Search API (free tier available)
3. Get subscription key
4. Add to `.env`: `BING_SEARCH_API_KEY=...`

### Google Cloud TTS (Text-to-Speech)
1. Go to https://console.cloud.google.com/
2. Enable "Cloud Text-to-Speech API"
3. Create service account and download JSON credentials
4. Add to `.env`: `GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json`

### AWS Polly (Alternative TTS)
1. Go to AWS Console → IAM
2. Create user with Polly permissions
3. Get access key and secret
4. Add to `.env`:
   ```bash
   AWS_ACCESS_KEY_ID=...
   AWS_SECRET_ACCESS_KEY=...
   AWS_REGION=us-east-1
   ```

---

## Features Overview

### ✅ Always Available (No API Keys Required)
- User authentication (JWT)
- Document upload (PDF, DOCX, images)
- OCR (with Tesseract)
- Basic file processing
- Database operations
- Library management

### 🔑 Requires API Keys

| Feature | Required Key | Fallback |
|---------|-------------|----------|
| **AI Document Generation** | OPENAI or ANTHROPIC or GOOGLE | Mock responses |
| **Jurisprudence Search** | None (structural) | Demo data |
| **Web Search** | GOOGLE_SEARCH or BING_SEARCH | Demo data |
| **Podcast/TTS** | GOOGLE_TTS or AWS_POLLY | gTTS (free, basic quality) |
| **Audio Transcription** | OPENAI_API_KEY | Whisper local (slow) |
| **Diagrams** | None | Frontend rendering |

---

## Testing

### Health Check
```bash
curl http://localhost:8000/health
```

### API Documentation
```
http://localhost:8000/docs
```

### Test Endpoints

**Register User:**
```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "password123",
    "name": "Test User",
    "account_type": "INDIVIDUAL"
  }'
```

**Upload Document:**
```bash
curl -X POST http://localhost:8000/api/documents/upload \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@document.pdf"
```

**Share Document:**
```bash
curl -X POST http://localhost:8000/api/documents/{doc_id}/share \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Search Jurisprudence:**
```bash
curl "http://localhost:8000/api/knowledge/jurisprudence/search?query=dano+moral" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## Production Deployment

### Database Migration
For production, use PostgreSQL:

```bash
# .env
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/iudex
```

Then run migration:
```bash
python scripts/migrate_database.py
```

### Using Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-por \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Run
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Using Docker Compose

```yaml
version: '3.8'

services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql+asyncpg://postgres:password@db:5432/iudex
    env_file:
      - .env
    depends_on:
      - db

  db:
    image: postgres:15
    environment:
      POSTGRES_DB: iudex
      POSTGRES_PASSWORD: password
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

---

## Troubleshooting

### Tesseract Not Found
```bash
# macOS
brew install tesseract tesseract-lang

# Ubuntu
sudo apt-get install tesseract-ocr tesseract-ocr-por
```

### FFmpeg Not Found
```bash
# macOS
brew install ffmpeg

# Ubuntu
sudo apt-get install ffmpeg
```

### Database Connection Error
Check that the database file exists or PostgreSQL is running:
```bash
# SQLite
ls -la iudex.db

# PostgreSQL
psql -h localhost -U postgres -l
```

### Import Errors
Reinstall dependencies:
```bash
pip install -r requirements.txt --force-reinstall
```

---

## Performance Optimization

### Enable Caching
Add Redis for caching search results:
```bash
REDIS_URL=redis://localhost:6379/0
```

### Background Tasks
Use Celery for async processing:
```bash
pip install celery[redis]
```

### Database Connection Pool
For PostgreSQL in production:
```bash
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=40
```

---

## Security Checklist

- [ ] Change `SECRET_KEY` to random value
- [ ] Use HTTPS in production (`CORS_ORIGINS=https://yourdomain.com`)
- [ ] Rotate API keys regularly
- [ ] Enable rate limiting
- [ ] Set up firewall rules
- [ ] Use environment variables, never commit `.env`
- [ ] Enable Sentry or error tracking
- [ ] Set up backup strategy for database
- [ ] Use strong passwords for PostgreSQL
- [ ] Enable API key restrictions (Google, etc.)

---

## Support

For issues or questions:
1. Check API documentation: `http://localhost:8000/docs`
2. Review logs: `tail -f logs/app.log`
3. Check `status.md` for implementation details
4. Refer to `implementation_plan.md` for architecture details
