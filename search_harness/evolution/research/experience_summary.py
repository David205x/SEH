"""Deterministic Experience Observation Packets and Detail projection."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .roles.contracts import (
    CapabilityExperienceProduct,
    CapabilityExperienceProductItem,
    CapabilityExperienceSummary,
    CapabilityObservation,
    CapabilitySummarizerInput,
    DirectionLayer,
    DirectionSummarizerInput,
    DirectionSummary,
    DirectionUpdateTarget,
    ExperienceDetailCoverage,
    ExperienceDetailDirectoryEntry,
    ExperienceObservation,
    ExperienceValidity,
    ResearchDirectionContext,
)


MAX_DETAIL_TOOL_CALLS = 20


class ExperienceDetail(BaseModel):
    """Program-only content behind one model-visible Detail directory entry."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    detail_id: int = Field(ge=1)
    observation_id: int = Field(ge=1)
    resolves: str = Field(min_length=1, max_length=120)
    coverage: ExperienceDetailCoverage
    description: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1)
    source_refs: list[str] = Field(default_factory=list)

    def directory_entry(self) -> ExperienceDetailDirectoryEntry:
        """Project the model-visible directory entry without Detail content."""

        return ExperienceDetailDirectoryEntry(
            detail_id=self.detail_id,
            observation_id=self.observation_id,
            resolves=self.resolves,
            coverage=self.coverage,
            description=self.description,
        )


class CapabilityEvidenceRecord(BaseModel):
    """Program-only expected and observed decisions for one Observation."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    expected_decision: str = Field(min_length=1, max_length=80)
    observed_by_condition: dict[str, list[str]] = Field(min_length=1)


class ExperienceSummaryResourceConfig(BaseModel):
    """One Pass's fixed source context and authorized Detail registry."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_processing_context: str = Field(min_length=1, max_length=1800)
    details: list[ExperienceDetail] = Field(default_factory=list)
    observation_sources: dict[int, list[str]] = Field(default_factory=dict)
    capability_evidence: dict[int, CapabilityEvidenceRecord] = Field(
        default_factory=dict
    )

    @model_validator(mode="after")
    def validate_registry(self) -> "ExperienceSummaryResourceConfig":
        detail_ids = [item.detail_id for item in self.details]
        if len(detail_ids) != len(set(detail_ids)):
            raise ValueError("experience Detail registry IDs must be unique")
        for observation_id, record in self.capability_evidence.items():
            if observation_id < 1:
                raise ValueError("Capability evidence IDs must be positive")
            if any(not values for values in record.observed_by_condition.values()):
                raise ValueError(
                    "Capability evidence conditions cannot be empty"
                )
        return self


@dataclass(frozen=True)
class ExperienceSummaryRequest:
    """Validated model input paired with its program-only Detail registry."""

    role_input: CapabilitySummarizerInput | DirectionSummarizerInput
    resources: ExperienceSummaryResourceConfig


@dataclass
class ExperienceDetailStore:
    """Read each authorized deterministic Detail projection at most once."""

    config: ExperienceSummaryResourceConfig
    _role_input: CapabilitySummarizerInput | DirectionSummarizerInput | None = (
        field(default=None, init=False, repr=False)
    )
    _read_detail_ids: set[int] = field(default_factory=set, init=False)
    call_count: int = field(default=0, init=False)

    def bind(
        self,
        role_input: CapabilitySummarizerInput | DirectionSummarizerInput,
    ) -> None:
        """Require the Packet directory to match the authorized registry."""

        expected = [item.directory_entry() for item in self.config.details]
        if role_input.detail_directory != expected:
            raise ValueError(
                "experience Packet Detail directory does not match registry"
            )
        observation_ids = {
            item.observation_id for item in role_input.observations
        }
        unknown_sources = set(self.config.observation_sources) - observation_ids
        if unknown_sources:
            raise ValueError(
                "experience source map references unknown observations: "
                f"{sorted(unknown_sources)}"
            )
        unknown_evidence = set(self.config.capability_evidence) - observation_ids
        if unknown_evidence:
            raise ValueError(
                "Capability evidence references unknown observations: "
                f"{sorted(unknown_evidence)}"
            )
        self._role_input = role_input

    def model_context(self) -> dict[str, Any]:
        """Expose only source semantics already relevant to model decisions."""

        if self._role_input is None:
            raise RuntimeError("experience Detail store is not bound")
        return {
            "source_processing_context": self.config.source_processing_context,
        }

    def inspect(self, detail_id: int) -> str:
        """Render one authorized Detail with a compact fixed header."""

        self.call_count += 1
        if self.call_count > MAX_DETAIL_TOOL_CALLS:
            raise ValueError(
                "experience Detail invocation limit exceeded: "
                f"used={self.call_count}, limit={MAX_DETAIL_TOOL_CALLS}"
            )
        if self._role_input is None:
            raise RuntimeError("experience Detail store is not bound")
        if detail_id in self._read_detail_ids:
            raise ValueError(f"experience Detail {detail_id} was already read")
        by_id = {item.detail_id: item for item in self.config.details}
        detail = by_id.get(detail_id)
        if detail is None:
            raise ValueError(
                f"unknown experience Detail {detail_id}; available: "
                f"{sorted(by_id)}"
            )
        self._read_detail_ids.add(detail_id)
        return (
            f"Detail {detail.detail_id}\n"
            f"Observation: {detail.observation_id}\n"
            f"Resolves: {detail.resolves}\n"
            f"Coverage: {detail.coverage}\n\n"
            f"{detail.content}"
        )

    def validate_capability_output(
        self,
        output: CapabilityExperienceSummary,
    ) -> None:
        """Bind every Capability Proposal to current Packet observations."""

        self._validate_refs(
            ref
            for item in output.items
            for ref in item.evidence_refs
        )

    def validate_direction_output(self, output: DirectionSummary) -> None:
        """Bind the optional Direction Draft to current Packet observations."""

        self._validate_refs(
            ref
            for item in output.items
            for ref in item.evidence_refs
        )

    def artifacts(self) -> dict[str, Any]:
        """Persist source provenance without duplicating Detail contents."""

        return {
            "experience_observation_sources": {
                str(key): list(value)
                for key, value in self.config.observation_sources.items()
            },
            "experience_details_read": sorted(self._read_detail_ids),
        }

    def _validate_refs(self, refs: Any) -> None:
        if self._role_input is None:
            raise RuntimeError("experience Detail store is not bound")
        allowed = {
            item.observation_id for item in self._role_input.observations
        }
        unknown = set(refs) - allowed
        if unknown:
            raise ValueError(
                "experience output references unknown observations: "
                f"{sorted(unknown)}"
            )


def make_capability_request(
    *,
    observations: list[CapabilityObservation],
    details: list[ExperienceDetail],
    source_processing_context: str,
    observation_sources: dict[int, list[str]],
    capability_evidence: dict[int, CapabilityEvidenceRecord],
) -> ExperienceSummaryRequest:
    """Assemble one validated Capability Packet and Detail registry."""

    role_input = CapabilitySummarizerInput(
        observations=observations,
        detail_directory=[item.directory_entry() for item in details],
    )
    resources = ExperienceSummaryResourceConfig(
        source_processing_context=source_processing_context,
        details=details,
        observation_sources=observation_sources,
        capability_evidence=capability_evidence,
    )
    ExperienceDetailStore(resources).bind(role_input)
    return ExperienceSummaryRequest(role_input=role_input, resources=resources)


def materialize_capability_experience_product(
    request: ExperienceSummaryRequest,
    summary: CapabilityExperienceSummary,
) -> CapabilityExperienceProduct:
    """Resolve one model Proposal into a program-owned Capability Product."""

    role_input = request.role_input
    if not isinstance(role_input, CapabilitySummarizerInput):
        raise TypeError("Capability Product requires Capability input")
    observations = {
        item.observation_id: item for item in role_input.observations
    }
    items: list[CapabilityExperienceProductItem] = []
    for proposal in summary.items:
        selected = [observations[ref] for ref in proposal.evidence_refs]
        scopes = {item.decision_scope for item in selected}
        if len(scopes) != 1:
            raise ValueError(
                "one Capability Proposal must reference one decision scope"
            )
        source_refs: list[str] = []
        for ref in proposal.evidence_refs:
            for source in request.resources.observation_sources.get(ref, []):
                if source not in source_refs:
                    source_refs.append(source)
        if not source_refs:
            raise ValueError(
                "Capability Proposal has no stable source evidence refs"
            )
        items.append(
            CapabilityExperienceProductItem(
                decision_scope=next(iter(scopes)),
                observed_limitation=proposal.observed_limitation,
                evidence_summary=_capability_evidence_summary(
                    proposal.evidence_refs,
                    request.resources.capability_evidence,
                ),
                evidence_refs=source_refs,
            )
        )
    return CapabilityExperienceProduct(items=items)


def make_direction_request(
    *,
    direction_context: ResearchDirectionContext,
    observations: list[ExperienceObservation],
    details: list[ExperienceDetail],
    source_processing_context: str,
    observation_sources: dict[int, list[str]],
) -> ExperienceSummaryRequest:
    """Assemble one validated Direction Packet and Detail registry."""

    role_input = DirectionSummarizerInput(
        observations=observations,
        detail_directory=[item.directory_entry() for item in details],
        direction_context=direction_context,
    )
    resources = ExperienceSummaryResourceConfig(
        source_processing_context=source_processing_context,
        details=details,
        observation_sources=observation_sources,
    )
    ExperienceDetailStore(resources).bind(role_input)
    return ExperienceSummaryRequest(role_input=role_input, resources=resources)


def build_hook_feasibility_capability_request(
    probe: dict[str, Any],
    *,
    source_ref: str,
) -> ExperienceSummaryRequest | None:
    """Project repeated Hook-model decisions into a Capability Packet."""

    phase_probes = probe.get("phase_probes")
    if not isinstance(phase_probes, list):
        raise TypeError("Hook feasibility probe lacks phase_probes")
    observations: list[CapabilityObservation] = []
    details: list[ExperienceDetail] = []
    sources: dict[int, list[str]] = {}
    capability_evidence: dict[int, CapabilityEvidenceRecord] = {}
    for phase_probe in phase_probes:
        if not isinstance(phase_probe, dict):
            raise TypeError("Hook feasibility phase probe must be an object")
        experiment = phase_probe.get("experiment")
        references = phase_probe.get("case_references")
        if not isinstance(experiment, dict) or not isinstance(references, list):
            raise TypeError(
                "Hook feasibility phase probe lacks experiment or references"
            )
        results = experiment.get("observations")
        if not isinstance(results, list):
            raise TypeError("Hook feasibility experiment lacks results")
        references_by_id = {
            str(item.get("case_id")): item
            for item in references
            if isinstance(item, dict)
            and isinstance(item.get("case_id"), str)
        }
        expected = {
            case_id: str(item.get("expected_label"))
            for case_id, item in references_by_id.items()
        }
        rows: list[tuple[str, str, int, str]] = []
        for result in results:
            if not isinstance(result, dict):
                continue
            case_id = str(result.get("case_id", ""))
            mode = str(result.get("thinking_mode", ""))
            repetition = result.get("repetition")
            observed = str(result.get("raw_output", "")).strip().lower()
            if case_id not in expected or not isinstance(repetition, int):
                continue
            rows.append((case_id, mode, repetition, observed))
        by_condition: dict[tuple[str, str], list[str]] = {}
        for case_id, mode, _, observed in rows:
            by_condition.setdefault((case_id, mode), []).append(observed)
        phase = str(phase_probe.get("phase", "unknown"))
        contract = phase_probe.get("decision_contract")
        decision_scope = _hook_decision_scope(phase_probe)
        case_inputs = {
            str(item.get("case_id")): str(item.get("user_prompt"))
            for item in experiment.get("cases", [])
            if isinstance(item, dict)
            and isinstance(item.get("case_id"), str)
            and isinstance(item.get("user_prompt"), str)
        }
        for case_id, reference in references_by_id.items():
            conditions = {
                mode: values
                for (condition_case, mode), values in by_condition.items()
                if condition_case == case_id
            }
            if not conditions or not any(
                len(set(values)) > 1
                or any(value != expected[case_id] for value in values)
                for values in conditions.values()
            ):
                continue
            observation_id = len(observations) + 1
            decisive = str(
                reference.get("decisive_observation", "not recorded")
            )
            observed_text = "; ".join(
                f"thinking={mode}: {','.join(values)}"
                for mode, values in sorted(conditions.items())
            )
            case_rows = [row for row in rows if row[0] == case_id]
            matched = sum(
                value == expected[case_id]
                for _, _, _, value in case_rows
            )
            observations.append(
                CapabilityObservation(
                    observation_id=observation_id,
                    decision_scope=decision_scope,
                    subject=(
                        "Hook model decision on one reviewed real-prefix "
                        f"case at {phase}"
                    ),
                    expected=(
                        f"Reference label={expected[case_id]}. Decisive "
                        f"observation: {decisive}"
                    ),
                    observed=observed_text,
                    comparison=(
                        "The same model-visible input was repeated within "
                        "each thinking mode; thinking modes are separate "
                        "conditions."
                    ),
                    conditions=(
                        f"phase={phase}; repetitions="
                        f"{probe.get('repetitions', 'unknown')}; "
                        f"thinking_modes={','.join(sorted(conditions))}"
                    ),
                    validity=ExperienceValidity(
                        reference="confirmed",
                        model_input="confirmed",
                        implementation_fidelity="confirmed",
                        data_environment="not_applicable",
                    ),
                    evidence_structure=(
                        f"{len(case_rows)} direct decisions on one fixed "
                        f"real prefix; {matched}/{len(case_rows)} matched "
                        "the reviewed reference."
                    ),
                    open_checks=[],
                )
            )
            stable_ref = _scoped_source_ref(source_ref, case_id)
            details.append(
                ExperienceDetail(
                    detail_id=len(details) + 1,
                    observation_id=observation_id,
                    resolves="decision_contract_and_case_validity",
                    coverage="complete",
                    description=(
                        "Frozen label rules and the decisive reviewed "
                        "observation for this case."
                    ),
                    content=_render_hook_contract(contract, [reference]),
                    source_refs=[stable_ref],
                )
            )
            details.append(
                ExperienceDetail(
                    detail_id=len(details) + 1,
                    observation_id=observation_id,
                    resolves="repeated_model_decisions",
                    coverage="complete",
                    description=(
                        "Expected and observed labels by thinking mode and "
                        "repetition for this case."
                    ),
                    content=_render_hook_rows(expected, case_rows),
                    source_refs=[stable_ref],
                )
            )
            if case_id in case_inputs:
                details.append(
                    ExperienceDetail(
                        detail_id=len(details) + 1,
                        observation_id=observation_id,
                        resolves="exact_model_visible_hook_input",
                        coverage="complete",
                        description=(
                            "Exact user input sent to the Hook model for "
                            "this real-prefix case."
                        ),
                        content=case_inputs[case_id],
                        source_refs=[stable_ref],
                    )
                )
            sources[observation_id] = [stable_ref]
            capability_evidence[observation_id] = CapabilityEvidenceRecord(
                expected_decision=expected[case_id],
                observed_by_condition=conditions,
            )
    if not observations:
        return None
    return make_capability_request(
        observations=observations,
        details=details,
        source_processing_context=(
            "A Hook Feasibility probe has already executed the frozen semantic "
            "decision contract on real Student prefixes. The program preserved "
            "the exact model-visible input, expected label, thinking mode, and "
            "repeated observed label. This source establishes direct Hook-model "
            "decisions, but it does not by itself establish downstream task utility."
        ),
        observation_sources=sources,
        capability_evidence=capability_evidence,
    )


def build_conformance_capability_request(
    findings: list[dict[str, Any]],
    *,
    source_refs: list[str],
    mechanism: dict[str, Any] | None = None,
) -> ExperienceSummaryRequest | None:
    """Project repeated direct evaluator mismatches from Conformance."""

    grouped: dict[str, list[dict[str, Any]]] = {}
    for finding in findings:
        if (
            finding.get("failure_layer") != "evaluator"
            or finding.get("observed_label") == "parse_error"
            or not isinstance(finding.get("predicate_ref"), str)
            or not isinstance(finding.get("expected_label"), str)
            or not isinstance(finding.get("observed_label"), str)
        ):
            continue
        grouped.setdefault(str(finding["predicate_ref"]), []).append(finding)
    eligible = {
        predicate: items
        for predicate, items in grouped.items()
        if len(items) >= 2
    }
    if not eligible:
        return None
    observations: list[CapabilityObservation] = []
    details: list[ExperienceDetail] = []
    sources: dict[int, list[str]] = {}
    capability_evidence: dict[int, CapabilityEvidenceRecord] = {}
    for predicate, items in sorted(eligible.items()):
        examples = {
            str(item.get("example_id") or item.get("candidate_run_ref") or "unknown")
            for item in items
        }
        decision_scope = _conformance_decision_scope(
            predicate,
            mechanism,
        )
        for index, item in enumerate(items, start=1):
            observation_id = len(observations) + 1
            decisive = str(
                item.get("decisive_input_summary", "not recorded")
            )
            observations.append(
                CapabilityObservation(
                    observation_id=observation_id,
                    decision_scope=decision_scope,
                    subject=(
                        "Hook model decision on one direct Candidate "
                        "conformance replay"
                    ),
                    expected=(
                        f"Reference label={item['expected_label']}. "
                        f"Decisive input: {decisive}"
                    ),
                    observed=f"Observed label={item['observed_label']}",
                    comparison=(
                        "This Finding compares one frozen expected label with "
                        "the Candidate Hook-model label on a direct replay."
                    ),
                    conditions=(
                        "Candidate conformance replay; parsing succeeded; "
                        f"predicate_ref={predicate}."
                    ),
                    validity=ExperienceValidity(
                        reference="confirmed",
                        model_input="confirmed",
                        implementation_fidelity="confirmed",
                        data_environment="confirmed",
                    ),
                    evidence_structure=(
                        f"One direct mismatch in a group of {len(items)} "
                        f"mismatches across {len(examples)} recorded replay "
                        "examples for the same predicate."
                    ),
                    open_checks=[],
                )
            )
            replicate = str(item.get("replicate_id", index))
            stable_refs = [
                _scoped_source_ref(
                    source,
                    f"{predicate}/{replicate}",
                )
                for source in source_refs
            ]
            details.append(
                ExperienceDetail(
                    detail_id=len(details) + 1,
                    observation_id=observation_id,
                    resolves="direct_evaluator_mismatch",
                    coverage="complete",
                    description=(
                        "Expected/observed labels and decisive input for this "
                        "non-parse evaluator mismatch."
                    ),
                    content=(
                        "Expected | Observed | Decisive input\n"
                        "--- | --- | ---\n"
                        f"{item['expected_label']} | "
                        f"{item['observed_label']} | {decisive}"
                    ),
                    source_refs=stable_refs,
                )
            )
            sources[observation_id] = stable_refs
            capability_evidence[observation_id] = CapabilityEvidenceRecord(
                expected_decision=str(item["expected_label"]),
                observed_by_condition={
                    "candidate conformance replay": [
                        str(item["observed_label"])
                    ]
                },
            )
    return make_capability_request(
        observations=observations,
        details=details,
        source_processing_context=(
            "A statically valid Candidate completed full Hook lifecycle and "
            "pipeline smoke before semantic conformance replay. The listed "
            "Findings are repeated direct expected-versus-observed evaluator "
            "labels with successful parsing. They can establish a bounded "
            "Hook-model behavior boundary, but not downstream task utility."
        ),
        observation_sources=sources,
        capability_evidence=capability_evidence,
    )


def build_promotion_direction_request(
    *,
    failure_direction_id: str,
    failure_summary: str,
    research_scheme_id: str,
    research_summary: str,
    mechanism_scheme_id: str,
    mechanism_summary: str,
    mechanism_goal: str,
    candidate_review: dict[str, Any],
    promotion_gate: dict[str, Any],
    source_refs: list[str],
) -> ExperienceSummaryRequest:
    """Project one final Candidate/Gate result into a Mechanism Direction Packet."""

    passed = promotion_gate.get("passed")
    if not isinstance(passed, bool):
        raise TypeError("Promotion Gate result lacks boolean passed")
    recommendation = str(candidate_review.get("recommendation", "unknown"))
    observed_effect = str(candidate_review.get("observed_effect", "unknown"))
    reasons = promotion_gate.get("reasons", [])
    reason_text = "; ".join(str(item) for item in reasons) or "none recorded"
    observation = ExperienceObservation(
        observation_id=1,
        subject="Candidate implementation of the current Mechanism Scheme",
        expected=mechanism_goal,
        observed=(
            f"Candidate Reviewer recommendation={recommendation}; "
            f"Promotion Gate passed={str(passed).lower()}; {observed_effect}"
        )[:800],
        comparison=(
            "Incumbent and Candidate were evaluated under the paired Candidate "
            "review protocol; the deterministic Promotion Gate then applied "
            "configured effect, safety, and cost thresholds."
        ),
        conditions="Current Candidate workspace and its recorded evaluation run.",
        validity=ExperienceValidity(
            reference="confirmed",
            model_input="not_applicable",
            implementation_fidelity="confirmed",
            data_environment="confirmed",
        ),
        evidence_structure=(
            "One complete Candidate evaluation, Candidate Review, and final "
            "deterministic Promotion Gate decision."
        ),
        open_checks=[],
    )
    detail = ExperienceDetail(
        detail_id=1,
        observation_id=1,
        resolves="candidate_effect_and_gate_basis",
        coverage="complete",
        description=(
            "Candidate Review effect assessment and deterministic gate reasons."
        ),
        content=(
            f"Reviewer recommendation: {recommendation}\n"
            f"Observed effect: {observed_effect}\n"
            f"Reviewer reason: {candidate_review.get('reason', 'not provided')}\n"
            f"Gate passed: {str(passed).lower()}\n"
            f"Gate reasons: {reason_text}"
        ),
        source_refs=source_refs,
    )
    return make_direction_request(
        direction_context=ResearchDirectionContext(
            failure_direction=DirectionLayer(
                ref=failure_direction_id,
                summary=failure_summary,
            ),
            research_scheme=DirectionLayer(
                ref=research_scheme_id,
                summary=research_summary,
            ),
            mechanism_scheme=DirectionLayer(
                ref=mechanism_scheme_id,
                summary=mechanism_summary,
            ),
            update_target="mechanism_scheme",
        ),
        observations=[observation],
        details=[detail],
        source_processing_context=(
            "The Candidate has completed static validation, semantic "
            "conformance review, full Candidate evaluation, Candidate Review, "
            "and the deterministic Promotion Gate. The review describes effect "
            "and attribution; the gate records whether configured promotion "
            "requirements passed. This source updates the current Mechanism "
            "Scheme, not the existence of the upstream Failure Direction."
        ),
        observation_sources={1: source_refs},
    )


def build_workflow_direction_request(
    *,
    source_event: str,
    failure_direction_id: str,
    failure_summary: str,
    research_scheme_id: str,
    research_summary: str,
    mechanism_scheme_id: str | None,
    mechanism_summary: str | None,
    expected: str,
    source_output: dict[str, Any],
    source_refs: list[str],
) -> ExperienceSummaryRequest:
    """Project one typed negative workflow result into a Direction Packet."""

    target = _direction_target(source_event)
    mechanism_layer = (
        DirectionLayer(
            ref=mechanism_scheme_id,
            summary=mechanism_summary or "Current Mechanism Scheme.",
        )
        if mechanism_scheme_id is not None
        else None
    )
    observed = _direction_observed(source_output)
    observation = ExperienceObservation(
        observation_id=1,
        subject=f"Current {target.replace('_', ' ').title()}",
        expected=expected,
        observed=observed,
        comparison=(
            "The typed decision compares the frozen expectation with direct "
            "Trial, feasibility, compilation, conformance, or Candidate evidence."
        ),
        conditions="The current Research Direction and the source's tested scope.",
        validity=ExperienceValidity(
            reference="confirmed",
            model_input=(
                "confirmed"
                if source_event.startswith("hook_feasibility.")
                else "not_applicable"
            ),
            implementation_fidelity=(
                "confirmed"
                if not source_event.startswith("compiler.")
                else "unknown"
            ),
            data_environment="confirmed",
        ),
        evidence_structure=(
            "One completed typed source decision with its direct assessment, "
            "route obligation, and attached evidence artifacts."
        ),
        open_checks=[],
    )
    detail = ExperienceDetail(
        detail_id=1,
        observation_id=1,
        resolves="typed_decision_basis",
        coverage="complete",
        description="Typed source decision, assessment, and revision obligation.",
        content=json.dumps(
            source_output,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        source_refs=source_refs,
    )
    context = ResearchDirectionContext(
        failure_direction=DirectionLayer(
            ref=failure_direction_id,
            summary=failure_summary,
        ),
        research_scheme=DirectionLayer(
            ref=research_scheme_id,
            summary=research_summary,
        ),
        mechanism_scheme=mechanism_layer,
        update_target=target,
    )
    return make_direction_request(
        direction_context=context,
        observations=[observation],
        details=[detail],
        source_processing_context=_direction_source_context(source_event),
        observation_sources={1: source_refs},
    )


def _hook_decision_scope(phase_probe: dict[str, Any]) -> str:
    """Return the frozen predicate verbatim as the tested decision scope."""

    contract = phase_probe.get("decision_contract")
    if not isinstance(contract, dict):
        raise TypeError("Hook feasibility phase lacks decision_contract")
    predicate = contract.get("predicate")
    if not isinstance(predicate, str) or not predicate.strip():
        raise TypeError("Hook feasibility decision contract lacks predicate")
    return predicate


def _conformance_decision_scope(
    predicate_ref: str,
    mechanism: dict[str, Any] | None,
) -> str:
    """Copy the referenced frozen predicate without synthesizing new prose."""

    if mechanism is not None and predicate_ref.endswith(
        ".decision_contract.predicate"
    ):
        phase = predicate_ref.split(".", maxsplit=1)[0]
        rules = mechanism.get("phase_rules")
        if not isinstance(rules, list):
            raise TypeError("Conformance Mechanism lacks phase_rules")
        rule = next(
            (
                item
                for item in rules
                if isinstance(item, dict) and item.get("phase") == phase
            ),
            None,
        )
        if not isinstance(rule, dict):
            raise ValueError(
                f"Conformance predicate phase is absent: {phase}"
            )
        contract = rule.get("decision_contract")
        if not isinstance(contract, dict):
            raise TypeError("Conformance Mechanism phase rule is incomplete")
        predicate = contract.get("predicate")
        if not isinstance(predicate, str) or not predicate.strip():
            raise TypeError("Conformance Mechanism predicate is missing")
        return predicate
    if " / negative_rule " in predicate_ref and ": " in predicate_ref:
        return predicate_ref.split(": ", maxsplit=1)[1]
    return predicate_ref


def _scoped_source_ref(source_ref: str, scope: str) -> str:
    """Bind one stable source Artifact ref to a case or replay scope."""

    return f"{source_ref}#{scope}"


def _capability_evidence_summary(
    observation_ids: list[int],
    evidence: dict[int, CapabilityEvidenceRecord],
) -> str:
    """Aggregate structured decisions into one compact support statement."""

    records: list[CapabilityEvidenceRecord] = []
    for observation_id in observation_ids:
        record = evidence.get(observation_id)
        if record is None:
            raise ValueError(
                "Capability Product lacks structured evidence for "
                f"Observation {observation_id}"
            )
        records.append(record)
    conditions = sorted(
        {
            condition
            for record in records
            for condition in record.observed_by_condition
        }
    )
    return " ".join(
        _condition_evidence_summary(condition, records)
        for condition in conditions
    )


def _condition_evidence_summary(
    condition: str,
    records: list[CapabilityEvidenceRecord],
) -> str:
    """Render one condition without repeating Observation metadata."""

    pairs = [
        (record.expected_decision, record.observed_by_condition[condition])
        for record in records
        if condition in record.observed_by_condition
    ]
    label = (
        f"thinking {condition}"
        if condition in {"enabled", "disabled"}
        else condition
    )
    expected = {item[0] for item in pairs}
    if len(expected) == 1:
        expected_label = next(iter(expected))
        wrong_stable = [
            values
            for _, values in pairs
            if len(set(values)) == 1 and values[0] != expected_label
        ]
        correct_stable = [
            values
            for _, values in pairs
            if len(set(values)) == 1 and values[0] == expected_label
        ]
        flips = [values for _, values in pairs if len(set(values)) > 1]
        if len(wrong_stable) == len(pairs):
            observed_label = wrong_stable[0][0]
            repeated = all(len(values) > 1 for values in wrong_stable)
            qualifier = " repeatedly" if repeated else ""
            subject, auxiliary = _evidence_subject(
                len(pairs),
                expected_label,
            )
            return (
                f"{label}: {subject} {auxiliary}{qualifier} labeled "
                f"{observed_label}."
            )
        if len(flips) == 1 and len(correct_stable) == len(pairs) - 1:
            sequence = "→".join(_ordered_unique(flips[0]))
            remainder = "the other" if len(pairs) == 2 else "the others"
            return (
                f"{label}: one input flipped {sequence} while {remainder} "
                f"remained {expected_label}."
            )
    rendered = "; ".join(
        f"expected {expected_label}, observed {','.join(values)}"
        for expected_label, values in pairs
    )
    return f"{label}: {rendered}."


def _evidence_subject(
    count: int,
    expected_label: str,
) -> tuple[str, str]:
    if count == 1:
        return f"the expected-{expected_label} input", "was"
    if count == 2:
        return f"both expected-{expected_label} inputs", "were"
    return f"all {count} expected-{expected_label} inputs", "were"


def _ordered_unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if not result or result[-1] != value:
            result.append(value)
    return result


def _render_hook_contract(contract: object, references: list[Any]) -> str:
    if not isinstance(contract, dict):
        raise TypeError("Hook feasibility phase lacks decision_contract")
    lines = [
        f"Predicate: {contract.get('predicate', 'not provided')}",
        f"Positive: {contract.get('positive_rule', 'not provided')}",
        f"Negative: {contract.get('negative_rule', 'not provided')}",
        f"Uncertain: {contract.get('uncertain_rule', 'not provided')}",
        "",
        "Case | Expected | Decisive reference observation",
        "--- | --- | ---",
    ]
    for item in references:
        if not isinstance(item, dict):
            continue
        lines.append(
            f"{item.get('case_id', 'unknown')} | "
            f"{item.get('expected_label', 'unknown')} | "
            f"{item.get('decisive_observation', 'not provided')}"
        )
    return "\n".join(lines)


def _direction_target(source_event: str) -> DirectionUpdateTarget:
    research_events = {
        "evidence_reviewer.reject",
        "evidence_reviewer.revise",
        "mechanism_distiller.not_distillable",
        "hook_feasibility.needs_research_revision",
        "conformance.revise_evidence",
        "candidate_reviewer.revise_evidence",
    }
    mechanism_events = {
        "hook_feasibility.needs_spec_revision",
        "compiler.needs_mechanism_revision",
        "compiler.implementation_blocked",
        "conformance.revise_mechanism",
        "candidate_reviewer.revise_mechanism",
        "candidate_reviewer.reject",
        "promotion_gate.failed",
        "promotion_gate.passed",
    }
    if source_event in research_events:
        return "research_scheme"
    if source_event in mechanism_events:
        return "mechanism_scheme"
    raise ValueError(f"unsupported Direction source event: {source_event}")


def _direction_observed(source_output: dict[str, Any]) -> str:
    decision = source_output.get("decision")
    recommendation = source_output.get("recommendation")
    assessment = source_output.get("assessment")
    reason = source_output.get("reason")
    obligation = (
        source_output.get("next_obligation")
        or source_output.get("revision_feedback")
    )
    parts = []
    if decision is not None:
        parts.append(f"decision={decision}")
    if recommendation is not None:
        parts.append(f"recommendation={recommendation}")
    if assessment:
        parts.append(str(assessment))
    elif reason:
        parts.append(str(reason))
    if obligation:
        parts.append(f"next evidence obligation: {obligation}")
    return "; ".join(parts)[:800] or "Typed source returned no reusable text."


def _direction_source_context(source_event: str) -> str:
    contexts = {
        "evidence_reviewer.reject": (
            "Intervention Trials and their local reviews have been aggregated. "
            "The Evidence Reviewer rejected the current Research Scheme within "
            "the tested assignments; this does not erase the Failure Direction."
        ),
        "evidence_reviewer.revise": (
            "Intervention Trials and their local reviews have been aggregated. "
            "The Evidence Reviewer requested a Research Scheme revision; its "
            "assessment defines the currently observed evidence defect."
        ),
        "mechanism_distiller.not_distillable": (
            "Reviewed Trial evidence reached Mechanism Distillation, but the "
            "Distiller found no faithful operational mechanism under the current "
            "Research Scheme. No Candidate implementation was tested."
        ),
        "hook_feasibility.needs_spec_revision": (
            "Real-prefix Hook feasibility probing found the Research Scheme "
            "plausible but the current Mechanism Scheme specification ambiguous "
            "or inoperable. The result updates only the Mechanism Scheme."
        ),
        "hook_feasibility.needs_research_revision": (
            "Real-prefix Hook feasibility probing found that the required model "
            "decision boundary was not reliably realizable under the current "
            "Research Scheme. No deployable Candidate was evaluated."
        ),
        "compiler.needs_mechanism_revision": (
            "The Compiler inspected the frozen Mechanism Scheme and could not "
            "implement it without changing its semantics. This is pre-Candidate "
            "implementation evidence, not downstream utility evidence."
        ),
        "compiler.implementation_blocked": (
            "The Compiler reached an implementation boundary under the current "
            "Mechanism Scheme. The source does not establish Student capability "
            "or Candidate utility."
        ),
        "conformance.revise_evidence": (
            "A statically valid Candidate completed semantic conformance replay. "
            "The Reviewer routed the failure to research evidence, so the result "
            "updates the Research Scheme rather than implementation details."
        ),
        "conformance.revise_mechanism": (
            "A statically valid Candidate completed semantic conformance replay. "
            "The Reviewer found a Mechanism-level mismatch that updates the "
            "current Mechanism Scheme before full Candidate Evaluation."
        ),
        "candidate_reviewer.revise_evidence": (
            "The Candidate completed validation, conformance, and evaluation. "
            "Candidate Review requested more or different research evidence, "
            "which updates the current Research Scheme."
        ),
        "candidate_reviewer.revise_mechanism": (
            "The Candidate completed validation, conformance, and evaluation. "
            "Candidate Review attributed the required revision to the current "
            "Mechanism Scheme."
        ),
        "candidate_reviewer.reject": (
            "The Candidate completed validation, conformance, and evaluation. "
            "Candidate Review rejected this Mechanism Scheme realization; the "
            "Failure Direction remains independently established."
        ),
    }
    try:
        return contexts[source_event]
    except KeyError as exc:
        raise ValueError(
            f"unsupported non-promotion Direction event: {source_event}"
        ) from exc


def _render_hook_rows(
    expected: dict[str, str],
    rows: list[tuple[str, str, int, str]],
) -> str:
    lines = [
        "Case | Expected | Thinking | Repetition | Observed",
        "--- | --- | --- | ---: | ---",
    ]
    lines.extend(
        f"{case} | {expected[case]} | {mode} | {rep} | {observed}"
        for case, mode, rep, observed in rows
    )
    return "\n".join(lines)
