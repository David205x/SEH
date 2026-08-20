"""Run one real-prefix Hook feasibility probe and repeated Teacher reviews."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from search_harness._internal import (
    evolution_effect_values,
    read_runtime_config,
    teacher_role_budget,
)
from search_harness.evolution.research.hook_feasibility import (
    HookFeasibilityProbeConfig,
    HookFeasibilityProbeExecutor,
    probe_total_tokens,
)
from search_harness.evolution.research.resources.base import (
    TeacherResourceConfig,
)
from search_harness.evolution.research.roles.contracts import (
    HookFeasibilityReview,
    MechanismSpec,
    TrialReview,
)
from search_harness.evolution.research.roles.native_chat_runner import (
    NativeChatRoleRunner,
    TeacherRoleRunFailed,
)
from search_harness.integrations.openai_compatible import (
    OpenAICompatibleConfig,
    ProfiledHookModelBackend,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REVIEWER_TEMPLATE = (
    PROJECT_ROOT
    / "harness_templates"
    / "teacher"
    / "hook_feasibility_reviewer"
)


async def run(args: argparse.Namespace) -> dict[str, Any]:
    """Materialize one Probe and repeated independent Reviewer artifacts."""

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    mechanism = MechanismSpec.model_validate(
        _read_json(args.mechanism_file)
    )
    distiller = _read_json(args.distiller_artifact)
    distiller_input = _required_object(distiller, "input")
    raw_reviews = distiller_input.get("trial_reviews")
    if not isinstance(raw_reviews, list) or not raw_reviews:
        raise TypeError("Distiller artifact lacks trial_reviews")
    reviews = [TrialReview.model_validate(item) for item in raw_reviews]
    trial_paths = _trial_paths(distiller)
    runtime = read_runtime_config(env_file=args.env_file)
    effects = evolution_effect_values(runtime)
    probe_config = HookFeasibilityProbeConfig(
        max_cases_per_phase=int(effects["hook_feasibility_max_cases"]),
        repetitions=int(effects["hook_feasibility_repetitions"]),
        thinking_modes=tuple(effects["hook_feasibility_thinking_modes"]),
    )
    probe = (
        _read_json(args.probe_file)
        if args.probe_file is not None
        else await asyncio.to_thread(
            HookFeasibilityProbeExecutor(
                backend=ProfiledHookModelBackend(env_file=args.env_file),
                config=probe_config,
            ).run,
            mechanism=mechanism,
            trial_paths=trial_paths,
            trial_reviews=reviews,
            rollout_file=args.rollout_file.resolve(),
        )
    )
    probe_path = _write_json(output_dir / "probe.json", probe)
    prior_experiments = _student_model_experiments(distiller)
    runner = _reviewer_runner(args=args, runtime=runtime)
    review_summaries = []
    for index in range(1, args.review_repetitions + 1):
        try:
            artifact = await runner.run(
                template_root=REVIEWER_TEMPLATE,
                role_id="hook_feasibility_reviewer",
                role_version=1,
                role_input={
                    "mechanism": mechanism.model_dump(mode="json"),
                    "probe_evidence": probe,
                    "prior_model_experiments": prior_experiments,
                },
                resource_config=TeacherResourceConfig(),
            )
        except TeacherRoleRunFailed as exc:
            artifact = exc.failure_artifact
            role_path = _write_json(
                output_dir / f"review_{index:03d}_failed.json",
                artifact,
            )
            review_summaries.append(
                {
                    "index": index,
                    "artifact": str(role_path),
                    "decision": "role_failure",
                    "error": str(exc),
                    "total_tokens": _artifact_total_tokens(artifact),
                }
            )
            continue
        output = HookFeasibilityReview.model_validate(artifact.get("output"))
        role_path = _write_json(
            output_dir / f"review_{index:03d}.json",
            artifact,
        )
        review_summaries.append(
            {
                "index": index,
                "artifact": str(role_path),
                "decision": output.decision,
                "phase_findings": [
                    finding.model_dump(mode="json")
                    for finding in output.phase_findings
                ],
                "assessment": output.assessment,
                "compiler_guidance": list(output.compiler_guidance),
                "revision_feedback": output.revision_feedback,
                "total_tokens": _artifact_total_tokens(artifact),
            }
        )
    summary = {
        "schema_version": 1,
        "mechanism_file": str(args.mechanism_file.resolve()),
        "distiller_artifact": str(args.distiller_artifact.resolve()),
        "rollout_file": str(args.rollout_file.resolve()),
        "probe_artifact": str(probe_path),
        "probe_total_tokens": probe_total_tokens(probe),
        "reviews": review_summaries,
    }
    _write_json(output_dir / "summary.json", summary)
    return summary


def _reviewer_runner(
    *,
    args: argparse.Namespace,
    runtime: dict[str, Any],
) -> NativeChatRoleRunner:
    if args.review_thinking_mode is None:
        return NativeChatRoleRunner(env_file=args.env_file)
    config = OpenAICompatibleConfig.from_env(
        env_file=args.env_file,
        prefix="TEACHER",
    )
    budget = teacher_role_budget(
        runtime,
        "hook_feasibility_reviewer",
        default_max_tokens=config.max_tokens,
        default_max_turns=15,
        default_thinking_mode=config.configured_thinking_mode,
    )
    config = replace(config, max_tokens=budget.max_tokens)
    config = config.with_configured_thinking_mode(
        args.review_thinking_mode
    )
    return NativeChatRoleRunner(
        env_file=args.env_file,
        max_turns=budget.max_turns,
        config=config,
    )


def _trial_paths(distiller: dict[str, Any]) -> list[Path]:
    resource_config = _required_object(distiller, "resource_config")
    raw = resource_config.get("trial_files")
    if not isinstance(raw, list) or not raw:
        raise TypeError("Distiller artifact lacks resource_config.trial_files")
    paths = [Path(value).resolve() for value in raw if isinstance(value, str)]
    if len(paths) != len(raw):
        raise TypeError("Distiller trial_files must contain only paths")
    return paths


def _student_model_experiments(
    distiller: dict[str, Any],
) -> list[dict[str, Any]]:
    resources = distiller.get("resource_artifacts")
    raw = (
        resources.get("student_model_experiments")
        if isinstance(resources, dict)
        else None
    )
    if not isinstance(raw, list):
        return []
    return [dict(item) for item in raw if isinstance(item, dict)]


def _artifact_total_tokens(artifact: dict[str, Any]) -> int:
    usage = artifact.get("usage")
    value = usage.get("total_tokens") if isinstance(usage, dict) else None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        return 0
    return value


def _required_object(value: dict[str, Any], name: str) -> dict[str, Any]:
    item = value.get(name)
    if not isinstance(item, dict):
        raise TypeError(f"{name} must be an object")
    return dict(item)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"JSON artifact must be an object: {path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path.resolve()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mechanism-file", type=Path, required=True)
    parser.add_argument("--distiller-artifact", type=Path, required=True)
    parser.add_argument("--rollout-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--probe-file", type=Path)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--review-repetitions", type=int, default=3)
    parser.add_argument(
        "--review-thinking-mode",
        choices=("enabled", "disabled"),
        help="Override Reviewer thinking for this A/B experiment only.",
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.review_repetitions < 1:
        raise ValueError("review_repetitions must be positive")
    summary = asyncio.run(run(args))
    print(
        json.dumps(
            {
                "probe_total_tokens": summary["probe_total_tokens"],
                "decisions": [
                    item["decision"] for item in summary["reviews"]
                ],
                "review_tokens": [
                    item["total_tokens"] for item in summary["reviews"]
                ],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
