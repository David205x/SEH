"""Run one real-API Compiler continuation followed by Conformance Review."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path
from typing import Any, Sequence

from search_harness.evolution.control.candidate_version_effects import (
    CandidateVersionEffects,
)
from search_harness.evolution.control.conformance_effects import (
    ConformanceEffects,
)
from search_harness.evolution.control.effects import (
    LocalControlEffects,
    LocalControlEffectsConfig,
)
from search_harness.evolution.control.evaluation import CandidateArtifact
from search_harness.evolution.control.research_role_effects import (
    ResearchRoleEffects,
)
from search_harness.evolution.research.roles.contracts import (
    CompilerResult,
    MechanismSpec,
)
from search_harness.evolution.research.roles.native_chat_runner import (
    NativeChatRoleRunner,
)
from search_harness.evolution.versioning import TemplateVersionStore


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--source-compiler", type=Path, required=True)
    parser.add_argument("--source-conformance", type=Path, required=True)
    parser.add_argument("--mechanism-file", type=Path, required=True)
    parser.add_argument("--trial-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    return parser.parse_args(argv)


async def run_probe(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    source_run = _read_json(args.source_run / "run.json")
    source_compiler = _read_json(args.source_compiler)
    source_conformance = _read_json(args.source_conformance)
    mechanism = MechanismSpec.model_validate(_read_json(args.mechanism_file))

    candidate = _compiler_candidate(source_compiler)
    candidate.setdefault("queried_symbols", [])
    continuation_file = output_dir / "continuation_candidate.json"
    _write_json(continuation_file, candidate)
    feedback = _compiler_feedback(source_conformance)

    source_store = TemplateVersionStore(Path(source_run["version_store"]))
    compiler_dir = output_dir / "compiler"
    compiler_effect = await ResearchRoleEffects(
        role_runner=NativeChatRoleRunner(env_file=args.env_file),
        store=source_store,
        env_file=args.env_file,
        teacher_template_root=Path("harness_templates/teacher"),
    ).compile_candidate(
        mechanism=mechanism,
        student_model_experiments=[],
        implementation_constraints=feedback,
        validation_feedback=[],
        conformance_failures=_conformance_failures(source_conformance),
        continuation_candidate_file=continuation_file,
        work_dir=compiler_dir,
    )
    compiler_output = CompilerResult.model_validate(
        compiler_effect.outcome["output"]
    )
    compiled_candidate = _read_json(
        Path(compiler_effect.artifact_refs["compiler_candidate_file"])
    )

    isolated_store = TemplateVersionStore(output_dir / "version_store")
    baseline = isolated_store.initialize(
        source_store.template_dir,
        summary="Initialize isolated Compiler-Conformance probe",
        env_file=args.env_file,
        version_store_id="compiler_conformance_probe",
    )
    staged = CandidateVersionEffects(
        store=isolated_store,
        env_file=args.env_file,
    ).stage(
        candidate=compiled_candidate,
        parent_version=baseline.version_id,
        work_dir=output_dir / "stage_candidate",
    )
    if staged.outcome.get("status") != "valid":
        raise RuntimeError(f"Compiler Candidate did not validate: {staged.outcome}")

    source_effects = source_run["effects_config"]
    effects = LocalControlEffects(
        store=isolated_store,
        config=LocalControlEffectsConfig(
            experience_file=args.source_run / "experience_set.jsonl",
            env_file=args.env_file,
            student_max_steps=int(source_effects["student_max_steps"]),
            teacher_max_turns=int(source_effects["teacher_max_turns"]),
            rollout_workers=int(source_effects["rollout_workers"]),
            rollouts_per_example=int(source_effects["rollouts_per_example"]),
            judge_workers=int(source_effects["judge_workers"]),
            teacher_judge=bool(source_effects["teacher_judge"]),
            show_progress=True,
            candidate_error_streak_limit=int(
                source_effects["candidate_error_streak_limit"]
            ),
        ),
    )
    candidate_artifact = CandidateArtifact(
        candidate_attempt_id=str(staged.outcome["candidate_attempt_id"]),
        parent_version=baseline.version_id,
        candidate_digest=str(staged.outcome["candidate_digest"]),
        compiler_log=Path(compiler_effect.artifact_refs["compiler_artifact"]),
        summary=compiler_output.implementation_summary,
        validation_passed=True,
        validation=dict(staged.outcome["validation"]),
    )
    conformance = await ConformanceEffects(
        backend=effects.backend,
        role_runner=effects.role_runner,
        experience_file=args.source_run / "experience_set.jsonl",
        reviewer_template_root=Path(
            "harness_templates/teacher/conformance_reviewer"
        ),
        judge_workers=int(source_effects["judge_workers"]),
    ).verify(
        mechanism=mechanism,
        trial_files=[args.trial_file],
        candidate=candidate_artifact,
        work_dir=output_dir / "conformance" / "verify",
    )

    compiler_role = _read_json(
        Path(compiler_effect.artifact_refs["compiler_artifact"])
    )
    summary = {
        "compiler": {
            "output": compiler_effect.outcome["output"],
            "usage": compiler_role.get("usage"),
            "tool_counts": _tool_counts(compiler_role),
            "continuation": compiler_role.get("resource_config", {}).get(
                "compiler", {}
            ),
        },
        "stage_candidate": staged.outcome,
        "conformance": {
            "outcome": conformance.outcome,
            "usage": conformance.usage,
            "artifact_refs": conformance.artifact_refs,
        },
    }
    _write_json(output_dir / "summary.json", summary)
    return summary


def _compiler_candidate(artifact: dict[str, Any]) -> dict[str, Any]:
    resources = artifact.get("resource_artifacts")
    resources = resources if isinstance(resources, dict) else {}
    candidate = resources.get("compiler_candidate")
    if not isinstance(candidate, dict):
        raise ValueError("source Compiler artifact has no compiler_candidate")
    return dict(candidate)


def _compiler_feedback(effect: dict[str, Any]) -> list[str]:
    conformance = effect.get("conformance")
    conformance = conformance if isinstance(conformance, dict) else effect
    outcome = conformance.get("outcome")
    outcome = outcome if isinstance(outcome, dict) else {}
    summary = outcome.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    feedback = summary.get("compiler_feedback")
    if not isinstance(feedback, list) or not feedback:
        raise ValueError("source Conformance effect has no compiler feedback")
    return [str(item) for item in feedback]


def _conformance_failures(effect: dict[str, Any]) -> list[dict[str, Any]]:
    refs = effect.get("artifact_refs")
    refs = refs if isinstance(refs, dict) else {}
    failures = []
    for key, value in refs.items():
        if not str(key).startswith("conformance_finding_") or not isinstance(
            value,
            str,
        ):
            continue
        finding = _read_json(Path(value)).get("output")
        if not isinstance(finding, dict) or finding.get("verdict") == "faithful":
            continue
        failures.append(
            {
                name: finding.get(name)
                for name in (
                    "candidate_run_ref",
                    "verdict",
                    "assessment",
                    "repair_obligation",
                    "failure_layer",
                    "predicate_ref",
                    "expected_label",
                    "observed_label",
                    "decisive_input_summary",
                    "recommended_route",
                )
            }
        )
    return failures


def _tool_counts(artifact: dict[str, Any]) -> dict[str, int]:
    calls = artifact.get("tool_calls")
    calls = calls if isinstance(calls, list) else []
    return dict(
        Counter(
            str(call.get("name"))
            for call in calls
            if isinstance(call, dict) and call.get("name")
        )
    )


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"JSON artifact must be an object: {path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main(argv: Sequence[str] | None = None) -> None:
    summary = asyncio.run(run_probe(parse_args(argv)))
    print(
        "compiler-conformance probe completed: "
        f"compiler_tokens={summary['compiler']['usage']['total_tokens']}, "
        f"conformance_tokens={summary['conformance']['usage']['total_tokens']}, "
        f"decision={summary['conformance']['outcome']['decision']}"
    )


if __name__ == "__main__":
    main()
