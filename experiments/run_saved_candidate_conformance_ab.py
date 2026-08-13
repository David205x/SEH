"""Stage saved Compiler candidates and replay one historical conformance set."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any, Sequence

from search_harness.evolution.control.candidate_version_effects import (
    CandidateVersionEffects,
)
from search_harness.evolution.control.conformance_effects import ConformanceEffects
from search_harness.evolution.control.effects import (
    LocalControlEffects,
    LocalControlEffectsConfig,
)
from search_harness.evolution.control.evaluation import CandidateArtifact
from search_harness.evolution.research.roles.contracts import MechanismSpec
from search_harness.evolution.versioning import TemplateVersionStore


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--source-compiler", type=Path, required=True)
    parser.add_argument("--candidate", action="append", type=Path, required=True)
    parser.add_argument("--label", action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    return parser.parse_args(argv)


async def run(args: argparse.Namespace) -> dict[str, Any]:
    if len(args.candidate) != len(args.label):
        raise ValueError("--candidate and --label counts must match")
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    source_run = _read_json(args.source_run / "run.json")
    source_compiler = _read_json(args.source_compiler)
    mechanism = MechanismSpec.model_validate(source_compiler["input"]["mechanism"])
    trial_files = [
        Path(path) for path in source_compiler["resource_config"]["trial_files"]
    ]
    if not trial_files:
        trial_files = _trial_files_from_journal(
            args.source_run / "events.jsonl",
            args.source_compiler.parent.name,
        )
    source_store = TemplateVersionStore(Path(source_run["version_store"]))
    records = []
    for label, artifact_path in zip(args.label, args.candidate, strict=True):
        records.append(
            await _run_one(
                label=label,
                artifact_path=artifact_path,
                source_run=source_run,
                source_store=source_store,
                mechanism=mechanism,
                trial_files=trial_files,
                output_dir=output_dir / label,
                env_file=args.env_file,
                experience_file=args.source_run / "experience_set.jsonl",
            )
        )
    summary = {
        "schema_version": 1,
        "mechanism_goal": mechanism.goal,
        "trial_count": len(trial_files),
        "records": records,
    }
    _write_json(output_dir / "summary.json", summary)
    return summary


async def _run_one(
    *,
    label: str,
    artifact_path: Path,
    source_run: dict[str, Any],
    source_store: TemplateVersionStore,
    mechanism: MechanismSpec,
    trial_files: list[Path],
    output_dir: Path,
    env_file: Path,
    experience_file: Path,
) -> dict[str, Any]:
    source = _read_json(artifact_path)
    candidate = source.get("resource_artifacts", {}).get("compiler_candidate")
    if not isinstance(candidate, dict):
        raise ValueError(f"saved Compiler artifact has no candidate: {artifact_path}")
    store = TemplateVersionStore(output_dir / "version_store")
    baseline = store.initialize(
        source_store.template_dir,
        summary=f"Initialize isolated conformance A/B store for {label}",
        env_file=env_file,
        version_store_id=f"compiler_conformance_{label}",
    )
    staged = CandidateVersionEffects(store=store, env_file=env_file).stage(
        candidate=candidate,
        parent_version=baseline.version_id,
        work_dir=output_dir / "stage_candidate",
    )
    if staged.outcome.get("status") != "valid":
        raise RuntimeError(f"{label} candidate did not stage: {staged.outcome}")

    effects_config = source_run["effects_config"]
    effects = LocalControlEffects(
        store=store,
        config=LocalControlEffectsConfig(
            experience_file=experience_file,
            env_file=env_file,
            student_max_steps=int(effects_config["student_max_steps"]),
            teacher_max_turns=int(effects_config["teacher_max_turns"]),
            rollout_workers=int(effects_config["rollout_workers"]),
            rollouts_per_example=int(effects_config["rollouts_per_example"]),
            judge_workers=int(effects_config["judge_workers"]),
            teacher_judge=bool(effects_config["teacher_judge"]),
            show_progress=True,
            candidate_error_streak_limit=int(
                effects_config["candidate_error_streak_limit"]
            ),
        ),
    )
    candidate_artifact = CandidateArtifact(
        candidate_attempt_id=str(staged.outcome["candidate_attempt_id"]),
        parent_version=baseline.version_id,
        candidate_digest=str(staged.outcome["candidate_digest"]),
        compiler_log=artifact_path.resolve(),
        summary=str(candidate.get("summary", label)),
        validation_passed=True,
        validation=dict(staged.outcome["validation"]),
    )
    result = await ConformanceEffects(
        backend=effects.backend,
        role_runner=effects.role_runner,
        experience_file=experience_file,
        reviewer_template_root=Path("harness_templates/teacher/conformance_reviewer"),
        judge_workers=int(effects_config["judge_workers"]),
    ).verify(
        mechanism=mechanism,
        trial_files=trial_files,
        candidate=candidate_artifact,
        work_dir=output_dir / "conformance" / "verify",
    )
    record = {
        "label": label,
        "compiler_artifact": str(artifact_path.resolve()),
        "stage": staged.outcome,
        "conformance": {
            "outcome": result.outcome,
            "usage": result.usage,
            "artifact_refs": result.artifact_refs,
        },
    }
    _write_json(output_dir / "result.json", record)
    return record


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def _trial_files_from_journal(events_file: Path, work_id: str) -> list[Path]:
    for line in events_file.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        payload = event.get("payload") if isinstance(event, dict) else None
        work = payload.get("work") if isinstance(payload, dict) else None
        if not isinstance(work, dict) or work.get("work_id") != work_id:
            continue
        refs = work.get("input_refs")
        refs = refs if isinstance(refs, dict) else {}
        trials = [
            Path(path)
            for key, path in sorted(refs.items())
            if str(key).startswith("trial_")
            and not str(key).endswith("_artifact")
            and isinstance(path, str)
        ]
        if trials:
            return trials
    raise ValueError(f"no intervention trials found for work {work_id}")


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    summary = asyncio.run(run(parse_args()))
    for record in summary["records"]:
        print(
            f"{record['label']}: "
            f"{record['conformance']['outcome'].get('decision')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
