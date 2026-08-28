"""Trial-level and aggregate Evidence Review effects."""

from __future__ import annotations

import asyncio
import hashlib
import json
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from search_harness.evolution.research.evidence import (
    aggregate_trial_observations,
    summarize_evidence_coverage,
)
from search_harness.evolution.research.resources.base import (
    TeacherResourceConfig,
)
from search_harness.evolution.research.roles.contracts import (
    EvidenceReview,
    InterventionHypothesis,
    TrialReview,
)
from search_harness.evolution.research.roles.runner import RoleRunner

from .domain import EffectResult


class EvidenceReviewBatchFailed(RuntimeError):
    """Expose durable diagnostics and usage for failed Trial reviews."""

    def __init__(
        self,
        message: str,
        *,
        failure_artifact: dict[str, Any],
    ) -> None:
        super().__init__(message)
        self.failure_artifact = failure_artifact


@dataclass(frozen=True)
class _ReviewedTrial:
    review: TrialReview
    path: Path
    incurred_tokens: int


class _TrialReviewFailed(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        failure_path: Path,
        incurred_tokens: int,
    ) -> None:
        super().__init__(message)
        self.failure_path = failure_path
        self.incurred_tokens = incurred_tokens


class EvidenceReviewEffects:
    """Review individual trials before judging their aggregate evidence."""

    def __init__(
        self,
        *,
        role_runner: RoleRunner,
        trial_reviewer_template_root: Path,
        evidence_reviewer_template_root: Path,
        judge_workers: int,
    ) -> None:
        if judge_workers < 1:
            raise ValueError("Trial Reviewer judge_workers must be positive")
        self.role_runner = role_runner
        self.trial_reviewer_template_root = trial_reviewer_template_root
        self.evidence_reviewer_template_root = (
            evidence_reviewer_template_root
        )
        self.judge_workers = judge_workers

    async def review(
        self,
        *,
        hypothesis: dict[str, Any],
        trial_paths: list[Path],
        persisted_trial_reviews: dict[int, Path],
        budget: dict[str, Any],
        prior_obligation: object,
        work_dir: Path,
        trial_reviews_only: bool = False,
    ) -> EffectResult:
        """Review each trial and optionally continue to aggregate review."""

        trial_artifacts = [_read_json(path) for path in trial_paths]
        validated_hypothesis = InterventionHypothesis.model_validate(hypothesis)
        aggregate = aggregate_trial_observations(
            trial_artifacts,
            trial_paths,
        )
        fingerprint = _review_fingerprint(
            hypothesis=hypothesis,
            trial_paths=trial_paths,
        )
        checkpoint_dir = (
            work_dir.parent
            / "evidence_review_checkpoints"
            / fingerprint[:24]
        )
        semaphore = asyncio.Semaphore(self.judge_workers)

        async def review_trial(
            index: int,
            trial_path: Path,
        ) -> _ReviewedTrial:
            trial_ref = trial_path.parent.name
            review_key = f"trial_review_{index:03d}_artifact"
            persisted_path = persisted_trial_reviews.get(index)
            trial_review_path = (
                persisted_path
                if persisted_path is not None
                else checkpoint_dir
                / "trial_reviews"
                / f"trial_review_{index:03d}.json"
            )
            if persisted_path is not None and not trial_review_path.is_file():
                raise FileNotFoundError(
                    f"persisted Trial Review is missing: {trial_review_path}"
                )
            if trial_review_path.is_file():
                artifact = _read_json(trial_review_path)
                stored_input = artifact.get("input")
                if (
                    not isinstance(stored_input, dict)
                    or stored_input.get("hypothesis") != hypothesis
                    or stored_input.get("trial_ref") != trial_ref
                ):
                    raise ValueError(
                        "persisted Trial Reviewer artifact does not match "
                        f"the frozen hypothesis and trial: {review_key}"
                    )
                review = TrialReview.model_validate(artifact.get("output"))
                if review.trial_ref != trial_ref:
                    raise ValueError(
                        "Trial Reviewer output reference differs from its "
                        f"assigned trial: {review.trial_ref} != {trial_ref}"
                    )
                return _ReviewedTrial(
                    review=review,
                    path=trial_review_path.resolve(),
                    incurred_tokens=0,
                )

            artifact: dict[str, Any] | None = None
            try:
                async with semaphore:
                    artifact = await self.role_runner.run(
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
                review = TrialReview.model_validate(artifact.get("output"))
                if review.trial_ref != trial_ref:
                    raise ValueError(
                        "Trial Reviewer output reference differs from its "
                        f"assigned trial: {review.trial_ref} != {trial_ref}"
                    )
                path = _write_json_atomic(trial_review_path, artifact)
                return _ReviewedTrial(
                    review=review,
                    path=path,
                    incurred_tokens=_artifact_total_tokens(artifact),
                )
            except Exception as exc:
                failure_artifact = getattr(exc, "failure_artifact", None)
                if artifact is None and isinstance(failure_artifact, dict):
                    artifact = failure_artifact
                incurred_tokens = _artifact_total_tokens(artifact)
                failure_path = _write_json_atomic(
                    checkpoint_dir
                    / "failures"
                    / f"trial_review_{index:03d}_{uuid4().hex[:8]}.json",
                    {
                        "schema_version": 1,
                        "status": "failed",
                        "stage": "review_trial",
                        "trial_ref": trial_ref,
                        "error": _error_diagnostic(exc),
                        "role_artifact": artifact,
                        "usage": {"total_tokens": incurred_tokens},
                    },
                )
                raise _TrialReviewFailed(
                    f"{trial_ref}: {type(exc).__name__}: {exc}",
                    failure_path=failure_path,
                    incurred_tokens=incurred_tokens,
                ) from exc

        raw_results = await asyncio.gather(
            *[
                review_trial(index, trial_path)
                for index, trial_path in enumerate(trial_paths, start=1)
            ],
            return_exceptions=True,
        )
        failures = [
            item for item in raw_results if isinstance(item, BaseException)
        ]
        completed = [
            item for item in raw_results if isinstance(item, _ReviewedTrial)
        ]
        incurred_tokens = sum(item.incurred_tokens for item in completed)
        incurred_tokens += sum(
            item.incurred_tokens
            for item in failures
            if isinstance(item, _TrialReviewFailed)
        )
        if failures:
            raise _evidence_review_batch_failure(
                checkpoint_dir=checkpoint_dir,
                failures=failures,
                incurred_tokens=incurred_tokens,
            )

        trial_reviews = [item.review for item in completed]
        trial_review_refs = {
            f"trial_review_{index:03d}_artifact": str(item.path)
            for index, item in enumerate(completed, start=1)
        }
        trial_review_payloads = [
            review.model_dump(mode="json") for review in trial_reviews
        ]
        if trial_reviews_only:
            return EffectResult(
                outcome={"trial_reviews": trial_review_payloads},
                artifact_refs=trial_review_refs,
                usage={"total_tokens": incurred_tokens},
            )

        coverage_summary = summarize_evidence_coverage(
            validated_hypothesis,
            trial_artifacts,
            trial_reviews,
        )
        coverage_payload = coverage_summary.model_dump(mode="json")
        coverage_path = _write_json(
            work_dir / "coverage_summary.json",
            coverage_payload,
        )

        try:
            artifact = await self.role_runner.run(
                template_root=self.evidence_reviewer_template_root,
                role_id="evidence_reviewer",
                role_version=1,
                role_input={
                    "hypothesis": hypothesis,
                    "aggregate_observations": aggregate,
                    "trial_reviews": trial_review_payloads,
                    "coverage_summary": coverage_payload,
                    "budget": budget,
                    "trial_selection_capabilities": {
                        "addressable": [
                            "unused prefix at the frozen fork_phase",
                            "prefer a previously unused Example",
                            "prefer a previously unused replicate",
                        ],
                        "not_addressable": [
                            "future Student or Hook-model outcome",
                            "semantic positive or negative predicate",
                            "sampling until a requested stochastic outcome",
                        ],
                    },
                    "prior_obligation": prior_obligation,
                },
                resource_config=TeacherResourceConfig(),
            )
        except Exception as exc:
            _add_incurred_usage(exc, incurred_tokens)
            raise
        output = EvidenceReview.model_validate(artifact.get("output"))
        incurred_tokens += _artifact_total_tokens(artifact)
        path = _write_json(work_dir / "role.json", artifact)
        return _role_result(
            output.model_dump(mode="json"),
            artifact,
            {
                "reviewer_artifact": str(path),
                "coverage_summary_artifact": str(coverage_path),
                **trial_review_refs,
            },
            coverage_summary=coverage_payload,
            trial_reviews=trial_review_payloads,
            total_tokens=incurred_tokens,
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


def _write_json_atomic(path: Path, value: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{uuid4().hex[:8]}.tmp"
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return path.resolve()


def _review_fingerprint(
    *,
    hypothesis: dict[str, Any],
    trial_paths: list[Path],
) -> str:
    payload = {
        "evidence_review_batch_schema": 1,
        "hypothesis": hypothesis,
        "trials": [
            {
                "path": str(path.resolve()),
                "digest": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for path in trial_paths
        ],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _evidence_review_batch_failure(
    *,
    checkpoint_dir: Path,
    failures: list[BaseException],
    incurred_tokens: int,
) -> EvidenceReviewBatchFailed:
    failure_items = []
    for failure in failures:
        item: dict[str, Any] = {
            "type": type(failure).__name__,
            "message": str(failure),
        }
        if isinstance(failure, _TrialReviewFailed):
            item["failure_artifact"] = str(failure.failure_path)
            item["total_tokens"] = failure.incurred_tokens
        failure_items.append(item)
    artifact = {
        "schema_version": 1,
        "status": "failed",
        "role": {"id": "trial_reviewer", "version": 1},
        "stage": "review_trials",
        "trial_review_failures": failure_items,
        "checkpoint_dir": str(checkpoint_dir.resolve()),
        "usage": {"total_tokens": incurred_tokens},
    }
    return EvidenceReviewBatchFailed(
        f"Trial Review batch failed: {len(failures)} review(s)",
        failure_artifact=artifact,
    )


def _error_diagnostic(exc: Exception) -> dict[str, Any]:
    return {
        "type": type(exc).__name__,
        "message": str(exc),
        "traceback": "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        ),
    }


def _role_result(
    output: dict[str, Any],
    artifact: dict[str, Any],
    refs: dict[str, str],
    *,
    coverage_summary: dict[str, Any],
    trial_reviews: list[dict[str, Any]],
    total_tokens: int,
) -> EffectResult:
    return EffectResult(
        outcome={
            "output": output,
            "coverage_summary": coverage_summary,
            "trial_reviews": trial_reviews,
        },
        artifact_refs=refs,
        usage={"total_tokens": _non_negative_int(total_tokens)},
    )


def _artifact_total_tokens(artifact: dict[str, Any]) -> int:
    usage = artifact.get("usage")
    return _non_negative_int(
        usage.get("total_tokens") if isinstance(usage, dict) else None
    )


def _add_incurred_usage(exc: Exception, incurred_tokens: int) -> None:
    """Include completed sub-role usage in the propagated failure artifact."""

    failure = getattr(exc, "failure_artifact", None)
    if not isinstance(failure, dict):
        return
    usage = failure.get("usage")
    usage = dict(usage) if isinstance(usage, dict) else {}
    usage["total_tokens"] = (
        _non_negative_int(usage.get("total_tokens"))
        + _non_negative_int(incurred_tokens)
    )
    failure["usage"] = usage


def _non_negative_int(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        return 0
    return value
