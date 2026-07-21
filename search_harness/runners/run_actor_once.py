"""Run one actor rollout with the core loop."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from search_harness.core import (
    AgentLoop,
    TaggedOutputParser,
    ToolRuntime,
)
from search_harness.models import OpenAICompatibleConfig, OpenAICompatibleTextModel
from search_harness.paths import ACTOR_TEMPLATE_ROOT
from search_harness.registry import build_harness
from search_harness.runtime import get_env_value, parse_int, read_env_file


MAX_AGENT_ITERS_ENV = "MAX_AGENT_ITERS"
DEFAULT_PLUGINS_ROOT = ACTOR_TEMPLATE_ROOT


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one actor rollout.")
    parser.add_argument("question", nargs="+", help="Question for the actor.")
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
        "--plugins-root",
        type=Path,
        default=DEFAULT_PLUGINS_ROOT,
        help="Root directory containing the UTF-8 harness.json and plugin instances.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    question = " ".join(args.question)

    loop = build_loop(
        env_file=args.env_file,
        model_role=args.model_role,
        plugins_root=args.plugins_root,
    )
    run = loop.run(question)
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


def build_loop(
    env_file: Path | None = None,
    model_role: str = "student",
    plugins_root: Path = DEFAULT_PLUGINS_ROOT,
    max_steps: int | None = None,
    seed: int | None = None,
) -> AgentLoop:
    """Build a core loop from an explicit external Harness plugin root."""

    values = read_env_file(env_file)
    selected_max_steps = max_steps or parse_int(
        get_env_value(values, MAX_AGENT_ITERS_ENV), default=10, name=MAX_AGENT_ITERS_ENV
    )

    model_config = OpenAICompatibleConfig.from_env(
        env_file=env_file, prefix=model_role.upper()
    )
    if seed is not None:
        model_config = replace(model_config, seed=seed)
    model = OpenAICompatibleTextModel(model_config)
    harness = build_harness(
        plugins_root, env_file=env_file, model_seed=model_config.seed
    )
    return AgentLoop(
        model=model,
        prompt_builder=harness.prompt_builder,
        parser=TaggedOutputParser(),
        tool_runtime=ToolRuntime(harness.tools.tools),
        max_steps=selected_max_steps,
        hooks=harness.hooks,
    )


if __name__ == "__main__":
    main()
