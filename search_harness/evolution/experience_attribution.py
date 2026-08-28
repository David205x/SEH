"""Canonical role and routing context for experience attribution."""

from __future__ import annotations

from typing import Iterable, Literal


ExperienceTeacherRoleId = Literal[
    "failure_analyst",
    "hypothesis_researcher",
    "intervention_worker",
    "trial_reviewer",
    "evidence_reviewer",
    "mechanism_distiller",
    "hook_feasibility_reviewer",
    "compiler",
    "conformance_reviewer",
    "candidate_reviewer",
    "capability_summarizer",
    "direction_summarizer",
]


ROLE_RESPONSIBILITIES: dict[str, str] = {
    "failure_analyst": (
        "Select one evidence-backed failure direction from Task Evaluation."
    ),
    "hypothesis_researcher": (
        "Propose or revise a causal intervention hypothesis, its success "
        "conditions, and trial obligations."
    ),
    "intervention_worker": (
        "Faithfully apply the approved soft intervention to a frozen "
        "trajectory prefix without inventing a deployable Candidate."
    ),
    "trial_reviewer": (
        "Judge one Intervention Trial against its declared predicates and "
        "record phase-local observations."
    ),
    "evidence_reviewer": (
        "Aggregate Trial Reviews and decide whether evidence supports more "
        "trials, hypothesis revision, rejection, or distillation."
    ),
    "mechanism_distiller": (
        "Convert reviewed evidence into guards, a three-way decision contract, "
        "runtime inputs, and fallback semantics."
    ),
    "hook_feasibility_reviewer": (
        "Judge whether the frozen Hook model can realize the distilled "
        "decision boundary and route specification versus research revision."
    ),
    "compiler": (
        "Implement the frozen Mechanism Spec in the Candidate without "
        "redefining its semantic boundary."
    ),
    "conformance_reviewer": (
        "Judge whether Candidate Student rollouts faithfully implement the "
        "Mechanism Spec and whether local effects are harmful."
    ),
    "candidate_reviewer": (
        "Combine validation, conformance, evaluation, attribution, and cost "
        "evidence into a Candidate recommendation."
    ),
    "capability_summarizer": (
        "Convert eligible direct model-behavior evidence into Capability "
        "Drafts without proposing a repair or settling them."
    ),
    "direction_summarizer": (
        "Convert eligible research outcomes into one bounded Direction Draft "
        "without controlling workflow routing or settlement."
    ),
}


DETERMINISTIC_RESPONSIBILITIES: dict[str, str] = {
    "trial_selector": (
        "Select bounded assignments using the frozen deterministic selection "
        "policy; it does not interpret natural-language obligations."
    ),
    "candidate_validation": (
        "Validate Candidate structure and declared files before conformance; "
        "it does not judge research utility."
    ),
    "evolution_controller": (
        "Persist effects, enforce budgets and retries, and apply deterministic "
        "TransitionPlan routing."
    ),
    "promotion_gate": (
        "Apply frozen deterministic acceptance and cost thresholds after "
        "Candidate Review."
    ),
    "student_or_hook_model": (
        "Produce the observed task or three-way decision behavior; repeated "
        "valid behavior may establish a capability boundary."
    ),
}


WORK_KIND_TEACHER_ROLE: dict[str, ExperienceTeacherRoleId] = {
    "analyze_failure": "failure_analyst",
    "research_hypothesis": "hypothesis_researcher",
    "execute_trial": "intervention_worker",
    "review_evidence": "evidence_reviewer",
    "distill_mechanism": "mechanism_distiller",
    "verify_hook_feasibility": "hook_feasibility_reviewer",
    "compile_candidate": "compiler",
    "verify_conformance": "conformance_reviewer",
    "review_candidate": "candidate_reviewer",
    "summarize_capability": "capability_summarizer",
    "summarize_direction": "direction_summarizer",
}


REVISION_FAMILIES: dict[str, str] = {
    "evidence_reviewer.revise_or_reject": (
        "Returns to hypothesis research while the decision role remains an "
        "observer, not the presumed cause."
    ),
    "mechanism_distiller.needs_evidence": (
        "Returns to deterministic trial selection when budget remains; budget "
        "exhaustion is terminal."
    ),
    "hook_feasibility.needs_spec_revision": (
        "Returns operation or runtime-input ambiguity to mechanism distillation."
    ),
    "hook_feasibility.needs_research_revision": (
        "Returns model-boundary or evidence-scope revision to hypothesis research."
    ),
    "compiler.needs_evidence": (
        "Returns to deterministic trial selection when budget remains."
    ),
    "compiler.needs_mechanism_revision_or_blocked": (
        "Returns a frozen-spec or implementation-boundary problem to distillation."
    ),
    "candidate_validation.validation_failed": (
        "Returns to compilation only while its revision budget remains."
    ),
    "candidate_validation.unchanged_rejected_candidate": (
        "Starts a new research attempt rather than returning to the Compiler."
    ),
    "conformance.revise": (
        "Routes by the typed evidence, mechanism, or implementation failure layer."
    ),
    "candidate_reviewer.revise": (
        "Routes by the typed evidence, mechanism, or implementation target."
    ),
    "candidate_reviewer.reject_or_promotion_gate.failed": (
        "Settles the Candidate attempt and returns the outcome to Researcher "
        "before any Failure Direction reanalysis."
    ),
}


EXPERIENCE_CONSUMERS: dict[str, str] = {
    "student_capability": "hypothesis_researcher",
    "experiment_direction": "hypothesis_researcher",
    "teacher_work": "the exact teacher_role_id carried by the draft",
}


def derive_route_target_role(
    next_work_kinds: Iterable[str],
) -> ExperienceTeacherRoleId | None:
    """Return one actual next Teacher role, never a guessed repair owner."""

    roles = {
        WORK_KIND_TEACHER_ROLE[kind]
        for kind in next_work_kinds
        if kind in WORK_KIND_TEACHER_ROLE
    }
    if len(roles) != 1:
        return None
    return next(iter(roles))


def global_attribution_context() -> dict[str, object]:
    """Return the compact, stable context shared by all Summary runs."""

    return {
        "experience_priority": [
            "student_capability",
            "experiment_direction",
            "teacher_work",
        ],
        "roles": dict(ROLE_RESPONSIBILITIES),
        "deterministic_mechanisms": dict(DETERMINISTIC_RESPONSIBILITIES),
        "revision_families": dict(REVISION_FAMILIES),
        "experience_consumers": dict(EXPERIENCE_CONSUMERS),
        "identity_rule": (
            "trigger decision role reports the outcome; actual route target is "
            "the next Teacher role; causal owner must be established by evidence"
        ),
    }
