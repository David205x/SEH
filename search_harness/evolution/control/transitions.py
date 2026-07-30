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
        payload={"generation": 1, "version_id": version_id},
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
        payload["assignment"] = _required_object(
            self.result.outcome,
            "assignment",
        )
        payload["assignment_count"] = int(
            self.result.outcome.get(
                "assignment_count",
                payload.get("assignment_count", 0),
            )
        )
        payload["used_assignments"] = _required_list(
            self.result.outcome,
            "used_assignments",
        )
        return self._one(
            WorkKind.EXECUTE_TRIAL,
            f"assignment:{payload['assignment_count']}",
            refs=self.item.input_refs,
            payload=payload,
        )

    def on_execute_trial(self) -> TransitionPlan:
        output = _required_object(self.result.outcome, "output")
        result_kind = _required_string(output, "result_kind")
        refs = _merge_refs(self.item.input_refs, self.result.artifact_refs)
        payload = _context(self.item)
        if result_kind == "unsuitable_assignment":
            if int(payload.get("assignment_count", 0)) >= (
                self.config.max_trial_assignments
            ):
                return TransitionPlan(
                    complete_reason="Trial assignment budget was exhausted."
                )
            return self._one(
                WorkKind.SELECT_TRIAL,
                "assignment_unsuitable",
                refs=refs,
                payload=payload,
            )
        if result_kind == "unsupported_hypothesis":
            return self._research_revision(
                feedback_source="intervention_worker",
                feedback=output,
                refs=refs,
                payload=payload,
            )
        if result_kind != "executed":
            raise ValueError(f"unknown Intervention Worker result: {result_kind}")

        trial_count = int(payload.get("trial_count", 0)) + 1
        payload["trial_count"] = trial_count
        trial_ref = self.result.artifact_refs.get("worker_artifact")
        if trial_ref is None:
            raise ValueError("executed trial result lacks worker_artifact")
        refs[f"trial_{trial_count:03d}"] = trial_ref
        return self._one(
            WorkKind.REVIEW_EVIDENCE,
            f"trial_executed:{trial_count}",
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
        if decision == "needs_revision":
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
                _required_string(output, "implementation_summary")
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
        if status != "valid":
            raise ValueError(f"unknown candidate stage status: {status}")
        payload.update(
            {
                "iteration_id": _required_string(
                    self.result.outcome,
                    "iteration_id",
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
            WorkKind.EVALUATE_CANDIDATE,
            "candidate_valid",
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
        else:
            payload["after_rejection"] = None
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
            return TransitionPlan(
                complete_reason="Candidate was rejected by review or promotion gate."
            )
        target = _required_string(after, "target")
        obligation = _required_string(after, "obligation")
        refs = _without_prefix(
            self.item.input_refs,
            (
                "candidate_",
                "compiler_artifact",
                "iteration_",
            ),
        )
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


def _required_object(value: dict[str, Any], name: str) -> dict[str, Any]:
    item = value.get(name)
    if not isinstance(item, dict):
        raise TypeError(f"{name} must be an object")
    return dict(item)


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
