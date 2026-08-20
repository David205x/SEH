"""Real-prefix probes for distilled Hook-model decision contracts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from search_harness.framework import HookModelBackend

from .intervention.bridge import initial_worker_snapshot
from .intervention.prefix import (
    load_reconstructed_prefix,
    load_rollout_record,
    resolve_prefix_boundary,
)
from .intervention.types import PrefixSelector
from .roles.contracts import (
    DecisionLabel,
    MechanismPhaseRule,
    MechanismSpec,
    TrialReview,
)
from .student_model_experiment import (
    StudentModelExperimentCase,
    run_student_model_experiment,
)


_LABELS: tuple[DecisionLabel, ...] = (
    "positive",
    "negative",
    "uncertain",
)


@dataclass(frozen=True)
class HookFeasibilityProbeConfig:
    """Bound one conditional feasibility check before compilation."""

    max_cases_per_phase: int = 6
    repetitions: int = 2
    thinking_modes: tuple[str, ...] = ("enabled", "disabled")

    def __post_init__(self) -> None:
        if not 1 <= self.max_cases_per_phase <= 6:
            raise ValueError(
                "Hook feasibility max_cases_per_phase must be between 1 and 6"
            )
        if not 1 <= self.repetitions <= 3:
            raise ValueError(
                "Hook feasibility repetitions must be between 1 and 3"
            )
        if not self.thinking_modes or len(self.thinking_modes) > 2:
            raise ValueError(
                "Hook feasibility requires one or two thinking modes"
            )
        if len(self.thinking_modes) != len(set(self.thinking_modes)):
            raise ValueError(
                "Hook feasibility thinking modes must not repeat"
            )
        invalid = set(self.thinking_modes) - {"enabled", "disabled"}
        if invalid:
            raise ValueError(
                "Hook feasibility thinking modes must be enabled or disabled"
            )


@dataclass(frozen=True)
class _ProbeCase:
    case_id: str
    trial_ref: str
    phase: str
    expected_label: DecisionLabel
    phase_execution: str
    decisive_observation: str
    user_prompt: str


class HookFeasibilityProbeExecutor:
    """Call the Student as an isolated Hook evaluator at real Trial prefixes."""

    def __init__(
        self,
        *,
        backend: HookModelBackend,
        config: HookFeasibilityProbeConfig,
    ) -> None:
        self.backend = backend
        self.config = config

    def run(
        self,
        *,
        mechanism: MechanismSpec,
        trial_paths: list[Path],
        trial_reviews: list[TrialReview],
        rollout_file: Path,
    ) -> dict[str, Any]:
        """Return descriptive observations without a program-owned verdict."""

        trial_by_ref = {
            path.resolve().parent.name: path.resolve()
            for path in trial_paths
        }
        if len(trial_by_ref) != len(trial_paths):
            raise ValueError("Hook feasibility trial refs must be unique")

        phase_probes = []
        for rule in mechanism.phase_rules:
            if rule.decision_evaluator != "hook_model":
                continue
            cases = _cases_for_rule(
                rule=rule,
                trial_by_ref=trial_by_ref,
                trial_reviews=trial_reviews,
                rollout_file=rollout_file,
                limit=self.config.max_cases_per_phase,
            )
            if not cases:
                raise ValueError(
                    "Hook-model phase has no reviewed real-prefix cases: "
                    f"{rule.phase}"
                )
            experiment = run_student_model_experiment(
                backend=self.backend,
                experiment_id=f"hook_feasibility_{rule.phase}",
                purpose=(
                    "distilled_hook_model_feasibility: Test the distilled "
                    "Hook-model decision contract on "
                    f"reviewed real prefixes at phase {rule.phase}."
                ),
                system_prompt=_system_prompt(rule),
                cases=tuple(
                    StudentModelExperimentCase(
                        case_id=case.case_id,
                        user_prompt=case.user_prompt,
                    )
                    for case in cases
                ),
                thinking_modes=self.config.thinking_modes,
                repetitions=self.config.repetitions,
            )
            phase_probes.append(
                {
                    "phase": rule.phase,
                    "decision_contract": rule.decision_contract.model_dump(
                        mode="json"
                    ),
                    "decision_inputs": list(rule.decision_inputs),
                    "runtime_inputs": list(rule.runtime_inputs),
                    "case_references": [
                        {
                            "case_id": case.case_id,
                            "trial_ref": case.trial_ref,
                            "expected_label": case.expected_label,
                            "phase_execution": case.phase_execution,
                            "decisive_observation": case.decisive_observation,
                        }
                        for case in cases
                    ],
                    "experiment": experiment,
                }
            )

        if not phase_probes:
            raise ValueError(
                "Hook feasibility requires at least one hook_model phase"
            )
        return {
            "schema_version": 1,
            "purpose": "distilled_hook_model_feasibility",
            "thinking_modes": list(self.config.thinking_modes),
            "repetitions": self.config.repetitions,
            "phase_probes": phase_probes,
        }


def mechanism_requires_hook_feasibility(mechanism: MechanismSpec) -> bool:
    """Return whether the distilled mechanism delegates semantics to a model."""

    return any(
        rule.decision_evaluator == "hook_model"
        for rule in mechanism.phase_rules
    )


def probe_total_tokens(probe: dict[str, Any]) -> int:
    """Sum normalized Student usage across every feasibility observation."""

    total = 0
    phase_probes = probe.get("phase_probes")
    if not isinstance(phase_probes, list):
        return 0
    for phase_probe in phase_probes:
        if not isinstance(phase_probe, dict):
            continue
        experiment = phase_probe.get("experiment")
        if not isinstance(experiment, dict):
            continue
        observations = experiment.get("observations")
        if not isinstance(observations, list):
            continue
        for observation in observations:
            if not isinstance(observation, dict):
                continue
            usage = observation.get("usage")
            if not isinstance(usage, dict):
                continue
            value = usage.get("total_tokens")
            if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                total += value
    return total


def render_hook_feasibility_review_input(
    value: dict[str, Any],
) -> str:
    """Render one compact Reviewer view while full Probe artifacts stay intact."""

    mechanism = _required_object(value, "mechanism")
    probe = _required_object(value, "probe_evidence")
    phase_probes = probe.get("phase_probes")
    if not isinstance(phase_probes, list):
        raise TypeError("probe_evidence.phase_probes must be a list")
    projected_phases = [
        _project_phase_probe(item)
        for item in phase_probes
        if isinstance(item, dict)
    ]
    prior = value.get("prior_model_experiments", [])
    if not isinstance(prior, list):
        raise TypeError("prior_model_experiments must be a list")
    projected = {
        "mechanism": mechanism,
        "real_prefix_probes": projected_phases,
        "prior_synthetic_experiments": [
            _project_prior_experiment(item)
            for item in prior
            if isinstance(item, dict)
        ],
    }
    return json.dumps(
        projected,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _cases_for_rule(
    *,
    rule: MechanismPhaseRule,
    trial_by_ref: dict[str, Path],
    trial_reviews: list[TrialReview],
    rollout_file: Path,
    limit: int,
) -> list[_ProbeCase]:
    candidates: dict[DecisionLabel, list[_ProbeCase]] = {
        label: [] for label in _LABELS
    }
    for review in trial_reviews:
        trial_path = trial_by_ref.get(review.trial_ref)
        if trial_path is None:
            raise ValueError(
                "Hook feasibility review references an unattached Trial: "
                f"{review.trial_ref}"
            )
        trial = _read_json(trial_path)
        task = _required_object(trial, "input")
        for observation in review.predicate_observations:
            if observation.phase != rule.phase:
                continue
            case = _build_case(
                trial_ref=review.trial_ref,
                task=task,
                expected_label=observation.predicate_label,
                phase_execution=observation.phase_execution,
                decisive_observation=observation.decisive_observation,
                rollout_file=rollout_file,
            )
            candidates[observation.predicate_label].append(case)

    for label in _LABELS:
        candidates[label].sort(
            key=lambda case: case.phase_execution == "invalid_execution"
        )
    selected = []
    while len(selected) < limit:
        added = False
        for label in _LABELS:
            if candidates[label] and len(selected) < limit:
                selected.append(candidates[label].pop(0))
                added = True
        if not added:
            break
    return selected


def _build_case(
    *,
    trial_ref: str,
    task: dict[str, Any],
    expected_label: DecisionLabel,
    phase_execution: str,
    decisive_observation: str,
    rollout_file: Path,
) -> _ProbeCase:
    example_id = _required_string(task, "example_id")
    replicate_id = _required_string(task, "replicate_id")
    prefix_id = _required_positive_int(task, "prefix_id")
    record = load_rollout_record(rollout_file, example_id, replicate_id)
    boundary = resolve_prefix_boundary(record, prefix_id)
    prefix = load_reconstructed_prefix(
        PrefixSelector(
            rollout_file=rollout_file,
            example_id=example_id,
            replicate_id=replicate_id,
            step=int(boundary["step"]),
            phase=str(boundary["phase"]),
        )
    )
    snapshot = initial_worker_snapshot(prefix)
    observation = {
        "phase": prefix.selector.phase,
        "task": snapshot["current_core"],
        "conversation": prefix.model_input.to_dict()["messages"],
        "active_stage": snapshot["active_stage"],
    }
    user_prompt = (
        "Apply the frozen decision contract to this runtime-visible Hook "
        "observation. Do not infer hidden facts or judge answer correctness.\n"
        + json.dumps(
            observation,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    case_id = f"{trial_ref}_{prefix.selector.phase}"
    return _ProbeCase(
        case_id=case_id,
        trial_ref=trial_ref,
        phase=prefix.selector.phase,
        expected_label=expected_label,
        phase_execution=phase_execution,
        decisive_observation=decisive_observation,
        user_prompt=user_prompt,
    )


def _system_prompt(rule: MechanismPhaseRule) -> str:
    contract = rule.decision_contract
    return (
        "You are the bounded semantic evaluator for one Student Harness Hook. "
        "Deterministic guards have already passed; do not rediscover them. "
        "Use only the supplied runtime-visible observation.\n\n"
        f"Phase: {rule.phase}\n"
        f"Predicate: {contract.predicate}\n"
        f"Positive: {contract.positive_rule}\n"
        f"Negative: {contract.negative_rule}\n"
        f"Uncertain: {contract.uncertain_rule}\n"
        "Return exactly one lowercase label and no other text: positive, "
        "negative, or uncertain."
    )


def _project_phase_probe(value: dict[str, Any]) -> dict[str, Any]:
    experiment = _required_object(value, "experiment")
    raw_cases = experiment.get("cases")
    raw_observations = experiment.get("observations")
    references = value.get("case_references")
    if not isinstance(raw_cases, list):
        raise TypeError("Hook feasibility experiment cases must be a list")
    if not isinstance(raw_observations, list):
        raise TypeError(
            "Hook feasibility experiment observations must be a list"
        )
    if not isinstance(references, list):
        raise TypeError("Hook feasibility case_references must be a list")
    prompts = {
        str(item.get("case_id")): item.get("user_prompt")
        for item in raw_cases
        if isinstance(item, dict)
    }
    observations_by_case: dict[str, list[dict[str, Any]]] = {}
    reference_labels = {
        str(item.get("case_id")): item.get("expected_label")
        for item in references
        if isinstance(item, dict)
    }
    for observation in raw_observations:
        if not isinstance(observation, dict):
            continue
        case_id = str(observation.get("case_id") or "")
        raw_output = observation.get("raw_output")
        observed_label = _leading_label(raw_output)
        projected = {
            "thinking_mode": observation.get("thinking_mode"),
            "repetition": observation.get("repetition"),
            "observed_label": observed_label,
            "raw_output": raw_output,
            "error": observation.get("error"),
            "total_tokens": _observation_total_tokens(observation),
        }
        if observed_label != reference_labels.get(case_id):
            metadata = observation.get("metadata")
            reasoning = (
                metadata.get("reasoning")
                if isinstance(metadata, dict)
                else None
            )
            if isinstance(reasoning, str) and reasoning.strip():
                projected["reasoning_excerpt"] = _excerpt(reasoning, 1200)
        observations_by_case.setdefault(case_id, []).append(projected)
    cases = []
    for reference in references:
        if not isinstance(reference, dict):
            continue
        case_id = str(reference.get("case_id") or "")
        cases.append(
            {
                **reference,
                "hook_input": prompts.get(case_id),
                "observations": observations_by_case.get(case_id, []),
            }
        )
    return {
        "phase": value.get("phase"),
        "decision_contract": value.get("decision_contract"),
        "decision_inputs": value.get("decision_inputs"),
        "runtime_inputs": value.get("runtime_inputs"),
        "system_prompt": experiment.get("system_prompt"),
        "cases": cases,
    }


def _project_prior_experiment(value: dict[str, Any]) -> dict[str, Any]:
    observations = value.get("observations")
    compact_observations = []
    if isinstance(observations, list):
        for observation in observations:
            if not isinstance(observation, dict):
                continue
            compact_observations.append(
                {
                    "case_id": observation.get("case_id"),
                    "thinking_mode": observation.get("thinking_mode"),
                    "repetition": observation.get("repetition"),
                    "observed_label": _leading_label(
                        observation.get("raw_output")
                    ),
                    "raw_output": observation.get("raw_output"),
                    "error": observation.get("error"),
                    "total_tokens": _observation_total_tokens(observation),
                }
            )
    return {
        "purpose": value.get("purpose"),
        "system_prompt": value.get("system_prompt"),
        "cases": value.get("cases"),
        "observations": compact_observations,
    }


def _leading_label(value: object) -> str:
    if not isinstance(value, str):
        return "parse_error"
    normalized = value.strip().casefold()
    for label in _LABELS:
        if normalized.startswith(label):
            return label
    return "parse_error"


def _observation_total_tokens(value: dict[str, Any]) -> int:
    usage = value.get("usage")
    amount = usage.get("total_tokens") if isinstance(usage, dict) else None
    if not isinstance(amount, int) or isinstance(amount, bool) or amount < 0:
        return 0
    return amount


def _excerpt(value: str, limit: int) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    half = (limit - 20) // 2
    return f"{text[:half]} ...[excerpt]... {text[-half:]}"


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"JSON artifact must be an object: {path}")
    return value


def _required_object(value: dict[str, Any], name: str) -> dict[str, Any]:
    item = value.get(name)
    if not isinstance(item, dict):
        raise TypeError(f"{name} must be an object")
    return dict(item)


def _required_string(value: dict[str, Any], name: str) -> str:
    item = value.get(name)
    if not isinstance(item, str) or not item.strip():
        raise TypeError(f"{name} must be a non-empty string")
    return item


def _required_positive_int(value: dict[str, Any], name: str) -> int:
    item = value.get(name)
    if not isinstance(item, int) or isinstance(item, bool) or item < 1:
        raise TypeError(f"{name} must be a positive integer")
    return item
