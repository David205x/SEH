"""Trial-level and aggregate Evidence Review effects."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from search_harness.evolution.research.evidence import (
    aggregate_trial_observations,
)
from search_harness.evolution.research.resources.base import (
    TeacherResourceConfig,
)
from search_harness.evolution.research.roles.contracts import (
    EvidenceReview,
    TrialReview,
)
from search_harness.evolution.research.roles.runner import RoleRunner

from .domain import EffectResult


class EvidenceReviewEffects:
    """Review individual trials before judging their aggregate evidence."""

    def __init__(
        self,
        *,
        role_runner: RoleRunner,
        trial_reviewer_template_root: Path,
        evidence_reviewer_template_root: Path,
    ) -> None:
        self.role_runner = role_runner
        self.trial_reviewer_template_root = trial_reviewer_template_root
        self.evidence_reviewer_template_root = (
            evidence_reviewer_template_root
        )

    async def review(
        self,
        *,
        hypothesis: dict[str, Any],
        trial_paths: list[Path],
        persisted_trial_reviews: dict[int, Path],
        budget: dict[str, Any],
        prior_obligation: object,
        work_dir: Path,
    ) -> EffectResult:
        """Review each trial, reuse valid artifacts, then review the aggregate."""

        trial_artifacts = [_read_json(path) for path in trial_paths]
        aggregate = aggregate_trial_observations(
            trial_artifacts,
            trial_paths,
        )
        trial_reviews: list[TrialReview] = []
        trial_review_refs: dict[str, str] = {}
        for index, trial_path in enumerate(trial_paths, start=1):
            trial_ref = trial_path.parent.name
            review_key = f"trial_review_{index:03d}_artifact"
            trial_review_path = persisted_trial_reviews.get(index)
            if trial_review_path is not None:
                trial_review_artifact = _read_json(trial_review_path)
                stored_input = trial_review_artifact.get("input")
                if (
                    not isinstance(stored_input, dict)
                    or stored_input.get("hypothesis") != hypothesis
                    or stored_input.get("trial_ref") != trial_ref
                ):
                    raise ValueError(
                        "persisted Trial Reviewer artifact does not match "
                        f"the frozen hypothesis and trial: {review_key}"
                    )
            else:
                trial_review_artifact = await self.role_runner.run(
                    template_root=self.trial_reviewer_template_root,
                    role_id="trial_reviewer",
                    role_version=1,
                    role_input={
                        "hypothesis": hypothesis,
                        "trial_ref": trial_ref,
                    },
                    resource_config=TeacherResourceConfig(
                        trial_files=[trial_path]
                    ),
                )
                trial_review_path = _write_json(
                    work_dir
                    / "trial_reviews"
                    / f"trial_review_{index:03d}.json",
                    trial_review_artifact,
                )
            trial_review = TrialReview.model_validate(
                trial_review_artifact.get("output")
            )
            trial_reviews.append(trial_review)
            if trial_review.trial_ref != trial_ref:
                raise ValueError(
                    "Trial Reviewer output reference differs from its "
                    f"assigned trial: {trial_review.trial_ref} != {trial_ref}"
                )
            trial_review_refs[review_key] = str(trial_review_path)

        artifact = await self.role_runner.run(
            template_root=self.evidence_reviewer_template_root,
            role_id="evidence_reviewer",
            role_version=1,
            role_input={
                "hypothesis": hypothesis,
                "aggregate_observations": aggregate,
                "trial_reviews": [
                    review.model_dump(mode="json")
                    for review in trial_reviews
                ],
                "budget": budget,
                "prior_obligation": prior_obligation,
            },
            resource_config=TeacherResourceConfig(),
        )
        output = EvidenceReview.model_validate(artifact.get("output"))
        path = _write_json(work_dir / "role.json", artifact)
        return _role_result(
            output.model_dump(mode="json"),
            artifact,
            {
                "reviewer_artifact": str(path),
                **trial_review_refs,
            },
        )


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"JSON artifact must be an object: {path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path.resolve()


def _role_result(
    output: dict[str, Any],
    artifact: dict[str, Any],
    refs: dict[str, str],
) -> EffectResult:
    usage = artifact.get("usage")
    total_tokens = (
        usage.get("total_tokens", 0)
        if isinstance(usage, dict)
        else 0
    )
    return EffectResult(
        outcome={"output": output},
        artifact_refs=refs,
        usage={"total_tokens": _non_negative_int(total_tokens)},
    )


def _non_negative_int(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        return 0
    return value
