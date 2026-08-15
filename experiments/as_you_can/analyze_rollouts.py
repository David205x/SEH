"""Create a compact, deterministic failure report from rollout JSONL."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from search_harness.evaluation.hotpotqa import normalize_answer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rollouts", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records = [
        json.loads(line)
        for line in args.rollouts.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    lines = ["# Rollout failure report", ""]
    exact_count = 0
    for index, record in enumerate(records):
        example = record["example"]
        run = record.get("run") or {}
        answer = run.get("answer") or ""
        golden = example.get("answer") or ""
        exact = normalize_answer(answer) == normalize_answer(golden)
        exact_count += int(exact)
        interactions = (run.get("state") or {}).get("tool_interactions") or []
        queries = [
            interaction["tool_call"]["arguments"].get("query", "")
            for interaction in interactions
        ]
        evidence = "\n".join(
            interaction["tool_result"].get("content", "")
            for interaction in interactions
        )
        golden_in_evidence = bool(golden) and normalize_answer(golden) in normalize_answer(
            evidence
        )
        status = "PASS" if exact else "FAIL"
        metadata = example.get("metadata") or {}
        lines.extend(
            [
                f"## {index:02d} {status} · {metadata.get('level')} / {metadata.get('type')}",
                "",
                f"- id: `{example.get('example_id')}`",
                f"- question: {example.get('question')}",
                f"- golden: `{golden}`",
                f"- predicted: `{answer}`",
                f"- golden literal present in retrieved evidence: `{golden_in_evidence}`",
                f"- queries: `{json.dumps(queries, ensure_ascii=False)}`",
                "",
            ]
        )
    lines[1:1] = [
        f"Exact match: {exact_count}/{len(records)} "
        f"({exact_count / len(records):.3f})",
        "",
    ]
    report = "\n".join(lines)
    output = args.output or args.rollouts.with_name("failure_report.md")
    output.write_text(report, encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
