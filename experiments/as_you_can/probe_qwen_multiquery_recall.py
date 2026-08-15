"""Measure whether qwen3-8b query diversification improves retriever recall.

Golden answers and supporting quotes are used only after retrieval for offline metrics.
They are never included in the query-generation prompt.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
import json
from pathlib import Path
from typing import Any

from experiments.as_you_can.final_template.tools.retriever_search.component import (
    RetrieverConfig,
    RetrieverSearchTool,
)
from search_harness.evaluation.hotpotqa import normalize_answer
from search_harness.framework import ChatMessage, ModelInput
from search_harness.integrations.openai_compatible import (
    OpenAICompatibleConfig,
    OpenAICompatibleModel,
)


SYSTEM = """Generate complementary corpus queries for a difficult factual question. Do not
answer it and do not add facts. Return exactly one JSON object:
{"anchor_query":"...","relation_query":"..."}
- anchor_query: the shortest distinctive named entity, title, event, work, organization, or
  quoted phrase explicitly present in the question; omit the requested property.
- relation_query: a concise standalone query preserving the requested relation and qualifiers,
  phrased differently from the previous query.
Both queries must be useful independently and must not contain a proposed answer."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--replicates", type=int, default=3)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--topk", type=int, default=5)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    student_config = OpenAICompatibleConfig.from_env(args.env_file, prefix="STUDENT")
    normalized_model = student_config.model_id.casefold().replace("-", "").replace(":", "")
    if "qwen3" not in normalized_model or "8b" not in normalized_model:
        raise RuntimeError(f"probe requires qwen3-8b, got {student_config.model_id!r}")
    retrieval_config = RetrieverConfig.from_env(args.env_file)

    rollouts = {
        item["example"]["example_id"]: item
        for item in _read_jsonl(args.run_root / "rollouts.jsonl")
    }
    judgments = {
        item["example_id"]: item
        for item in _read_jsonl(
            args.run_root / "evaluation_teacher" / "per_rollout.jsonl"
        )
    }
    failures = [
        record
        for example_id, record in rollouts.items()
        if judgments[example_id]["score"] == 0
    ]

    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [
            pool.submit(
                _probe,
                record,
                student_config,
                retrieval_config,
                replicate,
                args.topk,
            )
            for record in failures
            for replicate in range(args.replicates)
        ]
        for future in as_completed(futures):
            rows.append(future.result())

    rows.sort(key=lambda row: (str(row["example_id"]), int(row["replicate"])))
    summary = _summarize(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    args.output.with_suffix(".summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def _probe(
    record: dict[str, Any],
    student_config: OpenAICompatibleConfig,
    retrieval_config: RetrieverConfig,
    replicate: int,
    topk: int,
) -> dict[str, Any]:
    example = record["example"]
    interactions = record["run"]["state"].get("tool_interactions", [])
    previous_queries = [
        interaction["tool_call"]["arguments"].get("query", "")
        for interaction in interactions
    ]
    baseline_evidence = "\n".join(
        interaction["tool_result"]["content"] for interaction in interactions
    )
    seeded = replace(
        student_config, seed=(student_config.seed or 42) + replicate
    )
    response = OpenAICompatibleModel(seeded).generate(
        ModelInput.from_messages(
            [
                ChatMessage(role="system", content=SYSTEM),
                ChatMessage(
                    role="user",
                    content=(
                        f"Question: {example['question']}\n"
                        "Previous queries: "
                        + json.dumps(previous_queries, ensure_ascii=False)
                    ),
                ),
            ]
        )
    )
    queries, parse_error = _parse_queries(response.raw_output)
    tool = RetrieverSearchTool(retrieval_config)
    retrieved: list[dict[str, str]] = []
    for kind, query in queries.items():
        result = tool.search(query=query, topk=topk)
        retrieved.append({"kind": kind, "query": query, "content": result.content})
    alternate_evidence = "\n".join(item["content"] for item in retrieved)
    union_evidence = baseline_evidence + "\n" + alternate_evidence
    supporting_quotes = [
        item.get("quote", "")
        for item in (example.get("metadata") or {}).get("filter_evidence", [])
        if isinstance(item, dict) and item.get("quote")
    ]
    return {
        "example_id": example["example_id"],
        "replicate": replicate,
        "question": example["question"],
        "golden_answer": example["answer"],
        "previous_queries": previous_queries,
        "queries": queries,
        "parse_error": parse_error,
        "parse_valid": parse_error is None,
        "baseline_gold_present": _contains(baseline_evidence, example["answer"]),
        "alternate_gold_present": _contains(alternate_evidence, example["answer"]),
        "union_gold_present": _contains(union_evidence, example["answer"]),
        "baseline_supporting_quote_hits": _quote_hits(
            baseline_evidence, supporting_quotes
        ),
        "alternate_supporting_quote_hits": _quote_hits(
            alternate_evidence, supporting_quotes
        ),
        "union_supporting_quote_hits": _quote_hits(union_evidence, supporting_quotes),
        "supporting_quote_count": len(supporting_quotes),
        "retrieved": retrieved,
        "raw_output": response.raw_output,
        "usage": response.usage,
    }


def _parse_queries(raw: str) -> tuple[dict[str, str], str | None]:
    start = raw.find("{")
    if start < 0:
        return {}, "no JSON object"
    try:
        payload, _ = json.JSONDecoder().raw_decode(raw[start:])
    except json.JSONDecodeError as exc:
        return {}, f"invalid JSON: {exc.msg}"
    if not isinstance(payload, dict):
        return {}, "JSON value is not an object"
    result = {}
    for field in ("anchor_query", "relation_query"):
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            return {}, f"missing {field}"
        result[field] = value.strip()
    return result, None


def _contains(text: str, answer: str) -> bool:
    normalized_answer = normalize_answer(answer)
    return bool(normalized_answer and normalized_answer in normalize_answer(text))


def _quote_hits(text: str, quotes: list[str]) -> int:
    normalized_text = normalize_answer(text)
    return sum(
        bool(normalized_quote and normalized_quote in normalized_text)
        for quote in quotes
        if (normalized_quote := normalize_answer(quote))
    )


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    case_ids = sorted({str(row["example_id"]) for row in rows})
    absent_rows = [row for row in rows if not row["baseline_gold_present"]]
    improved_rows = [
        row
        for row in absent_rows
        if row["alternate_gold_present"] or row["alternate_supporting_quote_hits"] > 0
    ]
    stable_query_cases = 0
    recovered_any_cases = 0
    recovered_all_replicates = 0
    for example_id in case_ids:
        subset = [row for row in rows if row["example_id"] == example_id]
        query_pairs = {
            (row["queries"].get("anchor_query"), row["queries"].get("relation_query"))
            for row in subset
        }
        stable_query_cases += int(len(query_pairs) == 1)
        recovery = [
            bool(row["alternate_gold_present"] or row["alternate_supporting_quote_hits"] > 0)
            for row in subset
            if not row["baseline_gold_present"]
        ]
        recovered_any_cases += int(bool(recovery) and any(recovery))
        recovered_all_replicates += int(bool(recovery) and all(recovery))
    return {
        "failure_cases": len(case_ids),
        "calls": len(rows),
        "parse_valid_rate": sum(row["parse_valid"] for row in rows) / len(rows),
        "baseline_gold_absent_calls": len(absent_rows),
        "alternate_recovery_call_rate": (
            len(improved_rows) / len(absent_rows) if absent_rows else None
        ),
        "recovered_any_case_count": recovered_any_cases,
        "recovered_all_replicates_case_count": recovered_all_replicates,
        "stable_query_case_rate": stable_query_cases / len(case_ids) if case_ids else None,
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


if __name__ == "__main__":
    main()
