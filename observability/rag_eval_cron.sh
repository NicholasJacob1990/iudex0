#!/bin/sh
set -e

CRON="${RAG_EVAL_CRON:-0 2 * * *}"
DATASET="${RAG_EVAL_DATASET:-/app/evals/sample_eval.jsonl}"
OUT="${RAG_EVAL_OUT:-/app/evals/eval_results.json}"

echo "$CRON python /app/eval_rag.py --dataset $DATASET --persist-db --out $OUT" > /etc/cron.d/rag-eval

exec /usr/local/bin/supercronic /etc/cron.d/rag-eval
