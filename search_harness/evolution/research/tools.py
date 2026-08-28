"""Teacher templates 可显式注册的内置只读工具和机制草稿工具。"""

from __future__ import annotations

import json
from typing import Annotated, Any, Callable, Literal

from search_harness.framework import ToolResult
from search_harness.framework.tools import CallableTool, ToolArg, tool
from search_harness.framework.harness import ComponentFactoryContext

from .compiler_views import render_hook_api_result
from .experience_summary import (
    ExperienceDetailStore,
)
from .candidate_views import (
    render_candidate_case,
    render_candidate_changes,
    render_candidate_harness_diff,
    render_candidate_trajectory_text,
    render_paired_candidate_trajectory,
)
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
from .views import (
    TeacherTrajectoryView,
    render_evaluation_case,
    render_distillation_trial_detail,
    render_student_behavior_interface,
    render_student_capability_view,
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
        "get_trajectory_change": _get_trajectory_change,
        "get_trajectory_block": _get_trajectory_block,
        "search_hidden_trajectory_blocks": _search_hidden_trajectory_blocks,
        "get_student_capability_view": _get_student_capability_view,
        "get_student_behavior_interface": _get_student_behavior_interface,
        "get_distillation_trial_detail": _get_distillation_trial_detail,
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
        "create_shadow_mechanism_draft": _create_shadow_mechanism_draft,
        "add_shadow_decision_phase": _add_shadow_decision_phase,
        "add_shadow_generation_phase": _add_shadow_generation_phase,
        "validate_shadow_mechanism_draft": (
            _validate_shadow_mechanism_draft
        ),
        "run_hook_prompt_probe": _run_hook_prompt_probe,
        "run_student_model_experiment": _run_student_model_experiment,
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
        "bind_hook_prompt_products": _bind_hook_prompt_products,
        "show_candidate_diff": _show_candidate_diff,
        "validate_candidate": _validate_candidate,
        "submit_candidate": _submit_candidate,
        "finalize_candidate": _finalize_candidate,
        "list_candidate_changes": _list_candidate_changes,
        "get_candidate_case": _get_candidate_case,
        "get_paired_student_trajectory": _get_paired_student_trajectory,
        "get_candidate_harness_diff": _get_candidate_harness_diff,
        "get_candidate_trajectory_text": _get_candidate_trajectory_text,
        "get_recent_candidate_digest": _get_recent_candidate_digest,
        "list_recent_candidate_cases": _list_recent_candidate_cases,
        "get_recent_candidate_case": _get_recent_candidate_case,
        "get_recent_candidate_trajectory": _get_recent_candidate_trajectory,
        "get_recent_candidate_implementation": (
            _get_recent_candidate_implementation
        ),
        "inspect_experience_detail": _inspect_experience_detail,
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
            ToolArg("Cases per page.", minimum=1, maximum=100),
        ] = 100,
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

        return _text_result(
            "get_evaluation_case",
            render_evaluation_case(store.get_case(example_id)),
        )

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
    ) -> ToolResult:
        """Read a de-duplicated Student behavior and context-revision view."""

        return _text_result(
            "get_student_trajectory",
            _trajectory_view(store, example_id, replicate_id).render(),
        )

    return CallableTool.from_callable(invoke)


def _get_trajectory_block(resources: TeacherResources) -> CallableTool:
    store = _require_evaluation(resources)

    @tool(name="get_trajectory_block")
    def invoke(
        example_id: Annotated[str, ToolArg("Trajectory example ID.")],
        replicate_id: Annotated[str, ToolArg("Trajectory replicate ID.")],
        block_id: Annotated[
            int,
            ToolArg("Numeric block ID from the trajectory view.", minimum=1),
        ],
        revision: Annotated[
            int,
            ToolArg("Block revision from the trajectory view.", minimum=1),
        ] = 1,
        offset: Annotated[
            int,
            ToolArg("Zero-based character offset.", minimum=0),
        ] = 0,
        max_characters: Annotated[
            int,
            ToolArg(
                "Maximum exact characters to return.",
                minimum=1,
                maximum=12000,
            ),
        ] = 4000,
    ) -> ToolResult:
        """Read one exact Context Block slice by stable reference."""

        view = _trajectory_view(store, example_id, replicate_id)
        return _text_result(
            "get_trajectory_block",
            view.read_block(
                block_id=block_id,
                revision=revision,
                offset=offset,
                max_characters=max_characters,
            ),
        )

    return CallableTool.from_callable(invoke)


def _get_trajectory_change(resources: TeacherResources) -> CallableTool:
    store = _require_evaluation(resources)

    @tool(name="get_trajectory_change")
    def invoke(
        example_id: Annotated[str, ToolArg("Trajectory example ID.")],
        replicate_id: Annotated[str, ToolArg("Trajectory replicate ID.")],
        change_id: Annotated[
            str,
            ToolArg("Change ID returned by get_student_trajectory."),
        ],
    ) -> ToolResult:
        """Read one Extension Change and its source/effective block directory."""

        return _text_result(
            "get_trajectory_change",
            _trajectory_view(store, example_id, replicate_id).render_change(
                change_id
            ),
        )

    return CallableTool.from_callable(invoke)


def _search_hidden_trajectory_blocks(
    resources: TeacherResources,
) -> CallableTool:
    store = _require_evaluation(resources)

    @tool(name="search_hidden_trajectory_blocks")
    def invoke(
        example_id: Annotated[str, ToolArg("Trajectory example ID.")],
        replicate_id: Annotated[str, ToolArg("Trajectory replicate ID.")],
        query: Annotated[
            str,
            ToolArg("Literal text to find in Runtime-only block contents."),
        ],
        max_matches: Annotated[
            int,
            ToolArg("Maximum returned matches.", minimum=1, maximum=20),
        ] = 8,
    ) -> ToolResult:
        """Search Runtime-only source blocks before exact retrieval."""

        return _text_result(
            "search_hidden_trajectory_blocks",
            _trajectory_view(store, example_id, replicate_id).search_runtime_blocks(
                query,
                max_matches=max_matches,
            ),
        )

    return CallableTool.from_callable(invoke)


def _get_student_capability_view(
    resources: TeacherResources,
) -> CallableTool:
    store = _require_evaluation(resources)

    @tool(name="get_student_capability_view")
    def invoke() -> ToolResult:
        """Read Student-observable registered capabilities, not source code."""

        return _text_result(
            "get_student_capability_view",
            render_student_capability_view(
                manifest=store.harness_manifest or {},
                records=_evaluation_records(store),
            ),
        )

    return CallableTool.from_callable(invoke)


def _get_student_behavior_interface(
    resources: TeacherResources,
) -> CallableTool:
    store = _require_evaluation(resources)

    @tool(name="get_student_behavior_interface")
    def invoke(
        example_id: Annotated[
            str,
            ToolArg("One cited trajectory's example ID."),
        ],
        replicate_id: Annotated[
            str,
            ToolArg("One cited trajectory's replicate ID."),
        ],
    ) -> ToolResult:
        """Read the exact Student-visible prompt and behavior surface."""

        reference = f"{example_id}/{replicate_id}"
        reads = set(store.role_session_state().get("trajectory_reads", []))
        if reference not in reads:
            raise ValueError(
                "inspect this trajectory through get_student_trajectory "
                "before reading its Student Behavior Interface"
            )
        return _text_result(
            "get_student_behavior_interface",
            render_student_behavior_interface(
                manifest=store.harness_manifest or {},
                record=store.rollouts[example_id][replicate_id],
            ),
        )

    return CallableTool.from_callable(invoke)


def _get_distillation_trial_detail(
    resources: TeacherResources,
) -> CallableTool:
    store = _require_trials(resources)

    @tool(name="get_distillation_trial_detail")
    def invoke(
        trial_ref: Annotated[
            str,
            ToolArg(
                "Trial reference listed in the Distillation Evidence Dossier."
            ),
        ],
    ) -> ToolResult:
        """Read one focused event catalog only to resolve an ambiguity."""

        return _text_result(
            "get_distillation_trial_detail",
            render_distillation_trial_detail(store.get_trial(trial_ref)),
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


def _create_shadow_mechanism_draft(
    resources: TeacherResources,
) -> CallableTool:
    @tool(name="create_shadow_mechanism_draft")
    def invoke(
        effect_kind: Annotated[
            Literal["task_outcome", "behavioral_intermediate"],
            ToolArg("Observable effect category supported by the Trials."),
        ],
        effect_success: Annotated[
            str,
            ToolArg(
                "Smallest observable Candidate success condition, without "
                "historical Trial narration."
            ),
        ],
    ) -> ToolResult:
        """Start one minimal Shadow Mechanism draft."""

        draft_id = resources.shadow_mechanisms.create(
            effect_kind=effect_kind,
            effect_success=effect_success,
        )
        return _json_result(
            "create_shadow_mechanism_draft",
            {"draft_id": draft_id},
        )

    return CallableTool.from_callable(invoke)


def _run_hook_prompt_probe(resources: TeacherResources) -> CallableTool:
    @tool(name="run_hook_prompt_probe")
    def invoke(
        prompt: Annotated[
            str,
            ToolArg(
                "Complete candidate system Prompt for the frozen Hook-model "
                "Task; maximum 6000 characters."
            ),
        ],
    ) -> ToolResult:
        """Probe one candidate Prompt on fixed reviewed real-prefix inputs."""

        store = resources.shadow_prompt_research
        if store is None:
            raise ValueError("Shadow Prompt Research resources are unavailable")
        return _json_result(
            "run_hook_prompt_probe",
            store.run_probe(prompt=prompt),
        )

    return CallableTool.from_callable(invoke)


def _add_shadow_decision_phase(
    resources: TeacherResources,
) -> CallableTool:
    @tool(name="add_shadow_decision_phase")
    def invoke(
        draft_id: Annotated[
            str,
            ToolArg("Draft ID returned by create_shadow_mechanism_draft."),
        ],
        phase: Annotated[
            str,
            ToolArg(
                "Harness phase for this task.",
                choices=(
                    "post_prompt",
                    "post_model",
                    "post_parse",
                    "pre_tool",
                    "post_tool",
                    "pre_final",
                ),
            ),
        ],
        guards: Annotated[
            list[str],
            ToolArg("Deterministic conditions checked before the task."),
        ],
        evaluator: Annotated[
            Literal["deterministic", "hook_model"],
            ToolArg("Executor for the three-label decision."),
        ],
        inputs: Annotated[
            list[dict[str, object]],
            ToolArg(
                "Ordered Task Inputs. Each object has name and a non-empty "
                "sources array from the controlled Source Catalog."
            ),
        ],
        positive: Annotated[
            str,
            ToolArg("Semantic boundary that executes on_success."),
        ],
        negative: Annotated[
            str,
            ToolArg("Semantic boundary that uses fallback.default."),
        ],
        uncertain: Annotated[
            str,
            ToolArg("Boundary where the declared inputs cannot decide."),
        ],
        on_success: Annotated[
            str,
            ToolArg("Complete phase-local positive action."),
        ],
        fallback_default: Annotated[
            str,
            ToolArg(
                "Default fallback; use exactly continue_without_change for "
                "a no-op."
            ),
        ],
        activation_limit: Annotated[
            int,
            ToolArg(
                "Maximum successful activations per Student rollout.",
                minimum=1,
                maximum=20,
            ),
        ] = 1,
        fallback_uncertain: Annotated[
            str,
            ToolArg(
                "Override for uncertain; empty string inherits default."
            ),
        ] = "",
        fallback_exhausted: Annotated[
            str,
            ToolArg(
                "Override after budget exhaustion; empty string inherits "
                "default."
            ),
        ] = "",
    ) -> ToolResult:
        """Validate and append one Shadow Decision phase."""

        resources.shadow_mechanisms.add_phase(
            draft_id=draft_id,
            phase_payload={
                "phase": phase,
                "guards": guards,
                "task": {
                    "kind": "decision",
                    "evaluator": evaluator,
                    "inputs": inputs,
                    "positive": positive,
                    "negative": negative,
                    "uncertain": uncertain,
                },
                "on_success": on_success,
                "fallback": {
                    "default": fallback_default,
                    "uncertain": fallback_uncertain or None,
                    "exhausted": fallback_exhausted or None,
                },
                "activation_limit": activation_limit,
            },
        )
        return _json_result(
            "add_shadow_decision_phase",
            {"draft_id": draft_id, "phase": phase, "added": True},
        )

    return CallableTool.from_callable(invoke)


def _add_shadow_generation_phase(
    resources: TeacherResources,
) -> CallableTool:
    @tool(name="add_shadow_generation_phase")
    def invoke(
        draft_id: Annotated[
            str,
            ToolArg("Draft ID returned by create_shadow_mechanism_draft."),
        ],
        phase: Annotated[
            str,
            ToolArg(
                "Harness phase for this task.",
                choices=(
                    "post_prompt",
                    "post_model",
                    "post_parse",
                    "pre_tool",
                    "post_tool",
                    "pre_final",
                ),
            ),
        ],
        guards: Annotated[
            list[str],
            ToolArg("Deterministic conditions checked before the task."),
        ],
        inputs: Annotated[
            list[dict[str, object]],
            ToolArg(
                "Ordered Task Inputs. Each object has name and a non-empty "
                "sources array from the controlled Source Catalog."
            ),
        ],
        output_name: Annotated[
            str,
            ToolArg("Identifier used by on_success for generated text."),
        ],
        requirement: Annotated[
            str,
            ToolArg("Semantic content and preservation requirements."),
        ],
        on_success: Annotated[
            str,
            ToolArg("Complete action consuming output_name."),
        ],
        fallback_default: Annotated[
            str,
            ToolArg(
                "Fallback for empty or unusable text; use exactly "
                "continue_without_change for a no-op."
            ),
        ],
        activation_limit: Annotated[
            int,
            ToolArg(
                "Maximum successful activations per Student rollout.",
                minimum=1,
                maximum=20,
            ),
        ] = 1,
        fallback_exhausted: Annotated[
            str,
            ToolArg(
                "Override after budget exhaustion; empty string inherits "
                "default."
            ),
        ] = "",
    ) -> ToolResult:
        """Validate and append one Shadow Generation phase."""

        resources.shadow_mechanisms.add_phase(
            draft_id=draft_id,
            phase_payload={
                "phase": phase,
                "guards": guards,
                "task": {
                    "kind": "generation",
                    "evaluator": "hook_model",
                    "inputs": inputs,
                    "output_name": output_name,
                    "requirement": requirement,
                },
                "on_success": on_success,
                "fallback": {
                    "default": fallback_default,
                    "uncertain": None,
                    "exhausted": fallback_exhausted or None,
                },
                "activation_limit": activation_limit,
            },
        )
        return _json_result(
            "add_shadow_generation_phase",
            {"draft_id": draft_id, "phase": phase, "added": True},
        )

    return CallableTool.from_callable(invoke)


def _validate_shadow_mechanism_draft(
    resources: TeacherResources,
) -> CallableTool:
    @tool(name="validate_shadow_mechanism_draft")
    def invoke(
        draft_id: Annotated[
            str,
            ToolArg("Draft ID returned by create_shadow_mechanism_draft."),
        ],
        state: Annotated[
            list[dict[str, object]],
            ToolArg(
                "Rollout-local state declarations with name, value_type and "
                "initial; use an empty list for a stateless mechanism."
            ),
        ],
        constraints: Annotated[
            list[str],
            ToolArg(
                "Only non-derivable implementation invariants; use an empty "
                "list when none exist."
            ),
        ],
    ) -> ToolResult:
        """Validate and freeze one assembled Shadow Mechanism."""

        mechanism_ref = resources.shadow_mechanisms.validate(
            draft_id=draft_id,
            state=state,
            constraints=constraints,
        )
        return _json_result(
            "validate_shadow_mechanism_draft",
            {"mechanism_ref": mechanism_ref, "validated": True},
        )

    return CallableTool.from_callable(invoke)


def _create_mechanism_draft(resources: TeacherResources) -> CallableTool:
    @tool(name="create_mechanism_draft")
    def invoke(
        goal: Annotated[
            str,
            ToolArg("General Student behavior the mechanism must cause."),
        ],
        effect_goal: Annotated[
            str,
            ToolArg(
                "Promotion objective: task_outcome requires attributable task "
                "benefit; behavioral_intermediate requires the declared process "
                "change while task outcome remains a safety guardrail.",
                choices=("task_outcome", "behavioral_intermediate"),
            ),
        ] = "task_outcome",
    ) -> ToolResult:
        """Create an empty no-Teacher mechanism draft."""

        draft_id = resources.mechanisms.create(
            goal=goal,
            effect_goal=effect_goal,
        )
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


def _run_student_model_experiment(
    resources: TeacherResources,
) -> CallableTool:
    @tool(name="run_student_model_experiment")
    def invoke(
        purpose: Annotated[
            str,
            ToolArg(
                "Question this descriptive experiment is intended to answer; "
                "maximum 300 characters, preferably no more than 240."
            ),
        ],
        system_prompt: Annotated[
            str,
            ToolArg(
                "Exact system instruction shown to the Student model; maximum "
                "6000 characters. Include the proposed output format and "
                "decision task when relevant."
            ),
        ],
        cases: Annotated[
            list[dict[str, object]],
            ToolArg(
                "One to six inputs shaped as "
                "{case_id:<unique string>, user_prompt:<exact string>}."
            ),
        ],
        thinking_modes: Annotated[
            list[str],
            ToolArg(
                "One or both per-request modes: enabled and disabled. Results "
                "are descriptive; the program does not choose a winner."
            ),
        ],
        repetitions: Annotated[
            int,
            ToolArg(
                "Repeated generations per case and thinking mode.",
                minimum=1,
                maximum=3,
            ),
        ] = 3,
    ) -> ToolResult:
        """Run bounded Student generations and return raw outputs and usage."""

        artifact = resources.run_student_model_experiment(
            purpose=purpose,
            system_prompt=system_prompt,
            cases=cases,
            thinking_modes=thinking_modes,
            repetitions=repetitions,
        )
        grouped: dict[tuple[str, str], dict[str, object]] = {}
        for observation in artifact["observations"]:
            key = (
                str(observation["case_id"]),
                str(observation["thinking_mode"]),
            )
            bucket = grouped.setdefault(
                key,
                {
                    "case_id": key[0],
                    "thinking_mode": key[1],
                    "outputs": [],
                    "total_tokens": 0,
                    "errors": [],
                },
            )
            output = observation.get("raw_output")
            bucket["outputs"].append(output)
            usage = observation.get("usage")
            usage = usage if isinstance(usage, dict) else {}
            total_tokens = usage.get("total_tokens", 0)
            if isinstance(total_tokens, int) and not isinstance(
                total_tokens,
                bool,
            ):
                bucket["total_tokens"] += max(0, total_tokens)
            error = observation.get("error")
            if error is not None:
                bucket["errors"].append(error)
        return _json_result(
            "run_student_model_experiment",
            {
                "experiment_id": artifact["experiment_id"],
                "experiment_signature": artifact["experiment_signature"],
                "cache_hit": artifact.get("cache_hit", False),
                "purpose": artifact["purpose"],
                "thinking_modes": artifact["thinking_modes"],
                "repetitions": artifact["repetitions"],
                "case_mode_results": list(grouped.values()),
                "provider_metadata_retained_in_artifact": True,
            },
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

        return _text_result(
            "query_hook_api",
            render_hook_api_result(store.query_hook_api(symbol)),
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


def _bind_hook_prompt_products(resources: TeacherResources) -> CallableTool:
    store = _require_compiler(resources)

    @tool(name="bind_hook_prompt_products")
    def invoke(
        instance_id: Annotated[
            str,
            ToolArg(
                "Mutable extension instance_id that consumes every managed "
                "Prompt Product in this Shadow Mechanism."
            ),
        ],
    ) -> ToolResult:
        """Materialize immutable Prompt Product bindings beside one extension."""

        return _json_result(
            "bind_hook_prompt_products",
            store.materialize_managed_prompt_products(instance_id=instance_id),
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
                "Paired outcome filter. The default lists improved and "
                "regressed cases before unchanged drill-down.",
                choices=("any", "improved", "regressed", "unchanged"),
            ),
        ] = "any",
    ) -> ToolResult:
        """List a changed-first incumbent/candidate outcome directory."""

        return _text_result(
            "list_candidate_changes",
            render_candidate_changes(
                store,
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
        """Read a paired Evaluation Case with replicate-level deltas."""

        return _text_result(
            "get_candidate_case",
            render_candidate_case(store, example_id),
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
            ToolArg(
                "A decisive replicate ID from get_candidate_case. Prefer an "
                "actual score-changing or mechanism-boundary pair."
            ),
        ],
    ) -> ToolResult:
        """Read one self-contained paired Candidate effect trajectory."""

        return _text_result(
            "get_paired_student_trajectory",
            render_paired_candidate_trajectory(
                store,
                example_id=example_id,
                replicate_id=replicate_id,
            ),
        )

    return CallableTool.from_callable(invoke)


def _get_candidate_harness_diff(resources: TeacherResources) -> CallableTool:
    store = _require_candidate_review(resources)

    @tool(name="get_candidate_harness_diff")
    def invoke(
        path: Annotated[
            str,
            ToolArg(
                "Exact changed path, or an empty string for a complete small "
                "diff or a large-diff directory."
            ),
        ] = "",
    ) -> ToolResult:
        """Read the Candidate Harness diff with size-aware path drill-down."""

        return _text_result(
            "get_candidate_harness_diff",
            render_candidate_harness_diff(store, path=path or None),
        )

    return CallableTool.from_callable(invoke)


def _get_candidate_trajectory_text(
    resources: TeacherResources,
) -> CallableTool:
    store = _require_candidate_review(resources)

    @tool(name="get_candidate_trajectory_text")
    def invoke(
        example_id: Annotated[str, ToolArg("Trajectory example ID.")],
        replicate_id: Annotated[str, ToolArg("Trajectory replicate ID.")],
        side: Annotated[
            str,
            ToolArg(
                "Paired trajectory side.",
                choices=("incumbent", "candidate"),
            ),
        ],
        event_index: Annotated[int, ToolArg("Exact event index.", minimum=0)],
        field: Annotated[
            str,
            ToolArg(
                "Exact long-text field exposed by the paired view.",
                choices=(
                    "tool_result_content",
                    "hook_raw_output",
                    "hook_model_input",
                    "final_answer",
                ),
            ),
        ],
        offset: Annotated[
            int,
            ToolArg("Zero-based character offset.", minimum=0),
        ] = 0,
        max_characters: Annotated[
            int,
            ToolArg("Maximum exact characters.", minimum=1, maximum=12000),
        ] = 4000,
    ) -> ToolResult:
        """Read one exact long text field when a preview is insufficient."""

        return _text_result(
            "get_candidate_trajectory_text",
            render_candidate_trajectory_text(
                store,
                example_id=example_id,
                replicate_id=replicate_id,
                side=side,
                event_index=event_index,
                field=field,
                offset=offset,
                max_characters=max_characters,
            ),
        )

    return CallableTool.from_callable(invoke)


def _get_recent_candidate_digest(resources: TeacherResources) -> CallableTool:
    @tool(name="get_recent_candidate_digest")
    def invoke() -> ToolResult:
        """Read the most recent rejected Candidate's compact outcome summary."""

        store = _require_candidate_review(resources)
        return _json_result("get_recent_candidate_digest", store.outcome_digest())

    return CallableTool.from_callable(invoke)


def _list_recent_candidate_cases(resources: TeacherResources) -> CallableTool:
    @tool(name="list_recent_candidate_cases")
    def invoke(
        category: Annotated[
            str,
            ToolArg(
                "Nearby-case category from the Candidate outcome digest.",
                choices=(
                    "beneficial_activation",
                    "harmful_activation",
                    "neutral_activation",
                    "missed_target",
                    "false_positive",
                    "parse_failure",
                    "unattributed_improvement",
                    "unattributed_regression",
                ),
            ),
        ],
        page: Annotated[int, ToolArg("One-based page number.", minimum=1)] = 1,
        page_size: Annotated[
            int,
            ToolArg("Cases per page.", minimum=1, maximum=20),
        ] = 10,
    ) -> ToolResult:
        """List high-value nearby cases from the rejected Candidate."""

        store = _require_candidate_review(resources)
        digest = store.outcome_digest()
        nearby = digest.get("nearby_cases")
        nearby = nearby if isinstance(nearby, dict) else {}
        items = nearby.get(category)
        items = items if isinstance(items, list) else []
        start = (page - 1) * page_size
        return _json_result(
            "list_recent_candidate_cases",
            {
                "category": category,
                "page": page,
                "page_size": page_size,
                "total_items": len(items),
                "items": items[start : start + page_size],
            },
        )

    return CallableTool.from_callable(invoke)


def _get_recent_candidate_case(resources: TeacherResources) -> CallableTool:
    @tool(name="get_recent_candidate_case")
    def invoke(
        example_id: Annotated[str, ToolArg("Nearby Candidate example ID.")],
    ) -> ToolResult:
        """Read one paired case from the most recent rejected Candidate."""

        store = _require_candidate_review(resources)
        return _text_result(
            "get_recent_candidate_case",
            render_candidate_case(store, example_id),
        )

    return CallableTool.from_callable(invoke)


def _get_recent_candidate_trajectory(
    resources: TeacherResources,
) -> CallableTool:
    @tool(name="get_recent_candidate_trajectory")
    def invoke(
        example_id: Annotated[str, ToolArg("Nearby Candidate example ID.")],
        replicate_id: Annotated[str, ToolArg("Decisive replicate ID.")],
    ) -> ToolResult:
        """Read one compact paired trajectory from the rejected Candidate."""

        store = _require_candidate_review(resources)
        return _text_result(
            "get_recent_candidate_trajectory",
            render_paired_candidate_trajectory(
                store,
                example_id=example_id,
                replicate_id=replicate_id,
            ),
        )

    return CallableTool.from_callable(invoke)


def _get_recent_candidate_implementation(
    resources: TeacherResources,
) -> CallableTool:
    @tool(name="get_recent_candidate_implementation")
    def invoke() -> ToolResult:
        """Read the rejected solution summary and bounded Compiler risks."""

        store = _require_candidate_review(resources)
        return _json_result(
            "get_recent_candidate_implementation",
            store.implementation_view(),
        )

    return CallableTool.from_callable(invoke)


def _inspect_experience_detail(
    resources: TeacherResources,
) -> CallableTool:
    store = _require_experience_summary(resources)

    @tool(name="inspect_experience_detail")
    def invoke(
        detail_id: Annotated[
            int,
            ToolArg(
                "One numeric Detail ID from detail_directory. Each ID can be "
                "read once; every call counts toward the role's safety fuse.",
                minimum=1,
            ),
        ],
    ) -> ToolResult:
        """Read one authorized Detail projection that resolves a named gap."""

        return _text_result(
            "inspect_experience_detail",
            store.inspect(detail_id),
        )

    return CallableTool.from_callable(invoke)


def _require_evaluation(
    resources: TeacherResources,
) -> EvaluationEvidenceStore:
    if resources.evaluation is None:
        raise ValueError("Teacher template requires evaluation resources")
    return resources.evaluation


def _trajectory_view(
    store: EvaluationEvidenceStore,
    example_id: str,
    replicate_id: str,
) -> TeacherTrajectoryView:
    # Keep the store's access ledger and evidence budget authoritative even
    # though presentation is built from the immutable source record.
    store.get_trajectory(
        example_id=example_id,
        replicate_id=replicate_id,
        view="behavior",
    )
    return TeacherTrajectoryView(
        store.rollouts[example_id][replicate_id],
        case=store.cases.get(example_id),
        replicate_id=replicate_id,
    )


def _evaluation_records(store: EvaluationEvidenceStore):
    for by_replicate in store.rollouts.values():
        yield from by_replicate.values()


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


def _require_experience_summary(
    resources: TeacherResources,
) -> ExperienceDetailStore:
    if resources.experience_summary is None:
        raise ValueError("Teacher template requires experience resources")
    return resources.experience_summary


def _json_result(name: str, payload: Any) -> ToolResult:
    return ToolResult(
        name=name,
        content=json.dumps(payload, ensure_ascii=False),
    )


def _text_result(name: str, content: str) -> ToolResult:
    return ToolResult(name=name, content=content)
