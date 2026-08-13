"""A/B test formal and shadow Intervention Worker query views."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from collections import Counter
from dataclasses import replace
from pathlib import Path
from statistics import mean
from typing import Any, Sequence

from experiments.teacher_query_views.intervention import (
    ShadowInterventionWorker,
)
from search_harness._internal import read_runtime_config, teacher_role_budget
from search_harness.evolution.research.intervention.prefix import (
    load_rollout_record,
    resolve_prefix_boundary,
)
from search_harness.evolution.research.intervention.role_runner import (
    _phase_runtime_plan,
    _worker_intent,
    _worker_result,
)
from search_harness.evolution.research.intervention.runtime import (
    InterventionRunner,
    InterventionRuntimeConfig,
)
from search_harness.evolution.research.intervention.worker import (
    InterventionWorker,
)
from search_harness.evolution.research.resources.base import (
    TeacherResourceConfig,
)
from search_harness.evolution.research.roles.contracts import (
    InterventionWorkerInput,
)
from search_harness.evolution.research.roles.loader import (
    load_teacher_agent_spec,
)
from search_harness.integrations.openai_compatible import (
    OpenAICompatibleConfig,
)


_ROOT = Path(__file__).resolve().parents[1]
_WORKER_TEMPLATE = _ROOT / "harness_templates" / "teacher" / "intervention_worker"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--trial-artifact",
        action="append",
        type=Path,
        required=True,
        help="Saved Intervention Worker trial.json; repeat for multiple cases.",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument(
        "--no-teacher-judge",
        action="store_true",
        help="Skip final semantic scoring while retaining Worker and Student runs.",
    )
    return parser.parse_args(argv)


async def run_ab(args: argparse.Namespace) -> dict[str, Any]:
    if args.repetitions < 1:
        raise ValueError("repetitions must be positive")
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    source_hashes = {
        str(path.resolve()): _digest(path)
        for path in args.trial_artifact
    }
    cases = []
    for case_index, source_path in enumerate(args.trial_artifact, start=1):
        source = _read_json(source_path)
        task = InterventionWorkerInput.model_validate(_required_object(source, "input"))
        resource_config = TeacherResourceConfig.model_validate(
            _required_object(source, "resource_config")
        )
        if resource_config.intervention is None:
            raise ValueError(f"trial has no Intervention resources: {source_path}")
        resource_config = resource_config.model_copy(
            update={
                "intervention": resource_config.intervention.model_copy(
                    update={"env_file": args.env_file}
                )
            }
        )
        case_name = (
            f"case_{case_index:02d}_{task.example_id}_{task.replicate_id}"
        )
        repetitions = []
        for repetition in range(1, args.repetitions + 1):
            order = (
                ("formal", "shadow")
                if repetition % 2 == 1
                else ("shadow", "formal")
            )
            pair: dict[str, Any] = {"repetition": repetition, "order": list(order)}
            for variant in order:
                worker_type = (
                    InterventionWorker
                    if variant == "formal"
                    else ShadowInterventionWorker
                )
                artifact = await asyncio.to_thread(
                    _run_variant,
                    task=task,
                    resource_config=resource_config,
                    env_file=args.env_file,
                    worker_type=worker_type,
                    teacher_judge=not args.no_teacher_judge,
                )
                artifact_path = (
                    output_dir
                    / case_name
                    / f"{variant}_{repetition:02d}.json"
                )
                _write_json(artifact_path, artifact)
                pair[variant] = {
                    "artifact": str(artifact_path.resolve()),
                    "metrics": extract_metrics(artifact),
                }
            repetitions.append(pair)
        aggregates = {
            variant: _aggregate(
                [item[variant]["metrics"] for item in repetitions]
            )
            for variant in ("formal", "shadow")
        }
        cases.append(
            {
                "case": case_name,
                "source_artifact": str(source_path.resolve()),
                "hypothesis": task.hypothesis.model_dump(mode="json"),
                "runs": repetitions,
                "aggregate": aggregates,
                "comparison": _comparison(aggregates),
            }
        )
    summary = {
        "schema_version": 1,
        "experiment": "intervention_query_views_ab_v1",
        "pairing": (
            "Each case uses the same saved Worker Input, reconstructed prefix, "
            "Student/Teacher configuration, and prompt. Variant order alternates "
            "by repetition; only read-only Worker query views differ."
        ),
        "cases": cases,
        "source_hashes_before": source_hashes,
        "source_hashes_after": {
            str(path.resolve()): _digest(path)
            for path in args.trial_artifact
        },
    }
    summary["source_artifacts_unchanged"] = (
        summary["source_hashes_before"] == summary["source_hashes_after"]
    )
    _write_json(output_dir / "summary.json", summary)
    return summary


def _run_variant(
    *,
    task: InterventionWorkerInput,
    resource_config: TeacherResourceConfig,
    env_file: Path,
    worker_type: type[InterventionWorker],
    teacher_judge: bool,
) -> dict[str, Any]:
    intervention = resource_config.intervention
    if intervention is None:
        raise ValueError("Intervention resources are required")
    record = load_rollout_record(
        intervention.rollout_file,
        task.example_id,
        task.replicate_id,
    )
    boundary = resolve_prefix_boundary(record, task.prefix_id)
    if boundary["phase"] != task.hypothesis.fork_phase:
        raise ValueError("saved prefix phase differs from the frozen hypothesis")
    guidance, budgets = _phase_runtime_plan(task.hypothesis)
    model_config = OpenAICompatibleConfig.from_env(
        env_file=env_file,
        prefix="TEACHER",
    )
    role_budget = teacher_role_budget(
        read_runtime_config(env_file=env_file),
        "intervention_worker",
        default_max_tokens=model_config.max_tokens,
        default_max_turns=8,
        default_thinking_mode=model_config.thinking_mode,
    )
    teacher_config = replace(
        model_config,
        max_tokens=role_budget.max_tokens,
        thinking_mode=(
            role_budget.thinking_mode
            if model_config.thinking_mode is not None
            else None
        ),
    )
    spec = load_teacher_agent_spec(
        _WORKER_TEMPLATE,
        runtime_context=None,
        role_id="intervention_worker",
        role_version=1,
    )
    runner = InterventionRunner(
        InterventionRuntimeConfig(
            env_file=env_file,
            template_root=intervention.student_template_root,
            student_max_steps=intervention.student_max_steps,
            worker_max_steps_per_activation=role_budget.max_turns,
            teacher_judge=teacher_judge,
        ),
        teacher_config=teacher_config,
        worker_type=worker_type,
    )
    artifact = runner.run(
        rollout_file=intervention.rollout_file,
        example_id=task.example_id,
        replicate_id=task.replicate_id,
        fork_step=int(boundary["step"]),
        fork_phase=str(boundary["phase"]),
        intent=_worker_intent(task),
        hook_guidance=guidance,
        activation_budgets=budgets,
        system_prompt_template=spec.prompt.instructions,
        persist=False,
    )
    artifact["worker_result"] = _worker_result(
        task.hypothesis,
        artifact,
    ).model_dump(mode="json")
    artifact["query_view_variant"] = (
        "shadow" if worker_type is ShadowInterventionWorker else "formal"
    )
    return artifact


def extract_metrics(artifact: dict[str, Any]) -> dict[str, Any]:
    calls = [
        call
        for call in artifact.get("worker_tool_calls", [])
        if isinstance(call, dict)
    ]
    counts = Counter(str(call.get("name")) for call in calls)
    query_names = {
        "inspect_active_observation",
        "inspect_editable_context",
        "inspect_context_block",
    }
    query_calls = [call for call in calls if call.get("name") in query_names]
    terminal_calls = [call for call in calls if call not in query_calls]
    usage = artifact.get("worker_usage")
    usage = usage if isinstance(usage, dict) else {}
    changes = [
        change
        for change in artifact.get("intervention_changes", [])
        if isinstance(change, dict)
    ]
    phase_effects = [
        effect
        for effect in artifact.get("phase_effects", [])
        if isinstance(effect, dict)
    ]
    comparison = artifact.get("comparison")
    comparison = comparison if isinstance(comparison, dict) else {}
    branch = comparison.get("branch")
    branch = branch if isinstance(branch, dict) else {}
    branch_execution = branch.get("execution")
    branch_execution = (
        branch_execution if isinstance(branch_execution, dict) else {}
    )
    return {
        "completed": True,
        "worker_model_turns": usage.get("requests"),
        "query_tool_calls": len(query_calls),
        "query_tool_counts": {
            name: counts.get(name, 0) for name in sorted(query_names)
        },
        "terminal_tool_calls": len(terminal_calls),
        "terminal_tool_counts": {
            name: count
            for name, count in sorted(counts.items())
            if name not in query_names
        },
        "tool_errors": sum(
            isinstance(call.get("metadata"), dict)
            and bool(
                call["metadata"].get("error")
                or call["metadata"].get("error_type")
            )
            for call in calls
        ),
        "query_result_characters": sum(
            len(str(call.get("content", ""))) for call in query_calls
        ),
        "worker_input_tokens": usage.get("input_tokens"),
        "worker_output_tokens": usage.get("output_tokens"),
        "worker_total_tokens": usage.get("total_tokens"),
        "modified": any(
            isinstance(change.get("action"), dict)
            and change["action"].get("kind") != "continue_without_change"
            for change in changes
        ),
        "action_kinds": [
            change.get("action", {}).get("kind")
            for change in changes
            if isinstance(change.get("action"), dict)
        ],
        "next_decisions": [effect.get("next_model_decision") for effect in phase_effects],
        "branch_status": branch.get("status"),
        "branch_score": branch.get("score"),
        "branch_answer": branch.get("answer"),
        "branch_steps": branch_execution.get("steps"),
        "branch_tool_calls": branch_execution.get("tool_calls"),
    }


def _aggregate(items: list[dict[str, Any]]) -> dict[str, Any]:
    numeric = (
        "worker_model_turns",
        "query_tool_calls",
        "terminal_tool_calls",
        "tool_errors",
        "query_result_characters",
        "worker_input_tokens",
        "worker_output_tokens",
        "worker_total_tokens",
        "branch_steps",
        "branch_tool_calls",
    )
    return {
        "runs": len(items),
        "modified_runs": sum(bool(item.get("modified")) for item in items),
        "branch_score_counts": dict(
            Counter(str(item.get("branch_score")) for item in items)
        ),
        "action_patterns": dict(
            Counter(
                " -> ".join(str(value) for value in item.get("action_kinds", []))
                or "none"
                for item in items
            )
        ),
        "means": {
            key: _mean(item.get(key) for item in items) for key in numeric
        },
        "ranges": {
            key: _range(item.get(key) for item in items) for key in numeric
        },
    }


def _comparison(aggregates: dict[str, Any]) -> dict[str, Any]:
    formal = aggregates["formal"]["means"]
    shadow = aggregates["shadow"]["means"]
    return {
        key: {
            "formal_mean": formal.get(key),
            "shadow_mean": shadow.get(key),
            "shadow_to_formal_ratio": _ratio(shadow.get(key), formal.get(key)),
        }
        for key in formal
    }


def _mean(values) -> float | None:
    selected = [value for value in values if isinstance(value, (int, float))]
    return round(mean(selected), 2) if selected else None


def _range(values) -> list[float] | None:
    selected = [value for value in values if isinstance(value, (int, float))]
    return [min(selected), max(selected)] if selected else None


def _ratio(left: object, right: object) -> float | None:
    if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
        return None
    return round(left / right, 4) if right else None


def _required_object(value: dict[str, Any], key: str) -> dict[str, Any]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise TypeError(f"source artifact field '{key}' must be an object")
    return item


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"JSON artifact must contain an object: {path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: Sequence[str] | None = None) -> None:
    summary = asyncio.run(run_ab(parse_args(argv)))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
