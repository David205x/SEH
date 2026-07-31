"""Source-derived intervention capabilities exposed to Teacher researchers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, get_args

from ._intervention.prefix import (
    recoverable_prefix_phases,
)
from search_harness.core import HookPhase
from search_harness.core.hooks import STAGE_KEYS_BY_PHASE

from .contracts import InterventionActionName
from .hook_api import query_hook_api


_ACTION_SPECS: dict[str, dict[str, Any]] = {
    "append_user_message": {
        "effect": "Append one user-role instruction before branch continuation.",
        "compatible_phases": "all_recoverable",
        "persistence": "branch_prefix",
    },
    "append_system_message": {
        "effect": "Append one system-role instruction before branch continuation.",
        "compatible_phases": "all_recoverable",
        "persistence": "branch_prefix",
    },
    "replace_system_instruction": {
        "effect": (
            "Replace the system instruction while preserving non-system "
            "messages and tool evidence."
        ),
        "compatible_phases": "all_recoverable",
        "persistence": "branch",
    },
    "defer_final_answer": {
        "effect": (
            "Reject the active final candidate once, append feedback, and "
            "request another Actor generation."
        ),
        "compatible_phases": (HookPhase.PRE_FINAL,),
        "persistence": "branch_prefix",
    },
    "no_op": {
        "effect": "Continue the branch without changing Actor context.",
        "compatible_phases": "all_recoverable",
        "persistence": "none",
    },
}


def intervention_capabilities() -> dict[str, Any]:
    """Build the stable trial capability catalog from runtime definitions."""

    recoverable = recoverable_prefix_phases()
    action_names = set(get_args(InterventionActionName))
    if action_names != set(_ACTION_SPECS):
        raise RuntimeError(
            "intervention action capability catalog differs from "
            "InterventionActionName"
        )
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
    for name in sorted(action_names):
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
            "teacher._intervention.prefix.recoverable_prefix_phases",
            "teacher.contracts.InterventionActionName",
            "teacher.hook_api.query_hook_api",
        ],
        "execution": {
            "one_action_per_activation": True,
            "multiple_phases_per_trial": True,
            "same_worker_transcript_across_activations": True,
            "maximum_phase_directives": 4,
            "unique_phase_directives": True,
            "action_application": "current_hook_activation",
            "actor_continues_from_selected_prefix": True,
            "teacher_loop_inside_actor": False,
        },
        "observability": {
            "selected_prefix": [
                "selector.step",
                "selector.phase",
                "question",
                "model_input.messages",
                "active_stage",
            ],
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
