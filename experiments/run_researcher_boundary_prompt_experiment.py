"""Run the staged shadow Hypothesis Researcher prompt-repair experiment."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import random
import re
import shutil
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any, Sequence

from search_harness.evolution.research.resources.base import TeacherResourceConfig
from search_harness.evolution.research.roles.contracts import (
    EvidenceReview,
    EvidenceReviewBudget,
    FailureDirection,
    InterventionHypothesis,
    TrialReview,
)
from search_harness.evolution.research.roles.native_chat_runner import (
    NativeChatRoleRunner,
    TeacherRoleRunFailed,
)
from search_harness.evolution.research.intervention.prefix import (
    build_prefix_timeline,
    load_rollout_record,
)
from search_harness.evolution.research.intervention.role_runner import (
    InterventionRoleRunner,
)
from search_harness.evolution.control.intervention_effects import (
    InterventionEffects,
)
from search_harness.evolution.research.evidence import (
    aggregate_trial_observations,
    summarize_evidence_coverage,
)
from search_harness.integrations.openai_compatible import (
    OpenAICompatibleConfig,
)


_INPUT_NAMES = ("corrective_regression", "mechanism_preservation", "preventive")
_VARIANTS = ("baseline", "repair")
_CRITERIA = (
    "minimum_failure_predicate_preserved",
    "temporal_observability",
    "claim_phase_alignment",
    "neighbor_falsifiability",
    "worker_semantics",
    "scope_discipline",
)
_FUTURE_FACT_PATTERNS = (
    re.compile(
        r"\b(?:only|sole|single)\s+(?:search|retrieval)\s+"
        r"(?:in|for|of)\s+(?:the\s+)?(?:trial|trajectory|run)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:will|would|going to)\s+(?:not\s+)?"
        r"(?:search|retrieve|finali[sz]e|stop|answer)\b",
        re.I,
    ),
    re.compile(r"\b(?:never|no)\s+(?:further|additional|later)\b", re.I),
    re.compile(r"\b(?:finali[sz]es?|stops?|answers?)\b", re.I),
)

def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare-repair")
    prepare.add_argument("--prior-experiment-dir", type=Path, required=True)
    prepare.add_argument("--preventive-input", type=Path, required=True)
    prepare.add_argument("--repair-template", type=Path, required=True)
    prepare.add_argument("--formal-template", type=Path, required=True)
    prepare.add_argument("--output-dir", type=Path, required=True)

    run_repair = subparsers.add_parser("run-researcher-repair")
    run_repair.add_argument("--experiment-dir", type=Path, required=True)
    run_repair.add_argument("--report-dir", type=Path, required=True)
    run_repair.add_argument("--rollout-file", type=Path, required=True)
    run_repair.add_argument("--student-template-root", type=Path, required=True)
    run_repair.add_argument("--env-file", type=Path, default=Path(".env"))
    run_repair.add_argument("--model-env-prefix", default="TEACHER")
    run_repair.add_argument("--model-id")
    run_repair.add_argument("--base-seed", type=int, default=5200)
    run_repair.add_argument("--repetitions", type=int, default=3)
    run_repair.add_argument("--max-turns", type=int, default=20)
    run_repair.add_argument("--max-tokens", type=int, default=8192)
    run_repair.add_argument("--temperature", type=float, default=0.2)
    run_repair.add_argument(
        "--thinking-mode",
        choices=("inherit", "enabled", "disabled"),
        default="inherit",
    )

    review = subparsers.add_parser("prepare-semantic-review")
    review.add_argument("--experiment-dir", type=Path, required=True)
    review.add_argument("--randomization-seed", type=int, default=9831)

    summarize = subparsers.add_parser("summarize-researcher")
    summarize.add_argument("--experiment-dir", type=Path, required=True)

    prepare_intervention_parser = subparsers.add_parser("prepare-intervention")
    prepare_intervention_parser.add_argument("--experiment-dir", type=Path, required=True)
    prepare_intervention_parser.add_argument("--rollout-file", type=Path, required=True)
    prepare_intervention_parser.add_argument("--student-template-root", type=Path, required=True)
    prepare_intervention_parser.add_argument("--env-file", type=Path, default=Path(".env"))
    run_intervention = subparsers.add_parser("run-intervention")
    run_intervention.add_argument("--experiment-dir", type=Path, required=True)
    run_intervention.add_argument(
        "--thinking-mode", choices=("enabled", "disabled"), required=True
    )
    run_intervention.add_argument("--max-workers", type=int, default=4)
    trial_review = subparsers.add_parser("review-trials")
    trial_review.add_argument("--experiment-dir", type=Path, required=True)
    trial_review.add_argument("--env-file", type=Path, default=Path(".env"))
    trial_review.add_argument("--max-workers", type=int, default=8)
    evidence_review = subparsers.add_parser("review-evidence")
    evidence_review.add_argument("--experiment-dir", type=Path, required=True)
    evidence_review.add_argument("--env-file", type=Path, default=Path(".env"))
    subparsers.add_parser("summarize").add_argument(
        "--experiment-dir", type=Path, required=True
    )
    return parser.parse_args(argv)


def prepare(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    input_dir = output_dir / "inputs" / "failure_directions"
    template_dir = output_dir / "templates"
    input_dir.mkdir(parents=True, exist_ok=True)
    template_dir.mkdir(parents=True, exist_ok=True)

    prior = args.prior_experiment_dir.resolve()
    input_sources = (
        prior / "inputs" / "failure_directions" / "input_01.json",
        prior / "inputs" / "failure_directions" / "input_03.json",
        args.preventive_input.resolve(),
    )
    sources: dict[str, str] = {}
    for index, source in enumerate(input_sources, start=1):
        target = input_dir / f"input_{index:02d}.json"
        _copy_or_verify_file(source, target)
        artifact = _read_json(target)
        FailureDirection.model_validate(_required_object(artifact, "output"))
        sources[_INPUT_NAMES[index - 1]] = str(source)

    templates = {
        "baseline": prior / "templates" / "boundary" / "hypothesis_researcher",
        "repair": args.repair_template.resolve(),
    }
    for variant, source in templates.items():
        target = template_dir / variant / "hypothesis_researcher"
        _copy_or_verify_tree(source, target)

    manifest = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "experiment": "researcher_boundary_prompt_repair_v1",
        "status": "prepared",
        "sources": sources,
        "hashes": {
            "formal_template_before": _tree_digest(
                args.formal_template.resolve()
            ),
            "repair_source_at_prepare": _tree_digest(
                args.repair_template.resolve()
            ),
            "baseline_template": _tree_digest(
                template_dir / "baseline" / "hypothesis_researcher"
            ),
            "repair_template": _tree_digest(
                template_dir / "repair" / "hypothesis_researcher"
            ),
            "inputs": {
                path.stem: _digest(path)
                for path in sorted(input_dir.glob("input_*.json"))
            },
        },
        "formal_template_path": str(args.formal_template.resolve()),
        "prompt_characters": {
            variant: len(
                (template_dir / variant / "hypothesis_researcher" / "prompt" / "system.md")
                .read_text(encoding="utf-8")
            )
            for variant in _VARIANTS
        },
        "prompt_pairing": (
            "Prior baseline artifacts are reused for inputs 1 and 2. New "
            "preventive baseline and every Repair run use the same frozen "
            "Failure Direction, resource views, model settings, budgets, and "
            "paired seed."
        ),
    }
    _write_json(output_dir / "manifest.json", manifest)
    return manifest


async def run_researcher_ab(args: argparse.Namespace) -> dict[str, Any]:
    if args.repetitions != 3:
        raise ValueError("the preregistered stage requires exactly 3 repetitions")
    experiment_dir = args.experiment_dir.resolve()
    manifest = _read_json(experiment_dir / "manifest.json")
    _verify_frozen_hashes(experiment_dir, manifest)
    resource_config = TeacherResourceConfig(
        report_dir=args.report_dir.resolve(),
        rollout_file=args.rollout_file.resolve(),
        student_template_root=args.student_template_root.resolve(),
    )
    loaded = OpenAICompatibleConfig.from_env(
        env_file=args.env_file,
        prefix=args.model_env_prefix,
    )
    base_config = _configured_model(
        loaded,
        model_id=args.model_id,
        seed=args.base_seed,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        thinking_mode=args.thinking_mode,
    )
    progress_path = experiment_dir / "researcher_ab" / "progress.json"
    completed: list[dict[str, Any]] = []
    for input_index in range(1, 4):
        source = _read_json(
            experiment_dir
            / "inputs"
            / "failure_directions"
            / f"input_{input_index:02d}.json"
        )
        direction = _required_object(source, "output")
        FailureDirection.model_validate(direction)
        for repetition in range(1, args.repetitions + 1):
            seed = args.base_seed + input_index * 100 + repetition
            order = ("baseline", "repair") if input_index == 3 else ("repair",)
            pair: dict[str, Any] = {
                "input_index": input_index,
                "repetition": repetition,
                "seed": seed,
                "order": list(order),
                "variants": {},
            }
            for variant in order:
                path = (
                    experiment_dir
                    / "researcher_ab"
                    / f"input_{input_index:02d}"
                    / f"{variant}_{repetition:02d}.json"
                )
                artifact = await _run_researcher_once(
                    template_root=(
                        experiment_dir
                        / "templates"
                        / variant
                        / "hypothesis_researcher"
                    ),
                    direction=direction,
                    resource_config=resource_config,
                    config=replace(base_config, seed=seed),
                    max_turns=args.max_turns,
                    artifact_path=path,
                )
                pair["variants"][variant] = _role_summary(artifact)
                _write_json(
                    progress_path,
                    {
                        "schema_version": 1,
                        "completed_pairs": completed,
                        "active_pair": pair,
                    },
                )
            completed.append(pair)
            _write_json(
                progress_path,
                {"schema_version": 1, "completed_pairs": completed},
            )
    _reuse_prior_baselines(experiment_dir, args.repetitions)
    summary = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "base_model": base_config.provenance(),
        "pairing": manifest["prompt_pairing"],
        "pairs": completed,
        "formal_template_unchanged": _formal_template_unchanged(manifest),
    }
    _write_json(experiment_dir / "researcher_ab" / "summary.json", summary)
    return summary


def _reuse_prior_baselines(experiment_dir: Path, repetitions: int) -> None:
    manifest = _read_json(experiment_dir / "manifest.json")
    sources = _required_object(manifest, "sources")
    first = Path(_required_string(sources, "corrective_regression"))
    prior = first.parents[2]
    for input_index, prior_input in ((1, 1), (2, 3)):
        for repetition in range(1, repetitions + 1):
            source = (
                prior
                / "researcher_ab"
                / f"input_{prior_input:02d}"
                / f"boundary_{repetition:02d}.json"
            )
            target = (
                experiment_dir
                / "researcher_ab"
                / f"input_{input_index:02d}"
                / f"baseline_{repetition:02d}.json"
            )
            _copy_or_verify_file(source, target)


def prepare_researcher_review(args: argparse.Namespace) -> dict[str, Any]:
    experiment_dir = args.experiment_dir.resolve()
    entries = [
        (input_index, variant, repetition)
        for input_index in range(1, 4)
        for variant in _VARIANTS
        for repetition in range(1, 4)
    ]
    random.Random(args.randomization_seed).shuffle(entries)
    mapping: dict[str, Any] = {}
    handoffs = []
    for index, (input_index, variant, repetition) in enumerate(entries, start=1):
        anonymous_id = f"A{index:02d}"
        source = _read_json(
            experiment_dir
            / "inputs"
            / "failure_directions"
            / f"input_{input_index:02d}.json"
        )
        artifact = _read_json(
            experiment_dir
            / "researcher_ab"
            / f"input_{input_index:02d}"
            / f"{variant}_{repetition:02d}.json"
        )
        output = artifact.get("output")
        protocol_legal = isinstance(output, dict)
        if protocol_legal:
            InterventionHypothesis.model_validate(output)
        mapping[anonymous_id] = {
            "input_index": input_index,
            "variant": variant,
            "repetition": repetition,
        }
        handoffs.append(
            {
                "anonymous_id": anonymous_id,
                "failure_direction": _review_direction(
                    _required_object(source, "output")
                ),
                "hypothesis": output,
                "protocol_legal": protocol_legal,
            }
        )
    packet = {
        "schema_version": 1,
        "instructions": (
            "Variant identity, transcript, tool metrics, usage, paths, and "
            "concrete assignment purposes are intentionally omitted. Judge "
            "the six frozen criteria. Every 0/1 judgment must quote exact "
            "text from both Failure Direction and Hypothesis and give a "
            "short reason. Record protocol_legal, case_leakage, whether a "
            "preventive claim is explicit, and whether its required recovery "
            "or unnecessary-intervention obligation is present."
        ),
        "criteria": list(_CRITERIA),
        "semantic_review_schema": {
            "reviews": [
                {
                    "anonymous_id": "A01",
                    "criteria": {
                        name: {
                            "score": "0|1",
                            "failure_quote": "exact quote",
                            "hypothesis_quote": "exact quote",
                            "reason": "short adjudication",
                        }
                        for name in _CRITERIA
                    },
                    "total": "sum of six scores",
                    "protocol_legal": True,
                    "case_leakage": False,
                    "preventive_claim_explicit": False,
                    "recovery_obligation_present": False,
                    "assessment": "overall semantic judgment",
                }
            ]
        },
        "handoffs": handoffs,
    }
    review_dir = experiment_dir / "researcher_review"
    _write_json(review_dir / "anonymous_packet.json", packet)
    _write_json(
        review_dir / "randomization.json",
        {
            "schema_version": 1,
            "seed": args.randomization_seed,
            "mapping": mapping,
        },
    )
    return {"anonymous_count": len(handoffs), "mapping": mapping}


def summarize(args: argparse.Namespace) -> dict[str, Any]:
    experiment_dir = args.experiment_dir.resolve()
    mapping = _required_object(
        _read_json(experiment_dir / "researcher_review" / "randomization.json"),
        "mapping",
    )
    semantic = _read_json(
        experiment_dir / "researcher_review" / "semantic_review.json"
    )
    validate_semantic_review(semantic)
    _validate_semantic_quotes(experiment_dir, semantic)
    reviews = semantic.get("reviews")
    if not isinstance(reviews, list) or len(reviews) != 18:
        raise ValueError("manual review must contain exactly 18 reviews")
    scored: dict[tuple[int, str, int], dict[str, Any]] = {}
    for review in reviews:
        if not isinstance(review, dict):
            raise TypeError("manual review item must be an object")
        anonymous_id = _required_string(review, "anonymous_id")
        source = _required_object(mapping, anonymous_id)
        criteria = _required_object(review, "criteria")
        if set(criteria) != set(_CRITERIA):
            raise ValueError(f"invalid semantic criteria: {anonymous_id}")
        for name, judgment in criteria.items():
            if not isinstance(judgment, dict) or judgment.get("score") not in {0, 1}:
                raise ValueError(f"invalid semantic score: {anonymous_id}/{name}")
            _required_string(judgment, "failure_quote")
            _required_string(judgment, "hypothesis_quote")
            _required_string(judgment, "reason")
        scores = {name: int(item["score"]) for name, item in criteria.items()}
        total = sum(scores.values())
        if review.get("total") != total:
            raise ValueError(f"semantic total mismatch: {anonymous_id}")
        key = (
            int(source["input_index"]),
            str(source["variant"]),
            int(source["repetition"]),
        )
        scored[key] = {**review, "scores": scores, "total": total}

    pairs = []
    improvements = 0
    regressions = 0
    for input_index in range(1, 4):
        for repetition in range(1, 4):
            baseline = scored[(input_index, "baseline", repetition)]
            repair = scored[(input_index, "repair", repetition)]
            delta = int(repair["total"]) - int(baseline["total"])
            improvements += delta > 0
            regressions += delta < 0
            pairs.append(
                {
                    "input_index": input_index,
                    "repetition": repetition,
                    "baseline": baseline,
                    "repair": repair,
                    "repair_minus_baseline": delta,
                }
            )
    repair_runs = [item["repair"] for item in pairs]
    all_legal_no_leak = all(
        item.get("protocol_legal") is True
        and item.get("case_leakage") is False
        for item in repair_runs
    )
    temporal_worker_passes = sum(
        item["scores"]["temporal_observability"] == 1
        and item["scores"]["worker_semantics"] == 1
        for item in repair_runs
    )
    input_full_passes = {
        input_index: sum(
            all(value == 1 for value in item["repair"]["scores"].values())
            for item in pairs
            if item["input_index"] == input_index
        )
        for input_index in range(1, 4)
    }
    phases = [_hypothesis_phase(experiment_dir, item["input_index"], "repair", item["repetition"]) for item in pairs]
    minimum_predicate_input_2 = sum(
        item["repair"]["scores"]["minimum_failure_predicate_preserved"] == 1
        for item in pairs if item["input_index"] == 2
    )
    preventive_valid = sum(
        all(value == 1 for value in item["repair"]["scores"].values())
        and item["repair"].get("preventive_claim_explicit") is True
        and item["repair"].get("recovery_obligation_present") is True
        for item in pairs if item["input_index"] == 3
    )
    cost = _repair_cost_gate(experiment_dir)
    criteria = {
        "repair_9_of_9_legal_no_leak": all_legal_no_leak,
        "corrective_regression_2_of_3_full_passes": input_full_passes[1] >= 2,
        "mechanism_preservation_2_of_3_full_passes": input_full_passes[2] >= 2,
        "mechanism_preservation_3_of_3_minimum_predicate": minimum_predicate_input_2 == 3,
        "preventive_2_of_3_full_explicit_with_recovery_obligation": preventive_valid >= 2,
        "repair_9_of_9_temporal_and_worker": temporal_worker_passes == 9,
        "static_prompt_cost_target": cost["static_prompt_target_met"],
    }
    passed = all(criteria.values())
    manifest = _read_json(experiment_dir / "manifest.json")
    summary = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "experiment": "researcher_boundary_prompt_repair_v1",
        "stage_one": {
            "status": "passed" if passed else "failed",
            "pairs": pairs,
            "baseline_mean": round(
                mean(int(item["baseline"]["total"]) for item in pairs), 3
            ),
            "repair_mean": round(
                mean(int(item["repair"]["total"]) for item in pairs), 3
            ),
            "paired_improvements": improvements,
            "paired_regressions": regressions,
            "repair_temporal_worker_passes": temporal_worker_passes,
            "repair_full_passes_by_input": input_full_passes,
            "repair_phase_distribution": {
                phase: phases.count(phase) for phase in sorted(set(phases))
            },
            "preventive_valid_passes": preventive_valid,
            "success_criteria": criteria,
            "cost_gate": cost,
        },
        "stage_two_authorized": passed,
        "role_metrics": _aggregate_researcher_metrics(experiment_dir),
        "formal_template_unchanged": _formal_template_unchanged(manifest),
        "decision": (
            "prepare_intervention"
            if passed
            else "stop_before_intervention_and_continue_shadow_prompt_research"
        ),
    }
    _write_json(experiment_dir / "summary.json", summary)
    return summary


def _aggregate_researcher_metrics(
    experiment_dir: Path,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for variant in _VARIANTS:
        artifacts = [
            _read_json(
                experiment_dir
                / "researcher_ab"
                / f"input_{input_index:02d}"
                / f"{variant}_{repetition:02d}.json"
            )
            for input_index in range(1, 4)
            for repetition in range(1, 4)
        ]
        requests = [int(item["usage"]["requests"]) for item in artifacts]
        tool_calls = [len(item.get("tool_calls", [])) for item in artifacts]
        total_tokens = [
            int(item["usage"]["total_tokens"]) for item in artifacts
        ]
        phases = [str(item["output"]["fork_phase"]) for item in artifacts]
        max_token_calls = 0
        for artifact in artifacts:
            max_tokens = int(artifact["model"]["max_tokens"])
            max_token_calls += sum(
                int(call.get("completion_tokens", 0)) == max_tokens
                for call in artifact["usage"].get("calls", [])
                if isinstance(call, dict)
            )
        result[variant] = {
            "runs": len(artifacts),
            "phase_distribution": {
                phase: phases.count(phase) for phase in sorted(set(phases))
            },
            "means": {
                "requests": round(mean(requests), 3),
                "tool_calls": round(mean(tool_calls), 3),
                "total_tokens": round(mean(total_tokens), 3),
            },
            "totals": {
                "requests": sum(requests),
                "tool_calls": sum(tool_calls),
                "total_tokens": sum(total_tokens),
                "max_token_calls": max_token_calls,
            },
        }
    return result


def _repair_cost_gate(experiment_dir: Path) -> dict[str, Any]:
    manifest = _read_json(experiment_dir / "manifest.json")
    characters = _required_object(manifest, "prompt_characters")
    baseline_chars = int(characters["baseline"])
    repair_chars = int(characters["repair"])
    metrics = _aggregate_researcher_metrics(experiment_dir)
    baseline = metrics["baseline"]
    repair = metrics["repair"]
    baseline_tokens = float(baseline["means"]["total_tokens"])
    repair_tokens = float(repair["means"]["total_tokens"])
    token_reduction = (
        (baseline_tokens - repair_tokens) / baseline_tokens
        if baseline_tokens
        else 0.0
    )
    return {
        "baseline_prompt_characters": baseline_chars,
        "repair_prompt_characters": repair_chars,
        "prompt_character_ratio": round(repair_chars / baseline_chars, 4),
        "static_prompt_target_met": repair_chars <= baseline_chars * 0.8,
        "mean_total_token_reduction": round(token_reduction, 4),
        "runtime_token_target_met": token_reduction >= 0.15,
        "requests_not_increased": (
            repair["means"]["requests"] <= baseline["means"]["requests"]
        ),
        "max_token_calls_not_increased": (
            repair["totals"]["max_token_calls"]
            <= baseline["totals"]["max_token_calls"]
        ),
    }


def _require_stage_two(experiment_dir: Path) -> dict[str, Any]:
    summary = _read_json(experiment_dir / "summary.json")
    if summary.get("stage_two_authorized") is not True:
        raise RuntimeError(
            "Researcher semantic gate did not authorize Intervention"
        )
    if summary.get("formal_template_unchanged") is not True:
        raise RuntimeError("formal Researcher template changed during experiment")
    return summary


def prepare_intervention(args: argparse.Namespace) -> dict[str, Any]:
    experiment_dir = args.experiment_dir.resolve()
    _require_stage_two(experiment_dir)
    selected = {
        "corrective": (2, 1),
        "preventive": (3, 1),
    }
    case_ids = (
        "5a7e36045542991319bc9440",
        "5a81ff1d554299676cceb1c3",
        "5ab3ed12554299753aec59f3",
        "5a736bfa5542991f29ee2e03",
        "5ac061ab554299294b218fac",
    )
    plan: dict[str, Any] = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "rollout_file": str(args.rollout_file.resolve()),
        "student_template_root": str(args.student_template_root.resolve()),
        "env_file": str(args.env_file.resolve()),
        "hypotheses": {},
    }
    for name, (input_index, repetition) in selected.items():
        artifact_path = (
            experiment_dir / "researcher_ab" / f"input_{input_index:02d}"
            / f"repair_{repetition:02d}.json"
        )
        artifact = _read_json(artifact_path)
        hypothesis = InterventionHypothesis.model_validate(artifact["output"])
        assignments = []
        for example_id in case_ids:
            for replicate_index in range(3):
                replicate_id = f"r{replicate_index:03d}"
                record = load_rollout_record(
                    args.rollout_file.resolve(), example_id, replicate_id
                )
                prefix_id = select_first_compatible_prefix(
                    build_prefix_timeline(record), hypothesis.fork_phase
                )
                assignments.append({
                    "trial_objective": (
                        f"{hypothesis.evaluation.primary_signal} | "
                        f"{hypothesis.evaluation.success_condition} | "
                        f"{hypothesis.evaluation.falsifier}"
                    ),
                    "example_id": example_id,
                    "replicate_id": replicate_id,
                    "prefix_id": prefix_id,
                    "not_reachable": prefix_id is None,
                    "prohibited_content": [],
                })
        payload = hypothesis.model_dump(mode="json")
        plan["hypotheses"][name] = {
            "source_artifact": str(artifact_path.resolve()),
            "sha256": hashlib.sha256(
                json.dumps(payload, sort_keys=True).encode("utf-8")
            ).hexdigest(),
            "hypothesis": payload,
            "assignments": assignments,
        }
    _write_json(experiment_dir / "intervention" / "plan.json", plan)
    return plan


async def run_intervention(args: argparse.Namespace) -> dict[str, Any]:
    experiment_dir = args.experiment_dir.resolve()
    _require_stage_two(experiment_dir)
    plan = _read_json(experiment_dir / "intervention" / "plan.json")
    config = OpenAICompatibleConfig.from_env(
        env_file=Path(plan["env_file"]), prefix="TEACHER"
    )
    actual_thinking = config.thinking_mode or (
        "enabled" if config.ollama_think else "disabled"
    )
    if actual_thinking != args.thinking_mode:
        raise ValueError(
            f"requested thinking={args.thinking_mode}, actual={actual_thinking}"
        )
    effects = InterventionEffects(
        role_runner=InterventionRoleRunner(
            env_file=Path(plan["env_file"]), max_steps_per_activation=20,
            teacher_judge=True,
        ),
        worker_template_root=Path("harness_templates/teacher/intervention_worker"),
        student_template_root=Path(plan["student_template_root"]),
        env_file=Path(plan["env_file"]), student_max_steps=20,
    )
    output: dict[str, Any] = {"schema_version": 1, "hypotheses": {}}
    for name, item in plan["hypotheses"].items():
        assignments = [
            {key: value for key, value in assignment.items() if key != "not_reachable"}
            for assignment in item["assignments"] if not assignment["not_reachable"]
        ]
        result = await effects.execute_batch(
            assignments=assignments, hypothesis=item["hypothesis"],
            rollout_file=Path(plan["rollout_file"]), max_workers=args.max_workers,
            work_dir=experiment_dir / "intervention" / name / "batch",
        )
        output["hypotheses"][name] = {
            "results": result.outcome["results"],
            "trial_paths": list(result.artifact_refs.values()),
            "usage": result.usage,
        }
    _write_json(experiment_dir / "intervention" / "run_summary.json", output)
    return output


async def review_trials(args: argparse.Namespace) -> dict[str, Any]:
    experiment_dir = args.experiment_dir.resolve()
    _require_stage_two(experiment_dir)
    plan = _read_json(experiment_dir / "intervention" / "plan.json")
    runs = _read_json(experiment_dir / "intervention" / "run_summary.json")
    semaphore = asyncio.Semaphore(args.max_workers)
    output: dict[str, Any] = {"schema_version": 1, "hypotheses": {}}

    async def review_one(
        name: str,
        hypothesis: dict[str, Any],
        index: int,
        trial_path: Path,
    ) -> Path:
        destination = (
            experiment_dir / "trial_reviews" / name
            / f"trial_review_{index:03d}.json"
        )
        if destination.is_file():
            artifact = _read_json(destination)
            TrialReview.model_validate(artifact.get("output"))
            return destination.resolve()
        async with semaphore:
            artifact = await NativeChatRoleRunner(
                env_file=args.env_file, max_turns=20
            ).run(
                template_root=Path("harness_templates/teacher/trial_reviewer"),
                role_input={
                    "hypothesis": hypothesis,
                    "trial_ref": trial_path.parent.name,
                },
                resource_config=TeacherResourceConfig(trial_files=[trial_path]),
                role_id="trial_reviewer", role_version=1,
            )
        TrialReview.model_validate(artifact.get("output"))
        _write_json(destination, artifact)
        return destination.resolve()

    for name, item in plan["hypotheses"].items():
        trial_paths = [Path(path) for path in runs["hypotheses"][name]["trial_paths"]]
        review_paths = await asyncio.gather(*[
            review_one(name, item["hypothesis"], index, trial_path)
            for index, trial_path in enumerate(trial_paths, start=1)
        ])
        output["hypotheses"][name] = {
            "trial_paths": [str(path.resolve()) for path in trial_paths],
            "review_paths": [str(path) for path in review_paths],
        }
    _write_json(experiment_dir / "trial_reviews" / "summary.json", output)
    return output


async def review_evidence(args: argparse.Namespace) -> dict[str, Any]:
    experiment_dir = args.experiment_dir.resolve()
    _require_stage_two(experiment_dir)
    plan = _read_json(experiment_dir / "intervention" / "plan.json")
    reviews = _read_json(experiment_dir / "trial_reviews" / "summary.json")
    output: dict[str, Any] = {"schema_version": 1, "hypotheses": {}}
    for name, item in plan["hypotheses"].items():
        trial_paths = [Path(path) for path in reviews["hypotheses"][name]["trial_paths"]]
        trial_artifacts = [_read_json(path) for path in trial_paths]
        review_artifacts = [
            _read_json(Path(path))
            for path in reviews["hypotheses"][name]["review_paths"]
        ]
        trial_reviews = [
            TrialReview.model_validate(artifact["output"])
            for artifact in review_artifacts
        ]
        hypothesis = InterventionHypothesis.model_validate(item["hypothesis"])
        aggregate = aggregate_trial_observations(trial_artifacts, trial_paths)
        coverage = summarize_evidence_coverage(
            hypothesis, trial_artifacts, trial_reviews
        )
        budget = EvidenceReviewBudget(
            max_trials_per_hypothesis=len(trial_paths),
            trials_used=len(trial_paths), trials_remaining=0,
            max_trial_assignments=len(trial_paths),
            assignments_used=len(trial_paths), assignments_remaining=0,
            conclusion_required=True,
        )
        artifact = await NativeChatRoleRunner(
            env_file=args.env_file, max_turns=20
        ).run(
            template_root=Path("harness_templates/teacher/evidence_reviewer"),
            role_input={
                "hypothesis": hypothesis.model_dump(mode="json"),
                "aggregate_observations": aggregate,
                "trial_reviews": [r.model_dump(mode="json") for r in trial_reviews],
                "coverage_summary": coverage.model_dump(mode="json"),
                "budget": budget.model_dump(mode="json"),
                "prior_obligation": None,
            },
            resource_config=TeacherResourceConfig(),
            role_id="evidence_reviewer", role_version=1,
        )
        review = EvidenceReview.model_validate(artifact["output"])
        destination = experiment_dir / "evidence_reviews" / name / "role.json"
        _write_json(destination, artifact)
        output["hypotheses"][name] = {
            "output": review.model_dump(mode="json"),
            "coverage_summary": coverage.model_dump(mode="json"),
            "aggregate_observations": aggregate,
            "artifact": str(destination.resolve()),
        }
    _write_json(experiment_dir / "evidence_reviews" / "summary.json", output)
    return output


def finalize_summary(args: argparse.Namespace) -> dict[str, Any]:
    experiment_dir = args.experiment_dir.resolve()
    summary = _read_json(experiment_dir / "summary.json")
    evidence = _read_json(experiment_dir / "evidence_reviews" / "summary.json")
    downstream: dict[str, Any] = {"status": "completed", "hypotheses": {}}
    for name, item in evidence["hypotheses"].items():
        output = item["output"]
        aggregate = item["aggregate_observations"]
        coverage = item["coverage_summary"]
        phase = coverage["phase_coverage"][0]
        downstream["hypotheses"][name] = {
            "evidence_decision": output["decision"],
            "phase_status": output["phase_findings"][0]["status"],
            "trial_count": aggregate["trial_count"],
            "positive_count": phase["positive_count"],
            "negative_count": phase["negative_count"],
            "positive_distinct_examples": phase["positive_distinct_examples"],
            "negative_distinct_examples": phase["negative_distinct_examples"],
            "intervention_applied_count": phase["intervention_applied_count"],
            "correct_non_intervention_count": phase["correct_non_intervention_count"],
            "answer_changed_count": aggregate["answer_changed_count"],
            "branch_continuation_tool_calls": aggregate["branch_continuation_tool_calls"],
            "branch_continuation_model_calls": aggregate["branch_continuation_model_calls"],
            "default_coverage_met": coverage["default_requirements_met"],
            "assessment": output["assessment"],
            "key_risk": output["key_risk"],
        }
    summary["stage_two"] = downstream
    summary["formal_template_unchanged"] = _formal_template_unchanged(
        _read_json(experiment_dir / "manifest.json")
    )
    summary["status"] = "completed"
    summary["decision"] = "revise_hypotheses_no_distillation_or_production_migration"
    summary["conclusion"] = (
        "Researcher semantic repair passed; runtime token optimization missed "
        "the preregistered 15% target; both downstream hypotheses require "
        "revision based on actual Trial evidence."
    )
    _write_json(experiment_dir / "summary.json", summary)
    return summary


def detect_future_fact_risk(hypothesis: dict[str, Any]) -> list[str]:
    """Return post_tool condition fragments that appear to require future facts."""

    risks = []
    for directive in hypothesis.get("phase_plan", []):
        if not isinstance(directive, dict) or directive.get("phase") != "post_tool":
            continue
        condition = str(directive.get("activation_condition", ""))
        if any(pattern.search(condition) for pattern in _FUTURE_FACT_PATTERNS):
            risks.append(condition)
    return risks


def _review_direction(direction: dict[str, Any]) -> dict[str, Any]:
    """Omit identity-bearing evidence refs from an anonymous review packet."""

    return {
        key: direction[key]
        for key in ("pattern", "applicability", "caveats")
        if key in direction
    }


def select_first_compatible_prefix(
    timeline: list[dict[str, Any]], phase: str
) -> int | None:
    """Select the earliest deterministic prefix compatible with a phase."""

    compatible = [
        int(item["prefix_id"])
        for item in timeline
        if item.get("phase") == phase and isinstance(item.get("prefix_id"), int)
    ]
    return min(compatible) if compatible else None


def worker_config_with_thinking(
    base: OpenAICompatibleConfig, thinking_mode: str
) -> OpenAICompatibleConfig:
    """Override only the Intervention Executor thinking request setting."""

    if thinking_mode not in {"enabled", "disabled"}:
        raise ValueError("thinking_mode must be enabled or disabled")
    if base.thinking_mode is None and base.ollama_think is None:
        raise ValueError("provider does not expose an explicit thinking switch")
    if base.ollama_think is not None:
        return replace(
            base,
            ollama_think=thinking_mode == "enabled",
            thinking_mode=None,
        )
    return replace(base, thinking_mode=thinking_mode)


async def _run_researcher_once(
    *,
    template_root: Path,
    direction: dict[str, Any],
    resource_config: TeacherResourceConfig,
    config: OpenAICompatibleConfig,
    max_turns: int,
    artifact_path: Path,
) -> dict[str, Any]:
    if artifact_path.is_file():
        return _read_json(artifact_path)
    try:
        artifact = await NativeChatRoleRunner(
            config=config, max_turns=max_turns
        ).run(
            template_root=template_root,
            role_input={"problem_direction": direction},
            resource_config=resource_config,
            role_id="hypothesis_researcher",
            role_version=1,
        )
    except TeacherRoleRunFailed as exc:
        artifact = exc.failure_artifact
    _write_json(artifact_path, artifact)
    return artifact


def _role_summary(artifact: dict[str, Any]) -> dict[str, Any]:
    output = artifact.get("output")
    valid = False
    if isinstance(output, dict):
        InterventionHypothesis.model_validate(output)
        valid = True
    usage = artifact.get("usage")
    return {
        "completed": valid,
        "fork_phase": output.get("fork_phase") if isinstance(output, dict) else None,
        "requests": usage.get("requests") if isinstance(usage, dict) else None,
        "tool_calls": len(artifact.get("tool_calls", [])),
        "total_tokens": usage.get("total_tokens") if isinstance(usage, dict) else None,
        "error": artifact.get("error"),
    }


def validate_semantic_review(value: dict[str, Any]) -> None:
    reviews = value.get("reviews")
    if not isinstance(reviews, list) or len(reviews) != 18:
        raise ValueError("semantic review must contain exactly 18 reviews")
    expected_ids = {f"A{index:02d}" for index in range(1, 19)}
    actual_ids = set()
    for review in reviews:
        if not isinstance(review, dict):
            raise TypeError("automatic review item must be an object")
        anonymous_id = _required_string(review, "anonymous_id")
        actual_ids.add(anonymous_id)
        criteria = _required_object(review, "criteria")
        if set(criteria) != set(_CRITERIA):
            raise ValueError(f"criteria mismatch: {anonymous_id}")
        total = 0
        for name, item in criteria.items():
            if not isinstance(item, dict) or item.get("score") not in {0, 1}:
                raise ValueError(f"invalid score: {anonymous_id}/{name}")
            _required_string(item, "failure_quote")
            _required_string(item, "hypothesis_quote")
            _required_string(item, "reason")
            total += int(item["score"])
        if review.get("total") != total:
            raise ValueError(f"total mismatch: {anonymous_id}")
        if not isinstance(review.get("protocol_legal"), bool):
            raise TypeError(f"protocol flag invalid: {anonymous_id}")
        if not isinstance(review.get("case_leakage"), bool):
            raise TypeError(f"leakage flag invalid: {anonymous_id}")
        if not isinstance(review.get("preventive_claim_explicit"), bool):
            raise TypeError(f"preventive flag invalid: {anonymous_id}")
        if not isinstance(review.get("recovery_obligation_present"), bool):
            raise TypeError(f"recovery obligation flag invalid: {anonymous_id}")
    if actual_ids != expected_ids:
        raise ValueError("anonymous IDs are incomplete or duplicated")


def _validate_semantic_quotes(
    experiment_dir: Path,
    semantic_review: dict[str, Any],
) -> None:
    packet = _read_json(
        experiment_dir / "researcher_review" / "anonymous_packet.json"
    )
    handoffs = packet.get("handoffs")
    if not isinstance(handoffs, list):
        raise TypeError("anonymous review packet handoffs must be an array")
    by_id = {
        _required_string(item, "anonymous_id"): item
        for item in handoffs
        if isinstance(item, dict)
    }
    for review in semantic_review["reviews"]:
        anonymous_id = _required_string(review, "anonymous_id")
        handoff = by_id.get(anonymous_id)
        if handoff is None:
            raise ValueError(f"semantic review references unknown ID: {anonymous_id}")
        direction_text = json.dumps(
            handoff.get("failure_direction"), ensure_ascii=False
        )
        hypothesis_text = json.dumps(
            handoff.get("hypothesis"), ensure_ascii=False
        )
        for name, judgment in review["criteria"].items():
            failure_quote = _required_string(judgment, "failure_quote")
            hypothesis_quote = _required_string(judgment, "hypothesis_quote")
            if failure_quote not in direction_text:
                raise ValueError(
                    f"failure quote is not exact: {anonymous_id}/{name}"
                )
            if hypothesis_quote not in hypothesis_text:
                raise ValueError(
                    f"hypothesis quote is not exact: {anonymous_id}/{name}"
                )


def _configured_model(
    base: OpenAICompatibleConfig,
    *,
    model_id: str | None,
    seed: int,
    max_tokens: int,
    temperature: float,
    thinking_mode: str,
) -> OpenAICompatibleConfig:
    ollama_think = base.ollama_think
    provider_thinking = base.thinking_mode
    if thinking_mode != "inherit":
        if ollama_think is not None:
            ollama_think = thinking_mode == "enabled"
            provider_thinking = None
        else:
            provider_thinking = thinking_mode
    return replace(
        base,
        model_id=model_id or base.model_id,
        seed=seed,
        max_tokens=max_tokens,
        temperature=temperature,
        ollama_think=ollama_think,
        thinking_mode=provider_thinking,
    )


def _hypothesis_phase(
    experiment_dir: Path,
    input_index: int,
    variant: str,
    repetition: int,
) -> str:
    artifact = _read_json(
        experiment_dir
        / "researcher_ab"
        / f"input_{input_index:02d}"
        / f"{variant}_{repetition:02d}.json"
    )
    return _required_string(_required_object(artifact, "output"), "fork_phase")


def _verify_frozen_hashes(
    experiment_dir: Path, manifest: dict[str, Any]
) -> None:
    hashes = _required_object(manifest, "hashes")
    for variant in _VARIANTS:
        actual = _tree_digest(
            experiment_dir / "templates" / variant / "hypothesis_researcher"
        )
        if actual != hashes[f"{variant}_template"]:
            raise ValueError(f"frozen {variant} template hash changed")
    input_hashes = _required_object(hashes, "inputs")
    for stem, expected in input_hashes.items():
        path = experiment_dir / "inputs" / "failure_directions" / f"{stem}.json"
        if _digest(path) != expected:
            raise ValueError(f"frozen input hash changed: {stem}")


def _formal_template_unchanged(manifest: dict[str, Any]) -> bool:
    path = Path(_required_string(manifest, "formal_template_path"))
    expected = _required_object(manifest, "hashes")["formal_template_before"]
    return _tree_digest(path) == expected


def _copy_or_verify_file(source: Path, target: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    if target.is_file():
        if _digest(source) != _digest(target):
            raise ValueError(f"existing frozen file differs from source: {target}")
        return
    shutil.copy2(source, target)


def _copy_or_verify_tree(source: Path, target: Path) -> None:
    if not source.is_dir():
        raise FileNotFoundError(source)
    if target.is_dir():
        if _tree_digest(source) != _tree_digest(target):
            raise ValueError(f"existing frozen tree differs from source: {target}")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(
        item for item in root.rglob("*") if item.is_file() and "__pycache__" not in item.parts
    ):
        if path.suffix == ".pyc":
            continue
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        first_newline = stripped.find("\n")
        last_fence = stripped.rfind("```")
        if first_newline >= 0 and last_fence > first_newline:
            stripped = stripped[first_newline + 1 : last_fence].strip()
    value = json.loads(stripped)
    if not isinstance(value, dict):
        raise TypeError("model output must be a JSON object")
    return value


def _required_object(value: dict[str, Any], key: str) -> dict[str, Any]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise TypeError(f"field '{key}' must be an object")
    return item


def _required_string(value: dict[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise TypeError(f"field '{key}' must be a non-empty string")
    return item


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"JSON artifact must be an object: {path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _not_yet_implemented(command: str) -> None:
    raise RuntimeError(
        f"{command} is gated on a passing stage-one summary and is not "
        "available before that decision"
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    if args.command == "prepare-repair":
        result = prepare(args)
    elif args.command == "run-researcher-repair":
        result = asyncio.run(run_researcher_ab(args))
    elif args.command == "prepare-semantic-review":
        result = prepare_researcher_review(args)
    elif args.command == "summarize-researcher":
        result = summarize(args)
    elif args.command == "prepare-intervention":
        result = prepare_intervention(args)
    elif args.command == "run-intervention":
        result = asyncio.run(run_intervention(args))
    elif args.command == "review-trials":
        result = asyncio.run(review_trials(args))
    elif args.command == "review-evidence":
        result = asyncio.run(review_evidence(args))
    elif args.command == "summarize":
        result = finalize_summary(args)
    else:
        _not_yet_implemented(args.command)
        return
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
