FROM python:3.11-slim

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL https://github.com/aptible/supercronic/releases/download/v0.2.24/supercronic-linux-amd64 \
    -o /usr/local/bin/supercronic && chmod +x /usr/local/bin/supercronic

WORKDIR /app
COPY eval_rag.py /app/eval_rag.py
COPY evals /app/evals
COPY apps /app/apps
COPY observability/rag_eval_cron.sh /app/rag_eval_cron.sh

RUN pip install --no-cache-dir ragas datasets chromadb sentence-transformers rank_bm25 sqlalchemy asyncpg

CMD ["/bin/sh", "/app/rag_eval_cron.sh"]
