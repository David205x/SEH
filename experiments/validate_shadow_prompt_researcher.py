"""Validate Shadow Prompt Research on existing Distiller and Trial artifacts."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

from search_harness.evolution.research.resources.base import (
    TeacherResourceConfig,
)
from search_harness.evolution.research.roles.native_chat_runner import (
    NativeChatRoleRunner,
    TeacherRoleRunFailed,
)
from search_harness.evolution.research.shadow_prompt_research import (
    ShadowPromptResearchResourceConfig,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = (
    PROJECT_ROOT
    / "harness_templates"
    / "teacher"
    / "shadow_prompt_researcher"
)


def main() -> None:
    args = _parse_args()
    result = asyncio.run(_run(args))
    print(json.dumps(result, ensure_ascii=False))


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    distiller_path = args.distiller_artifact.resolve()
    distiller = _read_json(distiller_path)
    output_dir = args.output_dir.resolve()
    if output_dir.exists():
        raise FileExistsError(
            f"Prompt Research output already exists: {output_dir}"
        )
    mechanism_path = (
        args.mechanism_artifact.resolve()
        if args.mechanism_artifact is not None
        else output_dir / "source_mechanism.json"
    )
    mechanism = (
        _read_json(mechanism_path)
        if args.mechanism_artifact is not None
        else _inline_shadow_mechanism(distiller)
    )
    distiller_input = _required_object(distiller, "input")
    trial_reviews = distiller_input.get("trial_reviews")
    if not isinstance(trial_reviews, list) or not trial_reviews:
        raise TypeError("Distiller artifact lacks Trial Reviews")
    resource_config = _required_object(distiller, "resource_config")
    raw_trial_files = resource_config.get("trial_files")
    if not isinstance(raw_trial_files, list) or not raw_trial_files:
        raise TypeError("Distiller artifact lacks trial_files")
    trial_files = [Path(str(path)).resolve() for path in raw_trial_files]
    rollout_file = _infer_rollout_file(trial_files[0])
    phase = _single_hook_phase(mechanism)
    output_dir.mkdir(parents=True)
    if args.mechanism_artifact is None:
        _write_json(mechanism_path, mechanism)
    source_hashes = {
        str(path): _sha256(path)
        for path in [mechanism_path, distiller_path, *trial_files, rollout_file]
    }
    results = []
    for repetition in range(1, args.repetitions + 1):
        run_dir = output_dir / f"run_{repetition:03d}"
        run_dir.mkdir(parents=True, exist_ok=True)
        try:
            artifact = await NativeChatRoleRunner(
                env_file=args.env_file,
            ).run(
                template_root=TEMPLATE_ROOT,
                role_id="shadow_prompt_researcher",
                role_version=1,
                role_input={
                    "mechanism": mechanism,
                    "phase": phase,
                    "trial_reviews": trial_reviews,
                },
                resource_config=TeacherResourceConfig(
                    trial_files=trial_files,
                    shadow_prompt_research=ShadowPromptResearchResourceConfig(
                        rollout_file=rollout_file,
                        env_file=args.env_file.resolve(),
                        max_cases=args.max_cases,
                        repetitions=args.probe_repetitions,
                        thinking_modes=("enabled", "disabled"),
                    ),
                ),
            )
            status = "completed"
            error = None
        except TeacherRoleRunFailed as exc:
            artifact = exc.failure_artifact
            status = "failed"
            error = str(exc)
        role_path = _write_json(run_dir / "role.json", artifact)
        output = artifact.get("output")
        probes = _prompt_probes(artifact)
        result = {
            "repetition": repetition,
            "status": status,
            "error": error,
            "artifact": str(role_path),
            "output": output,
            "tool_names": [
                item.get("name")
                for item in artifact.get("tool_calls", [])
                if isinstance(item, dict)
            ],
            "usage": artifact.get("usage", {}),
            "probe_count": len(probes),
            "nested_usage": _nested_usage(probes),
        }
        results.append(result)
    preserved = all(
        path.is_file() and _sha256(path) == digest
        for path_text, digest in source_hashes.items()
        for path in [Path(path_text)]
    )
    summary = {
        "schema_version": 1,
        "mechanism_artifact": str(mechanism_path),
        "distiller_artifact": str(distiller_path),
        "rollout_file": str(rollout_file),
        "source_hashes_preserved": preserved,
        "results": results,
        "aggregate": _aggregate(results),
    }
    summary_path = _write_json(output_dir / "summary.json", summary)
    return {
        "status": "completed",
        "result_count": len(results),
        "summary": str(summary_path),
    }


def _parse_args(
    argv: Sequence[str] | None = None,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mechanism-artifact",
        type=Path,
        help=(
            "Optional standalone Shadow Mechanism. When omitted, extract "
            "output.mechanism from --distiller-artifact."
        ),
    )
    parser.add_argument("--distiller-artifact", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--max-cases", type=int, default=4)
    parser.add_argument("--probe-repetitions", type=int, default=2)
    args = parser.parse_args(argv)
    if args.repetitions < 1:
        parser.error("--repetitions must be positive")
    return args


def _inline_shadow_mechanism(
    distiller: dict[str, Any],
) -> dict[str, Any]:
    output = _required_object(distiller, "output")
    if output.get("outcome") != "distilled":
        raise ValueError("Shadow Distiller did not produce a mechanism")
    mechanism = output.get("mechanism")
    if not isinstance(mechanism, dict):
        raise TypeError("Shadow Distiller output lacks inline mechanism")
    return dict(mechanism)


def _infer_rollout_file(trial_file: Path) -> Path:
    trial = _read_json(trial_file)
    resource_config = _required_object(trial, "resource_config")
    intervention = _required_object(resource_config, "intervention")
    value = intervention.get("rollout_file")
    if not isinstance(value, str) or not value:
        raise TypeError("Trial artifact lacks intervention rollout_file")
    path = Path(value).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Trial rollout does not exist: {path}")
    return path


def _single_hook_phase(mechanism: dict[str, Any]) -> str:
    phases = mechanism.get("phases")
    if not isinstance(phases, list) or len(phases) != 1:
        raise ValueError("experiment requires one Mechanism phase")
    phase = phases[0]
    if not isinstance(phase, dict):
        raise TypeError("Mechanism phase must be an object")
    task = _required_object(phase, "task")
    if task.get("evaluator") != "hook_model":
        raise ValueError("experiment requires a hook_model Task")
    value = phase.get("phase")
    if not isinstance(value, str) or not value:
        raise TypeError("Mechanism phase lacks phase name")
    return value


def _prompt_probes(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    resources = artifact.get("resource_artifacts")
    if not isinstance(resources, dict):
        return []
    probes = resources.get("shadow_prompt_probes")
    if not isinstance(probes, list):
        return []
    return [dict(item) for item in probes if isinstance(item, dict)]


def _nested_usage(probes: list[dict[str, Any]]) -> dict[str, int]:
    student = 0
    reviewer = 0
    for probe in probes:
        prompt_review = probe.get("prompt_review")
        if isinstance(prompt_review, dict):
            reviewer += _usage_total(prompt_review.get("usage"))
        for item in probe.get("observations", []):
            if not isinstance(item, dict):
                continue
            student += _usage_total(item.get("usage"))
            review = item.get("review")
            if isinstance(review, dict):
                reviewer += _usage_total(review.get("usage"))
    return {
        "student_tokens": student,
        "reviewer_tokens": reviewer,
        "total_tokens": student + reviewer,
    }


def _aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [item for item in results if item["status"] == "completed"]
    role_tokens = sum(_usage_total(item.get("usage")) for item in results)
    nested_tokens = sum(
        int(item["nested_usage"]["total_tokens"]) for item in results
    )
    return {
        "runs": len(results),
        "completed": len(completed),
        "ready": sum(
            1
            for item in completed
            if isinstance(item.get("output"), dict)
            and item["output"].get("outcome") == "ready"
        ),
        "role_tokens": role_tokens,
        "nested_tokens": nested_tokens,
        "total_tokens": role_tokens + nested_tokens,
    }


def _usage_total(value: object) -> int:
    if not isinstance(value, dict):
        return 0
    amount = value.get("total_tokens")
    return amount if isinstance(amount, int) and not isinstance(amount, bool) else 0


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: dict[str, Any]) -> Path:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path.resolve()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"JSON artifact must contain an object: {path}")
    return value


def _required_object(value: dict[str, Any], name: str) -> dict[str, Any]:
    item = value.get(name)
    if not isinstance(item, dict):
        raise TypeError(f"{name} must be an object")
    return dict(item)


if __name__ == "__main__":
    main()
