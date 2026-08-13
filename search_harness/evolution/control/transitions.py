"""Localized deterministic transitions between Evolution Controller work items."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .domain import (
    EffectResult,
    EvolutionControlConfig,
    WorkItem,
    WorkKind,
)
from .policies import evaluate_promotion


@dataclass(frozen=True)
class TransitionPlan:
    """The durable control-plane actions caused by one terminal work item."""

    next_items: tuple[WorkItem, ...] = ()
    complete_reason: str | None = None
    version_advance: tuple[str, int] | None = None


def initial_work(*, run_id: str, version_id: str) -> WorkItem:
    """Create the first incumbent evaluation for a new run."""

    return WorkItem(
        work_id=_stable_id(run_id, "initial", WorkKind.EVALUATE_INCUMBENT),
        kind=WorkKind.EVALUATE_INCUMBENT,
        subject_ref=f"generation:1:{version_id}",
        payload={
            "generation": 1,
            "version_id": version_id,
            "research_attempt": 1,
        },
    )


def retry_work(item: WorkItem) -> WorkItem:
    """Create one deterministic retry without mutating the original item."""

    return WorkItem(
        work_id=_stable_id(
            item.work_id,
            f"retry:{item.attempt + 1}",
            item.kind,
        ),
        kind=item.kind,
        subject_ref=item.subject_ref,
        input_refs=dict(item.input_refs),
        payload=dict(item.payload),
        parent_work_id=item.work_id,
        attempt=item.attempt + 1,
    )


def transition_completed(
    *,
    item: WorkItem,
    result: EffectResult,
    config: EvolutionControlConfig,
) -> TransitionPlan:
    """Route one successful effect by its local result and explicit budgets."""

    route = _CompletedTransition(
        item=item,
        result=result,
        config=config,
    )
    handler = getattr(route, f"on_{item.kind.value}")
    return handler()


class _CompletedTransition:
    def __init__(
        self,
        *,
        item: WorkItem,
        result: EffectResult,
        config: EvolutionControlConfig,
    ) -> None:
        self.item = item
        self.result = result
        self.config = config

    def on_evaluate_incumbent(self) -> TransitionPlan:
        refs = _merge_refs(self.item.input_refs, self.result.artifact_refs)
        payload = _context(self.item)
        payload["incumbent_metrics"] = _required_object(
            self.result.outcome,
            "metrics",
        )
        return self._one(
            WorkKind.ANALYZE_FAILURE,
            "incumbent_evaluated",
            refs=refs,
            payload=payload,
        )

    def on_analyze_failure(self) -> TransitionPlan:
        refs = _merge_refs(self.item.input_refs, self.result.artifact_refs)
        payload = _context(self.item)
        return self._one(
            WorkKind.RESEARCH_HYPOTHESIS,
            "failure_analyzed",
            refs=refs,
            payload=payload,
        )

    def on_research_hypothesis(self) -> TransitionPlan:
        current_refs = _merge_refs(
            self.item.input_refs,
            self.result.artifact_refs,
        )
        refs = {
            key: current_refs[key]
            for key in (
                "rollout_file",
                "report_dir",
                "failure_artifact",
                "hypothesis_artifact",
            )
            if key in current_refs
        }
        payload = _context(self.item)
        payload.pop("research_continuation", None)
        payload.pop("assignment", None)
        payload.update(
            {
                "trial_count": 0,
                "assignment_count": 0,
                "used_assignments": [],
                "prior_obligation": None,
                "pending_assignments": [],
                "batch_assignment_count": 0,
                "batch_executed_count": 0,
                "trial_budget": {
                    "max_trials_per_hypothesis": (
                        self.config.max_trials_per_hypothesis
                    ),
                    "trial_batch_size": self.config.trial_batch_size,
                    "max_trial_assignments": (
                        self.config.max_trial_assignments
                    ),
                },
            }
        )
        return self._one(
            WorkKind.SELECT_TRIAL,
            "hypothesis_ready",
            refs=refs,
            payload=payload,
        )

    def on_select_trial(self) -> TransitionPlan:
        status = _required_string(self.result.outcome, "status")
        if status == "exhausted":
            return TransitionPlan(
                complete_reason=(
                    "No unused rollout prefix matched the frozen "
                    "hypothesis and assignment budget."
                )
            )
        if status != "selected":
            raise ValueError(f"unknown trial selection status: {status}")
        payload = _context(self.item)
        selection_mode = _required_string(
            self.result.outcome,
            "selection_mode",
        )
        if selection_mode not in {"fresh", "reuse"}:
            raise ValueError(
                f"unknown trial selection mode: {selection_mode}"
            )
        raw_assignments = _required_list(
            self.result.outcome,
            "assignments",
        )
        assignments = [
            _required_list_object(raw_assignments, index, "assignments")
            for index in range(len(raw_assignments))
        ]
        if not assignments:
            raise ValueError("selected trial batch must contain assignments")
        previous_count = _non_negative_payload_int(
            payload,
            "assignment_count",
        )
        trial_count = _non_negative_payload_int(payload, "trial_count")
        if len(assignments) > self.config.trial_batch_size:
            raise ValueError(
                "selected trial batch exceeds trial_batch_size"
            )
        if trial_count + len(assignments) > (
            self.config.max_trials_per_hypothesis
        ):
            raise ValueError(
                "selected trial batch exceeds the remaining Trial budget"
            )
        output_count = _non_negative_payload_int(
            self.result.outcome,
            "assignment_count",
        )
        expected_count = previous_count + len(assignments)
        if expected_count > self.config.max_trial_assignments:
            raise ValueError(
                "selected trial batch exceeds the remaining Assignment budget"
            )
        if output_count != expected_count:
            raise ValueError(
                "Selector assignment_count differs from the deterministic "
                "batch increment"
            )
        previous_used = _string_list(
            payload.get("used_assignments", []),
            "used_assignments",
        )
        selected_keys = [_assignment_key(item) for item in assignments]
        if len(selected_keys) != len(set(selected_keys)):
            raise ValueError("selected trial batch contains duplicate assignments")
        output_used = _string_list(
            self.result.outcome.get("used_assignments"),
            "used_assignments",
        )
        expected_used = sorted({*previous_used, *selected_keys})
        if output_used != expected_used:
            raise ValueError(
                "Selector used_assignments differs from the deterministic "
                "Assignment set"
            )
        previous_examples = {
            _assignment_key_parts(key)[0] for key in previous_used
        }
        extends_coverage = any(
            str(assignment["example_id"]) not in previous_examples
            for assignment in assignments
        )
        expected_mode = "fresh" if extends_coverage else "reuse"
        if selection_mode != expected_mode:
            raise ValueError(
                "selection_mode does not match example coverage expansion"
            )
        payload["pending_assignments"] = assignments
        payload["batch_assignment_count"] = len(assignments)
        payload["batch_executed_count"] = 0
        payload["assignment"] = dict(assignments[0])
        payload["assignment_count"] = expected_count
        payload["used_assignments"] = expected_used
        return self._one(
            WorkKind.EXECUTE_TRIAL,
            f"batch:{payload['assignment_count']}",
            refs=self.item.input_refs,
            payload=payload,
        )

    def on_execute_trial(self) -> TransitionPlan:
        if "results" in self.result.outcome:
            return self._on_execute_trial_batch()
        output = _required_object(self.result.outcome, "output")
        result_kind = _required_string(output, "result_kind")
        refs = _merge_refs(self.item.input_refs, self.result.artifact_refs)
        payload = _context(self.item)
        if result_kind not in {"executed", "unsuitable_assignment"}:
            raise ValueError(f"unknown Intervention Worker result: {result_kind}")
        assignment = _required_object(payload, "assignment")
        pending = _pending_assignments(payload, assignment)
        if pending[0] != assignment:
            raise ValueError(
                "current assignment differs from pending batch head"
            )
        batch_assignment_count = _optional_non_negative_payload_int(
            payload,
            "batch_assignment_count",
            len(pending),
        )
        batch_executed_count = _optional_non_negative_payload_int(
            payload,
            "batch_executed_count",
            0,
        )
        if batch_assignment_count < len(pending):
            raise ValueError(
                "batch_assignment_count is smaller than pending assignments"
            )
        processed_count = batch_assignment_count - len(pending)
        if batch_executed_count > processed_count:
            raise ValueError(
                "batch_executed_count exceeds processed assignments"
            )

        if result_kind == "executed":
            trial_count = int(payload.get("trial_count", 0)) + 1
            payload["trial_count"] = trial_count
            trial_ref = self.result.artifact_refs.get("worker_artifact")
            if trial_ref is None:
                raise ValueError("executed trial result lacks worker_artifact")
            refs[f"trial_{trial_count:03d}"] = trial_ref
            batch_executed_count += 1

        pending = pending[1:]
        payload["pending_assignments"] = pending
        payload["batch_executed_count"] = batch_executed_count
        payload.pop("assignment", None)
        if pending:
            payload["assignment"] = dict(pending[0])
            processed_count = batch_assignment_count - len(pending)
            return self._one(
                WorkKind.EXECUTE_TRIAL,
                f"batch_assignment:{processed_count + 1}",
                refs=refs,
                payload=payload,
            )

        _clear_batch_state(payload)
        if batch_executed_count > 0:
            return self._one(
                WorkKind.REVIEW_EVIDENCE,
                f"batch_executed:{batch_executed_count}",
                refs=refs,
                payload=payload,
            )
        if int(payload.get("assignment_count", 0)) >= (
            self.config.max_trial_assignments
        ):
            return TransitionPlan(
                complete_reason="Trial assignment budget was exhausted."
            )
        if int(payload.get("trial_count", 0)) >= (
            self.config.max_trials_per_hypothesis
        ):
            return TransitionPlan(
                complete_reason="Per-hypothesis trial budget was exhausted."
            )
        return self._one(
            WorkKind.SELECT_TRIAL,
            "batch_without_trial",
            refs=refs,
            payload=payload,
        )

    def _on_execute_trial_batch(self) -> TransitionPlan:
        """Commit one ordered parallel batch as a single durable transition."""

        payload = _context(self.item)
        assignment = _required_object(payload, "assignment")
        pending = _pending_assignments(payload, assignment)
        if pending[0] != assignment:
            raise ValueError(
                "current assignment differs from pending batch head"
            )
        raw_results = _required_list(self.result.outcome, "results")
        results = [
            _required_list_object(raw_results, index, "results")
            for index in range(len(raw_results))
        ]
        if len(results) != len(pending):
            raise ValueError(
                "parallel Trial result count differs from pending assignments"
            )
        batch_assignment_count = _optional_non_negative_payload_int(
            payload,
            "batch_assignment_count",
            len(pending),
        )
        if batch_assignment_count != len(pending):
            raise ValueError(
                "parallel Trial batch size differs from pending assignments"
            )

        refs = dict(self.item.input_refs)
        trial_count = _non_negative_payload_int(payload, "trial_count")
        batch_executed_count = 0
        for index, (current, result) in enumerate(
            zip(pending, results, strict=True),
            start=1,
        ):
            expected_key = _assignment_key(current)
            if _required_string(result, "assignment_key") != expected_key:
                raise ValueError(
                    "parallel Trial results do not preserve Assignment order"
                )
            output = _required_object(result, "output")
            result_kind = _required_string(output, "result_kind")
            if result_kind not in {"executed", "unsuitable_assignment"}:
                raise ValueError(
                    "unknown Intervention Worker result: "
                    f"{result_kind}"
                )
            artifact_key = _required_string(result, "artifact_key")
            expected_artifact_key = f"worker_artifact_{index:03d}"
            if artifact_key != expected_artifact_key:
                raise ValueError(
                    "parallel Trial artifact keys do not preserve batch order"
                )
            artifact_ref = self.result.artifact_refs.get(artifact_key)
            if artifact_ref is None:
                raise ValueError(
                    f"parallel Trial result lacks {artifact_key}"
                )
            if result_kind == "executed":
                trial_count += 1
                batch_executed_count += 1
                refs[f"trial_{trial_count:03d}"] = artifact_ref

        payload["trial_count"] = trial_count
        _clear_batch_state(payload)
        if batch_executed_count > 0:
            return self._one(
                WorkKind.REVIEW_EVIDENCE,
                f"parallel_batch_executed:{batch_executed_count}",
                refs=refs,
                payload=payload,
            )
        if int(payload.get("assignment_count", 0)) >= (
            self.config.max_trial_assignments
        ):
            return TransitionPlan(
                complete_reason="Trial assignment budget was exhausted."
            )
        if trial_count >= self.config.max_trials_per_hypothesis:
            return TransitionPlan(
                complete_reason="Per-hypothesis trial budget was exhausted."
            )
        return self._one(
            WorkKind.SELECT_TRIAL,
            "parallel_batch_without_trial",
            refs=refs,
            payload=payload,
        )

    def on_review_evidence(self) -> TransitionPlan:
        output = _required_object(self.result.outcome, "output")
        decision = _required_string(output, "decision")
        refs = _merge_refs(self.item.input_refs, self.result.artifact_refs)
        payload = _context(self.item)
        payload["prior_obligation"] = output.get("next_obligation")

        if decision == "continue":
            if int(payload.get("trial_count", 0)) >= (
                self.config.max_trials_per_hypothesis
            ):
                return TransitionPlan(
                    complete_reason=(
                        "Evidence Reviewer requested another trial after the "
                        "per-hypothesis trial budget was exhausted."
                    )
                )
            if int(payload.get("assignment_count", 0)) >= (
                self.config.max_trial_assignments
            ):
                return TransitionPlan(
                    complete_reason=(
                        "Evidence Reviewer requested another trial after "
                        "the assignment budget was exhausted."
                    )
                )
            return self._one(
                WorkKind.SELECT_TRIAL,
                "review_continue",
                refs=refs,
                payload=payload,
            )
        if decision in {"revise", "reject"}:
            return self._research_revision(
                feedback_source="evidence_reviewer",
                feedback=output,
                refs=refs,
                payload=payload,
            )
        if decision != "ready_to_distill":
            raise ValueError(f"unknown Evidence Reviewer decision: {decision}")
        return self._one(
            WorkKind.DISTILL_MECHANISM,
            "evidence_ready",
            refs=refs,
            payload=payload,
        )

    def on_distill_mechanism(self) -> TransitionPlan:
        output = _required_object(self.result.outcome, "output")
        decision = _required_string(output, "decision")
        refs = _merge_refs(self.item.input_refs, self.result.artifact_refs)
        payload = _context(self.item)
        if decision == "not_distillable":
            return TransitionPlan(
                complete_reason="Evidence was judged not distillable."
            )
        if decision == "needs_evidence":
            if int(payload.get("trial_count", 0)) >= (
                self.config.max_trials_per_hypothesis
            ):
                return TransitionPlan(
                    complete_reason=(
                        "Mechanism Distiller requested more evidence after "
                        "the trial budget was exhausted."
                    )
                )
            if int(payload.get("assignment_count", 0)) >= (
                self.config.max_trial_assignments
            ):
                return TransitionPlan(
                    complete_reason=(
                        "Mechanism Distiller requested more evidence after "
                        "the assignment budget was exhausted."
                    )
                )
            payload["prior_obligation"] = output.get("next_obligation")
            return self._one(
                WorkKind.SELECT_TRIAL,
                "distiller_needs_evidence",
                refs=refs,
                payload=payload,
            )
        if decision != "distilled":
            raise ValueError(f"unknown Mechanism Distiller decision: {decision}")
        return self._one(
            WorkKind.COMPILE_CANDIDATE,
            "mechanism_distilled",
            refs=refs,
            payload=payload,
        )

    def on_compile_candidate(self) -> TransitionPlan:
        output = _required_object(self.result.outcome, "output")
        decision = _required_string(output, "decision")
        refs = _merge_refs(self.item.input_refs, self.result.artifact_refs)
        payload = _context(self.item)
        if decision == "needs_evidence":
            refs.pop("compiler_candidate_file", None)
            if int(payload.get("trial_count", 0)) >= (
                self.config.max_trials_per_hypothesis
            ):
                return TransitionPlan(
                    complete_reason=(
                        "Compiler requested more evidence after the trial "
                        "budget was exhausted."
                    )
                )
            if int(payload.get("assignment_count", 0)) >= (
                self.config.max_trial_assignments
            ):
                return TransitionPlan(
                    complete_reason=(
                        "Compiler requested more evidence after the assignment "
                        "budget was exhausted."
                    )
                )
            payload["prior_obligation"] = _required_string(
                output,
                "next_obligation",
            )
            return self._one(
                WorkKind.SELECT_TRIAL,
                "compiler_needs_evidence",
                refs=refs,
                payload=payload,
            )
        if decision in {
            "needs_mechanism_revision",
            "implementation_blocked",
        }:
            refs.pop("compiler_candidate_file", None)
            revision = int(payload.get("mechanism_revision", 0)) + 1
            if revision > self.config.max_mechanism_revisions:
                return TransitionPlan(
                    complete_reason=(
                        "Compiler requested a mechanism revision after the "
                        "configured revision budget was exhausted."
                    )
                )
            payload["mechanism_revision"] = revision
            constraints = list(payload.get("capability_constraints", []))
            constraints.append(
                _required_string(output, "next_obligation")
            )
            payload["capability_constraints"] = constraints
            return self._one(
                WorkKind.DISTILL_MECHANISM,
                f"compiler_mechanism_revision:{revision}",
                refs=refs,
                payload=payload,
            )
        if decision != "submitted":
            raise ValueError(f"unknown Compiler decision: {decision}")
        return self._one(
            WorkKind.STAGE_CANDIDATE,
            "compiler_submitted",
            refs=refs,
            payload=payload,
        )

    def on_stage_candidate(self) -> TransitionPlan:
        status = _required_string(self.result.outcome, "status")
        refs = _merge_refs(self.item.input_refs, self.result.artifact_refs)
        payload = _context(self.item)
        if status == "validation_failed":
            revision = int(payload.get("compiler_revision", 0)) + 1
            if revision > self.config.max_compiler_revisions:
                return TransitionPlan(
                    complete_reason=(
                        "Candidate validation failed after the Compiler "
                        "revision budget was exhausted."
                    )
                )
            payload["compiler_revision"] = revision
            feedback = self.result.outcome.get("validation")
            payload["validation_feedback"] = (
                list(feedback.get("errors", []))
                if isinstance(feedback, dict)
                else ["Candidate validation failed."]
            )
            return self._one(
                WorkKind.COMPILE_CANDIDATE,
                f"validation_revision:{revision}",
                refs=refs,
                payload=payload,
            )
        if status == "unchanged_rejected_candidate":
            reason = self.result.outcome.get("rejection_reason")
            detail = (
                str(reason).strip()
                if isinstance(reason, str) and reason.strip()
                else "the Compiler resubmitted an unchanged rejected Candidate"
            )
            return self._new_research_attempt(
                refs=refs,
                payload=payload,
                rejection_reason=detail,
                route="unchanged_rejected_candidate",
            )
        if status != "valid":
            raise ValueError(f"unknown candidate stage status: {status}")
        payload.update(
            {
                "candidate_attempt_id": _required_string(
                    self.result.outcome,
                    "candidate_attempt_id",
                ),
                "candidate_digest": _required_string(
                    self.result.outcome,
                    "candidate_digest",
                ),
                "validation_summary": _required_object(
                    self.result.outcome,
                    "validation",
                ),
            }
        )
        return self._one(
            WorkKind.VERIFY_CONFORMANCE,
            "candidate_valid",
            refs=refs,
            payload=payload,
        )

    def on_verify_conformance(self) -> TransitionPlan:
        decision = _required_string(self.result.outcome, "decision")
        refs = _merge_refs(self.item.input_refs, self.result.artifact_refs)
        payload = _context(self.item)
        summary = _required_object(self.result.outcome, "summary")
        payload["conformance_summary"] = summary
        if decision == "pass":
            return self._one(
                WorkKind.EVALUATE_CANDIDATE,
                "conformance_passed",
                refs=refs,
                payload=payload,
            )
        if decision not in {"revise", "revise_implementation"}:
            raise ValueError(
                f"unknown conformance decision: {decision}"
            )
        revision = int(payload.get("candidate_revision", 0)) + 1
        payload["candidate_revision"] = revision
        target = summary.get("recommended_route", "implementation")
        if target not in {"evidence", "mechanism", "implementation"}:
            target = "implementation"
        route_feedback = summary.get("route_feedback")
        selected_feedback = (
            route_feedback.get(target)
            if isinstance(route_feedback, dict)
            else None
        )
        feedback = (
            selected_feedback
            if isinstance(selected_feedback, list)
            else summary.get("compiler_feedback")
        )
        obligations = (
            [str(value) for value in feedback if str(value).strip()]
            if isinstance(feedback, list)
            else []
        )
        obligation = (
            " | ".join(obligations)
            if obligations
            else (
                "Repair the Candidate so every intervention example has "
                "at least one faithful complete replay and no runtime or "
                "implementation mismatch."
            )
        )
        payload["after_rejection"] = (
            {
                "target": target,
                "obligation": obligation,
            }
            if revision <= self.config.max_candidate_revisions
            else None
        )
        return self._one(
            WorkKind.REJECT_CANDIDATE,
            "conformance_failed",
            refs=refs,
            payload=payload,
        )

    def on_evaluate_candidate(self) -> TransitionPlan:
        refs = _merge_refs(self.item.input_refs, self.result.artifact_refs)
        payload = _context(self.item)
        payload["candidate_metrics"] = _required_object(
            self.result.outcome,
            "metrics",
        )
        return self._one(
            WorkKind.REVIEW_CANDIDATE,
            "candidate_evaluated",
            refs=refs,
            payload=payload,
        )

    def on_review_candidate(self) -> TransitionPlan:
        output = _required_object(self.result.outcome, "output")
        recommendation = _required_string(output, "recommendation")
        refs = _merge_refs(self.item.input_refs, self.result.artifact_refs)
        payload = _context(self.item)
        gate = evaluate_promotion(
            reviewer_recommendation=recommendation,
            validation_summary=_required_payload_object(
                payload,
                "validation_summary",
            ),
            incumbent_metrics=_required_payload_object(
                payload,
                "incumbent_metrics",
            ),
            candidate_metrics=_required_payload_object(
                payload,
                "candidate_metrics",
            ),
            config=self.config,
        )
        payload["promotion_gate"] = gate.to_dict()
        payload["candidate_review"] = output

        if gate.passed:
            return self._one(
                WorkKind.PROMOTE_CANDIDATE,
                "promotion_gate_passed",
                refs=refs,
                payload=payload,
            )
        if recommendation == "revise":
            revision = int(payload.get("candidate_revision", 0)) + 1
            if revision <= self.config.max_candidate_revisions:
                payload["candidate_revision"] = revision
                payload["after_rejection"] = {
                    "target": _required_string(output, "revision_target"),
                    "obligation": _required_string(
                        output,
                        "next_obligation",
                    ),
                }
            else:
                payload["after_rejection"] = None
            payload["start_new_research_attempt"] = False
        else:
            payload["after_rejection"] = None
            payload["start_new_research_attempt"] = True
        return self._one(
            WorkKind.REJECT_CANDIDATE,
            f"promotion_gate_failed:{recommendation}",
            refs=refs,
            payload=payload,
        )

    def on_promote_candidate(self) -> TransitionPlan:
        version_id = _required_string(self.result.outcome, "version_id")
        generation = int(self.item.payload.get("generation", 1))
        if generation >= self.config.max_generations:
            return TransitionPlan(
                complete_reason=(
                    f"Accepted {version_id}; generation budget completed."
                ),
                version_advance=(version_id, generation),
            )
        next_generation = generation + 1
        next_item = WorkItem(
            work_id=_stable_id(
                self.item.work_id,
                f"generation:{next_generation}",
                WorkKind.EVALUATE_INCUMBENT,
            ),
            kind=WorkKind.EVALUATE_INCUMBENT,
            subject_ref=f"generation:{next_generation}:{version_id}",
            payload={
                "generation": next_generation,
                "version_id": version_id,
                "research_attempt": 1,
            },
            parent_work_id=self.item.work_id,
        )
        return TransitionPlan(
            next_items=(next_item,),
            version_advance=(version_id, next_generation),
        )

    def on_reject_candidate(self) -> TransitionPlan:
        after = self.item.payload.get("after_rejection")
        if not isinstance(after, dict):
            if self.item.payload.get("start_new_research_attempt") is True:
                return self._new_research_attempt(
                    refs=_merge_refs(
                        self.item.input_refs,
                        self.result.artifact_refs,
                    ),
                    payload=_context(self.item),
                    rejection_reason=_candidate_rejection_reason(
                        self.item.payload
                    ),
                    route="candidate_rejected",
                )
            return TransitionPlan(
                complete_reason="Candidate was rejected by review or promotion gate."
            )
        target = _required_string(after, "target")
        obligation = _required_string(after, "obligation")
        refs = _without_prefix(
            self.item.input_refs,
            (
                "candidate_",
                "conformance_",
                "compiler_artifact",
                "candidate_attempt_",
            ),
        )
        if target != "implementation":
            refs.pop("compiler_candidate_file", None)
        payload = _context(self.item)
        payload["after_rejection"] = None
        if target == "evidence":
            payload["prior_obligation"] = obligation
            if int(payload.get("trial_count", 0)) >= (
                self.config.max_trials_per_hypothesis
            ):
                return TransitionPlan(
                    complete_reason=(
                        "Candidate evidence revision was requested after "
                        "the trial budget was exhausted."
                    )
                )
            if int(payload.get("assignment_count", 0)) >= (
                self.config.max_trial_assignments
            ):
                return TransitionPlan(
                    complete_reason=(
                        "Candidate evidence revision was requested after "
                        "the assignment budget was exhausted."
                    )
                )
            kind = WorkKind.SELECT_TRIAL
        elif target == "mechanism":
            constraints = list(
                payload.get("capability_constraints", [])
            )
            constraints.append(obligation)
            payload["capability_constraints"] = constraints
            kind = WorkKind.DISTILL_MECHANISM
        elif target == "implementation":
            constraints = list(
                payload.get("implementation_constraints", [])
            )
            constraints.append(obligation)
            payload["implementation_constraints"] = constraints
            kind = WorkKind.COMPILE_CANDIDATE
        else:
            raise ValueError(f"unknown candidate revision target: {target}")
        return self._one(
            kind,
            f"candidate_revision:{target}",
            refs=refs,
            payload=payload,
        )

    def _new_research_attempt(
        self,
        *,
        refs: dict[str, str],
        payload: dict[str, Any],
        rejection_reason: str,
        route: str,
    ) -> TransitionPlan:
        """Abandon one rejected direction while reusing incumbent evidence."""

        attempt = int(payload.get("research_attempt", 1)) + 1
        next_refs = {
            key: value
            for key, value in refs.items()
            if key in {"report_dir", "rollout_file"}
        }
        next_payload = {
            key: payload[key]
            for key in ("generation", "version_id", "incumbent_metrics")
            if key in payload
        }
        next_payload["research_attempt"] = attempt
        next_payload["analysis_focus"] = _alternate_failure_focus(
            rejection_reason
        )
        return self._one(
            WorkKind.ANALYZE_FAILURE,
            f"research_attempt:{attempt}:{route}",
            refs=next_refs,
            payload=next_payload,
        )

    def _research_revision(
        self,
        *,
        feedback_source: str,
        feedback: dict[str, Any],
        refs: dict[str, str],
        payload: dict[str, Any],
    ) -> TransitionPlan:
        revision = int(payload.get("hypothesis_revision", 0)) + 1
        if revision > self.config.max_hypothesis_revisions:
            return TransitionPlan(
                complete_reason=(
                    "Hypothesis revision budget was exhausted before "
                    "evidence became distillable."
                )
            )
        payload["hypothesis_revision"] = revision
        payload["research_continuation"] = {
            "feedback_source": feedback_source,
            "feedback": feedback,
        }
        return self._one(
            WorkKind.RESEARCH_HYPOTHESIS,
            f"hypothesis_revision:{revision}",
            refs=refs,
            payload=payload,
        )

    def _one(
        self,
        kind: WorkKind,
        route: str,
        *,
        refs: dict[str, str],
        payload: dict[str, Any],
    ) -> TransitionPlan:
        return TransitionPlan(
            next_items=(
                WorkItem(
                    work_id=_stable_id(self.item.work_id, route, kind),
                    kind=kind,
                    subject_ref=self.item.subject_ref,
                    input_refs=dict(refs),
                    payload=dict(payload),
                    parent_work_id=self.item.work_id,
                ),
            )
        )


def _stable_id(parent_id: str, route: str, kind: WorkKind) -> str:
    raw = json.dumps(
        [parent_id, route, kind.value],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{kind.value}-{digest}"


def _context(item: WorkItem) -> dict[str, Any]:
    return dict(item.payload)


def _merge_refs(
    current: dict[str, str],
    added: dict[str, str],
) -> dict[str, str]:
    merged = dict(current)
    for key, value in added.items():
        merged[key] = value
    return merged


def _without_prefix(
    refs: dict[str, str],
    prefixes: tuple[str, ...],
) -> dict[str, str]:
    return {
        key: value
        for key, value in refs.items()
        if not key.startswith(prefixes)
    }


def _candidate_rejection_reason(payload: dict[str, Any]) -> str:
    review = payload.get("candidate_review")
    if isinstance(review, dict):
        recommendation = review.get("recommendation")
        reason = review.get("reason")
        if (
            recommendation == "reject"
            and isinstance(reason, str)
            and reason.strip()
        ):
            return reason.strip()
    gate = payload.get("promotion_gate")
    if isinstance(gate, dict):
        reasons = gate.get("reasons")
        if isinstance(reasons, list):
            joined = "; ".join(
                str(reason).strip()
                for reason in reasons
                if str(reason).strip()
            )
            if joined:
                return joined
    if isinstance(review, dict):
        reason = review.get("reason")
        if isinstance(reason, str) and reason.strip():
            return reason.strip()
    return "the Candidate was rejected by review or the promotion gate"


def _alternate_failure_focus(rejection_reason: str) -> str:
    prefix = (
        "Select a different bounded failure pattern supported directly by "
        "the incumbent trajectories. Do not continue the rejected research "
        "direction. The previous Candidate was rejected because: "
    )
    return (prefix + rejection_reason.strip())[:300]


def _required_object(value: dict[str, Any], name: str) -> dict[str, Any]:
    item = value.get(name)
    if not isinstance(item, dict):
        raise TypeError(f"{name} must be an object")
    return dict(item)


def _required_list_object(
    values: list[Any],
    index: int,
    name: str,
) -> dict[str, Any]:
    item = values[index]
    if not isinstance(item, dict):
        raise TypeError(f"{name}[{index}] must be an object")
    return dict(item)


def _pending_assignments(
    payload: dict[str, Any],
    current_assignment: dict[str, Any],
) -> list[dict[str, Any]]:
    """Load one active queue, including legacy single-assignment work."""

    raw_pending = payload.get("pending_assignments")
    if raw_pending is None:
        return [dict(current_assignment)]
    if not isinstance(raw_pending, list) or not raw_pending:
        raise ValueError("active Trial work requires pending assignments")
    return [
        _required_list_object(raw_pending, index, "pending_assignments")
        for index in range(len(raw_pending))
    ]


def _clear_batch_state(payload: dict[str, Any]) -> None:
    """Remove queue-local state before aggregate Evidence Review or reselection."""

    for name in (
        "assignment",
        "pending_assignments",
        "batch_assignment_count",
        "batch_executed_count",
    ):
        payload.pop(name, None)


def _assignment_key(assignment: dict[str, Any]) -> str:
    example_id = _required_string(assignment, "example_id")
    replicate_id = _required_string(assignment, "replicate_id")
    prefix_id = assignment.get("prefix_id")
    if not isinstance(prefix_id, int) or isinstance(prefix_id, bool) or prefix_id < 1:
        raise TypeError("prefix_id must be a positive integer")
    return f"{example_id}/{replicate_id}/{prefix_id}"


def _assignment_key_parts(assignment_key: str) -> tuple[str, str, int]:
    parts = assignment_key.split("/")
    if len(parts) != 3 or any(not part for part in parts):
        raise ValueError(
            "Assignment keys must use example_id/replicate_id/prefix_id format"
        )
    try:
        prefix_id = int(parts[2])
    except ValueError as exc:
        raise ValueError("Assignment key prefix_id must be an integer") from exc
    if prefix_id < 1:
        raise ValueError("Assignment key prefix_id must be positive")
    return parts[0], parts[1], prefix_id


def _non_negative_payload_int(value: dict[str, Any], name: str) -> int:
    item = value.get(name)
    if not isinstance(item, int) or isinstance(item, bool) or item < 0:
        raise TypeError(f"{name} must be a non-negative integer")
    return item


def _optional_non_negative_payload_int(
    value: dict[str, Any],
    name: str,
    default: int,
) -> int:
    if name not in value:
        return default
    return _non_negative_payload_int(value, name)


def _string_list(value: object, name: str) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise TypeError(f"{name} must be a list of non-empty strings")
    return list(value)


def _required_payload_object(
    value: dict[str, Any],
    name: str,
) -> dict[str, Any]:
    return _required_object(value, name)


def _required_string(value: dict[str, Any], name: str) -> str:
    item = value.get(name)
    if not isinstance(item, str) or not item.strip():
        raise TypeError(f"{name} must be a non-empty string")
    return item


def _required_list(value: dict[str, Any], name: str) -> list[Any]:
    item = value.get(name)
    if not isinstance(item, list):
        raise TypeError(f"{name} must be a list")
    return list(item)
