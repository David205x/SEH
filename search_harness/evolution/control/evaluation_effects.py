"""Incumbent and Candidate evaluation effects."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from search_harness.evolution.versioning import TemplateVersionStore

from .domain import EffectResult
from .evaluation import CandidateArtifact, LocalEvaluationBackend


class EvaluationEffects:
    """Run comparable evaluations against one Experience Set."""

    def __init__(
        self,
        *,
        store: TemplateVersionStore,
        backend: LocalEvaluationBackend,
        experience_file: Path,
    ) -> None:
        self.store = store
        self.backend = backend
        self.experience_file = experience_file

    def evaluate_incumbent(
        self,
        *,
        version_id: str,
        work_dir: Path,
    ) -> EffectResult:
        """Evaluate the latest accepted Template Version."""

        versions = self.store.list_versions()
        if not versions or versions[-1].version_id != version_id:
            raise ValueError(
                f"Controller version is not latest accepted: {version_id}"
            )
        evaluation = self.backend.evaluate_accepted(
            version_id=version_id,
            experience_file=self.experience_file,
            output_dir=work_dir / "report",
        )
        return _evaluation_result(evaluation)

    def evaluate_candidate(
        self,
        *,
        candidate: CandidateArtifact,
        work_dir: Path,
    ) -> EffectResult:
        """Evaluate a staged Candidate against the same Experience Set."""

        evaluation = self.backend.evaluate_candidate(
            candidate=candidate,
            experience_file=self.experience_file,
            output_dir=work_dir / "report",
        )
        return _evaluation_result(evaluation, prefix="candidate_")


def _evaluation_result(
    evaluation: Any,
    *,
    prefix: str = "",
) -> EffectResult:
    metrics = dict(evaluation.metrics)
    tokens = metrics.get("tokens")
    total_tokens = (
        tokens.get("total_tokens", 0)
        if isinstance(tokens, dict)
        else 0
    )
    return EffectResult(
        outcome={"metrics": metrics},
        artifact_refs={
            f"{prefix}rollout_file": str(
                evaluation.rollout_file.resolve()
            ),
            f"{prefix}report_dir": str(
                evaluation.report_dir.resolve()
            ),
        },
        usage={"total_tokens": _non_negative_int(total_tokens)},
    )


def _non_negative_int(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        return 0
    return value
