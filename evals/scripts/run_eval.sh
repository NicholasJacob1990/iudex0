#!/bin/bash
# =============================================================================
# RAG Evaluation Script - Local Execution
# =============================================================================
# Usage:
#   ./evals/scripts/run_eval.sh [OPTIONS]
#
# Options:
#   --dataset PATH     Dataset file (default: evals/benchmarks/v1.0_legal_domain.jsonl)
#   --top-k N          Number of documents to retrieve (default: 8)
#   --with-llm         Enable LLM-based metrics (faithfulness, answer_relevancy)
#   --persist-db       Persist results to database
#   --min-precision N  Minimum context precision threshold (default: 0.70)
#   --min-recall N     Minimum context recall threshold (default: 0.65)
#
# Examples:
#   ./evals/scripts/run_eval.sh
#   ./evals/scripts/run_eval.sh --with-llm --persist-db
#   ./evals/scripts/run_eval.sh --dataset evals/sample_eval.jsonl --top-k 5
# =============================================================================

set -e

# Navigate to project root
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

# Default values
DATASET="evals/benchmarks/v1.0_legal_domain.jsonl"
TOP_K=8
WITH_LLM=""
PERSIST_DB=""
MIN_PRECISION="0.70"
MIN_RECALL="0.65"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dataset)
            DATASET="$2"
            shift 2
            ;;
        --top-k)
            TOP_K="$2"
            shift 2
            ;;
        --with-llm)
            WITH_LLM="--with-llm"
            shift
            ;;
        --persist-db)
            PERSIST_DB="--persist-db"
            shift
            ;;
        --min-precision)
            MIN_PRECISION="$2"
            shift 2
            ;;
        --min-recall)
            MIN_RECALL="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Generate output filename with timestamp
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_FILE="evals/results/${TIMESTAMP}.json"

# Create results directory if it doesn't exist
mkdir -p evals/results

echo "=============================================="
echo "RAG Evaluation - $(date)"
echo "=============================================="
echo "Dataset:     $DATASET"
echo "Top-K:       $TOP_K"
echo "Output:      $OUTPUT_FILE"
echo "LLM Metrics: ${WITH_LLM:-disabled}"
echo "Persist DB:  ${PERSIST_DB:-disabled}"
echo "Min Precision: $MIN_PRECISION"
echo "Min Recall:    $MIN_RECALL"
echo "=============================================="

# Check if dataset exists
if [ ! -f "$DATASET" ]; then
    echo "ERROR: Dataset file not found: $DATASET"
    exit 1
fi

# Check for required environment variables
if [ -z "$OPENAI_API_KEY" ] && [ -n "$WITH_LLM" ]; then
    echo "WARNING: OPENAI_API_KEY not set. LLM metrics may fail."
fi

# Run evaluation
echo ""
echo "Running evaluation..."
echo ""

python eval_rag.py \
    --dataset "$DATASET" \
    --top-k "$TOP_K" \
    --out "$OUTPUT_FILE" \
    --min-context-precision "$MIN_PRECISION" \
    --min-context-recall "$MIN_RECALL" \
    $WITH_LLM \
    $PERSIST_DB

EXIT_CODE=$?

echo ""
echo "=============================================="

if [ $EXIT_CODE -eq 0 ]; then
    echo "SUCCESS: Evaluation passed all thresholds"
    echo "Results saved to: $OUTPUT_FILE"

    # Generate report if eval_report.py exists
    if [ -f "eval_report.py" ]; then
        echo ""
        echo "Generating report..."
        REPORT_MD="evals/results/${TIMESTAMP}_report.md"
        REPORT_HTML="evals/results/${TIMESTAMP}_report.html"
        python eval_report.py --input "$OUTPUT_FILE" --md "$REPORT_MD" --html "$REPORT_HTML"
        echo "Report saved to: $REPORT_MD"
    fi
elif [ $EXIT_CODE -eq 2 ]; then
    echo "FAILED: Evaluation did not meet thresholds"
    echo "Results saved to: $OUTPUT_FILE"
else
    echo "ERROR: Evaluation failed with exit code $EXIT_CODE"
fi

echo "=============================================="

exit $EXIT_CODE
