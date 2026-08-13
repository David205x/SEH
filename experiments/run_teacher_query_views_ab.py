"""A/B test production and shadow Teacher query-tool schemes."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any, Sequence

from search_harness.evolution.research.resources.base import TeacherResourceConfig
from search_harness.evolution.research.roles.native_chat_runner import (
    NativeChatRoleRunner,
    TeacherRoleRunFailed,
)


_ROOT = Path(__file__).resolve().parents[1]
_FORMAL_TEMPLATES = _ROOT / "harness_templates" / "teacher"
_SHADOW_TEMPLATES = (
    _ROOT / "experiments" / "teacher_query_views" / "templates"
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--failure-artifact", type=Path, required=True)
    parser.add_argument("--researcher-artifact", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument(
        "--only",
        choices=("all", "failure_analyst", "hypothesis_researcher"),
        default="all",
    )
    return parser.parse_args(argv)


async def run_ab(args: argparse.Namespace) -> dict[str, Any]:
    if args.repetitions < 1:
        raise ValueError("repetitions must be positive")
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    sources = {
        "failure_analyst": _read_json(args.failure_artifact),
        "hypothesis_researcher": _read_json(args.researcher_artifact),
    }
    roles = (
        ("failure_analyst", "hypothesis_researcher")
        if args.only == "all"
        else (args.only,)
    )
    results: dict[str, Any] = {}
    for role_id in roles:
        role_results = await _run_role_ab(
            role_id=role_id,
            source=sources[role_id],
            env_file=args.env_file,
            repetitions=args.repetitions,
            output_dir=output_dir / role_id,
        )
        results[role_id] = {
            "runs": role_results,
            "aggregate": {
                variant: _aggregate(
                    [
                        item[variant]["metrics"]
                        for item in role_results
                    ]
                )
                for variant in ("formal", "shadow")
            },
        }
        results[role_id]["comparison"] = _comparison(
            results[role_id]["aggregate"]
        )
    summary = {
        "schema_version": 1,
        "experiment": "teacher_query_views_ab_v1",
        "pairing": (
            "Each repetition runs formal and shadow concurrently with the "
            "same saved Role Input, Resource Config, API configuration, and "
            "role budget. Repetitions are run sequentially."
        ),
        "known_confound": (
            "The two current schemes include their current role prompts as "
            "well as their current query tools; results measure the complete "
            "schemes, not a view-only microbenchmark."
        ),
        "roles": results,
    }
    _write_json(output_dir / "summary.json", summary)
    return summary


async def _run_role_ab(
    *,
    role_id: str,
    source: dict[str, Any],
    env_file: Path,
    repetitions: int,
    output_dir: Path,
) -> list[dict[str, Any]]:
    role_input = _required_object(source, "input")
    resource_config = TeacherResourceConfig.model_validate(
        _required_object(source, "resource_config")
    )
    role = _required_object(source, "role")
    role_version = role.get("version", 1)
    if not isinstance(role_version, int):
        raise TypeError("source role version must be an integer")
    output_dir.mkdir(parents=True, exist_ok=True)
    pairs = []
    for index in range(1, repetitions + 1):
        formal, shadow = await asyncio.gather(
            _run_variant(
                role_id=role_id,
                role_version=role_version,
                role_input=role_input,
                resource_config=resource_config,
                template_root=_FORMAL_TEMPLATES / role_id,
                env_file=env_file,
                artifact_path=output_dir / f"formal_{index:02d}.json",
            ),
            _run_variant(
                role_id=role_id,
                role_version=role_version,
                role_input=role_input,
                resource_config=resource_config,
                template_root=_SHADOW_TEMPLATES / role_id,
                env_file=env_file,
                artifact_path=output_dir / f"shadow_{index:02d}.json",
            ),
        )
        pairs.append(
            {
                "repetition": index,
                "formal": formal,
                "shadow": shadow,
            }
        )
    return pairs


async def _run_variant(
    *,
    role_id: str,
    role_version: int,
    role_input: dict[str, Any],
    resource_config: TeacherResourceConfig,
    template_root: Path,
    env_file: Path,
    artifact_path: Path,
) -> dict[str, Any]:
    try:
        artifact = await NativeChatRoleRunner(env_file=env_file).run(
            template_root=template_root,
            role_input=role_input,
            resource_config=resource_config,
            role_id=role_id,
            role_version=role_version,
        )
    except TeacherRoleRunFailed as exc:
        artifact = exc.failure_artifact
    _write_json(artifact_path, artifact)
    return {
        "artifact": str(artifact_path.resolve()),
        "metrics": extract_metrics(artifact),
        "output_summary": _output_summary(role_id, artifact.get("output")),
    }


def extract_metrics(artifact: dict[str, Any]) -> dict[str, Any]:
    """Extract comparable budget and tool metrics without reading transcripts."""

    usage = artifact.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    error = artifact.get("error")
    error = error if isinstance(error, dict) else {}
    calls = [
        call
        for call in artifact.get("tool_calls", [])
        if isinstance(call, dict)
    ]
    terminal_calls = [
        call for call in calls if str(call.get("name", "")).startswith("submit_")
    ]
    query_calls = [call for call in calls if call not in terminal_calls]
    result_characters = sum(len(str(call.get("content", ""))) for call in query_calls)
    tool_errors = sum(
        1
        for call in query_calls
        if isinstance(call.get("metadata"), dict)
        and call["metadata"].get("error_type")
    )
    tool_counts = Counter(str(call.get("name")) for call in query_calls)
    role_budget = artifact.get("role_budget")
    role_budget = role_budget if isinstance(role_budget, dict) else {}
    turns = usage.get("requests")
    if not isinstance(turns, int):
        turns = error.get("turn_count")
    return {
        "status": artifact.get("status", "completed"),
        "model_turns": turns,
        "max_turns": role_budget.get("max_turns"),
        "query_tool_calls": len(query_calls),
        "query_tool_counts": dict(tool_counts),
        "terminal_submit_calls": len(terminal_calls),
        "terminal_retries": max(0, len(terminal_calls) - 1),
        "tool_errors": tool_errors,
        "tool_result_characters": result_characters,
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "cache_hit_tokens": usage.get("prompt_cache_hit_tokens"),
        "cache_miss_tokens": usage.get("prompt_cache_miss_tokens"),
    }


def _aggregate(items: list[dict[str, Any]]) -> dict[str, Any]:
    numeric = (
        "model_turns",
        "query_tool_calls",
        "terminal_submit_calls",
        "terminal_retries",
        "tool_errors",
        "tool_result_characters",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "cache_hit_tokens",
        "cache_miss_tokens",
    )
    return {
        "runs": len(items),
        "completed": sum(item["status"] == "completed" for item in items),
        "exhausted": sum(item["status"] != "completed" for item in items),
        "means": {
            key: _mean_available(item.get(key) for item in items)
            for key in numeric
        },
        "ranges": {
            key: _range_available(item.get(key) for item in items)
            for key in numeric
        },
    }


def _comparison(aggregate: dict[str, Any]) -> dict[str, Any]:
    formal = aggregate["formal"]["means"]
    shadow = aggregate["shadow"]["means"]
    keys = (
        "model_turns",
        "query_tool_calls",
        "terminal_retries",
        "tool_result_characters",
        "input_tokens",
        "output_tokens",
        "total_tokens",
    )
    return {
        key: {
            "formal_mean": formal.get(key),
            "shadow_mean": shadow.get(key),
            "shadow_minus_formal": _difference(shadow.get(key), formal.get(key)),
            "shadow_to_formal_ratio": _ratio(shadow.get(key), formal.get(key)),
        }
        for key in keys
    }


def _output_summary(role_id: str, value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    if role_id == "failure_analyst":
        refs = value.get("evidence_refs")
        refs = refs if isinstance(refs, list) else []
        return {
            "pattern": value.get("pattern"),
            "evidence_ref_count": len(refs),
            "distinct_example_count": len(
                {
                    str(reference).split("/", maxsplit=1)[0]
                    for reference in refs
                }
            ),
        }
    phase_plan = value.get("phase_plan")
    phase_plan = phase_plan if isinstance(phase_plan, list) else []
    return {
        "fork_phase": value.get("fork_phase"),
        "phases": [
            item.get("phase")
            for item in phase_plan
            if isinstance(item, dict)
        ],
    }


def _mean_available(values) -> float | None:
    selected = [value for value in values if isinstance(value, (int, float))]
    return round(mean(selected), 2) if selected else None


def _range_available(values) -> list[float] | None:
    selected = [value for value in values if isinstance(value, (int, float))]
    return [min(selected), max(selected)] if selected else None


def _difference(left: object, right: object) -> float | None:
    if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
        return None
    return round(left - right, 2)


def _ratio(left: object, right: object) -> float | None:
    if (
        not isinstance(left, (int, float))
        or not isinstance(right, (int, float))
        or right == 0
    ):
        return None
    return round(left / right, 4)


def _required_object(value: dict[str, Any], key: str) -> dict[str, Any]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise TypeError(f"source artifact field '{key}' must be an object")
    return item


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"JSON artifact must be an object: {path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main(argv: Sequence[str] | None = None) -> None:
    summary = asyncio.run(run_ab(parse_args(argv)))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
