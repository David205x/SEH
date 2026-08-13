"""Run offline and real-API probes for shadow Teacher query views."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

from experiments.teacher_query_views.judge import ShadowTeacherBinaryJudge
from experiments.teacher_query_views.views import (
    ShadowTrajectoryView,
    render_evaluation_case,
)
from search_harness.evaluation import EvaluationCase, HotpotQAEvaluator
from search_harness.evolution.research.resources.base import (
    EvaluationEvidenceStore,
    TeacherResourceConfig,
)
from search_harness.evolution.research.roles.native_chat_runner import (
    NativeChatRoleRunner,
    TeacherRoleRunFailed,
)
from search_harness.integrations.openai_compatible import OpenAICompatibleModel


_TEMPLATE_ROOT = (
    Path(__file__).resolve().parent / "teacher_query_views" / "templates"
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    offline = subparsers.add_parser("offline")
    offline.add_argument("--report-dir", type=Path, required=True)
    offline.add_argument("--rollout-file", type=Path, required=True)
    offline.add_argument("--student-template-root", type=Path, required=True)
    offline.add_argument("--hook-rollout-file", type=Path)
    offline.add_argument("--output-dir", type=Path, required=True)

    api = subparsers.add_parser("api")
    api.add_argument("--failure-artifact", type=Path, required=True)
    api.add_argument("--researcher-artifact", type=Path, required=True)
    api.add_argument("--output-dir", type=Path, required=True)
    api.add_argument("--env-file", type=Path, default=Path(".env"))
    api.add_argument("--repetitions", type=int, default=3)
    api.add_argument(
        "--only",
        choices=(
            "all",
            "failure_analyst",
            "hypothesis_researcher",
            "teacher_judge",
        ),
        default="all",
    )
    return parser.parse_args(argv)


def run_offline(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    source_hashes = {
        "report_summary": _digest(args.report_dir / "summary.json"),
        "evaluation_cases": _digest(args.report_dir / "per_example.jsonl"),
        "rollouts": _digest(args.rollout_file),
    }
    if args.hook_rollout_file is not None:
        source_hashes["hook_rollouts"] = _digest(args.hook_rollout_file)

    store = EvaluationEvidenceStore.load(
        report_dir=args.report_dir,
        rollout_file=args.rollout_file,
        student_template_root=args.student_template_root,
    )
    case_stats = []
    trajectory_stats = []
    sample_case: str | None = None
    sample_trajectory: str | None = None
    for example_id, case in store.cases.items():
        old_case = _compact_json(case)
        new_case = render_evaluation_case(case)
        case_stats.append((len(old_case), len(new_case)))
        if sample_case is None and case.get("stability") in {
            "stable_failure",
            "unstable",
        }:
            sample_case = new_case
        for replicate_id, record in store.rollouts.get(example_id, {}).items():
            old_trajectory = _compact_json(record)
            new_trajectory = ShadowTrajectoryView(
                record,
                case=case,
                replicate_id=replicate_id,
            ).render()
            trajectory_stats.append((len(old_trajectory), len(new_trajectory)))
            if sample_trajectory is None and case.get("stability") in {
                "stable_failure",
                "unstable",
            }:
                sample_trajectory = new_trajectory

    hook_summary = None
    if args.hook_rollout_file is not None:
        hook_record = _first_changed_hook_record(args.hook_rollout_file)
        if hook_record is not None:
            hook_view = ShadowTrajectoryView(hook_record).render()
            (output_dir / "hook_trajectory.txt").write_text(
                hook_view + "\n",
                encoding="utf-8",
            )
            hook_summary = {
                "old_characters": len(_compact_json(hook_record)),
                "new_characters": len(hook_view),
                "verified_change_present": (
                    '"delivery_status":"verified"' in hook_view
                ),
                "runtime_only_present": "RUNTIME_ONLY" in hook_view,
            }

    if sample_case is not None:
        (output_dir / "evaluation_case.txt").write_text(
            sample_case + "\n",
            encoding="utf-8",
        )
    if sample_trajectory is not None:
        (output_dir / "student_trajectory.txt").write_text(
            sample_trajectory + "\n",
            encoding="utf-8",
        )

    summary = {
        "schema_version": 1,
        "experiment": "teacher_query_views_v1",
        "case_outputs": _size_summary(case_stats),
        "trajectory_outputs": _size_summary(trajectory_stats),
        "hook_output": hook_summary,
        "checks": {
            "metadata_results_absent": all(
                '"results"' not in ShadowTrajectoryView(
                    record,
                    case=store.cases.get(example_id),
                    replicate_id=replicate_id,
                ).render()
                for example_id, by_replicate in store.rollouts.items()
                for replicate_id, record in by_replicate.items()
            ),
            "omitted_absent": all(
                '"omitted"' not in ShadowTrajectoryView(
                    record,
                    case=store.cases.get(example_id),
                    replicate_id=replicate_id,
                ).render()
                for example_id, by_replicate in store.rollouts.items()
                for replicate_id, record in by_replicate.items()
            ),
        },
        "source_hashes_before": source_hashes,
        "source_hashes_after": {
            "report_summary": _digest(args.report_dir / "summary.json"),
            "evaluation_cases": _digest(args.report_dir / "per_example.jsonl"),
            "rollouts": _digest(args.rollout_file),
            **(
                {"hook_rollouts": _digest(args.hook_rollout_file)}
                if args.hook_rollout_file is not None
                else {}
            ),
        },
    }
    summary["checks"]["source_artifacts_unchanged"] = (
        summary["source_hashes_before"] == summary["source_hashes_after"]
    )
    _write_json(output_dir / "summary.json", summary)
    return summary


async def run_api(args: argparse.Namespace) -> dict[str, Any]:
    if args.repetitions < 1:
        raise ValueError("repetitions must be positive")
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    failure_source = _read_json(args.failure_artifact)
    researcher_source = _read_json(args.researcher_artifact)

    failure_results = None
    if args.only in {"all", "failure_analyst"}:
        failure_results = await _run_role_repetitions(
            role_id="failure_analyst",
            source=failure_source,
            template_root=_TEMPLATE_ROOT / "failure_analyst",
            env_file=args.env_file,
            repetitions=args.repetitions,
            output_dir=output_dir / "failure_analyst",
        )
    researcher_results = None
    if args.only in {"all", "hypothesis_researcher"}:
        researcher_results = await _run_role_repetitions(
            role_id="hypothesis_researcher",
            source=researcher_source,
            template_root=_TEMPLATE_ROOT / "hypothesis_researcher",
            env_file=args.env_file,
            repetitions=args.repetitions,
            output_dir=output_dir / "hypothesis_researcher",
        )
    judgment_results = None
    if args.only in {"all", "teacher_judge"}:
        judgment_results = await _run_judge_repetitions(
            source=failure_source,
            env_file=args.env_file,
            repetitions=args.repetitions,
            output_dir=output_dir / "teacher_judge",
        )
    summary = {
        "schema_version": 1,
        "experiment": "teacher_query_views_v1",
        "failure_analyst": failure_results,
        "hypothesis_researcher": researcher_results,
        "teacher_judge": judgment_results,
    }
    _write_json(output_dir / "summary.json", summary)
    return summary


async def _run_role_repetitions(
    *,
    role_id: str,
    source: dict[str, Any],
    template_root: Path,
    env_file: Path,
    repetitions: int,
    output_dir: Path,
) -> list[dict[str, Any]]:
    role_input = _required_object(source, "input")
    resource_config = TeacherResourceConfig.model_validate(
        _required_object(source, "resource_config")
    )
    role = _required_object(source, "role")
    role_version = role.get("version", 1)
    if not isinstance(role_version, int):
        raise TypeError("source role version must be an integer")
    output_dir.mkdir(parents=True, exist_ok=True)

    async def invoke(index: int) -> dict[str, Any]:
        try:
            artifact = await NativeChatRoleRunner(env_file=env_file).run(
                template_root=template_root,
                role_input=role_input,
                resource_config=resource_config,
                role_id=role_id,
                role_version=role_version,
            )
        except TeacherRoleRunFailed as exc:
            artifact = exc.failure_artifact
        path = output_dir / f"role_{index:02d}.json"
        _write_json(path, artifact)
        return {
            "index": index,
            "status": artifact.get("status", "completed"),
            "output": artifact.get("output"),
            "usage": artifact.get("usage"),
            "artifact": str(path),
        }

    return await asyncio.gather(
        *(invoke(index) for index in range(1, repetitions + 1))
    )


async def _run_judge_repetitions(
    *,
    source: dict[str, Any],
    env_file: Path,
    repetitions: int,
    output_dir: Path,
) -> list[dict[str, Any]]:
    config = TeacherResourceConfig.model_validate(
        _required_object(source, "resource_config")
    )
    if config.report_dir is None:
        raise ValueError("Failure Analyst source has no Evaluation Report")
    store = EvaluationEvidenceStore.load(
        report_dir=config.report_dir,
        rollout_file=config.rollout_file,
        student_template_root=config.student_template_root,
    )
    case = _first_teacher_case(store)
    output_dir.mkdir(parents=True, exist_ok=True)

    async def invoke(index: int) -> dict[str, Any]:
        judge = ShadowTeacherBinaryJudge(
            OpenAICompatibleModel.from_env(env_file=env_file, prefix="TEACHER"),
            HotpotQAEvaluator(),
        )
        result = await asyncio.to_thread(judge.judge, case)
        payload = result.to_dict()
        path = output_dir / f"judgment_{index:02d}.json"
        _write_json(path, payload)
        return {
            "index": index,
            "status": "completed" if result.score is not None else "failed",
            "score": result.score,
            "assessment": result.assessment,
            "error": result.error,
            "artifact": str(path),
        }

    return await asyncio.gather(
        *(invoke(index) for index in range(1, repetitions + 1))
    )


def _first_teacher_case(store: EvaluationEvidenceStore) -> EvaluationCase:
    for case in store.cases.values():
        golden = case.get("golden_answer")
        question = case.get("question")
        for replicate in case.get("replicates", []):
            if not isinstance(replicate, dict):
                continue
            if replicate.get("score_source") != "teacher":
                continue
            return EvaluationCase(
                example_id=str(case.get("example_id")),
                question=str(question),
                golden_answer=golden if isinstance(golden, str) else None,
                predicted_answer=(
                    replicate.get("predicted_answer")
                    if isinstance(replicate.get("predicted_answer"), str)
                    else None
                ),
            )
    raise ValueError("Evaluation Report contains no Teacher-judged Replicate")


def _first_changed_hook_record(path: Path) -> dict[str, Any] | None:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            if not isinstance(record, dict):
                continue
            trace = record.get("run", {}).get("trace", [])
            if any(
                isinstance(event, dict)
                and event.get("event_type") == "hook_applied"
                and event.get("payload", {}).get("changes")
                for event in trace
            ):
                return record
    return None


def _size_summary(values: list[tuple[int, int]]) -> dict[str, Any]:
    old_total = sum(item[0] for item in values)
    new_total = sum(item[1] for item in values)
    return {
        "count": len(values),
        "old_characters": old_total,
        "new_characters": new_total,
        "new_to_old_ratio": (
            round(new_total / old_total, 4) if old_total else None
        ),
    }


def _required_object(value: dict[str, Any], key: str) -> dict[str, Any]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise TypeError(f"source artifact field '{key}' must be an object")
    return item


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


def _compact_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    if args.command == "offline":
        summary = run_offline(args)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return
    summary = asyncio.run(run_api(args))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
