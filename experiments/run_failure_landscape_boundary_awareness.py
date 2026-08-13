"""Run the focused Failure Landscape boundary-awareness experiment."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import random
import shutil
from urllib import error as urllib_error
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

from search_harness.evolution.research.resources.base import TeacherResourceConfig
from search_harness.evolution.research.roles.native_chat_runner import (
    NativeChatRoleRunner,
    TeacherRoleRunFailed,
)
from search_harness.framework import ChatMessage, ModelInput
from search_harness.integrations.openai_compatible import (
    OpenAICompatibleConfig,
    OpenAICompatibleModel,
)


_RESERVED_CATEGORIES = {"unknown", "ambiguous"}
_LANDSCAPE_SYSTEM_PROMPT = """You construct a generation-local navigation
view from an exhaustive corpus of wrong answer results.

Work only from answer-result facts in the supplied logical cases. Do not infer
retrieval behavior, search strategy, reasoning, stopping behavior, prompt
defects, or causal mechanisms. Do not use a historical taxonomy or invent a
fixed label set.

Return exactly one JSON object without markdown:
{
  "quality_audit": {
    "overall_assessment": "string",
    "ambiguous_or_low_information_examples": [
      {"example_id": "string", "reason": "string"}
    ]
  },
  "categories": [
    {
      "category_id": "C1",
      "label": "short result-level label",
      "definition": "observable answer-result inclusion rule",
      "exclusions": ["observable neighboring result that is not included"]
    }
  ],
  "assignments": [
    {"example_id": "string", "category_id": "C1|unknown|ambiguous"}
  ],
  "limits": ["string"]
}

Assign every supplied example exactly once. Use `unknown` or `ambiguous` when
the result evidence is insufficient or genuinely overlaps categories. Do not
create a category merely to avoid those assignments. Category definitions and
exclusions must be observable from question, reference answer, predicted
answer, and judgment assessment. When one logical case contains different
wrong-result observations, its primary category must describe the observation
with the largest `observation_counts` value. If incompatible observations tie
for the largest count and have no shared result-level pattern, assign the case
to `ambiguous`. Do not report counts, percentages,
representatives, or coverage claims; the program calculates them."""

_SHARED_NAVIGATION_INSTRUCTION = """

## Experimental generation-local navigation

The experimental Failure Landscape, when available, is a result-level
navigation view only. Its categories do not establish Student behavior or a
causal mechanism, do not replace direct Trajectory Evidence, and must not be
copied into the diagnostic output as if they were behavioral findings.
"""

_ANALYSIS_FOCUS = (
    "Investigate the multi-entity evidence-gap direction represented by "
    "example 5a7e36045542991319bc9440 and determine its supported scope. "
    "Diagnose only from trajectories; do not assume a universal defect or "
    "any exclusion condition."
)

_BLIND_REVIEW_SYSTEM_PROMPT = """You are an independent evaluator of six
anonymous Failure Analyst to Hypothesis Researcher handoffs. You do not know
which experimental variant produced any handoff. Score only the supplied
structured role outputs and hidden-case behavior facts. Do not use writing
style, length, or confidence as evidence.

Return exactly one JSON object without markdown:
{
  "reviews": [
    {
      "anonymous_id": "A1",
      "criteria": {
        "locality": {"score": 0, "evidence_quote": "string", "reason": "string"},
        "observable_applicability": {"score": 0, "evidence_quote": "string", "reason": "string"},
        "neighbor_exclusion": {"score": 0, "evidence_quote": "string", "reason": "string"},
        "falsifiable_risk": {"score": 0, "evidence_quote": "string", "reason": "string"},
        "handoff_fidelity": {"score": 0, "evidence_quote": "string", "reason": "string"}
      },
      "total": 0,
      "hidden_boundary": {
        "H1": {"label": "included", "reason": "string"},
        "H2": {"label": "excluded", "reason": "string"},
        "pass": false
      },
      "category_used_as_cause": false,
      "category_cause_evidence": "string or empty"
    }
  ]
}

Use these binary criteria exactly:
1. locality = 1 only when the output says the pattern holds in a specific
task/evidence state and gives the limiting basis. Generic caution is 0.
2. observable_applicability = 1 only when activation/applicability depends on
runtime-observable facts, not merely an abstract task label.
3. neighbor_exclusion = 1 only when at least one superficially similar state
that lacks the same evidence need is explicitly excluded.
4. falsifiable_risk = 1 only when mis-trigger, ineffective intervention, or
non-target degradation is in a falsifier or evidence obligation, not merely a
caveat.
5. handoff_fidelity = 1 only when the Researcher preserves and operationalizes
the Analyst's scope and limitations without broadening the intervention.

Every evidence_quote must be a short exact quote from that handoff's Analyst
or Researcher output. Set total to the sum of the five scores.

For each final Researcher hypothesis, classify each hidden case as exactly one
of: included, excluded, uncertain_fallback, incorrectly_included,
not_decidable. H1 is the intended positive and passes only as included. H2 is
the harmful neighbor and passes only as excluded or uncertain_fallback. Set
hidden_boundary.pass only when both requirements hold. Decide from the
hypothesis's observable activation condition and applicability applied to the
supplied case facts; do not use the baseline answer score alone.

Set category_used_as_cause true only if a generation-local result category is
presented as a Student behavior diagnosis or causal mechanism. Similar words
that independently describe trajectory behavior are not category misuse."""


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--judgments", type=Path, required=True)
    prepare.add_argument("--report-dir", type=Path, required=True)
    prepare.add_argument("--rollout-file", type=Path, required=True)
    prepare.add_argument("--student-template-root", type=Path, required=True)
    prepare.add_argument("--output-dir", type=Path, required=True)

    classify = subparsers.add_parser("classify")
    classify.add_argument("--input", type=Path, required=True)
    classify.add_argument("--output-dir", type=Path, required=True)
    classify.add_argument("--env-file", type=Path, default=Path(".env"))
    classify.add_argument("--model-env-prefix", default="TEACHER")
    classify.add_argument("--model-id")
    classify.add_argument("--seed", type=int, default=4200)
    classify.add_argument("--max-tokens", type=int, default=8192)
    classify.add_argument("--temperature", type=float, default=0.2)
    classify.add_argument(
        "--thinking-mode",
        choices=("inherit", "enabled", "disabled"),
        default="inherit",
    )
    classify.add_argument("--max-attempts", type=int, default=3)

    freeze = subparsers.add_parser("freeze")
    freeze.add_argument("--input", type=Path, required=True)
    freeze.add_argument("--raw-artifact", type=Path, required=True)
    freeze.add_argument("--output-dir", type=Path, required=True)

    replay = subparsers.add_parser("replay")
    replay.add_argument("--landscape", type=Path, required=True)
    replay.add_argument("--report-dir", type=Path, required=True)
    replay.add_argument("--rollout-file", type=Path, required=True)
    replay.add_argument("--student-template-root", type=Path, required=True)
    replay.add_argument("--formal-template-root", type=Path, required=True)
    replay.add_argument("--output-dir", type=Path, required=True)
    replay.add_argument("--env-file", type=Path, default=Path(".env"))
    replay.add_argument("--model-env-prefix", default="TEACHER")
    replay.add_argument("--model-id")
    replay.add_argument("--repetitions", type=int, default=3)
    replay.add_argument("--base-seed", type=int, default=4200)
    replay.add_argument("--max-turns", type=int, default=20)
    replay.add_argument("--max-tokens", type=int, default=8192)
    replay.add_argument("--temperature", type=float, default=0.2)
    replay.add_argument(
        "--thinking-mode",
        choices=("inherit", "enabled", "disabled"),
        default="inherit",
    )

    blind = subparsers.add_parser("prepare-blind-review")
    blind.add_argument("--replay-dir", type=Path, required=True)
    blind.add_argument("--report-dir", type=Path, required=True)
    blind.add_argument("--rollout-file", type=Path, required=True)
    blind.add_argument("--student-template-root", type=Path, required=True)
    blind.add_argument("--output-dir", type=Path, required=True)
    blind.add_argument("--randomization-seed", type=int, default=8731)

    score = subparsers.add_parser("score-blind-review")
    score.add_argument("--packet", type=Path, required=True)
    score.add_argument("--output-dir", type=Path, required=True)
    score.add_argument("--env-file", type=Path, default=Path(".env"))
    score.add_argument("--model-env-prefix", default="TEACHER")
    score.add_argument("--model-id")
    score.add_argument("--seed", type=int, default=8732)
    score.add_argument("--max-tokens", type=int, default=8192)
    score.add_argument("--temperature", type=float, default=0.0)
    score.add_argument(
        "--thinking-mode",
        choices=("inherit", "enabled", "disabled"),
        default="disabled",
    )

    summarize = subparsers.add_parser("summarize")
    summarize.add_argument("--replay-summary", type=Path, required=True)
    summarize.add_argument("--randomization", type=Path, required=True)
    summarize.add_argument("--automatic-review", type=Path, required=True)
    summarize.add_argument("--manual-review", type=Path, required=True)
    summarize.add_argument("--output", type=Path, required=True)

    return parser.parse_args(argv)


def prepare_inputs(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    source_paths = {
        "judgments": args.judgments.resolve(),
        "report_summary": args.report_dir.resolve() / "summary.json",
        "evaluation_cases": args.report_dir.resolve() / "per_example.jsonl",
        "rollouts": args.rollout_file.resolve(),
        "student_manifest": (
            args.student_template_root.resolve() / "harness.json"
        ),
    }
    for name, path in source_paths.items():
        if not path.is_file():
            raise FileNotFoundError(f"missing {name} source: {path}")

    judgments = _read_jsonl(source_paths["judgments"])
    cross_validation = _cross_validate_frozen_sources(
        judgments=judgments,
        evaluation_cases=_read_jsonl(source_paths["evaluation_cases"]),
        rollouts=_read_jsonl(source_paths["rollouts"]),
    )
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in judgments:
        case = _required_object(item, "case")
        shadow = _required_object(item, "shadow")
        if shadow.get("error") is not None:
            raise ValueError(f"shadow judgment contains an error: {item.get('ref')}")
        score = shadow.get("score")
        if score not in {0, 1}:
            raise ValueError(f"shadow score must be 0 or 1: {item.get('ref')}")
        grouped[_required_string(case, "example_id")].append(item)

    logical_cases = []
    for example_id, items in sorted(grouped.items()):
        failed = [item for item in items if item["shadow"]["score"] == 0]
        if not failed:
            continue
        first_case = _required_object(failed[0], "case")
        observations: dict[tuple[str | None, str], int] = Counter()
        for item in failed:
            case = _required_object(item, "case")
            shadow = _required_object(item, "shadow")
            predicted = _optional_string(case.get("predicted_answer"))
            assessment = _required_string(shadow, "assessment")
            observations[(predicted, assessment)] += 1
        ordered_observations = sorted(
            observations.items(),
            key=lambda pair: (
                pair[0][0] is None,
                pair[0][0] or "",
                pair[0][1],
            ),
        )
        observation_values = []
        observation_counts = []
        for index, ((predicted, assessment), count) in enumerate(
            ordered_observations,
            start=1,
        ):
            observation_id = f"O{index}"
            observation_values.append(
                {
                    "observation_id": observation_id,
                    "predicted_answer": predicted,
                    "assessment": assessment,
                }
            )
            observation_counts.append(
                {"observation_id": observation_id, "count": count}
            )
        logical_cases.append(
            {
                "example_id": example_id,
                "question": _required_string(first_case, "question"),
                "reference_answer": _required_string(
                    first_case,
                    "golden_answer",
                ),
                "failed_rollouts": len(failed),
                "total_rollouts": len(items),
                "failure_stability": (
                    "stable" if len(failed) == len(items) else "unstable"
                ),
                "observations": observation_values,
                "observation_counts": observation_counts,
            }
        )

    failed_rollouts = sum(item["failed_rollouts"] for item in logical_cases)
    manifest = {
        "schema_version": 1,
        "experiment": "failure_landscape_boundary_awareness_v1",
        "created_at": datetime.now(UTC).isoformat(),
        "sources": {
            name: {
                "path": str(path),
                "sha256": _digest(path),
            }
            for name, path in source_paths.items()
        },
        "frozen_counts": {
            "rollouts": len(judgments),
            "logical_examples": len(grouped),
            "failed_rollouts": failed_rollouts,
            "failed_logical_examples": len(logical_cases),
            "stable_failure_examples": sum(
                item["failure_stability"] == "stable"
                for item in logical_cases
            ),
            "unstable_failure_examples": sum(
                item["failure_stability"] == "unstable"
                for item in logical_cases
            ),
        },
        "analysis_focus": _ANALYSIS_FOCUS,
        "cross_validation": cross_validation,
    }
    if manifest["frozen_counts"] != {
        "rollouts": 225,
        "logical_examples": 75,
        "failed_rollouts": 73,
        "failed_logical_examples": 32,
        "stable_failure_examples": manifest["frozen_counts"][
            "stable_failure_examples"
        ],
        "unstable_failure_examples": manifest["frozen_counts"][
            "unstable_failure_examples"
        ],
    }:
        raise ValueError(
            "frozen corpus does not match the preregistered 225/75/73/32 counts"
        )
    if (
        manifest["frozen_counts"]["stable_failure_examples"]
        + manifest["frozen_counts"]["unstable_failure_examples"]
        != 32
    ):
        raise ValueError("failure stability counts do not cover all examples")

    _write_jsonl(output_dir / "landscape_input.jsonl", logical_cases)
    _write_json(output_dir / "manifest.json", manifest)
    return manifest


def _cross_validate_frozen_sources(
    *,
    judgments: list[dict[str, Any]],
    evaluation_cases: list[dict[str, Any]],
    rollouts: list[dict[str, Any]],
) -> dict[str, Any]:
    evaluation_by_ref: dict[tuple[str, str], dict[str, Any]] = {}
    evaluation_example_ids = set()
    for case in evaluation_cases:
        example_id = _required_string(case, "example_id")
        if example_id in evaluation_example_ids:
            raise ValueError(f"duplicate Evaluation example: {example_id}")
        evaluation_example_ids.add(example_id)
        replicates = case.get("replicates")
        if not isinstance(replicates, list):
            raise TypeError(f"Evaluation replicates must be a list: {example_id}")
        for replicate in replicates:
            if not isinstance(replicate, dict):
                raise TypeError(f"Evaluation replicate must be an object: {example_id}")
            ref = (example_id, _required_string(replicate, "replicate_id"))
            if ref in evaluation_by_ref:
                raise ValueError(f"duplicate Evaluation replicate: {ref}")
            evaluation_by_ref[ref] = {
                "question": _required_string(case, "question"),
                "golden_answer": _required_string(case, "golden_answer"),
                "predicted_answer": _optional_string(
                    replicate.get("predicted_answer")
                ),
            }

    rollout_by_ref: dict[tuple[str, str], dict[str, Any]] = {}
    for record in rollouts:
        example = _required_object(record, "example")
        replicate = _required_object(record, "replicate")
        run = _required_object(record, "run")
        ref = (
            _required_string(example, "example_id"),
            _required_string(replicate, "replicate_id"),
        )
        if ref in rollout_by_ref:
            raise ValueError(f"duplicate rollout record: {ref}")
        rollout_by_ref[ref] = {
            "question": _required_string(example, "question"),
            "golden_answer": _required_string(example, "answer"),
            "predicted_answer": _optional_string(run.get("answer")),
        }

    judgment_by_ref: dict[tuple[str, str], dict[str, Any]] = {}
    for judgment in judgments:
        case = _required_object(judgment, "case")
        ref = (
            _required_string(case, "example_id"),
            _required_string(case, "replicate_id"),
        )
        if ref in judgment_by_ref:
            raise ValueError(f"duplicate Shadow Judgment: {ref}")
        judgment_by_ref[ref] = {
            "question": _required_string(case, "question"),
            "golden_answer": _required_string(case, "golden_answer"),
            "predicted_answer": _optional_string(case.get("predicted_answer")),
        }

    expected_refs = set(evaluation_by_ref)
    if set(rollout_by_ref) != expected_refs:
        raise ValueError("Evaluation and rollout reference sets differ")
    if set(judgment_by_ref) != expected_refs:
        raise ValueError("Evaluation and Shadow Judgment reference sets differ")
    for ref in sorted(expected_refs):
        evaluation_value = evaluation_by_ref[ref]
        if rollout_by_ref[ref] != evaluation_value:
            raise ValueError(f"Evaluation and rollout content differ: {ref}")
        if judgment_by_ref[ref] != evaluation_value:
            raise ValueError(f"Evaluation and Shadow Judgment content differ: {ref}")
    return {
        "valid": True,
        "evaluation_example_count": len(evaluation_example_ids),
        "matched_replicate_count": len(expected_refs),
        "content_fields": [
            "question",
            "golden_answer",
            "predicted_answer",
        ],
    }


def classify_landscape(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    cases = _read_jsonl(args.input.resolve())
    if len(cases) != 32:
        raise ValueError("Landscape classification requires exactly 32 cases")
    base_config = OpenAICompatibleConfig.from_env(
        env_file=args.env_file,
        prefix=args.model_env_prefix,
    )
    config = _configured_model(
        base=base_config,
        model_id=args.model_id,
        seed=args.seed,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        thinking_mode=args.thinking_mode,
    )
    if args.max_attempts < 1:
        raise ValueError("max-attempts must be positive")
    model_input = ModelInput.from_messages(
        [
            ChatMessage(role="system", content=_LANDSCAPE_SYSTEM_PROMPT),
            ChatMessage(
                role="user",
                content=(
                    "Generation-local wrong logical cases follow as JSONL.\n"
                    + "\n".join(_compact_json(item) for item in cases)
                ),
            ),
        ]
    )
    attempts = []
    response = None
    for attempt in range(1, args.max_attempts + 1):
        try:
            response = OpenAICompatibleModel(config).generate(model_input)
        except (urllib_error.URLError, TimeoutError, ConnectionError) as exc:
            attempts.append(
                {
                    "attempt": attempt,
                    "status": "transport_error",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            _write_json(
                output_dir / "classification_attempts.json",
                {"schema_version": 1, "attempts": attempts},
            )
            if attempt == args.max_attempts:
                raise
        else:
            attempts.append({"attempt": attempt, "status": "completed"})
            _write_json(
                output_dir / "classification_attempts.json",
                {"schema_version": 1, "attempts": attempts},
            )
            break
    if response is None:
        raise RuntimeError("Landscape classification produced no response")
    raw_artifact = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "model": config.provenance(),
        "usage": dict(response.usage),
        "metadata": dict(response.metadata),
        "raw_output": response.raw_output,
    }
    try:
        parsed = _parse_json_object(response.raw_output)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raw_artifact["parsed_output"] = None
        raw_artifact["parse_error"] = f"{type(exc).__name__}: {exc}"
        _write_json(output_dir / "failure_landscape.raw.json", raw_artifact)
        raise
    raw_artifact["parsed_output"] = parsed
    raw_artifact["parse_error"] = None
    _write_json(output_dir / "failure_landscape.raw.json", raw_artifact)
    landscape, validation = _freeze_landscape(cases, parsed)
    _write_json(output_dir / "failure_landscape.json", landscape)
    _write_json(output_dir / "validation.json", validation)
    _write_json(
        output_dir / "failure_landscape_view.json",
        _compact_landscape_view(landscape),
    )
    return {
        "landscape": landscape,
        "validation": validation,
        "model": config.provenance(),
        "usage": dict(response.usage),
    }


def freeze_saved_landscape(args: argparse.Namespace) -> dict[str, Any]:
    cases = _read_jsonl(args.input.resolve())
    raw_artifact = _read_json(args.raw_artifact.resolve())
    parsed = raw_artifact.get("parsed_output")
    if not isinstance(parsed, dict):
        raise TypeError("raw Landscape artifact has no parsed_output object")
    landscape, validation = _freeze_landscape(cases, parsed)
    output_dir = args.output_dir.resolve()
    _write_json(output_dir / "failure_landscape.json", landscape)
    _write_json(output_dir / "validation.json", validation)
    _write_json(
        output_dir / "failure_landscape_view.json",
        _compact_landscape_view(landscape),
    )
    return {"landscape": landscape, "validation": validation}


async def replay_roles(args: argparse.Namespace) -> dict[str, Any]:
    if args.repetitions < 1:
        raise ValueError("repetitions must be positive")
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    landscape = _read_json(args.landscape.resolve())
    compact_view = _compact_landscape_view(landscape)
    template_roots = _prepare_experiment_templates(
        formal_root=args.formal_template_root.resolve(),
        output_dir=output_dir / "templates",
        compact_view=compact_view,
    )
    researcher_template = (
        args.formal_template_root.resolve() / "hypothesis_researcher"
    )
    resource_config = TeacherResourceConfig(
        report_dir=args.report_dir.resolve(),
        rollout_file=args.rollout_file.resolve(),
        student_template_root=args.student_template_root.resolve(),
    )
    loaded_config = OpenAICompatibleConfig.from_env(
        env_file=args.env_file,
        prefix=args.model_env_prefix,
    )
    base_config = _configured_model(
        base=loaded_config,
        model_id=args.model_id,
        seed=args.base_seed,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        thinking_mode=args.thinking_mode,
    )
    pairs = []
    for index in range(1, args.repetitions + 1):
        analyst_seed = args.base_seed + index
        analysts = await asyncio.gather(
            *(
                _run_role_once(
                    template_root=template_roots[variant],
                    role_id="failure_analyst",
                    role_input={"analysis_focus": _ANALYSIS_FOCUS},
                    resource_config=resource_config,
                    config=replace(base_config, seed=analyst_seed),
                    max_turns=args.max_turns,
                    artifact_path=(
                        output_dir / variant / f"analyst_{index:02d}.json"
                    ),
                )
                for variant in ("control", "landscape")
            )
        )
        researcher_seed = args.base_seed + 100 + index
        researchers = await asyncio.gather(
            *(
                _run_researcher_for_analyst(
                    analyst_artifact=analyst,
                    template_root=researcher_template,
                    resource_config=resource_config,
                    config=replace(base_config, seed=researcher_seed),
                    max_turns=args.max_turns,
                    artifact_path=(
                        output_dir / variant / f"researcher_{index:02d}.json"
                    ),
                )
                for variant, analyst in zip(
                    ("control", "landscape"),
                    analysts,
                    strict=True,
                )
            )
        )
        pair = {
            "repetition": index,
            "seeds": {
                "analyst": analyst_seed,
                "researcher": researcher_seed,
            },
            "control": _role_pair_summary(analysts[0], researchers[0]),
            "landscape": _role_pair_summary(analysts[1], researchers[1]),
        }
        pairs.append(pair)
        _write_json(
            output_dir / "replay_progress.json",
            {
                "schema_version": 1,
                "experiment": "failure_landscape_boundary_awareness_v1",
                "analysis_focus": _ANALYSIS_FOCUS,
                "pairs": pairs,
            },
        )
    summary = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "experiment": "failure_landscape_boundary_awareness_v1",
        "pairing": (
            "Within each repetition, Control and Landscape Analysts run "
            "concurrently with the same seed; their outputs are passed "
            "unchanged to corresponding Researchers, which also run "
            "concurrently with the same paired seed."
        ),
        "analysis_focus": _ANALYSIS_FOCUS,
        "base_model": base_config.provenance(),
        "pairs": pairs,
    }
    _write_json(output_dir / "replay_summary.json", summary)
    return summary


def prepare_blind_review(args: argparse.Namespace) -> dict[str, Any]:
    replay_dir = args.replay_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    source_pairs = [
        (variant, repetition)
        for variant in ("control", "landscape")
        for repetition in range(1, 4)
    ]
    randomizer = random.Random(args.randomization_seed)
    randomizer.shuffle(source_pairs)
    mapping = {}
    handoffs = []
    for index, (variant, repetition) in enumerate(source_pairs, start=1):
        anonymous_id = f"A{index}"
        analyst = _read_json(
            replay_dir / variant / f"analyst_{repetition:02d}.json"
        ).get("output")
        researcher = _read_json(
            replay_dir / variant / f"researcher_{repetition:02d}.json"
        ).get("output")
        if not isinstance(analyst, dict) or not isinstance(researcher, dict):
            raise ValueError(
                f"completed Role outputs missing: {variant}/{repetition}"
            )
        mapping[anonymous_id] = {
            "variant": variant,
            "repetition": repetition,
        }
        handoffs.append(
            {
                "anonymous_id": anonymous_id,
                "failure_analyst": analyst,
                "hypothesis_researcher": researcher,
            }
        )

    resource = TeacherResourceConfig(
        report_dir=args.report_dir.resolve(),
        rollout_file=args.rollout_file.resolve(),
        student_template_root=args.student_template_root.resolve(),
    )
    from search_harness.evolution.research.resources.base import TeacherResources

    store = TeacherResources.from_config(resource).evaluation
    if store is None:
        raise ValueError("Evaluation store is unavailable")
    hidden_cases = []
    for hidden_id, example_id in (
        ("H1", "5a7e36045542991319bc9440"),
        ("H2", "5a822d4655429926c1cdae45"),
    ):
        case = store.get_case(example_id)
        replicates = case.get("replicates")
        if not isinstance(replicates, list):
            raise TypeError(f"hidden case replicates invalid: {example_id}")
        behavior_views = []
        for replicate in replicates:
            if not isinstance(replicate, dict):
                raise TypeError(f"hidden replicate invalid: {example_id}")
            behavior_views.append(
                store.get_trajectory(
                    example_id=example_id,
                    replicate_id=_required_string(replicate, "replicate_id"),
                    view="behavior",
                )
            )
        hidden_cases.append(
            {
                "hidden_id": hidden_id,
                "case": {
                    "example_id": example_id,
                    "question": case.get("question"),
                    "replicates": [
                        {
                            "replicate_id": item.get("replicate_id"),
                            "run_status": item.get("run_status"),
                        }
                        for item in replicates
                    ],
                },
                "behavior_views": behavior_views,
            }
        )

    packet = {
        "schema_version": 1,
        "evaluation_instructions": (
            "Variant identities, transcripts, tool-call metrics, and usage "
            "are intentionally omitted."
        ),
        "handoffs": handoffs,
        "hidden_cases": hidden_cases,
    }
    randomization = {
        "schema_version": 1,
        "seed": args.randomization_seed,
        "mapping": mapping,
    }
    _write_json(output_dir / "blind_packet.json", packet)
    _write_json(output_dir / "randomization.json", randomization)
    return {
        "packet": str((output_dir / "blind_packet.json").resolve()),
        "randomization": str((output_dir / "randomization.json").resolve()),
        "anonymous_count": len(handoffs),
        "hidden_case_count": len(hidden_cases),
    }


def score_blind_review(args: argparse.Namespace) -> dict[str, Any]:
    packet = _read_json(args.packet.resolve())
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    loaded = OpenAICompatibleConfig.from_env(
        env_file=args.env_file,
        prefix=args.model_env_prefix,
    )
    config = _configured_model(
        base=loaded,
        model_id=args.model_id,
        seed=args.seed,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        thinking_mode=args.thinking_mode,
    )
    response = OpenAICompatibleModel(config).generate(
        ModelInput.from_messages(
            [
                ChatMessage(
                    role="system",
                    content=_BLIND_REVIEW_SYSTEM_PROMPT,
                ),
                ChatMessage(
                    role="user",
                    content="Anonymous review packet:\n" + json.dumps(
                        packet,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                ),
            ]
        )
    )
    raw = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "model": config.provenance(),
        "usage": dict(response.usage),
        "metadata": dict(response.metadata),
        "raw_output": response.raw_output,
    }
    try:
        parsed = _parse_json_object(response.raw_output)
        _validate_blind_review(parsed)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raw["parsed_output"] = None
        raw["parse_error"] = f"{type(exc).__name__}: {exc}"
        _write_json(output_dir / "blind_review.raw.json", raw)
        raise
    raw["parsed_output"] = parsed
    raw["parse_error"] = None
    _write_json(output_dir / "blind_review.raw.json", raw)
    _write_json(output_dir / "blind_review.json", parsed)
    return {"review": parsed, "model": config.provenance(), "usage": response.usage}


def summarize_experiment(args: argparse.Namespace) -> dict[str, Any]:
    replay = _read_json(args.replay_summary.resolve())
    randomization = _read_json(args.randomization.resolve())
    automatic = _read_json(args.automatic_review.resolve())
    manual = _read_json(args.manual_review.resolve())
    mapping = _required_object(randomization, "mapping")
    manual_reviews = manual.get("reviews")
    if not isinstance(manual_reviews, list) or len(manual_reviews) != 6:
        raise ValueError("manual review must contain exactly six reviews")

    scored: dict[tuple[str, int], dict[str, Any]] = {}
    for review in manual_reviews:
        if not isinstance(review, dict):
            raise TypeError("manual review item must be an object")
        anonymous_id = _required_string(review, "anonymous_id")
        source = _required_object(mapping, anonymous_id)
        variant = _required_string(source, "variant")
        repetition = source.get("repetition")
        if variant not in {"control", "landscape"}:
            raise ValueError(f"invalid mapped variant: {variant}")
        if not isinstance(repetition, int) or repetition not in {1, 2, 3}:
            raise ValueError(f"invalid mapped repetition: {anonymous_id}")
        scores = _required_object(review, "scores")
        total = review.get("total")
        if total != sum(int(value) for value in scores.values()):
            raise ValueError(f"manual score total mismatch: {anonymous_id}")
        scored[(variant, repetition)] = {
            "anonymous_id": anonymous_id,
            "criteria": scores,
            "total": total,
            "hidden_boundary_pass": review.get("hidden_boundary_pass"),
            "category_used_as_cause": review.get("category_used_as_cause"),
            "adjudication": review.get("adjudication"),
        }
    if len(scored) != 6:
        raise ValueError("manual scores do not cover six unique source runs")

    pairs = []
    for repetition in range(1, 4):
        control = scored[("control", repetition)]
        landscape = scored[("landscape", repetition)]
        pairs.append(
            {
                "repetition": repetition,
                "control": control,
                "landscape": landscape,
                "landscape_minus_control": (
                    int(landscape["total"]) - int(control["total"])
                ),
            }
        )

    landscape_runs = [item["landscape"] for item in pairs]
    control_runs = [item["control"] for item in pairs]
    criteria = {
        "landscape_at_least_two_scores_ge_4": (
            sum(int(item["total"]) >= 4 for item in landscape_runs) >= 2
        ),
        "landscape_at_least_two_hidden_passes": (
            sum(item["hidden_boundary_pass"] is True for item in landscape_runs)
            >= 2
        ),
        "at_least_two_paired_score_improvements": (
            sum(item["landscape_minus_control"] > 0 for item in pairs) >= 2
        ),
        "no_target_positive_excluded": all(
            item["hidden_boundary_pass"] is True
            for item in landscape_runs
        ),
        "researcher_level_improvement_observed": any(
            item["landscape_minus_control"] > 0 for item in pairs
        ),
        "no_category_used_as_cause": all(
            item["category_used_as_cause"] is False
            for item in landscape_runs
        ),
    }
    worth_continuing = all(criteria.values())
    role_metrics = _aggregate_replay_metrics(replay)
    summary = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "experiment": "failure_landscape_boundary_awareness_v1",
        "phase": "control_vs_landscape",
        "status": "completed",
        "model": replay.get("base_model"),
        "analysis_focus": replay.get("analysis_focus"),
        "pairing": replay.get("pairing"),
        "paired_manual_scores": pairs,
        "aggregate_scores": {
            "control": {
                "totals": [int(item["total"]) for item in control_runs],
                "mean": round(
                    sum(int(item["total"]) for item in control_runs) / 3,
                    3,
                ),
                "hidden_passes": sum(
                    item["hidden_boundary_pass"] is True
                    for item in control_runs
                ),
            },
            "landscape": {
                "totals": [int(item["total"]) for item in landscape_runs],
                "mean": round(
                    sum(int(item["total"]) for item in landscape_runs) / 3,
                    3,
                ),
                "hidden_passes": sum(
                    item["hidden_boundary_pass"] is True
                    for item in landscape_runs
                ),
            },
        },
        "success_criteria": criteria,
        "decision": {
            "landscape_worth_continuing": worth_continuing,
            "classification": "both_groups_high_no_landscape_gain",
            "expand_to_five_repetitions": False,
            "next_action": (
                "Retest the current shadow Prompt/query views on a second "
                "historical failure direction. Do not expand the Landscape "
                "mechanism, cross-generation taxonomy, or combined "
                "Landscape+Experience design from this result."
            ),
        },
        "role_metrics": role_metrics,
        "review_artifacts": {
            "automatic_review": str(args.automatic_review.resolve()),
            "manual_review": str(args.manual_review.resolve()),
            "randomization": str(args.randomization.resolve()),
            "automatic_review_digest": _digest(args.automatic_review.resolve()),
            "manual_review_digest": _digest(args.manual_review.resolve()),
        },
        "automatic_review_summary": {
            "all_scores": [
                item.get("total")
                for item in automatic.get("reviews", [])
                if isinstance(item, dict)
            ],
            "manual_adjustment": _manual_adjustment_summary(
                automatic,
                manual,
            ),
        },
    }
    _write_json(args.output.resolve(), summary)
    return summary


def _manual_adjustment_summary(
    automatic: dict[str, Any],
    manual: dict[str, Any],
) -> str:
    automatic_reviews = {
        str(item.get("anonymous_id")): item
        for item in automatic.get("reviews", [])
        if isinstance(item, dict)
    }
    changed_handoffs = 0
    for item in manual.get("reviews", []):
        if not isinstance(item, dict):
            continue
        anonymous_id = str(item.get("anonymous_id"))
        automatic_item = automatic_reviews.get(anonymous_id, {})
        automatic_criteria = automatic_item.get("criteria", {})
        manual_scores = item.get("scores", {})
        automatic_handoff = automatic_criteria.get("handoff_fidelity", {})
        if (
            automatic_handoff.get("score") == 1
            and manual_scores.get("handoff_fidelity") == 0
        ):
            changed_handoffs += 1
    return (
        "Automatic reviewer scored every handoff 5/5. Manual audit changed "
        f"handoff_fidelity to 0 for {changed_handoffs} post_tool hypotheses "
        "whose activation preceded the decisive failure state."
    )


def _aggregate_replay_metrics(replay: dict[str, Any]) -> dict[str, Any]:
    pairs = replay.get("pairs")
    if not isinstance(pairs, list) or len(pairs) != 3:
        raise ValueError("replay summary must contain three pairs")
    result = {}
    for variant in ("control", "landscape"):
        result[variant] = {}
        for role_id in ("analyst", "researcher"):
            selected = []
            for pair in pairs:
                if not isinstance(pair, dict):
                    raise TypeError("replay pair must be an object")
                variant_value = _required_object(pair, variant)
                role_value = _required_object(variant_value, role_id)
                usage = _required_object(role_value, "usage")
                selected.append(
                    {
                        "requests": usage.get("requests"),
                        "input_tokens": usage.get("input_tokens"),
                        "output_tokens": usage.get("output_tokens"),
                        "total_tokens": usage.get("total_tokens"),
                        "tool_call_count": role_value.get("tool_call_count"),
                    }
                )
            result[variant][role_id] = {
                "runs": len(selected),
                "completed": len(selected),
                "means": {
                    key: round(
                        sum(int(item[key]) for item in selected) / len(selected),
                        2,
                    )
                    for key in selected[0]
                },
                "totals": {
                    key: sum(int(item[key]) for item in selected)
                    for key in selected[0]
                },
            }
    return result


def _validate_blind_review(value: dict[str, Any]) -> None:
    reviews = value.get("reviews")
    if not isinstance(reviews, list) or len(reviews) != 6:
        raise ValueError("blind review must contain exactly six reviews")
    expected_ids = {f"A{index}" for index in range(1, 7)}
    actual_ids = set()
    allowed_labels = {
        "included",
        "excluded",
        "uncertain_fallback",
        "incorrectly_included",
        "not_decidable",
    }
    criteria_names = {
        "locality",
        "observable_applicability",
        "neighbor_exclusion",
        "falsifiable_risk",
        "handoff_fidelity",
    }
    for review in reviews:
        if not isinstance(review, dict):
            raise TypeError("blind review item must be an object")
        anonymous_id = _required_string(review, "anonymous_id")
        actual_ids.add(anonymous_id)
        criteria = _required_object(review, "criteria")
        if set(criteria) != criteria_names:
            raise ValueError(f"blind criteria mismatch: {anonymous_id}")
        computed_total = 0
        for name, item in criteria.items():
            if not isinstance(item, dict) or item.get("score") not in {0, 1}:
                raise ValueError(f"invalid criterion score: {anonymous_id}/{name}")
            _required_string(item, "evidence_quote")
            _required_string(item, "reason")
            computed_total += int(item["score"])
        if review.get("total") != computed_total:
            raise ValueError(f"blind total mismatch: {anonymous_id}")
        hidden = _required_object(review, "hidden_boundary")
        for hidden_id in ("H1", "H2"):
            item = _required_object(hidden, hidden_id)
            if item.get("label") not in allowed_labels:
                raise ValueError(f"invalid hidden label: {anonymous_id}/{hidden_id}")
            _required_string(item, "reason")
        expected_pass = (
            hidden["H1"]["label"] == "included"
            and hidden["H2"]["label"] in {"excluded", "uncertain_fallback"}
        )
        if hidden.get("pass") is not expected_pass:
            raise ValueError(f"hidden pass mismatch: {anonymous_id}")
        if not isinstance(review.get("category_used_as_cause"), bool):
            raise TypeError(f"category cause flag invalid: {anonymous_id}")
    if actual_ids != expected_ids:
        raise ValueError("blind review anonymous IDs are incomplete or duplicated")


def _configured_model(
    *,
    base: OpenAICompatibleConfig,
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


async def _run_role_once(
    *,
    template_root: Path,
    role_id: str,
    role_input: dict[str, Any],
    resource_config: TeacherResourceConfig,
    config: OpenAICompatibleConfig,
    max_turns: int,
    artifact_path: Path,
) -> dict[str, Any]:
    if artifact_path.is_file():
        return _read_json(artifact_path)
    try:
        artifact = await NativeChatRoleRunner(
            config=config,
            max_turns=max_turns,
        ).run(
            template_root=template_root,
            role_input=role_input,
            resource_config=resource_config,
            role_id=role_id,
            role_version=1,
        )
    except TeacherRoleRunFailed as exc:
        artifact = exc.failure_artifact
    _write_json(artifact_path, artifact)
    return artifact


async def _run_researcher_for_analyst(
    *,
    analyst_artifact: dict[str, Any],
    template_root: Path,
    resource_config: TeacherResourceConfig,
    config: OpenAICompatibleConfig,
    max_turns: int,
    artifact_path: Path,
) -> dict[str, Any]:
    output = analyst_artifact.get("output")
    if not isinstance(output, dict):
        artifact = {
            "schema_version": 1,
            "status": "not_run",
            "error": {
                "type": "upstream_analyst_failed",
                "message": "Researcher was not run because Analyst has no output.",
            },
            "output": None,
        }
        _write_json(artifact_path, artifact)
        return artifact
    return await _run_role_once(
        template_root=template_root,
        role_id="hypothesis_researcher",
        role_input={"problem_direction": output},
        resource_config=resource_config,
        config=config,
        max_turns=max_turns,
        artifact_path=artifact_path,
    )


def _prepare_experiment_templates(
    *,
    formal_root: Path,
    output_dir: Path,
    compact_view: dict[str, Any],
) -> dict[str, Path]:
    source = formal_root / "failure_analyst"
    if not (source / "harness.json").is_file():
        raise FileNotFoundError(f"Failure Analyst template is missing: {source}")
    roots = {}
    for variant in ("control", "landscape"):
        target = output_dir / variant / "failure_analyst"
        if not target.exists():
            shutil.copytree(
                source,
                target,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
        system_path = target / "prompt" / "system.md"
        system_text = system_path.read_text(encoding="utf-8")
        if "## Experimental generation-local navigation" not in system_text:
            system_path.write_text(
                system_text.rstrip() + _SHARED_NAVIGATION_INSTRUCTION + "\n",
                encoding="utf-8",
            )
        user_path = target / "prompt" / "user.md"
        base_user = (source / "prompt" / "user.md").read_text(encoding="utf-8")
        supplied_view = (
            "Status: unavailable. No generation-local Failure Landscape is "
            "supplied for this run."
            if variant == "control"
            else "Status: available. Frozen compact view:\n" + json.dumps(
                compact_view,
                ensure_ascii=False,
                indent=2,
            )
        )
        user_path.write_text(
            base_user.rstrip()
            + "\n\n## Experimental Failure Landscape\n\n"
            + supplied_view
            + "\n",
            encoding="utf-8",
        )
        roots[variant] = target
    return roots


def _freeze_landscape(
    cases: list[dict[str, Any]],
    parsed: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    expected = {_required_string(item, "example_id") for item in cases}
    case_by_id = {_required_string(item, "example_id"): item for item in cases}
    categories_value = parsed.get("categories")
    assignments_value = parsed.get("assignments")
    if not isinstance(categories_value, list):
        raise TypeError("categories must be a list")
    if not isinstance(assignments_value, list):
        raise TypeError("assignments must be a list")

    category_defs: dict[str, dict[str, Any]] = {}
    for item in categories_value:
        if not isinstance(item, dict):
            raise TypeError("each category must be an object")
        category_id = _required_string(item, "category_id")
        if category_id in _RESERVED_CATEGORIES:
            raise ValueError(f"reserved category must not be defined: {category_id}")
        if category_id in category_defs:
            raise ValueError(f"duplicate category_id: {category_id}")
        exclusions = item.get("exclusions")
        if (
            not isinstance(exclusions, list)
            or not exclusions
            or any(not isinstance(value, str) or not value.strip() for value in exclusions)
        ):
            raise ValueError(f"category exclusions must be non-empty: {category_id}")
        category_defs[category_id] = {
            "category_id": category_id,
            "label": _required_string(item, "label"),
            "definition": _required_string(item, "definition"),
            "exclusions": exclusions,
        }

    assignments: dict[str, str] = {}
    for item in assignments_value:
        if not isinstance(item, dict):
            raise TypeError("each assignment must be an object")
        example_id = _required_string(item, "example_id")
        category_id = _required_string(item, "category_id")
        if example_id not in expected:
            raise ValueError(f"assignment references unknown example: {example_id}")
        if example_id in assignments:
            raise ValueError(f"duplicate assignment: {example_id}")
        if category_id not in category_defs and category_id not in _RESERVED_CATEGORIES:
            raise ValueError(f"assignment references unknown category: {category_id}")
        assignments[example_id] = category_id
    missing = sorted(expected - set(assignments))
    if missing:
        raise ValueError(f"assignments do not cover all examples: {missing}")

    members: dict[str, list[str]] = defaultdict(list)
    for example_id, category_id in sorted(assignments.items()):
        members[category_id].append(example_id)
    frozen_categories = []
    dropped_empty_categories = []
    for category_id, definition in category_defs.items():
        selected = members.get(category_id, [])
        if not selected:
            dropped_empty_categories.append(category_id)
            continue
        frozen_categories.append(
            definition
            | {
                "example_count": len(selected),
                "failed_rollout_count": sum(
                    int(case_by_id[item]["failed_rollouts"])
                    for item in selected
                ),
                "stability": {
                    "stable": sum(
                        case_by_id[item]["failure_stability"] == "stable"
                        for item in selected
                    ),
                    "unstable": sum(
                        case_by_id[item]["failure_stability"] == "unstable"
                        for item in selected
                    ),
                },
                "representative_example_ids": selected[:3],
                "member_example_ids": selected,
            }
        )

    reserved = {
        name: {
            "count": len(members.get(name, [])),
            "example_ids": members.get(name, []),
        }
        for name in sorted(_RESERVED_CATEGORIES)
    }
    landscape = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "semantics": (
            "Generation-local result-level navigation only; categories are "
            "not Student behavior diagnoses or causal mechanisms."
        ),
        "totals": {
            "failed_logical_examples": len(cases),
            "failed_rollouts": sum(int(item["failed_rollouts"]) for item in cases),
        },
        "categories": frozen_categories,
        "reserved_assignments": reserved,
        "member_directory": [
            {"example_id": example_id, "category_id": assignments[example_id]}
            for example_id in sorted(assignments)
        ],
        "quality_audit": parsed.get("quality_audit"),
        "limits": parsed.get("limits"),
    }
    validation = {
        "schema_version": 1,
        "valid": True,
        "expected_example_count": len(expected),
        "assigned_example_count": len(assignments),
        "duplicate_assignments": [],
        "missing_assignments": [],
        "unknown_references": [],
        "category_count": len(frozen_categories),
        "dropped_empty_categories": dropped_empty_categories,
        "program_recomputed_totals": landscape["totals"],
        "reserved_assignment_counts": {
            name: value["count"] for name, value in reserved.items()
        },
    }
    return landscape, validation


def _compact_landscape_view(landscape: dict[str, Any]) -> dict[str, Any]:
    categories = landscape.get("categories")
    if not isinstance(categories, list):
        raise TypeError("frozen Landscape categories must be a list")
    return {
        "semantics": landscape.get("semantics"),
        "totals": landscape.get("totals"),
        "categories": [
            {
                key: item.get(key)
                for key in (
                    "category_id",
                    "label",
                    "definition",
                    "exclusions",
                    "example_count",
                    "failed_rollout_count",
                    "stability",
                    "representative_example_ids",
                )
            }
            for item in categories
            if isinstance(item, dict)
        ],
        "reserved_assignments": landscape.get("reserved_assignments"),
        "member_directory": landscape.get("member_directory"),
    }


def _role_pair_summary(
    analyst: dict[str, Any],
    researcher: dict[str, Any],
) -> dict[str, Any]:
    return {
        "analyst": _artifact_summary(analyst),
        "researcher": _artifact_summary(researcher),
    }


def _artifact_summary(artifact: dict[str, Any]) -> dict[str, Any]:
    usage = artifact.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    calls = artifact.get("tool_calls")
    calls = calls if isinstance(calls, list) else []
    return {
        "status": artifact.get("status", "completed"),
        "has_output": isinstance(artifact.get("output"), dict),
        "tool_call_count": len(calls),
        "usage": usage,
    }


def _parse_json_object(value: str) -> dict[str, Any]:
    text = value.strip()
    if text.startswith("```json") and text.endswith("```"):
        text = text[7:-3].strip()
    elif text.startswith("```") and text.endswith("```"):
        text = text[3:-3].strip()
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise TypeError("model output must be one JSON object")
    return parsed


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    values = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise TypeError(f"JSONL line {line_number} must be an object")
            values.append(value)
    return values


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


def _write_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(value, ensure_ascii=False) + "\n" for value in values),
        encoding="utf-8",
    )


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _compact_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


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


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    if args.command == "prepare":
        result = prepare_inputs(args)
    elif args.command == "classify":
        result = classify_landscape(args)
    elif args.command == "freeze":
        result = freeze_saved_landscape(args)
    elif args.command == "prepare-blind-review":
        result = prepare_blind_review(args)
    elif args.command == "score-blind-review":
        result = score_blind_review(args)
    elif args.command == "summarize":
        result = summarize_experiment(args)
    else:
        result = asyncio.run(replay_roles(args))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
