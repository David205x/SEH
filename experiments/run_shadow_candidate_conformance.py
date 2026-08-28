"""Replay one Shadow Compiler Candidate and run Shadow Conformance Review。"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

from search_harness.evolution.control.conformance_effects import (
    ConformanceEffects,
)
from search_harness.evolution.control.evaluation import (
    CandidateArtifact,
    LocalEvaluationBackend,
    LocalEvaluationConfig,
)
from search_harness.evolution.research.roles.contracts import (
    ShadowMechanismSpec,
)
from search_harness.evolution.research.roles.native_chat_runner import (
    NativeChatRoleRunner,
)
from search_harness.evolution.versioning import (
    FileEdit,
    TemplateVersionStore,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REVIEWER_TEMPLATE_ROOT = (
    PROJECT_ROOT
    / "harness_templates"
    / "teacher"
    / "shadow_conformance_reviewer"
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--distiller-artifact", type=Path, required=True)
    parser.add_argument("--compiler-artifact", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    return parser.parse_args(argv)


async def run(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    source_run_dir = args.source_run.resolve()
    distiller_path = args.distiller_artifact.resolve()
    compiler_path = args.compiler_artifact.resolve()
    env_file = args.env_file.resolve()

    source_run = _read_json(source_run_dir / "run.json")
    distiller = _read_json(distiller_path)
    compiler = _read_json(compiler_path)
    mechanism = _shadow_mechanism(distiller)
    trial_files = _trial_files(distiller)
    candidate = _compiler_candidate(compiler)
    parent_template_root = _parent_template_root(compiler)
    experience_file = _experience_file(source_run, source_run_dir)
    effects_config = _required_object(source_run, "effects_config")

    source_hashes = {
        str(path): _sha256(path)
        for path in (
            source_run_dir / "run.json",
            experience_file,
            distiller_path,
            compiler_path,
            *trial_files,
        )
    }
    store = TemplateVersionStore(output_dir / "version_store")
    baseline = store.initialize(
        parent_template_root,
        summary="Initialize isolated Shadow Conformance baseline",
        env_file=env_file,
        version_store_id="shadow_conformance_debug",
    )
    attempt = store.start_candidate_attempt(
        parent_version=baseline.version_id,
        metadata={
            "source": "shadow_conformance_debug",
            "compiler_artifact": str(compiler_path),
        },
    )
    changed_files = _required_object(candidate, "changed_files")
    attempt.apply_patch(
        FileEdit(
            operation="delete" if content is None else "write",
            path=path,
            content=content,
        )
        for path, content in changed_files.items()
    )
    expected_digest = _required_string(candidate, "candidate_digest")
    if attempt.digest != expected_digest:
        raise ValueError(
            "Staged Candidate digest differs from Compiler Artifact: "
            f"{attempt.digest} != {expected_digest}"
        )
    validation = attempt.validate(env_file=env_file)
    if not validation.passed:
        raise ValueError(
            "Staged Shadow Candidate failed validation: "
            + "; ".join(validation.errors)
        )

    backend = LocalEvaluationBackend(
        store=store,
        config=LocalEvaluationConfig(
            env_file=env_file,
            student_max_steps=int(effects_config["student_max_steps"]),
            rollout_workers=int(effects_config["rollout_workers"]),
            rollouts_per_example=int(
                effects_config["rollouts_per_example"]
            ),
            judge_workers=int(effects_config["judge_workers"]),
            teacher_judge=bool(effects_config["teacher_judge"]),
            show_progress=bool(effects_config["show_progress"]),
            candidate_error_streak_limit=int(
                effects_config["candidate_error_streak_limit"]
            ),
        ),
    )
    candidate_artifact = CandidateArtifact(
        candidate_attempt_id=attempt.candidate_attempt_id,
        parent_version=baseline.version_id,
        candidate_digest=attempt.digest,
        compiler_log=compiler_path,
        summary=str(candidate.get("summary") or "Shadow Compiler Candidate"),
        validation_passed=True,
        validation=_validation_dict(validation),
    )
    result = await ConformanceEffects(
        backend=backend,
        role_runner=NativeChatRoleRunner(env_file=env_file),
        experience_file=experience_file,
        reviewer_template_root=REVIEWER_TEMPLATE_ROOT,
        judge_workers=int(effects_config["judge_workers"]),
        reviewer_role_id="shadow_conformance_reviewer",
        reviewer_role_version=1,
    ).verify(
        mechanism=mechanism,
        trial_files=trial_files,
        candidate=candidate_artifact,
        work_dir=output_dir / "conformance" / "verify",
    )

    if any(
        not Path(path).is_file() or _sha256(Path(path)) != digest
        for path, digest in source_hashes.items()
    ):
        raise RuntimeError("Shadow Conformance changed an upstream Artifact")
    summary = {
        "schema_version": 1,
        "source_run": str(source_run_dir),
        "distiller_artifact": str(distiller_path),
        "compiler_artifact": str(compiler_path),
        "parent_template_root": str(parent_template_root),
        "experience_file": str(experience_file),
        "trial_files": [str(path) for path in trial_files],
        "source_hashes_preserved": True,
        "candidate": {
            "candidate_attempt_id": attempt.candidate_attempt_id,
            "candidate_digest": attempt.digest,
            "validation": _validation_dict(validation),
        },
        "conformance": {
            "outcome": result.outcome,
            "artifact_refs": result.artifact_refs,
            "usage": result.usage,
        },
    }
    summary_path = _write_json(output_dir / "summary.json", summary)
    return {
        "status": "completed",
        "decision": result.outcome.get("decision"),
        "summary": str(summary_path),
    }


def _shadow_mechanism(artifact: dict[str, Any]) -> ShadowMechanismSpec:
    output = _required_object(artifact, "output")
    mechanism = output.get("mechanism")
    if not isinstance(mechanism, dict):
        raise TypeError("Shadow Distiller Artifact has no mechanism")
    return ShadowMechanismSpec.model_validate(mechanism)


def _trial_files(artifact: dict[str, Any]) -> list[Path]:
    resource_config = _required_object(artifact, "resource_config")
    values = resource_config.get("trial_files")
    if not isinstance(values, list) or not values:
        raise TypeError("Shadow Distiller Artifact has no trial_files")
    paths = [Path(str(value)).resolve() for value in values]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Shadow trial files are missing: {missing}")
    return paths


def _compiler_candidate(artifact: dict[str, Any]) -> dict[str, Any]:
    resources = artifact.get("resource_artifacts")
    if isinstance(resources, dict):
        candidate = resources.get("compiler_candidate")
        if isinstance(candidate, dict):
            return dict(candidate)
    if isinstance(artifact.get("changed_files"), dict):
        return dict(artifact)
    raise TypeError("Compiler Artifact has no submitted Candidate")


def _parent_template_root(artifact: dict[str, Any]) -> Path:
    resource_config = _required_object(artifact, "resource_config")
    compiler = _required_object(resource_config, "compiler")
    value = compiler.get("parent_template_root")
    if not isinstance(value, str) or not value.strip():
        raise TypeError("Compiler Artifact lacks parent_template_root")
    path = Path(value).resolve()
    if not path.is_dir():
        raise FileNotFoundError(f"Parent Template is missing: {path}")
    return path


def _experience_file(
    source_run: dict[str, Any],
    source_run_dir: Path,
) -> Path:
    effects = _required_object(source_run, "effects_config")
    value = effects.get("experience_file")
    path = (
        Path(value).resolve()
        if isinstance(value, str) and value.strip()
        else (source_run_dir / "experience_set.jsonl").resolve()
    )
    if not path.is_file():
        raise FileNotFoundError(f"Experience Set is missing: {path}")
    return path


def _validation_dict(report: Any) -> dict[str, Any]:
    return {
        "passed": report.passed,
        "parent_version": report.parent_version,
        "revision": report.revision,
        "candidate_digest": report.candidate_digest,
        "added_paths": list(report.added_paths),
        "modified_paths": list(report.modified_paths),
        "removed_paths": list(report.removed_paths),
        "errors": list(report.errors),
    }


def _required_object(value: dict[str, Any], name: str) -> dict[str, Any]:
    item = value.get(name)
    if not isinstance(item, dict):
        raise TypeError(f"Artifact field {name} must be an object")
    return dict(item)


def _required_string(value: dict[str, Any], name: str) -> str:
    item = value.get(name)
    if not isinstance(item, str) or not item.strip():
        raise TypeError(f"Artifact field {name} must be a string")
    return item


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"JSON Artifact must be an object: {path}")
    return value


def _write_json(path: Path, value: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path.resolve()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    result = asyncio.run(run(parse_args()))
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
