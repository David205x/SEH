"""Run the read-only Critic Agent against one evaluation report."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from search_harness.versioning import HarnessVersionStore, content_digest
from search_harness.paths import ACTOR_TEMPLATE_ROOT, CRITIC_TEMPLATE_ROOT, new_component_run_dir

from .context import CriticContext
from .evidence import (
    validate_accepted_rollouts,
    validate_iteration_rollouts,
    validate_paired_rollouts,
)
from .runtime import build_critic_loop, parse_critic_result


DEFAULT_ACTOR_PLUGINS_ROOT = ACTOR_TEMPLATE_ROOT
DEFAULT_CRITIC_PLUGINS_ROOT = CRITIC_TEMPLATE_ROOT
DEFAULT_TASK = (
    "Analyze the evaluated Actor rollouts, identify repeated Harness-level failure "
    "patterns, and return prioritized behavioral problem directions or evidence requests."
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report_dir", type=Path, help="Evaluation report directory.")
    parser.add_argument(
        "--rollout-file",
        type=Path,
        help="Override the source rollout path recorded by summary.json.",
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--actor-plugins-root",
        type=Path,
        help=f"Actor plugins directory; default: {DEFAULT_ACTOR_PLUGINS_ROOT}.",
    )
    source.add_argument(
        "--checkpoint-store",
        dest="checkpoint_store",
        type=Path,
        help="Checkpoint Store containing the Actor Harness snapshot.",
    )
    version_source = parser.add_mutually_exclusive_group()
    version_source.add_argument(
        "--harness-version",
        help="Accepted version from --checkpoint-store; default: latest.",
    )
    version_source.add_argument(
        "--iteration-id",
        help="Pending Version Store iteration to review as the primary Harness.",
    )
    parser.add_argument(
        "--compare-report-dir",
        type=Path,
        help="Optional second evaluation report to align by example_id.",
    )
    parser.add_argument(
        "--compare-rollout-file",
        type=Path,
        help="Override the source rollout path for --compare-report-dir.",
    )
    parser.add_argument(
        "--compare-actor-plugins-root",
        type=Path,
        help="Optional Actor plugins directory used by the comparison report.",
    )
    parser.add_argument(
        "--compare-harness-version",
        help="Accepted comparison version from --checkpoint-store.",
    )
    parser.add_argument(
        "--critic-plugins-root",
        type=Path,
        default=DEFAULT_CRITIC_PLUGINS_ROOT,
        help=f"Critic plugin root; default: {DEFAULT_CRITIC_PLUGINS_ROOT}.",
    )
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--model-role", default="teacher")
    parser.add_argument("--max-steps", type=int, default=20)
    parser.add_argument("--task", default=DEFAULT_TASK)
    parser.add_argument(
        "--output-file",
        type=Path,
        help="UTF-8 JSON log path; default: runs/components/critic/<run-id>/critic.json.",
    )
    args = parser.parse_args(argv)
    if args.max_steps < 1:
        parser.error("--max-steps must be positive")
    if args.harness_version and args.checkpoint_store is None:
        parser.error("--harness-version requires --checkpoint-store")
    if args.iteration_id and args.checkpoint_store is None:
        parser.error("--iteration-id requires --checkpoint-store")
    comparison_options = (
        args.compare_rollout_file,
        args.compare_actor_plugins_root,
        args.compare_harness_version,
    )
    if (
        any(value is not None for value in comparison_options)
        and args.compare_report_dir is None
    ):
        parser.error("comparison options require --compare-report-dir")
    if args.compare_harness_version and args.checkpoint_store is None:
        parser.error("--compare-harness-version requires --checkpoint-store")
    if args.compare_actor_plugins_root is not None and args.checkpoint_store is not None:
        parser.error("--compare-actor-plugins-root cannot be combined with --checkpoint-store")
    return args


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    output_file = args.output_file or _default_output_file()
    critic_context, actor_source, iteration = _build_context(args)
    inputs = {
        "report_dir": str(critic_context.report_dir),
        "rollout_file": str(critic_context.rollout_file),
        "actor_source": actor_source,
        "checkpoint_store_id": (
            HarnessVersionStore(Path(actor_source)).checkpoint_store_id
            if args.checkpoint_store is not None
            else None
        ),
        "harness_version": critic_context.harness_version,
        "harness_digest": content_digest(critic_context.harness_files),
        "iteration": iteration,
        "critic_plugins_root": str(args.critic_plugins_root.resolve()),
        "model_role": args.model_role,
        "data_split": critic_context.data_split,
        "comparison": (
            {
                "report_dir": str(critic_context.comparison.report_dir),
                "rollout_file": str(critic_context.comparison.rollout_file),
                "harness_version": critic_context.comparison.harness_version,
                "harness_digest": content_digest(
                    critic_context.comparison.harness_files
                ),
            }
            if critic_context.comparison is not None
            else None
        ),
    }
    loop = build_critic_loop(
        critic_context=critic_context,
        plugins_root=args.critic_plugins_root,
        env_file=args.env_file,
        model_role=args.model_role,
        max_steps=args.max_steps,
    )
    try:
        run = loop.run(args.task)
    except Exception as exc:
        _write_log(
            output_file,
            {
                "schema_version": 1,
                "created_at": datetime.now(UTC).isoformat(),
                "inputs": inputs,
                "critic_result": None,
                "result_error": f"{type(exc).__name__}: {exc}",
                "run": None,
            },
        )
        print(f"Critic failure log written to: {output_file}")
        raise
    result = None
    result_error = None
    if run.answer is None:
        result_error = f"Critic Agent did not complete: {run.status.value}: {run.error}"
    else:
        try:
            result = parse_critic_result(run.answer)
        except ValueError as exc:
            result_error = str(exc)

    payload: dict[str, Any] = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "inputs": inputs,
        "critic_result": result.to_dict() if result is not None else None,
        "result_error": result_error,
        "run": run.to_dict(),
    }
    _write_log(output_file, payload)
    print(f"Critic log written to: {output_file}")
    if result_error is not None:
        raise RuntimeError(result_error)
    assert result is not None
    print(
        f"Critic completed: problem_directions={len(result.problem_directions)}, "
        f"evidence_requests={len(result.evidence_requests)}"
    )


def _build_context(
    args: argparse.Namespace,
) -> tuple[CriticContext, str, dict[str, Any] | None]:
    if args.checkpoint_store is not None:
        store = HarnessVersionStore(args.checkpoint_store)
        versions = store.list_versions()
        if not versions:
            raise RuntimeError(f"Harness Version Store is not initialized: {store.root}")
        if args.iteration_id is not None:
            session = store.resume_iteration(args.iteration_id)
            with session.stage() as plugins_root:
                candidate_files = _read_plugins_files(plugins_root)
            context = CriticContext.load(
                report_dir=args.report_dir,
                rollout_file=args.rollout_file,
                harness_files=candidate_files,
                harness_version=f"pending:{session.iteration_id}",
            )
            validate_iteration_rollouts(
                context,
                iteration_id=session.iteration_id,
                candidate_digest=session.digest,
            )
            if args.compare_report_dir is not None:
                comparison_version = (
                    args.compare_harness_version or session.parent_version
                )
                comparison_snapshot = store.resolve(comparison_version)
                context = context.bind_comparison(
                    report_dir=args.compare_report_dir,
                    rollout_file=args.compare_rollout_file,
                    harness_files=comparison_snapshot.files,
                    harness_version=comparison_version,
                )
                validate_accepted_rollouts(
                    context.comparison.rollout_records,
                    store_root=store.root,
                    checkpoint_store_id=store.checkpoint_store_id,
                    version_id=comparison_snapshot.version_id,
                    digest=comparison_snapshot.digest,
                    evidence_name="comparison",
                )
                validate_paired_rollouts(context)
            return (
                context,
                str(store.root),
                {
                    "iteration_id": session.iteration_id,
                    "parent_version": session.parent_version,
                    "candidate_digest": session.digest,
                    "revision": session.revision,
                },
            )

        version_id = args.harness_version or versions[-1].version_id
        snapshot = store.resolve(version_id)
        context = CriticContext.load(
            report_dir=args.report_dir,
            rollout_file=args.rollout_file,
            harness_files=snapshot.files,
            harness_version=version_id,
        )
        validate_accepted_rollouts(
            context.rollout_records,
            store_root=store.root,
            checkpoint_store_id=store.checkpoint_store_id,
            version_id=snapshot.version_id,
            digest=snapshot.digest,
            evidence_name="primary",
        )
        if args.compare_report_dir is not None:
            comparison_version = args.compare_harness_version or version_id
            comparison_snapshot = store.resolve(comparison_version)
            context = context.bind_comparison(
                report_dir=args.compare_report_dir,
                rollout_file=args.compare_rollout_file,
                harness_files=comparison_snapshot.files,
                harness_version=comparison_version,
            )
            validate_accepted_rollouts(
                context.comparison.rollout_records,
                store_root=store.root,
                checkpoint_store_id=store.checkpoint_store_id,
                version_id=comparison_snapshot.version_id,
                digest=comparison_snapshot.digest,
                evidence_name="comparison",
            )
            validate_paired_rollouts(context)
        return context, str(store.root), None

    plugins_root = args.actor_plugins_root or DEFAULT_ACTOR_PLUGINS_ROOT
    context = CriticContext.from_plugins_root(
        report_dir=args.report_dir,
        rollout_file=args.rollout_file,
        plugins_root=plugins_root,
    )
    if args.compare_report_dir is not None:
        comparison_root = args.compare_actor_plugins_root or plugins_root
        comparison_files = _read_plugins_files(comparison_root)
        context = context.bind_comparison(
            report_dir=args.compare_report_dir,
            rollout_file=args.compare_rollout_file,
            harness_files=comparison_files,
            harness_version=(
                "comparison_working_directory"
                if comparison_root.resolve() != plugins_root.resolve()
                else context.harness_version
            ),
        )
        validate_paired_rollouts(context)
    return context, str(plugins_root.resolve()), None


def _read_plugins_files(root: Path) -> dict[PurePosixPath, bytes]:
    resolved = root.resolve()
    return {
        PurePosixPath(path.relative_to(resolved).as_posix()): path.read_bytes()
        for path in sorted(resolved.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    }


def _default_output_file() -> Path:
    return new_component_run_dir("critic") / "critic.json"


def _write_log(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
