"""Probe qwen3-8b evidence sufficiency, extraction, quoting, and query planning.

The probe reads frozen rollouts only. Golden answers are used after generation for
measurement and are never included in Student prompts.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
import json
from pathlib import Path
import re
from typing import Any

from search_harness.evaluation.hotpotqa import normalize_answer
from search_harness.framework import ChatMessage, ModelInput
from search_harness.integrations.openai_compatible import (
    OpenAICompatibleConfig,
    OpenAICompatibleModel,
)


SYSTEM = """You are an evidence controller, not a free-form question answerer.
Given one factual question and the evidence returned by exactly one search, decide whether the
evidence directly supports the requested answer. Preserve relation direction, answer type,
qualifiers, comparison attribute, and geographic granularity.

Return exactly one JSON object with these fields:
{"action":"synthesize|search","answer_candidate":"minimal answer or empty","quote":"exact evidence substring or empty","missing_relation":"what is still unsupported or empty","next_query":"standalone entity-centered query or empty"}

Use synthesize only when the quote directly supports the answer_candidate for the original
question. The quote must be copied verbatim from the supplied evidence. Otherwise use search,
leave answer_candidate and quote empty, and provide a focused next_query. Never use outside
knowledge. Never treat missing evidence as evidence for no."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rollouts", type=Path, required=True)
    parser.add_argument("--judgments", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--cases", type=int, default=18)
    parser.add_argument("--replicates", type=int, default=3)
    parser.add_argument("--workers", type=int, default=6)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = OpenAICompatibleConfig.from_env(args.env_file, prefix="STUDENT")
    normalized_model = config.model_id.casefold().replace("-", "").replace(":", "")
    if "qwen3" not in normalized_model or "8b" not in normalized_model:
        raise RuntimeError(f"probe requires qwen3-8b, got {config.model_id!r}")

    rollouts = _read_jsonl(args.rollouts)
    judgments = {
        item["example_id"]: item for item in _read_jsonl(args.judgments)
    }
    cases = _select_cases(rollouts, judgments, args.cases)

    futures = []
    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for case in cases:
            for replicate in range(args.replicates):
                futures.append(
                    pool.submit(_run_probe, case, config, replicate)
                )
        for future in as_completed(futures):
            rows.append(future.result())

    rows.sort(key=lambda row: (str(row["example_id"]), int(row["replicate"])))
    summary = _summarize(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    summary_path = args.output.with_suffix(".summary.json")
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def _select_cases(
    rollouts: list[dict[str, Any]],
    judgments: dict[str, dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {
        "wrong_present": [],
        "wrong_absent": [],
        "right_present": [],
    }
    for record in rollouts:
        example = record["example"]
        example_id = example["example_id"]
        interactions = record["run"]["state"].get("tool_interactions", [])
        if not interactions:
            continue
        first_evidence = interactions[0]["tool_result"]["content"]
        present = _normalized_contains(first_evidence, example["answer"])
        correct = judgments[example_id]["score"] == 1
        bucket = (
            "right_present"
            if correct and present
            else "wrong_present"
            if present
            else "wrong_absent"
        )
        if bucket in buckets:
            buckets[bucket].append(
                {
                    "example_id": example_id,
                    "question": example["question"],
                    "golden_answer": example["answer"],
                    "first_query": interactions[0]["tool_call"]["arguments"].get(
                        "query", ""
                    ),
                    "evidence": first_evidence[:7000],
                    "gold_present": present,
                    "baseline_correct": correct,
                    "bucket": bucket,
                }
            )

    # Balance capability positives, retrieval negatives, and known synthesis failures.
    quotas = {
        "wrong_present": limit // 3,
        "wrong_absent": limit // 3,
        "right_present": limit - 2 * (limit // 3),
    }
    selected: list[dict[str, Any]] = []
    for name, quota in quotas.items():
        selected.extend(sorted(buckets[name], key=lambda item: item["example_id"])[:quota])
    return selected


def _run_probe(
    case: dict[str, Any],
    config: OpenAICompatibleConfig,
    replicate: int,
) -> dict[str, Any]:
    seeded = replace(config, seed=(config.seed or 42) + replicate)
    user = (
        f"Original question: {case['question']}\n"
        f"Previous query: {case['first_query']}\n"
        f"Retrieved evidence:\n{case['evidence']}"
    )
    response = OpenAICompatibleModel(seeded).generate(
        ModelInput.from_messages(
            [
                ChatMessage(role="system", content=SYSTEM),
                ChatMessage(role="user", content=user),
            ]
        )
    )
    parsed, parse_error = _parse(response.raw_output)
    expected_action = "synthesize" if case["gold_present"] else "search"
    action = parsed.get("action", "")
    answer = parsed.get("answer_candidate", "")
    quote = parsed.get("quote", "")
    next_query = parsed.get("next_query", "")
    return {
        "example_id": case["example_id"],
        "replicate": replicate,
        "bucket": case["bucket"],
        "question": case["question"],
        "golden_answer": case["golden_answer"],
        "gold_present": case["gold_present"],
        "baseline_correct": case["baseline_correct"],
        "first_query": case["first_query"],
        "expected_action": expected_action,
        "parsed": parsed,
        "parse_error": parse_error,
        "parse_valid": parse_error is None,
        "action_correct": action == expected_action,
        "answer_exact_match": (
            normalize_answer(answer) == normalize_answer(case["golden_answer"])
            if answer
            else False
        ),
        "quote_valid": bool(quote and quote in case["evidence"]),
        "query_nonempty_when_search": action != "search" or bool(next_query.strip()),
        "query_novel_when_search": (
            action != "search"
            or normalize_answer(next_query) != normalize_answer(case["first_query"])
        ),
        "raw_output": response.raw_output,
        "usage": response.usage,
    }


def _parse(raw: str) -> tuple[dict[str, str], str | None]:
    start = raw.find("{")
    if start < 0:
        return {}, "no JSON object"
    try:
        payload, _ = json.JSONDecoder().raw_decode(raw[start:])
    except json.JSONDecodeError as exc:
        return {}, f"invalid JSON: {exc.msg}"
    if not isinstance(payload, dict):
        return {}, "JSON value is not an object"
    action = payload.get("action")
    if action not in {"synthesize", "search"}:
        return {}, "invalid action"
    fields = (
        "action",
        "answer_candidate",
        "quote",
        "missing_relation",
        "next_query",
    )
    parsed = {
        field: payload.get(field, "").strip()
        if isinstance(payload.get(field, ""), str)
        else ""
        for field in fields
    }
    return parsed, None


def _normalized_contains(text: str, answer: str) -> bool:
    normalized_text = normalize_answer(text)
    normalized_answer = normalize_answer(answer)
    return bool(normalized_answer and normalized_answer in normalized_text)


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def rate(field: str, subset: list[dict[str, Any]]) -> float | None:
        return (
            sum(bool(item[field]) for item in subset) / len(subset) if subset else None
        )

    synthesize_rows = [row for row in rows if row["gold_present"]]
    search_rows = [row for row in rows if not row["gold_present"]]
    by_bucket = {}
    for bucket in sorted({str(row["bucket"]) for row in rows}):
        subset = [row for row in rows if row["bucket"] == bucket]
        by_bucket[bucket] = {
            "count": len(subset),
            "parse_valid_rate": rate("parse_valid", subset),
            "action_accuracy": rate("action_correct", subset),
            "answer_exact_match_rate": rate("answer_exact_match", subset),
            "quote_valid_rate": rate("quote_valid", subset),
        }
    stable_cases = 0
    for example_id in {str(row["example_id"]) for row in rows}:
        outputs = [
            (
                row["parsed"].get("action", ""),
                normalize_answer(row["parsed"].get("answer_candidate", "")),
                normalize_answer(row["parsed"].get("next_query", "")),
            )
            for row in rows
            if row["example_id"] == example_id
        ]
        stable_cases += int(len(set(outputs)) == 1)
    case_count = len({str(row["example_id"]) for row in rows})
    return {
        "cases": case_count,
        "calls": len(rows),
        "parse_valid_rate": rate("parse_valid", rows),
        "action_accuracy": rate("action_correct", rows),
        "sufficiency_positive_action_accuracy": rate(
            "action_correct", synthesize_rows
        ),
        "sufficiency_negative_action_accuracy": rate("action_correct", search_rows),
        "answer_exact_match_when_gold_present": rate(
            "answer_exact_match", synthesize_rows
        ),
        "quote_valid_when_gold_present": rate("quote_valid", synthesize_rows),
        "next_query_nonempty_when_gold_absent": rate(
            "query_nonempty_when_search", search_rows
        ),
        "next_query_novel_when_gold_absent": rate(
            "query_novel_when_search", search_rows
        ),
        "fully_stable_case_rate": stable_cases / case_count if case_count else None,
        "by_bucket": by_bucket,
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


if __name__ == "__main__":
    main()
