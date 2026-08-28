"""Run frozen TASK-007 attribution cases through the real Teacher API."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from search_harness.evolution.research.experience_summary import (  # noqa: E402
    MAX_EVIDENCE_TOOL_CALLS,
    build_experience_summary_request,
)
from search_harness.evolution.research.resources.base import (  # noqa: E402
    TeacherResourceConfig,
)
from search_harness.evolution.research.roles.native_chat_runner import (  # noqa: E402
    NativeChatRoleRunner,
    TeacherRoleRunFailed,
)
from search_harness.evolution.research.roles.role_execution import (  # noqa: E402
    prepare_role_run,
)
from search_harness.integrations.openai_compatible import (  # noqa: E402
    OpenAICompatibleConfig,
)
from cvpr_workspace.analysis.task_007_artifact_input_projection import (  # noqa: E402
    project_artifact_input,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cases",
        type=Path,
        default=PROJECT_ROOT
        / "cvpr_workspace"
        / "configs"
        / "task_007_attribution_cases_v2.json",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--selection", type=Path)
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> None:
    if args.concurrency < 1 or args.concurrency > 4:
        raise ValueError("concurrency must be between one and four")
    suite = _read_json(args.cases.resolve())
    cases = _validated_cases(suite)
    repetitions = _selected_repetitions(
        cases,
        args.selection.resolve() if args.selection is not None else None,
    )
    output_dir = args.output_dir.resolve()

    template_root = PROJECT_ROOT / _required_string(suite, "template_root")
    role_id = _required_string(suite, "role_id")
    role_version = _required_int(suite, "role_version")
    base_config = OpenAICompatibleConfig.from_env(
        env_file=args.env_file.resolve(),
        prefix="TEACHER",
    )
    model_config = replace(base_config, max_tokens=4096)
    if args.validate_only:
        for case in cases:
            if _required_string(case, "case_id") not in repetitions:
                continue
            request, _ = _build_request(case)
            prepare_role_run(
                template_root=template_root,
                role_id=role_id,
                role_version=role_version,
                role_input=request.role_input.model_dump(mode="json"),
                resource_config=TeacherResourceConfig(
                    experience_summary=request.resources
                ),
            )
        print(
            json.dumps(
                {
                    "status": "valid",
                    "case_count": len(repetitions),
                    "run_count": sum(repetitions.values()),
                    "external_api_called": False,
                },
                ensure_ascii=False,
            )
        )
        return
    output_dir.mkdir(parents=True, exist_ok=False)
    semaphore = asyncio.Semaphore(args.concurrency)
    jobs = [
        (case, repetition)
        for case in cases
        if _required_string(case, "case_id") in repetitions
        for repetition in range(
            1,
            repetitions[_required_string(case, "case_id")] + 1,
        )
    ]

    _write_json(
        output_dir / "execution_context.json",
        {
            "suite_id": _required_string(suite, "suite_id"),
            "case_file": str(args.cases.resolve()),
            "selection_file": (
                str(args.selection.resolve())
                if args.selection is not None
                else None
            ),
            "template_root": str(template_root.resolve()),
            "role_id": role_id,
            "role_version": role_version,
            "model": model_config.provenance(),
            "max_tokens": model_config.max_tokens,
            "max_turns": MAX_EVIDENCE_TOOL_CALLS + 2,
            "concurrency": args.concurrency,
            "job_count": len(jobs),
        },
    )

    async def invoke(case: dict[str, Any], repetition: int) -> dict[str, Any]:
        case_id = _required_string(case, "case_id")
        request, projection = _build_request(case)
        artifact_path = output_dir / "runs" / case_id / f"run_{repetition:02d}.json"
        projection_path = (
            output_dir
            / "runs"
            / case_id
            / f"run_{repetition:02d}_input_projection.json"
        )
        _write_json(
            projection_path,
            {
                "case_id": case_id,
                "repetition": repetition,
                "role_input": request.role_input.model_dump(mode="json"),
                "artifact_projection": projection.audit,
            },
        )
        async with semaphore:
            try:
                artifact = await NativeChatRoleRunner(
                    env_file=args.env_file.resolve(),
                    max_turns=MAX_EVIDENCE_TOOL_CALLS + 2,
                    config=model_config,
                ).run(
                    template_root=template_root,
                    role_id=role_id,
                    role_version=role_version,
                    role_input=request.role_input.model_dump(mode="json"),
                    resource_config=TeacherResourceConfig(
                        experience_summary=request.resources
                    ),
                )
            except TeacherRoleRunFailed as exc:
                artifact = exc.failure_artifact
            except Exception as exc:  # Preserve provider/runtime failures.
                artifact = {
                    "status": "failed",
                    "error": {
                        "type": type(exc).__name__,
                        "message": str(exc),
                    },
                }
        _write_json(artifact_path, artifact)
        return {
            "case_id": case_id,
            "repetition": repetition,
            "status": artifact.get("status", "completed"),
            "artifact": str(artifact_path.resolve()),
            "input_projection": str(projection_path.resolve()),
            "output": artifact.get("output"),
            "tool_calls": artifact.get("tool_calls", []),
            "usage": artifact.get("usage", {}),
            "error": artifact.get("error"),
        }

    results = await asyncio.gather(*(invoke(case, rep) for case, rep in jobs))
    _write_json(
        output_dir / "summary.json",
        {
            "suite_id": _required_string(suite, "suite_id"),
            "case_count": len(repetitions),
            "run_count": len(results),
            "results": results,
        },
    )


def _validated_cases(suite: dict[str, Any]) -> list[dict[str, Any]]:
    if suite.get("schema_version") != 2:
        raise ValueError("unsupported attribution suite schema_version")
    raw_cases = suite.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise TypeError("attribution suite cases must be a non-empty list")
    cases: list[dict[str, Any]] = []
    ids: set[str] = set()
    for raw_case in raw_cases:
        if not isinstance(raw_case, dict):
            raise TypeError("attribution case must be an object")
        case_id = _required_string(raw_case, "case_id")
        if case_id in ids:
            raise ValueError(f"duplicate attribution case_id: {case_id}")
        ids.add(case_id)
        _required_object(raw_case, "sources")
        _required_object(raw_case, "projection")
        _required_object(raw_case, "rubric")
        _required_int(raw_case, "repetitions")
        _build_request(raw_case)
        cases.append(raw_case)
    return cases


def _selected_repetitions(
    cases: list[dict[str, Any]],
    selection_file: Path | None,
) -> dict[str, int]:
    available = {_required_string(case, "case_id"): case for case in cases}
    if selection_file is None:
        return {
            case_id: _required_int(case, "repetitions")
            for case_id, case in available.items()
        }
    selection = _read_json(selection_file)
    if selection.get("schema_version") != 1:
        raise ValueError("unsupported attribution selection schema_version")
    raw = _required_object(selection, "repetitions")
    selected: dict[str, int] = {}
    for case_id, repetitions in raw.items():
        if case_id not in available:
            raise ValueError(f"selection references unknown case: {case_id}")
        if (
            not isinstance(repetitions, int)
            or isinstance(repetitions, bool)
            or repetitions < 1
        ):
            raise TypeError(f"selection repetition must be positive: {case_id}")
        selected[case_id] = repetitions
    if not selected:
        raise ValueError("attribution selection must not be empty")
    return selected


def _build_request(case: dict[str, Any]):
    projection = project_artifact_input(
        project_root=PROJECT_ROOT,
        case=case,
    )
    request = build_experience_summary_request(
        trigger=case["trigger"],
        direction=projection.direction,
        attempt=projection.attempt,
        evidence=projection.evidence,
        evidence_views=projection.evidence_views,
        evidence_prompt_variants=projection.evidence_prompt_variants,
        source_context=_required_object(case, "source_context"),
    )
    return request, projection


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"JSON file must contain an object: {path}")
    return value


def _required_string(value: dict[str, Any], field: str) -> str:
    item = value.get(field)
    if not isinstance(item, str) or not item.strip():
        raise TypeError(f"{field} must be a non-empty string")
    return item


def _required_int(value: dict[str, Any], field: str) -> int:
    item = value.get(field)
    if not isinstance(item, int) or isinstance(item, bool) or item < 1:
        raise TypeError(f"{field} must be a positive integer")
    return item


def _required_object(value: dict[str, Any], field: str) -> dict[str, Any]:
    item = value.get(field)
    if not isinstance(item, dict):
        raise TypeError(f"{field} must be an object")
    return item


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    asyncio.run(_run(_parse_args()))


if __name__ == "__main__":
    main()
