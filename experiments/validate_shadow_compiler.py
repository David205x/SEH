"""Compile one Shadow Mechanism with an exact managed Prompt Product."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

from search_harness.evolution.research.resources.base import TeacherResourceConfig
from search_harness.evolution.research.resources.stores import CompilerResourceConfig
from search_harness.evolution.research.roles.native_chat_runner import (
    NativeChatRoleRunner,
    TeacherRoleRunFailed,
)
from search_harness.evolution.research.roles.contracts import ShadowCompilerInput


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = PROJECT_ROOT / "harness_templates" / "teacher" / "shadow_compiler"


def main() -> None:
    args = _parse_args()
    result = asyncio.run(_run(args))
    print(json.dumps(result, ensure_ascii=False))


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    distiller_path = args.distiller_artifact.resolve()
    prompt_path = args.prompt_artifact.resolve()
    distiller = _read_json(distiller_path)
    prompt_role = _read_json(prompt_path)
    mechanism = _required_object(_required_object(distiller, "output"), "mechanism")
    prompt_output = _required_object(prompt_role, "output")
    product = _required_object(prompt_output, "product")
    compiler_input = ShadowCompilerInput.model_validate(
        {
            "mechanism": mechanism,
            "prompt_products": [product],
            "implementation_constraints": [],
            "validation_feedback": [],
        }
    )
    source_hashes = {
        str(path): _sha256(path) for path in (distiller_path, prompt_path)
    }
    results = []
    for repetition in range(1, args.repetitions + 1):
        try:
            artifact = await NativeChatRoleRunner(env_file=args.env_file).run(
                template_root=TEMPLATE_ROOT,
                role_id="shadow_compiler",
                role_version=1,
                role_input=compiler_input.model_dump(mode="json"),
                resource_config=TeacherResourceConfig(
                    compiler=CompilerResourceConfig(
                        parent_template_root=args.parent_template_root.resolve(),
                        env_file=args.env_file.resolve(),
                    )
                ),
            )
            status = "completed"
            error = None
        except TeacherRoleRunFailed as exc:
            artifact = exc.failure_artifact
            status = "failed"
            error = str(exc)
        run_dir = output_dir / f"run_{repetition:03d}"
        role_path = _write_json(run_dir / "role.json", artifact)
        candidate = _candidate_artifact(artifact)
        candidate_path = (
            _write_json(run_dir / "candidate.json", candidate)
            if candidate is not None
            else None
        )
        results.append(
            {
                "repetition": repetition,
                "status": status,
                "error": error,
                "output": artifact.get("output"),
                "role_artifact": str(role_path),
                "candidate_artifact": (
                    str(candidate_path) if candidate_path is not None else None
                ),
                "tool_names": [
                    item.get("name")
                    for item in artifact.get("tool_calls", [])
                    if isinstance(item, dict)
                ],
                "usage": artifact.get("usage", {}),
            }
        )
    if any(
        not Path(path).is_file() or _sha256(Path(path)) != digest
        for path, digest in source_hashes.items()
    ):
        raise RuntimeError("Shadow Compiler changed an upstream Artifact")
    summary = {
        "schema_version": 1,
        "distiller_artifact": str(distiller_path),
        "prompt_artifact": str(prompt_path),
        "parent_template_root": str(args.parent_template_root.resolve()),
        "source_hashes_preserved": True,
        "results": results,
    }
    summary_path = _write_json(output_dir / "summary.json", summary)
    return {
        "status": "completed",
        "result_count": len(results),
        "summary": str(summary_path),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--distiller-artifact", type=Path, required=True)
    parser.add_argument("--prompt-artifact", type=Path, required=True)
    parser.add_argument("--parent-template-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--repetitions", type=int, default=1)
    args = parser.parse_args()
    if args.repetitions < 1:
        parser.error("--repetitions must be positive")
    return args


def _candidate_artifact(artifact: dict[str, Any]) -> dict[str, Any] | None:
    resources = artifact.get("resource_artifacts")
    if not isinstance(resources, dict):
        return None
    candidate = resources.get("compiler_candidate")
    return dict(candidate) if isinstance(candidate, dict) else None


def _required_object(value: dict[str, Any], name: str) -> dict[str, Any]:
    item = value.get(name)
    if not isinstance(item, dict):
        raise TypeError(f"Artifact field {name} must be an object")
    return dict(item)


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


if __name__ == "__main__":
    main()
