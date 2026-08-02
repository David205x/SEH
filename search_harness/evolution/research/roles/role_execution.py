"""Shared application support for executing one Teacher Role."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .contracts import (
    CandidateReview,
    CompilerResult,
    EvidenceReview,
    FailureDirection,
    InterventionHypothesis,
    InterventionWorkerResult,
    MechanismDistillation,
    TeacherPayload,
    TrialReview,
)
from .loader import load_teacher_agent_spec
from ..resources.base import TeacherResourceConfig, TeacherResources
from .spec import TeacherAgentSpec


@dataclass(frozen=True)
class PreparedRoleRun:
    """Validated Role inputs and assembled resources for one execution."""

    template_root: Path
    spec: TeacherAgentSpec
    resources: TeacherResources
    role_input: TeacherPayload
    rendered_input: str
    resource_config: TeacherResourceConfig


def prepare_role_run(
    *,
    template_root: Path,
    role_input: dict[str, Any],
    resource_config: TeacherResourceConfig,
    role_id: str,
    role_version: int,
) -> PreparedRoleRun:
    """Validate the Role Input and assemble its external Harness Template."""

    resources = TeacherResources.from_config(resource_config)
    spec = load_teacher_agent_spec(
        template_root,
        runtime_context=resources,
        role_id=role_id,
        role_version=role_version,
    )
    validated_input = spec.role.input_type.model_validate(role_input)
    resources.bind_role_input(validated_input)
    rendered_input = spec.prompt.render_input(
        validated_input,
        resources.model_context(spec.role.role_id),
    )
    return PreparedRoleRun(
        template_root=template_root,
        spec=spec,
        resources=resources,
        role_input=validated_input,
        rendered_input=rendered_input,
        resource_config=resource_config,
    )


def validate_role_output(
    output: TeacherPayload,
    resources: TeacherResources,
) -> None:
    """Validate resource-backed obligations of one Role Output."""

    if isinstance(output, FailureDirection):
        if resources.evaluation is None:
            raise ValueError("Failure Analyst resources are unavailable")
        resources.evaluation.validate_evidence_refs(output.evidence_refs)
    if isinstance(output, InterventionHypothesis):
        resources.validate_hypothesis_research()
    if isinstance(output, EvidenceReview):
        resources.validate_evidence_review(output)
    if isinstance(output, TrialReview):
        if resources.trials is None:
            raise ValueError("Trial Reviewer resources are unavailable")
        resources.trials.validate_trial_review(output)
    if isinstance(output, MechanismDistillation) and output.decision == "distilled":
        if output.mechanism_ref is None:
            raise ValueError("distilled result lacks mechanism_ref")
        resources.mechanisms.resolve(output.mechanism_ref)
    if isinstance(output, InterventionWorkerResult):
        raise ValueError(
            "Intervention Worker must run through "
            "InterventionRoleRunner so one transcript can span Hook phases"
        )
    if isinstance(output, CompilerResult) and output.decision == "submitted":
        if resources.compiler is None:
            raise ValueError("Compiler resources are unavailable")
        if output.candidate_ref is None:
            raise ValueError("submitted Compiler result lacks candidate_ref")
        resources.compiler.resolve(output.candidate_ref)
    if isinstance(output, CandidateReview):
        if resources.candidate_review is None:
            raise ValueError("Candidate Reviewer resources are unavailable")
        resources.candidate_review.validate_review()


def build_role_artifact(
    prepared: PreparedRoleRun,
    *,
    runtime: str,
    model: dict[str, Any],
    output: TeacherPayload,
    tool_calls: list[dict[str, Any]],
    usage: dict[str, Any],
    transcript: list[dict[str, Any]],
    runtime_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the shared persisted artifact envelope for one Role Run."""

    output_schema = prepared.spec.role.output_type.model_json_schema()
    artifact = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "template_root": str(prepared.template_root.resolve()),
        "harness_id": prepared.spec.manifest.harness_id,
        "role": {
            "id": prepared.spec.role.role_id,
            "version": prepared.spec.role.version,
        },
        "output_contract": {
            "id": prepared.spec.role.output_contract_id,
            "version": prepared.spec.role.output_contract_version,
            "schema_digest": _schema_digest(output_schema),
        },
        "runtime": runtime,
        "model": model,
        "input": prepared.role_input.model_dump(mode="json"),
        "resource_config": prepared.resource_config.model_dump(mode="json"),
        "output": output.model_dump(mode="json"),
        "validated_mechanisms": prepared.resources.mechanisms.validated_payloads(),
        "resource_artifacts": prepared.resources.artifacts(),
        "tool_calls": tool_calls,
        "usage": usage,
        "transcript": transcript,
    }
    if runtime_fields:
        overlap = set(artifact) & set(runtime_fields)
        if overlap:
            raise ValueError(
                f"runtime artifact fields overlap shared fields: {sorted(overlap)}"
            )
        artifact.update(runtime_fields)
    return artifact


def _schema_digest(schema: dict[str, Any]) -> str:
    payload = json.dumps(
        schema,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
