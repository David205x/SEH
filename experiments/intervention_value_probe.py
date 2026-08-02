"""Run a paired probe of whether soft intervention can improve Student behavior.

The script deliberately separates three concerns:

1. ``prepare`` exposes Student-visible prefixes without golden answers.
2. ``run`` executes a no-op control and a Worker-authored treatment.
3. ``review`` joins hidden evaluation evidence after both branches finish.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from search_harness.evolution.research.intervention.prefix import (
    build_prefix_timeline,
    load_rollout_record,
)
from search_harness.evaluation import EvaluationCase, HotpotQAEvaluator
from search_harness.evolution.research.roles.contracts import (
    InterventionHypothesis,
    InterventionWorkerInput,
)
from search_harness.evolution.research.resources.stores import (
    InterventionBranchStore,
    InterventionResourceConfig,
)


class ProbeCase(BaseModel):
    """One source trajectory selected for a paired branch experiment."""

    model_config = ConfigDict(extra="forbid")

    example_id: str = Field(min_length=1)
    replicate_id: str = Field(default="r000", min_length=1)
    prefix_id: int | None = Field(default=None, ge=1)


class PrepareRequest(BaseModel):
    """Researcher-owned configuration used to construct a Worker brief."""

    model_config = ConfigDict(extra="forbid")

    hypothesis: InterventionHypothesis
    trial_objective: str = Field(min_length=1)
    rollout_file: Path
    student_template_root: Path
    env_file: Path = Path(".env")
    student_max_steps: int = Field(default=8, ge=1)
    control_mode: Literal["rerun", "source"] = "rerun"
    cases: list[ProbeCase] = Field(min_length=1)
    prohibited_content: list[str] = Field(default_factory=list)


class WorkerTrialPlan(BaseModel):
    """One Worker-selected context action for one case."""

    model_config = ConfigDict(extra="forbid")

    example_id: str = Field(min_length=1)
    replicate_id: str = Field(min_length=1)
    action: str
    content: str | None = None
    rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_content(self) -> "WorkerTrialPlan":
        if self.action == "no_op":
            if self.content is not None:
                raise ValueError("no_op must not include content")
        elif not self.content or not self.content.strip():
            raise ValueError(f"{self.action} requires non-empty content")
        return self


class WorkerPlan(BaseModel):
    """Sub-agent output consumed by the deterministic experiment runner."""

    model_config = ConfigDict(extra="forbid")

    mechanism_summary: str = Field(min_length=1)
    trials: list[WorkerTrialPlan] = Field(min_length=1)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser(
        "prepare",
        help="Create a golden-free brief for an Intervention Worker.",
    )
    prepare.add_argument("request_file", type=Path)
    prepare.add_argument("--output-dir", type=Path, required=True)

    run = subparsers.add_parser(
        "run",
        help="Run paired no-op and intervention branches from a Worker plan.",
    )
    run.add_argument("brief_file", type=Path)
    run.add_argument("plan_file", type=Path)
    run.add_argument("--output-dir", type=Path, required=True)

    review = subparsers.add_parser(
        "review",
        help="Join golden evidence after execution for researcher review.",
    )
    review.add_argument("experiment_file", type=Path)
    review.add_argument("--report-dir", type=Path, required=True)
    review.add_argument("--output-file", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    if args.command == "prepare":
        brief_file = prepare_worker_brief(args.request_file, args.output_dir)
        print(f"Worker brief written to: {brief_file}")
    elif args.command == "run":
        experiment_file = run_paired_experiment(
            args.brief_file,
            args.plan_file,
            args.output_dir,
        )
        print(f"Paired experiment written to: {experiment_file}")
    else:
        review_file = build_review_bundle(
            args.experiment_file,
            args.report_dir,
            args.output_file,
        )
        print(f"Review bundle written to: {review_file}")


def prepare_worker_brief(request_file: Path, output_dir: Path) -> Path:
    """Create a no-golden Worker brief with one reconstructable prefix per case."""

    request = PrepareRequest.model_validate(_read_json(request_file))
    cases = []
    identities: set[tuple[str, str]] = set()
    for selected in request.cases:
        identity = (selected.example_id, selected.replicate_id)
        if identity in identities:
            raise ValueError(f"duplicate probe case: {identity[0]}/{identity[1]}")
        identities.add(identity)
        record = load_rollout_record(
            request.rollout_file,
            selected.example_id,
            selected.replicate_id,
        )
        timeline = build_prefix_timeline(record)
        prefix_id = selected.prefix_id or _first_post_tool_prefix(timeline)
        boundary = _timeline_item(timeline, prefix_id)
        task = InterventionWorkerInput(
            hypothesis=request.hypothesis,
            trial_objective=request.trial_objective,
            example_id=selected.example_id,
            replicate_id=selected.replicate_id,
            prefix_id=prefix_id,
            prohibited_content=request.prohibited_content,
        )
        store = InterventionBranchStore(
            InterventionResourceConfig(
                rollout_file=request.rollout_file,
                student_template_root=request.student_template_root,
                env_file=request.env_file,
                student_max_steps=request.student_max_steps,
            )
        )
        store.bind(task)
        prefix = store.inspect_selected_prefix()
        cases.append(
            {
                "example_id": selected.example_id,
                "replicate_id": selected.replicate_id,
                "prefix_id": prefix_id,
                "boundary": boundary,
                "question": prefix["question"],
                "student_visible_model_input": prefix["model_input"],
                "active_stage": prefix["active_stage"],
            }
        )

    brief = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "purpose": (
            "Design one bounded, answer-free context intervention per case. "
            "The same causal mechanism must be expressed across all cases."
        ),
        "hypothesis": request.hypothesis.model_dump(mode="json"),
        "trial_objective": request.trial_objective,
        "prohibited_content": request.prohibited_content,
        "worker_instructions": [
            "Use only the question and Student-visible prefix evidence.",
            "Do not provide an answer, answer-equivalent fact, or ready-made query.",
            "Choose one supported context action per case.",
            "Keep case-specific wording limited to identifying visible evidence gaps.",
            "Do not evaluate success; execution and review happen after planning.",
        ],
        "supported_actions": {
            "append_user_message": "Append one user message for the next generation.",
            "append_system_message": (
                "Append one system message for the next generation."
            ),
            "replace_system_instruction": (
                "Replace the system instruction while preserving visible history."
            ),
            "defer_final_answer": (
                "At a pre_final prefix, reject the current answer once with feedback."
            ),
            "no_op": "Leave the Student-visible prefix unchanged.",
        },
        "resources": {
            "rollout_file": str(request.rollout_file.resolve()),
            "student_template_root": str(request.student_template_root.resolve()),
            "env_file": str(request.env_file.resolve()),
            "student_max_steps": request.student_max_steps,
            "control_mode": request.control_mode,
        },
        "cases": cases,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "worker_brief.json"
    _write_json(output_file, brief)
    return output_file


def run_paired_experiment(
    brief_file: Path,
    plan_file: Path,
    output_dir: Path,
) -> Path:
    """Run a paired control/treatment branch for every Worker plan item."""

    brief = _read_json(brief_file)
    plan = WorkerPlan.model_validate(_read_json(plan_file))
    cases = _require_list(brief, "cases")
    plan_by_identity = {
        (trial.example_id, trial.replicate_id): trial for trial in plan.trials
    }
    if len(plan_by_identity) != len(plan.trials):
        raise ValueError("Worker plan contains duplicate case identities")
    expected = {
        (str(case["example_id"]), str(case["replicate_id"])) for case in cases
    }
    if set(plan_by_identity) != expected:
        missing = sorted(expected - set(plan_by_identity))
        unexpected = sorted(set(plan_by_identity) - expected)
        raise ValueError(
            f"Worker plan identities do not match brief; "
            f"missing={missing}, unexpected={unexpected}"
        )

    resources = _require_object(brief, "resources")
    hypothesis = InterventionHypothesis.model_validate(
        _require_object(brief, "hypothesis")
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for index, case in enumerate(cases, start=1):
        identity = (str(case["example_id"]), str(case["replicate_id"]))
        treatment = plan_by_identity[identity]
        print(f"Running paired trial {index}/{len(cases)}: {identity[0]}/{identity[1]}")
        task = InterventionWorkerInput(
            hypothesis=hypothesis,
            trial_objective=str(brief["trial_objective"]),
            example_id=identity[0],
            replicate_id=identity[1],
            prefix_id=int(case["prefix_id"]),
            prohibited_content=[
                str(item) for item in _require_list(brief, "prohibited_content")
            ],
        )
        config = InterventionResourceConfig(
            rollout_file=Path(str(resources["rollout_file"])),
            student_template_root=Path(str(resources["student_template_root"])),
            env_file=Path(str(resources["env_file"])),
            student_max_steps=int(resources["student_max_steps"]),
        )
        control_mode = str(resources.get("control_mode") or "rerun")
        if control_mode == "rerun":
            control = _run_branch(
                task=task,
                config=config,
                action="no_op",
                content=None,
                rationale=(
                    "Paired control from the same prefix without context changes."
                ),
            )
        elif control_mode == "source":
            control = _source_control_artifact(task, config)
        else:
            raise ValueError(f"unsupported control_mode: {control_mode}")
        treatment_artifact = _run_branch(
            task=task,
            config=config,
            action=treatment.action,
            content=treatment.content,
            rationale=treatment.rationale,
        )
        case_dir = output_dir / f"{index:02d}_{identity[0]}_{identity[1]}"
        case_dir.mkdir(parents=True, exist_ok=True)
        _write_json(case_dir / "control_trace.json", control)
        _write_json(case_dir / "treatment_trace.json", treatment_artifact)
        records.append(
            {
                "example_id": identity[0],
                "replicate_id": identity[1],
                "prefix_id": task.prefix_id,
                "worker_action": treatment.model_dump(mode="json"),
                "control_artifact": str(
                    (case_dir / "control_trace.json").resolve()
                ),
                "treatment_artifact": str(
                    (case_dir / "treatment_trace.json").resolve()
                ),
                "control": control["comparison"]["branch"],
                "treatment": treatment_artifact["comparison"]["branch"],
            }
        )

    experiment = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "brief_file": str(brief_file.resolve()),
        "plan_file": str(plan_file.resolve()),
        "mechanism_summary": plan.mechanism_summary,
        "paired_seed_policy": (
            "For rerun controls, control and treatment load the same STUDENT "
            "configuration and source prefix. For source controls, the retained "
            "source answer is compared with a treatment fork at that boundary."
        ),
        "records": records,
    }
    experiment_file = output_dir / "experiment.json"
    _write_json(experiment_file, experiment)
    return experiment_file


def build_review_bundle(
    experiment_file: Path,
    report_dir: Path,
    output_file: Path,
) -> Path:
    """Add hidden reference evidence and deterministic metrics for final review."""

    experiment = _read_json(experiment_file)
    report_items = _load_report_items(report_dir / "per_example.jsonl")
    evaluator = HotpotQAEvaluator()
    reviewed = []
    for record in _require_list(experiment, "records"):
        example_id = str(record["example_id"])
        report = report_items.get(example_id)
        if report is None:
            raise KeyError(f"evaluation report lacks example_id: {example_id}")
        question = str(report.get("question") or "")
        golden = report.get("golden_answer")
        if not isinstance(golden, str):
            raise ValueError(f"golden answer is missing for {example_id}")
        branches = {}
        for branch_name in ("control", "treatment"):
            branch = _require_object(record, branch_name)
            answer = branch.get("answer")
            static = evaluator.evaluate_static(
                EvaluationCase(
                    example_id=example_id,
                    question=question,
                    golden_answer=golden,
                    predicted_answer=answer if isinstance(answer, str) else None,
                )
            )
            branches[branch_name] = {
                **branch,
                "review_static": {
                    "decision": static.decision.value,
                    "metrics": dict(static.metrics),
                    "reason": static.reason,
                },
            }
        reviewed.append(
            {
                "example_id": example_id,
                "replicate_id": record["replicate_id"],
                "question": question,
                "golden_answer": golden,
                "source_success_rate": report.get("success_rate"),
                "worker_action": record["worker_action"],
                **branches,
                "control_artifact": record["control_artifact"],
                "treatment_artifact": record["treatment_artifact"],
            }
        )

    bundle = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "experiment_file": str(experiment_file.resolve()),
        "mechanism_summary": experiment["mechanism_summary"],
        "records": reviewed,
        "aggregate": _aggregate_review(reviewed),
        "review_note": (
            "Static exact match is deterministic evidence only. The Reviewer must "
            "inspect paired traces before attributing changes to the intervention."
        ),
    }
    _write_json(output_file, bundle)
    return output_file


def _run_branch(
    *,
    task: InterventionWorkerInput,
    config: InterventionResourceConfig,
    action: str,
    content: str | None,
    rationale: str,
) -> dict[str, Any]:
    store = InterventionBranchStore(config)
    store.bind(task)
    store.run_branch(
        action=action,
        content=content,
        rationale=rationale,
    )
    artifact = store.artifact()
    if artifact is None:
        raise RuntimeError("Intervention branch did not produce an artifact")
    return artifact


def _source_control_artifact(
    task: InterventionWorkerInput,
    config: InterventionResourceConfig,
) -> dict[str, Any]:
    """Represent the retained source outcome as a zero-continuation control."""

    record = load_rollout_record(
        config.rollout_file,
        task.example_id,
        task.replicate_id,
    )
    run = _require_object(record, "run")
    summary = {
        "status": run.get("status"),
        "answer": run.get("answer"),
        "error": run.get("error"),
        "model_calls": 0,
        "tool_calls": 0,
    }
    return {
        "trial_id": "source_control",
        "source": {
            "rollout_file": str(config.rollout_file.resolve()),
            "example_id": task.example_id,
            "replicate_id": task.replicate_id,
            "prefix_id": task.prefix_id,
        },
        "action": {
            "action": "source_control",
            "content": None,
            "rationale": "Use the retained source outcome without another generation.",
        },
        "context_changes": [],
        "branch_run": run,
        "comparison": {"branch": summary},
    }


def _first_post_tool_prefix(timeline: list[dict[str, Any]]) -> int:
    for item in timeline:
        if item.get("phase") == "post_tool":
            return int(item["prefix_id"])
    raise ValueError("source trajectory has no reconstructable post_tool prefix")


def _timeline_item(
    timeline: list[dict[str, Any]],
    prefix_id: int,
) -> dict[str, Any]:
    for item in timeline:
        if item.get("prefix_id") == prefix_id:
            return dict(item)
    raise ValueError(f"prefix_id is not present in timeline: {prefix_id}")


def _load_report_items(path: Path) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"evaluation report file does not exist: {path}")
    items = {}
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise TypeError(f"report item at line {line_number} must be an object")
            example_id = str(value.get("example_id") or "")
            if not example_id:
                raise ValueError(f"report item at line {line_number} lacks example_id")
            items[example_id] = value
    return items


def _aggregate_review(records: list[dict[str, Any]]) -> dict[str, Any]:
    def exact(branch: str) -> int:
        return sum(
            int(record[branch]["review_static"]["metrics"].get("exact_match", 0))
            for record in records
        )

    def continuation_tool_calls(branch: str) -> float:
        values = [
            record[branch].get("tool_calls")
            for record in records
            if isinstance(record[branch].get("tool_calls"), int)
        ]
        return sum(values) / len(values) if values else 0.0

    control_exact = exact("control")
    treatment_exact = exact("treatment")
    return {
        "cases": len(records),
        "control_exact_match": control_exact,
        "treatment_exact_match": treatment_exact,
        "exact_match_delta": treatment_exact - control_exact,
        "control_mean_continuation_tool_calls": continuation_tool_calls("control"),
        "treatment_mean_continuation_tool_calls": continuation_tool_calls(
            "treatment"
        ),
    }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON at {path}: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise TypeError(f"JSON root must be an object: {path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _require_object(value: dict[str, Any], key: str) -> dict[str, Any]:
    selected = value.get(key)
    if not isinstance(selected, dict):
        raise TypeError(f"{key} must be an object")
    return selected


def _require_list(value: dict[str, Any], key: str) -> list[Any]:
    selected = value.get(key)
    if not isinstance(selected, list):
        raise TypeError(f"{key} must be an array")
    return selected


if __name__ == "__main__":
    main()
