"""Standalone Intervention Coordinator assembly and artifact persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from search_harness.adapter.critic.types import validate_problem_direction
from search_harness.core import AgentLoop, ModelClient, TaggedOutputParser, ToolRuntime
from search_harness.paths import COMPONENT_RUNS_ROOT, INTERVENTION_COORDINATOR_TEMPLATE_ROOT
from search_harness.registry import build_harness

from .coordinator_context import InterventionCoordinatorContext, WorkerTrialRunner
from .coordinator_types import InterventionCoordinatorResult
from .runtime import InterventionRunner, InterventionRuntimeConfig, _build_model


DEFAULT_COORDINATOR_TASK = (
    "Use the bound Critic problem direction and evaluation failure pool to discover "
    "one bounded intervention hypothesis, "
    "validate the same mechanism on additional relevant failed cases, compare measured "
    "effects and costs, and recommend it only when cross-case evidence supports "
    "generalization or report that none is sufficiently supported."
)


@dataclass(frozen=True)
class InterventionCoordinatorConfig:
    """Standalone Coordinator and nested Worker runtime settings."""

    env_file: Path = Path(".env")
    plugins_root: Path = INTERVENTION_COORDINATOR_TEMPLATE_ROOT
    output_root: Path = COMPONENT_RUNS_ROOT / "intervention_coordinator"
    model_role: str = "teacher"
    max_steps: int = 40
    max_trials: int = 10
    worker: InterventionRuntimeConfig | None = None

    def __post_init__(self) -> None:
        if self.max_steps < 1:
            raise ValueError("coordinator max_steps must be positive")
        if self.max_trials < 1:
            raise ValueError("coordinator max_trials must be positive")


class InterventionCoordinatorRunner:
    """Let one teacher Coordinator propose and compare independent Worker trials."""

    def __init__(
        self,
        config: InterventionCoordinatorConfig | None = None,
        *,
        coordinator_model: ModelClient | None = None,
        worker_runner: WorkerTrialRunner | None = None,
    ) -> None:
        self.config = config or InterventionCoordinatorConfig()
        self._coordinator_model = coordinator_model
        self._worker_runner = worker_runner

    def run(
        self,
        *,
        rollout_file: Path | None = None,
        example_id: str | None = None,
        report_dir: Path | None = None,
        critic_log: Path | None = None,
        direction_index: int = 0,
        problem_direction: dict[str, Any] | None = None,
        previous_intervention_log: Path | None = None,
        compiler_feedback: str | None = None,
        task: str = DEFAULT_COORDINATOR_TASK,
    ) -> dict[str, Any]:
        """Run one bounded Coordinator session and persist its complete ledger."""

        source_rollout = _resolve_rollout_file(rollout_file, report_dir)
        direction_source = _resolve_problem_direction(
            critic_log=critic_log,
            direction_index=direction_index,
            problem_direction=problem_direction,
            rollout_file=source_rollout,
            report_dir=report_dir,
        )
        worker_config = self.config.worker or InterventionRuntimeConfig(
            env_file=self.config.env_file
        )
        prior = _load_previous_intervention(previous_intervention_log)
        worker_runner = self._worker_runner or InterventionRunner(worker_config)
        context = InterventionCoordinatorContext(
            rollout_file=source_rollout,
            example_id=example_id,
            report_dir=report_dir,
            worker_runner=worker_runner,
            max_trials=self.config.max_trials,
            problem_direction=direction_source["problem_direction"],
            prior_trials=prior["trials"],
            compiler_feedback=compiler_feedback,
        )
        components = build_harness(
            self.config.plugins_root,
            env_file=self.config.env_file,
            runtime_context=context,
        )
        model = self._coordinator_model or _build_model(
            env_file=self.config.env_file,
            model_role=self.config.model_role,
            intervention_timeout=True,
        )
        loop = AgentLoop(
            model=model,
            prompt_builder=components.prompt_builder,
            parser=TaggedOutputParser(),
            tool_runtime=ToolRuntime(components.tools.tools),
            max_steps=self.config.max_steps,
            hooks=components.hooks,
        )
        output_dir = _new_output_dir(self.config.output_root)
        artifact_file = output_dir / "coordinator.json"
        artifact: dict[str, Any] = {
            "schema_version": 1,
            "created_at": datetime.now(UTC).isoformat(),
            "source": context.initial_context(),
            "direction_source": direction_source,
            "runtime": {
                "coordinator_plugins_root": str(self.config.plugins_root.resolve()),
                "coordinator_model_role": self.config.model_role,
                "max_steps": self.config.max_steps,
                "max_trials": self.config.max_trials,
                "worker_plugins_root": str(worker_config.plugins_root.resolve()),
            },
            "task": task,
            "revision_source": {
                "previous_intervention_log": (
                    str(previous_intervention_log.resolve())
                    if previous_intervention_log is not None
                    else None
                ),
                "compiler_feedback": compiler_feedback,
                "prior_trial_count": context.prior_trial_count,
                "new_trial_count": len(context.new_trials),
            },
            "coordinator_result": None,
            "trials": [],
            "run": None,
            "result_error": None,
        }
        output_dir.mkdir(parents=True, exist_ok=False)
        try:
            run = loop.run(task)
            artifact["run"] = run.to_dict()
            artifact["trials"] = list(context.trials)
            if run.answer is None:
                raise RuntimeError(
                    f"Intervention Coordinator did not complete: "
                    f"{run.status.value}: {run.error}"
                )
            result = parse_coordinator_result(run.answer)
            _validate_coordinator_result(result, context.trials)
            artifact["coordinator_result"] = result.to_dict()
        except (RuntimeError, TypeError, ValueError) as exc:
            artifact["source"] = context.initial_context()
            artifact["trials"] = list(context.trials)
            artifact["result_error"] = f"{type(exc).__name__}: {exc}"
            _write_artifact(artifact_file, artifact)
            raise RuntimeError(
                f"Intervention Coordinator failed; log written to {artifact_file.resolve()}: "
                f"{exc}"
            ) from exc
        artifact["source"] = context.initial_context()
        _write_artifact(artifact_file, artifact)
        artifact["artifact_file"] = str(artifact_file.resolve())
        return artifact


def parse_coordinator_result(answer: str) -> InterventionCoordinatorResult:
    """Parse the Coordinator's JSON final-answer payload."""

    try:
        payload = json.loads(answer.strip())
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Coordinator final answer is not valid JSON: {exc.msg}"
        ) from exc
    if not isinstance(payload, dict):
        raise ValueError("Coordinator final answer must be a JSON object")
    return InterventionCoordinatorResult.from_dict(payload)


def _validate_coordinator_result(
    result: InterventionCoordinatorResult,
    trials: tuple[dict[str, Any], ...],
) -> None:
    trial_ids = {trial["trial_id"] for trial in trials}
    if result.selected_trial_id is not None and result.selected_trial_id not in trial_ids:
        raise ValueError(f"Coordinator selected unknown trial: {result.selected_trial_id}")
    selected = next(
        (trial for trial in trials if trial["trial_id"] == result.selected_trial_id),
        None,
    )
    if selected is not None and selected["status"] != "completed":
        raise ValueError(f"Coordinator selected failed trial: {result.selected_trial_id}")
    if result.verdict == "supported" and selected is None:
        raise ValueError("supported Coordinator result must select a completed trial")


def _write_artifact(path: Path, artifact: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _new_output_dir(root: Path) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return root.resolve() / timestamp


def _load_previous_intervention(path: Path | None) -> dict[str, Any]:
    """Load an immutable prior trial ledger for one Compiler-requested revision."""

    if path is None:
        return {"trials": []}
    raw = json.loads(path.read_text(encoding="utf-8"))
    trials = raw.get("trials")
    if not isinstance(trials, list) or not all(isinstance(item, dict) for item in trials):
        raise ValueError("previous intervention log must contain a trial list")
    return {"trials": trials}


def _resolve_rollout_file(
    rollout_file: Path | None,
    report_dir: Path | None,
) -> Path:
    if rollout_file is not None:
        return rollout_file
    if report_dir is None:
        raise ValueError("coordinator requires rollout_file or report_dir")
    summary_file = report_dir / "summary.json"
    if not summary_file.is_file():
        raise FileNotFoundError(f"evaluation summary does not exist: {summary_file}")
    try:
        summary = json.loads(summary_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"invalid evaluation summary JSON at {summary_file}: {exc.msg}"
        ) from exc
    if not isinstance(summary, dict) or not isinstance(summary.get("source_file"), str):
        raise ValueError("evaluation summary must contain string source_file")
    return Path(summary["source_file"])


def _resolve_problem_direction(
    *,
    critic_log: Path | None,
    direction_index: int,
    problem_direction: dict[str, Any] | None,
    rollout_file: Path,
    report_dir: Path | None,
) -> dict[str, Any]:
    if direction_index < 0:
        raise ValueError("direction_index must not be negative")
    if critic_log is None:
        if problem_direction is None:
            raise ValueError("coordinator requires critic_log or problem_direction")
        direction = _validated_direction(problem_direction, direction_index)
        return {
            "critic_log": None,
            "direction_index": direction_index,
            "critic_analysis": None,
            "problem_direction": direction,
            "critic_inputs": None,
        }
    if problem_direction is not None:
        raise ValueError("provide critic_log or problem_direction, not both")
    path = critic_log.resolve()
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TypeError("Critic log must contain a JSON object")
    result = raw.get("critic_result")
    if not isinstance(result, dict):
        raise ValueError("Critic log has no completed critic_result")
    directions = result.get("problem_directions")
    analysis = result.get("analysis")
    if not isinstance(analysis, str) or not analysis.strip():
        raise ValueError("Critic result has no analysis")
    if not isinstance(directions, list) or not directions:
        raise ValueError("Critic result has no problem directions")
    if direction_index >= len(directions):
        raise IndexError(f"Critic direction index out of range: {direction_index}")
    inputs = raw.get("inputs")
    if not isinstance(inputs, dict):
        raise ValueError("Critic log has no provenance inputs")
    if Path(str(inputs.get("rollout_file"))).resolve() != rollout_file.resolve():
        raise ValueError("Critic rollout does not match Coordinator rollout")
    if (
        report_dir is not None
        and Path(str(inputs.get("report_dir"))).resolve() != report_dir.resolve()
    ):
        raise ValueError("Critic report does not match Coordinator report")
    return {
        "critic_log": str(path),
        "direction_index": direction_index,
        "critic_analysis": analysis.strip(),
        "problem_direction": _validated_direction(
            directions[direction_index], direction_index
        ),
        "critic_inputs": dict(inputs),
    }


def _validated_direction(value: Any, index: int) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"Critic problem direction {index} must be an object")
    return validate_problem_direction(value, index=index)
