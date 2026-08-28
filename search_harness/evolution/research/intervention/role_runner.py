"""Persistent multi-phase Intervention Worker Role Runner."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from search_harness._internal import read_runtime_config, teacher_role_budget
from search_harness.integrations.openai_compatible import OpenAICompatibleConfig

from .prefix import load_rollout_record, resolve_prefix_boundary
from .runtime import InterventionRunner, InterventionRuntimeConfig
from ..roles.contracts import (
    InterventionHypothesis,
    InterventionWorkerInput,
    InterventionWorkerResult,
)
from ..roles.loader import load_teacher_agent_spec
from ..roles.provenance import (
    base_prompt_digest,
    content_digest,
    input_view_digest,
    teacher_role_scope,
)
from ..resources.base import TeacherResourceConfig


class InterventionRoleRunner:
    """Run one Worker transcript across every configured branch Hook phase."""

    def __init__(
        self,
        *,
        env_file: Path = Path(".env"),
        max_steps_per_activation: int = 8,
        teacher_judge: bool = True,
        extended_worker_tools: bool = False,
    ) -> None:
        if max_steps_per_activation < 1:
            raise ValueError(
                "Intervention Worker max steps per activation must be positive"
            )
        self.env_file = env_file
        self.max_steps_per_activation = max_steps_per_activation
        self.teacher_judge = teacher_judge
        self.extended_worker_tools = extended_worker_tools

    async def run(
        self,
        *,
        template_root: Path,
        role_input: dict[str, Any],
        resource_config: TeacherResourceConfig,
        role_id: str = "intervention_worker",
        role_version: int = 1,
    ) -> dict[str, Any]:
        """Execute one assigned multi-phase branch and return a Teacher artifact."""

        if role_id != "intervention_worker" or role_version != 1:
            raise ValueError(
                "InterventionRoleRunner only supports intervention_worker@1"
            )

        spec = load_teacher_agent_spec(
            template_root,
            runtime_context=None,
            role_id=role_id,
            role_version=role_version,
        )
        manifest = spec.manifest
        role = spec.role
        if role.role_id != "intervention_worker":
            raise ValueError(
                "InterventionRoleRunner requires intervention_worker template"
            )
        task = InterventionWorkerInput.model_validate(role_input)
        config = resource_config.intervention
        if config is None:
            raise ValueError(
                "Intervention Worker requires intervention resources"
            )
        record = load_rollout_record(
            config.rollout_file,
            task.example_id,
            task.replicate_id,
        )
        boundary = resolve_prefix_boundary(record, task.prefix_id)
        if boundary["phase"] != task.hypothesis.fork_phase:
            raise ValueError(
                "selected prefix phase differs from hypothesis fork_phase: "
                f"{boundary['phase']} != {task.hypothesis.fork_phase}"
            )

        system_prompt_template = spec.prompt.instructions
        guidance, budgets = _phase_runtime_plan(task.hypothesis)
        model_config = OpenAICompatibleConfig.from_env(
            env_file=config.env_file,
            prefix="TEACHER",
        )
        role_budget = teacher_role_budget(
            read_runtime_config(env_file=config.env_file),
            role_id,
            default_max_tokens=model_config.max_tokens,
            default_max_turns=self.max_steps_per_activation,
            default_thinking_mode=model_config.configured_thinking_mode,
        )
        runner = InterventionRunner(
            InterventionRuntimeConfig(
                env_file=config.env_file,
                template_root=config.student_template_root,
                student_model_role="student",
                teacher_model_role="teacher",
                student_max_steps=config.student_max_steps,
                worker_max_steps_per_activation=role_budget.max_turns,
                teacher_judge=self.teacher_judge,
                extended_worker_tools=self.extended_worker_tools,
            ),
            teacher_config=replace(
                model_config,
                max_tokens=role_budget.max_tokens,
            ).with_configured_thinking_mode(role_budget.thinking_mode),
        )
        branch_artifact = await asyncio.to_thread(
            runner.run,
            rollout_file=config.rollout_file,
            example_id=task.example_id,
            replicate_id=task.replicate_id,
            fork_step=int(boundary["step"]),
            fork_phase=str(boundary["phase"]),
            intent=_worker_intent(task),
            hook_guidance=guidance,
            activation_budgets=budgets,
            system_prompt_template=system_prompt_template,
            persist=False,
        )
        output = _worker_result(task.hypothesis, branch_artifact)
        trial = _trial_artifact(task, branch_artifact)
        output_schema = role.output_type.model_json_schema()
        runtime = branch_artifact.get("runtime")
        runtime = runtime if isinstance(runtime, dict) else {}
        model = runtime.get("teacher_model")
        if not isinstance(model, dict):
            raise TypeError(
                "Intervention Worker artifact lacks Teacher model provenance"
            )
        teacher_role_scope(
            role_id=role.role_id,
            role_contract_version=role.version,
            model=model,
        )
        return {
            "schema_version": 2,
            "created_at": datetime.now(UTC).isoformat(),
            "template_root": str(template_root.resolve()),
            "harness_id": manifest.harness_id,
            "role": {
                "id": role.role_id,
                "version": role.version,
            },
            "output_contract": {
                "id": role.output_contract_id,
                "version": role.output_contract_version,
                "schema_digest": content_digest(output_schema),
            },
            "runtime": "persistent_intervention_branch",
            "role_budget": {
                "max_tokens": role_budget.max_tokens,
                "max_turns": role_budget.max_turns,
            },
            "model": model,
            "base_prompt_digest": base_prompt_digest(spec.prompt),
            "input_view_digest": input_view_digest(
                _worker_model_inputs(branch_artifact)
            ),
            "input": task.model_dump(mode="json"),
            "resource_config": resource_config.model_dump(mode="json"),
            "output": output.model_dump(mode="json"),
            "validated_mechanisms": {},
            "resource_artifacts": {"intervention_trial": trial},
            "tool_calls": list(branch_artifact.get("worker_tool_calls", [])),
            "usage": _usage(branch_artifact),
            "transcript": list(branch_artifact.get("worker_transcript", [])),
        }


def _phase_runtime_plan(
    hypothesis: InterventionHypothesis,
) -> tuple[dict[str, str], dict[str, int]]:
    guidance: dict[str, str] = {}
    budgets: dict[str, int] = {}
    for directive in hypothesis.phase_plan:
        guidance[directive.phase] = (
            f"Observable condition: {directive.activation_condition}\n"
            f"Instruction when satisfied: {directive.instruction}\n"
            f"Expected immediate effect: {directive.expected_effect}"
        )
        budgets[directive.phase] = directive.max_activations
    return guidance, budgets


def _worker_intent(task: InterventionWorkerInput) -> str:
    payload = {
        "trial_objective": task.trial_objective,
        "applicability": task.hypothesis.applicability,
        "evaluation": task.hypothesis.evaluation.model_dump(mode="json"),
        "prohibited_content": task.prohibited_content,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _worker_result(
    hypothesis: InterventionHypothesis,
    artifact: dict[str, Any],
) -> InterventionWorkerResult:
    modified_phases = list(
        dict.fromkeys(
            str(change.get("phase"))
            for change in artifact.get("intervention_changes", [])
            if isinstance(change, dict)
            and isinstance(change.get("action"), dict)
            and change["action"].get("kind")
            != "continue_without_change"
        )
    )
    activation_counts = artifact.get("activation_counts")
    activation_counts = (
        activation_counts if isinstance(activation_counts, dict) else {}
    )
    planned_phases = [directive.phase for directive in hypothesis.phase_plan]
    activated_phases = [
        phase
        for phase in planned_phases
        if _integer(activation_counts.get(phase)) > 0
    ]
    unmet = [
        phase for phase in planned_phases if phase not in activated_phases
    ]
    return InterventionWorkerResult(
        result_kind=(
            "executed" if activated_phases else "unsuitable_assignment"
        ),
        activated_phases=activated_phases,
        modified_phases=modified_phases,
        unmet_phases=unmet,
    )


def _trial_artifact(
    task: InterventionWorkerInput,
    artifact: dict[str, Any],
) -> dict[str, Any]:
    return {
        "source": artifact["source"],
        "intent": task.trial_objective,
        "phase_plan": [
            directive.model_dump(mode="json")
            for directive in task.hypothesis.phase_plan
        ],
        "activation_budgets": artifact["activation_budgets"],
        "activation_counts": artifact["activation_counts"],
        "worker_tool_protocol": artifact.get("runtime", {}).get(
            "worker_tool_protocol",
            "native",
        ),
        "context_changes": artifact["intervention_changes"],
        "phase_effects": artifact.get("phase_effects", []),
        "trial_state": artifact.get("trial_state", {}),
        "branch_run": artifact["branch_run"],
        "comparison": artifact["comparison"],
        "worker_trace": artifact["worker_trace"],
    }


def _usage(artifact: dict[str, Any]) -> dict[str, Any]:
    calls: list[dict[str, int]] = []
    for event in artifact.get("worker_trace", []):
        if not isinstance(event, dict):
            continue
        metadata = event.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        usage = metadata.get("usage")
        if isinstance(usage, dict):
            calls.append(_usage_call(usage))
    branch = artifact.get("comparison", {}).get("branch", {})
    execution = branch.get("execution") if isinstance(branch, dict) else {}
    tokens = execution.get("tokens") if isinstance(execution, dict) else {}
    if isinstance(tokens, dict) and tokens:
        calls.append(_usage_call(tokens))
    return {
        "requests": len(calls),
        "input_tokens": sum(item["input_tokens"] for item in calls),
        "output_tokens": sum(item["output_tokens"] for item in calls),
        "total_tokens": sum(item["total_tokens"] for item in calls),
        "calls": calls,
    }


def _usage_call(value: dict[str, Any]) -> dict[str, int]:
    input_tokens = _integer(
        value.get("prompt_tokens", value.get("input_tokens", 0))
    )
    output_tokens = _integer(
        value.get("completion_tokens", value.get("output_tokens", 0))
    )
    total_tokens = _integer(value.get("total_tokens", 0))
    if total_tokens == 0:
        total_tokens = input_tokens + output_tokens
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def _integer(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _worker_model_inputs(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    trace = artifact.get("worker_trace")
    if not isinstance(trace, list):
        raise TypeError("Intervention Worker trace must be an array")
    views: list[dict[str, Any]] = []
    for event in trace:
        if not isinstance(event, dict):
            continue
        if event.get("event_type") != "worker_model_output":
            continue
        model_input = event.get("model_input")
        if not isinstance(model_input, dict):
            raise TypeError(
                "Intervention Worker model output lacks model_input"
            )
        views.append(model_input)
    if not views:
        raise ValueError(
            "Intervention Worker artifact has no model-visible input"
        )
    return views
