"""Evaluate complex Compiler candidates with deterministic semantic smoke tests."""

from __future__ import annotations

import argparse
import ast
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from search_harness.framework import (
    AgentState,
    ChatMessage,
    FinalDecision,
    FinalDecisionAction,
    HookModelRequest,
    HookModelResponse,
    HookPhase,
    HookPipeline,
    ModelInput,
    ToolCall,
    ToolResult,
)
from search_harness.framework import InMemoryTrajectoryRecorder
from search_harness.framework.harness import (
    BaseHook,
    assemble_harness_components,
)
from search_harness.evolution.versioning import CandidateWorkspace, HarnessSnapshot
from search_harness.evolution.versioning.validation import stage_files


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STUDY_ROOT = (
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
SCENARIOS = (
    "post_tool_rewrite",
    "post_prompt_context",
    "hook_model_refinement",
    "pre_final_semantic",
)


@dataclass
class StubHookModelBackend:
    """Return deterministic Hook-model content while recording requests."""

    raw_output: str
    requests: list[HookModelRequest] = field(default_factory=list)

    def generate(self, request: HookModelRequest) -> HookModelResponse:
        self.requests.append(request)
        return HookModelResponse(raw_output=self.raw_output)


def main() -> None:
    args = parse_args()
    records = []
    for condition in args.conditions:
        for scenario in SCENARIOS:
            for path in sorted((STUDY_ROOT / scenario / condition).glob("compiler_run_*.json")):
                records.append(_evaluate(path, scenario, condition))
    args.output_file.parent.mkdir(parents=True, exist_ok=True)
    args.output_file.write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    for record in records:
        print(
            f"{record['condition']}/{record['scenario']}/{record['run']}: "
            f"semantic={record['semantic_passed']} "
            f"quality={record['quality_score']}/{record['quality_total']} "
            f"tokens={record['total_tokens']}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--conditions", nargs="+", required=True)
    parser.add_argument(
        "--output-file",
        type=Path,
        default=STUDY_ROOT / "matrix_evaluation.json",
    )
    return parser.parse_args()


def _evaluate(path: Path, scenario: str, condition: str) -> dict[str, Any]:
    artifact = json.loads(path.read_text(encoding="utf-8"))
    candidate = artifact["resource_artifacts"]["compiler_candidate"]
    errors = []
    checks = {}
    if candidate is None:
        errors.append("Compiler did not submit a candidate")
        semantic_passed = False
        source = ""
    else:
        source = "\n".join(
            content
            for name, content in candidate["changed_files"].items()
            if name.endswith(".py") and isinstance(content, str)
        )
        try:
            _semantic_smoke(candidate["changed_files"], scenario)
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
        semantic_passed = not errors
        checks = _quality_checks(
            source=source,
            changed_files=candidate["changed_files"],
            scenario=scenario,
        )

    validations = []
    for call in artifact["tool_calls"]:
        if call["name"] not in {"validate_candidate", "finalize_candidate"}:
            continue
        try:
            validations.append(json.loads(call["content"]))
        except json.JSONDecodeError:
            continue
    first_validation_passed = bool(validations) and _validation_passed(
        validations[0]
    )
    return {
        "condition": condition,
        "scenario": scenario,
        "run": path.stem,
        "artifact": str(path.resolve()),
        "submitted": candidate is not None,
        "static_validation_passed": bool(
            candidate and candidate["validation"]["passed"]
        ),
        "first_validation_passed": first_validation_passed,
        "semantic_passed": semantic_passed,
        "semantic_errors": errors,
        "quality_checks": checks,
        "quality_score": sum(checks.values()),
        "quality_total": len(checks),
        "requests": artifact["usage"]["requests"],
        "total_tokens": artifact["usage"]["total_tokens"],
        "tool_calls": len(artifact["tool_calls"]),
        "python_lines": len(source.splitlines()),
    }


def _validation_passed(payload: dict[str, Any]) -> bool:
    if payload.get("status") == "repair_required":
        return False
    return bool(payload.get("passed", payload.get("validation_passed", False)))


def _semantic_smoke(
    changed_files: dict[str, str | None],
    scenario: str,
) -> None:
    parent = HarnessSnapshot.from_directory(
        PARENT_TEMPLATE_ROOT,
        version_id="parent",
    )
    workspace = CandidateWorkspace(parent)
    for path, content in changed_files.items():
        if content is None:
            workspace.delete(path)
        else:
            workspace.write_text(path, content)
    with stage_files(workspace.materialized_files()) as template_root:
        assembled = assemble_harness_components(
            template_root,
            env_file=PROJECT_ROOT / ".env",
        )
        hooks = _extension_hooks(assembled.extensions)
        if scenario == "post_tool_rewrite":
            _smoke_post_tool_rewrite(hooks)
        elif scenario == "post_prompt_context":
            _smoke_post_prompt_context(hooks)
        elif scenario == "hook_model_refinement":
            _smoke_hook_model_refinement(hooks)
        elif scenario == "pre_final_semantic":
            _smoke_pre_final_semantic(hooks)
        else:
            raise ValueError(f"unknown scenario: {scenario}")


def _extension_hooks(extension_bindings: tuple[Any, ...]) -> tuple[BaseHook, ...]:
    hooks: list[BaseHook] = []
    for binding in extension_bindings:
        for component in binding.components:
            if not isinstance(component, BaseHook):
                raise TypeError(
                    f"Extension '{binding.instance_id}' returned a non-Hook"
                )
            hooks.append(component)
    return tuple(hooks)


def _smoke_post_tool_rewrite(hooks: tuple[Any, ...]) -> None:
    pipeline = HookPipeline(hooks)
    state = AgentState(question="Complex probe", max_steps=8, step=1)
    store = pipeline.begin_run(state)
    original = ToolResult(
        name="search",
        content="ORIGINAL_EVIDENCE",
        metadata={"source": "probe"},
    )
    call = ToolCall(name="search", arguments={"query": "probe"})
    first = _run_phase(
        pipeline,
        HookPhase.POST_TOOL,
        state,
        store,
        {"tool_call": call, "tool_result": original},
    )["tool_result"]
    _require(first.name == original.name, "first rewrite changed result name")
    _require(first.content.startswith(original.content), "first rewrite lost evidence")
    _require(first.content != original.content, "first rewrite added no instruction")
    _require(first.metadata.get("source") == "probe", "first rewrite lost metadata")

    second = _run_phase(
        pipeline,
        HookPhase.POST_TOOL,
        state,
        store,
        {"tool_call": call, "tool_result": original},
    )["tool_result"]
    _require(second.content != original.content, "second rewrite did not activate")

    third = _run_phase(
        pipeline,
        HookPhase.POST_TOOL,
        state,
        store,
        {"tool_call": call, "tool_result": original},
    )["tool_result"]
    _require(third == original, "third rewrite exceeded activation budget")

    other = ToolResult(name="other", content="UNCHANGED", metadata={"k": "v"})
    other_call = ToolCall(name="other", arguments={})
    unchanged = _run_phase(
        pipeline,
        HookPhase.POST_TOOL,
        state,
        store,
        {"tool_call": other_call, "tool_result": other},
    )["tool_result"]
    _require(unchanged == other, "non-search result was modified")
    counts = [value for value in state.hook_state.values() if isinstance(value, int)]
    _require(counts == [2], f"unexpected rewrite state: {state.hook_state}")


def _smoke_post_prompt_context(hooks: tuple[Any, ...]) -> None:
    pipeline = HookPipeline(hooks)
    state = AgentState(question="Complex probe", max_steps=8, step=1)
    store = pipeline.begin_run(state)
    original = ModelInput.from_messages(
        [
            ChatMessage(role="system", content="SYSTEM"),
            ChatMessage(role="user", content="QUESTION"),
        ]
    )
    first = _run_phase(
        pipeline,
        HookPhase.POST_PROMPT,
        state,
        store,
        {"model_input": original},
    )["model_input"]
    _require(first.messages[:2] == original.messages, "original messages changed")
    _require(len(first.messages) == 3, "expected exactly one appended message")
    _require(first.messages[-1].role == "user", "appended message is not user")
    _require(first.messages[-1].content.strip(), "appended message is empty")

    later = ModelInput.from_messages(
        [ChatMessage(role="user", content="LATER")]
    )
    second = _run_phase(
        pipeline,
        HookPhase.POST_PROMPT,
        state,
        store,
        {"model_input": later},
    )["model_input"]
    _require(second == later, "context injection activated more than once")
    flags = [value for value in state.hook_state.values() if isinstance(value, bool)]
    _require(flags == [True], f"unexpected context state: {state.hook_state}")


def _smoke_hook_model_refinement(hooks: tuple[Any, ...]) -> None:
    valid_backend = StubHookModelBackend('{"summary": "CONDENSED_EVIDENCE"}')
    pipeline = HookPipeline(hooks, model_backend=valid_backend)
    state = AgentState(question="Complex probe", max_steps=8, step=1)
    store = pipeline.begin_run(state)
    call = ToolCall(name="search", arguments={"query": "probe query"})
    original = ToolResult(
        name="search",
        content="ORIGINAL_EVIDENCE",
        metadata={"source": "probe"},
    )
    first = _run_phase(
        pipeline,
        HookPhase.POST_TOOL,
        state,
        store,
        {"tool_call": call, "tool_result": original},
    )["tool_result"]
    _require(first.name == original.name, "model rewrite changed result name")
    _require(first.content == "CONDENSED_EVIDENCE", "valid summary not applied")
    _require(first.metadata.get("source") == "probe", "model rewrite lost metadata")
    _require(len(valid_backend.requests) == 1, "expected one Hook model call")
    _require(valid_backend.requests[0].profile == "student", "wrong model profile")

    second = _run_phase(
        pipeline,
        HookPhase.POST_TOOL,
        state,
        store,
        {"tool_call": call, "tool_result": original},
    )["tool_result"]
    _require(second == original, "Hook model activated more than once")
    _require(len(valid_backend.requests) == 1, "Hook model call budget exceeded")

    invalid_backend = StubHookModelBackend("not-json")
    fallback_pipeline = HookPipeline(hooks, model_backend=invalid_backend)
    fallback_state = AgentState(question="Complex probe", max_steps=8, step=1)
    fallback_store = fallback_pipeline.begin_run(fallback_state)
    fallback = _run_phase(
        fallback_pipeline,
        HookPhase.POST_TOOL,
        fallback_state,
        fallback_store,
        {"tool_call": call, "tool_result": original},
    )["tool_result"]
    _require(fallback == original, "invalid model output changed result")
    flags = [
        value
        for value in fallback_state.hook_state.values()
        if isinstance(value, bool)
    ]
    _require(flags == [True], "invalid output did not consume attempt")


def _smoke_pre_final_semantic(hooks: tuple[Any, ...]) -> None:
    pipeline = HookPipeline(hooks)
    state = AgentState(question="Complex probe", max_steps=8, step=1)
    store = pipeline.begin_run(state)
    first = _run_phase(
        pipeline,
        HookPhase.PRE_FINAL,
        state,
        store,
        {"final_decision": FinalDecision.accept("first candidate")},
    )["final_decision"]
    _require(
        first.action is FinalDecisionAction.DEFER,
        "first final answer was not deferred",
    )
    _require(first.feedback is not None, "deferral feedback is missing")
    _require("first candidate" not in first.feedback, "feedback copied answer")

    second_candidate = FinalDecision.accept("second candidate")
    second = _run_phase(
        pipeline,
        HookPhase.PRE_FINAL,
        state,
        store,
        {"final_decision": second_candidate},
    )["final_decision"]
    _require(second == second_candidate, "second final answer was modified")
    flags = [
        value
        for value in state.hook_state.values()
        if isinstance(value, bool)
    ]
    _require(flags == [True], f"unexpected deferral state: {state.hook_state}")


def _run_phase(
    pipeline: HookPipeline,
    phase: str,
    state: AgentState,
    store: Any,
    stage_values: dict[str, Any],
) -> dict[str, Any]:
    return pipeline.run_phase(
        phase,
        state=state,
        store=store,
        trajectory=InMemoryTrajectoryRecorder(),
        stage_values=stage_values,
    )


def _quality_checks(
    *,
    source: str,
    changed_files: dict[str, str | None],
    scenario: str,
) -> dict[str, bool]:
    tree = ast.parse(source)
    checks = {
        "uses_state_ref": "StateRef(" in source,
        "rejects_unknown_config": (
            "set(config)" in source
            or "if config" in source
            or "unknown" in source.casefold()
            or "unsupported config" in source.casefold()
        ),
        "no_dummy_del": not any(isinstance(node, ast.Delete) for node in ast.walk(tree)),
        "no_reflection": not any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"getattr", "hasattr", "setattr", "delattr"}
            for node in ast.walk(tree)
        ),
    }
    if scenario == "post_tool_rewrite":
        checks.update(
            {
                "checks_tool_types": (
                    "isinstance" in source
                    and "ToolCall" in source
                    and "ToolResult" in source
                ),
                "copies_metadata": "dict(" in source and ".metadata" in source,
                "uses_no_model": "call_model(" not in source,
            }
        )
    elif scenario == "post_prompt_context":
        checks.update(
            {
                "uses_model_input": "ModelInput.from_messages" in source,
                "uses_user_message": (
                    "ChatMessage(" in source
                    and ("role=\"user\"" in source or "role='user'" in source)
                ),
                "preserves_messages": (
                    ".messages" in source
                    and ("list(" in source or "[*" in source)
                ),
            }
        )
    elif scenario == "hook_model_refinement":
        prompt_files = [
            name
            for name, content in changed_files.items()
            if name != "harness.json"
            and not name.endswith(".py")
            and isinstance(content, str)
        ]
        checks.update(
            {
                "checks_tool_types": (
                    "isinstance" in source
                    and "ToolCall" in source
                    and "ToolResult" in source
                ),
                "uses_student_profile": (
                    "model_profiles" in source and '"student"' in source
                ),
                "limits_model_calls": "max_model_calls_per_invocation=1" in source,
                "uses_hook_model_request": (
                    "HookModelRequest(" in source and "call_model(" in source
                ),
                "parses_json_object": ".json_object()" in source,
                "copies_metadata": "dict(" in source and ".metadata" in source,
                "has_local_prompt": bool(prompt_files),
                "reads_prompt_utf8": (
                    "read_text(encoding=\"utf-8\")" in source
                    or "read_text(encoding='utf-8')" in source
                ),
                "bounds_result_content": (
                    "max_result_chars" in source and "[:" in source
                ),
                "no_broad_exception": "except Exception" not in source,
            }
        )
    elif scenario == "pre_final_semantic":
        checks.update(
            {
                "uses_final_defer": "FinalDecision.defer(" in source,
                "does_not_reaccept": "FinalDecision.accept(" not in source,
                "uses_no_model": "call_model(" not in source,
            }
        )
    return checks


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


if __name__ == "__main__":
    main()
