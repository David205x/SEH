"""Run sequential actor rollouts for questions loaded from a dataset."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from itertools import islice
from pathlib import Path
from typing import TextIO

from tqdm import tqdm

from search_harness.core import AgentLoop
from search_harness.datasets import (
    DatasetConfig,
    DatasetExample,
    create_dataset_loader,
)
from search_harness.models import OpenAICompatibleConfig
from search_harness.paths import new_component_run_dir
from search_harness.runtime import ordered_parallel_map
from search_harness.versioning import HarnessSnapshot, HarnessVersionStore

from .run_actor_once import DEFAULT_PLUGINS_ROOT, build_loop


@dataclass(frozen=True)
class DatasetRunSummary:
    """Counts emitted after a dataset rollout completes."""

    output_file: Path
    requested: int
    processed: int
    runner_errors: int
    requested_rollouts: int | None = None
    rollouts_per_example: int = 1
    stopped_early: bool = False
    stop_reason: str | None = None


@dataclass(frozen=True)
class RolloutWorkItem:
    """One reproducible replicate of one logical dataset example."""

    example: DatasetExample
    replicate_index: int
    sampling_seed: int | None

    @property
    def replicate_id(self) -> str:
        return f"r{self.replicate_index:03d}"


@dataclass(frozen=True)
class HarnessRunSource:
    """Auditable identity of the Harness used for one rollout batch."""

    source_type: str
    plugins_root: str | None = None
    checkpoint_store: str | None = None
    checkpoint_store_id: str | None = None
    version_id: str | None = None
    parent_version: str | None = None
    iteration_id: str | None = None
    candidate_digest: str | None = None
    revision: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            key: value
            for key, value in vars(self).items()
            if value is not None
        }


def run_examples(
    examples: Iterable[DatasetExample],
    loop_factory: Callable[[int | None], AgentLoop],
    output_file: Path,
    limit: int,
    fail_fast: bool = False,
    show_progress: bool = True,
    harness_source: Mapping[str, object] | None = None,
    experiment_provenance: Mapping[str, object] | None = None,
    max_workers: int = 1,
    rollouts_per_example: int = 1,
    base_seed: int | None = None,
    max_consecutive_identical_errors: int | None = None,
) -> DatasetRunSummary:
    """Run up to ``limit`` examples and append one complete record per line."""

    if limit < 1:
        raise ValueError("limit must be positive")
    if max_workers < 1:
        raise ValueError("max_workers must be positive")
    if rollouts_per_example < 1:
        raise ValueError("rollouts_per_example must be positive")
    if rollouts_per_example > 1 and base_seed is None:
        raise ValueError("repeated rollouts require a configured base_seed")
    if (
        max_consecutive_identical_errors is not None
        and max_consecutive_identical_errors < 1
    ):
        raise ValueError(
            "max_consecutive_identical_errors must be positive when configured"
        )

    output_file.parent.mkdir(parents=True, exist_ok=True)
    selected_examples = list(islice(examples, limit))
    work_items = [
        RolloutWorkItem(
            example=example,
            replicate_index=replicate_index,
            sampling_seed=(
                base_seed + replicate_index if base_seed is not None else None
            ),
        )
        for example in selected_examples
        for replicate_index in range(rollouts_per_example)
    ]
    processed = 0
    runner_errors = 0
    consecutive_error_count = 0
    previous_error_fingerprint: tuple[str, str] | None = None
    stop_reason: str | None = None
    with tqdm(
        total=len(work_items),
        desc="Rollouts",
        unit="rollout",
        dynamic_ncols=True,
        disable=not show_progress,
    ) as progress:
        with output_file.open("w", encoding="utf-8") as file:
            records = ordered_parallel_map(
                work_items,
                lambda work_item: _run_example(
                    work_item,
                    loop_factory=loop_factory,
                    fail_fast=fail_fast,
                    harness_source=harness_source,
                    experiment_provenance=experiment_provenance,
                ),
                max_workers=max_workers,
                max_in_flight=max_workers * 2,
                on_complete=lambda _: progress.update(1),
            )
            for record in records:
                runner_error = record.get("runner_error")
                if isinstance(runner_error, dict):
                    runner_errors += 1
                    fingerprint = (
                        str(runner_error.get("type", "")),
                        str(runner_error.get("message", "")),
                    )
                    if fingerprint == previous_error_fingerprint:
                        consecutive_error_count += 1
                    else:
                        previous_error_fingerprint = fingerprint
                        consecutive_error_count = 1
                else:
                    previous_error_fingerprint = None
                    consecutive_error_count = 0
                _write_record(file, record)
                processed += 1
                if (
                    max_consecutive_identical_errors is not None
                    and consecutive_error_count
                    >= max_consecutive_identical_errors
                ):
                    stop_reason = (
                        "consecutive identical runner error limit reached: "
                        f"{consecutive_error_count}; "
                        f"{previous_error_fingerprint[0]}: "
                        f"{previous_error_fingerprint[1]}"
                    )
                    break

    return DatasetRunSummary(
        output_file=output_file,
        requested=limit,
        processed=processed,
        runner_errors=runner_errors,
        requested_rollouts=len(work_items),
        rollouts_per_example=rollouts_per_example,
        stopped_early=stop_reason is not None,
        stop_reason=stop_reason,
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="Path to UTF-8 .env file.",
    )
    parser.add_argument(
        "--dataset-path",
        type=Path,
        help="Override the dataset path configured in the .env file.",
    )
    parser.add_argument(
        "--dataset-format",
        help="Dataset format used with --dataset-path.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1,
        help="Number of examples to run; default: 1.",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        help="UTF-8 JSONL output path; default: runs/components/actor/<run-id>/rollout.jsonl.",
    )
    parser.add_argument(
        "--model-role",
        choices=["student", "teacher"],
        default="student",
        help="Model env prefix to use: STUDENT_* or TEACHER_*.",
    )
    parser.add_argument(
        "--rollout-workers",
        type=int,
        default=2,
        help="Maximum concurrent independent rollouts; default: 2.",
    )
    parser.add_argument(
        "--rollouts-per-example",
        type=int,
        default=1,
        help="Independent rollouts per logical example; default: 1.",
    )
    harness_source = parser.add_mutually_exclusive_group()
    harness_source.add_argument(
        "--plugins-root",
        type=Path,
        help=(
            "Root directory containing the UTF-8 harness.json and plugin instances; "
            f"default: {DEFAULT_PLUGINS_ROOT}."
        ),
    )
    harness_source.add_argument(
        "--checkpoint-store",
        dest="checkpoint_store",
        type=Path,
        help="Harness Checkpoint Store containing accepted versions and pending iterations.",
    )
    version_selector = parser.add_mutually_exclusive_group()
    version_selector.add_argument(
        "--harness-version",
        help="Accepted Harness version to run; default: latest accepted version.",
    )
    version_selector.add_argument(
        "--iteration-id",
        help="Validated pending iteration to run without accepting it.",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop immediately when a model or runner exception occurs.",
    )
    args = parser.parse_args(argv)
    if (
        args.harness_version is not None or args.iteration_id is not None
    ) and args.checkpoint_store is None:
        parser.error("--harness-version and --iteration-id require --checkpoint-store")
    return args


def main() -> None:
    args = parse_args()
    dataset_config = _dataset_config_from_args(args)
    loader = create_dataset_loader(dataset_config)
    with open_harness_source(
        plugins_root=args.plugins_root,
        checkpoint_store=args.checkpoint_store,
        harness_version=args.harness_version,
        iteration_id=args.iteration_id,
        env_file=args.env_file,
    ) as (plugins_root, harness_source):
        summary = run_examples(
            examples=loader.iter_examples(),
            loop_factory=lambda seed: build_loop(
                env_file=args.env_file,
                model_role=args.model_role,
                plugins_root=plugins_root,
                seed=seed,
            ),
            output_file=args.output_file or (new_component_run_dir("actor") / "rollout.jsonl"),
            limit=args.limit,
            fail_fast=args.fail_fast,
            harness_source=harness_source.to_dict(),
            experiment_provenance=_experiment_provenance(
                args=args,
                dataset_config=dataset_config,
                harness_source=harness_source,
            ),
            max_workers=args.rollout_workers,
            rollouts_per_example=args.rollouts_per_example,
            base_seed=OpenAICompatibleConfig.from_env(
                env_file=args.env_file, prefix=args.model_role.upper()
            ).seed,
        )
    print(
        "completed "
        f"{summary.processed}/{summary.requested_rollouts} rollout(s) from "
        f"{summary.requested} example(s); "
        f"runner_errors={summary.runner_errors}"
    )
    print(f"results written to: {summary.output_file}")


@contextmanager
def open_harness_source(
    *,
    plugins_root: Path | None = None,
    checkpoint_store: Path | None = None,
    harness_version: str | None = None,
    iteration_id: str | None = None,
    env_file: Path | None = None,
) -> Iterator[tuple[Path, HarnessRunSource]]:
    """Stage one direct, accepted or pending Harness for a complete rollout batch."""

    if plugins_root is not None and checkpoint_store is not None:
        raise ValueError("plugins_root and checkpoint_store are mutually exclusive")
    if harness_version is not None and iteration_id is not None:
        raise ValueError("harness_version and iteration_id are mutually exclusive")
    if checkpoint_store is None:
        if harness_version is not None or iteration_id is not None:
            raise ValueError("Harness version selectors require checkpoint_store")
        root = (plugins_root or DEFAULT_PLUGINS_ROOT).resolve()
        yield root, HarnessRunSource(
            source_type="plugins_root",
            plugins_root=str(root),
            candidate_digest=HarnessSnapshot.from_directory(root).digest,
        )
        return

    store = HarnessVersionStore(checkpoint_store)
    if iteration_id is not None:
        session = store.resume_iteration(iteration_id)
        report = session.validate(env_file=env_file)
        if not report.passed:
            details = "; ".join(report.errors) or "unknown validation error"
            raise ValueError(f"pending Harness candidate failed validation: {details}")
        source = HarnessRunSource(
            source_type="pending_iteration",
            checkpoint_store=str(store.root),
            checkpoint_store_id=store.checkpoint_store_id,
            parent_version=session.parent_version,
            iteration_id=session.iteration_id,
            candidate_digest=session.digest,
            revision=session.revision,
        )
        with session.stage() as root:
            yield root, source
        return

    versions = store.list_versions()
    if not versions:
        raise RuntimeError(f"Harness Version Store is not initialized: {store.root}")
    version_id = harness_version or versions[-1].version_id
    snapshot = store.resolve(version_id)
    source = HarnessRunSource(
        source_type="accepted_version",
        checkpoint_store=str(store.root),
        checkpoint_store_id=store.checkpoint_store_id,
        version_id=snapshot.version_id,
        candidate_digest=snapshot.digest,
    )
    with store.stage(snapshot) as root:
        yield root, source


def _dataset_config_from_args(args: argparse.Namespace) -> DatasetConfig:
    if args.dataset_path is None:
        return DatasetConfig.from_env(env_file=args.env_file)

    config = (
        DatasetConfig(path=args.dataset_path)
        if args.dataset_format is None
        else DatasetConfig(path=args.dataset_path, format_name=args.dataset_format)
    )
    return config


def _experiment_provenance(
    *,
    args: argparse.Namespace,
    dataset_config: DatasetConfig,
    harness_source: HarnessRunSource,
) -> dict[str, object]:
    """Build one non-secret, per-record provenance payload for a rollout batch."""

    model = OpenAICompatibleConfig.from_env(
        env_file=args.env_file,
        prefix=args.model_role.upper(),
    )
    return {
        "schema_version": 1,
        "dataset": {
            "path": str(dataset_config.path.resolve()),
            "format": dataset_config.format_name,
            "filter_status": dataset_config.filter_status,
            "selection": {"limit": args.limit, "order": "source_order"},
        },
        "model": {"role": args.model_role, **model.provenance()},
        "harness": harness_source.to_dict(),
        "execution": {
            "rollout_workers": args.rollout_workers,
            "rollouts_per_example": args.rollouts_per_example,
            "seed_strategy": "base_plus_replicate_index",
        },
    }


def _run_example(
    work_item: RolloutWorkItem,
    *,
    loop_factory: Callable[[int | None], AgentLoop],
    fail_fast: bool,
    harness_source: Mapping[str, object] | None,
    experiment_provenance: Mapping[str, object] | None,
) -> dict[str, object]:
    """Run one isolated example and return a complete serializable record."""

    example = work_item.example
    record: dict[str, object] = {
        "example": example.to_dict(),
        "replicate": {
            "replicate_id": work_item.replicate_id,
            "index": work_item.replicate_index,
            "sampling_seed": work_item.sampling_seed,
        },
    }
    if harness_source is not None:
        record["harness"] = dict(harness_source)
    if experiment_provenance is not None:
        record["provenance"] = dict(experiment_provenance)
    try:
        run = loop_factory(work_item.sampling_seed).run(example.question)
    except Exception as exc:
        if fail_fast:
            raise
        record["runner_error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
        }
        return record
    record["run"] = run.to_dict()
    return record


def _write_record(file: TextIO, record: dict[str, object]) -> None:
    line = json.dumps(record, ensure_ascii=False)
    file.write(f"{line}\n")
    file.flush()


if __name__ == "__main__":
    main()
