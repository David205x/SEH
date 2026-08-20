"""Run the formal Researcher-to-Intervention handoff on frozen artifacts."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from search_harness.evolution.control.intervention_effects import (
    InterventionEffects,
)
from search_harness.evolution.research.intervention.role_runner import (
    InterventionRoleRunner,
)
from search_harness.evolution.research.resources.base import TeacherResourceConfig
from search_harness.evolution.research.roles.contracts import (
    FailureDirection,
    InterventionHypothesis,
)
from search_harness.evolution.research.roles.native_chat_runner import (
    NativeChatRoleRunner,
    TeacherRoleRunFailed,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEACHER_ROOT = PROJECT_ROOT / "harness_templates" / "teacher"
DEFAULT_SOURCE = (
    PROJECT_ROOT / "runs" / "evolution" / "20260815_qwen3-8b_hook_feasibility"
)
DEFAULT_FAILURE_WORK = "analyze_failure-f84a7c940bac3611"
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "runs"
    / "experiments"
    / "20260816_researcher_intervention_joint"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-run", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--failure-work", default=DEFAULT_FAILURE_WORK)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument("--repetitions", type=int, default=3)
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    if args.repetitions < 1:
        raise ValueError("repetitions must be positive")
    source_run = args.source_run.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    incumbent = _only_directory(source_run / "artifacts", "evaluate_incumbent-")
    rollout_file = incumbent / "report_rollouts.jsonl"
    template_root = source_run / "version_store" / "template"
    failure_artifact = _read_json(
        source_run / "artifacts" / args.failure_work / "role.json"
    )
    failure = FailureDirection.model_validate(failure_artifact.get("output"))

    researcher = NativeChatRoleRunner(env_file=args.env_file.resolve())
    intervention = InterventionEffects(
        role_runner=InterventionRoleRunner(
            env_file=args.env_file.resolve(),
            max_steps_per_activation=20,
            teacher_judge=False,
            extended_worker_tools=True,
        ),
        worker_template_root=TEACHER_ROOT / "intervention_worker",
        student_template_root=template_root,
        env_file=args.env_file.resolve(),
        student_max_steps=20,
    )
    resources = TeacherResourceConfig(
        report_dir=incumbent / "report",
        rollout_file=rollout_file,
        student_template_root=template_root,
    )
    results: list[dict[str, Any]] = []
    for repetition in range(1, args.repetitions + 1):
        run_dir = output_dir / f"run_{repetition:03d}"
        run_dir.mkdir(parents=True, exist_ok=True)
        try:
            research_artifact = await researcher.run(
                template_root=TEACHER_ROOT / "hypothesis_researcher",
                role_id="hypothesis_researcher",
                role_version=1,
                role_input={
                    "problem_direction": failure.model_dump(mode="json")
                },
                resource_config=resources,
            )
        except TeacherRoleRunFailed as exc:
            path = _write_json(run_dir / "researcher.failed.json", exc.failure_artifact)
            results.append(
                {
                    "repetition": repetition,
                    "status": "researcher_failed",
                    "artifact": str(path),
                    "error": str(exc),
                    "researcher_tokens": _tokens(exc.failure_artifact),
                }
            )
            continue
        research_path = _write_json(run_dir / "researcher.json", research_artifact)
        hypothesis = InterventionHypothesis.model_validate(
            research_artifact.get("output")
        )
        selection = intervention.select_trial(
            failure=failure,
            hypothesis=hypothesis,
            rollout_file=rollout_file,
            used_assignments=set(),
            assignment_count=0,
            trial_batch_size=1,
            remaining_trial_budget=1,
            remaining_assignment_budget=1,
            prior_obligation=None,
            work_dir=run_dir / "selection",
        )
        assignments = selection.outcome.get("assignments")
        if not isinstance(assignments, list) or not assignments:
            results.append(
                {
                    "repetition": repetition,
                    "status": "selection_exhausted",
                    "researcher_artifact": str(research_path),
                    "hypothesis": hypothesis.model_dump(mode="json"),
                    "researcher_tools": _tool_names(research_artifact),
                    "researcher_tokens": _tokens(research_artifact),
                }
            )
            continue
        trial = await intervention.execute_trial(
            assignment=dict(assignments[0]),
            hypothesis=hypothesis.model_dump(mode="json"),
            rollout_file=rollout_file,
            work_dir=run_dir / "trial",
        )
        trial_path = Path(trial.artifact_refs["worker_artifact"])
        trial_artifact = _read_json(trial_path)
        intervention_trial = (
            trial_artifact.get("resource_artifacts", {}).get(
                "intervention_trial", {}
            )
        )
        results.append(
            {
                "repetition": repetition,
                "status": "completed",
                "researcher_artifact": str(research_path),
                "trial_artifact": str(trial_path),
                "hypothesis": hypothesis.model_dump(mode="json"),
                "assignment": assignments[0],
                "researcher_tools": _tool_names(research_artifact),
                "researcher_tokens": _tokens(research_artifact),
                "worker_output": trial.outcome.get("output"),
                "worker_tools": _tool_names(trial_artifact),
                "worker_tokens": _tokens(trial_artifact),
                "trial_state": (
                    intervention_trial.get("trial_state")
                    if isinstance(intervention_trial, dict)
                    else None
                ),
                "context_changes": (
                    intervention_trial.get("context_changes")
                    if isinstance(intervention_trial, dict)
                    else None
                ),
                "branch_answer": (
                    intervention_trial.get("branch_run", {}).get("answer")
                    if isinstance(intervention_trial, dict)
                    else None
                ),
            }
        )
        print(f"completed repetition={repetition}", flush=True)

    _write_json(
        output_dir / "summary.json",
        {
            "schema_version": 1,
            "source_run": str(source_run),
            "failure_artifact": str(
                source_run / "artifacts" / args.failure_work / "role.json"
            ),
            "results": results,
        },
    )


def _only_directory(root: Path, prefix: str) -> Path:
    matches = sorted(path for path in root.iterdir() if path.name.startswith(prefix))
    if len(matches) != 1:
        raise ValueError(f"expected one {prefix} directory, got {len(matches)}")
    return matches[0]


def _tool_names(artifact: dict[str, Any]) -> list[str]:
    return [
        str(item.get("name"))
        for item in artifact.get("tool_calls", [])
        if isinstance(item, dict)
    ]


def _tokens(artifact: dict[str, Any]) -> int:
    usage = artifact.get("usage")
    value = usage.get("total_tokens") if isinstance(usage, dict) else 0
    return value if isinstance(value, int) else 0


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path.resolve()


if __name__ == "__main__":
    asyncio.run(main())
