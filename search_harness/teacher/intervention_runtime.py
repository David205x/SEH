"""Persistent multi-phase Intervention Worker role runtime."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ._intervention import (
    InterventionRunner,
    InterventionRuntimeConfig,
    load_rollout_record,
    resolve_prefix_boundary,
)

from .contracts import (
    InterventionHypothesis,
    InterventionWorkerInput,
    InterventionWorkerResult,
    get_teacher_role,
)
from .manifest import load_teacher_manifest
from .resources import TeacherResourceConfig


class InterventionRoleRuntime:
    """Run one Worker transcript across every configured branch Hook phase."""

    def __init__(
        self,
        *,
        env_file: Path = Path(".env"),
        max_steps_per_activation: int = 8,
        teacher_judge: bool = True,
    ) -> None:
        if max_steps_per_activation < 1:
            raise ValueError(
                "Intervention Worker max steps per activation must be positive"
            )
        self.env_file = env_file
        self.max_steps_per_activation = max_steps_per_activation
        self.teacher_judge = teacher_judge

    async def run(
        self,
        *,
        template_root: Path,
        role_input: dict[str, Any],
        resource_config: TeacherResourceConfig,
    ) -> dict[str, Any]:
        """Execute one assigned multi-phase branch and return a Teacher artifact."""

        manifest = load_teacher_manifest(template_root)
        role = get_teacher_role(
            manifest.role.contract_id,
            manifest.role.version,
        )
        if role.role_id != "intervention_worker":
            raise ValueError(
                "InterventionRoleRuntime requires intervention_worker template"
            )
        if (
            manifest.output_contract.contract_id
            != role.output_contract_id
            or manifest.output_contract.version
            != role.output_contract_version
        ):
            raise ValueError(
                "Intervention Worker template output contract mismatch: "
                f"{manifest.output_contract.contract_id}@"
                f"{manifest.output_contract.version}, expected "
                f"{role.output_contract_id}@"
                f"{role.output_contract_version}"
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

        prompt_file = (
            template_root
            / "prompts"
            / "intervention_worker"
            / "templates"
            / "activation_system.md"
        )
        system_prompt_template = prompt_file.read_text(encoding="utf-8")
        guidance, budgets = _phase_runtime_plan(task.hypothesis)
        runner = InterventionRunner(
            InterventionRuntimeConfig(
                env_file=config.env_file,
                plugins_root=config.actor_plugins_root,
                student_model_role="student",
                teacher_model_role="teacher",
                actor_max_steps=config.actor_max_steps,
                worker_max_steps_per_activation=(
                    self.max_steps_per_activation
                ),
                teacher_judge=self.teacher_judge,
            )
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
        return {
            "schema_version": 1,
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
                "schema_digest": _schema_digest(output_schema),
            },
            "runtime": "persistent_intervention_branch",
            "model": branch_artifact["runtime"]["teacher_model"],
            "input": task.model_dump(mode="json"),
            "resource_config": resource_config.model_dump(mode="json"),
            "output": output.model_dump(mode="json"),
            "validated_mechanisms": {},
            "resource_artifacts": {"intervention_trial": trial},
            "tool_calls": [],
            "usage": _usage(branch_artifact),
            "transcript": list(branch_artifact["worker_trace"]),
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
            "executed" if modified_phases else "unsuitable_assignment"
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
        "context_changes": artifact["intervention_changes"],
        "phase_effects": artifact.get("phase_effects", []),
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


def _schema_digest(schema: dict[str, Any]) -> str:
    payload = json.dumps(
        schema,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
