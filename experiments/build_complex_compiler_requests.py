"""Build complex Compiler requests used by runtime optimization experiments."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = (
    PROJECT_ROOT
    / "runs"
    / "components"
    / "teacher"
    / "mechanism_compilation_validation_01"
    / "complex_optimization_study"
)
PARENT_TEMPLATE_ROOT = (
    PROJECT_ROOT / "harness_templates" / "student" / "baseline"
)


def main() -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    requests = {
        "post_tool_rewrite": _post_tool_rewrite(),
        "post_prompt_context": _post_prompt_context(),
        "hook_model_refinement": _hook_model_refinement(),
        "pre_final_semantic": _pre_final_semantic(),
    }
    for name, payload in requests.items():
        target = OUTPUT_ROOT / name / "compiler_request.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {target}")


def _request(
    mechanism: dict[str, Any],
    constraints: list[str],
) -> dict[str, Any]:
    return {
        "input": {
            "mechanism": mechanism,
            "implementation_constraints": constraints,
            "validation_feedback": [],
        },
        "resources": {
            "compiler": {
                "parent_template_root": str(PARENT_TEMPLATE_ROOT),
                "env_file": str(PROJECT_ROOT / ".env"),
            }
        },
    }


def _post_tool_rewrite() -> dict[str, Any]:
    return _request(
        {
            "goal": (
                "After at most two successful search calls, preserve the original "
                "ToolResult while appending one generic evidence-review instruction."
            ),
            "trigger_phase": "post_tool",
            "trigger_condition": (
                "At post_tool when both stage values are search objects and the "
                "rollout-local rewrite count is below two."
            ),
            "decision_inputs": [
                "stage.tool_call",
                "stage.tool_result",
                "extension result-rewrite count",
            ],
            "action": (
                "Replace the search ToolResult with an equivalent result whose "
                "content ends with one static evidence-review instruction."
            ),
            "behavioral_pseudocode": (
                "At post_tool, read the ToolCall, ToolResult, and rollout-local "
                "rewrite_count initially 0. If either object is not for search, "
                "or rewrite_count is already 2, return without changes. Otherwise "
                "create a new ToolResult with the same name and a copied metadata "
                "mapping. Preserve the original content exactly, append one static "
                "instruction asking the Student to identify the unresolved entity "
                "and relation before its next action, and add metadata recording "
                "that this Hook applied and the new activation number. Replace "
                "stage.tool_result with that object, then increment rewrite_count."
            ),
            "state_scope": (
                "One rollout-local integer rewrite_count with default 0 and maximum 2."
            ),
            "fallback": (
                "For non-search calls, mismatched call/result names, or exhausted "
                "budget, leave the ToolResult unchanged."
            ),
            "expected_behavior": (
                "The first two search observations retain their original evidence "
                "and metadata while carrying one auditable generic instruction; "
                "later observations are unchanged."
            ),
            "evidence_refs": ["complex_probe/post_tool_rewrite"],
            "activation_budget": 2,
            "required_capabilities": [
                "ToolCall",
                "ToolResult",
                "StateRef",
                "HookStateView.get",
                "HookStateView.set",
                "stage.tool_call",
                "stage.tool_result",
            ],
            "prohibited_behaviors": [
                "Do not parse or delete retrieved passages.",
                "Do not mutate ToolResult metadata in place.",
                "Do not inject case-specific entities, queries, or answers.",
                "Do not activate more than twice per rollout.",
            ],
            "observability": [
                "rewrite_count transition",
                "stage.tool_result before and after values",
                "metadata activation number",
            ],
            "known_limits": [
                "The static instruction cannot determine whether evidence is sufficient."
            ],
        },
        [
            "Use one integer StateRef under extension.<hook_id> with default 0.",
            "Declare stage.tool_result writable only at post_tool.",
            "Validate ToolCall and ToolResult types explicitly.",
            "Copy metadata before adding the Hook audit entry.",
            "Preserve the original ToolResult name and content before the suffix.",
            "Reject unsupported factory configuration and avoid dummy del statements.",
            "Use no reflection, model call, case fact, or undocumented runtime state.",
        ],
    )


def _post_prompt_context() -> dict[str, Any]:
    return _request(
        {
            "goal": (
                "Append one generic evidence-planning user message to the first "
                "model input while preserving every existing message."
            ),
            "trigger_phase": "post_prompt",
            "trigger_condition": (
                "The Hook enters post_prompt for the first time in a rollout."
            ),
            "decision_inputs": [
                "stage.model_input",
                "extension context-injection consumed flag",
            ],
            "action": (
                "Append one ChatMessage to the existing ModelInput and replace "
                "stage.model_input once."
            ),
            "behavioral_pseudocode": (
                "At post_prompt, read rollout-local consumed initially false. "
                "If consumed is true, return without changes. Read stage.model_input "
                "and require a ModelInput. Construct a new ordered message list "
                "containing every existing message exactly once, followed by one "
                "user ChatMessage that asks the Student to identify missing evidence "
                "before choosing between search and a final answer. Build a new "
                "ModelInput from that list, replace stage.model_input, then set "
                "consumed to true."
            ),
            "state_scope": (
                "One rollout-local boolean consumed flag reset for each rollout."
            ),
            "fallback": (
                "After the first injection, preserve later ModelInput values without changes."
            ),
            "expected_behavior": (
                "The first model request contains all original messages in the "
                "same order plus exactly one generic user instruction."
            ),
            "evidence_refs": ["complex_probe/post_prompt_context"],
            "activation_budget": 1,
            "required_capabilities": [
                "ChatMessage",
                "ModelInput",
                "ModelInput.from_messages",
                "StateRef",
                "HookStateView.get",
                "HookStateView.set",
                "stage.model_input",
            ],
            "prohibited_behaviors": [
                "Do not replace, reorder, or duplicate existing messages.",
                "Do not replace the system instruction.",
                "Do not inject case-specific entities, queries, or answers.",
                "Do not activate more than once per rollout.",
            ],
            "observability": [
                "consumed flag transition",
                "stage.model_input before and after values",
                "appended message role and content",
            ],
            "known_limits": [
                "The Student may ignore the appended planning instruction."
            ],
        },
        [
            "Use ModelInput.from_messages and ChatMessage from the public Hook API.",
            "Preserve the exact existing ModelInput.messages order.",
            "Append exactly one role=user message and no system message.",
            "Use one boolean StateRef and declare stage.model_input writable.",
            "Reject unsupported factory configuration and avoid dummy del statements.",
            "Use no reflection, model call, case fact, or undocumented runtime state.",
        ],
    )


def _hook_model_refinement() -> dict[str, Any]:
    return _request(
        {
            "goal": (
                "Use one bounded student-profile Hook model call to condense the "
                "first search result, with a deterministic pass-through fallback."
            ),
            "trigger_phase": "post_tool",
            "trigger_condition": (
                "At post_tool for the first matching search ToolCall and ToolResult "
                "in the rollout."
            ),
            "decision_inputs": [
                "stage.tool_call",
                "stage.tool_result",
                "extension refinement-attempted flag",
            ],
            "action": (
                "Ask the configured student Hook model for a JSON evidence summary "
                "and replace the search ToolResult only when that summary is valid."
            ),
            "behavioral_pseudocode": (
                "At post_tool, read ToolCall, ToolResult, and rollout-local attempted "
                "initially false. If attempted is true, or either object is not for "
                "search, return without changes. Set attempted to true. Read the "
                "search query as a non-empty string; otherwise keep the original "
                "result. Build a HookModelRequest for profile student from a local "
                "system prompt and a user message containing the query plus a "
                "bounded prefix of the result content. Make exactly one Hook model "
                "call. Parse the response as a JSON object with non-empty string "
                "field summary. If parsing or field validation fails, keep the "
                "original ToolResult. On success, copy metadata, add an audit entry, "
                "and replace stage.tool_result with a ToolResult of the same name "
                "whose content is the summary."
            ),
            "state_scope": (
                "One rollout-local boolean attempted flag; one model call at most."
            ),
            "fallback": (
                "For a missing query, invalid JSON, or missing/empty summary, preserve "
                "the original ToolResult after consuming the one attempt."
            ),
            "expected_behavior": (
                "A valid Hook-model JSON summary replaces the first search result "
                "and is traced; malformed model output leaves the original result "
                "unchanged and does not retry."
            ),
            "evidence_refs": ["complex_probe/hook_model_refinement"],
            "activation_budget": 1,
            "required_capabilities": [
                "BaseHook.model_profiles",
                "BaseHook.max_model_calls_per_invocation",
                "ChatMessage",
                "ModelInput",
                "ModelInput.from_messages",
                "HookContext.call_model",
                "HookModelRequest",
                "HookModelResponse",
                "HookModelResponse.json_object",
                "ToolCall",
                "ToolResult",
                "StateRef",
                "HookStateView.get",
                "HookStateView.set",
                "stage.tool_call",
                "stage.tool_result",
            ],
            "prohibited_behaviors": [
                "Do not create an HTTP client or nested AgentLoop.",
                "Do not call a Teacher profile.",
                "Do not make more than one Hook model call.",
                "Do not include case-specific entities, queries, or answers in the prompt.",
                "Do not discard the original result when model output is invalid.",
            ],
            "observability": [
                "attempted flag transition",
                "hook_model_output or parsing failure",
                "stage.tool_result before and after values",
                "metadata refinement audit entry",
            ],
            "known_limits": [
                "A syntactically valid summary may still omit useful evidence.",
                "The result prefix limit may exclude late passages.",
            ],
        },
        [
            "Create a local UTF-8 prompt file under the new extension directory.",
            "Support config keys template and max_result_chars; reject unknown keys.",
            "Use Path and explicit UTF-8 reading for the local prompt.",
            "Allow only model profile student and one call per invocation.",
            "Catch only JSON/field validation failures for deterministic pass-through.",
            "Copy ToolResult metadata and record successful refinement.",
            "Declare stage.tool_result writable and use one boolean StateRef.",
            "Use no reflection, Teacher call, case fact, or undocumented runtime state.",
        ],
    )


def _pre_final_semantic() -> dict[str, Any]:
    return _request(
        {
            "goal": (
                "Give the Student one additional chance to gather direct evidence "
                "before accepting its first proposed final answer."
            ),
            "trigger_phase": "pre_final",
            "trigger_condition": (
                "The Student proposes its first final answer in the rollout."
            ),
            "decision_inputs": [
                "Student final-answer candidate",
                "rollout-local deferral-used flag",
            ],
            "action": (
                "Defer the first final answer with a generic evidence-planning "
                "instruction and allow the next final answer."
            ),
            "behavioral_pseudocode": (
                "Keep one rollout-local boolean deferred_once initially false. "
                "At pre_final, if deferred_once is true, preserve the accepted "
                "candidate and stop. Otherwise set deferred_once to true and "
                "defer with a static instruction. The instruction delegates to "
                "the Student: identify the unresolved relation from its visible "
                "context, perform one evidence-oriented search if needed, and "
                "answer only from direct evidence. Never include a case entity, "
                "answer, or ready-made query."
            ),
            "state_scope": (
                "One rollout-local boolean deferred_once reset between rollouts."
            ),
            "fallback": (
                "After one deferral, leave every later final decision unchanged."
            ),
            "expected_behavior": (
                "The first candidate is deferred with generic feedback and the "
                "second candidate can complete normally."
            ),
            "evidence_refs": ["complex_probe/pre_final_semantic"],
            "activation_budget": 1,
            "required_capabilities": [
                "Student can follow a generic continuation instruction",
                "Student can use its configured search tool",
                "Student can inspect question and visible evidence",
                "Student can continue after a deferred final answer",
            ],
            "prohibited_behaviors": [
                "Do not inject a golden answer or case-specific entity.",
                "Do not formulate the Student's concrete search query.",
                "Do not call a model or tool from the Hook.",
                "Do not defer more than once.",
            ],
            "observability": [
                "deferred_once state transition",
                "stage.final_decision action",
                "deferred feedback",
            ],
            "known_limits": [
                "The Student may ignore the feedback or choose the wrong relation."
            ],
        },
        [
            "Use one boolean StateRef under extension.<hook_id>.",
            "Declare stage.final_decision writable only at pre_final.",
            "Use FinalDecision.defer for the first candidate.",
            "Preserve later accepted decisions with an early return.",
            "Reject unsupported factory configuration and avoid dummy statements.",
            "Use no reflection, model call, case fact, or undocumented runtime state.",
        ],
    )


if __name__ == "__main__":
    main()
