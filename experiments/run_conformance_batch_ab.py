"""Compare saved per-replicate Conformance with shadow example-level batches."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from statistics import mean
from typing import Any, Sequence

from pydantic import ValidationError

from experiments.teacher_query_views.conformance import (
    ShadowConformanceBatch,
    build_shadow_conformance_input,
    render_shadow_conformance_input,
    validate_shadow_batch,
)
from search_harness._internal import read_runtime_config, teacher_role_budget
from search_harness.evolution.research.roles.contracts import ConformanceReview
from search_harness.integrations.openai_compatible import (
    NativeToolRunExhausted,
    OpenAICompatibleConfig,
    OpenAICompatibleToolRunner,
)


_ROOT = Path(__file__).resolve().parents[1]
_SHADOW_PROMPT = (
    _ROOT
    / "experiments"
    / "teacher_query_views"
    / "templates"
    / "conformance_reviewer_batch"
    / "prompt"
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument(
        "--variant",
        action="append",
        choices=("batch_full_reference", "batch_compact_reference"),
        default=[],
    )
    parser.add_argument("--example-limit", type=int)
    return parser.parse_args(argv)


async def run_ab(args: argparse.Namespace) -> dict[str, Any]:
    if args.repetitions < 1:
        raise ValueError("repetitions must be positive")
    variants = args.variant or [
        "batch_full_reference",
        "batch_compact_reference",
    ]
    checkpoint_dir = args.checkpoint_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    sources = sorted((checkpoint_dir / "findings").glob("finding_*.json"))
    if not sources:
        raise ValueError(f"checkpoint has no findings: {checkpoint_dir}")
    source_hashes_before = {str(path): _digest(path) for path in sources}
    cases = _load_cases(sources)
    if args.example_limit is not None:
        cases = cases[: args.example_limit]
    config, max_turns = _teacher_config(args.env_file)
    records = []
    for case_index, case in enumerate(cases, start=1):
        formal = _formal_case_summary(case)
        runs = []
        for repetition in range(1, args.repetitions + 1):
            results = await asyncio.gather(
                *(
                    _run_variant(
                        variant=variant,
                        case=case,
                        config=config,
                        max_turns=max_turns,
                        artifact_path=(
                            output_dir
                            / f"case_{case_index:02d}_{case['example_id']}"
                            / f"{variant}_{repetition:02d}.json"
                        ),
                    )
                    for variant in variants
                )
            )
            runs.append(
                {
                    "repetition": repetition,
                    **dict(zip(variants, results, strict=True)),
                }
            )
        records.append(
            {
                "example_id": case["example_id"],
                "formal": formal,
                "runs": runs,
            }
        )
    summary = _summarize(records, variants)
    source_hashes_after = {str(path): _digest(path) for path in sources}
    summary.update(
        {
            "schema_version": 1,
            "experiment": "conformance_example_batch_ab_v1",
            "checkpoint_dir": str(checkpoint_dir),
            "pairing": (
                "Every shadow variant uses the exact Mechanism and saved "
                "candidate trajectory views from the formal findings. Full "
                "reference preserves the formal reference observations; compact "
                "reference changes only their model-visible projection. No "
                "Student rollout is executed."
            ),
            "records": records,
            "source_hashes_before": source_hashes_before,
            "source_hashes_after": source_hashes_after,
            "source_artifacts_unchanged": source_hashes_before == source_hashes_after,
        }
    )
    _write_json(output_dir / "summary.json", summary)
    return summary


async def _run_variant(
    *,
    variant: str,
    case: dict[str, Any],
    config: OpenAICompatibleConfig,
    max_turns: int,
    artifact_path: Path,
) -> dict[str, Any]:
    compact_references = variant == "batch_compact_reference"
    role_input = build_shadow_conformance_input(
        mechanism=deepcopy(case["mechanism"]),
        trial_refs=list(case["trial_refs"]),
        reference_observations=deepcopy(case["reference_observations"]),
        example_id=str(case["example_id"]),
        trajectories=deepcopy(case["trajectories"]),
        compact_references=compact_references,
    )
    expected_ids = [
        str(item["replicate_id"]) for item in case["trajectories"]
    ]
    messages = [
        {
            "role": "system",
            "content": (_SHADOW_PROMPT / "system.md").read_text(
                encoding="utf-8"
            ),
        },
        {"role": "user", "content": render_shadow_conformance_input(role_input)},
    ]

    def submit(arguments: dict[str, Any]) -> tuple[object | None, str, dict[str, Any]]:
        try:
            output = ShadowConformanceBatch.model_validate(arguments)
            validate_shadow_batch(output, expected_replicate_ids=expected_ids)
        except (ValidationError, ValueError) as exc:
            return None, (
                "Structured batch validation failed. Preserve valid findings, "
                f"repair the complete batch, and submit again:\n{exc}"
            ), {"terminal": False, "validation_error": True}
        return output, json.dumps(
            output.model_dump(mode="json"), ensure_ascii=False
        ), {"terminal": True}

    status = "completed"
    error = None
    output: dict[str, Any] | None = None
    usage: dict[str, Any] = {}
    transcript: list[dict[str, Any]] = []
    tool_calls: list[dict[str, Any]] = []
    try:
        result = await OpenAICompatibleToolRunner(config=config).run(
            messages=messages,
            tools=(),
            terminal_tool_name="submit_conformance_batch",
            terminal_tool_description=(
                "Submit exactly one independently validated Conformance finding "
                "for every supplied replicate."
            ),
            terminal_output_schema=ShadowConformanceBatch.model_json_schema(),
            missing_terminal_message=(
                "Submit the complete batch through submit_conformance_batch."
            ),
            submit_terminal=submit,
            max_turns=max_turns,
            run_label=f"shadow Conformance {variant}",
        )
        output = result.output.model_dump(mode="json")
        usage = result.usage
        transcript = result.transcript
        tool_calls = [item.__dict__ for item in result.tool_calls]
    except NativeToolRunExhausted as exc:
        status = "failed"
        error = str(exc)
        usage = exc.failure.usage
        transcript = exc.failure.transcript
        tool_calls = [item.__dict__ for item in exc.failure.tool_calls]
    artifact = {
        "schema_version": 1,
        "variant": variant,
        "status": status,
        "input": role_input,
        "input_characters": sum(len(str(item["content"])) for item in messages),
        "output": output,
        "error": error,
        "usage": usage,
        "tool_calls": tool_calls,
        "transcript": transcript,
    }
    _write_json(artifact_path, artifact)
    return {
        "artifact": str(artifact_path.resolve()),
        "status": status,
        "metrics": _metrics(artifact, case),
        "findings": output.get("findings") if isinstance(output, dict) else None,
    }


def _load_cases(paths: list[Path]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for path in paths:
        checkpoint = _read_json(path)
        artifact = _required_object(checkpoint, "role_artifact")
        role_input = _required_object(artifact, "input")
        example_id = str(role_input["example_id"])
        if example_id not in grouped:
            order.append(example_id)
            grouped[example_id] = []
        grouped[example_id].append(
            {"path": path, "checkpoint": checkpoint, "input": role_input}
        )
    cases = []
    for example_id in order:
        items = sorted(grouped[example_id], key=lambda item: item["input"]["replicate_id"])
        first = items[0]["input"]
        cases.append(
            {
                "example_id": example_id,
                "mechanism": first["mechanism"],
                "trial_refs": first["trial_refs"],
                "reference_observations": first["reference_observations"],
                "trajectories": [
                    {
                        "replicate_id": item["input"]["replicate_id"],
                        "candidate_trajectory_view": item["input"]["candidate_trajectory_view"],
                    }
                    for item in items
                ],
                "formal_items": items,
            }
        )
    return cases


def _formal_case_summary(case: dict[str, Any]) -> dict[str, Any]:
    findings = [item["checkpoint"]["output"] for item in case["formal_items"]]
    usages = [
        item["checkpoint"].get("role_artifact", {}).get("usage", {})
        for item in case["formal_items"]
    ]
    role_inputs = [item["input"] for item in case["formal_items"]]
    return {
        "finding_artifacts": [str(item["path"]) for item in case["formal_items"]],
        "findings": findings,
        "metrics": {
            "completed": True,
            "input_characters": sum(
                len(json.dumps(item, ensure_ascii=False)) for item in role_inputs
            ),
            "input_tokens": sum(_int(item.get("input_tokens")) for item in usages),
            "output_tokens": sum(_int(item.get("output_tokens")) for item in usages),
            "total_tokens": sum(_int(item.get("total_tokens")) for item in usages),
            "requests": sum(_int(item.get("requests")) for item in usages),
        },
    }


def _metrics(artifact: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    usage = artifact.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    output = artifact.get("output")
    findings = output.get("findings") if isinstance(output, dict) else []
    findings = findings if isinstance(findings, list) else []
    formal = [item["checkpoint"]["output"] for item in case["formal_items"]]
    pairs = list(zip(formal, findings, strict=False))
    return {
        "completed": artifact.get("status") == "completed",
        "finding_count": len(findings),
        "input_characters": artifact.get("input_characters"),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "requests": usage.get("requests"),
        "verdict_agreement": sum(a.get("verdict") == b.get("verdict") for a, b in pairs),
        "failure_layer_agreement": sum(
            a.get("failure_layer") == b.get("failure_layer") for a, b in pairs
        ),
        "route_agreement": sum(
            a.get("recommended_route") == b.get("recommended_route")
            for a, b in pairs
        ),
    }


def _summarize(records: list[dict[str, Any]], variants: list[str]) -> dict[str, Any]:
    formal_metrics = [record["formal"]["metrics"] for record in records]
    result: dict[str, Any] = {
        "formal_saved": _aggregate(formal_metrics),
        "variants": {},
    }
    for variant in variants:
        values = [
            run[variant]["metrics"]
            for record in records
            for run in record["runs"]
        ]
        aggregate = _aggregate(values)
        aggregate["total_token_ratio_vs_formal_saved"] = _ratio(
            aggregate["means"].get("total_tokens"),
            result["formal_saved"]["means"].get("total_tokens"),
        )
        result["variants"][variant] = aggregate
    return result


def _aggregate(values: list[dict[str, Any]]) -> dict[str, Any]:
    numeric = sorted(
        {
            key
            for item in values
            for key, value in item.items()
            if key != "completed" and isinstance(value, (int, float))
        }
    )
    return {
        "runs": len(values),
        "completed": sum(bool(item.get("completed")) for item in values),
        "means": {
            key: round(mean(float(item[key]) for item in values if item.get(key) is not None), 2)
            for key in numeric
        },
    }


def _teacher_config(env_file: Path) -> tuple[OpenAICompatibleConfig, int]:
    config = OpenAICompatibleConfig.from_env(env_file=env_file, prefix="TEACHER")
    budget = teacher_role_budget(
        read_runtime_config(env_file=env_file),
        "conformance_reviewer",
        default_max_tokens=config.max_tokens,
        default_max_turns=20,
        default_thinking_mode=config.thinking_mode,
    )
    return replace(
        config,
        max_tokens=budget.max_tokens,
        thinking_mode=budget.thinking_mode if config.thinking_mode is not None else None,
    ), budget.max_turns


def _ratio(numerator: object, denominator: object) -> float | None:
    if not isinstance(numerator, (int, float)) or not isinstance(denominator, (int, float)) or denominator == 0:
        return None
    return round(float(numerator) / float(denominator), 4)


def _int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _required_object(value: dict[str, Any], key: str) -> dict[str, Any]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise TypeError(f"{key} must be an object")
    return item


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    summary = asyncio.run(run_ab(parse_args()))
    print(json.dumps({key: value for key, value in summary.items() if key in {"formal_saved", "variants", "source_artifacts_unchanged"}}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
