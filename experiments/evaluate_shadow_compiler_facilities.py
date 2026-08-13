"""Run deterministic semantic smoke tests for uncovered Compiler facilities."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from experiments.evaluate_complex_compiler_matrix import (
    PARENT_TEMPLATE_ROOT,
    _extension_hooks,
    _run_phase,
)
from search_harness.evolution.versioning import CandidateWorkspace, HarnessSnapshot
from search_harness.evolution.versioning.validation import stage_files
from search_harness.framework import (
    AgentState,
    FinalDecision,
    FinalDecisionAction,
    HookPhase,
    HookPipeline,
    ToolCall,
    ToolResult,
)
from search_harness.framework.harness import assemble_harness_components


_ROOT = Path(__file__).resolve().parents[1]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output-file", type=Path, required=True)
    return parser.parse_args(argv)


def evaluate(args: argparse.Namespace) -> list[dict[str, Any]]:
    records = []
    scenarios = {"case_01": "pre_tool", "case_02": "multi_phase"}
    for case, scenario in scenarios.items():
        for path in sorted((args.artifact_root / case).glob("*.json")):
            artifact = _read_json(path)
            candidate = (
                artifact.get("resource_artifacts", {}).get("compiler_candidate")
            )
            errors = []
            try:
                _smoke(candidate["changed_files"], scenario)
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
            records.append(
                {
                    "case": case,
                    "scenario": scenario,
                    "artifact": str(path.resolve()),
                    "passed": not errors,
                    "errors": errors,
                }
            )
    args.output_file.parent.mkdir(parents=True, exist_ok=True)
    args.output_file.write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return records


def _smoke(changed_files: dict[str, str | None], scenario: str) -> None:
    parent = HarnessSnapshot.from_directory(PARENT_TEMPLATE_ROOT, version_id="parent")
    workspace = CandidateWorkspace(parent)
    for path, content in changed_files.items():
        if content is None:
            workspace.delete(path)
        else:
            workspace.write_text(path, content)
    with stage_files(workspace.materialized_files()) as template_root:
        assembled = assemble_harness_components(
            template_root,
            env_file=_ROOT / ".env",
        )
        hooks = _extension_hooks(assembled.extensions)
        if scenario == "pre_tool":
            _smoke_pre_tool(hooks)
        elif scenario == "multi_phase":
            _smoke_multi_phase(hooks)
        else:
            raise ValueError(f"unknown scenario: {scenario}")


def _smoke_pre_tool(hooks: tuple[Any, ...]) -> None:
    pipeline = HookPipeline(hooks)
    state = AgentState(question="facility probe", max_steps=8, step=1)
    store = pipeline.begin_run(state)
    call = ToolCall(name="search", arguments={"query": "  alpha beta  ", "k": 3})
    first = _run_phase(
        pipeline,
        HookPhase.PRE_TOOL,
        state,
        store,
        {"tool_call": call},
    )["tool_call"]
    _require(first.name == "search", "tool name changed")
    _require(first.arguments == {"query": "alpha beta", "k": 3}, "arguments not preserved")
    later = ToolCall(name="search", arguments={"query": "  later  ", "k": 4})
    second = _run_phase(
        pipeline,
        HookPhase.PRE_TOOL,
        state,
        store,
        {"tool_call": later},
    )["tool_call"]
    _require(second == later, "pre_tool rewrite exceeded activation budget")
    other_pipeline = HookPipeline(hooks)
    other_state = AgentState(question="facility probe", max_steps=8, step=1)
    other_store = other_pipeline.begin_run(other_state)
    other = ToolCall(name="other", arguments={"query": "  untouched  "})
    unchanged = _run_phase(
        other_pipeline,
        HookPhase.PRE_TOOL,
        other_state,
        other_store,
        {"tool_call": other},
    )["tool_call"]
    _require(unchanged == other, "non-search tool changed")


def _smoke_multi_phase(hooks: tuple[Any, ...]) -> None:
    pipeline = HookPipeline(hooks)
    state = AgentState(question="facility probe", max_steps=8, step=1)
    store = pipeline.begin_run(state)
    call = ToolCall(name="search", arguments={"query": "probe"})
    empty = ToolResult(name="search", content="   ", metadata={"source": "probe"})
    observed = _run_phase(
        pipeline,
        HookPhase.POST_TOOL,
        state,
        store,
        {"tool_call": call, "tool_result": empty},
    )["tool_result"]
    _require(observed == empty, "state-only post_tool action changed result")
    first = _run_phase(
        pipeline,
        HookPhase.PRE_FINAL,
        state,
        store,
        {"final_decision": FinalDecision.accept("first")},
    )["final_decision"]
    _require(first.action is FinalDecisionAction.DEFER, "empty result did not defer")
    accepted = FinalDecision.accept("second")
    second = _run_phase(
        pipeline,
        HookPhase.PRE_FINAL,
        state,
        store,
        {"final_decision": accepted},
    )["final_decision"]
    _require(second == accepted, "multi-phase Hook deferred more than once")

    clean_pipeline = HookPipeline(hooks)
    clean_state = AgentState(question="facility probe", max_steps=8, step=1)
    clean_store = clean_pipeline.begin_run(clean_state)
    result = ToolResult(name="search", content="evidence", metadata={})
    _run_phase(
        clean_pipeline,
        HookPhase.POST_TOOL,
        clean_state,
        clean_store,
        {"tool_call": call, "tool_result": result},
    )
    decision = FinalDecision.accept("answer")
    unchanged = _run_phase(
        clean_pipeline,
        HookPhase.PRE_FINAL,
        clean_state,
        clean_store,
        {"final_decision": decision},
    )["final_decision"]
    _require(unchanged == decision, "non-empty result caused false deferral")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    records = evaluate(parse_args())
    for record in records:
        print(
            f"{record['case']} {Path(record['artifact']).name}: "
            f"{'PASS' if record['passed'] else record['errors']}"
        )
    return 0 if all(record["passed"] for record in records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
