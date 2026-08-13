"""Shadow Teacher tools backed by the production resource stores."""

from __future__ import annotations

from typing import Annotated, Any, Callable

from search_harness.evolution.research.resources.base import (
    CandidateComparisonStore,
    EvaluationEvidenceStore,
    TeacherResources,
    TrialEvidenceStore,
)
from search_harness.evolution.research.tools import build_builtin_tool
from search_harness.framework import ToolResult
from search_harness.framework.harness import ComponentFactoryContext
from search_harness.framework.tools import CallableTool, ToolArg, tool

from .views import (
    ShadowTrajectoryView,
    render_evaluation_case,
    render_distillation_trial_detail,
    render_student_behavior_interface,
    render_student_capability_view,
)
from .compiler import render_shadow_hook_api_result
from .candidate import (
    render_candidate_case,
    render_candidate_changes,
    render_candidate_harness_diff,
    render_candidate_trajectory_text,
    render_paired_candidate_trajectory,
)


def build_shadow_tool(
    config: dict[str, Any],
    context: ComponentFactoryContext,
) -> CallableTool:
    """Build one shadow tool or delegate unchanged tools to production."""

    if set(config) != {"kind"}:
        raise ValueError("shadow Teacher tool config must contain only kind")
    kind = config.get("kind")
    if not isinstance(kind, str):
        raise TypeError("shadow Teacher tool kind must be a string")
    resources = context.runtime_context
    if not isinstance(resources, TeacherResources):
        raise TypeError("shadow Teacher tools require TeacherResources")
    factories: dict[str, Callable[[TeacherResources], CallableTool]] = {
        "get_evaluation_case": _get_evaluation_case,
        "get_student_trajectory": _get_student_trajectory,
        "get_trajectory_change": _get_trajectory_change,
        "get_trajectory_block": _get_trajectory_block,
        "search_hidden_trajectory_blocks": _search_hidden_trajectory_blocks,
        "get_student_capability_view": _get_student_capability_view,
        "get_student_behavior_interface": _get_student_behavior_interface,
        "get_distillation_trial_detail": _get_distillation_trial_detail,
        "shadow_query_hook_api": _shadow_query_hook_api,
        "shadow_list_candidate_changes": _shadow_list_candidate_changes,
        "shadow_get_candidate_case": _shadow_get_candidate_case,
        "shadow_get_paired_student_trajectory": (
            _shadow_get_paired_student_trajectory
        ),
        "shadow_get_candidate_harness_diff": _shadow_get_candidate_harness_diff,
        "shadow_get_candidate_trajectory_text": (
            _shadow_get_candidate_trajectory_text
        ),
    }
    factory = factories.get(kind)
    if factory is not None:
        return factory(resources)
    return build_builtin_tool({"kind": kind}, context)


def _get_evaluation_case(resources: TeacherResources) -> CallableTool:
    store = _require_evaluation(resources)

    @tool(name="get_evaluation_case")
    def invoke(
        example_id: Annotated[
            str,
            ToolArg("Example ID returned by list_evaluation_cases."),
        ],
    ) -> ToolResult:
        """Read one compact Evaluation Case and its Replicate facts."""

        return _result(
            "get_evaluation_case",
            render_evaluation_case(store.get_case(example_id)),
        )

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

        view = _trajectory(store, example_id, replicate_id)
        return _result("get_student_trajectory", view.render())

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

        view = _trajectory(store, example_id, replicate_id)
        return _result(
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

        view = _trajectory(store, example_id, replicate_id)
        return _result(
            "get_trajectory_change",
            view.render_change(change_id),
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

        view = _trajectory(store, example_id, replicate_id)
        return _result(
            "search_hidden_trajectory_blocks",
            view.search_runtime_blocks(query, max_matches=max_matches),
        )

    return CallableTool.from_callable(invoke)


def _get_student_capability_view(
    resources: TeacherResources,
) -> CallableTool:
    store = _require_evaluation(resources)

    @tool(name="get_student_capability_view")
    def invoke() -> ToolResult:
        """Read Student-observable registered capabilities, not source code."""

        return _result(
            "get_student_capability_view",
            render_student_capability_view(
                manifest=store.harness_manifest or {},
                records=_records(store),
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
        """Read the exact Student-visible prompt and declared behavior surface."""

        reference = f"{example_id}/{replicate_id}"
        reads = set(store.role_session_state().get("trajectory_reads", []))
        if reference not in reads:
            raise ValueError(
                "inspect this trajectory through get_student_trajectory "
                "before reading its Student Behavior Interface"
            )
        record = store.rollouts[example_id][replicate_id]
        return _result(
            "get_student_behavior_interface",
            render_student_behavior_interface(
                manifest=store.harness_manifest or {},
                record=record,
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
            ToolArg("Trial reference listed in the Distillation Evidence Dossier."),
        ],
    ) -> ToolResult:
        """Read one role-specific event catalog only to resolve an ambiguity."""

        return _result(
            "get_distillation_trial_detail",
            render_distillation_trial_detail(store.get_trial(trial_ref)),
        )

    return CallableTool.from_callable(invoke)


def _shadow_query_hook_api(resources: TeacherResources) -> CallableTool:
    store = _require_compiler(resources)

    @tool(name="query_hook_api")
    def invoke(
        symbol: Annotated[
            str,
            ToolArg(
                "A Runtime Input Topic ID, exact public symbol, or short search "
                "phrase. Use this only when the initial Authoring Packet does "
                "not settle the implementation detail."
            ),
        ],
    ) -> ToolResult:
        """Resolve one missing public API detail without repeating two views."""

        return _result(
            "query_hook_api",
            render_shadow_hook_api_result(store.query_hook_api(symbol)),
        )

    return CallableTool.from_callable(invoke)


def _shadow_list_candidate_changes(resources: TeacherResources) -> CallableTool:
    store = _require_candidate(resources)

    @tool(name="list_candidate_changes")
    def invoke(
        page: Annotated[int, ToolArg("One-based page number.", minimum=1)] = 1,
        page_size: Annotated[
            int,
            ToolArg("Cases per page.", minimum=1, maximum=100),
        ] = 100,
        change: Annotated[
            str,
            ToolArg(
                "Paired outcome filter. The default lists all improved and "
                "regressed cases before unchanged drill-down.",
                choices=("any", "improved", "regressed", "unchanged"),
            ),
        ] = "any",
    ) -> ToolResult:
        """List a changed-first incumbent/candidate outcome directory."""

        return _result(
            "list_candidate_changes",
            render_candidate_changes(
                store,
                page=page,
                page_size=page_size,
                change=change,
            ),
        )

    return CallableTool.from_callable(invoke)


def _shadow_get_candidate_case(resources: TeacherResources) -> CallableTool:
    store = _require_candidate(resources)

    @tool(name="get_candidate_case")
    def invoke(
        example_id: Annotated[
            str,
            ToolArg("Example ID returned by list_candidate_changes."),
        ],
    ) -> ToolResult:
        """Read a paired Evaluation Case with replicate-level deltas."""

        return _result(
            "get_candidate_case",
            render_candidate_case(store, example_id),
        )

    return CallableTool.from_callable(invoke)


def _shadow_get_paired_student_trajectory(
    resources: TeacherResources,
) -> CallableTool:
    store = _require_candidate(resources)

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

        return _result(
            "get_paired_student_trajectory",
            render_paired_candidate_trajectory(
                store,
                example_id=example_id,
                replicate_id=replicate_id,
            ),
        )

    return CallableTool.from_callable(invoke)


def _shadow_get_candidate_harness_diff(
    resources: TeacherResources,
) -> CallableTool:
    store = _require_candidate(resources)

    @tool(name="get_candidate_harness_diff")
    def invoke(
        path: Annotated[
            str,
            ToolArg(
                "Exact changed path, or an empty string for a complete small diff "
                "or a large-diff directory."
            ),
        ] = "",
    ) -> ToolResult:
        """Read the Candidate Harness diff with size-aware path drill-down."""

        return _result(
            "get_candidate_harness_diff",
            render_candidate_harness_diff(store, path=path or None),
        )

    return CallableTool.from_callable(invoke)


def _shadow_get_candidate_trajectory_text(
    resources: TeacherResources,
) -> CallableTool:
    store = _require_candidate(resources)

    @tool(name="get_candidate_trajectory_text")
    def invoke(
        example_id: Annotated[str, ToolArg("Trajectory example ID.")],
        replicate_id: Annotated[str, ToolArg("Trajectory replicate ID.")],
        side: Annotated[
            str,
            ToolArg("Paired trajectory side.", choices=("incumbent", "candidate")),
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
        offset: Annotated[int, ToolArg("Zero-based character offset.", minimum=0)] = 0,
        max_characters: Annotated[
            int,
            ToolArg("Maximum exact characters.", minimum=1, maximum=12000),
        ] = 4000,
    ) -> ToolResult:
        """Read one exact long text field only when the default preview is insufficient."""

        return _result(
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


def _trajectory(
    store: EvaluationEvidenceStore,
    example_id: str,
    replicate_id: str,
) -> ShadowTrajectoryView:
    _mark_read(store, example_id, replicate_id)
    return ShadowTrajectoryView(
        store.rollouts[example_id][replicate_id],
        case=store.cases.get(example_id),
        replicate_id=replicate_id,
    )


def _mark_read(
    store: EvaluationEvidenceStore,
    example_id: str,
    replicate_id: str,
) -> None:
    store.get_trajectory(
        example_id=example_id,
        replicate_id=replicate_id,
        view="behavior",
    )


def _records(store: EvaluationEvidenceStore):
    for by_replicate in store.rollouts.values():
        yield from by_replicate.values()


def _require_evaluation(resources: TeacherResources) -> EvaluationEvidenceStore:
    if resources.evaluation is None:
        raise ValueError("evaluation resources are unavailable")
    return resources.evaluation


def _require_trials(resources: TeacherResources) -> TrialEvidenceStore:
    if resources.trials is None:
        raise ValueError("trial resources are unavailable")
    return resources.trials


def _require_compiler(resources: TeacherResources):
    if resources.compiler is None:
        raise ValueError("compiler resources are unavailable")
    return resources.compiler


def _require_candidate(resources: TeacherResources) -> CandidateComparisonStore:
    if resources.candidate_review is None:
        raise ValueError("candidate-review resources are unavailable")
    return resources.candidate_review


def _result(name: str, content: str) -> ToolResult:
    return ToolResult(
        name=name,
        content=content,
        metadata={"view_experiment": "teacher_query_views_v1"},
    )
