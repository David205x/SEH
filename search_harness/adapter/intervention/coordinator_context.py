"""Case-bound state and Worker trial ledger for Intervention coordination."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Annotated, Any, Protocol

from search_harness.core import HookPhase, ToolResult
from search_harness.framework.tooling import CallableTool, ToolArg, ToolDefinition, tool

from .prefix import (
    build_prefix_timeline,
    load_rollout_record,
    resolve_prefix_boundary,
    summarize_rollout_example,
)


class WorkerTrialRunner(Protocol):
    """Minimal Worker runtime capability required by the Coordinator."""

    def run(
        self,
        *,
        rollout_file: Path,
        example_id: str,
        replicate_id: str,
        fork_step: int,
        fork_phase: str,
        intent: str,
        hook_guidance: dict[str, str],
    ) -> dict[str, Any]:
        """Execute one isolated Worker trial."""


class InterventionCoordinatorContext:
    """Bind a rollout, optional failure pool and independent Worker trial ledger."""

    def __init__(
        self,
        *,
        rollout_file: Path,
        example_id: str | None,
        report_dir: Path | None,
        worker_runner: WorkerTrialRunner,
        max_trials: int,
        problem_direction: dict[str, Any],
        prior_trials: list[dict[str, Any]] | None = None,
        compiler_feedback: str | None = None,
    ) -> None:
        if max_trials < 1:
            raise ValueError("coordinator max_trials must be positive")
        self.rollout_file = rollout_file.resolve()
        self.report_dir = report_dir.resolve() if report_dir is not None else None
        self.worker_runner = worker_runner
        self.max_trials = max_trials
        self.problem_direction = json.loads(
            json.dumps(problem_direction, ensure_ascii=False)
        )
        self.compiler_feedback = (
            compiler_feedback.strip()
            if isinstance(compiler_feedback, str) and compiler_feedback.strip()
            else None
        )
        self._prior_trials = json.loads(
            json.dumps(prior_trials or [], ensure_ascii=False)
        )
        self._failed_cases = _load_failed_cases(self.report_dir)
        self.example_id: str | None = None
        self._trials: list[dict[str, Any]] = []
        if example_id is not None:
            self.select_failed_case(
                example_id,
                require_failed=self.report_dir is not None,
            )
        elif self.report_dir is None:
            raise ValueError("coordinator requires example_id or report_dir")

    @property
    def trials(self) -> tuple[dict[str, Any], ...]:
        """Return completed trial summaries in execution order."""

        return tuple(
            json.loads(json.dumps(item, ensure_ascii=False))
            for item in (*self._prior_trials, *self._trials)
        )

    @property
    def new_trials(self) -> tuple[dict[str, Any], ...]:
        """Return only trials executed during the current Coordinator session."""

        return tuple(
            json.loads(json.dumps(item, ensure_ascii=False)) for item in self._trials
        )

    @property
    def prior_trial_count(self) -> int:
        """Return the immutable trial-ledger length inherited from the previous pass."""

        return len(self._prior_trials)

    def initial_context(self) -> dict[str, Any]:
        """Return the golden-free case summary injected into the first prompt."""

        selected = self._selected_evaluation()
        if selected is None and self.example_id is not None:
            selected = summarize_rollout_example(
                self.rollout_file, self.example_id
            )
        return {
            "rollout_file": str(self.rollout_file),
            "report_dir": str(self.report_dir) if self.report_dir is not None else None,
            "example_id": self.example_id,
            "question": selected.get("question") if selected is not None else None,
            "stability": selected.get("stability") if selected is not None else None,
            "success_rate": selected.get("success_rate") if selected is not None else None,
            "available_replicates": (
                selected.get("replicates", []) if selected is not None else []
            ),
            "failed_case_count": len(self._failed_cases),
            "max_trials": self.max_trials,
            "prior_trial_count": self.prior_trial_count,
            "compiler_feedback": self.compiler_feedback,
            "problem_direction": dict(self.problem_direction),
            "available_hook_phases": list(HookPhase.ALL),
            "golden_answer_available": False,
        }

    def inspect_source_case(
        self, *, example_id: str, replicate_id: str, detail: str
    ) -> dict[str, Any]:
        """Return a compact or complete Actor run without reference-answer fields."""

        self.select_failed_case(
            example_id, require_failed=self.report_dir is not None
        )
        record = load_rollout_record(
            self.rollout_file, example_id, replicate_id
        )
        example = _object(record, "example")
        run = _object(record, "run")
        payload = {
            "example_id": self.example_id,
            "replicate_id": replicate_id,
            "question": example.get("question") or run.get("question"),
            "source_status": run.get("status"),
            "source_answer": run.get("answer"),
            "prefix_timeline": build_prefix_timeline(record),
            "completed_trials": list(self.trials),
        }
        if detail == "full":
            payload["source_run"] = run
        elif detail == "summary":
            payload["trace_summary"] = _trace_summary(run.get("trace"))
        else:
            raise ValueError("inspection detail must be summary or full")
        return payload

    def list_failed_cases(self, *, page: int, page_size: int) -> dict[str, Any]:
        """Return one deterministic page from the evaluation score-zero pool."""

        self._require_failure_pool()
        if page < 1:
            raise ValueError("page must be positive")
        if page_size < 1 or page_size > 100:
            raise ValueError("page_size must be between 1 and 100")
        total_items = len(self._failed_cases)
        total_pages = max(1, (total_items + page_size - 1) // page_size)
        if page > total_pages:
            raise ValueError(f"page exceeds total_pages={total_pages}")
        start = (page - 1) * page_size
        return {
            "items": [
                _public_failed_case(item)
                for item in self._failed_cases[start : start + page_size]
            ],
            "page": page,
            "page_size": page_size,
            "total_items": total_items,
            "total_pages": total_pages,
            "selected_example_id": self.example_id,
        }

    def select_failed_case(
        self,
        example_id: str,
        *,
        require_failed: bool = True,
    ) -> dict[str, Any]:
        """Select one logical example and return its aggregate replicate summary."""

        if not example_id.strip():
            raise ValueError("example_id must not be empty")
        evaluation = next(
            (
                item
                for item in self._failed_cases
                if item.get("example_id") == example_id
            ),
            None,
        )
        if require_failed and evaluation is None:
            raise KeyError(f"example_id is not in the failed case pool: {example_id}")
        self.example_id = example_id
        return _public_failed_case(evaluation) or summarize_rollout_example(
            self.rollout_file, example_id
        )

    def sample_failed_case(self, *, seed: int) -> dict[str, Any]:
        """Reproducibly select one failure using a caller-provided seed."""

        self._require_failure_pool()
        selected = random.Random(seed).choice(self._failed_cases)
        result = self.select_failed_case(str(selected["example_id"]))
        result["seed"] = seed
        return result

    def run_worker_trial(
        self,
        *,
        example_id: str,
        replicate_id: str,
        intent: str,
        prefix_id: int,
        hook_phases: list[str],
        hook_instructions: list[str],
    ) -> dict[str, Any]:
        """Validate one scheme, run a fresh Worker branch and record its effect."""

        if len(self._trials) >= self.max_trials:
            raise RuntimeError(f"coordinator trial budget exhausted: {self.max_trials}")
        if not intent.strip():
            raise ValueError("worker trial intent must not be empty")
        self.select_failed_case(
            example_id, require_failed=self.report_dir is not None
        )
        record = load_rollout_record(
            self.rollout_file, example_id, replicate_id
        )
        boundary = resolve_prefix_boundary(record, prefix_id)
        fork_step = int(boundary["step"])
        fork_phase = str(boundary["phase"])
        guidance = _hook_guidance(hook_phases, hook_instructions)
        trial_id = f"trial_{self.prior_trial_count + len(self._trials) + 1:03d}"
        base = {
            "trial_id": trial_id,
            "example_id": example_id,
            "replicate_id": replicate_id,
            "intent": intent.strip(),
            "prefix_id": prefix_id,
            "resolved_boundary": {
                "step": fork_step,
                "phase": fork_phase,
                "event_index": boundary["event_index"],
            },
            "hook_guidance": guidance,
        }
        try:
            artifact = self.worker_runner.run(
                rollout_file=self.rollout_file,
                example_id=example_id,
                replicate_id=replicate_id,
                fork_step=fork_step,
                fork_phase=fork_phase,
                intent=intent.strip(),
                hook_guidance=guidance,
            )
        except Exception as exc:
            summary = {
                **base,
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
                "artifact_file": None,
                "comparison": None,
                "worker_summary": None,
                "intervention_changes": [],
            }
        else:
            summary = {
                **base,
                "status": "completed",
                "error": None,
                "artifact_file": artifact.get("artifact_file"),
                "comparison": artifact.get("comparison"),
                "worker_summary": artifact.get("worker_summary"),
                "intervention_changes": _compact_changes(
                    artifact.get("intervention_changes")
                ),
            }
        self._trials.append(summary)
        return json.loads(json.dumps(summary, ensure_ascii=False))

    def _selected_evaluation(self) -> dict[str, Any] | None:
        if self.example_id is None:
            return None
        return next(
            (
                item
                for item in self._failed_cases
                if item.get("example_id") == self.example_id
            ),
            None,
        )

    def _require_failure_pool(self) -> None:
        if self.report_dir is None:
            raise RuntimeError("coordinator has no evaluation report bound")
        if not self._failed_cases:
            raise RuntimeError("evaluation report contains no failed or unstable cases")


class InspectInterventionCaseTool:
    """Coordinator-facing read tool for its bound source trajectory."""

    def __init__(self, context: InterventionCoordinatorContext) -> None:
        self._context = context
        self._tool = CallableTool.from_callable(self.inspect_intervention_case)

    @property
    def name(self) -> str:
        return self._tool.name

    @property
    def definition(self) -> ToolDefinition:
        return self._tool.definition

    def run(self, arguments: dict[str, object]) -> ToolResult:
        return self._tool.run(arguments)

    @tool(name="inspect_intervention_case")
    def inspect_intervention_case(
        self,
        example_id: Annotated[
            str,
            ToolArg("Logical example ID returned by a case summary tool."),
        ],
        replicate_id: Annotated[
            str,
            ToolArg("Concrete replicate ID listed in that example summary."),
        ],
        detail: Annotated[
            str,
            ToolArg(
                "Use summary by default; request full only when exact source events "
                "are necessary.",
                choices=("summary", "full"),
            ),
        ] = "summary",
    ) -> ToolResult:
        """Read the bound Actor trajectory and prior Worker trial summaries."""

        try:
            payload = self._context.inspect_source_case(
                example_id=example_id,
                replicate_id=replicate_id,
                detail=detail,
            )
        except (KeyError, ValueError, RuntimeError) as exc:
            return _input_error(self.name, exc)
        return ToolResult(
            name=self.name,
            content=json.dumps(payload, ensure_ascii=False),
        )


class RunWorkerTrialTool:
    """Coordinator-facing tool bound to one source case and Worker runtime."""

    def __init__(self, context: InterventionCoordinatorContext) -> None:
        self._context = context
        self._tool = CallableTool.from_callable(self.run_worker_trial)

    @property
    def name(self) -> str:
        return self._tool.name

    @property
    def definition(self) -> ToolDefinition:
        return self._tool.definition

    def run(self, arguments: dict[str, object]) -> ToolResult:
        return self._tool.run(arguments)

    @tool(name="run_worker_trial")
    def run_worker_trial(
        self,
        example_id: Annotated[
            str, ToolArg("Logical example ID for the source trajectory.")
        ],
        replicate_id: Annotated[
            str, ToolArg("Concrete replicate ID for the source trajectory.")
        ],
        intent: Annotated[str, ToolArg("One intervention hypothesis to test.")],
        prefix_id: Annotated[
            int,
            ToolArg(
                "Selectable prefix number from inspect_intervention_case timeline.",
                minimum=1,
            ),
        ],
        hook_phases: Annotated[
            list[str],
            ToolArg("Hook phases activated for this Worker scheme."),
        ],
        hook_instructions: Annotated[
            list[str],
            ToolArg("Instructions aligned positionally with hook_phases."),
        ],
    ) -> ToolResult:
        """Run one fresh Worker on one scheme/case branch and return measured effect."""

        try:
            summary = self._context.run_worker_trial(
                intent=intent,
                example_id=example_id,
                replicate_id=replicate_id,
                prefix_id=prefix_id,
                hook_phases=hook_phases,
                hook_instructions=hook_instructions,
            )
        except (KeyError, ValueError, RuntimeError) as exc:
            return ToolResult(
                name=self.name,
                content=f"TOOL_INPUT_ERROR: {exc}",
                metadata={"error": str(exc), "error_type": "trial_request"},
            )
        return ToolResult(
            name=self.name,
            content=json.dumps(summary, ensure_ascii=False),
            metadata={
                "trial_id": summary["trial_id"],
                "artifact_file": summary["artifact_file"],
            },
        )


class ListFailedCasesTool:
    """Paginated view over stable-failure and unstable evaluation cases."""

    def __init__(self, context: InterventionCoordinatorContext) -> None:
        self._context = context
        self._tool = CallableTool.from_callable(self.list_failed_cases)

    @property
    def name(self) -> str:
        return self._tool.name

    @property
    def definition(self) -> ToolDefinition:
        return self._tool.definition

    def run(self, arguments: dict[str, object]) -> ToolResult:
        return self._tool.run(arguments)

    @tool(name="list_failed_cases")
    def list_failed_cases(
        self,
        page: Annotated[int, ToolArg("One-based result page.", minimum=1)] = 1,
        page_size: Annotated[
            int,
            ToolArg("Cases per page.", minimum=1, maximum=100),
        ] = 20,
    ) -> ToolResult:
        """List logical examples with failed or unstable rollout behavior."""

        try:
            payload = self._context.list_failed_cases(page=page, page_size=page_size)
        except (ValueError, RuntimeError) as exc:
            return _input_error(self.name, exc)
        return ToolResult(name=self.name, content=json.dumps(payload, ensure_ascii=False))


class SelectFailedCaseTool:
    """Select a specific failed evaluation case by stable ID."""

    def __init__(self, context: InterventionCoordinatorContext) -> None:
        self._context = context
        self._tool = CallableTool.from_callable(self.select_failed_case)

    @property
    def name(self) -> str:
        return self._tool.name

    @property
    def definition(self) -> ToolDefinition:
        return self._tool.definition

    def run(self, arguments: dict[str, object]) -> ToolResult:
        return self._tool.run(arguments)

    @tool(name="select_failed_case")
    def select_failed_case(
        self,
        example_id: Annotated[str, ToolArg("Stable example ID from the failure pool.")],
    ) -> ToolResult:
        """Return one failed logical-example summary and replicate directory."""

        try:
            payload = self._context.select_failed_case(example_id)
        except (KeyError, ValueError) as exc:
            return _input_error(self.name, exc)
        return ToolResult(name=self.name, content=json.dumps(payload, ensure_ascii=False))


class SampleFailedCaseTool:
    """Reproducibly sample and select one failed evaluation case."""

    def __init__(self, context: InterventionCoordinatorContext) -> None:
        self._context = context
        self._tool = CallableTool.from_callable(self.sample_failed_case)

    @property
    def name(self) -> str:
        return self._tool.name

    @property
    def definition(self) -> ToolDefinition:
        return self._tool.definition

    def run(self, arguments: dict[str, object]) -> ToolResult:
        return self._tool.run(arguments)

    @tool(name="sample_failed_case")
    def sample_failed_case(
        self,
        seed: Annotated[int, ToolArg("Explicit seed for reproducible selection.")],
    ) -> ToolResult:
        """Randomly select one failed or unstable logical example."""

        try:
            payload = self._context.sample_failed_case(seed=seed)
        except (KeyError, ValueError, RuntimeError) as exc:
            return _input_error(self.name, exc)
        return ToolResult(name=self.name, content=json.dumps(payload, ensure_ascii=False))


def _hook_guidance(phases: list[str], instructions: list[str]) -> dict[str, str]:
    if not phases:
        raise ValueError("hook_phases must not be empty")
    if len(phases) != len(instructions):
        raise ValueError("hook_phases and hook_instructions must have equal length")
    if len(phases) != len(set(phases)):
        raise ValueError("hook_phases must not contain duplicates")
    guidance: dict[str, str] = {}
    for phase, instruction in zip(phases, instructions, strict=True):
        if phase not in HookPhase.ALL:
            raise ValueError(f"unknown Hook phase: {phase}")
        if not instruction.strip():
            raise ValueError(f"Hook instruction for {phase} must not be empty")
        guidance[phase] = instruction.strip()
    return guidance


def _object(record: dict[str, Any], key: str) -> dict[str, Any]:
    value = record.get(key)
    if not isinstance(value, dict):
        raise TypeError(f"rollout record {key} must be an object")
    return json.loads(json.dumps(value, ensure_ascii=False))


def _source_steps(run: dict[str, Any]) -> int | None:
    state = run.get("state")
    if not isinstance(state, dict):
        return None
    step = state.get("step")
    return step if isinstance(step, int) else None


def _trace_summary(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    included = {
        "model_output",
        "tool_call",
        "tool_result",
        "final_answer_candidate",
        "final_answer",
        "final_deferred",
        "invalid_output",
        "tool_error",
    }
    summary = []
    for event in value:
        if not isinstance(event, dict) or event.get("event_type") not in included:
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        compact_payload = {
            key: _truncate_text(item)
            for key, item in payload.items()
            if key != "metadata"
        }
        summary.append(
            {
                "step": event.get("step"),
                "event_type": event.get("event_type"),
                "payload": compact_payload,
            }
        )
    return summary


def _compact_changes(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    changes = []
    for item in value:
        if not isinstance(item, dict):
            continue
        action = item.get("action") if isinstance(item.get("action"), dict) else {}
        changes.append(
            {
                "scope": item.get("scope"),
                "phase": item.get("phase"),
                "step": item.get("step"),
                "action": {
                    "kind": action.get("kind"),
                    "payload": action.get("payload", {}),
                    "reason": action.get("reason", ""),
                },
            }
        )
    return changes


def _truncate_text(value: Any, limit: int = 2000) -> Any:
    if isinstance(value, str) and len(value) > limit:
        return f"{value[:limit]}...[truncated {len(value) - limit} chars]"
    return value


def _load_failed_cases(report_dir: Path | None) -> list[dict[str, Any]]:
    if report_dir is None:
        return []
    path = report_dir / "per_example.jsonl"
    if not path.is_file():
        raise FileNotFoundError(f"evaluation cases file does not exist: {path}")
    cases = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"invalid evaluation JSONL at {path}:{line_number}: {exc.msg}"
                ) from exc
            if not isinstance(value, dict):
                raise TypeError(
                    f"evaluation record at {path}:{line_number} must be an object"
                )
            if value.get("score") == 0 or value.get("stability") == "unstable":
                cases.append(value)
    example_ids = [item.get("example_id") for item in cases]
    if not all(isinstance(item, str) and item for item in example_ids):
        raise ValueError("failed evaluation cases require non-empty example_id")
    if len(example_ids) != len(set(example_ids)):
        raise ValueError("failed evaluation cases contain duplicate example_id")
    return cases


def _public_failed_case(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    static = value.get("static") if isinstance(value.get("static"), dict) else {}
    teacher = value.get("teacher") if isinstance(value.get("teacher"), dict) else None
    return {
        "example_id": value.get("example_id"),
        "question": value.get("question"),
        "predicted_answer": value.get("predicted_answer"),
        "run_status": value.get("run_status"),
        "score": value.get("score"),
        "score_source": value.get("score_source"),
        "stability": value.get("stability"),
        "success_rate": value.get("success_rate"),
        "correct_count": value.get("correct_count"),
        "requested_rollouts": value.get("requested_rollouts"),
        "failed_replicate_ids": value.get("failed_replicate_ids", []),
        "unresolved_replicate_ids": value.get("unresolved_replicate_ids", []),
        "replicates": value.get("replicates", []),
        "static": {
            "decision": static.get("decision"),
            "metrics": static.get("metrics"),
            "reason": static.get("reason"),
        },
        "teacher_score": teacher.get("score") if teacher is not None else None,
    }


def _input_error(name: str, exc: Exception) -> ToolResult:
    message = str(exc)
    return ToolResult(
        name=name,
        content=f"TOOL_INPUT_ERROR: {message}",
        metadata={"error": message, "error_type": "case_selection"},
    )
