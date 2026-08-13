"""A/B test the formal and shadow Compiler authoring views."""

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
_FORMAL = _ROOT / "harness_templates" / "teacher" / "compiler"
_SHADOW = _ROOT / "experiments" / "teacher_query_views" / "templates" / "compiler"
_QUERY_TOOLS = frozenset(
    {"list_harness_files", "read_harness_file", "query_hook_api"}
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler-artifact", action="append", type=Path, default=[])
    parser.add_argument("--request-file", action="append", type=Path, default=[])
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--max-turns", type=int, default=30)
    parser.add_argument(
        "--variants",
        nargs="+",
        choices=("formal", "shadow"),
        default=["formal", "shadow"],
    )
    return parser.parse_args(argv)


async def run_ab(args: argparse.Namespace) -> dict[str, Any]:
    sources = [*args.compiler_artifact, *args.request_file]
    if not sources:
        raise ValueError("at least one Compiler artifact or request is required")
    if args.repetitions < 1:
        raise ValueError("repetitions must be positive")
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    hashes_before = _source_hashes(sources)
    cases = []
    for case_index, source_path in enumerate(sources, start=1):
        source = _read_json(source_path)
        normalized = _normalize_source(source)
        pairs = []
        for repetition in range(1, args.repetitions + 1):
            variants = await asyncio.gather(
                *(
                    _run_variant(
                        source=normalized,
                        template_root=(
                            _FORMAL if variant == "formal" else _SHADOW
                        ),
                        env_file=args.env_file,
                        max_turns=args.max_turns,
                        artifact_path=output_dir
                        / f"case_{case_index:02d}"
                        / f"{variant}_{repetition:02d}.json",
                    )
                    for variant in args.variants
                )
            )
            pairs.append(
                {"repetition": repetition}
                | dict(zip(args.variants, variants, strict=True))
            )
        aggregate = {
            variant: _aggregate([item[variant]["metrics"] for item in pairs])
            for variant in args.variants
        }
        cases.append(
            {
                "case": f"case_{case_index:02d}",
                "source": str(source_path.resolve()),
                "input_migrations": normalized.get("input_migrations", []),
                "goal": normalized["input"].get("mechanism", {}).get("goal"),
                "runs": pairs,
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
        "experiment": "compiler_authoring_view_ab_v1",
        "pairing": (
            "Formal and shadow use the same saved Compiler Input, parent or "
            "continuation workspace, API configuration, output contract, mutable "
            "workspace tools and deterministic candidate validation. The shadow "
            "changes only the initial authoring brief and query_hook_api result view."
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
            role_id="compiler",
            role_version=int(role.get("version", 1)),
        )
    except TeacherRoleRunFailed as exc:
        artifact = exc.failure_artifact
    _write_json(artifact_path, artifact)
    return {
        "artifact": str(artifact_path.resolve()),
        "metrics": extract_metrics(artifact),
        "candidate_summary": _candidate_summary(artifact),
    }


def extract_metrics(artifact: dict[str, Any]) -> dict[str, Any]:
    usage = artifact.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    calls = [item for item in artifact.get("tool_calls", []) if isinstance(item, dict)]
    finalize = [item for item in calls if item.get("name") == "finalize_candidate"]
    query = [item for item in calls if item.get("name") in _QUERY_TOOLS]
    candidate = _candidate(artifact)
    first_call = (usage.get("calls") or [{}])[0]
    return {
        "completed": artifact.get("output") is not None,
        "submitted": candidate is not None,
        "validation_passed": bool(
            isinstance(candidate, dict)
            and isinstance(candidate.get("validation"), dict)
            and candidate["validation"].get("passed")
        ),
        "first_finalize_passed": (
            len(finalize) == 1 and candidate is not None
        ),
        "finalize_repairs": max(0, len(finalize) - 1),
        "list_calls": sum(item.get("name") == "list_harness_files" for item in calls),
        "read_calls": sum(item.get("name") == "read_harness_file" for item in calls),
        "read_result_characters": sum(
            len(str(item.get("content", "")))
            for item in calls
            if item.get("name") == "read_harness_file"
        ),
        "api_query_calls": sum(item.get("name") == "query_hook_api" for item in calls),
        "api_rejected_calls": sum(
            item.get("name") == "query_hook_api"
            and '"status": "rejected"' in str(item.get("content", ""))
            for item in calls
        ),
        "workspace_write_calls": sum(
            item.get("name") in {"write_candidate_file", "delete_candidate_file"}
            for item in calls
        ),
        "query_result_characters": sum(
            len(str(item.get("content", ""))) for item in query
        ),
        "tool_errors": sum(_is_error(item.get("content")) for item in calls),
        "first_prompt_tokens": first_call.get("prompt_tokens"),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "requests": usage.get("requests"),
    }


def _candidate_summary(artifact: dict[str, Any]) -> dict[str, Any] | None:
    candidate = _candidate(artifact)
    if not isinstance(candidate, dict):
        return None
    changed = candidate.get("changed_files")
    changed = changed if isinstance(changed, dict) else {}
    return {
        "candidate_ref": candidate.get("candidate_ref"),
        "summary": candidate.get("summary"),
        "changed_paths": sorted(changed),
        "python_lines": sum(
            len(content.splitlines())
            for path, content in changed.items()
            if path.endswith(".py") and isinstance(content, str)
        ),
        "queried_symbols": candidate.get("queried_symbols"),
    }


def _candidate(artifact: dict[str, Any]) -> dict[str, Any] | None:
    resources = artifact.get("resource_artifacts")
    resources = resources if isinstance(resources, dict) else {}
    candidate = resources.get("compiler_candidate")
    return candidate if isinstance(candidate, dict) else None


def _aggregate(values: list[dict[str, Any]]) -> dict[str, Any]:
    booleans = {
        "completed",
        "submitted",
        "validation_passed",
        "first_finalize_passed",
    }
    numeric = tuple(key for key in values[0] if key not in booleans)
    return {
        "runs": len(values),
        **{key: sum(bool(item[key]) for item in values) for key in booleans},
        "means": {
            key: round(
                mean(float(item[key]) for item in values if item[key] is not None),
                2,
            )
            for key in numeric
            if any(item[key] is not None for item in values)
        },
    }


def _comparison(aggregate: dict[str, Any]) -> dict[str, Any]:
    formal = aggregate["formal"]
    shadow = aggregate["shadow"]
    return {
        key + "_rate": {
            "formal": formal[key] / formal["runs"],
            "shadow": shadow[key] / shadow["runs"],
        }
        for key in ("completed", "submitted", "validation_passed", "first_finalize_passed")
    } | {
        "total_token_ratio": _ratio(
            shadow["means"].get("total_tokens"),
            formal["means"].get("total_tokens"),
        ),
        "request_ratio": _ratio(
            shadow["means"].get("requests"), formal["means"].get("requests")
        ),
    }


def _normalize_source(source: dict[str, Any]) -> dict[str, Any]:
    resources = source.get("resource_config")
    if not isinstance(resources, dict):
        resources = source.get("resources")
    resources = dict(resources) if isinstance(resources, dict) else resources
    migrations = []
    compiler = resources.get("compiler") if isinstance(resources, dict) else None
    if isinstance(compiler, dict) and "parent_plugins_root" in compiler:
        compiler = dict(compiler)
        compiler.pop("parent_plugins_root")
        compiler["parent_template_root"] = str(
            (_ROOT / "harness_templates" / "student" / "baseline").resolve()
        )
        resources["compiler"] = compiler
        migrations.append("parent_plugins_root -> current baseline parent_template_root")
    role_input = dict(_required_object(source, "input"))
    mechanism = role_input.get("mechanism")
    if isinstance(mechanism, dict) and "phase_rules" not in mechanism:
        mechanism = dict(mechanism)
        phase = mechanism.get("trigger_phase")
        action_text = str(mechanism.get("action", "")).casefold()
        pseudocode = str(mechanism.get("behavioral_pseudocode", "")).casefold()
        model_gated = "hook model" in action_text or "hookmodelrequest" in pseudocode
        mechanism["decision_evaluator"] = (
            "hook_model" if model_gated else "deterministic"
        )
        mechanism["runtime_inputs"] = _legacy_runtime_inputs(
            str(phase), model_gated=model_gated
        )
        role_input["mechanism"] = mechanism
        migrations.append(
            "legacy single-phase mechanism -> current evaluator/runtime-input fields"
        )
    return {
        "role": source.get("role") or {"id": "compiler", "version": 1},
        "input": role_input,
        "resource_config": resources,
        "input_migrations": migrations,
    }


def _legacy_runtime_inputs(phase: str, *, model_gated: bool) -> list[str]:
    topics = {
        "post_prompt": ["conversation", "model_io", "persistent_state"],
        "post_tool": ["tool", "persistent_state"],
        "pre_final": ["conversation", "final_decision", "persistent_state"],
    }.get(phase, ["persistent_state"])
    if model_gated:
        topics = ["task", *topics, "model_io"]
    return list(dict.fromkeys(topics))


def _source_hashes(sources: list[Path]) -> dict[str, str]:
    paths = set(sources)
    for source_path in sources:
        source = _normalize_source(_read_json(source_path))
        compiler = _required_object(source, "resource_config").get("compiler")
        if not isinstance(compiler, dict):
            continue
        continuation = compiler.get("continuation_candidate_file")
        if isinstance(continuation, str) and continuation:
            paths.add(Path(continuation))
    return {str(path.resolve()): _digest(path) for path in sorted(paths)}


def _is_error(content: object) -> bool:
    text = str(content or "").lower()
    return any(
        marker in text
        for marker in (
            "validation failed",
            "repair_required",
            "invalid json",
            "tool_input_error",
            "tool arguments are invalid json",
        )
    )


def _ratio(numerator: object, denominator: object) -> float | None:
    if not isinstance(numerator, (int, float)) or not isinstance(
        denominator, (int, float)
    ):
        return None
    if denominator == 0:
        return None
    return round(numerator / denominator, 4)


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
