"""Replay changed Teacher Roles on existing Candidate artifacts with real API."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from search_harness.evolution.research.candidate_digest import (
    build_candidate_outcome_digest,
    write_candidate_outcome_digest,
)
from search_harness.evolution.research.resources.base import TeacherResourceConfig
from search_harness.evolution.research.resources.stores import (
    CandidateComparisonStore,
    CandidateReviewResourceConfig,
)
from search_harness.evolution.research.roles.native_chat_runner import (
    NativeChatRoleRunner,
    TeacherRoleRunFailed,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEACHER_ROOT = PROJECT_ROOT / "harness_templates" / "teacher"


async def run(args: argparse.Namespace) -> dict[str, Any]:
    """Run every affected semantic Role repeatedly on one frozen evidence set."""

    run_dir = args.run_dir.resolve()
    artifacts = run_dir / "artifacts"
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    incumbent = _only_dir(artifacts, "evaluate_incumbent-")
    candidate = _choose_dir(artifacts, args.candidate_work_id)
    review = _choose_dir(artifacts, args.review_work_id)
    old_review = _read_json(review / "role.json")
    old_review_input = _object(old_review, "input")
    mechanism = _object(old_review_input, "mechanism")
    compiler_path = Path(
        _object(old_review, "resource_config").get(
            "compiler_artifact_file",
            "",
        )
    )
    if not compiler_path.is_file():
        compiler_path = _compiler_from_events(
            run_dir,
            args.review_work_id,
        )
    compiler = _read_json(compiler_path)
    implementation = str(
        _object(compiler, "output").get("implementation_summary") or
        old_review_input.get("implementation_summary") or
        "unavailable"
    )
    comparison = CandidateReviewResourceConfig(
        incumbent_report_dir=incumbent / "report",
        candidate_report_dir=candidate / "report",
        incumbent_rollout_file=incumbent / "report_rollouts.jsonl",
        candidate_rollout_file=candidate / "report_rollouts.jsonl",
        incumbent_template_root=run_dir / "version_store" / "template",
        outcome_digest_file=output_dir / "candidate_outcome_digest.json",
        compiler_artifact_file=compiler_path,
    )
    digest = build_candidate_outcome_digest(
        store=CandidateComparisonStore.load(comparison),
        mechanism=mechanism,
        implementation_summary=implementation,
    )
    write_candidate_outcome_digest(comparison.outcome_digest_file, digest)

    post_reject_analyst = _latest_role_artifact(
        artifacts,
        "analyze_failure-",
    )
    problem_direction = _object(post_reject_analyst, "output")
    analyst_focus = (
        "Reassess the incumbent evidence for the bounded behavior pattern; "
        "one rejected solution does not invalidate the problem direction. "
        "Use the recent Candidate evidence to refine scope only when needed."
    )
    recent_resource = TeacherResourceConfig(
        report_dir=incumbent / "report",
        rollout_file=incumbent / "report_rollouts.jsonl",
        student_template_root=run_dir / "version_store" / "template",
        candidate_review=comparison,
    )
    runner = NativeChatRoleRunner(env_file=args.env_file.resolve())
    jobs = {
        "failure_analyst": (
            {"analysis_focus": analyst_focus},
            recent_resource,
        ),
        "hypothesis_researcher": (
            {"problem_direction": problem_direction},
            recent_resource,
        ),
        "candidate_reviewer": (
            {
                **old_review_input,
                "mechanism": mechanism,
                "candidate_outcome_digest": digest,
            },
            TeacherResourceConfig(candidate_review=comparison),
        ),
    }
    distiller = _latest_role_artifact(artifacts, "distill_mechanism-")
    distiller_config = _object(distiller, "resource_config")
    jobs["mechanism_distiller"] = (
        _object(distiller, "input"),
        TeacherResourceConfig.model_validate(
            {
                **distiller_config,
                "hook_probe_env_file": str(args.env_file.resolve()),
            }
        ),
    )
    batch = _first_conformance_batch(artifacts)
    jobs["conformance_reviewer"] = (
        _object(_object(batch, "role_artifact"), "input"),
        TeacherResourceConfig(),
    )

    summaries: dict[str, list[dict[str, Any]]] = {}
    for role_id, (role_input, resource_config) in jobs.items():
        summaries[role_id] = []
        for index in range(1, args.repetitions + 1):
            try:
                artifact = await runner.run(
                    template_root=TEACHER_ROOT / role_id,
                    role_id=role_id,
                    role_version=1,
                    role_input=role_input,
                    resource_config=resource_config,
                )
                status = "completed"
            except TeacherRoleRunFailed as exc:
                artifact = exc.failure_artifact
                status = "failed"
            path = _write_json(
                output_dir / role_id / f"run_{index:03d}.json",
                artifact,
            )
            summaries[role_id].append(
                {
                    "status": status,
                    "artifact": str(path),
                    "output": artifact.get("output"),
                    "tool_names": [
                        item.get("name")
                        for item in artifact.get("tool_calls", [])
                        if isinstance(item, dict)
                    ],
                    "total_tokens": _total_tokens(artifact),
                }
            )
    summary = {
        "schema_version": 1,
        "source_run": str(run_dir),
        "candidate_work_id": args.candidate_work_id,
        "effect_digest": digest,
        "roles": summaries,
    }
    _write_json(output_dir / "summary.json", summary)
    return summary


def _only_dir(root: Path, prefix: str) -> Path:
    matches = sorted(path for path in root.iterdir() if path.name.startswith(prefix))
    if len(matches) != 1:
        raise ValueError(f"expected one {prefix} directory, got {len(matches)}")
    return matches[0]


def _choose_dir(root: Path, work_id: str) -> Path:
    path = root / work_id
    if not path.is_dir():
        raise FileNotFoundError(path)
    return path


def _latest_role_artifact(root: Path, prefix: str) -> dict[str, Any]:
    matches = sorted(
        (path / "role.json" for path in root.iterdir() if path.name.startswith(prefix)),
        key=lambda path: path.stat().st_mtime,
    )
    if not matches:
        raise FileNotFoundError(f"no {prefix} role artifact")
    return _read_json(matches[-1])


def _first_conformance_batch(root: Path) -> dict[str, Any]:
    matches = sorted(root.glob("conformance_checkpoints/*/batches/batch_*.json"))
    if not matches:
        raise FileNotFoundError("no Conformance batch artifact")
    return _read_json(matches[0])


def _compiler_from_events(run_dir: Path, review_work_id: str) -> Path:
    for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        payload = event.get("payload")
        work = payload.get("work") if isinstance(payload, dict) else None
        if isinstance(work, dict) and work.get("work_id") == review_work_id:
            refs = work.get("input_refs")
            value = refs.get("compiler_artifact") if isinstance(refs, dict) else None
            if isinstance(value, str):
                return Path(value)
    raise FileNotFoundError(f"compiler ref for {review_work_id}")


def _object(value: dict[str, Any], name: str) -> dict[str, Any]:
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


def _total_tokens(artifact: dict[str, Any]) -> int:
    usage = artifact.get("usage")
    value = usage.get("total_tokens") if isinstance(usage, dict) else 0
    return int(value) if isinstance(value, int) else 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("candidate_work_id")
    parser.add_argument("review_work_id")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=3)
    args = parser.parse_args()
    summary = asyncio.run(run(args))
    print(
        json.dumps(
            {
                "status": "completed",
                "role_count": len(summary["roles"]),
                "output_dir": str(args.output_dir.resolve()),
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
