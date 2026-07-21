"""单候选、可恢复的 Harness Evolution Runner。"""

from __future__ import annotations

import json
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from search_harness.adapter.critic import CriticResult
from search_harness.adapter.intervention import InterventionCoordinatorResult
from search_harness.datasets import DatasetExample
from search_harness.versioning import HarnessVersionStore

from .experience import file_digest, materialize_experience_set
from .journal import EvolutionEvent, EvolutionJournal
from .progress import (
    EvolutionProgressEvent,
    EvolutionProgressReporter,
    LoggingProgressReporter,
)
from .types import (
    CandidateArtifact,
    CriticArtifact,
    EvaluationArtifact,
    EvolutionBackend,
    EvolutionOutcome,
    InterventionArtifact,
    RunStatus,
)


@dataclass(frozen=True)
class EvolutionConfig:
    """一次 Evolution run 内保持不变的调度配置。"""

    max_iterations: int = 1
    experience_limit: int = 20
    failure_memory_limit: int = 5
    compiler_revision_limit: int = 2
    intervention_continuation_limit: int = 2

    def __post_init__(self) -> None:
        if self.max_iterations < 1:
            raise ValueError("max_iterations must be positive")
        if self.experience_limit < 1:
            raise ValueError("experience_limit must be positive")
        if self.failure_memory_limit < 0:
            raise ValueError("failure_memory_limit must not be negative")
        if self.compiler_revision_limit < 0:
            raise ValueError("compiler_revision_limit must not be negative")
        if self.intervention_continuation_limit < 0:
            raise ValueError("intervention_continuation_limit must not be negative")


class EvolutionRunner:
    """协调固定经验集、Adapter 角色与 Version Store 事务。"""

    def __init__(
        self,
        *,
        run_dir: Path,
        store: HarnessVersionStore,
        backend: EvolutionBackend,
        config: EvolutionConfig,
        metadata: dict[str, Any] | None = None,
        validation_env_file: Path | None = None,
        progress_reporter: EvolutionProgressReporter | None = None,
    ) -> None:
        self.run_dir = run_dir.resolve()
        self.store = store
        self.backend = backend
        self.config = config
        self.metadata = dict(metadata or {})
        self.validation_env_file = validation_env_file
        self.progress = progress_reporter or LoggingProgressReporter()
        self.journal = EvolutionJournal(self.run_dir / "events.jsonl")
        self.run_file = self.run_dir / "run.json"
        self.experience_file = self.run_dir / "experience_set.jsonl"

    def initialize(self, examples: Iterable[DatasetExample]) -> None:
        """创建新 run，并一次性冻结 Experience Set。"""

        if self.run_file.exists() or self.journal.events():
            raise FileExistsError(f"evolution run is already initialized: {self.run_dir}")
        versions = self.store.list_versions()
        if not versions:
            raise RuntimeError(f"Harness Version Store is not initialized: {self.store.root}")
        self.run_dir.mkdir(parents=True, exist_ok=True)
        selected, digest = materialize_experience_set(
            examples, self.experience_file, limit=self.config.experience_limit
        )
        payload = {
            "schema_version": 1,
            "checkpoint_store": str(self.store.root),
            "checkpoint_store_id": self.store.checkpoint_store_id,
            "initial_version": versions[-1].version_id,
            "config": {
                "max_iterations": self.config.max_iterations,
                "experience_limit": self.config.experience_limit,
                "failure_memory_limit": self.config.failure_memory_limit,
                "compiler_revision_limit": self.config.compiler_revision_limit,
                "intervention_continuation_limit": (
                    self.config.intervention_continuation_limit
                ),
            },
            "experience_set": {
                "path": str(self.experience_file),
                "count": len(selected),
                "digest": digest,
            },
            "metadata": self.metadata,
        }
        self.run_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self.journal.append(
            "run_started",
            {
                "initial_version": versions[-1].version_id,
                "experience_digest": digest,
                "experience_count": len(selected),
            },
        )

    def run(self) -> EvolutionOutcome:
        """执行或从最近一个已提交阶段继续 Evolution run。"""

        self._validate_run_identity()
        events = self.journal.events()
        self._report(
            "run_started",
            "Resuming evolution run" if len(events) > 1 else "Starting evolution run",
            details={
                "run_dir": self.run_dir,
                "experience_examples": self.config.experience_limit,
                "latest_version": self.store.list_versions()[-1].version_id,
            },
        )
        self._reconcile_version_store_decisions()
        completed = self._terminal_outcome()
        if completed is not None:
            self._report_outcome(completed, reused=True)
            return completed
        try:
            return self._run_iterations()
        except Exception as exc:
            self.journal.append(
                "run_failed",
                {"error_type": type(exc).__name__, "message": str(exc)},
            )
            self._report(
                "run_failed",
                "Evolution run failed",
                details={"error": f"{type(exc).__name__}: {exc}"},
            )
            raise

    def _run_iterations(self) -> EvolutionOutcome:
        decisions = self._decision_events()
        for iteration_number in range(len(decisions) + 1, self.config.max_iterations + 1):
            parent_version = self.store.list_versions()[-1].version_id
            paths = self._iteration_paths(iteration_number)
            paths.mkdir(parents=True, exist_ok=True)
            if self.journal.find("iteration_started", iteration_number) is None:
                self.journal.append(
                    "iteration_started",
                    {"parent_version": parent_version},
                    iteration=iteration_number,
                )
            self._report(
                "iteration_started",
                f"Using parent {parent_version}",
                iteration=iteration_number,
            )
            parent_evaluation = self._ensure_incumbent_evaluation(
                iteration_number, parent_version, paths
            )
            failure = self._ensure_failure_analysis(
                iteration_number, parent_version, parent_evaluation, paths
            )
            if not failure.result.problem_directions:
                return self._finish(
                    "no_direction",
                    "Critic returned no prioritized problem direction",
                )
            intervention = self._ensure_direction_intervention(
                iteration_number, parent_version, parent_evaluation, failure, paths
            )
            continuation = 0
            while (
                intervention.result.verdict == "inconclusive"
                and continuation < self.config.intervention_continuation_limit
            ):
                continuation += 1
                intervention = self._ensure_intervention_continuation(
                    iteration_number,
                    parent_version,
                    parent_evaluation,
                    failure,
                    intervention,
                    paths,
                    continuation=continuation,
                )
            if intervention.result.verdict != "supported":
                return self._finish(
                    "no_supported_strategy",
                    "Coordinator did not validate a strategy for the Critic direction: "
                    f"{intervention.result.verdict}",
                )
            revision = 0
            while True:
                candidate = self._ensure_candidate(
                    iteration_number,
                    parent_version,
                    intervention,
                    paths,
                    revision=revision,
                )
                if candidate.clarification is None:
                    break
                exhausted = revision >= self.config.compiler_revision_limit
                self._record_compiler_clarification(
                    iteration_number,
                    candidate,
                    revision=revision,
                    final=exhausted,
                )
                if exhausted:
                    return self._finish(
                        "needs_clarification", candidate.clarification
                    )
                revision += 1
                intervention = self._ensure_intervention_revision(
                    iteration_number,
                    parent_version,
                    parent_evaluation,
                    failure,
                    intervention,
                    candidate.clarification,
                    paths,
                    revision=revision,
                )
                if intervention.result.verdict != "supported":
                    return self._finish(
                        "no_supported_strategy",
                        "Coordinator could not satisfy Compiler clarification: "
                        f"{intervention.result.verdict}",
                    )
            if not candidate.validation_passed:
                validation_errors = _validation_errors(candidate.validation)
                reason = "Candidate failed deterministic validation"
                if validation_errors:
                    reason = f"{reason}: {'; '.join(validation_errors)}"
                self._reject_candidate(
                    iteration_number,
                    candidate,
                    reason,
                    None,
                )
                continue
            if self._is_rejected_duplicate(candidate.candidate_digest, iteration_number):
                self._reject_candidate(
                    iteration_number,
                    candidate,
                    "Candidate digest repeats an earlier rejected attempt",
                    None,
                )
                continue
            candidate_evaluation = self._ensure_candidate_evaluation(
                iteration_number, candidate, paths
            )
            review = self._ensure_candidate_review(
                iteration_number,
                candidate,
                candidate_evaluation,
                parent_evaluation,
                paths,
            )
            assert review.result.review is not None
            if review.result.review.decision == "accept":
                self._accept_candidate(
                    iteration_number, candidate, candidate_evaluation, review
                )
            else:
                self._reject_candidate(
                    iteration_number,
                    candidate,
                    review.result.review.reason,
                    candidate_evaluation,
                    review=review,
                )
        return self._finish("completed", "maximum iteration count reached")

    def _ensure_incumbent_evaluation(
        self, iteration: int, version_id: str, paths: Path
    ) -> EvaluationArtifact:
        reused = self._stored_evaluation(version_id)
        if reused is not None:
            self._report_reused(
                iteration, "incumbent_evaluation", "Reusing stored incumbent evaluation"
            )
            return reused
        event = self.journal.find("incumbent_evaluated", iteration)
        if event is not None:
            self._report_reused(
                iteration, "incumbent_evaluation", "Reusing incumbent evaluation"
            )
            return _evaluation_from_payload(event.payload)
        started = self._report_stage_started(
            iteration,
            "incumbent_evaluation",
            f"Evaluating incumbent {version_id}",
        )
        artifact = self.backend.evaluate_accepted(
            version_id=version_id,
            experience_file=self.experience_file,
            output_dir=paths / "incumbent_report",
        )
        self.journal.append(
            "incumbent_evaluated",
            {"version_id": version_id, **_evaluation_payload(artifact)},
            iteration=iteration,
        )
        self._report_stage_completed(
            iteration,
            "incumbent_evaluation",
            "Incumbent evaluation completed",
            started,
            details={
                "accuracy": _accuracy(artifact.metrics),
                "report": artifact.report_dir,
            },
        )
        return artifact

    def _ensure_failure_analysis(
        self,
        iteration: int,
        version_id: str,
        evaluation: EvaluationArtifact,
        paths: Path,
    ) -> CriticArtifact:
        event = self.journal.find("failure_critic_completed", iteration)
        if event is not None:
            try:
                artifact = _critic_from_payload(event.payload)
            except (TypeError, ValueError) as exc:
                self.journal.append(
                    "failure_critic_invalidated",
                    {
                        "source_sequence": event.sequence,
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                    iteration=iteration,
                )
                self._report(
                    "artifact_invalidated",
                    "Stored failure-analysis Critic result violates the current schema; "
                    "rerunning Critic",
                    iteration=iteration,
                    stage="failure_critic",
                    details={"error": f"{type(exc).__name__}: {exc}"},
                )
            else:
                self._report_reused(
                    iteration, "failure_critic", "Reusing failure-analysis Critic result"
                )
                return artifact
        started = self._report_stage_started(
            iteration, "failure_critic", "Running failure-analysis Critic"
        )
        artifact = self.backend.analyze_failures(
            version_id=version_id,
            evaluation=evaluation,
            failed_attempts=self._failed_attempt_memory(),
            output_file=paths / "failure_critic.json",
        )
        if artifact.result.review is not None:
            raise ValueError("failure-analysis Critic result must not contain review")
        self.journal.append(
            "failure_critic_completed",
            _critic_payload(artifact),
            iteration=iteration,
        )
        self._report_stage_completed(
            iteration,
            "failure_critic",
            "Failure-analysis Critic completed",
            started,
            details={
                "problem_directions": len(artifact.result.problem_directions),
                "evidence_requests": len(artifact.result.evidence_requests),
                "log": artifact.log_file,
            },
        )
        return artifact

    def _ensure_direction_intervention(
        self,
        iteration: int,
        version_id: str,
        evaluation: EvaluationArtifact,
        critic: CriticArtifact,
        paths: Path,
    ) -> InterventionArtifact:
        event = self.journal.find("direction_intervention_completed", iteration)
        if event is not None:
            self._report_reused(
                iteration,
                "direction_intervention",
                "Reusing Coordinator intervention evidence",
            )
            return _intervention_from_payload(event.payload)
        started = self._report_stage_started(
            iteration,
            "direction_intervention",
            "Validating Critic problem direction with Intervention",
        )
        artifact = self.backend.validate_direction(
            version_id=version_id,
            evaluation=evaluation,
            critic=critic,
            output_dir=paths / "intervention",
        )
        self.journal.append(
            "direction_intervention_completed",
            _intervention_payload(artifact),
            iteration=iteration,
        )
        self._report_stage_completed(
            iteration,
            "direction_intervention",
            "Coordinator intervention completed",
            started,
            details={
                "verdict": artifact.result.verdict,
                "selected_trial": artifact.result.selected_trial_id,
                "log": artifact.log_file,
            },
        )
        return artifact

    def _ensure_intervention_continuation(
        self,
        iteration: int,
        version_id: str,
        evaluation: EvaluationArtifact,
        critic: CriticArtifact,
        previous: InterventionArtifact,
        paths: Path,
        *,
        continuation: int,
    ) -> InterventionArtifact:
        """Continue an inconclusive Coordinator result with a new trial budget."""

        event = self._find_revision_event(
            "direction_intervention_continued", iteration, continuation
        )
        if event is not None:
            self._report_reused(
                iteration,
                "direction_intervention_continuation",
                f"Reusing Coordinator continuation {continuation}",
            )
            return _intervention_from_payload(event.payload)
        started = self._report_stage_started(
            iteration,
            "direction_intervention_continuation",
            f"Continuing inconclusive intervention (pass {continuation})",
        )
        artifact = self.backend.continue_direction(
            version_id=version_id,
            evaluation=evaluation,
            critic=critic,
            previous_intervention=previous,
            output_dir=paths / f"intervention_continuation_{continuation:02d}",
        )
        self.journal.append(
            "direction_intervention_continued",
            {
                "revision": continuation,
                "previous_verdict": previous.result.verdict,
                **_intervention_payload(artifact),
            },
            iteration=iteration,
        )
        self._report_stage_completed(
            iteration,
            "direction_intervention_continuation",
            f"Coordinator continuation {continuation} completed",
            started,
            details={
                "verdict": artifact.result.verdict,
                "selected_trial": artifact.result.selected_trial_id,
                "log": artifact.log_file,
            },
        )
        return artifact

    def _ensure_candidate(
        self,
        iteration: int,
        parent_version: str,
        intervention: InterventionArtifact,
        paths: Path,
        *,
        revision: int,
    ) -> CandidateArtifact:
        event = self._find_revision_event("compiler_completed", iteration, revision)
        if event is not None:
            candidate = _candidate_from_payload(event.payload)
            self._report_reused(iteration, "compiler", "Reusing Compiler candidate")
            return candidate
        started = self._report_stage_started(
            iteration, "compiler", "Running Compiler"
        )
        candidate = self.backend.compile_candidate(
            parent_version=parent_version,
            intervention=intervention,
            output_file=paths / (
                "compiler.json" if revision == 0 else f"compiler_revision_{revision:02d}.json"
            ),
            experience_file=self.experience_file,
        )
        if candidate.parent_version != parent_version:
            raise ValueError("Compiler candidate parent does not match Runner incumbent")
        self.journal.append(
            "compiler_completed",
            {"revision": revision, **_candidate_payload(candidate)},
            iteration=iteration,
        )
        changed_files = _changed_file_count(candidate.validation)
        self._report_stage_completed(
            iteration,
            "compiler",
            "Compiler candidate prepared",
            started,
            details={
                "candidate": candidate.iteration_id,
                "validation": "passed" if candidate.validation_passed else "failed",
                "changed_files": changed_files,
                "log": candidate.compiler_log,
            },
        )
        return candidate

    def _ensure_intervention_revision(
        self,
        iteration: int,
        version_id: str,
        evaluation: EvaluationArtifact,
        critic: CriticArtifact,
        previous: InterventionArtifact,
        compiler_feedback: str,
        paths: Path,
        *,
        revision: int,
    ) -> InterventionArtifact:
        event = self._find_revision_event(
            "direction_intervention_revised", iteration, revision
        )
        if event is not None:
            self._report_reused(
                iteration,
                "direction_intervention_revision",
                f"Reusing Coordinator revision {revision}",
            )
            return _intervention_from_payload(event.payload)
        started = self._report_stage_started(
            iteration,
            "direction_intervention_revision",
            f"Returning Compiler clarification to Coordinator (revision {revision})",
        )
        artifact = self.backend.refine_direction(
            version_id=version_id,
            evaluation=evaluation,
            critic=critic,
            previous_intervention=previous,
            compiler_feedback=compiler_feedback,
            output_dir=paths / f"intervention_revision_{revision:02d}",
        )
        self.journal.append(
            "direction_intervention_revised",
            {
                "revision": revision,
                "compiler_feedback": compiler_feedback,
                **_intervention_payload(artifact),
            },
            iteration=iteration,
        )
        self._report_stage_completed(
            iteration,
            "direction_intervention_revision",
            f"Coordinator revision {revision} completed",
            started,
            details={
                "verdict": artifact.result.verdict,
                "selected_trial": artifact.result.selected_trial_id,
                "log": artifact.log_file,
            },
        )
        return artifact

    def _record_compiler_clarification(
        self,
        iteration: int,
        candidate: CandidateArtifact,
        *,
        revision: int,
        final: bool,
    ) -> None:
        event = self._find_revision_event(
            "compiler_clarification_requested", iteration, revision
        )
        if event is None:
            self.journal.append(
                "compiler_clarification_requested",
                {
                    "revision": revision,
                    "iteration_id": candidate.iteration_id,
                    "candidate_digest": candidate.candidate_digest,
                    "compiler_summary": candidate.summary,
                    "clarification": candidate.clarification,
                },
                iteration=iteration,
            )
        summary = next(
            (
                item for item in self.store.list_iterations()
                if item.iteration_id == candidate.iteration_id
            ),
            None,
        )
        if summary is not None and summary.status == "pending":
            self.store.resume_iteration(candidate.iteration_id).reject(
                f"Compiler requested clarification: {candidate.clarification}"
            )
        self._report(
            "compiler_clarification",
            (
                "Compiler clarification returned to Coordinator"
                if not final
                else "Compiler clarification budget exhausted"
            ),
            iteration=iteration,
            details={"revision": revision, "clarification": candidate.clarification},
        )
        if final and self.journal.find("candidate_rejected", iteration) is None:
            payload = {
                "iteration_id": candidate.iteration_id,
                "candidate_digest": candidate.candidate_digest,
                "compiler_summary": candidate.summary,
                "reason": f"Compiler requested clarification: {candidate.clarification}",
                "metrics": {},
            }
            self.journal.append("candidate_rejected", payload, iteration=iteration)
            self._write_decision(iteration, "reject", payload)

    def _find_revision_event(
        self, event_type: str, iteration: int, revision: int
    ) -> EvolutionEvent | None:
        for event in reversed(self.journal.events()):
            if (
                event.event_type == event_type
                and event.iteration == iteration
                and int(event.payload.get("revision", 0)) == revision
            ):
                return event
        return None

    def _ensure_candidate_evaluation(
        self, iteration: int, candidate: CandidateArtifact, paths: Path
    ) -> EvaluationArtifact:
        event = self.journal.find("candidate_evaluated", iteration)
        if event is not None:
            self._report_reused(
                iteration, "candidate_evaluation", "Reusing candidate evaluation"
            )
            return _evaluation_from_payload(event.payload)
        started = self._report_stage_started(
            iteration, "candidate_evaluation", "Evaluating candidate"
        )
        artifact = self.backend.evaluate_candidate(
            candidate=candidate,
            experience_file=self.experience_file,
            output_dir=paths / "candidate_report",
        )
        self.journal.append(
            "candidate_evaluated",
            _evaluation_payload(artifact),
            iteration=iteration,
        )
        self._report_stage_completed(
            iteration,
            "candidate_evaluation",
            "Candidate evaluation completed",
            started,
            details={
                "accuracy": _accuracy(artifact.metrics),
                "report": artifact.report_dir,
            },
        )
        return artifact

    def _ensure_candidate_review(
        self,
        iteration: int,
        candidate: CandidateArtifact,
        candidate_evaluation: EvaluationArtifact,
        parent_evaluation: EvaluationArtifact,
        paths: Path,
    ) -> CriticArtifact:
        event = self.journal.find("candidate_reviewed", iteration)
        if event is not None:
            self._report_reused(
                iteration, "candidate_review", "Reusing candidate review"
            )
            return _critic_from_payload(event.payload)
        started = self._report_stage_started(
            iteration, "candidate_review", "Running candidate-review Critic"
        )
        artifact = self.backend.review_candidate(
            candidate=candidate,
            candidate_evaluation=candidate_evaluation,
            parent_evaluation=parent_evaluation,
            output_file=paths / "candidate_review.json",
        )
        if artifact.result.review is None:
            raise ValueError("candidate review must contain a review decision")
        self.journal.append(
            "candidate_reviewed",
            {
                **_critic_payload(artifact),
                "metric_delta": _metric_delta(
                    parent_evaluation.metrics, candidate_evaluation.metrics
                ),
            },
            iteration=iteration,
        )
        assert artifact.result.review is not None
        delta = _metric_delta(parent_evaluation.metrics, candidate_evaluation.metrics)
        self._report_stage_completed(
            iteration,
            "candidate_review",
            "Candidate review completed",
            started,
            details={
                "decision": artifact.result.review.decision,
                "accuracy_delta": _accuracy(delta),
                "log": artifact.log_file,
            },
        )
        return artifact

    def _accept_candidate(
        self,
        iteration: int,
        candidate: CandidateArtifact,
        evaluation: EvaluationArtifact,
        review: CriticArtifact,
    ) -> None:
        if self.journal.find("candidate_accepted", iteration) is not None:
            return
        session = self.store.resume_iteration(candidate.iteration_id)
        record = session.accept(
            summary=candidate.summary,
            evaluation={
                "metrics": evaluation.metrics,
                "review": review.result.review.to_dict(),
                "report_dir": str(evaluation.report_dir),
            },
            env_file=self.validation_env_file,
        )
        payload = {
            "iteration_id": candidate.iteration_id,
            "candidate_digest": candidate.candidate_digest,
            "version_id": record.version_id,
            "compiler_summary": candidate.summary,
            "review": review.result.review.to_dict(),
            **_evaluation_payload(evaluation),
        }
        review_event = self.journal.find("candidate_reviewed", iteration)
        if review_event is not None:
            payload["metric_delta"] = review_event.payload.get("metric_delta", {})
        self.journal.append("candidate_accepted", payload, iteration=iteration)
        self._write_decision(iteration, "accept", payload)
        self._report(
            "decision",
            f"Accepted candidate as {record.version_id}",
            iteration=iteration,
            details={"reason": review.result.review.reason},
        )

    def _reject_candidate(
        self,
        iteration: int,
        candidate: CandidateArtifact,
        reason: str,
        evaluation: EvaluationArtifact | None,
        *,
        review: CriticArtifact | None = None,
    ) -> None:
        if self.journal.find("candidate_rejected", iteration) is not None:
            return
        session = self.store.resume_iteration(candidate.iteration_id)
        metrics = evaluation.metrics if evaluation is not None else {}
        session.reject(reason, evaluation={"metrics": metrics})
        payload: dict[str, Any] = {
            "iteration_id": candidate.iteration_id,
            "candidate_digest": candidate.candidate_digest,
            "compiler_summary": candidate.summary,
            "reason": reason,
            "metrics": metrics,
            "validation": candidate.validation,
        }
        if review is not None and review.result.review is not None:
            payload["review"] = review.result.review.to_dict()
        review_event = self.journal.find("candidate_reviewed", iteration)
        if review_event is not None:
            payload["metric_delta"] = review_event.payload.get("metric_delta", {})
        self.journal.append("candidate_rejected", payload, iteration=iteration)
        self._write_decision(iteration, "reject", payload)
        self._report(
            "decision",
            "Rejected candidate",
            iteration=iteration,
            details={"reason": reason},
        )

    def _stored_evaluation(self, version_id: str) -> EvaluationArtifact | None:
        for event in reversed(self.journal.events()):
            if (
                event.event_type in {"candidate_accepted", "incumbent_evaluated"}
                and event.payload.get("version_id") == version_id
            ):
                artifact = _evaluation_from_payload(event.payload)
                if artifact.rollout_file.is_file() and artifact.report_dir.is_dir():
                    return artifact
        return None

    def _failed_attempt_memory(self) -> tuple[dict[str, Any], ...]:
        failures = [
            {
                "candidate_digest": event.payload.get("candidate_digest"),
                "compiler_summary": event.payload.get("compiler_summary"),
                "metrics": event.payload.get("metrics", {}),
                "metric_delta": event.payload.get("metric_delta", {}),
                "reason": event.payload.get("reason"),
                "validation": event.payload.get("validation"),
            }
            for event in self.journal.events()
            if event.event_type == "candidate_rejected"
        ]
        limit = self.config.failure_memory_limit
        return tuple(failures[-limit:]) if limit else ()

    def _is_rejected_duplicate(self, digest: str, current_iteration: int) -> bool:
        return any(
            event.event_type == "candidate_rejected"
            and event.iteration != current_iteration
            and event.payload.get("candidate_digest") == digest
            for event in self.journal.events()
        )

    def _decision_events(self) -> tuple[EvolutionEvent, ...]:
        return tuple(
            event
            for event in self.journal.events()
            if event.event_type in {"candidate_accepted", "candidate_rejected"}
        )

    def _reconcile_version_store_decisions(self) -> None:
        """补记 Version Store 已提交、Runner 尚未落盘的终态决定。"""

        decisions = {event.iteration for event in self._decision_events()}
        version_by_iteration = {
            record.iteration_id: record
            for record in self.store.list_versions()
            if record.iteration_id is not None
        }
        store_summaries = {
            summary.iteration_id: summary for summary in self.store.list_iterations()
        }
        for event in self.journal.events():
            if event.event_type != "compiler_completed" or event.iteration in decisions:
                continue
            assert event.iteration is not None
            candidate = _candidate_from_payload(event.payload)
            if candidate.clarification is not None:
                continue
            accepted = version_by_iteration.get(candidate.iteration_id)
            if accepted is not None:
                evaluation_event = self.journal.find(
                    "candidate_evaluated", event.iteration
                )
                review_event = self.journal.find("candidate_reviewed", event.iteration)
                if evaluation_event is None or review_event is None:
                    raise RuntimeError(
                        "accepted Version Store candidate has incomplete Runner evidence"
                    )
                review = _critic_from_payload(review_event.payload)
                assert review.result.review is not None
                self.journal.append(
                    "candidate_accepted",
                    {
                        "iteration_id": candidate.iteration_id,
                        "candidate_digest": candidate.candidate_digest,
                        "version_id": accepted.version_id,
                        "compiler_summary": candidate.summary,
                        "review": review.result.review.to_dict(),
                        "metric_delta": review_event.payload.get("metric_delta", {}),
                        **evaluation_event.payload,
                        "recovered": True,
                    },
                    iteration=event.iteration,
                )
                recovered = self.journal.find("candidate_accepted", event.iteration)
                assert recovered is not None
                self._write_decision(event.iteration, "accept", recovered.payload)
                self._report(
                    "decision_recovered",
                    f"Recovered accepted decision for {accepted.version_id}",
                    iteration=event.iteration,
                )
                continue
            summary = store_summaries.get(candidate.iteration_id)
            if summary is None or summary.status != "rejected":
                continue
            evaluation_event = self.journal.find("candidate_evaluated", event.iteration)
            self.journal.append(
                "candidate_rejected",
                {
                    "iteration_id": candidate.iteration_id,
                    "candidate_digest": candidate.candidate_digest,
                    "compiler_summary": candidate.summary,
                    "reason": summary.rejection_reason,
                    "metrics": (
                        evaluation_event.payload.get("metrics", {})
                        if evaluation_event is not None
                        else {}
                    ),
                    "metric_delta": {},
                    "recovered": True,
                },
                iteration=event.iteration,
            )
            recovered = self.journal.find("candidate_rejected", event.iteration)
            assert recovered is not None
            self._write_decision(event.iteration, "reject", recovered.payload)
            self._report(
                "decision_recovered",
                "Recovered rejected decision",
                iteration=event.iteration,
                details={"reason": summary.rejection_reason},
            )

    def _finish(self, status: RunStatus, reason: str) -> EvolutionOutcome:
        latest = self.store.list_versions()[-1].version_id
        decisions = self._decision_events()
        accepted = sum(event.event_type == "candidate_accepted" for event in decisions)
        self.journal.append(
            "run_completed",
            {
                "status": status,
                "reason": reason,
                "completed_iterations": len(decisions),
                "accepted_iterations": accepted,
                "latest_version": latest,
            },
        )
        outcome = EvolutionOutcome(
            status=status,
            completed_iterations=len(decisions),
            accepted_iterations=accepted,
            latest_version=latest,
            reason=reason,
        )
        self._report_outcome(outcome)
        return outcome

    def _terminal_outcome(self) -> EvolutionOutcome | None:
        for event in reversed(self.journal.events()):
            if event.event_type != "run_completed":
                continue
            return EvolutionOutcome(
                status=event.payload["status"],
                completed_iterations=int(event.payload["completed_iterations"]),
                accepted_iterations=int(event.payload["accepted_iterations"]),
                latest_version=str(event.payload["latest_version"]),
                reason=str(event.payload["reason"]),
            )
        return None

    def _validate_run_identity(self) -> None:
        if not self.run_file.exists():
            raise RuntimeError(f"evolution run is not initialized: {self.run_dir}")
        raw = json.loads(self.run_file.read_text(encoding="utf-8"))
        if Path(raw["checkpoint_store"]).resolve() != self.store.root:
            raise ValueError("evolution run Harness Checkpoint Store does not match")
        expected = raw["experience_set"]["digest"]
        if file_digest(self.experience_file) != expected:
            raise ValueError("evolution Experience Set digest does not match run.json")

    def _report_stage_started(
        self, iteration: int, stage: str, message: str
    ) -> float:
        self._report("stage_started", message, iteration=iteration, stage=stage)
        return time.perf_counter()

    def _report_stage_completed(
        self,
        iteration: int,
        stage: str,
        message: str,
        started: float,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self._report(
            "stage_completed",
            message,
            iteration=iteration,
            stage=stage,
            elapsed_seconds=time.perf_counter() - started,
            details=details,
        )

    def _report_reused(self, iteration: int, stage: str, message: str) -> None:
        self._report("stage_reused", message, iteration=iteration, stage=stage)

    def _report_outcome(
        self, outcome: EvolutionOutcome, *, reused: bool = False
    ) -> None:
        self._report(
            "run_completed",
            "Evolution run already completed" if reused else "Evolution run completed",
            details={
                "status": outcome.status,
                "iterations": outcome.completed_iterations,
                "accepted": outcome.accepted_iterations,
                "latest_version": outcome.latest_version,
                "reason": outcome.reason,
            },
        )

    def _report(
        self,
        event_type: str,
        message: str,
        *,
        iteration: int | None = None,
        stage: str | None = None,
        elapsed_seconds: float | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.progress.report(
            EvolutionProgressEvent(
                event_type=event_type,
                message=message,
                iteration=iteration,
                total_iterations=(
                    self.config.max_iterations if iteration is not None else None
                ),
                stage=stage,
                elapsed_seconds=elapsed_seconds,
                details=dict(details or {}),
            )
        )

    def _iteration_paths(self, iteration: int) -> Path:
        return self.run_dir / "iterations" / f"{iteration:04d}"

    def _write_decision(
        self, iteration: int, decision: str, payload: dict[str, Any]
    ) -> None:
        path = self._iteration_paths(iteration) / "decision.json"
        path.write_text(
            json.dumps(
                {"schema_version": 1, "decision": decision, **payload},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


def _evaluation_payload(artifact: EvaluationArtifact) -> dict[str, Any]:
    return {
        "rollout_file": str(artifact.rollout_file.resolve()),
        "report_dir": str(artifact.report_dir.resolve()),
        "metrics": artifact.metrics,
    }


def _evaluation_from_payload(payload: dict[str, Any]) -> EvaluationArtifact:
    return EvaluationArtifact(
        rollout_file=Path(payload["rollout_file"]),
        report_dir=Path(payload["report_dir"]),
        metrics=dict(payload["metrics"]),
    )


def _critic_payload(artifact: CriticArtifact) -> dict[str, Any]:
    return {"log_file": str(artifact.log_file.resolve()), "result": artifact.result.to_dict()}


def _critic_from_payload(payload: dict[str, Any]) -> CriticArtifact:
    return CriticArtifact(
        log_file=Path(payload["log_file"]),
        result=CriticResult.from_dict(payload["result"]),
    )


def _intervention_payload(artifact: InterventionArtifact) -> dict[str, Any]:
    return {
        "log_file": str(artifact.log_file.resolve()),
        "result": artifact.result.to_dict(),
    }


def _intervention_from_payload(payload: dict[str, Any]) -> InterventionArtifact:
    return InterventionArtifact(
        log_file=Path(payload["log_file"]),
        result=InterventionCoordinatorResult.from_dict(payload["result"]),
    )


def _candidate_payload(candidate: CandidateArtifact) -> dict[str, Any]:
    return {
        "iteration_id": candidate.iteration_id,
        "parent_version": candidate.parent_version,
        "candidate_digest": candidate.candidate_digest,
        "compiler_log": str(candidate.compiler_log.resolve()),
        "summary": candidate.summary,
        "validation_passed": candidate.validation_passed,
        "validation": candidate.validation,
        "clarification": candidate.clarification,
    }


def _candidate_from_payload(payload: dict[str, Any]) -> CandidateArtifact:
    return CandidateArtifact(
        iteration_id=str(payload["iteration_id"]),
        parent_version=str(payload["parent_version"]),
        candidate_digest=str(payload["candidate_digest"]),
        compiler_log=Path(payload["compiler_log"]),
        summary=str(payload["summary"]),
        validation_passed=bool(payload["validation_passed"]),
        validation=payload.get("validation"),
        clarification=payload.get("clarification"),
    )


def _metric_delta(
    parent: dict[str, Any], candidate: dict[str, Any]
) -> dict[str, Any]:
    """递归计算可比较数值的 candidate-parent 差值。"""

    result: dict[str, Any] = {}
    for key in sorted(set(parent) & set(candidate)):
        before = parent[key]
        after = candidate[key]
        if isinstance(before, dict) and isinstance(after, dict):
            nested = _metric_delta(before, after)
            if nested:
                result[key] = nested
        elif (
            isinstance(before, (int, float))
            and not isinstance(before, bool)
            and isinstance(after, (int, float))
            and not isinstance(after, bool)
        ):
            result[key] = after - before
    return result


def _accuracy(metrics: dict[str, Any]) -> float | None:
    answers = metrics.get("answers")
    if not isinstance(answers, dict):
        return None
    value = answers.get("accuracy")
    return float(value) if isinstance(value, (int, float)) else None


def _changed_file_count(validation: dict[str, Any] | None) -> int | None:
    if validation is None:
        return None
    paths: set[str] = set()
    for key in ("added_paths", "modified_paths", "removed_paths"):
        value = validation.get(key)
        if isinstance(value, (list, tuple)):
            paths.update(str(path) for path in value)
    return len(paths)


def _validation_errors(validation: dict[str, Any] | None) -> tuple[str, ...]:
    if not isinstance(validation, dict):
        return ()
    errors = validation.get("errors")
    if not isinstance(errors, (list, tuple)):
        return ()
    return tuple(str(error) for error in errors if str(error).strip())
