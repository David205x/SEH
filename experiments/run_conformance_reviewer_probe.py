"""Run repeated real-API Conformance Reviewer checks on one saved role input."""

from __future__ import annotations

import argparse
import asyncio
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


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-artifact", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument(
        "--role-id",
        default="conformance_reviewer",
        choices=("conformance_reviewer", "shadow_conformance_reviewer"),
    )
    parser.add_argument("--template-root", type=Path)
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.repetitions < 1:
        raise ValueError("repetitions must be positive")
    source = _read_json(args.source_artifact)
    role_artifact = source.get("role_artifact", source)
    if not isinstance(role_artifact, dict):
        raise TypeError("source role_artifact must be an object")
    role_input = role_artifact.get("input")
    if not isinstance(role_input, dict):
        raise TypeError("source artifact has no Conformance Reviewer input")

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "request.json", {"input": role_input})
    template_root = (
        args.template_root
        if args.template_root is not None
        else Path("harness_templates/teacher") / args.role_id
    )

    async def invoke(index: int) -> dict[str, Any]:
        runner = NativeChatRoleRunner(env_file=args.env_file)
        try:
            artifact = await runner.run(
                template_root=template_root,
                role_input=role_input,
                resource_config=TeacherResourceConfig(),
                role_id=args.role_id,
                role_version=1,
            )
        except TeacherRoleRunFailed as exc:
            artifact = exc.failure_artifact
        path = output_dir / f"review_{index:02d}.json"
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
    _write_json(output_dir / "summary.json", {"results": results})
    return results


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    results = asyncio.run(_run(args))
    for result in results:
        output = result.get("output")
        verdict = output.get("verdict") if isinstance(output, dict) else None
        print(
            f"review {result['index']}: status={result['status']}, "
            f"verdict={verdict}"
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


if __name__ == "__main__":
    main()
