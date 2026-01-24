Metabase seed (starter)

1) Create a collection named "RAG Eval".
2) For each query in `rag_eval_questions.sql`, create a SQL question:
   - Set the parameter `dataset` (e.g. `evals/sample_eval.jsonl`).
3) Save the questions in the "RAG Eval" collection.
4) Build a dashboard with the three trend questions + "Latest Run".

Tip: Use the SQL in `observability/metabase/rag_eval_questions.sql` as the seed.
