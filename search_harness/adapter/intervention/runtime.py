"""Standalone single-case Intervention trial runtime and coordinator-facing tool."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from search_harness.core import (
    AgentLoop,
    HookPhase,
    ModelClient,
    TaggedOutputParser,
    ToolResult,
    ToolRuntime,
)
from search_harness.evaluation import (
    EvaluationCase,
    HotpotQAEvaluator,
    StaticDecision,
    TeacherBinaryJudge,
)
from search_harness.framework.tooling import CallableTool, ToolArg, ToolDefinition, tool
from search_harness.models import OpenAICompatibleTextModel
from search_harness.models.openai_compatible import OpenAICompatibleConfig
from search_harness.paths import ACTOR_TEMPLATE_ROOT, COMPONENT_RUNS_ROOT
from search_harness.registry import build_harness
from search_harness.runtime import get_env_value, parse_float, read_env_file

from .bridge import (
    InterventionContext,
    InterventionHookBridge,
    initial_worker_snapshot,
)
from .prefix import PrefixPromptBuilder, load_reconstructed_prefix
from .types import PrefixSelector
from .worker import InterventionWorker


_PHASE_CHOICES = (
    HookPhase.PRE_PROMPT,
    HookPhase.POST_PROMPT,
    HookPhase.POST_MODEL,
    HookPhase.POST_PARSE,
    HookPhase.PRE_TOOL,
    HookPhase.POST_TOOL,
    HookPhase.PRE_FINAL,
    HookPhase.ON_ERROR,
)
INTERVENTION_REQUEST_TIMEOUT_ENV = "INTERVENTION_REQUEST_TIMEOUT"


@dataclass(frozen=True)
class InterventionRuntimeConfig:
    """Environment and bounded-loop settings for one Intervention tool instance."""

    env_file: Path = Path(".env")
    plugins_root: Path = ACTOR_TEMPLATE_ROOT
    output_root: Path = COMPONENT_RUNS_ROOT / "intervention"
    student_model_role: str = "student"
    teacher_model_role: str = "teacher"
    actor_max_steps: int = 20
    worker_max_steps_per_activation: int = 8
    teacher_judge: bool = False

    def __post_init__(self) -> None:
        if self.actor_max_steps < 1:
            raise ValueError("intervention actor_max_steps must be positive")
        if self.worker_max_steps_per_activation < 1:
            raise ValueError(
                "intervention worker_max_steps_per_activation must be positive"
            )


class InterventionRunner:
    """Execute and persist one Worker-controlled Actor context fork."""

    def __init__(
        self,
        config: InterventionRuntimeConfig | None = None,
        *,
        student_model: ModelClient | None = None,
        teacher_model: ModelClient | None = None,
        judge_model: OpenAICompatibleTextModel | None = None,
    ) -> None:
        self.config = config or InterventionRuntimeConfig()
        self._student_model = student_model
        self._teacher_model = teacher_model
        self._judge_model = judge_model

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
        activation_budgets: dict[str, int] | None = None,
        system_prompt_template: str | None = None,
        persist: bool = True,
    ) -> dict[str, Any]:
        """Run one isolated Intervention Worker and return its complete artifact."""

        guidance = _normalize_guidance(hook_guidance)
        budgets = _normalize_activation_budgets(
            guidance,
            activation_budgets,
            default=self.config.actor_max_steps,
        )
        selector = PrefixSelector(
            rollout_file=rollout_file,
            example_id=example_id,
            replicate_id=replicate_id,
            step=fork_step,
            phase=fork_phase,
        )
        prefix = load_reconstructed_prefix(selector)
        student_model = self._student_model or _build_model(
            env_file=self.config.env_file,
            model_role=self.config.student_model_role,
            intervention_timeout=False,
        )
        teacher_model = self._teacher_model or _build_model(
            env_file=self.config.env_file,
            model_role=self.config.teacher_model_role,
            intervention_timeout=True,
        )
        worker = InterventionWorker(
            model=teacher_model,
            intent=intent,
            hook_guidance=guidance,
            max_steps_per_activation=self.config.worker_max_steps_per_activation,
            system_prompt_template=system_prompt_template,
        )
        intervention_context = InterventionContext(prefix)
        activation_counts = {phase: 0 for phase in guidance}

        initial_guidance = guidance.get(fork_phase)
        if initial_guidance is not None:
            activation_counts[fork_phase] = 1
            action = worker.activate(
                phase=fork_phase,
                guidance=initial_guidance,
                snapshot=initial_worker_snapshot(prefix),
                phase_activation=1,
                max_activations=budgets[fork_phase],
            )
            intervention_context.apply_initial(action)

        components = build_harness(
            self.config.plugins_root,
            env_file=self.config.env_file,
        )
        bridge = InterventionHookBridge(
            worker=worker,
            intervention_context=intervention_context,
            hook_guidance=guidance,
            activation_budgets=budgets,
            initial_activation_counts=activation_counts,
        )
        loop = AgentLoop(
            model=student_model,
            prompt_builder=PrefixPromptBuilder(intervention_context.model_input),
            parser=TaggedOutputParser(),
            tool_runtime=ToolRuntime(components.tools.tools),
            max_steps=self.config.actor_max_steps,
            hooks=components.hooks.extended((bridge,)),
        )
        question = str(prefix.example.get("question") or prefix.source_run.get("question") or "")
        if not question.strip():
            raise ValueError("source rollout question is missing")
        branch_run = loop.run(question)

        judge = None
        if self.config.teacher_judge:
            judge_model = self._judge_model or _build_model(
                env_file=self.config.env_file,
                model_role=self.config.teacher_model_role,
                intervention_timeout=True,
            )
            judge = TeacherBinaryJudge(judge_model, HotpotQAEvaluator())
        comparison = _evaluate_effect(
            prefix.example,
            prefix.source_run,
            branch_run.to_dict(),
            teacher_judge=judge,
        )
        artifact = {
            "schema_version": 1,
            "created_at": datetime.now(UTC).isoformat(),
            "source": {
                "rollout_file": str(prefix.selector.rollout_file),
                "rollout_sha256": _file_digest(prefix.selector.rollout_file),
                "example_id": prefix.selector.example_id,
                "replicate_id": prefix.selector.replicate_id,
                "fork_step": prefix.selector.step,
                "fork_phase": prefix.selector.phase,
                "boundary_inclusive": True,
                "source_run": prefix.source_run,
            },
            "runtime": {
                "plugins_root": str(self.config.plugins_root.resolve()),
                "student_model_role": self.config.student_model_role,
                "teacher_model_role": self.config.teacher_model_role,
                "student_model": _model_provenance(student_model),
                "teacher_model": _model_provenance(teacher_model),
                "actor_max_steps": self.config.actor_max_steps,
                "worker_max_steps_per_activation": self.config.worker_max_steps_per_activation,
                "teacher_judge": self.config.teacher_judge,
            },
            "intent": intent,
            "hook_guidance": guidance,
            "activation_budgets": budgets,
            "activation_counts": bridge.activation_counts,
            "reconstructed_prefix": intervention_context.model_input.to_dict(),
            "intervention_changes": list(intervention_context.changes),
            "phase_effects": _phase_effects(
                list(intervention_context.changes),
                branch_run.to_dict().get("trace"),
            ),
            "branch_run": branch_run.to_dict(),
            "comparison": comparison,
            "worker_trace": list(worker.trace),
        }
        if persist:
            output_dir = _new_trial_dir(self.config.output_root)
            artifact_file = output_dir / "intervention.json"
            output_dir.mkdir(parents=True, exist_ok=False)
            artifact_file.write_text(
                json.dumps(artifact, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            artifact["artifact_file"] = str(artifact_file.resolve())
        return artifact


class RunInterventionWorkerTool:
    """Coordinator-facing adapter around the standalone Intervention runtime."""

    def __init__(self, runner: InterventionRunner) -> None:
        self._runner = runner
        self._tool = CallableTool.from_callable(self.run_intervention_worker)

    @property
    def name(self) -> str:
        return self._tool.name

    @property
    def definition(self) -> ToolDefinition:
        return self._tool.definition

    def run(self, arguments: dict[str, object]) -> ToolResult:
        return self._tool.run(arguments)

    @tool(name="run_intervention_worker")
    def run_intervention_worker(
        self,
        rollout_file: Annotated[
            str,
            ToolArg("UTF-8 Actor rollout JSON or JSONL file."),
        ],
        example_id: Annotated[
            str,
            ToolArg("Stable logical example ID."),
        ],
        replicate_id: Annotated[
            str,
            ToolArg("Replicate ID identifying one concrete rollout trajectory."),
        ],
        fork_step: Annotated[
            int,
            ToolArg("One-based Actor step retained by the inclusive prefix.", minimum=1),
        ],
        fork_phase: Annotated[
            str,
            ToolArg("Inclusive lifecycle boundary phase.", choices=_PHASE_CHOICES),
        ],
        intent: Annotated[
            str,
            ToolArg("General intervention hypothesis the Worker should test."),
        ],
        hook_guidance: Annotated[
            dict[str, object],
            ToolArg("Mapping from Hook phase names to Worker behavior guidance."),
        ],
    ) -> ToolResult:
        """Run one teacher-guided Worker on one Actor prefix and return its effect."""

        artifact = self._runner.run(
            rollout_file=Path(rollout_file),
            example_id=example_id,
            replicate_id=replicate_id,
            fork_step=fork_step,
            fork_phase=fork_phase,
            intent=intent,
            hook_guidance=_normalize_guidance(hook_guidance),
        )
        compact = {
            "artifact_file": artifact["artifact_file"],
            "source": {
                key: artifact["source"][key]
                for key in (
                    "example_id",
                    "replicate_id",
                    "fork_step",
                    "fork_phase",
                )
            },
            "comparison": artifact["comparison"],
            "intervention_changes": artifact["intervention_changes"],
        }
        return ToolResult(
            name=self.name,
            content=json.dumps(compact, ensure_ascii=False),
            metadata={"artifact_file": artifact["artifact_file"]},
        )


def _normalize_guidance(value: dict[str, object]) -> dict[str, str]:
    if not isinstance(value, dict) or not value:
        raise ValueError("hook_guidance must be a non-empty object")
    normalized: dict[str, str] = {}
    for phase, guidance in value.items():
        if phase not in HookPhase.ALL:
            raise ValueError(f"hook_guidance contains unknown phase: {phase}")
        if not isinstance(guidance, str) or not guidance.strip():
            raise ValueError(f"hook guidance for {phase} must be a non-empty string")
        normalized[phase] = guidance.strip()
    return normalized


def _normalize_activation_budgets(
    guidance: dict[str, str],
    value: dict[str, int] | None,
    *,
    default: int,
) -> dict[str, int]:
    if value is None:
        return {phase: default for phase in guidance}
    if set(value) != set(guidance):
        raise ValueError(
            "activation_budgets must contain exactly the guidance phases"
        )
    if any(
        not isinstance(budget, int)
        or isinstance(budget, bool)
        or budget < 1
        for budget in value.values()
    ):
        raise ValueError("activation budgets must be positive integers")
    return dict(value)


def _build_model(
    *,
    env_file: Path,
    model_role: str,
    intervention_timeout: bool,
) -> OpenAICompatibleTextModel:
    config = OpenAICompatibleConfig.from_env(
        env_file=env_file,
        prefix=model_role.upper(),
    )
    if not intervention_timeout:
        return OpenAICompatibleTextModel(config)
    values = read_env_file(env_file)
    timeout = parse_float(
        get_env_value(values, INTERVENTION_REQUEST_TIMEOUT_ENV),
        default=config.timeout,
        name=INTERVENTION_REQUEST_TIMEOUT_ENV,
    )
    return OpenAICompatibleTextModel(replace(config, timeout=timeout))


def _evaluate_effect(
    example: dict[str, Any],
    source_run: dict[str, Any],
    branch_run: dict[str, Any],
    *,
    teacher_judge: TeacherBinaryJudge | None = None,
) -> dict[str, Any]:
    evaluator = HotpotQAEvaluator()
    example_id = str(example.get("example_id") or "")
    question = str(example.get("question") or source_run.get("question") or "")
    golden = example.get("answer") if isinstance(example.get("answer"), str) else None
    source_answer = source_run.get("answer") if isinstance(source_run.get("answer"), str) else None
    branch_answer = branch_run.get("answer") if isinstance(branch_run.get("answer"), str) else None
    source_static = evaluator.evaluate_static(
        EvaluationCase(example_id, question, golden, source_answer)
    )
    branch_static = evaluator.evaluate_static(
        EvaluationCase(example_id, question, golden, branch_answer)
    )
    branch_case = EvaluationCase(example_id, question, golden, branch_answer)
    branch_teacher = None
    if (
        branch_static.decision is StaticDecision.NEEDS_TEACHER
        and teacher_judge is not None
    ):
        judgment = teacher_judge.judge(branch_case)
        branch_teacher = {"score": judgment.score, "error": judgment.error}
    branch_score, branch_score_source = _resolved_score(
        branch_static, branch_teacher
    )
    return {
        "source": {
            "status": source_run.get("status"),
            "answer": source_answer,
            "static": _static_payload(source_static),
            "execution": _execution_summary(source_run),
        },
        "branch": {
            "status": branch_run.get("status"),
            "answer": branch_answer,
            "static": _static_payload(branch_static),
            "teacher": branch_teacher,
            "score": branch_score,
            "score_source": branch_score_source,
            "execution": _execution_summary(branch_run),
        },
        "exact_match_delta": (
            branch_static.metrics.get("exact_match", 0)
            - source_static.metrics.get("exact_match", 0)
        ),
    }


def _resolved_score(
    static: Any, teacher: dict[str, Any] | None
) -> tuple[int | None, str | None]:
    if static.decision is StaticDecision.PASS:
        return 1, "static"
    if static.decision is StaticDecision.AUTOMATIC_ZERO:
        return 0, "static"
    if teacher is not None and teacher.get("score") in {0, 1}:
        return int(teacher["score"]), "teacher"
    return None, None


def _phase_effects(
    changes: list[dict[str, Any]],
    trace: object,
) -> list[dict[str, Any]]:
    """Project each intervention onto its following Actor decision window."""

    events = trace if isinstance(trace, list) else []
    effects: list[dict[str, Any]] = []
    for change in changes:
        if not isinstance(change, dict):
            continue
        phase = str(change.get("phase") or "")
        action = change.get("action")
        action = action if isinstance(action, dict) else {}
        scope = str(change.get("scope") or "branch")
        activation = _positive_int(change.get("phase_activation"), default=1)
        anchor = -1
        anchor_found = scope == "source_boundary"
        if scope == "branch":
            anchor = _hook_anchor_position(
                events,
                phase=phase,
                step=change.get("step"),
            )
            anchor_found = anchor >= 0
        window = events[anchor + 1 :] if anchor_found else []
        next_decision = _next_event(window, "parsed_output")
        next_final = _next_event(window, "final_answer")
        final_index = (
            _event_index(next_final)
            if next_final is not None
            else None
        )
        tool_calls = [
            event
            for event in window
            if _event_type(event) == "tool_call"
            and (
                final_index is None
                or _event_index(event) < final_index
            )
        ]
        effects.append(
            {
                "phase": phase,
                "phase_activation": activation,
                "scope": scope,
                "action_kind": action.get("kind"),
                "modified": action.get("kind")
                != "continue_without_change",
                "activation_step": change.get("step"),
                "anchor_found": anchor_found,
                "next_model_decision": _parsed_decision(next_decision),
                "tool_calls_before_next_final": len(tool_calls),
                "next_final_step": (
                    next_final.get("step")
                    if isinstance(next_final, dict)
                    else None
                ),
            }
        )
    return effects


def _hook_anchor_position(
    events: list[object],
    *,
    phase: str,
    step: object,
) -> int:
    for position, event in enumerate(events):
        if (
            isinstance(event, dict)
            and _event_type(event) == "hook_applied"
            and isinstance(event.get("payload"), dict)
            and event["payload"].get("phase") == phase
            and event["payload"].get("hook_id")
            == "intervention_worker_bridge"
            and (step is None or event.get("step") == step)
        ):
            return position
    return -1


def _next_event(
    events: list[object],
    event_type: str,
) -> dict[str, Any] | None:
    for event in events:
        if isinstance(event, dict) and _event_type(event) == event_type:
            return event
    return None


def _parsed_decision(event: dict[str, Any] | None) -> dict[str, Any] | None:
    if event is None:
        return None
    payload = event.get("payload")
    payload = payload if isinstance(payload, dict) else {}
    return {
        "step": event.get("step"),
        "kind": payload.get("kind"),
        "tool_name": (
            payload.get("tool_call", {}).get("name")
            if isinstance(payload.get("tool_call"), dict)
            else None
        ),
    }


def _event_type(event: object) -> object:
    return event.get("event_type") if isinstance(event, dict) else None


def _event_index(event: object) -> int:
    if not isinstance(event, dict):
        return -1
    value = event.get("index")
    return value if isinstance(value, int) and not isinstance(value, bool) else -1


def _positive_int(value: object, *, default: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return default


def _static_payload(value: Any) -> dict[str, Any]:
    score = None
    if value.decision is StaticDecision.PASS:
        score = 1
    elif value.decision is StaticDecision.AUTOMATIC_ZERO:
        score = 0
    return {
        "decision": value.decision.value,
        "score": score,
        "metrics": dict(value.metrics),
        "reason": value.reason,
    }


def _execution_summary(run: dict[str, Any]) -> dict[str, Any]:
    state = run.get("state") if isinstance(run.get("state"), dict) else {}
    interactions = state.get("tool_interactions")
    outputs = state.get("model_outputs")
    return {
        "steps": state.get("step"),
        "model_calls": len(outputs) if isinstance(outputs, list) else 0,
        "tool_calls": len(interactions) if isinstance(interactions, list) else 0,
        "tokens": _token_usage(run.get("trace")),
    }


def _token_usage(trace: Any) -> dict[str, int]:
    totals: dict[str, int] = {}
    if not isinstance(trace, list):
        return totals
    for event in trace:
        if not isinstance(event, dict) or event.get("event_type") not in {
            "model_output",
            "hook_model_output",
        }:
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        usage = metadata.get("usage") if isinstance(metadata.get("usage"), dict) else {}
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = usage.get(key)
            if isinstance(value, int):
                totals[key] = totals.get(key, 0) + value
    return totals


def _model_provenance(model: ModelClient) -> dict[str, Any]:
    config = getattr(model, "config", None)
    provenance = getattr(config, "provenance", None)
    if callable(provenance):
        return provenance()
    return {"type": type(model).__name__}


def _new_trial_dir(root: Path) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return root.resolve() / timestamp


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
