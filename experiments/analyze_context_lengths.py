"""Summarize exact provider token usage from historical rollout traces."""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ModelCallUsage:
    source_file: str
    example_id: str
    question: str
    step: int
    event_type: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=[Path("runs")],
        help="Rollout JSONL files or directories; default: runs.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional UTF-8 JSON output file.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    files = discover_rollout_files(args.paths)
    usages, uncovered = collect_usage(files)
    report = build_report(files, usages, uncovered)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")


def discover_rollout_files(paths: list[Path]) -> list[Path]:
    """Discover Actor rollout JSONL and Intervention branch artifacts."""

    files: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved.is_file():
            files.add(resolved)
            continue
        if not resolved.is_dir():
            raise FileNotFoundError(path)
        files.update(
            candidate
            for candidate in resolved.rglob("*.jsonl")
            if "rollout" in candidate.name.casefold()
        )
        files.update(resolved.rglob("intervention.json"))
    return sorted(files)


def collect_usage(
    files: list[Path],
) -> tuple[list[ModelCallUsage], int]:
    """Collect exact model-call token usage and count calls without usage."""

    usages: list[ModelCallUsage] = []
    uncovered = 0
    for path in files:
        if path.name == "intervention.json":
            artifact = json.loads(path.read_text(encoding="utf-8"))
            branch_run = artifact.get("branch_run")
            if not isinstance(branch_run, dict):
                continue
            source = artifact.get("source")
            source = source if isinstance(source, dict) else {}
            found, missing = _collect_run_usage(
                path=path,
                run=branch_run,
                example_id=str(source.get("example_id", "")),
                question=str(branch_run.get("question", "")),
            )
            usages.extend(found)
            uncovered += missing
            continue
        with path.open("r", encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):
                if not line.strip():
                    continue
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ValueError(f"{path}:{line_number}: record must be an object")
                run = record.get("run")
                if not isinstance(run, dict):
                    continue
                example = record.get("example")
                example = example if isinstance(example, dict) else {}
                found, missing = _collect_run_usage(
                    path=path,
                    run=run,
                    example_id=str(example.get("example_id", "")),
                    question=str(example.get("question", run.get("question", ""))),
                )
                usages.extend(found)
                uncovered += missing
    return usages, uncovered


def _collect_run_usage(
    *,
    path: Path,
    run: dict[str, Any],
    example_id: str,
    question: str,
) -> tuple[list[ModelCallUsage], int]:
    usages: list[ModelCallUsage] = []
    uncovered = 0
    for event in run.get("trace", []):
        if not isinstance(event, dict) or event.get("event_type") not in {
            "model_output",
            "hook_model_output",
        }:
            continue
        usage = _event_usage(event)
        if usage is None:
            uncovered += 1
            continue
        usages.append(
            ModelCallUsage(
                source_file=str(path),
                example_id=example_id,
                question=question,
                step=int(event.get("step", 0)),
                event_type=str(event["event_type"]),
                prompt_tokens=usage[0],
                completion_tokens=usage[1],
                total_tokens=usage[2],
            )
        )
    return usages, uncovered


def build_report(
    files: list[Path], usages: list[ModelCallUsage], uncovered: int
) -> dict[str, Any]:
    by_file: dict[str, list[ModelCallUsage]] = defaultdict(list)
    by_step: dict[int, list[ModelCallUsage]] = defaultdict(list)
    by_event: dict[str, list[ModelCallUsage]] = defaultdict(list)
    for usage in usages:
        by_file[usage.source_file].append(usage)
        by_step[usage.step].append(usage)
        by_event[usage.event_type].append(usage)

    return {
        "schema_version": 1,
        "files": len(files),
        "model_calls": len(usages),
        "calls_without_usage": uncovered,
        "coverage_rate": (
            len(usages) / (len(usages) + uncovered)
            if usages or uncovered
            else None
        ),
        "overall": _summarize(usages),
        "by_event_type": {
            event_type: _summarize(values)
            for event_type, values in sorted(by_event.items())
        },
        "by_step": {
            str(step): _summarize(values)
            for step, values in sorted(by_step.items())
        },
        "by_file": {
            path: _summarize(values)
            for path, values in sorted(by_file.items())
        },
        "largest_calls": [
            asdict(usage)
            for usage in sorted(
                usages, key=lambda item: item.total_tokens, reverse=True
            )[:10]
        ],
    }


def _event_usage(event: dict[str, Any]) -> tuple[int, int, int] | None:
    payload = event.get("payload")
    payload = payload if isinstance(payload, dict) else {}
    metadata = payload.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    usage = metadata.get("usage")
    if not isinstance(usage, dict):
        return None
    prompt = usage.get("prompt_tokens", usage.get("prompt_eval_count"))
    completion = usage.get("completion_tokens", usage.get("eval_count"))
    total = usage.get("total_tokens")
    if not isinstance(prompt, int) or not isinstance(completion, int):
        return None
    if not isinstance(total, int):
        total = prompt + completion
    return prompt, completion, total


def _summarize(usages: list[ModelCallUsage]) -> dict[str, Any]:
    return {
        "calls": len(usages),
        "prompt_tokens": _distribution([item.prompt_tokens for item in usages]),
        "completion_tokens": _distribution(
            [item.completion_tokens for item in usages]
        ),
        "total_tokens": _distribution([item.total_tokens for item in usages]),
    }


def _distribution(values: list[int]) -> dict[str, int | float | None]:
    if not values:
        return {
            "mean": None,
            "p50": None,
            "p90": None,
            "p95": None,
            "p99": None,
            "max": None,
        }
    ordered = sorted(values)
    return {
        "mean": round(sum(ordered) / len(ordered), 2),
        "p50": _percentile(ordered, 0.50),
        "p90": _percentile(ordered, 0.90),
        "p95": _percentile(ordered, 0.95),
        "p99": _percentile(ordered, 0.99),
        "max": ordered[-1],
    }


def _percentile(ordered: list[int], quantile: float) -> int:
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[index]


if __name__ == "__main__":
    main()
