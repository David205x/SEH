"""Unified public command composition for Search Harness."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path


def main(argv: Sequence[str] | None = None) -> None:
    """Dispatch one supported root command to its application entry."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments[0] in {"-h", "--help"}:
        _print_help()
        return
    command, *remainder = arguments
    if command == "run":
        from search_harness.runners.run_agent_once import main as run_main

        run_main(remainder)
        return
    if command == "evaluate":
        from search_harness.evaluation.run_evaluation import (
            main as evaluate_main,
        )

        evaluate_main(remainder)
        return
    if command == "evolve":
        _run_evolution(remainder)
        return
    if command == "template":
        _run_template(remainder)
        return
    if command == "version-store":
        from search_harness.evolution.versioning.cli import (
            main as version_store_main,
        )

        version_store_main(remainder)
        return
    raise SystemExit(
        f"unknown command '{command}'; use 'python -m search_harness --help'"
    )


def _run_evolution(arguments: list[str]) -> None:
    if not arguments:
        raise SystemExit("evolve requires 'start' or 'resume'")
    action, *remainder = arguments
    if action not in {"start", "resume"}:
        raise SystemExit("evolve requires 'start' or 'resume'")
    from search_harness.evolution.control.cli import main as evolve_main

    evolve_main([action, *remainder])


def _run_template(arguments: list[str]) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m search_harness template",
        description="Inspect and validate a Harness Template.",
    )
    commands = parser.add_subparsers(dest="action", required=True)
    validate = commands.add_parser(
        "validate",
        help="Load the Manifest and assemble all declared Components.",
    )
    validate.add_argument("template_root", type=Path)
    validate.add_argument("--env-file", type=Path, default=Path(".env"))
    args = parser.parse_args(arguments)

    from search_harness.framework.harness import assemble_harness_components

    root = args.template_root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Harness Template does not exist: {root}")
    assembled = assemble_harness_components(root, env_file=args.env_file)
    print(f"template valid: {root}")
    print(f"harness_id: {assembled.manifest.harness_id}")
    print(f"tools: {len(assembled.tools.tools)}")
    print(f"extensions: {len(assembled.extensions)}")


def _print_help() -> None:
    print(
        "\n".join(
            [
                "usage: python -m search_harness <command> [options]",
                "",
                "commands:",
                "  run        Run one Agent rollout.",
                "  evaluate   Evaluate a rollout JSONL file.",
                "  evolve     Start or resume an Evolution Run.",
                "  template   Validate a Harness Template.",
                "  version-store  Initialize a Template Version Store.",
                "",
                "Use '<command> --help' for command-specific options.",
            ]
        )
    )
