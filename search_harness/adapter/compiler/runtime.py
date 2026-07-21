"""Compiler Agent assembly, artifact parsing and transaction application."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from search_harness.core import (
    AgentLoop,
    AgentRun,
    ModelClient,
    TaggedOutputParser,
    ToolRuntime,
)
from search_harness.models import OpenAICompatibleConfig, OpenAICompatibleTextModel
from search_harness.registry import build_harness
from search_harness.runtime import get_env_value, parse_float, read_env_file
from search_harness.versioning import IterationSession, ValidationReport
from search_harness.adapter.result_guard import StructuredResultGuard

from .context import CompilerContext
from .types import CompilerResult


COMPILER_REQUEST_TIMEOUT_ENV = "COMPILER_REQUEST_TIMEOUT"


def build_compiler_loop(
    *,
    compiler_context: CompilerContext,
    plugins_root: Path,
    env_file: Path | None = None,
    model: ModelClient | None = None,
    model_role: str = "teacher",
    max_steps: int = 20,
) -> AgentLoop:
    """Assemble a Compiler Agent from an external plugin root."""

    components = build_harness(
        plugins_root,
        env_file=env_file,
        runtime_context=compiler_context,
    )
    selected_model = model or _build_compiler_model(
        env_file=env_file, model_role=model_role
    )
    return AgentLoop(
        model=selected_model,
        prompt_builder=components.prompt_builder,
        parser=TaggedOutputParser(),
        tool_runtime=ToolRuntime(components.tools.tools),
        max_steps=max_steps,
        hooks=components.hooks.extended(
            (
                StructuredResultGuard(
                    hook_id="compiler_result_protocol_guard",
                    role_name="Compiler",
                    parser=parse_compiler_result,
                    shape_hint=(
                        "{summary: non-empty string, edits: complete edit array, "
                        "clarification: null} or {summary, edits: [], "
                        "clarification: non-empty string}"
                    ),
                ),
            )
        ),
    )


def run_compiler(loop: AgentLoop, task: str) -> tuple[AgentRun, CompilerResult]:
    """Run one Compiler loop and parse its completed transaction artifact."""

    run = loop.run(task)
    if run.answer is None:
        raise RuntimeError(f"Compiler Agent did not complete: {run.status.value}: {run.error}")
    return run, parse_compiler_result(run.answer)


def parse_compiler_result(answer: str) -> CompilerResult:
    """Parse the JSON object inside the loop's final-answer branch."""

    try:
        payload = json.loads(answer.strip())
    except json.JSONDecodeError as exc:
        raise ValueError(f"Compiler final answer is not valid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Compiler final answer must be a JSON object")
    return CompilerResult.from_dict(payload)


def apply_compiler_result(
    session: IterationSession,
    result: CompilerResult,
    *,
    env_file: Path | None = None,
) -> ValidationReport | None:
    """Journal, apply and validate one complete Compiler transaction."""

    if result.clarification is not None:
        return None
    session.apply_patch(result.edits)
    return session.validate(env_file=env_file)


def _build_compiler_model(
    *, env_file: Path | None, model_role: str
) -> OpenAICompatibleTextModel:
    config = OpenAICompatibleConfig.from_env(
        env_file=env_file,
        prefix=model_role.upper(),
    )
    values = read_env_file(env_file)
    timeout = parse_float(
        get_env_value(values, COMPILER_REQUEST_TIMEOUT_ENV),
        default=config.timeout,
        name=COMPILER_REQUEST_TIMEOUT_ENV,
    )
    return OpenAICompatibleTextModel(replace(config, timeout=timeout))
