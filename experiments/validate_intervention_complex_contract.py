"""Exercise complex Intervention contracts with real Teacher and Student models."""

from __future__ import annotations

import argparse
import asyncio
import json
import random
from dataclasses import dataclass
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
TEACHER_TEMPLATE = (
    PROJECT_ROOT / "harness_templates" / "teacher" / "intervention_worker"
)
BASE_RUN = (
    PROJECT_ROOT / "runs" / "evolution" / "20260815_qwen3-8b_hook_feasibility"
)
BASE_ROLLOUT = (
    BASE_RUN
    / "artifacts"
    / "evaluate_incumbent-acfbd8c527582fd7"
    / "report_rollouts.jsonl"
)
BASE_TEMPLATE = BASE_RUN / "version_store" / "template"
ADAPTIVE_ROLLOUT = (
    PROJECT_ROOT
    / "experiments"
    / "as_you_can"
    / "artifacts"
    / "benchmarks"
    / "train24_v11_routed_adaptive"
    / "rollouts.jsonl"
)
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "runs"
    / "experiments"
    / "20260816_intervention_complex_contract"
)
BASE_EXAMPLE = "5a7e36045542991319bc9440"
ADAPTIVE_EXAMPLE = "5abcfc3b554299114383a1ad"
RANDOM_SEED = 20260816


@dataclass(frozen=True)
class Scenario:
    """One frozen complex-contract experiment unit."""

    group: str
    name: str
    rollout_file: Path
    template_root: Path
    example_id: str
    replicate_id: str
    prefix_id: int
    objective: str
    hypothesis: dict[str, Any]
    expected_phases: tuple[str, ...]
    expected_action_kinds: tuple[str, ...]
    expected_state_keys: tuple[str, ...] = ()
    source_note: str = ""

    def role_input(self) -> dict[str, Any]:
        """Return the exact formal Role input used by InterventionRoleRunner."""

        return {
            "hypothesis": self.hypothesis,
            "trial_objective": self.objective,
            "example_id": self.example_id,
            "replicate_id": self.replicate_id,
            "prefix_id": self.prefix_id,
            "prohibited_content": ["golden answer"],
        }

    def to_manifest(self) -> dict[str, Any]:
        """Serialize the immutable scenario without hiding contract text."""

        return {
            "group": self.group,
            "name": self.name,
            "rollout_file": str(self.rollout_file.resolve()),
            "template_root": str(self.template_root.resolve()),
            "role_input": self.role_input(),
            "expected_phases": list(self.expected_phases),
            "expected_action_kinds": list(self.expected_action_kinds),
            "expected_state_keys": list(self.expected_state_keys),
            "source_note": self.source_note,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument(
        "--group",
        action="append",
        choices=("phase", "multi", "adaptive"),
        help="Run only selected groups; repeat to select more than one.",
    )
    parser.add_argument(
        "--scenario",
        action="append",
        help="Run only an exact scenario name; repeat to select more than one.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    if args.repetitions < 1:
        raise ValueError("repetitions must be positive")
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    scenarios = _scenarios()
    scenarios = [
        item
        for item in scenarios
        if (not args.group or item.group in args.group)
        and (not args.scenario or item.name in args.scenario)
    ]
    if not scenarios:
        raise ValueError("no experiment scenarios selected")
    _write_json(
        output_dir / "manifest.json",
        {
            "schema_version": 1,
            "random_seed": RANDOM_SEED,
            "repetitions": args.repetitions,
            "worker_thinking_mode": "disabled_by_runtime_role_config",
            "scenarios": [item.to_manifest() for item in scenarios],
        },
    )

    runner = InterventionRoleRunner(
        env_file=args.env_file.resolve(),
        max_steps_per_activation=20,
        teacher_judge=False,
        extended_worker_tools=True,
    )
    results: list[dict[str, Any]] = []
    for scenario in scenarios:
        resources = TeacherResourceConfig(
            intervention=InterventionResourceConfig(
                rollout_file=scenario.rollout_file,
                student_template_root=scenario.template_root,
                env_file=args.env_file.resolve(),
                student_max_steps=20,
            )
        )
        for repetition in range(1, args.repetitions + 1):
            path = (
                output_dir
                / scenario.group
                / scenario.name
                / f"run_{repetition:03d}.json"
            )
            try:
                artifact = await runner.run(
                    template_root=TEACHER_TEMPLATE,
                    role_input=scenario.role_input(),
                    resource_config=resources,
                )
                _write_json(path, artifact)
                result = _summarize(
                    scenario=scenario,
                    repetition=repetition,
                    artifact_path=path.resolve(),
                    artifact=artifact,
                )
            except Exception as exc:
                result = {
                    "group": scenario.group,
                    "scenario": scenario.name,
                    "repetition": repetition,
                    "status": "execution_error",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "artifact": None,
                }
                _write_json(path, result)
            results.append(result)
            print(
                f"completed group={scenario.group} scenario={scenario.name} "
                f"repetition={repetition} status={result['status']}",
                flush=True,
            )

    _write_json(
        output_dir / "summary.json",
        {
            "schema_version": 1,
            "manifest": str((output_dir / "manifest.json").resolve()),
            "results": results,
        },
    )


def _scenarios() -> list[Scenario]:
    return [
        *_single_phase_scenarios(),
        *_selected_multi_phase_scenarios(),
        _adaptive_scenario(),
    ]


def _single_phase_scenarios() -> list[Scenario]:
    return [
        _scenario(
            group="phase",
            name="post_prompt_context_operations",
            prefix_id=6,
            fork_phase="post_prompt",
            directives=[
                _directive(
                    "post_prompt",
                    "At least four editable context blocks are present, ending in "
                    "an assistant action block followed by a retrieved result block.",
                    "Inspect the exact last assistant action and result blocks. In one "
                    "atomic patch, delete that assistant block; insert immediately "
                    "before the result an assistant block with exactly the deleted "
                    "content; replace the result with its exact content plus a final "
                    "newline '[POST_PROMPT_REPLACED]'; then insert after it a user "
                    "block containing exactly '[POST_PROMPT_INSERTED]'. Preserve all "
                    "other blocks.",
                    "The next Student ModelInput contains equivalent action history, "
                    "the replaced result marker, and the inserted user marker.",
                )
            ],
            expected_phases=("post_prompt",),
            expected_action_kinds=("apply_context_patch",),
        ),
        _scenario(
            group="phase",
            name="post_model_raw_output",
            prefix_id=1,
            fork_phase="post_prompt",
            directives=[
                _directive(
                    "post_model",
                    "A non-empty raw Student output is active.",
                    "Replace only raw output content with exactly "
                    "'<tool_call>{\"name\":\"search\",\"arguments\":{\"query\":"
                    "\"field coverage post model query\",\"topk\":5}}</tool_call>'.",
                    "The parser produces and executes that exact search action.",
                )
            ],
            expected_phases=("post_model",),
            expected_action_kinds=("replace_stage_value",),
        ),
        _post_parse_scenario(
            name="post_parse_tool_call",
            patch_instruction=(
                "Patch parsed output to kind tool_call with tool name 'search' and "
                "arguments {query:'field coverage post parse query',topk:4}. Replace "
                "all mutually exclusive final_answer/error payload fields."
            ),
            expected_effect="The exact patched search call reaches pre_tool and executes.",
        ),
        _post_parse_scenario(
            name="post_parse_tool_call_to_final",
            patch_instruction=(
                "Patch parsed output to kind final_answer with final_answer exactly "
                "'FIELD_COVERAGE_FINAL'; remove the tool_call/error union payload."
            ),
            expected_effect=(
                "The loop prepares and accepts FIELD_COVERAGE_FINAL without a tool call."
            ),
        ),
        _existing_final_answer_scenario(),
        _post_parse_scenario(
            name="post_parse_invalid",
            patch_instruction=(
                "Patch parsed output to kind invalid with error exactly "
                "'FIELD_COVERAGE_INVALID'; remove tool_call/final_answer payloads."
            ),
            expected_effect=(
                "The loop records FIELD_COVERAGE_INVALID and supplies its normal "
                "invalid-output feedback."
            ),
        ),
        _scenario(
            group="phase",
            name="pre_tool_tool_call",
            prefix_id=1,
            fork_phase="post_prompt",
            directives=[
                _directive(
                    "pre_tool",
                    "The pending tool is the available search tool.",
                    "Inspect the active Tool Call, preserve its name exactly, and "
                    "replace the complete arguments with {query:'field coverage pre "
                    "tool query',topk:3}.",
                    "Tool Executor runs search with the exact patched arguments.",
                )
            ],
            expected_phases=("pre_tool",),
            expected_action_kinds=("replace_stage_value",),
        ),
        _scenario(
            group="phase",
            name="post_tool_tool_result",
            prefix_id=1,
            fork_phase="post_prompt",
            directives=[
                _directive(
                    "post_tool",
                    "A successful search Tool Result with non-empty content is active.",
                    "Inspect the active result and replace only content with exactly "
                    "'FIELD_COVERAGE_POST_TOOL_RESULT'. Do not change or reproduce "
                    "the name or runtime metadata.",
                    "The next Student generation sees only the replacement content, "
                    "while Tool Result name and metadata remain unchanged.",
                )
            ],
            expected_phases=("post_tool",),
            expected_action_kinds=("replace_stage_value",),
        ),
        _pre_final_scenario(
            name="pre_final_defer",
            instruction=(
                "Defer this candidate once with feedback exactly "
                "'FIELD_COVERAGE_DEFER_FEEDBACK'."
            ),
            expected_effect=(
                "The candidate is not accepted and the next ModelInput contains the "
                "exact feedback."
            ),
            action_kind="replace_stage_value",
        ),
        _pre_final_scenario(
            name="pre_final_accept",
            instruction=(
                "Accept the active Student candidate exactly as shown; copy it without "
                "rewriting, explaining, or substituting another answer."
            ),
            expected_effect="The branch final answer equals the active candidate.",
            action_kind="replace_stage_value",
        ),
    ]


def _post_parse_scenario(
    *,
    name: str,
    patch_instruction: str,
    expected_effect: str,
) -> Scenario:
    return _scenario(
        group="phase",
        name=name,
        prefix_id=1,
        fork_phase="post_prompt",
        directives=[
            _directive(
                "post_parse",
                "A ParsedOutput object is active after parsing the Student response.",
                patch_instruction,
                expected_effect,
            )
        ],
        expected_phases=("post_parse",),
        expected_action_kinds=("replace_stage_value",),
    )


def _existing_final_answer_scenario() -> Scenario:
    directive = _directive(
        "post_parse",
        "The active ParsedOutput is kind final_answer with a non-empty answer.",
        "Inspect the exact parsed final_answer and patch it to the same text followed "
        "by exactly ' [POST_PARSE_FINAL_READ]'. Preserve kind final_answer and do not "
        "add tool_call/error payloads.",
        "The accepted final answer preserves the original candidate and ends with the "
        "exact sentinel.",
    )
    return Scenario(
        group="phase",
        name="post_parse_existing_final_answer",
        rollout_file=ADAPTIVE_ROLLOUT,
        template_root=BASE_TEMPLATE,
        example_id=ADAPTIVE_EXAMPLE,
        replicate_id="r000",
        prefix_id=11,
        objective=_objective([directive]),
        hypothesis=_hypothesis(
            fork_phase="post_prompt",
            directives=[directive],
            applicability=(
                "A controlled synthesis prompt with complete retrieved evidence, used "
                "only to test reading and modifying a live final-answer ParsedOutput."
            ),
        ),
        expected_phases=("post_parse",),
        expected_action_kinds=("replace_stage_value",),
        source_note=(
            "Uses the routed-adaptive source synthesis ModelInput with the baseline "
            "runtime so no private Hook State continuation is claimed."
        ),
    )


def _pre_final_scenario(
    *,
    name: str,
    instruction: str,
    expected_effect: str,
    action_kind: str,
) -> Scenario:
    return _scenario(
        group="phase",
        name=name,
        prefix_id=6,
        fork_phase="post_prompt",
        directives=[
            _directive(
                "pre_final",
                "A non-empty Student final candidate is active.",
                instruction,
                expected_effect,
            )
        ],
        expected_phases=("pre_final",),
        expected_action_kinds=(action_kind,),
    )


def _selected_multi_phase_scenarios() -> list[Scenario]:
    candidates = {
        "repeated_retrieval": _multi_repeated_retrieval(),
        "observe_state_final": _multi_observe_state_final(),
        "raw_result_final": _multi_raw_result_final(),
        "context_action": _multi_context_action(),
    }
    selected = random.Random(RANDOM_SEED).sample(list(candidates), 3)
    return [candidates[name] for name in selected]


def _multi_repeated_retrieval() -> Scenario:
    return _scenario(
        group="multi",
        name="repeated_retrieval",
        prefix_id=1,
        fork_phase="post_prompt",
        directives=[
            _directive(
                "pre_tool",
                "A search call is pending and fewer than two planned searches are "
                "recorded in Trial state.",
                "Before the terminal action, set route='stateful_retrieval', status="
                "'awaiting_result', and planned_search_index to 1 on the first "
                "activation or 2 on the second. Then preserve tool name and patch "
                "arguments to query 'stateful retrieval one' or 'stateful retrieval "
                "two' respectively, with topk 3.",
                "The matching indexed query executes and state records its index.",
                max_activations=2,
            ),
            _directive(
                "post_tool",
                "A result for the indexed planned search is active.",
                "Inspect the result. After index 1, set search_count=1 and status="
                "'need_second', then append Student-visible feedback requiring one "
                "more search. After index 2, set search_count=2 and status="
                "'ready_to_synthesize', then continue without changing context.",
                "State advances monotonically and exactly two indexed searches can "
                "complete before synthesis.",
                max_activations=2,
            ),
        ],
        expected_phases=("pre_tool", "post_tool"),
        expected_action_kinds=("replace_stage_value", "apply_context_patch"),
        expected_state_keys=(
            "route",
            "status",
            "planned_search_index",
            "search_count",
        ),
    )


def _multi_observe_state_final() -> Scenario:
    return _scenario(
        group="multi",
        name="observe_state_final",
        prefix_id=1,
        fork_phase="post_prompt",
        directives=[
            _directive(
                "post_tool",
                "The first completed search covers only one side of the comparison.",
                "Set route='two_side_check', status='missing_second_side', "
                "search_count=1, and evidence_gap=true; then continue without "
                "changing Student-visible context.",
                "The exact observation is available in Trial state at pre_final.",
            ),
            _directive(
                "pre_final",
                "State says evidence_gap=true, no later search covered the missing "
                "side, and the Student is finalizing the comparison.",
                "Set status='deferred_for_second_side', then defer once with feedback "
                "requiring a search for the still-uncovered side. If current history "
                "already contains that search, set evidence_gap=false and continue "
                "without change instead.",
                "Only an unresolved gap causes defer; natural recovery is preserved.",
            ),
        ],
        expected_phases=("post_tool", "pre_final"),
        expected_action_kinds=("continue_without_change", "replace_stage_value"),
        expected_state_keys=(
            "route",
            "status",
            "search_count",
            "evidence_gap",
        ),
    )


def _multi_raw_result_final() -> Scenario:
    return _scenario(
        group="multi",
        name="raw_result_final",
        prefix_id=6,
        fork_phase="post_prompt",
        directives=[
            _directive(
                "post_model",
                "A raw output is active before parsing.",
                "Set route='forced_evidence_check' and status='action_rewritten', then "
                "replace raw output with exactly one search action for query 'raw "
                "result final chain' with topk 3.",
                "The parser and Tool Executor consume the replacement search action.",
            ),
            _directive(
                "post_tool",
                "The forced search result is active.",
                "Inspect the result; set status='evidence_collected', search_count=1, "
                "and evidence_gap=false; replace only result content with its exact "
                "original content plus a final newline '[CHAIN_RESULT_READ]'.",
                "The next generation sees the marked result and state records the read.",
            ),
            _directive(
                "pre_final",
                "State status is evidence_collected and a final candidate is active.",
                "Accept the active candidate exactly as shown without rewriting it.",
                "The accepted answer equals the Student candidate after the marked result.",
            ),
        ],
        expected_phases=("post_model", "post_tool", "pre_final"),
        expected_action_kinds=(
            "replace_stage_value",
            "replace_stage_value",
            "replace_stage_value",
        ),
        expected_state_keys=(
            "route",
            "status",
            "search_count",
            "evidence_gap",
        ),
    )


def _multi_context_action() -> Scenario:
    return _scenario(
        group="multi",
        name="context_action",
        prefix_id=1,
        fork_phase="post_prompt",
        directives=[
            _directive(
                "post_prompt",
                "The initial Student input is active.",
                "Append a user block containing exactly '[CONTEXT_ACTION_ROUTE]' and "
                "set route='context_action', status='context_marked'.",
                "The first generated action is conditioned on the visible marker.",
            ),
            _directive(
                "pre_tool",
                "State status is context_marked and a search call is pending.",
                "Set status='action_patched', preserve tool name, and replace arguments "
                "with query 'context action chain' and topk 3.",
                "The patched action executes after the marked context.",
            ),
        ],
        expected_phases=("post_prompt", "pre_tool"),
        expected_action_kinds=("apply_context_patch", "replace_stage_value"),
        expected_state_keys=("route", "status"),
    )


def _adaptive_scenario() -> Scenario:
    directives = [
        _directive(
            "post_prompt",
            "The retained retrieval prompt is active and Trial state has no route.",
            "Inspect the current question and retrieval prompt. Set route='decompose', "
            "status='bridge_pending', search_count=0, and evidence_summary='Need the "
            "described school bus driver identity before the funding relation.' Then "
            "append one concise Student-visible instruction to perform only that "
            "answer-neutral bridge search; do not name or guess the bridge.",
            "The first action is grounded in an explicit bridge obligation and Trial "
            "state starts before any search result.",
        ),
        _directive(
            "pre_tool",
            "A search call is pending while route='decompose' and fewer than two "
            "searches are recorded.",
            "Set status='awaiting_result' and planned_search_index to 1 or 2 for the "
            "current activation. For index 1 preserve the pending "
            "bridge-resolution query. For index 2 inspect the pending query and patch "
            "it only if needed so it uses the bridge entity recorded from the first "
            "result and targets the relation requested by the original question.",
            "The correct answer-neutral evidence obligation is executed for this stage.",
            max_activations=2,
        ),
        _directive(
            "post_tool",
            "A result for planned search index 1 or 2 is active.",
            "Inspect the exact result. After index 1, record bridge_entity from explicit "
            "evidence, evidence_summary, search_count=1, and status='need_relation'; "
            "append a Student-visible instruction to search the original question's "
            "remaining relation using that bridge. After index 2, update "
            "evidence_summary, search_count=2, status='ready_to_synthesize', and append "
            "an instruction to answer only from both retrieved results.",
            "State and visible guidance advance from bridge resolution to relation "
            "retrieval and then synthesis without storing a proposed answer.",
            max_activations=2,
        ),
        _directive(
            "pre_final",
            "A final candidate is active after the routed retrieval chain.",
            "If status='ready_to_synthesize' and search_count=2, accept the active "
            "candidate exactly. Otherwise defer once with feedback to complete the "
            "missing evidence obligation; never supply an answer in feedback.",
            "Finalization is allowed only after the two-stage evidence state is complete.",
        ),
    ]
    return Scenario(
        group="adaptive",
        name="routed_adaptive_decomposition",
        rollout_file=ADAPTIVE_ROLLOUT,
        template_root=BASE_TEMPLATE,
        example_id=ADAPTIVE_EXAMPLE,
        replicate_id="r000",
        prefix_id=1,
        objective=_objective(directives),
        hypothesis=_hypothesis(
            fork_phase="post_prompt",
            directives=directives,
            applicability=(
                "A bridge-style factual question whose retained first retrieval prompt "
                "begins a two-stage, answer-neutral evidence chain. The baseline branch "
                "is used because private routed-adaptive Hook State is not recoverable "
                "from retained prefix artifacts."
            ),
        ),
        expected_phases=("post_prompt", "pre_tool", "post_tool", "pre_final"),
        expected_action_kinds=(
            "apply_context_patch",
            "continue_without_change",
            "apply_context_patch",
            "apply_context_patch",
            "replace_stage_value",
        ),
        expected_state_keys=(
            "route",
            "status",
            "planned_search_index",
            "search_count",
            "bridge_entity",
            "evidence_summary",
        ),
        source_note=(
            "The source rollout was produced by final_template_routed_adaptive. "
            "Execution deliberately uses the baseline template from its initial "
            "post_prompt prefix because retained prefixes do not restore private Hook "
            "State; the Worker contract reproduces the routing/state idea explicitly."
        ),
    )


def _scenario(
    *,
    group: str,
    name: str,
    prefix_id: int,
    fork_phase: str,
    directives: list[dict[str, Any]],
    expected_phases: tuple[str, ...],
    expected_action_kinds: tuple[str, ...],
    expected_state_keys: tuple[str, ...] = (),
) -> Scenario:
    return Scenario(
        group=group,
        name=name,
        rollout_file=BASE_ROLLOUT,
        template_root=BASE_TEMPLATE,
        example_id=BASE_EXAMPLE,
        replicate_id="r000",
        prefix_id=prefix_id,
        objective=_objective(directives),
        hypothesis=_hypothesis(
            fork_phase=fork_phase,
            directives=directives,
            applicability=(
                "A controlled field-coverage branch used only to test the frozen "
                "Intervention runtime contract; no dataset-wide benefit is claimed."
            ),
        ),
        expected_phases=expected_phases,
        expected_action_kinds=expected_action_kinds,
        expected_state_keys=expected_state_keys,
    )


def _directive(
    phase: str,
    condition: str,
    instruction: str,
    expected_effect: str,
    *,
    max_activations: int = 1,
) -> dict[str, Any]:
    return {
        "phase": phase,
        "activation_condition": condition,
        "instruction": instruction,
        "expected_effect": expected_effect,
        "max_activations": max_activations,
    }


def _hypothesis(
    *,
    fork_phase: str,
    directives: list[dict[str, Any]],
    applicability: str,
) -> dict[str, Any]:
    phases = ", ".join(str(item["phase"]) for item in directives)
    return {
        "fork_phase": fork_phase,
        "phase_plan": directives,
        "evaluation": {
            "primary_signal": (
                f"Trace-confirmed field and action fidelity across phases: {phases}."
            ),
            "success_condition": (
                "Every activated instruction uses the intended native tool, changes "
                "the exact live semantic field, and preserves unmentioned state."
            ),
            "falsifier": (
                "Any intended live field is not changed, a wrong phase/action is used, "
                "or hidden metadata must be reconstructed by the Worker."
            ),
            "secondary_metrics": [
                "Teacher requests and total tokens per activation.",
                "Repeated inspections before a terminal action.",
                "Student branch status after the facility test.",
            ],
        },
        "applicability": applicability,
        "special_evidence_obligations": [],
    }


def _objective(directives: list[dict[str, Any]]) -> str:
    phases = ", ".join(str(item["phase"]) for item in directives)
    return (
        f"Test whether the disabled-thinking Worker faithfully executes the frozen "
        f"semantic contract across {phases}; final answer quality is not the gate."
    )


def _summarize(
    *,
    scenario: Scenario,
    repetition: int,
    artifact_path: Path,
    artifact: dict[str, Any],
) -> dict[str, Any]:
    resources = artifact.get("resource_artifacts")
    resources = resources if isinstance(resources, dict) else {}
    trial = resources.get("intervention_trial")
    trial = trial if isinstance(trial, dict) else {}
    branch = trial.get("branch_run")
    branch = branch if isinstance(branch, dict) else {}
    changes = trial.get("context_changes")
    changes = changes if isinstance(changes, list) else []
    action_sequence = [
        {
            "scope": item.get("scope"),
            "phase": item.get("phase"),
            "step": item.get("step"),
            "kind": item.get("action", {}).get("kind")
            if isinstance(item.get("action"), dict)
            else None,
            "payload": item.get("action", {}).get("payload")
            if isinstance(item.get("action"), dict)
            else None,
            "reason": item.get("action", {}).get("reason")
            if isinstance(item.get("action"), dict)
            else None,
        }
        for item in changes
        if isinstance(item, dict)
    ]
    observed_phases = tuple(
        dict.fromkeys(
            str(item["phase"])
            for item in action_sequence
            if isinstance(item.get("phase"), str)
        )
    )
    observed_kinds = tuple(
        str(item["kind"])
        for item in action_sequence
        if isinstance(item.get("kind"), str)
    )
    trial_state = trial.get("trial_state")
    trial_state = trial_state if isinstance(trial_state, dict) else {}
    structural_checks = {
        "all_expected_phases_activated": all(
            phase in observed_phases for phase in scenario.expected_phases
        ),
        "expected_action_kinds_are_subsequence": _is_subsequence(
            scenario.expected_action_kinds,
            observed_kinds,
        ),
        "expected_state_keys_present": all(
            key in trial_state for key in scenario.expected_state_keys
        ),
        "no_worker_tool_input_error": not _has_worker_tool_error(artifact),
    }
    status = (
        "structural_pass"
        if all(structural_checks.values())
        else "needs_semantic_review"
    )
    return {
        "group": scenario.group,
        "scenario": scenario.name,
        "repetition": repetition,
        "status": status,
        "artifact": str(artifact_path),
        "model": artifact.get("model"),
        "role_budget": artifact.get("role_budget"),
        "output": artifact.get("output"),
        "usage": artifact.get("usage"),
        "worker_tools": [
            item.get("name")
            for item in artifact.get("tool_calls", [])
            if isinstance(item, dict)
        ],
        "action_sequence": action_sequence,
        "trial_state": trial_state,
        "phase_effects": trial.get("phase_effects"),
        "branch_status": branch.get("status"),
        "branch_answer": branch.get("answer"),
        "tool_interactions": _project_tool_interactions(branch),
        "trace_events": _project_trace(branch),
        "structural_checks": structural_checks,
    }


def _is_subsequence(expected: tuple[str, ...], observed: tuple[str, ...]) -> bool:
    iterator = iter(observed)
    return all(any(item == wanted for item in iterator) for wanted in expected)


def _has_worker_tool_error(artifact: dict[str, Any]) -> bool:
    for item in artifact.get("tool_calls", []):
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if isinstance(content, str) and "TOOL_INPUT_ERROR" in content:
            return True
    return False


def _project_tool_interactions(branch: dict[str, Any]) -> list[dict[str, Any]]:
    state = branch.get("state")
    state = state if isinstance(state, dict) else {}
    interactions = state.get("tool_interactions")
    interactions = interactions if isinstance(interactions, list) else []
    projected = []
    for item in interactions:
        if not isinstance(item, dict):
            continue
        call = item.get("tool_call")
        result = item.get("tool_result")
        call = call if isinstance(call, dict) else {}
        result = result if isinstance(result, dict) else {}
        projected.append(
            {
                "tool_call": call,
                "tool_result": {
                    "name": result.get("name"),
                    "content_preview": _preview(result.get("content")),
                    "metadata_keys": sorted(result.get("metadata", {}))
                    if isinstance(result.get("metadata"), dict)
                    else [],
                },
            }
        )
    return projected


def _project_trace(branch: dict[str, Any]) -> list[dict[str, Any]]:
    trace = branch.get("trace")
    trace = trace if isinstance(trace, list) else []
    keep = {
        "parsed_output",
        "tool_call",
        "tool_result",
        "invalid_output",
        "invalid_output_feedback",
        "final_answer_candidate",
        "final_deferred",
        "final_answer",
        "hook_error",
    }
    projected = []
    for event in trace:
        if not isinstance(event, dict) or event.get("event_type") not in keep:
            continue
        payload = event.get("payload")
        payload = payload if isinstance(payload, dict) else {}
        projected.append(
            {
                "index": event.get("index"),
                "step": event.get("step"),
                "event_type": event.get("event_type"),
                "payload": _compact_payload(payload),
            }
        )
    return projected


def _compact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    if "content" in result:
        result["content"] = _preview(result["content"])
    if "message" in result:
        result["message"] = _preview(result["message"])
    return result


def _preview(value: object, limit: int = 320) -> object:
    if not isinstance(value, str) or len(value) <= limit:
        return value
    return f"{value[:limit]}...[truncated {len(value) - limit} chars]"


def _write_json(path: Path, value: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path.resolve()


if __name__ == "__main__":
    asyncio.run(main())
