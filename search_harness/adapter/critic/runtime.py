"""Critic Agent assembly and final artifact parsing."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from search_harness.core import AgentLoop, AgentRun, ModelClient, TaggedOutputParser, ToolRuntime
from search_harness.models import OpenAICompatibleConfig, OpenAICompatibleTextModel
from search_harness.registry import build_harness
from search_harness.runtime import get_env_value, parse_float, read_env_file
from search_harness.adapter.result_guard import StructuredResultGuard

from .context import CriticContext
from .types import CriticResult


CRITIC_REQUEST_TIMEOUT_ENV = "CRITIC_REQUEST_TIMEOUT"


def build_critic_loop(
    *,
    critic_context: CriticContext,
    plugins_root: Path,
    env_file: Path | None = None,
    model: ModelClient | None = None,
    model_role: str = "teacher",
    max_steps: int = 20,
) -> AgentLoop:
    """Assemble a Critic Agent from an external plugin root."""

    components = build_harness(
        plugins_root,
        env_file=env_file,
        runtime_context=critic_context,
    )
    selected_model = model or _build_critic_model(
        env_file=env_file,
        model_role=model_role,
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
                    hook_id="critic_result_protocol_guard",
                    role_name="Critic",
                    parser=parse_critic_result,
                    shape_hint=(
                        "{analysis, problem_directions: [{problem, observed_pattern, "
                        "excluded_causes, desired_behavior, success_criteria, "
                        "constraints}], evidence_requests, review}"
                    ),
                ),
            )
        ),
    )


def _build_critic_model(
    *,
    env_file: Path | None,
    model_role: str,
) -> OpenAICompatibleTextModel:
    """Build the Critic model with its role-specific request timeout."""

    config = OpenAICompatibleConfig.from_env(
        env_file=env_file,
        prefix=model_role.upper(),
    )
    values = read_env_file(env_file)
    timeout = parse_float(
        get_env_value(values, CRITIC_REQUEST_TIMEOUT_ENV),
        default=config.timeout,
        name=CRITIC_REQUEST_TIMEOUT_ENV,
    )
    return OpenAICompatibleTextModel(replace(config, timeout=timeout))


def run_critic(loop: AgentLoop, task: str) -> tuple[AgentRun, CriticResult]:
    """Run one Critic loop and parse its completed answer artifact."""

    run = loop.run(task)
    if run.answer is None:
        raise RuntimeError(f"Critic Agent did not complete: {run.status.value}: {run.error}")
    return run, parse_critic_result(run.answer)


def parse_critic_result(answer: str) -> CriticResult:
    """Parse the JSON object inside the loop's final-answer branch."""

    try:
        payload = json.loads(answer.strip())
    except json.JSONDecodeError as exc:
        raise ValueError(f"Critic final answer is not valid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Critic final answer must be a JSON object")
    return CriticResult.from_dict(payload)
