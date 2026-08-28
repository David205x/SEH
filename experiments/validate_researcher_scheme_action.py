"""Validate the Researcher lineage wrapper on one historical Failure Direction."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from search_harness.evolution.research.resources.base import TeacherResourceConfig
from search_harness.evolution.research.roles.native_chat_runner import (
    NativeChatRoleRunner,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ARTIFACT = (
    PROJECT_ROOT
    / "runs/evolution/20260803/artifacts"
    / "analyze_failure-ec66e26531d23d6b/role.json"
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=3)
    return parser.parse_args()


async def _run(
    runner: NativeChatRoleRunner,
    source: dict[str, Any],
    output_dir: Path,
    repetition: int,
) -> dict[str, Any]:
    target = output_dir / f"rep_{repetition:02d}"
    target.mkdir(parents=True, exist_ok=False)
    try:
        artifact = await runner.run(
            template_root=(
                PROJECT_ROOT
                / "harness_templates/teacher/hypothesis_researcher"
            ),
            role_id="hypothesis_researcher",
            role_version=2,
            role_input={"problem_direction": source["output"]},
            resource_config=TeacherResourceConfig.model_validate(
                source["resource_config"]
            ),
        )
        _write_json(target / "role.json", artifact)
        return {
            "repetition": repetition,
            "status": "completed",
            "scheme_action": artifact["output"]["scheme_action"],
            "usage": artifact.get("usage", {}),
        }
    except Exception as exc:
        result = {
            "repetition": repetition,
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
        }
        artifact = getattr(exc, "failure_artifact", None)
        if isinstance(artifact, dict):
            _write_json(target / "role.failed.json", artifact)
            result["usage"] = artifact.get("usage", {})
        return result


async def _main() -> None:
    args = _parse_args()
    if args.repetitions < 1:
        raise ValueError("repetitions must be positive")
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    source = _read_json(SOURCE_ARTIFACT)
    runner = NativeChatRoleRunner(env_file=args.env_file)
    results = await asyncio.gather(
        *(
            _run(runner, source, output_dir, repetition)
            for repetition in range(1, args.repetitions + 1)
        )
    )
    summary = {
        "schema_version": 1,
        "results": results,
        "completed": sum(item["status"] == "completed" for item in results),
        "total_tokens": sum(
            int(item.get("usage", {}).get("total_tokens", 0) or 0)
            for item in results
        ),
    }
    _write_json(output_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    asyncio.run(_main())
