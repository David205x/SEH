"""Read-only data view bound to one Critic run."""

from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any

from search_harness.datasets import stable_example_id


_CATEGORIES = {"tools", "prompts", "extensions"}
_COMPARISON_TRANSITIONS = {
    "any",
    "primary_only_correct",
    "comparison_only_correct",
    "both_correct",
    "both_incorrect",
    "unresolved",
    "unmatched",
    "success_rate_improved",
    "success_rate_regressed",
    "success_rate_unchanged",
}


@dataclass(frozen=True)
class CriticComparison:
    """Second evidence set aligned with the primary Critic evidence by example ID."""

    report_dir: Path
    rollout_file: Path
    harness_version: str
    evaluation_summary: Mapping[str, Any]
    evaluation_cases: Mapping[str, Mapping[str, Any]]
    rollout_records: Mapping[str, Mapping[str, Mapping[str, Any]]]
    harness_files: Mapping[PurePosixPath, bytes]
    harness_manifest: Mapping[str, Any]


@dataclass(frozen=True)
class CriticContext:
    """Evaluation, rollout and Harness evidence visible to one Critic run."""

    report_dir: Path
    rollout_file: Path
    harness_version: str
    evaluation_summary: Mapping[str, Any]
    evaluation_cases: tuple[Mapping[str, Any], ...]
    rollout_records: Mapping[str, Mapping[str, Mapping[str, Any]]]
    harness_files: Mapping[PurePosixPath, bytes]
    harness_manifest: Mapping[str, Any]
    data_split: str = "experience"
    comparison: CriticComparison | None = None

    @classmethod
    def load(
        cls,
        *,
        report_dir: Path,
        harness_files: Mapping[PurePosixPath, bytes],
        harness_version: str,
        rollout_file: Path | None = None,
        data_split: str = "experience",
    ) -> "CriticContext":
        """Load one report and its source rollout using explicit UTF-8 decoding."""

        if data_split != "experience":
            raise ValueError("Critic MVP only supports the experience data split")
        root = report_dir.resolve()
        summary = _read_json_object(root / "summary.json")
        cases = _prepare_evaluation_cases(_read_jsonl(root / "per_example.jsonl"))
        source = rollout_file or _source_rollout(summary)
        source = source.resolve()
        records = _index_rollouts(_read_jsonl(source))
        files = MappingProxyType(dict(harness_files))
        manifest = _read_manifest(files)
        return cls(
            report_dir=root,
            rollout_file=source,
            harness_version=harness_version,
            evaluation_summary=MappingProxyType(summary),
            evaluation_cases=cases,
            rollout_records=MappingProxyType(records),
            harness_files=files,
            harness_manifest=MappingProxyType(manifest),
            data_split=data_split,
        )

    def bind_comparison(
        self,
        *,
        report_dir: Path,
        harness_files: Mapping[PurePosixPath, bytes],
        harness_version: str,
        rollout_file: Path | None = None,
    ) -> "CriticContext":
        """Return this context with a second aligned report and Harness snapshot."""

        root = report_dir.resolve()
        summary = _read_json_object(root / "summary.json")
        cases = _prepare_evaluation_cases(_read_jsonl(root / "per_example.jsonl"))
        source = (rollout_file or _source_rollout(summary)).resolve()
        files = MappingProxyType(dict(harness_files))
        comparison = CriticComparison(
            report_dir=root,
            rollout_file=source,
            harness_version=harness_version,
            evaluation_summary=MappingProxyType(summary),
            evaluation_cases=MappingProxyType(
                {str(item["example_id"]): item for item in cases}
            ),
            rollout_records=MappingProxyType(_index_rollouts(_read_jsonl(source))),
            harness_files=files,
            harness_manifest=MappingProxyType(_read_manifest(files)),
        )
        return replace(self, comparison=comparison)

    @classmethod
    def from_plugins_root(
        cls,
        *,
        report_dir: Path,
        plugins_root: Path,
        rollout_file: Path | None = None,
        harness_version: str = "working_directory",
    ) -> "CriticContext":
        """Load Critic evidence from an ordinary Actor plugins directory."""

        root = plugins_root.resolve()
        files: dict[PurePosixPath, bytes] = {}
        for path in sorted(root.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                files[PurePosixPath(path.relative_to(root).as_posix())] = path.read_bytes()
        return cls.load(
            report_dir=report_dir,
            rollout_file=rollout_file,
            harness_files=files,
            harness_version=harness_version,
        )

    def initial_context(self) -> dict[str, Any]:
        """Return the compact evidence included in the initial user prompt."""

        payload = {
            "data_split": self.data_split,
            "harness_version": self.harness_version,
            "evaluation_summary": dict(self.evaluation_summary),
            "harness_manifest_summary": _manifest_summary(self.harness_manifest),
        }
        payload["comparison_summary"] = (
            self.get_comparison_summary() if self.comparison is not None else None
        )
        return payload

    def get_comparison_summary(self) -> dict[str, Any]:
        """Return aggregate score transitions for the bound report pair."""

        comparison = self._require_comparison()
        primary = _case_map(self.evaluation_cases)
        secondary = comparison.evaluation_cases
        counts = {name: 0 for name in _COMPARISON_TRANSITIONS if name != "any"}
        matched = set(primary) & set(secondary)
        for example_id in matched:
            counts[_comparison_transition(primary[example_id], secondary[example_id])] += 1
        primary_only = set(primary) - set(secondary)
        comparison_only = set(secondary) - set(primary)
        counts["unmatched"] = len(primary_only) + len(comparison_only)
        replicate_counts = Counter()
        primary_replicates = _evaluation_replicate_map(primary.values())
        comparison_replicates = _evaluation_replicate_map(
            secondary.values()
        )
        for identity in set(primary_replicates) & set(comparison_replicates):
            replicate_counts[
                _comparison_transition(
                    primary_replicates[identity],
                    comparison_replicates[identity],
                )
            ] += 1
        replicate_counts["unmatched"] = len(
            set(primary_replicates) ^ set(comparison_replicates)
        )
        return {
            "primary": {
                "harness_version": self.harness_version,
                "report_dir": str(self.report_dir),
                **_score_summary(primary.values()),
            },
            "comparison": {
                "harness_version": comparison.harness_version,
                "report_dir": str(comparison.report_dir),
                **_score_summary(secondary.values()),
            },
            "matched_count": len(matched),
            "primary_only_count": len(primary_only),
            "comparison_only_count": len(comparison_only),
            "transitions": counts,
            "replicate_comparison": {
                "primary_count": len(primary_replicates),
                "comparison_count": len(comparison_replicates),
                "matched_count": len(
                    set(primary_replicates) & set(comparison_replicates)
                ),
                "transitions": dict(replicate_counts),
            },
        }

    def list_comparison_cases(
        self,
        *,
        page: int,
        page_size: int,
        transition: str,
    ) -> dict[str, Any]:
        """List aligned case outcomes without exposing case content."""

        if page < 1:
            raise ValueError("comparison case page must be positive")
        if page_size < 1 or page_size > 100:
            raise ValueError("comparison case page_size must be between 1 and 100")
        if transition not in _COMPARISON_TRANSITIONS:
            raise ValueError(f"unsupported comparison transition: {transition}")
        comparison = self._require_comparison()
        primary = _case_map(self.evaluation_cases)
        all_ids = sorted(set(primary) | set(comparison.evaluation_cases))
        items = [
            _compact_comparison_case(
                example_id,
                primary.get(example_id),
                comparison.evaluation_cases.get(example_id),
            )
            for example_id in all_ids
        ]
        if transition != "any":
            items = [item for item in items if item["transition"] == transition]
        total_items = len(items)
        total_pages = math.ceil(total_items / page_size) if total_items else 0
        start = (page - 1) * page_size
        return {
            "total_items": total_items,
            "total_pages": total_pages,
            "page": page,
            "page_size": page_size,
            "items": items[start : start + page_size],
        }

    def get_comparison_case(self, example_id: str) -> dict[str, Any]:
        """Return paired complete evaluation records for one aligned ID."""

        comparison = self._require_comparison()
        primary = _case_map(self.evaluation_cases).get(example_id)
        secondary = comparison.evaluation_cases.get(example_id)
        if primary is None and secondary is None:
            raise KeyError(f"comparison case not found: {example_id}")
        return {
            "example_id": example_id,
            "transition": _comparison_transition(primary, secondary),
            "primary": dict(primary) if primary is not None else None,
            "comparison": dict(secondary) if secondary is not None else None,
            "replicate_transitions": _replicate_transitions(primary, secondary),
        }

    def get_comparison_trajectory(
        self, example_id: str, replicate_id: str
    ) -> dict[str, Any]:
        """Return paired complete rollouts and their recorded execution delta."""

        comparison = self._require_comparison()
        primary = self.rollout_records.get(example_id, {}).get(replicate_id)
        secondary = comparison.rollout_records.get(example_id, {}).get(replicate_id)
        if primary is None and secondary is None:
            raise KeyError(
                f"comparison trajectory not found: {example_id}/{replicate_id}"
            )
        paired_case = self.get_comparison_case(example_id)
        primary_case = _replicate_case(paired_case["primary"], replicate_id)
        comparison_case = _replicate_case(
            paired_case["comparison"], replicate_id
        )
        return {
            "example_id": example_id,
            "replicate_id": replicate_id,
            "transition": _comparison_transition(primary_case, comparison_case),
            "execution_delta": _execution_delta(
                primary_case, comparison_case
            ),
            "primary": dict(primary) if primary is not None else None,
            "comparison": dict(secondary) if secondary is not None else None,
        }

    def get_harness_change_summary(self) -> dict[str, Any]:
        """Return candidate (primary) changes relative to its baseline comparison."""

        comparison = self._require_comparison()
        primary_paths = set(self.harness_files)
        secondary_paths = set(comparison.harness_files)
        modified = sorted(
            path
            for path in primary_paths & secondary_paths
            if self.harness_files[path] != comparison.harness_files[path]
        )
        return {
            "primary_version": self.harness_version,
            "comparison_version": comparison.harness_version,
            "added_paths": [str(path) for path in sorted(primary_paths - secondary_paths)],
            "modified_paths": [str(path) for path in modified],
            "removed_paths": [str(path) for path in sorted(secondary_paths - primary_paths)],
            "components": _component_changes(
                self.harness_manifest, comparison.harness_manifest
            ),
        }

    def _require_comparison(self) -> CriticComparison:
        if self.comparison is None:
            raise ValueError("no comparison report is bound to this Critic run")
        return self.comparison

    def list_evaluation_cases(
        self,
        *,
        page: int,
        page_size: int,
        score: int,
        run_status: str,
        has_retriever_error: str,
        stability: str = "any",
    ) -> dict[str, Any]:
        """Filter and paginate compact evaluation case records."""

        if page < 1:
            raise ValueError("evaluation case page must be positive")
        if page_size < 1 or page_size > 100:
            raise ValueError("evaluation case page_size must be between 1 and 100")
        if score not in {-1, 0, 1}:
            raise ValueError("evaluation case score must be -1, 0 or 1")
        if has_retriever_error not in {"any", "true", "false"}:
            raise ValueError("invalid retriever error filter")
        if stability not in {
            "any",
            "stable_correct",
            "stable_failure",
            "unstable",
            "unresolved",
        }:
            raise ValueError("invalid stability filter")
        filtered = [
            item
            for item in self.evaluation_cases
            if _matches_case(
                item,
                score=score,
                run_status=run_status,
                has_retriever_error=has_retriever_error,
                stability=stability,
            )
        ]
        total_items = len(filtered)
        total_pages = math.ceil(total_items / page_size) if total_items else 0
        start = (page - 1) * page_size
        items = [_compact_case(item) for item in filtered[start : start + page_size]]
        return {
            "total_items": total_items,
            "total_pages": total_pages,
            "page": page,
            "page_size": page_size,
            "items": items,
        }

    def get_case_evaluation(self, example_id: str) -> dict[str, Any]:
        """Return one complete item from the evaluation report."""

        for item in self.evaluation_cases:
            if item.get("example_id") == example_id:
                return dict(item)
        raise KeyError(f"evaluation case not found: {example_id}")

    def get_case_trajectory(
        self, example_id: str, replicate_id: str
    ) -> dict[str, Any]:
        """Return one complete source rollout record."""

        try:
            return dict(self.rollout_records[example_id][replicate_id])
        except KeyError as exc:
            raise KeyError(
                f"rollout trajectory not found: {example_id}/{replicate_id}"
            ) from exc

    def get_harness_manifest(self) -> dict[str, Any]:
        """Return the complete manifest for the bound Actor Harness."""

        return dict(self.harness_manifest)

    def get_harness_component(self, category: str, component_id: str) -> dict[str, Any]:
        """Return one manifest component and all UTF-8 files in its directory."""

        if category not in _CATEGORIES:
            raise ValueError(f"unsupported Harness category: {category}")
        raw_specs = self.harness_manifest.get(category)
        if category == "prompts":
            raw_specs = [self.harness_manifest.get("prompt")]
        if not isinstance(raw_specs, list):
            raise ValueError(f"Harness manifest category is invalid: {category}")
        spec = next(
            (
                item
                for item in raw_specs
                if isinstance(item, dict) and item.get("instance_id") == component_id
            ),
            None,
        )
        if spec is None:
            raise KeyError(f"Harness component not found: {category}/{component_id}")
        entrypoint = spec.get("entrypoint")
        if not isinstance(entrypoint, str):
            raise ValueError("Harness component entrypoint must be a string")
        module_path = PurePosixPath(entrypoint.partition(":")[0])
        component_dir = module_path.parent
        files: dict[str, str] = {}
        for path, content in sorted(self.harness_files.items(), key=lambda item: str(item[0])):
            if path == component_dir or component_dir not in path.parents:
                continue
            try:
                files[str(path)] = content.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError(f"Harness component file is not UTF-8: {path}") from exc
        return {
            "category": category,
            "component_id": component_id,
            "manifest": dict(spec),
            "files": files,
        }


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Critic input does not exist: {path}") from exc
    if not isinstance(value, dict):
        raise TypeError(f"Critic input must contain a JSON object: {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Critic input does not exist: {path}") from exc
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"{path}:{line_number}: invalid JSON: {exc.msg}"
            ) from exc
        if not isinstance(value, dict):
            raise TypeError(f"{path}:{line_number}: JSONL record must be an object")
        records.append(value)
    return records


def _source_rollout(summary: Mapping[str, Any]) -> Path:
    source = summary.get("source_file")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("evaluation summary has no source_file; pass rollout_file explicitly")
    return Path(source)


def _index_rollouts(
    records: list[dict[str, Any]],
) -> dict[str, Mapping[str, Mapping[str, Any]]]:
    indexed: dict[str, dict[str, Mapping[str, Any]]] = {}
    for record in records:
        example = record.get("example")
        raw_id = example.get("example_id") if isinstance(example, dict) else None
        raw_question = example.get("question") if isinstance(example, dict) else None
        run = record.get("run")
        if not isinstance(raw_question, str) and isinstance(run, dict):
            raw_question = run.get("question")
        question = raw_question if isinstance(raw_question, str) else ""
        example_id = stable_example_id(raw_id, question)
        replicate = record.get("replicate")
        replicate_id = (
            replicate.get("replicate_id") if isinstance(replicate, dict) else "r000"
        )
        if not isinstance(replicate_id, str) or not replicate_id.strip():
            raise ValueError(f"rollout {example_id} has invalid replicate_id")
        by_replicate = indexed.setdefault(example_id, {})
        if replicate_id in by_replicate:
            raise ValueError(
                f"duplicate rollout identity: {example_id}/{replicate_id}"
            )
        by_replicate[replicate_id] = MappingProxyType(dict(record))
    return {
        example_id: MappingProxyType(dict(by_replicate))
        for example_id, by_replicate in indexed.items()
    }


def _prepare_evaluation_cases(
    cases: list[dict[str, Any]],
) -> tuple[Mapping[str, Any], ...]:
    prepared: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for item in cases:
        question = item.get("question")
        example_id = stable_example_id(
            item.get("example_id"), question if isinstance(question, str) else ""
        )
        if example_id in seen:
            raise ValueError(f"duplicate evaluation example_id: {example_id}")
        seen.add(example_id)
        copied = dict(item)
        copied["example_id"] = example_id
        prepared.append(MappingProxyType(copied))
    return tuple(prepared)


def _case_map(
    cases: tuple[Mapping[str, Any], ...],
) -> dict[str, Mapping[str, Any]]:
    return {str(item["example_id"]): item for item in cases}


def _comparison_transition(
    primary: Mapping[str, Any] | None,
    comparison: Mapping[str, Any] | None,
) -> str:
    if primary is None or comparison is None:
        return "unmatched"
    primary_score = primary.get("score")
    comparison_score = comparison.get("score")
    if primary_score == 1 and comparison_score == 0:
        return "primary_only_correct"
    if primary_score == 0 and comparison_score == 1:
        return "comparison_only_correct"
    if primary_score == 1 and comparison_score == 1:
        return "both_correct"
    if primary_score == 0 and comparison_score == 0:
        return "both_incorrect"
    primary_rate = primary.get("success_rate")
    comparison_rate = comparison.get("success_rate")
    if isinstance(primary_rate, (int, float)) and isinstance(
        comparison_rate, (int, float)
    ):
        if primary_rate > comparison_rate:
            return "success_rate_improved"
        if primary_rate < comparison_rate:
            return "success_rate_regressed"
        return "success_rate_unchanged"
    return "unresolved"


def _replicate_transitions(
    primary: Mapping[str, Any] | None,
    comparison: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    def index(case: Mapping[str, Any] | None) -> dict[str, Mapping[str, Any]]:
        raw = case.get("replicates") if case is not None else None
        if not isinstance(raw, list):
            return {}
        return {
            str(item["replicate_id"]): item
            for item in raw
            if isinstance(item, Mapping) and isinstance(item.get("replicate_id"), str)
        }

    primary_replicates = index(primary)
    comparison_replicates = index(comparison)
    return [
        {
            "replicate_id": replicate_id,
            "transition": _comparison_transition(
                primary_replicates.get(replicate_id),
                comparison_replicates.get(replicate_id),
            ),
            "primary_score": (
                primary_replicates[replicate_id].get("score")
                if replicate_id in primary_replicates
                else None
            ),
            "comparison_score": (
                comparison_replicates[replicate_id].get("score")
                if replicate_id in comparison_replicates
                else None
            ),
        }
        for replicate_id in sorted(
            set(primary_replicates) | set(comparison_replicates)
        )
    ]


def _evaluation_replicate_map(
    cases: Any,
) -> dict[tuple[str, str], Mapping[str, Any]]:
    result: dict[tuple[str, str], Mapping[str, Any]] = {}
    for case in cases:
        example_id = str(case.get("example_id"))
        raw = case.get("replicates")
        replicates = raw if isinstance(raw, list) else [{**case, "replicate_id": "r000"}]
        for replicate in replicates:
            if not isinstance(replicate, Mapping):
                continue
            replicate_id = replicate.get("replicate_id")
            if isinstance(replicate_id, str):
                result[(example_id, replicate_id)] = replicate
    return result


def _replicate_case(
    case: Mapping[str, Any] | None, replicate_id: str
) -> Mapping[str, Any] | None:
    if case is None:
        return None
    raw = case.get("replicates")
    if not isinstance(raw, list):
        return case if replicate_id == "r000" else None
    return next(
        (
            item
            for item in raw
            if isinstance(item, Mapping)
            and item.get("replicate_id") == replicate_id
        ),
        None,
    )


def _score_summary(cases: Any) -> dict[str, Any]:
    scores = [item.get("score") for item in cases if item.get("score") in {0, 1}]
    correct = sum(scores)
    return {
        "record_count": len(cases) if hasattr(cases, "__len__") else None,
        "scored_count": len(scores),
        "correct_count": correct,
        "accuracy": correct / len(scores) if scores else None,
        "mean_success_rate": _mean_case_value(cases, "success_rate"),
    }


def _compact_comparison_case(
    example_id: str,
    primary: Mapping[str, Any] | None,
    comparison: Mapping[str, Any] | None,
) -> dict[str, Any]:
    return {
        "example_id": example_id,
        "transition": _comparison_transition(primary, comparison),
        "primary_score": primary.get("score") if primary is not None else None,
        "comparison_score": comparison.get("score") if comparison is not None else None,
        "primary_run_status": primary.get("run_status") if primary is not None else None,
        "primary_stability": primary.get("stability") if primary is not None else None,
        "primary_success_rate": (
            primary.get("success_rate") if primary is not None else None
        ),
        "comparison_run_status": (
            comparison.get("run_status") if comparison is not None else None
        ),
        "comparison_stability": (
            comparison.get("stability") if comparison is not None else None
        ),
        "comparison_success_rate": (
            comparison.get("success_rate") if comparison is not None else None
        ),
    }


def _execution_delta(
    primary: Mapping[str, Any] | None,
    comparison: Mapping[str, Any] | None,
) -> dict[str, Any]:
    primary_execution = primary.get("execution") if isinstance(primary, Mapping) else None
    comparison_execution = (
        comparison.get("execution") if isinstance(comparison, Mapping) else None
    )
    if not isinstance(primary_execution, dict):
        primary_execution = {}
    if not isinstance(comparison_execution, dict):
        comparison_execution = {}
    delta: dict[str, Any] = {}
    for key in ("steps", "model_calls", "tool_calls", "retriever_errors", "duplicate_queries"):
        candidate_value = primary_execution.get(key)
        baseline_value = comparison_execution.get(key)
        if isinstance(candidate_value, (int, float)) and isinstance(
            baseline_value, (int, float)
        ):
            delta[key] = candidate_value - baseline_value
        else:
            delta[key] = None
    return delta


def _component_changes(
    primary: Mapping[str, Any],
    comparison: Mapping[str, Any],
) -> dict[str, list[str]]:
    primary_components = _manifest_components(primary)
    comparison_components = _manifest_components(comparison)
    common = set(primary_components) & set(comparison_components)
    return {
        "added": sorted(set(primary_components) - set(comparison_components)),
        "modified": sorted(
            component_id
            for component_id in common
            if primary_components[component_id] != comparison_components[component_id]
        ),
        "removed": sorted(set(comparison_components) - set(primary_components)),
    }


def _manifest_components(manifest: Mapping[str, Any]) -> dict[str, Any]:
    components: dict[str, Any] = {}
    for category in ("tools", "extensions"):
        raw = manifest.get(category, [])
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict) and isinstance(item.get("instance_id"), str):
                    components[item["instance_id"]] = (category, item)
    prompt = manifest.get("prompt")
    if isinstance(prompt, dict) and isinstance(prompt.get("instance_id"), str):
        components[prompt["instance_id"]] = ("prompts", prompt)
    return components


def _read_manifest(files: Mapping[PurePosixPath, bytes]) -> dict[str, Any]:
    try:
        content = files[PurePosixPath("harness.json")]
    except KeyError as exc:
        raise FileNotFoundError("Actor Harness snapshot has no harness.json") from exc
    try:
        value = json.loads(content.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ValueError("Actor Harness manifest is not UTF-8") from exc
    if not isinstance(value, dict):
        raise TypeError("Actor Harness manifest must contain a JSON object")
    return value


def _manifest_summary(manifest: Mapping[str, Any]) -> dict[str, Any]:
    def compact(spec: object) -> dict[str, Any] | None:
        if not isinstance(spec, dict):
            return None
        return {
            key: spec.get(key)
            for key in ("instance_id", "enabled", "evolution_policy")
        }

    return {
        "harness_id": manifest.get("harness_id"),
        "tools": [compact(item) for item in manifest.get("tools", [])],
        "prompt": compact(manifest.get("prompt")),
        "extensions": [compact(item) for item in manifest.get("extensions", [])],
    }


def _matches_case(
    item: Mapping[str, Any],
    *,
    score: int,
    run_status: str,
    has_retriever_error: str,
    stability: str,
) -> bool:
    if score != -1 and item.get("score") != score:
        return False
    if stability != "any" and item.get("stability") != stability:
        return False
    actual_status = item.get("run_status")
    if actual_status is None and item.get("runner_error") is not None:
        actual_status = "runner_error"
    if run_status != "any" and actual_status != run_status:
        return False
    execution = item.get("execution")
    errors = execution.get("retriever_errors", 0) if isinstance(execution, dict) else 0
    has_error = isinstance(errors, int) and errors > 0
    if has_retriever_error == "true" and not has_error:
        return False
    if has_retriever_error == "false" and has_error:
        return False
    return True


def _mean_case_value(cases: Any, key: str) -> float | None:
    values = [
        item.get(key)
        for item in cases
        if isinstance(item.get(key), (int, float))
    ]
    return sum(values) / len(values) if values else None


def _compact_case(item: Mapping[str, Any]) -> dict[str, Any]:
    execution = item.get("execution") if isinstance(item.get("execution"), dict) else {}
    static = item.get("static") if isinstance(item.get("static"), dict) else {}
    return {
        "example_id": item.get("example_id"),
        "question": item.get("question"),
        "golden_answer": item.get("golden_answer"),
        "predicted_answer": item.get("predicted_answer"),
        "score": item.get("score"),
        "score_source": item.get("score_source"),
        "stability": item.get("stability"),
        "success_rate": item.get("success_rate"),
        "correct_count": item.get("correct_count"),
        "requested_rollouts": item.get("requested_rollouts"),
        "failed_replicate_ids": item.get("failed_replicate_ids", []),
        "unresolved_replicate_ids": item.get("unresolved_replicate_ids", []),
        "static_decision": static.get("decision"),
        "run_status": item.get("run_status"),
        "runner_error": item.get("runner_error"),
        "tool_calls": execution.get("tool_calls", execution.get("mean_tool_calls")),
        "retriever_errors": execution.get("retriever_errors"),
    }
