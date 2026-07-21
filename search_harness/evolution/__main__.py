"""启动或恢复单候选 Harness Evolution run。"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Sequence

from search_harness.datasets import DatasetConfig, create_dataset_loader
from search_harness.versioning import HarnessVersionStore

from .backend import LocalEvolutionBackend, LocalEvolutionBackendConfig
from .progress import LoggingProgressReporter, TqdmLoggingHandler
from .runner import EvolutionConfig, EvolutionRunner


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """解析 Evolution Runner CLI 参数。"""

    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="Start a new evolution run.")
    run.add_argument("--run-dir", type=Path, required=True)
    run.add_argument("--checkpoint-store", type=Path, required=True)
    run.add_argument("--dataset-path", type=Path)
    run.add_argument("--dataset-format")
    run.add_argument("--limit", type=int, default=20)
    run.add_argument("--max-iterations", type=int, default=1)
    run.add_argument("--failure-memory-limit", type=int, default=5)
    run.add_argument("--compiler-revision-limit", type=int, default=2)
    run.add_argument("--intervention-continuation-limit", type=int, default=2)
    _add_backend_arguments(run)

    resume = subparsers.add_parser("resume", help="Resume a durable evolution run.")
    resume.add_argument("run_dir", type=Path)
    _add_backend_arguments(resume, defaults_none=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    """构建 backend，并执行或恢复状态机。"""

    args = parse_args(argv)
    if args.command == "run":
        _start(args)
    else:
        _resume(args)


def _start(args: argparse.Namespace) -> None:
    env_file = args.env_file
    dataset_config = (
        DatasetConfig.from_env(env_file=env_file)
        if args.dataset_path is None
        else DatasetConfig(
            path=args.dataset_path,
            **({"format_name": args.dataset_format} if args.dataset_format else {}),
        )
    )
    config = EvolutionConfig(
        max_iterations=args.max_iterations,
        experience_limit=args.limit,
        failure_memory_limit=args.failure_memory_limit,
        compiler_revision_limit=args.compiler_revision_limit,
        intervention_continuation_limit=args.intervention_continuation_limit,
    )
    backend_config = _backend_config(args)
    progress = _configure_logging(
        args.run_dir, level=args.log_level, use_tqdm=backend_config.show_progress
    )
    store = HarnessVersionStore(args.checkpoint_store)
    runner = EvolutionRunner(
        run_dir=args.run_dir,
        store=store,
        backend=LocalEvolutionBackend(store=store, config=backend_config),
        config=config,
        validation_env_file=backend_config.env_file,
        progress_reporter=progress,
        metadata={
            "dataset": {
                "path": str(dataset_config.path.resolve()),
                "format": dataset_config.format_name,
                "filter_status": dataset_config.filter_status,
            },
            "backend": _backend_metadata(backend_config),
        },
    )
    loader = create_dataset_loader(dataset_config)
    runner.initialize(loader.iter_examples())
    _print_outcome(runner.run())


def _resume(args: argparse.Namespace) -> None:
    run_dir = args.run_dir.resolve()
    raw = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    config = EvolutionConfig(**raw["config"])
    stored_backend = dict(raw.get("metadata", {}).get("backend", {}))
    backend_config = _backend_config(args, stored=stored_backend)
    progress = _configure_logging(
        run_dir, level=args.log_level, use_tqdm=backend_config.show_progress
    )
    store = HarnessVersionStore(Path(raw["checkpoint_store"]))
    runner = EvolutionRunner(
        run_dir=run_dir,
        store=store,
        backend=LocalEvolutionBackend(store=store, config=backend_config),
        config=config,
        validation_env_file=backend_config.env_file,
        progress_reporter=progress,
        metadata=dict(raw.get("metadata", {})),
    )
    _print_outcome(runner.run())


def _add_backend_arguments(
    parser: argparse.ArgumentParser, *, defaults_none: bool = False
) -> None:
    default = None if defaults_none else Path(".env")
    parser.add_argument("--env-file", type=Path, default=default)
    parser.add_argument("--critic-plugins-root", type=Path, default=None)
    parser.add_argument("--compiler-plugins-root", type=Path, default=None)
    parser.add_argument(
        "--intervention-coordinator-plugins-root", type=Path, default=None
    )
    parser.add_argument("--actor-model-role", default=None)
    parser.add_argument("--adapter-model-role", default=None)
    parser.add_argument("--actor-max-steps", type=int, default=None)
    parser.add_argument("--critic-max-steps", type=int, default=None)
    parser.add_argument("--critic-protocol-repair-limit", type=int, default=None)
    parser.add_argument("--compiler-max-steps", type=int, default=None)
    parser.add_argument("--compiler-validation-repair-limit", type=int, default=None)
    parser.add_argument("--compiler-smoke-examples", type=int, default=None)
    parser.add_argument("--intervention-max-steps", type=int, default=None)
    parser.add_argument("--intervention-max-trials", type=int, default=None)
    parser.add_argument("--rollout-workers", type=int, default=None)
    parser.add_argument("--rollouts-per-example", type=int, default=None)
    parser.add_argument("--judge-workers", type=int, default=None)
    parser.add_argument("--no-teacher-judge", action="store_true")
    parser.add_argument("--no-progress", action="store_true")
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        default="INFO",
    )


def _backend_config(
    args: argparse.Namespace, *, stored: dict[str, Any] | None = None
) -> LocalEvolutionBackendConfig:
    stored = stored or {}
    defaults = LocalEvolutionBackendConfig()

    def choose(name: str) -> Any:
        value = getattr(args, name, None)
        if value is not None:
            return value
        if name in stored:
            if name.endswith("_root") or name == "env_file":
                return Path(stored[name])
            return stored[name]
        return getattr(defaults, name)

    return LocalEvolutionBackendConfig(
        env_file=choose("env_file"),
        critic_plugins_root=choose("critic_plugins_root"),
        compiler_plugins_root=choose("compiler_plugins_root"),
        intervention_coordinator_plugins_root=choose(
            "intervention_coordinator_plugins_root"
        ),
        actor_model_role=choose("actor_model_role"),
        adapter_model_role=choose("adapter_model_role"),
        actor_max_steps=choose("actor_max_steps"),
        critic_max_steps=choose("critic_max_steps"),
        critic_protocol_repair_limit=choose("critic_protocol_repair_limit"),
        compiler_max_steps=choose("compiler_max_steps"),
        compiler_validation_repair_limit=choose(
            "compiler_validation_repair_limit"
        ),
        compiler_smoke_examples=choose("compiler_smoke_examples"),
        intervention_max_steps=choose("intervention_max_steps"),
        intervention_max_trials=choose("intervention_max_trials"),
        rollout_workers=choose("rollout_workers"),
        rollouts_per_example=choose("rollouts_per_example"),
        judge_workers=choose("judge_workers"),
        teacher_judge=False if args.no_teacher_judge else stored.get("teacher_judge", True),
        show_progress=False if args.no_progress else stored.get("show_progress", True),
    )


def _backend_metadata(config: LocalEvolutionBackendConfig) -> dict[str, Any]:
    return {
        "env_file": str(config.env_file.resolve()),
        "critic_plugins_root": str(config.critic_plugins_root.resolve()),
        "compiler_plugins_root": str(config.compiler_plugins_root.resolve()),
        "intervention_coordinator_plugins_root": str(
            config.intervention_coordinator_plugins_root.resolve()
        ),
        "actor_model_role": config.actor_model_role,
        "adapter_model_role": config.adapter_model_role,
        "actor_max_steps": config.actor_max_steps,
        "critic_max_steps": config.critic_max_steps,
        "critic_protocol_repair_limit": config.critic_protocol_repair_limit,
        "compiler_max_steps": config.compiler_max_steps,
        "compiler_validation_repair_limit": config.compiler_validation_repair_limit,
        "compiler_smoke_examples": config.compiler_smoke_examples,
        "intervention_max_steps": config.intervention_max_steps,
        "intervention_max_trials": config.intervention_max_trials,
        "rollout_workers": config.rollout_workers,
        "rollouts_per_example": config.rollouts_per_example,
        "judge_workers": config.judge_workers,
        "teacher_judge": config.teacher_judge,
        "show_progress": config.show_progress,
    }


def _print_outcome(outcome: Any) -> None:
    print(
        f"evolution {outcome.status}: iterations={outcome.completed_iterations}, "
        f"accepted={outcome.accepted_iterations}, latest={outcome.latest_version}"
    )
    print(outcome.reason)


def _configure_logging(
    run_dir: Path, *, level: str, use_tqdm: bool
) -> LoggingProgressReporter:
    """配置兼容 tqdm 的控制台日志和 UTF-8 文本日志。"""

    resolved = run_dir.resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("search_harness.evolution")
    logger.setLevel(getattr(logging, level))
    logger.propagate = False
    logger.handlers.clear()

    console: logging.Handler = (
        TqdmLoggingHandler() if use_tqdm else logging.StreamHandler()
    )
    console.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(console)

    file_handler = logging.FileHandler(
        resolved / "evolution.log", encoding="utf-8"
    )
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    )
    logger.addHandler(file_handler)
    return LoggingProgressReporter(logger)


if __name__ == "__main__":
    main()
