"""Run real-model probes for the extended Intervention Worker tool surface."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from search_harness.evolution.research.intervention.role_runner import (
    InterventionRoleRunner,
)
from search_harness.evolution.research.resources.base import TeacherResourceConfig
from search_harness.evolution.research.resources.stores import (
    InterventionResourceConfig,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKER_TEMPLATE = PROJECT_ROOT / "harness_templates" / "teacher" / "intervention_worker"
DEFAULT_SOURCE = (
    PROJECT_ROOT
    / "runs"
    / "evolution"
    / "20260815_qwen3-8b_hook_feasibility"
)
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "runs"
    / "experiments"
    / "20260816_extended_intervention_worker_live"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-run", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument(
        "--scenario",
        action="append",
        choices=(
            "pre_tool_query_patch",
            "post_model_action_rewrite",
            "cross_phase_trial_state",
        ),
        help="Run only the named scenario; repeat to select multiple.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    if args.repetitions < 1:
        raise ValueError("repetitions must be positive")
    source_run = args.source_run.resolve()
    rollout_file = (
        source_run
        / "artifacts"
        / "evaluate_incumbent-acfbd8c527582fd7"
        / "report_rollouts.jsonl"
    )
    template_root = source_run / "version_store" / "template"
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    runner = InterventionRoleRunner(
        env_file=args.env_file.resolve(),
        max_steps_per_activation=20,
        teacher_judge=False,
        extended_worker_tools=True,
    )
    resources = TeacherResourceConfig(
        intervention=InterventionResourceConfig(
            rollout_file=rollout_file,
            student_template_root=template_root,
            env_file=args.env_file.resolve(),
            student_max_steps=20,
        )
    )
    scenarios = [
        scenario
        for scenario in _scenarios()
        if not args.scenario or scenario["name"] in args.scenario
    ]
    results = []
    for scenario in scenarios:
        for repetition in range(1, args.repetitions + 1):
            name = str(scenario["name"])
            path = output_dir / name / f"run_{repetition:03d}.json"
            try:
                artifact = await runner.run(
                    template_root=WORKER_TEMPLATE,
                    role_input=dict(scenario["role_input"]),
                    resource_config=resources,
                )
                _write_json(path, artifact)
                results.append(_summarize(name, repetition, path, artifact))
                print(f"completed {name} repetition={repetition}", flush=True)
            except Exception as exc:
                failure = {
                    "scenario": name,
                    "repetition": repetition,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
                _write_json(path, failure)
                results.append(failure)
                print(
                    f"failed {name} repetition={repetition}: "
                    f"{type(exc).__name__}: {exc}",
                    flush=True,
                )
    _write_json(
        output_dir / "summary.json",
        {
            "schema_version": 1,
            "source_run": str(source_run),
            "repetitions": args.repetitions,
            "results": results,
        },
    )


def _scenarios() -> list[dict[str, Any]]:
    common = {
        "example_id": "5a7e36045542991319bc9440",
        "replicate_id": "r000",
        "prohibited_content": ["golden answer"],
    }
    return [
        {
            "name": "pre_tool_query_patch",
            "role_input": {
                **common,
                "prefix_id": 1,
                "trial_objective": "Observe the executed search query after the patch.",
                "hypothesis": {
                    "fork_phase": "post_prompt",
                    "phase_plan": [
                        {
                            "phase": "pre_tool",
                            "activation_condition": (
                                "The pending search query is not exactly 'Jonathan "
                                "Stark tennis Grand Slam doubles titles'."
                            ),
                            "instruction": (
                                "Patch only the pending Tool Call arguments so its "
                                "query becomes 'Jonathan Stark tennis Grand Slam "
                                "doubles titles'; preserve the tool name and topk."
                            ),
                            "expected_effect": (
                                "The executed search uses the exact focused query."
                            ),
                            "max_activations": 1,
                        }
                    ],
                    "evaluation": {
                        "primary_signal": "executed_tool_call_arguments",
                        "success_condition": "The exact focused query is executed.",
                        "falsifier": "The original pending query is executed.",
                        "secondary_metrics": ["worker_turns"],
                    },
                    "applicability": "A pending one-sided comparison search.",
                },
            },
        },
        {
            "name": "post_model_action_rewrite",
            "role_input": {
                **common,
                "prefix_id": 6,
                "trial_objective": (
                    "Observe the parsed and executed action after rewrite."
                ),
                "hypothesis": {
                    "fork_phase": "post_prompt",
                    "phase_plan": [
                        {
                            "phase": "post_model",
                            "activation_condition": (
                                "The raw output is not exactly one search action for "
                                "'Jonathan Stark tennis Grand Slam doubles titles'."
                            ),
                            "instruction": (
                                "Replace the raw output with exactly one valid Student "
                                "tool-call action that searches for 'Jonathan Stark "
                                "tennis Grand Slam doubles titles' with topk 5."
                            ),
                            "expected_effect": (
                                "The parser yields and executes a search Tool Call."
                            ),
                            "max_activations": 1,
                        }
                    ],
                    "evaluation": {
                        "primary_signal": "parsed_action_after_rewrite",
                        "success_condition": "A Jonathan Stark search is executed.",
                        "falsifier": (
                            "The original final answer remains the next action."
                        ),
                        "secondary_metrics": ["worker_turns"],
                    },
                    "applicability": "A one-sided comparison answer at post_model.",
                },
            },
        },
        {
            "name": "cross_phase_trial_state",
            "role_input": {
                **common,
                "prefix_id": 5,
                "trial_objective": "Observe explicit state hand-off and final control.",
                "hypothesis": {
                    "fork_phase": "post_tool",
                    "phase_plan": [
                        {
                            "phase": "post_tool",
                            "activation_condition": (
                                "The visible result covers Henri Leconte but contains "
                                "no evidence about Jonathan Stark."
                            ),
                            "instruction": (
                                "Set Trial state missing_second_entity=true, then "
                                "continue without changing Student-visible context."
                            ),
                            "expected_effect": (
                                "The later phase receives the explicit "
                                "missing-side state."
                            ),
                            "max_activations": 1,
                        },
                        {
                            "phase": "pre_final",
                            "activation_condition": (
                                "Trial state missing_second_entity is true, no later "
                                "search targeted Jonathan Stark, and the candidate "
                                "resolves the comparison."
                            ),
                            "instruction": (
                                "Defer once with feedback requiring a Jonathan Stark "
                                "search before resolving the comparison."
                            ),
                            "expected_effect": (
                                "The next Student generation searches for "
                                "Jonathan Stark."
                            ),
                            "max_activations": 1,
                        },
                    ],
                    "evaluation": {
                        "primary_signal": "state_conditioned_final_control",
                        "success_condition": (
                            "State is retained and the unsupported final is deferred."
                        ),
                        "falsifier": (
                            "State is lost or the unsupported final is accepted."
                        ),
                        "secondary_metrics": ["worker_turns", "student_tool_calls"],
                    },
                    "applicability": "A multi-phase one-sided comparison branch.",
                },
            },
        },
    ]


def _summarize(
    scenario: str,
    repetition: int,
    path: Path,
    artifact: dict[str, Any],
) -> dict[str, Any]:
    trial = artifact.get("resource_artifacts", {}).get("intervention_trial", {})
    branch = trial.get("branch_run", {}) if isinstance(trial, dict) else {}
    state = branch.get("state", {}) if isinstance(branch, dict) else {}
    return {
        "scenario": scenario,
        "repetition": repetition,
        "artifact": str(path.resolve()),
        "model": artifact.get("model"),
        "role_budget": artifact.get("role_budget"),
        "output": artifact.get("output"),
        "usage": artifact.get("usage"),
        "tool_names": [
            item.get("name")
            for item in artifact.get("tool_calls", [])
            if isinstance(item, dict)
        ],
        "trial_state": trial.get("trial_state") if isinstance(trial, dict) else None,
        "branch_status": branch.get("status") if isinstance(branch, dict) else None,
        "branch_answer": branch.get("answer") if isinstance(branch, dict) else None,
        "branch_tool_interactions": (
            state.get("tool_interactions") if isinstance(state, dict) else None
        ),
    }


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    asyncio.run(main())
