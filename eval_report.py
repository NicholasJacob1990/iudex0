#!/usr/bin/env python3
import argparse
import json
from datetime import datetime
from typing import Any, Dict, List


def _load(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _build_markdown(payload: Dict[str, Any]) -> str:
    summary = payload.get("summary") or {}
    samples = payload.get("samples") or []
    lines: List[str] = []
    lines.append("# RAG Eval Report")
    lines.append("")
    lines.append(f"- Dataset: `{payload.get('dataset')}`")
    lines.append(f"- Timestamp: `{payload.get('ts')}`")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | --- |")
    for key in ("context_precision", "context_recall", "faithfulness", "answer_relevancy"):
        if key in summary:
            lines.append(f"| {key} | {summary.get(key):.4f} |")
    lines.append("")
    if samples:
        lines.append("## Samples")
        lines.append("")
        lines.append("| Question | context_precision | context_recall | faithfulness | answer_relevancy |")
        lines.append("| --- | --- | --- | --- | --- |")
        for row in samples:
            q = str(row.get("question") or row.get("query") or "")
            cp = row.get("context_precision")
            cr = row.get("context_recall")
            fa = row.get("faithfulness")
            ar = row.get("answer_relevancy")
            lines.append(
                f"| {q[:120]} | {cp if cp is not None else ''} | {cr if cr is not None else ''} | "
                f"{fa if fa is not None else ''} | {ar if ar is not None else ''} |"
            )
        lines.append("")
    return "\n".join(lines)


def _build_html(payload: Dict[str, Any]) -> str:
    summary = payload.get("summary") or {}
    samples = payload.get("samples") or []
    def _cell(val: Any) -> str:
        return "" if val is None else f"{val}"
    summary_rows = ""
    for key in ("context_precision", "context_recall", "faithfulness", "answer_relevancy"):
        if key in summary:
            summary_rows += f"<tr><td>{key}</td><td>{summary.get(key):.4f}</td></tr>"
    sample_rows = ""
    for row in samples:
        q = str(row.get("question") or row.get("query") or "")[:120]
        sample_rows += (
            "<tr>"
            f"<td>{q}</td>"
            f"<td>{_cell(row.get('context_precision'))}</td>"
            f"<td>{_cell(row.get('context_recall'))}</td>"
            f"<td>{_cell(row.get('faithfulness'))}</td>"
            f"<td>{_cell(row.get('answer_relevancy'))}</td>"
            "</tr>"
        )
    return f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>RAG Eval Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; padding: 24px; }}
    table {{ border-collapse: collapse; width: 100%; margin-bottom: 24px; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; }}
    th {{ background: #f4f4f4; text-align: left; }}
  </style>
</head>
<body>
  <h1>RAG Eval Report</h1>
  <p><b>Dataset:</b> {payload.get("dataset")}</p>
  <p><b>Timestamp:</b> {payload.get("ts")}</p>
  <h2>Summary</h2>
  <table>
    <tr><th>Metric</th><th>Value</th></tr>
    {summary_rows}
  </table>
  <h2>Samples</h2>
  <table>
    <tr>
      <th>Question</th>
      <th>context_precision</th>
      <th>context_recall</th>
      <th>faithfulness</th>
      <th>answer_relevancy</th>
    </tr>
    {sample_rows}
  </table>
</body>
</html>
""".strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="evals/eval_results.json")
    parser.add_argument("--md", default="evals/eval_report.md")
    parser.add_argument("--html", default="evals/eval_report.html")
    args = parser.parse_args()

    payload = _load(args.input)
    with open(args.md, "w", encoding="utf-8") as f:
        f.write(_build_markdown(payload))
    with open(args.html, "w", encoding="utf-8") as f:
        f.write(_build_html(payload))
    print(f"Report generated at {args.md} and {args.html} ({datetime.utcnow().isoformat()})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
