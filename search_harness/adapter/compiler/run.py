"""Run the standalone Compiler against supported Coordinator evidence."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from search_harness.versioning import HarnessVersionStore
from search_harness.paths import COMPILER_TEMPLATE_ROOT, new_component_run_dir

from .context import CompilerContext
from .runtime import apply_compiler_result, build_compiler_loop, parse_compiler_result


DEFAULT_COMPILER_PLUGINS_ROOT = COMPILER_TEMPLATE_ROOT
DEFAULT_TASK = (
    "Compile the Coordinator-validated strategy into the smallest coherent Harness "
    "plugin transaction that implements its generalized intent."
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "intervention_log", type=Path, help="Supported Coordinator JSON artifact."
    )
    parser.add_argument(
        "--checkpoint-store",
        dest="checkpoint_store",
        type=Path,
        required=True,
        help="Initialized Harness Version Store to evolve.",
    )
    parser.add_argument(
        "--harness-version",
        help="Parent accepted version; default: latest (only latest is writable).",
    )
    parser.add_argument(
        "--compiler-plugins-root",
        type=Path,
        default=DEFAULT_COMPILER_PLUGINS_ROOT,
    )
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--model-role", default="teacher")
    parser.add_argument("--max-steps", type=int, default=35)
    parser.add_argument("--task", default=DEFAULT_TASK)
    parser.add_argument(
        "--output-file",
        type=Path,
        help="UTF-8 JSON log path; default: runs/components/compiler/<run-id>/compiler.json.",
    )
    args = parser.parse_args(argv)
    if args.max_steps < 1:
        parser.error("--max-steps must be positive")
    return args


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    output_file = args.output_file or _default_output_file()
    store = HarnessVersionStore(args.checkpoint_store)
    versions = store.list_versions()
    if not versions:
        raise RuntimeError(f"Harness Version Store is not initialized: {store.root}")
    parent_version = args.harness_version or versions[-1].version_id
    parent = store.resolve(parent_version)
    context = CompilerContext.from_intervention_log(
        intervention_log=args.intervention_log,
        parent=parent,
    )
    session = store.start_iteration(
        parent_version=parent_version,
        metadata={
            "role": "compiler",
            "intervention_log": str(context.intervention_log),
            "critic_log": str(context.critic_log),
            "direction_index": context.direction_index,
        },
    )
    inputs = {
        "intervention_log": str(context.intervention_log),
        "critic_log": str(context.critic_log),
        "direction_index": context.direction_index,
        "checkpoint_store": str(store.root),
        "checkpoint_store_id": store.checkpoint_store_id,
        "parent_version": parent_version,
        "iteration_id": session.iteration_id,
        "compiler_plugins_root": str(args.compiler_plugins_root.resolve()),
        "model_role": args.model_role,
    }
    loop = build_compiler_loop(
        compiler_context=context,
        plugins_root=args.compiler_plugins_root,
        env_file=args.env_file,
        model_role=args.model_role,
        max_steps=args.max_steps,
    )
    try:
        run = loop.run(args.task)
    except Exception as exc:
        _write_log(
            output_file,
            _log_payload(
                inputs=inputs,
                result=None,
                result_error=f"{type(exc).__name__}: {exc}",
                validation=None,
                run=None,
            ),
        )
        print(f"Compiler failure log written to: {output_file}")
        raise

    result = None
    validation = None
    result_error = None
    if run.answer is None:
        result_error = f"Compiler Agent did not complete: {run.status.value}: {run.error}"
    else:
        try:
            result = parse_compiler_result(run.answer)
            validation = apply_compiler_result(
                session, result, env_file=args.env_file
            )
        except (KeyError, TypeError, ValueError, RuntimeError) as exc:
            result_error = f"{type(exc).__name__}: {exc}"

    _write_log(
        output_file,
        _log_payload(
            inputs=inputs,
            result=result.to_dict() if result is not None else None,
            result_error=result_error,
            validation=asdict(validation) if validation is not None else None,
            run=run.to_dict(),
        ),
    )
    print(f"Compiler log written to: {output_file}")
    if result_error is not None:
        raise RuntimeError(result_error)
    assert result is not None
    if result.clarification is not None:
        print(f"Compiler requested clarification; iteration={session.iteration_id}")
    else:
        assert validation is not None
        print(
            f"Compiler candidate prepared: iteration={session.iteration_id}, "
            f"validation_passed={validation.passed}"
        )


def _log_payload(
    *,
    inputs: dict[str, Any],
    result: dict[str, Any] | None,
    result_error: str | None,
    validation: dict[str, Any] | None,
    run: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "inputs": inputs,
        "compiler_result": result,
        "result_error": result_error,
        "validation": validation,
        "run": run,
    }


def _default_output_file() -> Path:
    return new_component_run_dir("compiler") / "compiler.json"


def _write_log(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
