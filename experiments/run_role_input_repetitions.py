"""Replay one persisted Teacher role input through the current template."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from search_harness.evolution.research.resources.base import (
    TeacherResourceConfig,
)
from search_harness.evolution.research.roles.native_chat_runner import (
    NativeChatRoleRunner,
    TeacherRoleRunFailed,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-artifact", type=Path, required=True)
    parser.add_argument("--template-root", type=Path, required=True)
    parser.add_argument("--role-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument(
        "--conformance-effect",
        type=Path,
        help="Add compact non-faithful findings to a Compiler replay.",
    )
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> None:
    if args.repetitions < 1:
        raise ValueError("repetitions must be positive")
    source = _read_json(args.source_artifact)
    role_input = source.get("input")
    if not isinstance(role_input, dict):
        raise TypeError("source artifact lacks a structured role input")
    role_input = dict(role_input)
    if args.role_id == "evidence_reviewer":
        role_input.setdefault(
            "trial_selection_capabilities",
            {
                "addressable": [
                    "unused prefix at the frozen fork_phase",
                    "prefer a previously unused Example",
                    "prefer a previously unused replicate",
                ],
                "not_addressable": [
                    "future Student or Hook-model outcome",
                    "semantic positive or negative predicate",
                    "sampling until a requested stochastic outcome",
                ],
            },
        )
    if args.role_id == "compiler" and args.conformance_effect is not None:
        role_input["conformance_failures"] = _conformance_failures(
            _read_json(args.conformance_effect)
        )
    raw_resources = source.get("resource_config")
    resources = TeacherResourceConfig.model_validate(
        raw_resources if isinstance(raw_resources, dict) else {}
    )
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=False)

    async def invoke(index: int) -> dict[str, Any]:
        runner = NativeChatRoleRunner(env_file=args.env_file)
        try:
            artifact = await runner.run(
                template_root=args.template_root,
                role_id=args.role_id,
                role_version=1,
                role_input=role_input,
                resource_config=resources,
            )
        except TeacherRoleRunFailed as exc:
            artifact = exc.failure_artifact
        path = output_dir / f"run_{index:02d}.json"
        _write_json(path, artifact)
        return {
            "index": index,
            "status": artifact.get("status", "completed"),
            "output": artifact.get("output"),
            "usage": artifact.get("usage"),
            "artifact": str(path.resolve()),
        }

    results = await asyncio.gather(
        *(invoke(index) for index in range(1, args.repetitions + 1))
    )
    _write_json(
        output_dir / "summary.json",
        {
            "source_artifact": str(args.source_artifact.resolve()),
            "role_id": args.role_id,
            "results": results,
        },
    )


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"JSON artifact must be an object: {path}")
    return value


def _conformance_failures(effect: dict[str, Any]) -> list[dict[str, Any]]:
    refs = effect.get("artifact_refs")
    refs = refs if isinstance(refs, dict) else {}
    failures = []
    for key, raw_path in refs.items():
        if not str(key).startswith("conformance_finding_"):
            continue
        if not isinstance(raw_path, str):
            continue
        finding = _read_json(Path(raw_path)).get("output")
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
