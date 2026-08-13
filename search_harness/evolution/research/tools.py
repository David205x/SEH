"""Teacher templates 可显式注册的内置只读工具和机制草稿工具。"""

from __future__ import annotations

import json
from typing import Annotated, Any, Callable

from search_harness.framework import ToolResult
from search_harness.framework.tools import CallableTool, ToolArg, tool
from search_harness.framework.harness import ComponentFactoryContext

from .mechanism.hook_api import hook_api_categories
from .mechanism.runtime_inputs import RuntimeInputId
from .intervention.capabilities import intervention_capabilities
from .resources.base import (
    EvaluationEvidenceStore,
    TeacherResources,
    TrialEvidenceStore,
)
from .resources.stores import (
    CandidateComparisonStore,
    CompilerWorkspaceStore,
    InterventionBranchStore,
)


def build_builtin_tool(
    config: dict[str, Any],
    context: ComponentFactoryContext,
) -> CallableTool:
    """按 manifest 中的 kind 创建一个显式工具实例。"""

    if set(config) != {"kind"}:
        raise ValueError("built-in Teacher tool config must contain only kind")
    kind = config.get("kind")
    if not isinstance(kind, str):
        raise TypeError("built-in Teacher tool kind must be a string")
    resources = context.runtime_context
    if not isinstance(resources, TeacherResources):
        raise TypeError("built-in Teacher tools require TeacherResources")
    factories: dict[str, Callable[[TeacherResources], CallableTool]] = {
        "list_evaluation_cases": _list_evaluation_cases,
        "list_evaluation_cases_by_cost": _list_evaluation_cases_by_cost,
        "get_cost_summary": _get_cost_summary,
        "get_evaluation_case": _get_evaluation_case,
        "get_student_trajectory": _get_student_trajectory,
        "get_intervention_capabilities": _get_intervention_capabilities,
        "get_harness_manifest": _get_harness_manifest,
        "get_harness_component": _get_harness_component,
        "list_trial_evidence": _list_trial_evidence,
        "get_trial_evidence": _get_trial_evidence,
        "get_trial_event": _get_trial_event,
        "create_mechanism_draft": _create_mechanism_draft,
        "add_mechanism_phase": _add_mechanism_phase,
        "complete_mechanism_draft": _complete_mechanism_draft,
        "set_mechanism_constraints": _set_mechanism_constraints,
        "validate_mechanism_draft": _validate_mechanism_draft,
        "probe_mechanism_evaluators": _probe_mechanism_evaluators,
        "list_intervention_timeline": _list_intervention_timeline,
        "inspect_intervention_prefix": _inspect_intervention_prefix,
        "run_intervention_branch": _run_intervention_branch,
        "list_harness_files": _list_harness_files,
        "read_harness_file": _read_harness_file,
        "get_hook_authoring_guide": _get_hook_authoring_guide,
        "list_hook_api_symbols": _list_hook_api_symbols,
        "query_hook_api": _query_hook_api,
        "write_candidate_file": _write_candidate_file,
        "delete_candidate_file": _delete_candidate_file,
        "show_candidate_diff": _show_candidate_diff,
        "validate_candidate": _validate_candidate,
        "submit_candidate": _submit_candidate,
        "finalize_candidate": _finalize_candidate,
        "list_candidate_changes": _list_candidate_changes,
        "get_candidate_case": _get_candidate_case,
        "get_paired_student_trajectory": _get_paired_student_trajectory,
        "get_candidate_harness_diff": _get_candidate_harness_diff,
    }
    try:
        factory = factories[kind]
    except KeyError as exc:
        raise ValueError(f"unknown built-in Teacher tool kind: {kind}") from exc
    return factory(resources)


def _list_evaluation_cases(resources: TeacherResources) -> CallableTool:
    store = _require_evaluation(resources)

    @tool(name="list_evaluation_cases")
    def invoke(
        page: Annotated[int, ToolArg("One-based page number.", minimum=1)] = 1,
        page_size: Annotated[
            int,
            ToolArg("Cases per page.", minimum=1, maximum=20),
        ] = 10,
        stability: Annotated[
            str,
            ToolArg(
                "Stability filter.",
                choices=(
                    "any",
                    "stable_failure",
                    "unstable",
                    "stable_correct",
                    "unresolved",
                ),
            ),
        ] = "any",
    ) -> ToolResult:
        """List logical evaluation cases without loading full trajectories."""

        return _json_result(
            "list_evaluation_cases",
            store.list_cases(
                page=page,
                page_size=page_size,
                stability=stability,
            ),
        )

    return CallableTool.from_callable(invoke)


def _get_evaluation_case(resources: TeacherResources) -> CallableTool:
    store = _require_evaluation(resources)

    @tool(name="get_evaluation_case")
    def invoke(
        example_id: Annotated[
            str,
            ToolArg("Example ID returned by list_evaluation_cases."),
        ],
    ) -> ToolResult:
        """Read one logical example's evaluation and replicate directory."""

        return _json_result("get_evaluation_case", store.get_case(example_id))

    return CallableTool.from_callable(invoke)


def _list_evaluation_cases_by_cost(
    resources: TeacherResources,
) -> CallableTool:
    store = _require_evaluation(resources)

    @tool(name="list_evaluation_cases_by_cost")
    def invoke(
        page: Annotated[int, ToolArg("One-based page number.", minimum=1)] = 1,
        page_size: Annotated[
            int,
            ToolArg("Cases per page.", minimum=1, maximum=20),
        ] = 10,
        stability: Annotated[
            str,
            ToolArg(
                "Stability filter.",
                choices=(
                    "any",
                    "stable_failure",
                    "unstable",
                    "stable_correct",
                    "unresolved",
                ),
            ),
        ] = "any",
        token_metric: Annotated[
            str,
            ToolArg(
                "Replicate token metric used for case ordering.",
                choices=(
                    "input_tokens",
                    "output_tokens",
                    "total_tokens",
                    "student_total_tokens",
                    "hook_total_tokens",
                ),
            ),
        ] = "total_tokens",
        order: Annotated[
            str,
            ToolArg(
                "Token ordering.",
                choices=("descending", "ascending"),
            ),
        ] = "descending",
    ) -> ToolResult:
        """List logical cases ordered by mean replicate token usage."""

        return _json_result(
            "list_evaluation_cases_by_cost",
            store.list_cases_by_cost(
                page=page,
                page_size=page_size,
                stability=stability,
                token_metric=token_metric,
                order=order,
            ),
        )

    return CallableTool.from_callable(invoke)


def _get_cost_summary(resources: TeacherResources) -> CallableTool:
    store = _require_evaluation(resources)

    @tool(name="get_cost_summary")
    def invoke() -> ToolResult:
        """Read replicate-level token coverage and distribution statistics."""

        return _json_result("get_cost_summary", store.get_cost_summary())

    return CallableTool.from_callable(invoke)


def _get_student_trajectory(resources: TeacherResources) -> CallableTool:
    store = _require_evaluation(resources)

    @tool(name="get_student_trajectory")
    def invoke(
        example_id: Annotated[
            str,
            ToolArg("Example ID returned by list_evaluation_cases."),
        ],
        replicate_id: Annotated[
            str,
            ToolArg("Replicate ID returned by get_evaluation_case."),
        ],
        view: Annotated[
            str,
            ToolArg(
                "Trajectory projection. behavior preserves Student reasoning, "
                "model output, actions, observations, and outcomes while "
                "removing repeated prompt/runtime data. full returns the "
                "complete rollout record.",
                choices=("behavior", "full"),
            ),
        ] = "behavior",
    ) -> ToolResult:
        """Read one Student trajectory at behavior or full diagnostic detail."""

        return _json_result(
            "get_student_trajectory",
            store.get_trajectory(
                example_id=example_id,
                replicate_id=replicate_id,
                view=view,
            ),
        )

    return CallableTool.from_callable(invoke)


def _get_intervention_capabilities(
    resources: TeacherResources,
) -> CallableTool:
    store = _require_evaluation(resources)

    @tool(name="get_intervention_capabilities")
    def invoke() -> ToolResult:
        """Read source-derived trial phases, observations, actions and limits."""

        catalog = intervention_capabilities()
        resources.mark_intervention_capabilities_inspected()
        manifest = store.harness_manifest or {}
        catalog["student"] = {
            "harness_id": manifest.get("harness_id"),
            "tools": [
                item.get("instance_id")
                for item in manifest.get("tools", [])
                if isinstance(item, dict)
            ],
        }
        return _json_result("get_intervention_capabilities", catalog)

    return CallableTool.from_callable(invoke)


def _get_harness_manifest(resources: TeacherResources) -> CallableTool:
    store = _require_evaluation(resources)

    @tool(name="get_harness_manifest")
    def invoke() -> ToolResult:
        """Read the current Student Harness manifest."""

        return _json_result("get_harness_manifest", store.get_harness_manifest())

    return CallableTool.from_callable(invoke)


def _get_harness_component(resources: TeacherResources) -> CallableTool:
    store = _require_evaluation(resources)

    @tool(name="get_harness_component")
    def invoke(
        category: Annotated[
            str,
            ToolArg(
                "Harness component category.",
                choices=("tool", "prompt", "extension"),
            ),
        ],
        component_id: Annotated[
            str,
            ToolArg("Manifest instance_id of the component."),
        ],
    ) -> ToolResult:
        """Read one current Harness component registration and source."""

        return _json_result(
            "get_harness_component",
            store.get_harness_component(
                category=category,
                component_id=component_id,
            ),
        )

    return CallableTool.from_callable(invoke)


def _list_trial_evidence(resources: TeacherResources) -> CallableTool:
    @tool(name="list_trial_evidence")
    def invoke() -> ToolResult:
        """List explicitly attached Intervention trial references and facts."""

        return _json_result(
            "list_trial_evidence",
            _require_trials(resources).list_trials(),
        )

    return CallableTool.from_callable(invoke)


def _get_trial_evidence(resources: TeacherResources) -> CallableTool:
    @tool(name="get_trial_evidence")
    def invoke(
        trial_ref: Annotated[
            str,
            ToolArg("Trial reference returned by list_trial_evidence."),
        ],
    ) -> ToolResult:
        """Read trace-canonical source and branch evidence for one trial."""

        return _json_result(
            "get_trial_evidence",
            _require_trials(resources).get_trial(trial_ref),
        )

    return CallableTool.from_callable(invoke)


def _get_trial_event(resources: TeacherResources) -> CallableTool:
    @tool(name="get_trial_event")
    def invoke(
        trial_ref: Annotated[
            str,
            ToolArg("Trial reference returned by get_trial_evidence."),
        ],
        stream: Annotated[
            str,
            ToolArg(
                "Event stream selected from the trial catalog.",
                choices=("source", "branch", "worker"),
            ),
        ],
        event_index: Annotated[
            int,
            ToolArg("Zero-based event index from the selected catalog.", minimum=0),
        ],
    ) -> ToolResult:
        """Read one exact event from a compact trial evidence catalog."""

        return _json_result(
            "get_trial_event",
            _require_trials(resources).get_trial_event(
                trial_ref=trial_ref,
                stream=stream,
                event_index=event_index,
            ),
        )

    return CallableTool.from_callable(invoke)


def _create_mechanism_draft(resources: TeacherResources) -> CallableTool:
    @tool(name="create_mechanism_draft")
    def invoke(
        goal: Annotated[
            str,
            ToolArg("General Student behavior the mechanism must cause."),
        ],
    ) -> ToolResult:
        """Create an empty no-Teacher mechanism draft."""

        draft_id = resources.mechanisms.create(goal=goal)
        return _json_result(
            "create_mechanism_draft",
            {"draft_id": draft_id},
        )

    return CallableTool.from_callable(invoke)


def _add_mechanism_phase(resources: TeacherResources) -> CallableTool:
    @tool(name="add_mechanism_phase")
    def invoke(
        draft_id: Annotated[
            str,
            ToolArg("Draft ID returned by create_mechanism_draft."),
        ],
        phase: Annotated[
            str,
            ToolArg("Student Hook phase where this rule observes state."),
        ],
        guards: Annotated[
            list[str],
            ToolArg(
                "Deterministic state and budget conditions checked before "
                "the decision evaluator; use an empty list when none apply."
            ),
        ],
        predicate: Annotated[
            str,
            ToolArg("The single case-independent question the evaluator decides."),
        ],
        positive_rule: Annotated[
            str,
            ToolArg("Operational boundary that requires the phase action."),
        ],
        negative_rule: Annotated[
            str,
            ToolArg("Operational boundary that requires a non-trigger result."),
        ],
        uncertain_rule: Annotated[
            str,
            ToolArg("Observable boundary where neither other rule is justified."),
        ],
        positive_evidence: Annotated[
            list[str],
            ToolArg(
                "Case-independent observed categories labeled positive."
            ),
        ],
        negative_evidence: Annotated[
            list[str],
            ToolArg(
                "Case-independent observed categories labeled negative."
            ),
        ],
        uncertain_evidence: Annotated[
            list[str],
            ToolArg(
                "Observed boundary categories labeled uncertain; use an "
                "empty list when no uncertain Trial was observed."
            ),
        ],
        decision_inputs: Annotated[
            list[str],
            ToolArg("Semantic values required by the phase rule."),
        ],
        runtime_inputs: Annotated[
            list[RuntimeInputId],
            ToolArg(
                "Controlled Runtime Input Topics required by this phase. "
                "Choose one or more of: task, conversation, tool, model_io, "
                "parsed_output, final_decision, trajectory, persistent_state."
            ),
        ],
        decision_evaluator: Annotated[
            str,
            ToolArg(
                "How the Hook evaluates trigger predicates: deterministic "
                "for explicit rules, or hook_model for bounded semantic "
                "judgment by an allowed Hook model.",
                choices=("deterministic", "hook_model"),
            ),
        ],
        action: Annotated[
            str,
            ToolArg("One short sentence describing this phase-local action."),
        ],
        fallback_negative: Annotated[
            str,
            ToolArg("Exact phase behavior for a negative evaluator label."),
        ],
        fallback_uncertain: Annotated[
            str,
            ToolArg("Safe phase behavior for an uncertain evaluator label."),
        ],
        fallback_budget_exhausted: Annotated[
            str,
            ToolArg("Exact phase behavior after its activation budget is used."),
        ],
        activation_budget: Annotated[
            int,
            ToolArg(
                "Maximum activations for this phase in one Student rollout.",
                minimum=1,
            ),
        ] = 1,
    ) -> ToolResult:
        """Append one flat phase rule to a no-Teacher mechanism draft."""

        resources.mechanisms.add_phase(
            draft_id=draft_id,
            phase=phase,
            guards=guards,
            predicate=predicate,
            positive_rule=positive_rule,
            negative_rule=negative_rule,
            uncertain_rule=uncertain_rule,
            positive_evidence=positive_evidence,
            negative_evidence=negative_evidence,
            uncertain_evidence=uncertain_evidence,
            decision_inputs=decision_inputs,
            runtime_inputs=runtime_inputs,
            decision_evaluator=decision_evaluator,
            action=action,
            fallback_negative=fallback_negative,
            fallback_uncertain=fallback_uncertain,
            fallback_budget_exhausted=fallback_budget_exhausted,
            activation_budget=activation_budget,
        )
        return _json_result(
            "add_mechanism_phase",
            {"draft_id": draft_id, "phase": phase, "added": True},
        )

    return CallableTool.from_callable(invoke)


def _complete_mechanism_draft(resources: TeacherResources) -> CallableTool:
    @tool(name="complete_mechanism_draft")
    def invoke(
        draft_id: Annotated[
            str,
            ToolArg("Draft ID returned by create_mechanism_draft."),
        ],
        behavioral_pseudocode: Annotated[
            str,
            ToolArg(
                "Implementation-neutral control flow, state transitions, "
                "Student obligations, and fallback; maximum 3000 characters."
            ),
        ],
        state_scope: Annotated[
            str,
            ToolArg("State retained by the mechanism and its lifetime."),
        ],
        expected_behavior: Annotated[
            str,
            ToolArg("Observable Student process effect after activation."),
        ],
    ) -> ToolResult:
        """Complete one mechanism draft's shared state and control flow."""

        resources.mechanisms.complete(
            draft_id=draft_id,
            behavioral_pseudocode=behavioral_pseudocode,
            state_scope=state_scope,
            expected_behavior=expected_behavior,
        )
        return _json_result(
            "complete_mechanism_draft",
            {"draft_id": draft_id, "completed": True},
        )

    return CallableTool.from_callable(invoke)


def _validate_mechanism_draft(resources: TeacherResources) -> CallableTool:
    @tool(name="validate_mechanism_draft")
    def invoke(
        draft_id: Annotated[
            str,
            ToolArg("Completed mechanism draft ID."),
        ],
        evidence_refs: Annotated[
            list[str],
            ToolArg("Trial references supporting this exact mechanism."),
        ],
    ) -> ToolResult:
        """Validate a complete mechanism draft and return its stable reference."""

        mechanism_ref = resources.mechanisms.validate(
            draft_id=draft_id,
            evidence_refs=evidence_refs,
        )
        return _json_result(
            "validate_mechanism_draft",
            {"mechanism_ref": mechanism_ref, "validated": True},
        )

    return CallableTool.from_callable(invoke)


def _probe_mechanism_evaluators(
    resources: TeacherResources,
) -> CallableTool:
    @tool(name="probe_mechanism_evaluators")
    def invoke(
        draft_id: Annotated[
            str,
            ToolArg("Completed mechanism draft ID to probe."),
        ],
        evidence_refs: Annotated[
            list[str],
            ToolArg("Trial references supporting the draft labels."),
        ],
        repetitions: Annotated[
            int,
            ToolArg(
                "Repeated classifications per labeled fixture.",
                minimum=1,
                maximum=3,
            ),
        ] = 3,
    ) -> ToolResult:
        """Run the production Hook model on every labeled decision fixture."""

        return _json_result(
            "probe_mechanism_evaluators",
            resources.probe_mechanism_evaluators(
                draft_id=draft_id,
                evidence_refs=evidence_refs,
                repetitions=repetitions,
            ),
        )

    return CallableTool.from_callable(invoke)


def _set_mechanism_constraints(resources: TeacherResources) -> CallableTool:
    @tool(name="set_mechanism_constraints")
    def invoke(
        draft_id: Annotated[
            str,
            ToolArg("Draft ID returned by create_mechanism_draft."),
        ],
        required_capabilities: Annotated[
            list[str],
            ToolArg(
                "Harness runtime and Student capabilities required by this "
                "mechanism, including any non-trigger Hook model use."
            ),
        ],
        prohibited_behaviors: Annotated[
            list[str],
            ToolArg("Actions the compiled mechanism must never perform."),
        ],
        observability: Annotated[
            list[str],
            ToolArg("Trace signals required to verify activation and effect."),
        ],
        known_limits: Annotated[
            list[str],
            ToolArg("Known cases the mechanism cannot solve."),
        ],
    ) -> ToolResult:
        """Attach bounded-execution and audit constraints to a mechanism draft."""

        resources.mechanisms.set_constraints(
            draft_id=draft_id,
            required_capabilities=required_capabilities,
            prohibited_behaviors=prohibited_behaviors,
            observability=observability,
            known_limits=known_limits,
        )
        return _json_result(
            "set_mechanism_constraints",
            {"draft_id": draft_id, "constraints_set": True},
        )

    return CallableTool.from_callable(invoke)


def _list_intervention_timeline(resources: TeacherResources) -> CallableTool:
    store = _require_intervention(resources)

    @tool(name="list_intervention_timeline")
    def invoke() -> ToolResult:
        """List recoverable Student context boundaries for the assigned trial."""

        return _json_result("list_intervention_timeline", store.timeline())

    return CallableTool.from_callable(invoke)


def _inspect_intervention_prefix(resources: TeacherResources) -> CallableTool:
    store = _require_intervention(resources)

    @tool(name="inspect_intervention_prefix")
    def invoke() -> ToolResult:
        """Inspect the selected Student-visible prefix before choosing an action."""

        return _json_result(
            "inspect_intervention_prefix",
            store.inspect_selected_prefix(),
        )

    return CallableTool.from_callable(invoke)


def _run_intervention_branch(resources: TeacherResources) -> CallableTool:
    store = _require_intervention(resources)

    @tool(name="run_intervention_branch")
    def invoke(
        action: Annotated[
            str,
            ToolArg(
                "Single context or control action.",
                choices=(
                    "append_user_message",
                    "append_system_message",
                    "replace_system_instruction",
                    "defer_final_answer",
                    "no_op",
                ),
            ),
        ],
        rationale: Annotated[
            str,
            ToolArg("Why this action tests the frozen hypothesis."),
        ],
        content: Annotated[
            str,
            ToolArg("Action text. Use an empty string only for no_op."),
        ] = "",
    ) -> ToolResult:
        """Apply one intervention and run the Student from the selected prefix."""

        normalized = content.strip() or None
        return _json_result(
            "run_intervention_branch",
            store.run_branch(
                action=action,
                content=normalized,
                rationale=rationale,
            ),
        )

    return CallableTool.from_callable(invoke)


def _list_harness_files(resources: TeacherResources) -> CallableTool:
    store = _require_compiler(resources)

    @tool(name="list_harness_files")
    def invoke() -> ToolResult:
        """List the current in-memory candidate Harness files."""

        return _json_result("list_harness_files", store.list_files())

    return CallableTool.from_callable(invoke)


def _read_harness_file(resources: TeacherResources) -> CallableTool:
    store = _require_compiler(resources)

    @tool(name="read_harness_file")
    def invoke(
        path: Annotated[
            str,
            ToolArg("POSIX path relative to the Template Root."),
        ],
    ) -> ToolResult:
        """Read one UTF-8 file from the in-memory candidate Harness."""

        return _json_result("read_harness_file", store.read_file(path))

    return CallableTool.from_callable(invoke)


def _get_hook_authoring_guide(resources: TeacherResources) -> CallableTool:
    store = _require_compiler(resources)

    @tool(name="get_hook_authoring_guide")
    def invoke(
        topic: Annotated[
            str,
            ToolArg(
                "Authoritative Hook API guide section.",
                choices=(
                    "index",
                    "implementation",
                    "lifecycle",
                    "state_access",
                    "model_inference",
                    "final_decision",
                    "manifest",
                ),
            ),
        ],
    ) -> ToolResult:
        """Read one progressively disclosed Hook authoring guide section."""

        return _json_result(
            "get_hook_authoring_guide",
            store.authoring_guide(topic),
        )

    return CallableTool.from_callable(invoke)


def _list_hook_api_symbols(resources: TeacherResources) -> CallableTool:
    store = _require_compiler(resources)

    @tool(name="list_hook_api_symbols")
    def invoke(
        category: Annotated[
            str,
            ToolArg(
                "Public Hook API category.",
                choices=hook_api_categories(),
            ),
        ] = "all",
        page: Annotated[int, ToolArg("One-based page number.", minimum=1)] = 1,
        page_size: Annotated[
            int,
            ToolArg("Symbols per page.", minimum=1, maximum=50),
        ] = 20,
    ) -> ToolResult:
        """List public Hook classes and state keys by category."""

        return _json_result(
            "list_hook_api_symbols",
            store.list_hook_api(
                category=category,
                page=page,
                page_size=page_size,
            ),
        )

    return CallableTool.from_callable(invoke)


def _query_hook_api(resources: TeacherResources) -> CallableTool:
    store = _require_compiler(resources)

    @tool(name="query_hook_api")
    def invoke(
        symbol: Annotated[
            str,
            ToolArg(
                "A Runtime Input Topic ID such as tool, an exact public symbol, "
                "or a short search phrase. Topic and unknown-query suggestions do "
                "not consume the twelve-symbol exact-query budget."
            ),
        ],
    ) -> ToolResult:
        """Resolve one Topic or API contract and suggest nearby public inputs."""

        return _json_result(
            "query_hook_api",
            store.query_hook_api(symbol),
        )

    return CallableTool.from_callable(invoke)


def _write_candidate_file(resources: TeacherResources) -> CallableTool:
    store = _require_compiler(resources)

    @tool(name="write_candidate_file")
    def invoke(
        path: Annotated[
            str,
            ToolArg("POSIX path relative to the Template Root."),
        ],
        content: Annotated[
            str,
            ToolArg("Complete UTF-8 replacement content for the file."),
        ],
    ) -> ToolResult:
        """Create or replace one mutable file in the candidate workspace."""

        return _json_result(
            "write_candidate_file",
            store.write_file(path=path, content=content),
        )

    return CallableTool.from_callable(invoke)


def _delete_candidate_file(resources: TeacherResources) -> CallableTool:
    store = _require_compiler(resources)

    @tool(name="delete_candidate_file")
    def invoke(
        path: Annotated[
            str,
            ToolArg("POSIX path relative to the Template Root."),
        ],
    ) -> ToolResult:
        """Delete one mutable file from the candidate workspace."""

        return _json_result(
            "delete_candidate_file",
            store.delete_file(path=path),
        )

    return CallableTool.from_callable(invoke)


def _show_candidate_diff(resources: TeacherResources) -> CallableTool:
    store = _require_compiler(resources)

    @tool(name="show_candidate_diff")
    def invoke() -> ToolResult:
        """Show the complete candidate diff against its parent Harness."""

        return _json_result("show_candidate_diff", store.diff())

    return CallableTool.from_callable(invoke)


def _validate_candidate(resources: TeacherResources) -> CallableTool:
    store = _require_compiler(resources)

    @tool(name="validate_candidate")
    def invoke() -> ToolResult:
        """Run manifest, fixed-boundary, syntax and assembly validation."""

        return _json_result("validate_candidate", store.validate())

    return CallableTool.from_callable(invoke)


def _submit_candidate(resources: TeacherResources) -> CallableTool:
    store = _require_compiler(resources)

    @tool(name="submit_candidate")
    def invoke(
        summary: Annotated[
            str,
            ToolArg("Concise description of the validated implementation."),
        ],
    ) -> ToolResult:
        """Freeze the latest validated workspace as this run's candidate."""

        return _json_result(
            "submit_candidate",
            store.submit(summary=summary),
        )

    return CallableTool.from_callable(invoke)


def _finalize_candidate(resources: TeacherResources) -> CallableTool:
    store = _require_compiler(resources)

    @tool(name="finalize_candidate")
    def invoke(
        summary: Annotated[
            str,
            ToolArg("Concise description of the candidate implementation."),
        ],
    ) -> ToolResult:
        """Validate and freeze the current revision, or return repair errors."""

        return _json_result(
            "finalize_candidate",
            store.finalize(summary=summary),
        )

    return CallableTool.from_callable(invoke)


def _list_candidate_changes(resources: TeacherResources) -> CallableTool:
    store = _require_candidate_review(resources)

    @tool(name="list_candidate_changes")
    def invoke(
        page: Annotated[int, ToolArg("One-based page number.", minimum=1)] = 1,
        page_size: Annotated[
            int,
            ToolArg("Cases per page.", minimum=1, maximum=20),
        ] = 10,
        change: Annotated[
            str,
            ToolArg(
                "Paired outcome filter.",
                choices=("any", "improved", "regressed", "unchanged"),
            ),
        ] = "any",
    ) -> ToolResult:
        """List paired incumbent/candidate outcome changes."""

        return _json_result(
            "list_candidate_changes",
            store.list_changes(
                page=page,
                page_size=page_size,
                change=change,
            ),
        )

    return CallableTool.from_callable(invoke)


def _get_candidate_case(resources: TeacherResources) -> CallableTool:
    store = _require_candidate_review(resources)

    @tool(name="get_candidate_case")
    def invoke(
        example_id: Annotated[
            str,
            ToolArg("Example ID returned by list_candidate_changes."),
        ],
    ) -> ToolResult:
        """Read paired evaluation details for one logical example."""

        return _json_result(
            "get_candidate_case",
            store.get_case(example_id),
        )

    return CallableTool.from_callable(invoke)


def _get_paired_student_trajectory(resources: TeacherResources) -> CallableTool:
    store = _require_candidate_review(resources)

    @tool(name="get_paired_student_trajectory")
    def invoke(
        example_id: Annotated[
            str,
            ToolArg("Example ID returned by list_candidate_changes."),
        ],
        replicate_id: Annotated[
            str,
            ToolArg("Replicate ID present in both evaluations."),
        ],
    ) -> ToolResult:
        """Read paired Student trajectories for one example replicate."""

        return _json_result(
            "get_paired_student_trajectory",
            store.get_paired_trajectory(
                example_id=example_id,
                replicate_id=replicate_id,
            ),
        )

    return CallableTool.from_callable(invoke)


def _get_candidate_harness_diff(resources: TeacherResources) -> CallableTool:
    store = _require_candidate_review(resources)

    @tool(name="get_candidate_harness_diff")
    def invoke() -> ToolResult:
        """Read the candidate Harness file diff when roots were configured."""

        return _json_result(
            "get_candidate_harness_diff",
            store.harness_diff(),
        )

    return CallableTool.from_callable(invoke)


def _require_evaluation(
    resources: TeacherResources,
) -> EvaluationEvidenceStore:
    if resources.evaluation is None:
        raise ValueError("Teacher template requires evaluation resources")
    return resources.evaluation


def _require_trials(resources: TeacherResources) -> TrialEvidenceStore:
    if resources.trials is None:
        raise ValueError("Teacher template requires trial resources")
    return resources.trials


def _require_intervention(
    resources: TeacherResources,
) -> InterventionBranchStore:
    if resources.intervention is None:
        raise ValueError("Teacher template requires intervention resources")
    return resources.intervention


def _require_compiler(
    resources: TeacherResources,
) -> CompilerWorkspaceStore:
    if resources.compiler is None:
        raise ValueError("Teacher template requires compiler resources")
    return resources.compiler


def _require_candidate_review(
    resources: TeacherResources,
) -> CandidateComparisonStore:
    if resources.candidate_review is None:
        raise ValueError("Teacher template requires candidate_review resources")
    return resources.candidate_review


def _json_result(name: str, payload: Any) -> ToolResult:
    return ToolResult(
        name=name,
        content=json.dumps(payload, ensure_ascii=False),
    )
