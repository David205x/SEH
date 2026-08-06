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
