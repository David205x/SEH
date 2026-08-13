"""A/B test formal and shadow Candidate Reviewer evidence views."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from statistics import mean
from typing import Any, Sequence

from search_harness.evolution.research.resources.base import TeacherResourceConfig
from search_harness.evolution.research.roles.native_chat_runner import (
    NativeChatRoleRunner,
    TeacherRoleRunFailed,
)


_ROOT = Path(__file__).resolve().parents[1]
_FORMAL = _ROOT / "harness_templates" / "teacher" / "candidate_reviewer"
_SHADOW = (
    _ROOT
    / "experiments"
    / "teacher_query_views"
    / "templates"
    / "candidate_reviewer"
)
_QUERY_TOOLS = frozenset(
    {
        "list_candidate_changes",
        "get_candidate_case",
        "get_paired_student_trajectory",
        "get_candidate_harness_diff",
        "get_candidate_trajectory_text",
    }
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--candidate-reviewer-artifact",
        action="append",
        type=Path,
        default=[],
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--max-turns", type=int, default=20)
    parser.add_argument(
        "--variants",
        nargs="+",
        choices=("formal", "shadow"),
        default=["formal", "shadow"],
    )
    return parser.parse_args(argv)


async def run_ab(args: argparse.Namespace) -> dict[str, Any]:
    sources = list(args.candidate_reviewer_artifact)
    if not sources:
        raise ValueError("at least one Candidate Reviewer artifact is required")
    if args.repetitions < 1:
        raise ValueError("repetitions must be positive")
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    hashes_before = _source_hashes(sources)
    cases = []
    for case_index, source_path in enumerate(sources, start=1):
        source = _read_json(source_path)
        normalized = _normalize_source(source, source_path)
        runs = []
        for repetition in range(1, args.repetitions + 1):
            variants = await asyncio.gather(
                *(
                    _run_variant(
                        source=normalized,
                        template_root=_FORMAL if variant == "formal" else _SHADOW,
                        env_file=args.env_file,
                        max_turns=args.max_turns,
                        artifact_path=(
                            output_dir
                            / f"case_{case_index:02d}"
                            / f"{variant}_{repetition:02d}.json"
                        ),
                    )
                    for variant in args.variants
                )
            )
            runs.append(
                {"repetition": repetition}
                | dict(zip(args.variants, variants, strict=True))
            )
        aggregate = {
            variant: _aggregate([item[variant]["metrics"] for item in runs])
            for variant in args.variants
        }
        cases.append(
            {
                "case": f"case_{case_index:02d}",
                "source_artifact": str(source_path.resolve()),
                "source_recommendation": (source.get("output") or {}).get(
                    "recommendation"
                ),
                "resource_migrations": normalized.get("resource_migrations", []),
                "runs": runs,
                "aggregate": aggregate,
                "comparison": (
                    _comparison(aggregate)
                    if {"formal", "shadow"} <= set(aggregate)
                    else None
                ),
            }
        )
    hashes_after = _source_hashes(sources)
    summary = {
        "schema_version": 1,
        "experiment": "candidate_reviewer_view_ab_v1",
        "pairing": (
            "Formal and shadow use the same saved Candidate Reviewer Input, "
            "incumbent/candidate Evaluation and Rollout Artifacts, API configuration, "
            "turn budget and output contract. The shadow changes only model-visible "
            "input and query-result projections plus prompt/tool-obligation alignment."
        ),
        "cases": cases,
        "source_hashes_before": hashes_before,
        "source_hashes_after": hashes_after,
        "source_artifacts_unchanged": hashes_before == hashes_after,
    }
    _write_json(output_dir / "summary.json", summary)
    return summary


async def _run_variant(
    *,
    source: dict[str, Any],
    template_root: Path,
    env_file: Path,
    max_turns: int,
    artifact_path: Path,
) -> dict[str, Any]:
    role = source.get("role")
    role = role if isinstance(role, dict) else {}
    try:
        artifact = await NativeChatRoleRunner(
            env_file=env_file,
            max_turns=max_turns,
        ).run(
            template_root=template_root,
            role_input=_required_object(source, "input"),
            resource_config=TeacherResourceConfig.model_validate(
                _required_object(source, "resource_config")
            ),
            role_id="candidate_reviewer",
            role_version=int(role.get("version", 1)),
        )
    except TeacherRoleRunFailed as exc:
        artifact = exc.failure_artifact
    _write_json(artifact_path, artifact)
    return {
        "artifact": str(artifact_path.resolve()),
        "metrics": extract_metrics(artifact),
        "review": _review_summary(artifact),
    }


def extract_metrics(artifact: dict[str, Any]) -> dict[str, Any]:
    usage = _object(artifact.get("usage"))
    calls = [item for item in artifact.get("tool_calls", []) if isinstance(item, dict)]
    query = [item for item in calls if item.get("name") in _QUERY_TOOLS]
    trajectories = [
        item for item in calls if item.get("name") == "get_paired_student_trajectory"
    ]
    first_call = (usage.get("calls") or [{}])[0]
    output = artifact.get("output")
    return {
        "completed": isinstance(output, dict),
        "recommendation": output.get("recommendation")
        if isinstance(output, dict)
        else None,
        "requests": usage.get("requests"),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "first_prompt_tokens": first_call.get("prompt_tokens"),
        "query_tool_calls": len(query),
        "list_calls": sum(item.get("name") == "list_candidate_changes" for item in calls),
        "case_calls": sum(item.get("name") == "get_candidate_case" for item in calls),
        "trajectory_calls": len(trajectories),
        "diff_calls": sum(item.get("name") == "get_candidate_harness_diff" for item in calls),
        "text_detail_calls": sum(item.get("name") == "get_candidate_trajectory_text" for item in calls),
        "query_result_characters": sum(len(str(item.get("content", ""))) for item in query),
        "trajectory_result_characters": sum(len(str(item.get("content", ""))) for item in trajectories),
        "tool_errors": sum(_is_error(item.get("content")) for item in calls),
    }


def _review_summary(artifact: dict[str, Any]) -> dict[str, Any] | None:
    output = artifact.get("output")
    if not isinstance(output, dict):
        return None
    return {
        "recommendation": output.get("recommendation"),
        "revision_target": output.get("revision_target"),
        "observed_effect": output.get("observed_effect"),
        "reason": output.get("reason"),
        "next_obligation": output.get("next_obligation"),
    }


def _aggregate(values: list[dict[str, Any]]) -> dict[str, Any]:
    numeric = (
        "requests",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "first_prompt_tokens",
        "query_tool_calls",
        "list_calls",
        "case_calls",
        "trajectory_calls",
        "diff_calls",
        "text_detail_calls",
        "query_result_characters",
        "trajectory_result_characters",
        "tool_errors",
    )
    recommendations = {}
    for item in values:
        recommendation = str(item.get("recommendation"))
        recommendations[recommendation] = recommendations.get(recommendation, 0) + 1
    return {
        "runs": len(values),
        "completed": sum(bool(item.get("completed")) for item in values),
        "recommendations": recommendations,
        "means": {
            key: round(
                mean(float(item[key]) for item in values if item.get(key) is not None),
                2,
            )
            for key in numeric
            if any(item.get(key) is not None for item in values)
        },
    }


def _comparison(aggregate: dict[str, Any]) -> dict[str, Any]:
    formal = aggregate["formal"]
    shadow = aggregate["shadow"]
    return {
        "completion_rate": {
            "formal": formal["completed"] / formal["runs"],
            "shadow": shadow["completed"] / shadow["runs"],
        },
        "recommendations": {
            "formal": formal["recommendations"],
            "shadow": shadow["recommendations"],
        },
        "total_token_ratio": _ratio(
            shadow["means"].get("total_tokens"),
            formal["means"].get("total_tokens"),
        ),
        "input_token_ratio": _ratio(
            shadow["means"].get("input_tokens"),
            formal["means"].get("input_tokens"),
        ),
        "query_result_character_ratio": _ratio(
            shadow["means"].get("query_result_characters"),
            formal["means"].get("query_result_characters"),
        ),
        "trajectory_character_ratio": _ratio(
            shadow["means"].get("trajectory_result_characters"),
            formal["means"].get("trajectory_result_characters"),
        ),
        "request_ratio": _ratio(
            shadow["means"].get("requests"),
            formal["means"].get("requests"),
        ),
    }


def _normalize_source(
    source: dict[str, Any],
    source_path: Path,
) -> dict[str, Any]:
    resources = dict(_required_object(source, "resource_config"))
    candidate = dict(_required_object(resources, "candidate_review"))
    migrations = []
    candidate_root = candidate.get("candidate_template_root")
    if not isinstance(candidate_root, str) or not Path(candidate_root).exists():
        replacement = _candidate_root_from_source(source_path, source)
        candidate["candidate_template_root"] = str(replacement)
        migrations.append(
            "missing staging candidate_template_root -> immutable compiler candidate snapshot"
        )
    resources["candidate_review"] = candidate
    return {
        "role": source.get("role") or {"id": "candidate_reviewer", "version": 1},
        "input": _required_object(source, "input"),
        "resource_config": resources,
        "resource_migrations": migrations,
    }


def _candidate_root_from_source(source_path: Path, source: dict[str, Any]) -> Path:
    run_root = source_path.resolve().parents[2]
    implementation = str(_required_object(source, "input").get("implementation_summary", ""))
    expected_digest = _object(_required_object(source, "input").get("validation_summary")).get("compiler_validation")
    expected_digest = _object(expected_digest).get("candidate_digest")
    candidates = []
    snapshot_sources: list[tuple[Path, dict[str, Any]]] = []
    for path in (run_root / "artifacts").glob("compile_candidate-*/candidate_workspace.json"):
        snapshot_sources.append((path, _read_json(path)))
    for path in (run_root / "artifacts").glob("compile_candidate-*/role.json"):
        role_artifact = _read_json(path)
        value = _object(_object(role_artifact.get("resource_artifacts")).get("compiler_candidate"))
        if value:
            snapshot_sources.append((path, value))
    for path, value in snapshot_sources:
        score = 0
        if expected_digest and value.get("candidate_digest") == expected_digest:
            score += 100
        summary = str(value.get("summary", ""))
        score += len(set(implementation.casefold().split()) & set(summary.casefold().split()))
        candidates.append((score, path, value))
    if not candidates:
        raise FileNotFoundError("no compiler candidate snapshot is available")
    _, candidate_file, value = max(candidates, key=lambda item: (item[0], str(item[1])))
    root = (
        run_root
        / "artifacts"
        / "shadow_candidate_inputs"
        / candidate_file.parent.name
        / "template"
    )
    if not root.exists():
        _materialize_candidate_snapshot(
            parent_root=Path(
                _required_object(
                    _required_object(source, "resource_config"),
                    "candidate_review",
                )["incumbent_template_root"]
            ),
            candidate=value,
            destination=root,
        )
    return root.resolve()


def _materialize_candidate_snapshot(
    *,
    parent_root: Path,
    candidate: dict[str, Any],
    destination: Path,
) -> None:
    import shutil

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(parent_root, destination)
    changed = _object(candidate.get("changed_files"))
    for relative, content in changed.items():
        target = destination / str(relative)
        if content is None:
            if target.exists():
                target.unlink()
            continue
        if not isinstance(content, str):
            raise TypeError(f"candidate changed file must be text: {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def _source_hashes(sources: list[Path]) -> dict[str, str]:
    paths = set(sources)
    for source_path in sources:
        source = _read_json(source_path)
        candidate = _required_object(
            _required_object(source, "resource_config"),
            "candidate_review",
        )
        for key in (
            "incumbent_report_dir",
            "candidate_report_dir",
            "incumbent_rollout_file",
            "candidate_rollout_file",
        ):
            raw = candidate.get(key)
            if not isinstance(raw, str):
                continue
            path = Path(raw)
            if path.is_dir():
                paths.update(item for item in path.rglob("*") if item.is_file())
            elif path.is_file():
                paths.add(path)
    return {str(path.resolve()): _digest(path) for path in sorted(paths)}


def _is_error(content: object) -> bool:
    text = str(content or "").casefold()
    return any(
        marker in text
        for marker in (
            "tool_input_error",
            "structured output validation failed",
            "unknown comparison example_id",
            "unknown paired trajectory",
        )
    )


def _ratio(numerator: object, denominator: object) -> float | None:
    if not isinstance(numerator, (int, float)) or not isinstance(denominator, (int, float)):
        return None
    if denominator == 0:
        return None
    return round(numerator / denominator, 4)


def _object(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _required_object(value: dict[str, Any], key: str) -> dict[str, Any]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise TypeError(f"artifact {key} must be an object")
    return item


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    summary = asyncio.run(run_ab(parse_args()))
    print(
        json.dumps(
            {
                "experiment": summary["experiment"],
                "cases": [
                    {"case": case["case"], "comparison": case["comparison"]}
                    for case in summary["cases"]
                ],
                "source_artifacts_unchanged": summary["source_artifacts_unchanged"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
