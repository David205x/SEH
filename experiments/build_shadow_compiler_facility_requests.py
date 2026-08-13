"""Build current-protocol Compiler requests for uncovered Hook facilities."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


_ROOT = Path(__file__).resolve().parents[1]
_OUTPUT = (
    _ROOT
    / "runs"
    / "components"
    / "teacher"
    / "compiler_authoring_ab_20260813_facilities"
    / "requests"
)
_PARENT = _ROOT / "harness_templates" / "student" / "baseline"


def main() -> None:
    requests = {
        "pre_tool_argument_rewrite": _pre_tool_argument_rewrite(),
        "multi_phase_state_handoff": _multi_phase_state_handoff(),
    }
    for name, value in requests.items():
        path = _OUTPUT / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(path)


def _request(mechanism: dict[str, Any], constraints: list[str]) -> dict[str, Any]:
    return {
        "input": {
            "mechanism": mechanism,
            "implementation_constraints": constraints,
            "validation_feedback": [],
        },
        "resources": {
            "compiler": {
                "parent_template_root": str(_PARENT.resolve()),
                "env_file": str((_ROOT / ".env").resolve()),
            }
        },
    }


def _contract(predicate: str, positive: str, negative: str) -> dict[str, Any]:
    return {
        "predicate": predicate,
        "positive_rule": positive,
        "negative_rule": negative,
        "uncertain_rule": (
            "Required runtime values have an unexpected type, so neither other "
            "label is justified."
        ),
        "output_labels": ["positive", "negative", "uncertain"],
        "evidence_coverage": {
            "positive": ["constructed facility positive boundary"],
            "negative": ["constructed facility negative boundary"],
            "uncertain": ["constructed invalid-type boundary"],
        },
    }


def _pre_tool_argument_rewrite() -> dict[str, Any]:
    return _request(
        {
            "goal": (
                "Before the first search call only, normalize surrounding "
                "whitespace in its query while preserving its remaining arguments."
            ),
            "phase_rules": [
                {
                    "phase": "pre_tool",
                    "guards": ["stage.tool_call is a search ToolCall"],
                    "decision_contract": _contract(
                        "The search query is a string with leading or trailing whitespace.",
                        "query.strip() differs from query and produces a non-empty string.",
                        "The query is already trimmed or the tool is not search.",
                    ),
                    "decision_inputs": ["stage.tool_call", "normalized_once"],
                    "runtime_inputs": ["tool", "persistent_state"],
                    "decision_evaluator": "deterministic",
                    "action": (
                        "Replace stage.tool_call with the same tool name and a copied "
                        "arguments mapping whose query value is stripped."
                    ),
                    "fallback": {
                        "negative": "Leave stage.tool_call unchanged.",
                        "uncertain": "Leave stage.tool_call unchanged.",
                        "budget_exhausted": "Leave every later call unchanged.",
                    },
                    "activation_budget": 1,
                }
            ],
            "behavioral_pseudocode": (
                "At pre_tool, return if normalized_once. Require a search ToolCall "
                "with a string query. Compute stripped query. If it is empty or "
                "unchanged, return. Copy arguments, replace only query, replace "
                "stage.tool_call, and set normalized_once true."
            ),
            "state_scope": "One rollout-local boolean normalized_once.",
            "expected_behavior": (
                "Only the first whitespace-bearing search query is normalized; "
                "other arguments, calls and later events are unchanged."
            ),
            "evidence_refs": ["constructed/pre_tool_argument_rewrite"],
            "required_capabilities": ["ToolCall", "StateRef", "stage.tool_call"],
            "prohibited_behaviors": [
                "Do not change the semantic query text beyond surrounding whitespace.",
                "Do not mutate arguments in place.",
                "Do not affect non-search tools.",
            ],
            "observability": ["stage.tool_call before and after", "normalized_once"],
            "known_limits": ["This facility probe is not expected to improve retrieval."],
        },
        [
            "Use only deterministic logic and public Hook API types.",
            "Declare stage.tool_call writable only at pre_tool.",
            "Copy the arguments mapping before replacing query.",
            "Reject non-empty factory configuration.",
        ],
    )


def _multi_phase_state_handoff() -> dict[str, Any]:
    return _request(
        {
            "goal": (
                "Remember whether any completed search returned an empty result and, "
                "if so, defer the first later final answer once with generic feedback."
            ),
            "phase_rules": [
                {
                    "phase": "post_tool",
                    "guards": ["stage.tool_result belongs to a search ToolCall"],
                    "decision_contract": _contract(
                        "The completed search ToolResult content is empty after stripping.",
                        "ToolResult.content is a string and not content.strip().",
                        "ToolResult.content contains at least one non-whitespace character.",
                    ),
                    "decision_inputs": ["stage.tool_call", "stage.tool_result"],
                    "runtime_inputs": ["tool", "persistent_state"],
                    "decision_evaluator": "deterministic",
                    "action": "Set rollout-local saw_empty_search to true; do not alter the result.",
                    "fallback": {
                        "negative": "Leave state and ToolResult unchanged.",
                        "uncertain": "Leave state and ToolResult unchanged.",
                        "budget_exhausted": "Keep existing state unchanged.",
                    },
                    "activation_budget": 1,
                },
                {
                    "phase": "pre_final",
                    "guards": ["saw_empty_search is true", "deferred_once is false"],
                    "decision_contract": _contract(
                        "An empty search was observed and no final answer has yet been deferred.",
                        "saw_empty_search is true and deferred_once is false.",
                        "No empty search was observed or deferral was already consumed.",
                    ),
                    "decision_inputs": ["stage.final_decision", "saw_empty_search", "deferred_once"],
                    "runtime_inputs": ["final_decision", "persistent_state"],
                    "decision_evaluator": "deterministic",
                    "action": (
                        "Replace stage.final_decision with FinalDecision.defer carrying "
                        "generic feedback to gather direct evidence, then set deferred_once true."
                    ),
                    "fallback": {
                        "negative": "Preserve the current final decision.",
                        "uncertain": "Preserve the current final decision.",
                        "budget_exhausted": "Preserve all later final decisions.",
                    },
                    "activation_budget": 1,
                },
            ],
            "behavioral_pseudocode": (
                "Declare two rollout-local booleans. POST_TOOL only records an empty "
                "search result. PRE_FINAL reads that state; when true and not already "
                "consumed, defer once and mark consumed. Every other path is a no-op."
            ),
            "state_scope": (
                "Two rollout-local booleans saw_empty_search and deferred_once shared "
                "by the extension across its two phases."
            ),
            "expected_behavior": (
                "A non-empty search never causes deferral. An empty search causes "
                "exactly one later pre_final deferral, after which finalization proceeds."
            ),
            "evidence_refs": ["constructed/multi_phase_state_handoff"],
            "required_capabilities": [
                "ToolCall",
                "ToolResult",
                "FinalDecision.defer",
                "StateRef",
                "stage.final_decision",
            ],
            "prohibited_behaviors": [
                "Do not alter ToolResult content.",
                "Do not defer without a prior empty search.",
                "Do not defer more than once.",
                "Do not call a model.",
            ],
            "observability": [
                "saw_empty_search transition",
                "deferred_once transition",
                "stage.final_decision action",
            ],
            "known_limits": ["Whitespace-only content is treated as empty."],
        },
        [
            "Implement both phase rules in one Hook with shared declared StateRefs.",
            "Declare only stage.final_decision writable; POST_TOOL performs a state-only action.",
            "Use deterministic type checks and FinalDecision.defer.",
            "Reject non-empty factory configuration and do not call a model.",
        ],
    )


if __name__ == "__main__":
    main()
