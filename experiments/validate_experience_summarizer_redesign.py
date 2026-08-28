"""Validate split Experience Summarizers on existing typed artifacts."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from search_harness.evolution.research.experience_summary import (
    ExperienceSummaryRequest,
    build_conformance_capability_request,
    build_hook_feasibility_capability_request,
    build_promotion_direction_request,
    materialize_capability_experience_product,
)
from search_harness.evolution.research.resources.base import (
    TeacherResourceConfig,
)
from search_harness.evolution.research.roles.native_chat_runner import (
    NativeChatRoleRunner,
)
from search_harness.evolution.research.roles.contracts import (
    CapabilityExperienceSummary,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = PROJECT_ROOT / "harness_templates" / "teacher"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument(
        "--case",
        action="append",
        choices=(
            "hook_model_boundary",
            "conformance_boundary",
            "promotion_failed",
            "promotion_passed",
        ),
    )
    return parser.parse_args()


async def _run_one(
    *,
    runner: NativeChatRoleRunner,
    case_id: str,
    pass_name: str,
    request: ExperienceSummaryRequest,
    repetition: int,
    output_dir: Path,
) -> dict[str, Any]:
    role_id = f"{pass_name}_summarizer"
    target = output_dir / case_id / f"rep_{repetition:02d}"
    target.mkdir(parents=True, exist_ok=False)
    try:
        artifact = await runner.run(
            template_root=TEMPLATE_ROOT / role_id,
            role_id=role_id,
            role_version=(2 if role_id == "capability_summarizer" else 1),
            role_input=request.role_input.model_dump(mode="json"),
            resource_config=TeacherResourceConfig(
                experience_summary=request.resources
            ),
        )
        _write_json(target / "role.json", artifact)
        output = artifact["output"]
        if pass_name == "capability":
            product = materialize_capability_experience_product(
                request,
                CapabilityExperienceSummary.model_validate(output),
            )
            output = product.model_dump(mode="json")
            _write_json(target / "capability_experience.json", output)
        return {
            "case_id": case_id,
            "pass": pass_name,
            "repetition": repetition,
            "status": "completed",
            "output": output,
            "usage": artifact.get("usage", {}),
            "tool_calls": artifact.get("tool_calls", []),
        }
    except Exception as exc:
        failure = {
            "case_id": case_id,
            "pass": pass_name,
            "repetition": repetition,
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
        }
        artifact = getattr(exc, "failure_artifact", None)
        if isinstance(artifact, dict):
            _write_json(target / "role.failed.json", artifact)
            failure["usage"] = artifact.get("usage", {})
            failure["tool_calls"] = artifact.get("tool_calls", [])
        _write_json(target / "result.json", failure)
        return failure


async def _main() -> None:
    args = _parse_args()
    if args.repetitions < 1:
        raise ValueError("repetitions must be positive")
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    cases = _build_cases()
    if args.case:
        selected = set(args.case)
        cases = [item for item in cases if item[0] in selected]
    runner = NativeChatRoleRunner(env_file=args.env_file)
    results: list[dict[str, Any]] = []
    for case_id, pass_name, request in cases:
        batch = await asyncio.gather(
            *(
                _run_one(
                    runner=runner,
                    case_id=case_id,
                    pass_name=pass_name,
                    request=request,
                    repetition=index,
                    output_dir=output_dir,
                )
                for index in range(1, args.repetitions + 1)
            )
        )
        results.extend(batch)
        print(
            f"completed case={case_id} pass={pass_name} "
            f"runs={len(batch)}",
            flush=True,
        )
    report = _summarize(results)
    _write_json(output_dir / "summary.json", report)
    print(json.dumps(report["totals"], ensure_ascii=False), flush=True)


def _build_cases() -> list[tuple[str, str, ExperienceSummaryRequest]]:
    probe_path = (
        PROJECT_ROOT
        / "runs/evolution/20260815_qwen3-8b_hook_feasibility/artifacts"
        / "verify_hook_feasibility-64ddfe9a2a85e492/probe.json"
    )
    capability = build_hook_feasibility_capability_request(
        _read_json(probe_path),
        source_ref="hook_feasibility_probe",
    )
    if capability is None:
        raise ValueError("selected Hook feasibility source is not eligible")
    return [
        ("hook_model_boundary", "capability", capability),
        (
            "conformance_boundary",
            "capability",
            _conformance_capability_request(),
        ),
        (
            "promotion_failed",
            "direction",
            _promotion_request(sequence=49),
        ),
        (
            "promotion_passed",
            "direction",
            _promotion_request(sequence=119),
        ),
    ]


def _conformance_capability_request() -> ExperienceSummaryRequest:
    root = (
        PROJECT_ROOT
        / "runs/evolution/20260815_qwen3-8b_fullchain/artifacts"
        / "conformance_checkpoints/8ec0c86505430d20dd952e5f/findings"
    )
    findings = [
        _read_json(path)["output"]
        for path in sorted(root.glob("finding_*.json"))
    ]
    request = build_conformance_capability_request(
        findings,
        source_refs=["conformance_findings"],
        mechanism=_read_json(
            PROJECT_ROOT
            / "runs/evolution/20260815_qwen3-8b_fullchain/artifacts"
            / "distill_mechanism-17ff2d1e1dd24b63/mechanism.json"
        ),
    )
    if request is None:
        raise ValueError("selected Conformance source is not eligible")
    return request


def _promotion_request(sequence: int) -> ExperienceSummaryRequest:
    run_dir = PROJECT_ROOT / "runs/evolution/20260803"
    event = next(
        item
        for item in _read_jsonl(run_dir / "events.jsonl")
        if item.get("sequence") == sequence
    )
    work = event["payload"]["work"]
    refs = work["input_refs"]
    payload = work["payload"]
    failure = _read_json(Path(refs["failure_artifact"]))["output"]
    researcher_output = _read_json(Path(refs["hypothesis_artifact"]))["output"]
    hypothesis = researcher_output.get("hypothesis", researcher_output)
    mechanism = _read_json(Path(refs["mechanism_file"]))
    review = payload["candidate_review"]
    gate = payload["promotion_gate"]
    return build_promotion_direction_request(
        failure_direction_id="run_20260803_g0001_fd0001",
        failure_summary=(
            f"{failure['pattern']} Applicability: {failure['applicability']}"
        )[:800],
        research_scheme_id="run_20260803_g0001_fd0001_rs0001",
        research_summary=(
            f"Applicability: {hypothesis['applicability']}; "
            f"primary signal: {hypothesis['evaluation']['primary_signal']}"
        )[:800],
        mechanism_scheme_id="run_20260803_g0001_fd0001_rs0001_ms",
        mechanism_summary=(
            f"Goal: {mechanism['goal']}; "
            f"expected behavior: {mechanism['expected_behavior']}"
        )[:800],
        mechanism_goal=mechanism["goal"],
        candidate_review=review,
        promotion_gate=gate,
        source_refs=[
            "failure_artifact",
            "hypothesis_artifact",
            "mechanism_file",
            "candidate_reviewer_artifact",
        ],
    )


def _summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [item for item in results if item["status"] == "completed"]
    total_tokens = sum(
        int(item.get("usage", {}).get("total_tokens", 0) or 0)
        for item in results
    )
    by_case: dict[str, list[dict[str, Any]]] = {}
    for item in results:
        by_case.setdefault(item["case_id"], []).append(item)
    return {
        "schema_version": 1,
        "totals": {
            "runs": len(results),
            "completed": len(completed),
            "failed": len(results) - len(completed),
            "total_tokens": total_tokens,
        },
        "cases": by_case,
    }


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    values = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise TypeError(f"expected JSONL object: {path}")
        values.append(value)
    return values


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    asyncio.run(_main())
