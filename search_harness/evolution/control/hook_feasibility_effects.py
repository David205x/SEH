"""Conditional real-prefix Hook-model feasibility effect."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from search_harness.evolution.research.hook_feasibility import (
    HookFeasibilityProbeConfig,
    HookFeasibilityProbeExecutor,
    probe_total_tokens,
)
from search_harness.evolution.research.resources.base import (
    TeacherResourceConfig,
)
from search_harness.evolution.research.roles.contracts import (
    HookFeasibilityReview,
    MechanismSpec,
    TrialReview,
)
from search_harness.evolution.research.roles.runner import RoleRunner
from search_harness.framework import HookModelBackend
from search_harness.integrations.openai_compatible import (
    ProfiledHookModelBackend,
)

from .domain import EffectResult


class HookFeasibilityEffects:
    """Probe one frozen Mechanism before Compiler implementation begins."""

    def __init__(
        self,
        *,
        role_runner: RoleRunner,
        reviewer_template_root: Path,
        env_file: Path,
        probe_config: HookFeasibilityProbeConfig,
        backend: HookModelBackend | None = None,
    ) -> None:
        self.role_runner = role_runner
        self.reviewer_template_root = reviewer_template_root
        self.env_file = env_file
        self.probe_config = probe_config
        self.backend = backend

    async def verify(
        self,
        *,
        mechanism: MechanismSpec,
        distiller_artifact: dict[str, Any],
        trial_paths: list[Path],
        rollout_file: Path,
        work_dir: Path,
    ) -> EffectResult:
        """Execute Student probes, then ask one Teacher for a semantic verdict."""

        distiller_input = _required_object(distiller_artifact, "input")
        raw_reviews = distiller_input.get("trial_reviews")
        if not isinstance(raw_reviews, list) or not raw_reviews:
            raise TypeError(
                "Distiller artifact lacks Trial Reviews for Hook feasibility"
            )
        trial_reviews = [TrialReview.model_validate(item) for item in raw_reviews]
        backend = self.backend or ProfiledHookModelBackend(
            env_file=self.env_file
        )
        probe = await asyncio.to_thread(
            HookFeasibilityProbeExecutor(
                backend=backend,
                config=self.probe_config,
            ).run,
            mechanism=mechanism,
            trial_paths=trial_paths,
            trial_reviews=trial_reviews,
            rollout_file=rollout_file,
        )
        probe_path = _write_json(work_dir / "probe.json", probe)
        prior_experiments = _student_model_experiments(distiller_artifact)
        artifact = await self.role_runner.run(
            template_root=self.reviewer_template_root,
            role_id="hook_feasibility_reviewer",
            role_version=1,
            role_input={
                "mechanism": mechanism.model_dump(mode="json"),
                "probe_evidence": probe,
                "prior_model_experiments": prior_experiments,
            },
            resource_config=TeacherResourceConfig(),
        )
        output = HookFeasibilityReview.model_validate(artifact.get("output"))
        resources = artifact.get("resource_artifacts")
        if not isinstance(resources, dict):
            resources = {}
            artifact["resource_artifacts"] = resources
        resources["hook_feasibility_probe"] = probe
        role_path = _write_json(work_dir / "role.json", artifact)
        return EffectResult(
            outcome={"output": output.model_dump(mode="json")},
            artifact_refs={
                "hook_feasibility_artifact": str(role_path),
                "hook_feasibility_probe": str(probe_path),
            },
            usage={
                "total_tokens": (
                    probe_total_tokens(probe)
                    + _artifact_total_tokens(artifact)
                )
            },
        )


def _student_model_experiments(
    artifact: dict[str, Any],
) -> list[dict[str, Any]]:
    resources = artifact.get("resource_artifacts")
    if not isinstance(resources, dict):
        return []
    raw = resources.get("student_model_experiments")
    if not isinstance(raw, list):
        return []
    return [dict(item) for item in raw if isinstance(item, dict)]


def _artifact_total_tokens(artifact: dict[str, Any]) -> int:
    usage = artifact.get("usage")
    if not isinstance(usage, dict):
        return 0
    value = usage.get("total_tokens")
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        return 0
    return value


def _required_object(value: dict[str, Any], name: str) -> dict[str, Any]:
    item = value.get(name)
    if not isinstance(item, dict):
        raise TypeError(f"{name} must be an object")
    return dict(item)


def _write_json(path: Path, value: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path.resolve()
