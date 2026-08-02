"""Run one Student rollout with the shared Agent loop."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from search_harness.framework import (
    Agent,
    BaseHook,
    Harness,
    HookPipeline,
    LoopRunner,
    RunResult,
    ToolExecutor,
    assemble_harness_components,
)
from search_harness.integrations.openai_compatible import (
    OpenAICompatibleConfig,
    OpenAICompatibleModel,
    ProfiledHookModelBackend,
)
from search_harness.paths import STUDENT_TEMPLATE_ROOT
from search_harness._internal import get_env_value, parse_int, read_env_file


MAX_AGENT_ITERS_ENV = "MAX_AGENT_ITERS"
DEFAULT_TEMPLATE_ROOT = STUDENT_TEMPLATE_ROOT


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m search_harness run",
        description="Run one Agent rollout.",
    )
    parser.add_argument("question", nargs="+", help="Question for the Agent.")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="Path to UTF-8 .env file.",
    )
    parser.add_argument(
        "--trace-file",
        type=Path,
        help="Write rollout trace JSON to this file.",
    )
    parser.add_argument(
        "--show-trace",
        action="store_true",
        help="Print full rollout trace JSON.",
    )
    parser.add_argument(
        "--model-role",
        choices=["student", "teacher"],
        default="student",
        help="Model env prefix to use: STUDENT_* or TEACHER_*.",
    )
    parser.add_argument(
        "--template-root",
        type=Path,
        default=DEFAULT_TEMPLATE_ROOT,
        help="Root directory containing the UTF-8 Harness Template.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    question = " ".join(args.question)

    agent, runner = build_agent_and_runner(
        env_file=args.env_file,
        model_role=args.model_role,
        template_root=args.template_root,
    )
    run = runner.run(agent, question)
    payload = run.to_dict()

    print(f"status: {run.status.value}")
    if run.answer:
        print(run.answer)
    elif run.error:
        print(f"error: {run.error}")

    if args.show_trace:
        print()
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    if args.trace_file:
        args.trace_file.parent.mkdir(parents=True, exist_ok=True)
        args.trace_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print()
        print(f"trace written to: {args.trace_file}")


def build_agent_and_runner(
    env_file: Path | None = None,
    model_role: str = "student",
    template_root: Path = DEFAULT_TEMPLATE_ROOT,
    max_steps: int | None = None,
    seed: int | None = None,
) -> tuple[Agent, LoopRunner]:
    """Build one role-neutral Agent and its configured Loop Runner."""

    values = read_env_file(env_file)
    selected_max_steps = max_steps or parse_int(
        get_env_value(values, MAX_AGENT_ITERS_ENV), default=10, name=MAX_AGENT_ITERS_ENV
    )

    model_config = OpenAICompatibleConfig.from_env(
        env_file=env_file, prefix=model_role.upper()
    )
    if seed is not None:
        model_config = replace(model_config, seed=seed)
    model = OpenAICompatibleModel(model_config)
    assembled = assemble_harness_components(
        template_root,
        env_file=env_file,
    )
    prompt_builder = assembled.prompt
    output_parser = assembled.output
    tool_executor = ToolExecutor(assembled.tools.tools)
    hook_instances = _student_hooks(assembled.extensions)
    hook_model_backend = (
        ProfiledHookModelBackend(env_file=env_file, seed=model_config.seed)
        if any(hook.model_profiles for hook in hook_instances)
        else None
    )
    harness = Harness(
        prompt=prompt_builder,
        output=output_parser,
        tool_executor=tool_executor,
        lifecycle=HookPipeline(
            hook_instances,
            model_backend=hook_model_backend,
        ),
    )
    return Agent(harness=harness, model=model), LoopRunner(max_steps=selected_max_steps)


def run_agent_once(
    question: str,
    *,
    env_file: Path | None = None,
    model_role: str = "student",
    template_root: Path = DEFAULT_TEMPLATE_ROOT,
    max_steps: int | None = None,
    seed: int | None = None,
) -> RunResult:
    """Build and execute one isolated Agent Run."""

    agent, runner = build_agent_and_runner(
        env_file=env_file,
        model_role=model_role,
        template_root=template_root,
        max_steps=max_steps,
        seed=seed,
    )
    return runner.run(agent, question)


def _student_hooks(extension_bindings: tuple[object, ...]) -> tuple[BaseHook, ...]:
    hooks: list[BaseHook] = []
    for binding in extension_bindings:
        for component in binding.components:
            if not isinstance(component, BaseHook):
                raise TypeError(
                    f"Student extension '{binding.instance_id}' returned a non-Hook"
                )
            hooks.append(component)
    return tuple(hooks)
