-- Metabase Question: Latest RAG Eval
SELECT
  created_at,
  dataset,
  context_precision,
  context_recall,
  faithfulness,
  answer_relevancy
FROM rag_eval_metrics
WHERE dataset = {{dataset}}
ORDER BY created_at DESC
LIMIT 1;

-- Metabase Question: Trend (Context Precision/Recall)
SELECT
  created_at AS ts,
  context_precision,
  context_recall
FROM rag_eval_metrics
WHERE dataset = {{dataset}}
ORDER BY created_at;

-- Metabase Question: Trend (Faithfulness/Answer Relevancy)
SELECT
  created_at AS ts,
  faithfulness,
  answer_relevancy
FROM rag_eval_metrics
WHERE dataset = {{dataset}}
ORDER BY created_at;

-- Metabase Question: Compare Last 2 Runs
WITH last_two AS (
  SELECT *
  FROM rag_eval_metrics
  WHERE dataset = {{dataset}}
  ORDER BY created_at DESC
  LIMIT 2
)
SELECT
  created_at,
  context_precision,
  context_recall,
  faithfulness,
  answer_relevancy
FROM last_two
ORDER BY created_at;
