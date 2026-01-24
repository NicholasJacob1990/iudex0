# Iudex MVP (FastAPI + OpenSearch + Qdrant)

This project gives you:
- Local ingestion (PDF/TXT/MD) -> OpenSearch (lexical) + Qdrant (vector)
- Search (lexical + vector) merged by chunk_uid
- TTL cleanup for local data (7 days) via background job (every 6 hours)

## 1) Start OpenSearch + Dashboards + Qdrant
1) Copy `.env.example` -> `.env`
2) Set `OPENSEARCH_INITIAL_ADMIN_PASSWORD` and `OPENAI_API_KEY`
3) Run:
```bash
docker compose up -d
```

OpenSearch API: https://localhost:9200 (demo certs)
Dashboards: http://localhost:5601
Qdrant: http://localhost:6333

## 2) Run the FastAPI app
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# export env vars (simple approach for MVP)
export $(grep -v '^#' .env | xargs)

uvicorn app.main:app --reload --port 8000
```

## 3) Ingest local (curl)
```bash
curl -X POST "http://localhost:8000/local/ingest"   -F tenant_id="t1"   -F case_id="case-123"   -F doc_id="doc-1"   -F doc_hash="abc123"   -F sigilo="publico"   -F allowed_users="user-1,user-2"   -F group_ids="group-a"   -F file=@./some.pdf
```

## 4) Search (curl)
```bash
curl -X POST "http://localhost:8000/search"   -H "Content-Type: application/json"   -d '{
    "query":"qual o prazo do agravo interno?",
    "tenant_id":"t1",
    "case_id":"case-123",
    "group_ids":["group-a"],
    "user_id":"user-1",
    "top_k": 10,
    "include_global": true,
    "include_private": true,
    "include_group": true,
    "include_local": true
  }'
```

## Notes
- OpenSearch demo config uses self-signed TLS. The client disables cert verification for local dev.
- Qdrant local TTL is implemented with a background cleanup job. In production, you can move it to cron.
- Embeddings use `text-embedding-3-large` via OpenAI API.
  You can optionally shorten vectors (still using the same model) by setting `OPENAI_EMBEDDING_DIMENSIONS`.
