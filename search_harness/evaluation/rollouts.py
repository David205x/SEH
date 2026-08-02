"""Run and persist comparable Agent rollouts for Evaluation."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from itertools import islice
from pathlib import Path
from typing import TextIO

from tqdm import tqdm

from search_harness.framework import RunResult
from search_harness.datasets import DatasetExample
from search_harness._internal import ordered_parallel_map
from search_harness.evolution.versioning import (
    HarnessSnapshot,
    TemplateVersionStore,
)
from search_harness.runners.run_agent_once import DEFAULT_TEMPLATE_ROOT


AgentRunCallable = Callable[[int | None, str], RunResult]


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
    template_root: str | None = None
    version_store: str | None = None
    version_store_id: str | None = None
    version_id: str | None = None
    parent_version: str | None = None
    candidate_attempt_id: str | None = None
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
    run_agent: AgentRunCallable,
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
                    run_agent=run_agent,
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


@contextmanager
def open_harness_source(
    *,
    template_root: Path | None = None,
    version_store: Path | None = None,
    harness_version: str | None = None,
    candidate_attempt_id: str | None = None,
    env_file: Path | None = None,
) -> Iterator[tuple[Path, HarnessRunSource]]:
    """Stage one direct, accepted or pending Harness for a complete rollout batch."""

    if template_root is not None and version_store is not None:
        raise ValueError("template_root and version_store are mutually exclusive")
    if harness_version is not None and candidate_attempt_id is not None:
        raise ValueError(
            "harness_version and candidate_attempt_id are mutually exclusive"
        )
    if version_store is None:
        if harness_version is not None or candidate_attempt_id is not None:
            raise ValueError("Harness version selectors require version_store")
        root = (template_root or DEFAULT_TEMPLATE_ROOT).resolve()
        yield root, HarnessRunSource(
            source_type="template_root",
            template_root=str(root),
            candidate_digest=HarnessSnapshot.from_directory(root).digest,
        )
        return

    store = TemplateVersionStore(version_store)
    if candidate_attempt_id is not None:
        attempt = store.resume_candidate_attempt(candidate_attempt_id)
        report = attempt.validate(env_file=env_file)
        if not report.passed:
            details = "; ".join(report.errors) or "unknown validation error"
            raise ValueError(f"pending Harness candidate failed validation: {details}")
        source = HarnessRunSource(
            source_type="pending_candidate_attempt",
            version_store=str(store.root),
            version_store_id=store.version_store_id,
            parent_version=attempt.parent_version,
            candidate_attempt_id=attempt.candidate_attempt_id,
            candidate_digest=attempt.digest,
            revision=attempt.revision,
        )
        with attempt.stage() as root:
            yield root, source
        return

    versions = store.list_versions()
    if not versions:
        raise RuntimeError(f"Harness Version Store is not initialized: {store.root}")
    version_id = harness_version or versions[-1].version_id
    snapshot = store.resolve(version_id)
    source = HarnessRunSource(
        source_type="accepted_version",
        version_store=str(store.root),
        version_store_id=store.version_store_id,
        version_id=snapshot.version_id,
        candidate_digest=snapshot.digest,
    )
    with store.stage(snapshot) as root:
        yield root, source


def _run_example(
    work_item: RolloutWorkItem,
    *,
    run_agent: AgentRunCallable,
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
        run = run_agent(work_item.sampling_seed, example.question)
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
