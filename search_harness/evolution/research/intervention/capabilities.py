"""Source-derived intervention capabilities exposed to Teacher researchers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .prefix import (
    recoverable_prefix_phases,
)
from search_harness.framework import HookPhase
from search_harness.framework.harness import STAGE_KEYS_BY_PHASE

from ..mechanism.hook_api import query_hook_api


_ACTION_SPECS: dict[str, dict[str, Any]] = {
    "apply_context_patch": {
        "effect": (
            "Atomically insert, replace or delete numbered Student-visible "
            "context blocks while preserving program-maintained metadata."
        ),
        "compatible_phases": (HookPhase.POST_PROMPT, HookPhase.POST_TOOL),
        "persistence": "next_generation",
    },
    "apply_active_stage_patch": {
        "effect": (
            "Replace only the editable semantic fields of the active raw model "
            "output, parsed action, Tool Call, or Tool Result while preserving "
            "program-maintained metadata. Raw output, parsed action, and Tool "
            "Call edits require a live branch activation after an earlier "
            "recoverable prefix; a source-boundary post_tool result remains "
            "directly editable."
        ),
        "compatible_phases": (
            HookPhase.POST_MODEL,
            HookPhase.POST_PARSE,
            HookPhase.PRE_TOOL,
            HookPhase.POST_TOOL,
        ),
        "persistence": "current_hook_transaction",
    },
    "defer_final_answer": {
        "effect": (
            "Reject the active final candidate once, append feedback, and "
            "request another Student generation."
        ),
        "compatible_phases": (HookPhase.PRE_FINAL,),
        "persistence": "branch_prefix",
    },
    "continue_without_change": {
        "effect": "Continue the branch without changing Student context.",
        "compatible_phases": "all_recoverable",
        "persistence": "none",
    },
    "update_trial_state": {
        "effect": (
            "Create or replace bounded JSON state visible to later Hook "
            "activations in the same Intervention Trial branch."
        ),
        "compatible_phases": "all_recoverable",
        "persistence": "trial_branch",
    },
}


def intervention_capabilities() -> dict[str, Any]:
    """Build the stable trial capability catalog from runtime definitions."""

    recoverable = recoverable_prefix_phases()
    phases = []
    for phase in recoverable:
        stage_keys = sorted(STAGE_KEYS_BY_PHASE[phase])
        phases.append(
            {
                "phase": phase,
                "stage": [
                    _stage_capability(state_key) for state_key in stage_keys
                ],
                "native_reasoning_visible": False,
            }
        )
    actions = []
    for name in sorted(_ACTION_SPECS):
        spec = deepcopy(_ACTION_SPECS[name])
        compatible = spec["compatible_phases"]
        if compatible == "all_recoverable":
            spec["compatible_phases"] = list(recoverable)
        else:
            spec["compatible_phases"] = list(compatible)
        actions.append({"name": name, **spec})
    return {
        "schema_version": 2,
        "source_contracts": [
            "core.hooks.HookPhase",
            "core.hooks.STAGE_KEYS_BY_PHASE",
            "evolution.research.intervention.prefix.recoverable_prefix_phases",
            "evolution.research.mechanism.hook_api.query_hook_api",
        ],
        "execution": {
            "one_action_per_activation": True,
            "multiple_phases_per_trial": True,
            "same_worker_transcript_across_activations": True,
            "maximum_phase_directives": 4,
            "unique_phase_directives": True,
            "action_application": "current_hook_activation",
            "student_continues_from_selected_prefix": True,
            "teacher_loop_inside_actor": False,
            "context_patch_is_atomic": True,
            "extended_tools_configurable": True,
            "trial_state_scope": "one_trial_branch",
            "trial_state_reset": "each_assignment",
            "source_boundary_stage_patch": (
                "post_tool_only; post_model, post_parse, and pre_tool require "
                "a preceding fork phase and a later live activation"
            ),
        },
        "observability": {
            "selected_prefix": [
                "selector.step",
                "selector.phase",
                "question",
                "editable_context.block_id",
                "editable_context.kind",
                "editable_context.role",
                "editable_context.summary",
            ],
            "full_block_content": "on_demand_by_numeric_block_id",
            "program_metadata": "hidden_and_preserved",
            "active_stage": (
                "phase-specific values listed under each phase.stage"
            ),
            "native_reasoning": "trace_only_not_hook_visible",
            "active_stage_projection": "on_demand_semantic_fields_only",
            "trial_state": "bounded_json_injected_at_each_activation",
            "inband_thinking": (
                "available through raw model text at post_model and "
                "ParsedOutput at post_parse"
            ),
        },
        "phases": phases,
        "actions": actions,
    }


def _stage_capability(state_key: str) -> dict[str, Any]:
    contract = query_hook_api(state_key)
    return {
        "key": state_key,
        "type": contract["type"],
        "stability": contract["stability"],
        "note": contract["note"],
    }
