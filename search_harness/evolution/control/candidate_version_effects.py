"""Candidate staging, promotion, and rejection Version Store effects."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from search_harness.evolution.versioning import (
    FileEdit,
    TemplateVersionStore,
    CandidateAttemptState,
    ValidationReport,
)

from .domain import EffectResult


class CandidateVersionEffects:
    """Apply deterministic Candidate lifecycle transactions."""

    def __init__(
        self,
        *,
        store: TemplateVersionStore,
        env_file: Path,
    ) -> None:
        self.store = store
        self.env_file = env_file

    def stage(
        self,
        *,
        candidate: dict[str, Any],
        parent_version: str,
        work_dir: Path,
    ) -> EffectResult:
        """Materialize and validate one idempotent Candidate transaction."""

        candidate_digest = _required_string(candidate, "candidate_digest")
        existing = self._find_candidate_attempt(
            parent_version=parent_version,
            candidate_digest=candidate_digest,
        )
        if existing is not None and existing.status == "rejected":
            return EffectResult(
                outcome={
                    "status": "validation_failed",
                    "candidate_attempt_id": existing.candidate_attempt_id,
                    "candidate_digest": candidate_digest,
                    "validation": self._candidate_attempt_validation(
                        existing.candidate_attempt_id
                    ),
                },
            )

        attempt = (
            self.store.start_candidate_attempt(
                parent_version=parent_version,
                metadata={
                    "controller_candidate_digest": candidate_digest,
                },
            )
            if existing is None
            else self.store.resume_candidate_attempt(existing.candidate_attempt_id)
        )
        changed_files = _required_object(candidate, "changed_files")
        edits = [
            FileEdit(
                operation=("delete" if content is None else "write"),
                path=path,
                content=content,
            )
            for path, content in changed_files.items()
            if content is not None or attempt.exists(path)
        ]
        if attempt.revision == 0:
            if not edits:
                message = "Compiler submitted an empty transaction."
                attempt.reject(message)
                return EffectResult(
                    outcome={
                        "status": "validation_failed",
                        "candidate_attempt_id": attempt.candidate_attempt_id,
                        "candidate_digest": candidate_digest,
                        "validation": {
                            "passed": False,
                            "errors": [message],
                        },
                    },
                )
            attempt.apply_patch(edits)

        if attempt.digest != candidate_digest:
            raise ValueError(
                "Version Store candidate digest does not match Compiler "
                f"artifact: {attempt.digest} != {candidate_digest}"
            )
        report = attempt.validate(env_file=self.env_file)
        validation = _validation_dict(report)
        validation_path = _write_json(
            work_dir / "validation.json",
            validation,
        )
        refs = {"validation_artifact": str(validation_path)}
        if not report.passed:
            attempt.reject(
                "Controller validation failed: "
                + "; ".join(report.errors)
            )
            return EffectResult(
                outcome={
                    "status": "validation_failed",
                    "candidate_attempt_id": attempt.candidate_attempt_id,
                    "candidate_digest": attempt.digest,
                    "validation": validation,
                },
                artifact_refs=refs,
            )
        return EffectResult(
            outcome={
                "status": "valid",
                "candidate_attempt_id": attempt.candidate_attempt_id,
                "candidate_digest": attempt.digest,
                "validation": validation,
            },
            artifact_refs=refs,
        )

    def promote(
        self,
        *,
        candidate_attempt_id: str,
        implementation_summary: str,
        candidate_metrics: dict[str, Any],
        candidate_review: dict[str, Any],
        promotion_gate: dict[str, Any],
        work_dir: Path,
    ) -> EffectResult:
        """Accept a pending Candidate exactly once."""

        existing = self.promotion_result_if_completed(
            candidate_attempt_id=candidate_attempt_id,
            work_dir=work_dir,
        )
        if existing is not None:
            return existing
        accepted = self.store.resume_candidate_attempt(candidate_attempt_id).accept(
            summary=implementation_summary,
            evaluation={
                "metrics": candidate_metrics,
                "candidate_review": candidate_review,
                "promotion_gate": promotion_gate,
            },
            env_file=self.env_file,
        )
        return _promotion_result(
            version_id=accepted.version_id,
            candidate_attempt_id=candidate_attempt_id,
            candidate_digest=accepted.digest,
            work_dir=work_dir,
        )

    def promotion_result_if_completed(
        self,
        *,
        candidate_attempt_id: str,
        work_dir: Path,
    ) -> EffectResult | None:
        """Return the durable receipt for an accepted Candidate Attempt."""

        accepted = next(
            (
                version
                for version in self.store.list_versions()
                if version.candidate_attempt_id == candidate_attempt_id
            ),
            None,
        )
        if accepted is None:
            return None
        return _promotion_result(
            version_id=accepted.version_id,
            candidate_attempt_id=candidate_attempt_id,
            candidate_digest=accepted.digest,
            work_dir=work_dir,
        )

    def reject(
        self,
        *,
        candidate_attempt_id: str,
        conformance_summary: dict[str, Any] | None,
        candidate_review: dict[str, Any] | None,
        promotion_gate: dict[str, Any] | None,
        candidate_metrics: dict[str, Any] | None,
        work_dir: Path,
    ) -> EffectResult:
        """Reject a pending Candidate and preserve its review evidence."""

        existing = self.rejection_result_if_completed(
            candidate_attempt_id=candidate_attempt_id,
            work_dir=work_dir,
        )
        if existing is not None:
            return existing
        conformance_only = (
            conformance_summary is not None and candidate_review is None
        )
        if conformance_only:
            feedback = conformance_summary.get("compiler_feedback")
            reasons = (
                [str(value) for value in feedback if str(value).strip()]
                if isinstance(feedback, list)
                else []
            )
            reason = (
                "; ".join(reasons)
                if reasons
                else "Mechanism conformance replay failed."
            )
            evaluation = {"mechanism_conformance": conformance_summary}
        else:
            if candidate_review is None:
                raise TypeError("candidate_review must be an object")
            if promotion_gate is None:
                raise TypeError("promotion_gate must be an object")
            if candidate_metrics is None:
                raise TypeError("candidate_metrics must be an object")
            reasons = promotion_gate.get("reasons")
            reason = (
                "; ".join(str(value) for value in reasons)
                if isinstance(reasons, list) and reasons
                else _required_string(candidate_review, "reason")
            )
            evaluation = {
                "metrics": candidate_metrics,
                "candidate_review": candidate_review,
                "promotion_gate": promotion_gate,
            }
        self.store.resume_candidate_attempt(candidate_attempt_id).reject(
            reason,
            evaluation=evaluation,
        )
        return _rejection_result(
            candidate_attempt_id=candidate_attempt_id,
            work_dir=work_dir,
        )

    def rejection_result_if_completed(
        self,
        *,
        candidate_attempt_id: str,
        work_dir: Path,
    ) -> EffectResult | None:
        """Return the durable receipt for a rejected Candidate Attempt."""

        summary = next(
            (
                item
                for item in self.store.list_candidate_attempts()
                if item.candidate_attempt_id == candidate_attempt_id
            ),
            None,
        )
        if summary is None:
            raise KeyError(f"unknown Candidate Attempt: {candidate_attempt_id}")
        if summary.status == "accepted":
            raise RuntimeError(
                f"cannot reject accepted Candidate Attempt: {candidate_attempt_id}"
            )
        if summary.status == "pending":
            return None
        return _rejection_result(
            candidate_attempt_id=candidate_attempt_id,
            work_dir=work_dir,
        )

    def _find_candidate_attempt(
        self,
        *,
        parent_version: str,
        candidate_digest: str,
    ) -> CandidateAttemptState | None:
        matches: list[CandidateAttemptState] = []
        for summary in self.store.list_candidate_attempts():
            events = self.store.get_candidate_attempt_events(
                summary.candidate_attempt_id
            )
            first = events[0]
            metadata = first.payload.get("metadata")
            if (
                first.payload.get("parent_version") == parent_version
                and isinstance(metadata, dict)
                and metadata.get("controller_candidate_digest")
                == candidate_digest
            ):
                matches.append(summary)
        if not matches:
            return None
        pending = [item for item in matches if item.status == "pending"]
        return pending[-1] if pending else matches[-1]

    def _candidate_attempt_validation(
        self,
        candidate_attempt_id: str,
    ) -> dict[str, Any]:
        for event in reversed(
            self.store.get_candidate_attempt_events(candidate_attempt_id)
        ):
            if event.event_type == "validation_completed":
                return dict(event.payload)
        return {
            "passed": False,
            "errors": ["Candidate Attempt was rejected before validation."],
        }


def _validation_dict(report: ValidationReport) -> dict[str, Any]:
    value = asdict(report)
    for key in (
        "added_paths",
        "modified_paths",
        "removed_paths",
        "errors",
    ):
        value[key] = list(value[key])
    return value


def _promotion_result(
    *,
    version_id: str,
    candidate_attempt_id: str,
    candidate_digest: str,
    work_dir: Path,
) -> EffectResult:
    receipt = {
        "version_id": version_id,
        "candidate_attempt_id": candidate_attempt_id,
        "candidate_digest": candidate_digest,
    }
    path = _write_json(work_dir / "promotion.json", receipt)
    return EffectResult(
        outcome=receipt,
        artifact_refs={"promotion_artifact": str(path)},
    )


def _rejection_result(
    *,
    candidate_attempt_id: str,
    work_dir: Path,
) -> EffectResult:
    receipt = {"status": "rejected", "candidate_attempt_id": candidate_attempt_id}
    path = _write_json(work_dir / "rejection.json", receipt)
    return EffectResult(
        outcome=receipt,
        artifact_refs={"rejection_artifact": str(path)},
    )


def _required_string(value: dict[str, Any], name: str) -> str:
    item = value.get(name)
    if not isinstance(item, str) or not item.strip():
        raise TypeError(f"{name} must be a non-empty string")
    return item


def _required_object(
    value: dict[str, Any],
    name: str,
) -> dict[str, Any]:
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
