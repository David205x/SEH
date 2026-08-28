"""Localized deterministic transitions between Evolution Controller work items."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from search_harness.evolution.identifiers import (
    make_generation_id,
    make_logical_work_id,
    make_failure_direction_id,
    make_mechanism_scheme_id,
    make_research_attempt_id,
    make_research_scheme_id,
    make_work_id,
)

from .domain import (
    EffectResult,
    EvolutionControlConfig,
    SettlementClass,
    SettlementDraft,
    SettlementScope,
    TrajectoryLineage,
    WorkItem,
    WorkKind,
)
from .policies import evaluate_promotion


_RESEARCH_REF_KEYS = (
    "rollout_file",
    "report_dir",
    "failure_artifact",
    "hypothesis_artifact",
    "candidate_report_dir",
    "candidate_rollout_file",
    "candidate_outcome_digest",
    "candidate_reviewer_artifact",
    "compiler_artifact",
    "mechanism_file",
    "conformance_summary_artifact",
)


@dataclass(frozen=True)
class TransitionPlan:
    """The durable control-plane actions caused by one terminal work item."""

    next_items: tuple[WorkItem, ...] = ()
    complete_reason: str | None = None
    version_advance: tuple[str, int, str] | None = None
    settlements: tuple[SettlementDraft, ...] = ()


def initial_work(*, run_id: str, version_id: str) -> WorkItem:
    """Create the first incumbent evaluation for a new run."""

    generation = 1
    generation_id = make_generation_id(run_id, generation)
    research_attempt = 1
    research_id = make_research_attempt_id(
        generation_id,
        research_attempt,
    )
    work_index = 1
    logical_work_id = make_logical_work_id(
        research_id,
        work_index,
        WorkKind.EVALUATE_INCUMBENT.value,
    )
    return WorkItem(
        work_id=make_work_id(logical_work_id, 1),
        logical_work_id=logical_work_id,
        work_index=work_index,
        kind=WorkKind.EVALUATE_INCUMBENT,
        subject_ref=generation_id,
        lineage=TrajectoryLineage(
            run_id=run_id,
            generation=generation,
            generation_id=generation_id,
            research_attempt=research_attempt,
            research_attempt_id=research_id,
        ),
        payload={
            "version_id": version_id,
        },
    )


def retry_work(item: WorkItem) -> WorkItem:
    """Create one deterministic retry without mutating the original item."""

    return WorkItem(
        work_id=make_work_id(item.logical_work_id, item.attempt + 1),
        logical_work_id=item.logical_work_id,
        work_index=item.work_index,
        kind=item.kind,
        subject_ref=item.subject_ref,
        lineage=item.lineage,
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
        direction_index = int(payload.get("direction_index", 0)) + 1
        payload["direction_index"] = direction_index
        payload["failure_direction_id"] = make_failure_direction_id(
            self.item.lineage.generation_id,
            direction_index,
        )
        payload["research_scheme_index"] = 0
        payload.pop("research_scheme_id", None)
        payload.pop("mechanism_scheme_id", None)
        return self._one(
            WorkKind.RESEARCH_HYPOTHESIS,
            "failure_analyzed",
            refs=refs,
            payload=payload,
        )

    def on_research_hypothesis(self) -> TransitionPlan:
        output = _required_object(self.result.outcome, "output")
        scheme_action = _required_string(output, "scheme_action")
        current_refs = _merge_refs(
            self.item.input_refs,
            self.result.artifact_refs,
        )
        refs = {
            key: current_refs[key]
            for key in _RESEARCH_REF_KEYS
            if key in current_refs
        }
        payload = _context(self.item)
        continuation = payload.get("research_continuation")
        is_continuation = isinstance(continuation, dict)
        if not is_continuation and scheme_action != "start_new":
            raise ValueError(
                "initial Researcher result must start a Research Scheme"
            )
        if scheme_action == "reanalyse_failure":
            return self._new_failure_analysis(
                refs=current_refs,
                payload=payload,
                route="researcher_reanalyse_failure",
            )
        if scheme_action not in {"revise_current", "start_new"}:
            raise ValueError(
                f"unknown Researcher scheme_action: {scheme_action}"
            )
        next_lineage = self._lineage_without_candidate()
        next_work_index: int | None = None
        if scheme_action == "start_new":
            failure_direction_id = _required_string(
                payload,
                "failure_direction_id",
            )
            scheme_index = int(payload.get("research_scheme_index", 0)) + 1
            payload["research_scheme_index"] = scheme_index
            payload["research_scheme_id"] = make_research_scheme_id(
                failure_direction_id,
                scheme_index,
            )
            payload["research_scheme_revision"] = 1
            payload["hypothesis_revision"] = 0
            payload.pop("mechanism_scheme_id", None)
            payload.pop("mechanism_revision", None)
            if is_continuation:
                next_lineage = self._next_research_lineage()
                next_work_index = 1
        else:
            if "research_scheme_id" not in payload:
                raise ValueError(
                    "revise_current requires an existing Research Scheme"
                )
            revision = int(payload.get("research_scheme_revision", 1)) + 1
            payload["research_scheme_revision"] = revision
            payload["hypothesis_revision"] = revision - 1
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
            lineage=next_lineage,
            work_index=next_work_index,
        )

    def on_select_trial(self) -> TransitionPlan:
        status = _required_string(self.result.outcome, "status")
        if status == "exhausted":
            return self._complete_negative(
                "no_matching_trial_prefix",
                "No unused rollout prefix matched the frozen "
                "hypothesis and assignment budget.",
                verdict=status,
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
            return self._complete_negative(
                "sequential_assignment_budget_exhausted",
                "Trial assignment budget was exhausted.",
            )
        if int(payload.get("trial_count", 0)) >= (
            self.config.max_trials_per_hypothesis
        ):
            return self._complete_negative(
                "sequential_trial_budget_exhausted",
                "Per-hypothesis trial budget was exhausted.",
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
            return self._complete_negative(
                "parallel_assignment_budget_exhausted",
                "Trial assignment budget was exhausted.",
            )
        if trial_count >= self.config.max_trials_per_hypothesis:
            return self._complete_negative(
                "parallel_trial_budget_exhausted",
                "Per-hypothesis trial budget was exhausted.",
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
                return self._complete_negative(
                    "evidence_continue_trial_budget_exhausted",
                    "Evidence Reviewer requested another trial after the "
                    "per-hypothesis trial budget was exhausted.",
                    verdict=decision,
                    revision_owner="evidence_reviewer",
                    revision_obligation=_required_string(
                        output,
                        "next_obligation",
                    ),
                )
            if int(payload.get("assignment_count", 0)) >= (
                self.config.max_trial_assignments
            ):
                return self._complete_negative(
                    "evidence_continue_assignment_budget_exhausted",
                    "Evidence Reviewer requested another trial after "
                    "the assignment budget was exhausted.",
                    verdict=decision,
                    revision_owner="evidence_reviewer",
                    revision_obligation=_required_string(
                        output,
                        "next_obligation",
                    ),
                )
            return self._one(
                WorkKind.SELECT_TRIAL,
                "review_continue",
                refs=refs,
                payload=payload,
            )
        if decision in {"revise", "reject"}:
            return self._with_experience(
                self._research_revision(
                    feedback_source="evidence_reviewer",
                    feedback=output,
                    refs=refs,
                    payload=payload,
                ),
                capability_event=f"evidence_reviewer.{decision}",
                direction_event=f"evidence_reviewer.{decision}",
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
            return self._with_experience(
                self._research_revision(
                    feedback_source="mechanism_distiller",
                    feedback=output,
                    refs=refs,
                    payload=payload,
                ),
                direction_event="mechanism_distiller.not_distillable",
            )
        if decision == "needs_evidence":
            if int(payload.get("trial_count", 0)) >= (
                self.config.max_trials_per_hypothesis
            ):
                return self._complete_negative(
                    "distiller_evidence_trial_budget_exhausted",
                    "Mechanism Distiller requested more evidence after "
                    "the trial budget was exhausted.",
                    verdict=decision,
                    revision_owner="mechanism_distiller",
                    revision_obligation=_required_string(
                        output,
                        "next_obligation",
                    ),
                )
            if int(payload.get("assignment_count", 0)) >= (
                self.config.max_trial_assignments
            ):
                return self._complete_negative(
                    "distiller_evidence_assignment_budget_exhausted",
                    "Mechanism Distiller requested more evidence after "
                    "the assignment budget was exhausted.",
                    verdict=decision,
                    revision_owner="mechanism_distiller",
                    revision_obligation=_required_string(
                        output,
                        "next_obligation",
                    ),
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
        payload["effect_goal"] = str(
            self.result.outcome.get("effect_goal", "task_outcome")
        )
        research_scheme_id = _required_string(
            payload,
            "research_scheme_id",
        )
        payload.setdefault(
            "mechanism_scheme_id",
            make_mechanism_scheme_id(research_scheme_id),
        )
        payload["mechanism_scheme_revision"] = (
            int(payload.get("mechanism_revision", 0)) + 1
        )
        if self.result.outcome.get("requires_hook_feasibility") is True:
            return self._one(
                WorkKind.VERIFY_HOOK_FEASIBILITY,
                "mechanism_requires_hook_feasibility",
                refs=refs,
                payload=payload,
            )
        return self._one(
            WorkKind.COMPILE_CANDIDATE,
            "mechanism_distilled",
            refs=refs,
            payload=payload,
        )

    def on_verify_hook_feasibility(self) -> TransitionPlan:
        output = _required_object(self.result.outcome, "output")
        decision = _required_string(output, "decision")
        refs = _merge_refs(self.item.input_refs, self.result.artifact_refs)
        payload = _context(self.item)
        if decision == "feasible":
            raw_guidance = output.get("compiler_guidance", [])
            guidance = _string_list(raw_guidance, "compiler_guidance")
            constraints = list(
                payload.get("implementation_constraints", [])
            )
            constraints.extend(guidance)
            payload["implementation_constraints"] = constraints
            return self._one(
                WorkKind.COMPILE_CANDIDATE,
                "hook_feasibility_supported",
                refs=refs,
                payload=payload,
            )
        feedback = _required_string(output, "revision_feedback")
        if decision == "needs_spec_revision":
            revision = int(payload.get("mechanism_revision", 0)) + 1
            if revision > self.config.max_mechanism_revisions:
                return self._complete_negative(
                    "hook_spec_revision_budget_exhausted",
                    "Hook feasibility requested a specification revision "
                    "after the mechanism revision budget was exhausted.",
                    verdict=decision,
                    revision_owner="mechanism_distiller",
                    revision_obligation=feedback,
                )
            payload["mechanism_revision"] = revision
            constraints = list(payload.get("capability_constraints", []))
            constraints.append(feedback)
            payload["capability_constraints"] = constraints
            refs.pop("hook_feasibility_artifact", None)
            refs.pop("hook_feasibility_probe", None)
            return self._with_experience(
                self._one(
                    WorkKind.DISTILL_MECHANISM,
                    f"hook_spec_revision:{revision}",
                    refs=refs,
                    payload=payload,
                ),
                direction_event="hook_feasibility.needs_spec_revision",
            )
        if decision == "needs_research_revision":
            return self._with_experience(
                self._research_revision(
                    feedback_source="hook_feasibility_reviewer",
                    feedback=output,
                    refs=refs,
                    payload=payload,
                ),
                capability_event=(
                    "hook_feasibility.needs_research_revision"
                ),
                direction_event=(
                    "hook_feasibility.needs_research_revision"
                ),
            )
        raise ValueError(f"unknown Hook feasibility decision: {decision}")

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
                return self._complete_negative(
                    "compiler_evidence_trial_budget_exhausted",
                    "Compiler requested more evidence after the trial "
                    "budget was exhausted.",
                    verdict=decision,
                    revision_owner="compiler",
                    revision_obligation=_required_string(
                        output,
                        "next_obligation",
                    ),
                )
            if int(payload.get("assignment_count", 0)) >= (
                self.config.max_trial_assignments
            ):
                return self._complete_negative(
                    "compiler_evidence_assignment_budget_exhausted",
                    "Compiler requested more evidence after the assignment "
                    "budget was exhausted.",
                    verdict=decision,
                    revision_owner="compiler",
                    revision_obligation=_required_string(
                        output,
                        "next_obligation",
                    ),
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
                return self._complete_negative(
                    "compiler_mechanism_revision_budget_exhausted",
                    "Compiler requested a mechanism revision after the "
                    "configured revision budget was exhausted.",
                    verdict=decision,
                    revision_owner="mechanism_distiller",
                    revision_obligation=_required_string(
                        output,
                        "next_obligation",
                    ),
                )
            payload["mechanism_revision"] = revision
            constraints = list(payload.get("capability_constraints", []))
            constraints.append(
                _required_string(output, "next_obligation")
            )
            payload["capability_constraints"] = constraints
            event = (
                "compiler.needs_mechanism_revision"
                if decision == "needs_mechanism_revision"
                else "compiler.implementation_blocked"
            )
            return self._with_experience(
                self._one(
                    WorkKind.DISTILL_MECHANISM,
                    f"compiler_mechanism_revision:{revision}",
                    refs=refs,
                    payload=payload,
                ),
                direction_event=event,
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
            candidate_attempt_id = _required_string(
                self.result.outcome,
                "candidate_attempt_id",
            )
            candidate_settlement = self._settlement(
                SettlementScope.CANDIDATE_ATTEMPT,
                SettlementClass.SETTLED_NEGATIVE,
                "candidate_validation_failed",
                verdict=status,
                candidate_attempt_id=candidate_attempt_id,
            )
            revision = int(payload.get("compiler_revision", 0)) + 1
            if revision > self.config.max_compiler_revisions:
                validation = self.result.outcome.get("validation")
                errors = (
                    list(validation.get("errors", []))
                    if isinstance(validation, dict)
                    else []
                )
                obligation = (
                    " | ".join(str(error) for error in errors if str(error))
                    or "Candidate validation remained invalid."
                )
                return self._with_settlement(
                    self._complete_negative(
                        "candidate_validation_revision_budget_exhausted",
                        "Candidate validation failed after the Compiler "
                        "revision budget was exhausted.",
                        verdict=status,
                        revision_owner="compiler",
                        revision_obligation=obligation,
                    ),
                    candidate_settlement,
                )
            payload["compiler_revision"] = revision
            feedback = self.result.outcome.get("validation")
            payload["validation_feedback"] = (
                list(feedback.get("errors", []))
                if isinstance(feedback, dict)
                else ["Candidate validation failed."]
            )
            return self._with_settlement(
                self._one(
                    WorkKind.COMPILE_CANDIDATE,
                    f"validation_revision:{revision}",
                    refs=refs,
                    payload=payload,
                ),
                candidate_settlement,
            )
        if status == "unchanged_rejected_candidate":
            candidate_attempt_id = _required_string(
                self.result.outcome,
                "candidate_attempt_id",
            )
            reason = self.result.outcome.get("rejection_reason")
            detail = (
                str(reason).strip()
                if isinstance(reason, str) and reason.strip()
                else "the Compiler resubmitted an unchanged rejected Candidate"
            )
            return self._with_settlement(
                self._research_revision(
                    feedback_source="candidate_validation",
                    feedback={
                        "decision": status,
                        "assessment": detail,
                    },
                    refs=refs,
                    payload=payload,
                ),
                self._settlement(
                    SettlementScope.CANDIDATE_ATTEMPT,
                    SettlementClass.SETTLED_NEGATIVE,
                    "candidate_validation_failed",
                    verdict=status,
                    candidate_attempt_id=candidate_attempt_id,
                ),
            )
        if status != "valid":
            raise ValueError(f"unknown candidate stage status: {status}")
        candidate_attempt_id = _required_string(
            self.result.outcome,
            "candidate_attempt_id",
        )
        payload.update(
            {
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
        lineage = self._lineage_with_candidate(candidate_attempt_id)
        return self._one(
            WorkKind.VERIFY_CONFORMANCE,
            "candidate_valid",
            refs=refs,
            payload=payload,
            lineage=lineage,
        )

    def on_verify_conformance(self) -> TransitionPlan:
        decision = _required_string(self.result.outcome, "decision")
        refs = _merge_refs(self.item.input_refs, self.result.artifact_refs)
        payload = _context(self.item)
        summary = _required_object(self.result.outcome, "summary")
        decision, summary = _apply_effect_goal_to_conformance_summary(
            decision=decision,
            summary=summary,
            effect_goal=_mechanism_effect_goal(payload),
        )
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
        plan = self._one(
            WorkKind.REJECT_CANDIDATE,
            "conformance_failed",
            refs=refs,
            payload=payload,
        )
        if target == "evidence":
            return self._with_experience(
                plan,
                capability_event="conformance.revise",
                direction_event="conformance.revise_evidence",
            )
        if target == "mechanism":
            return self._with_experience(
                plan,
                capability_event="conformance.revise",
                direction_event="conformance.revise_mechanism",
            )
        return plan

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
        raw_digest = self.result.outcome.get("candidate_outcome_digest")
        outcome_digest = raw_digest if isinstance(raw_digest, dict) else None
        hook_activity = (
            outcome_digest.get("hook_activity")
            if outcome_digest is not None
            else None
        )
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
            effect_goal=_mechanism_effect_goal(payload),
            effect_summary=(
                hook_activity if isinstance(hook_activity, dict) else None
            ),
        )
        if outcome_digest is not None:
            payload["candidate_outcome_digest"] = outcome_digest
            mechanism_digest = outcome_digest.get("mechanism")
            if isinstance(mechanism_digest, dict):
                fingerprint = mechanism_digest.get("fingerprint")
                if isinstance(fingerprint, str) and fingerprint:
                    payload["solution_fingerprint"] = fingerprint
        payload["promotion_gate"] = gate.to_dict()
        payload["candidate_review"] = output

        if gate.passed:
            return self._with_experience(
                self._one(
                    WorkKind.PROMOTE_CANDIDATE,
                    "promotion_gate_passed",
                    refs=refs,
                    payload=payload,
                ),
                direction_event="promotion_gate.passed",
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
        plan = self._one(
            WorkKind.REJECT_CANDIDATE,
            f"promotion_gate_failed:{recommendation}",
            refs=refs,
            payload=payload,
        )
        if recommendation == "revise":
            target = _required_string(output, "revision_target")
            if target == "evidence":
                return self._with_experience(
                    plan,
                    direction_event="candidate_reviewer.revise_evidence",
                )
            if target == "mechanism":
                return self._with_experience(
                    plan,
                    direction_event="candidate_reviewer.revise_mechanism",
                )
            return plan
        if recommendation == "reject":
            return self._with_experience(
                plan,
                direction_event="candidate_reviewer.reject",
            )
        return self._with_experience(
            plan,
            direction_event="promotion_gate.failed",
        )

    def on_summarize_capability(self) -> TransitionPlan:
        """Finish an independent Capability Draft side work."""

        return TransitionPlan()

    def on_summarize_direction(self) -> TransitionPlan:
        """Finish an independent Direction Draft side work."""

        return TransitionPlan()

    def on_promote_candidate(self) -> TransitionPlan:
        version_id = _required_string(self.result.outcome, "version_id")
        generation = self.item.lineage.generation
        settlement = self._settlement(
            SettlementScope.CANDIDATE_ATTEMPT,
            SettlementClass.SETTLED_POSITIVE,
            "candidate_promoted",
            verdict=str(self.result.outcome.get("status", "accepted")),
            candidate_attempt_id=self._candidate_attempt_id(),
        )
        if generation >= self.config.max_generations:
            return TransitionPlan(
                complete_reason=(
                    f"Accepted {version_id}; generation budget completed."
                ),
                version_advance=(
                    version_id,
                    generation,
                    self.item.lineage.generation_id,
                ),
                settlements=(settlement,),
            )
        next_generation = generation + 1
        generation_id = make_generation_id(
            self.item.lineage.run_id,
            next_generation,
        )
        research_attempt = 1
        research_id = make_research_attempt_id(
            generation_id,
            research_attempt,
        )
        next_lineage = TrajectoryLineage(
            run_id=self.item.lineage.run_id,
            generation=next_generation,
            generation_id=generation_id,
            research_attempt=research_attempt,
            research_attempt_id=research_id,
        )
        work_index = 1
        logical_work_id = make_logical_work_id(
            research_id,
            work_index,
            WorkKind.EVALUATE_INCUMBENT.value,
        )
        next_item = WorkItem(
            work_id=make_work_id(logical_work_id, 1),
            logical_work_id=logical_work_id,
            work_index=work_index,
            kind=WorkKind.EVALUATE_INCUMBENT,
            subject_ref=generation_id,
            lineage=next_lineage,
            payload={
                "version_id": version_id,
            },
            parent_work_id=self.item.work_id,
        )
        return TransitionPlan(
            next_items=(next_item,),
            version_advance=(version_id, next_generation, generation_id),
            settlements=(settlement,),
        )

    def on_reject_candidate(self) -> TransitionPlan:
        candidate_settlement = self._settlement(
            SettlementScope.CANDIDATE_ATTEMPT,
            SettlementClass.SETTLED_NEGATIVE,
            "candidate_rejected",
            verdict=str(self.result.outcome.get("status", "rejected")),
            candidate_attempt_id=self._candidate_attempt_id(),
        )
        after = self.item.payload.get("after_rejection")
        if not isinstance(after, dict):
            if self.item.payload.get("start_new_research_attempt") is True:
                feedback_source = (
                    "candidate_reviewer"
                    if isinstance(
                        self.item.payload.get("candidate_review"),
                        dict,
                    )
                    and self.item.payload["candidate_review"].get(
                        "recommendation"
                    )
                    == "reject"
                    else "promotion_gate"
                )
                return self._with_settlement(
                    self._research_revision(
                        feedback_source=feedback_source,
                        feedback=_candidate_research_feedback(
                            self.item.payload
                        ),
                        refs=_merge_refs(
                            self.item.input_refs,
                            self.result.artifact_refs,
                        ),
                        payload=_context(self.item),
                    ),
                    candidate_settlement,
                )
            return TransitionPlan(
                complete_reason=(
                    "Candidate was rejected by review or promotion gate."
                ),
                settlements=(candidate_settlement,),
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
                return self._with_settlement(
                    self._complete_negative(
                        "candidate_evidence_trial_budget_exhausted",
                        "Candidate evidence revision was requested after "
                        "the trial budget was exhausted.",
                        verdict="revision_budget_exhausted",
                        revision_owner="evidence_reviewer",
                        revision_obligation=obligation,
                    ),
                    candidate_settlement,
                )
            if int(payload.get("assignment_count", 0)) >= (
                self.config.max_trial_assignments
            ):
                return self._with_settlement(
                    self._complete_negative(
                        "candidate_evidence_assignment_budget_exhausted",
                        "Candidate evidence revision was requested after "
                        "the assignment budget was exhausted.",
                        verdict="revision_budget_exhausted",
                        revision_owner="evidence_reviewer",
                        revision_obligation=obligation,
                    ),
                    candidate_settlement,
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
        return self._with_settlement(
            self._one(
                kind,
                f"candidate_revision:{target}",
                refs=refs,
                payload=payload,
                lineage=self._lineage_without_candidate(),
            ),
            candidate_settlement,
        )

    def _new_failure_analysis(
        self,
        *,
        refs: dict[str, str],
        payload: dict[str, Any],
        route: str,
    ) -> TransitionPlan:
        """Start a new attempt whose Analyst creates a new Failure Direction."""

        next_lineage = self._next_research_lineage()
        next_refs = {
            key: value for key, value in refs.items() if key in _RESEARCH_REF_KEYS
        }
        next_refs.pop("failure_artifact", None)
        next_refs.pop("hypothesis_artifact", None)
        next_payload = {
            key: payload[key]
            for key in (
                "version_id",
                "incumbent_metrics",
                "direction_index",
                "solution_failure_count",
                "analysis_focus",
            )
            if key in payload
        }
        return self._one(
            WorkKind.ANALYZE_FAILURE,
            f"research_attempt:{next_lineage.research_attempt}:{route}",
            refs=next_refs,
            payload=next_payload,
            lineage=next_lineage,
            work_index=1,
        )

    def _next_research_lineage(self) -> TrajectoryLineage:
        """Advance the Research Attempt without changing the Generation."""

        attempt = self.item.lineage.research_attempt + 1
        research_id = make_research_attempt_id(
            self.item.lineage.generation_id,
            attempt,
        )
        return TrajectoryLineage(
            run_id=self.item.lineage.run_id,
            generation=self.item.lineage.generation,
            generation_id=self.item.lineage.generation_id,
            research_attempt=attempt,
            research_attempt_id=research_id,
        )

    def _research_revision(
        self,
        *,
        feedback_source: str,
        feedback: dict[str, Any],
        refs: dict[str, str],
        payload: dict[str, Any],
    ) -> TransitionPlan:
        revision_request = int(
            payload.get("researcher_revision_count", 0)
        ) + 1
        if revision_request > self.config.max_hypothesis_revisions:
            return self._complete_negative(
                "hypothesis_revision_budget_exhausted",
                "Hypothesis revision budget was exhausted before "
                "evidence became distillable.",
                verdict=feedback_source,
                revision_owner="hypothesis_researcher",
                revision_obligation=_revision_obligation(feedback),
            )
        payload["researcher_revision_count"] = revision_request
        payload["research_continuation"] = {
            "feedback_source": feedback_source,
            "feedback": feedback,
        }
        return self._one(
            WorkKind.RESEARCH_HYPOTHESIS,
            f"researcher_revision:{revision_request}",
            refs=refs,
            payload=payload,
        )

    def _lineage_with_candidate(
        self,
        candidate_attempt_id: str,
    ) -> TrajectoryLineage:
        lineage = self.item.lineage
        return TrajectoryLineage(
            run_id=lineage.run_id,
            generation=lineage.generation,
            generation_id=lineage.generation_id,
            research_attempt=lineage.research_attempt,
            research_attempt_id=lineage.research_attempt_id,
            candidate_attempt_id=candidate_attempt_id,
        )

    def _lineage_without_candidate(self) -> TrajectoryLineage:
        lineage = self.item.lineage
        return TrajectoryLineage(
            run_id=lineage.run_id,
            generation=lineage.generation,
            generation_id=lineage.generation_id,
            research_attempt=lineage.research_attempt,
            research_attempt_id=lineage.research_attempt_id,
        )

    def _candidate_attempt_id(self) -> str:
        candidate_attempt_id = self.item.lineage.candidate_attempt_id
        if candidate_attempt_id is None:
            raise ValueError(
                f"{self.item.kind.value} requires candidate_attempt_id"
            )
        return candidate_attempt_id

    def _settlement(
        self,
        scope: SettlementScope,
        classification: SettlementClass,
        terminal_code: str,
        *,
        verdict: str | None = None,
        candidate_attempt_id: str | None = None,
        revision_owner: str | None = None,
        revision_obligation: str | None = None,
    ) -> SettlementDraft:
        return SettlementDraft(
            scope=scope,
            classification=classification,
            terminal_code=terminal_code,
            verdict=verdict or terminal_code,
            candidate_attempt_id=candidate_attempt_id,
            revision_owner=revision_owner,
            revision_obligation=revision_obligation,
        )

    def _complete_negative(
        self,
        terminal_code: str,
        reason: str,
        *,
        verdict: str | None = None,
        revision_owner: str | None = None,
        revision_obligation: str | None = None,
    ) -> TransitionPlan:
        return TransitionPlan(
            complete_reason=reason,
            settlements=(
                self._settlement(
                    SettlementScope.RESEARCH_ATTEMPT,
                    SettlementClass.SETTLED_NEGATIVE,
                    terminal_code,
                    verdict=verdict,
                    revision_owner=revision_owner,
                    revision_obligation=revision_obligation,
                ),
            ),
        )

    def _with_settlement(
        self,
        plan: TransitionPlan,
        settlement: SettlementDraft,
    ) -> TransitionPlan:
        return TransitionPlan(
            next_items=plan.next_items,
            complete_reason=plan.complete_reason,
            version_advance=plan.version_advance,
            settlements=(*plan.settlements, settlement),
        )

    def _with_experience(
        self,
        plan: TransitionPlan,
        *,
        capability_event: str | None = None,
        direction_event: str | None = None,
    ) -> TransitionPlan:
        """Schedule independent Draft passes before the unchanged main route."""

        events = [
            (WorkKind.SUMMARIZE_CAPABILITY, capability_event),
            (WorkKind.SUMMARIZE_DIRECTION, direction_event),
        ]
        selected = [(kind, event) for kind, event in events if event]
        if not selected:
            return plan
        if not plan.next_items or plan.complete_reason is not None:
            # Budget and terminal settlements already close the run. They do
            # not create a resumable agenda boundary for optional Draft work.
            return plan
        if len(plan.next_items) != 1:
            raise ValueError(
                "experience side work requires one resumable next WorkItem"
            )
        main = plan.next_items[0]
        source_refs = _merge_refs(
            self.item.input_refs,
            self.result.artifact_refs,
        )
        source_payload = _context(self.item)
        source_payload["experience_source_kind"] = self.item.kind.value
        source_payload["experience_source_outcome"] = dict(
            self.result.outcome
        )
        side_items: list[WorkItem] = []
        for offset, (kind, event) in enumerate(selected, start=1):
            work_index = self.item.work_index + offset
            logical_work_id = make_logical_work_id(
                self.item.lineage.research_attempt_id,
                work_index,
                kind.value,
            )
            payload = dict(source_payload)
            payload["experience_source_event"] = event
            side_items.append(
                WorkItem(
                    work_id=make_work_id(logical_work_id, 1),
                    logical_work_id=logical_work_id,
                    work_index=work_index,
                    kind=kind,
                    subject_ref=self.item.lineage.generation_id,
                    lineage=self.item.lineage,
                    input_refs=source_refs,
                    payload=payload,
                    parent_work_id=self.item.work_id,
                )
            )
        if (
            main.lineage.research_attempt_id
            == self.item.lineage.research_attempt_id
        ):
            main = _reindex_work_item(
                main,
                work_index=self.item.work_index + len(side_items) + 1,
            )
        return TransitionPlan(
            next_items=(*side_items, main),
            complete_reason=plan.complete_reason,
            version_advance=plan.version_advance,
            settlements=plan.settlements,
        )

    def _one(
        self,
        kind: WorkKind,
        route: str,
        *,
        refs: dict[str, str],
        payload: dict[str, Any],
        lineage: TrajectoryLineage | None = None,
        work_index: int | None = None,
    ) -> TransitionPlan:
        del route
        selected_lineage = lineage or self.item.lineage
        selected_index = work_index or self.item.work_index + 1
        logical_work_id = make_logical_work_id(
            selected_lineage.research_attempt_id,
            selected_index,
            kind.value,
        )
        return TransitionPlan(
            next_items=(
                WorkItem(
                    work_id=make_work_id(logical_work_id, 1),
                    logical_work_id=logical_work_id,
                    work_index=selected_index,
                    kind=kind,
                    subject_ref=selected_lineage.generation_id,
                    lineage=selected_lineage,
                    input_refs=dict(refs),
                    payload=dict(payload),
                    parent_work_id=self.item.work_id,
                ),
            )
        )


def _context(item: WorkItem) -> dict[str, Any]:
    return dict(item.payload)


def _reindex_work_item(item: WorkItem, *, work_index: int) -> WorkItem:
    """Shift one queued WorkItem after inserted side work in the same attempt."""

    logical_work_id = make_logical_work_id(
        item.lineage.research_attempt_id,
        work_index,
        item.kind.value,
    )
    return WorkItem(
        work_id=make_work_id(logical_work_id, 1),
        logical_work_id=logical_work_id,
        work_index=work_index,
        kind=item.kind,
        subject_ref=item.subject_ref,
        lineage=item.lineage,
        input_refs=dict(item.input_refs),
        payload=dict(item.payload),
        parent_work_id=item.parent_work_id,
    )


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


def _candidate_research_feedback(payload: dict[str, Any]) -> dict[str, Any]:
    """Project the final Candidate result for Researcher-first routing."""

    review = payload.get("candidate_review")
    gate = payload.get("promotion_gate")
    digest = payload.get("candidate_outcome_digest")
    return {
        "decision": "candidate_rejected",
        "assessment": _candidate_rejection_reason(payload),
        "candidate_review": dict(review) if isinstance(review, dict) else None,
        "promotion_gate": dict(gate) if isinstance(gate, dict) else None,
        "candidate_outcome_digest": (
            dict(digest) if isinstance(digest, dict) else None
        ),
    }


def _mechanism_effect_goal(payload: dict[str, Any]) -> str:
    value = payload.get("effect_goal", "task_outcome")
    if value not in {"task_outcome", "behavioral_intermediate"}:
        raise ValueError(f"unknown mechanism effect_goal: {value}")
    return str(value)


def _apply_effect_goal_to_conformance_summary(
    *,
    decision: str,
    summary: dict[str, Any],
    effect_goal: str,
) -> tuple[str, dict[str, Any]]:
    """Apply current effect semantics to resumable legacy summaries."""

    if decision != "pass":
        return decision, summary
    efficacy = summary.get("local_efficacy_counts")
    if not isinstance(efficacy, dict):
        return decision, summary
    harmful = int(efficacy.get("harmful", 0) or 0)
    beneficial = int(efficacy.get("beneficial", 0) or 0)
    target = int(summary.get("target_behavior_example_count", 0) or 0)
    blocked = harmful > 0 or (
        effect_goal == "task_outcome" and beneficial < 1
    ) or (
        effect_goal == "behavioral_intermediate" and target < 1
    )
    if not blocked:
        return decision, summary
    updated = dict(summary)
    updated["decision"] = "revise"
    updated["effect_goal"] = effect_goal
    updated["recommended_route"] = "evidence"
    route_feedback = updated.get("route_feedback")
    route_feedback = (
        dict(route_feedback) if isinstance(route_feedback, dict) else {}
    )
    existing = route_feedback.get("evidence")
    messages = list(existing) if isinstance(existing, list) else []
    messages.append(
        "The Conformance replay does not satisfy the declared effect_goal; "
        "re-establish the required local benefit or target behavior before "
        "full Candidate Evaluation."
    )
    route_feedback["evidence"] = messages
    updated["route_feedback"] = route_feedback
    return "revise", updated


def _revision_obligation(feedback: dict[str, Any]) -> str:
    for name in (
        "next_obligation",
        "revision_feedback",
        "assessment",
        "reason",
    ):
        value = feedback.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "The requested research revision remained unresolved."


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
