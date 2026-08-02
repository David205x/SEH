"""Standalone Teacher v2 命令行入口。"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from .intervention.role_runner import InterventionRoleRunner
from .roles.contracts import get_teacher_role
from .roles.native_chat_runner import NativeChatRoleRunner
from .roles.runner import RoleRunner
from .resources.stores import (
    CandidateReviewResourceConfig,
    CompilerResourceConfig,
    InterventionResourceConfig,
)
from .resources.base import TeacherResourceConfig


DEFAULT_RUN_ROOT = Path("runs/components/teacher")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one Teacher role template with native tool calling.",
    )
    parser.add_argument("--template_root", type=Path, required=True)
    parser.add_argument("--role-id")
    parser.add_argument("--request_file", type=Path, required=True)
    parser.add_argument("--output-file", type=Path)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--max-turns", type=int, default=15)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    request_file = args.request_file.resolve()
    request = _read_request(request_file)
    resources = _resolve_resource_config(
        TeacherResourceConfig.model_validate(request.get("resources", {})),
        base_dir=request_file.parent,
    )
    role_input = request.get("input")
    if not isinstance(role_input, dict):
        raise TypeError("Teacher request field 'input' must be an object")

    role_id = args.role_id or args.template_root.name
    role = get_teacher_role(role_id, 1)
    runner: RoleRunner
    if role.role_id == "intervention_worker":
        runner = InterventionRoleRunner(
            env_file=args.env_file,
            max_steps_per_activation=args.max_turns,
        )
    else:
        runner = NativeChatRoleRunner(
            env_file=args.env_file,
            max_turns=args.max_turns,
        )
    artifact = asyncio.run(
        runner.run(
            template_root=args.template_root,
            role_input=role_input,
            resource_config=resources,
            role_id=role.role_id,
            role_version=role.version,
        )
    )
    output_file = args.output_file or _default_output_file(artifact)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Teacher role completed: {artifact['role']['id']}")
    print(f"Result written to: {output_file.resolve()}")


def _read_request(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Teacher request does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid Teacher request JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise TypeError("Teacher request must contain a JSON object")
    unknown = set(payload) - {"input", "resources"}
    if unknown:
        raise ValueError(f"Teacher request has unsupported fields: {sorted(unknown)}")
    return payload


def _resolve_resource_config(
    config: TeacherResourceConfig,
    *,
    base_dir: Path,
) -> TeacherResourceConfig:
    def resolve(path: Path | None) -> Path | None:
        if path is None:
            return None
        return path if path.is_absolute() else (base_dir / path).resolve()

    return TeacherResourceConfig(
        report_dir=resolve(config.report_dir),
        rollout_file=resolve(config.rollout_file),
        student_template_root=resolve(config.student_template_root),
        trial_files=[
            path if path.is_absolute() else (base_dir / path).resolve()
            for path in config.trial_files
        ],
        intervention=(
            InterventionResourceConfig(
                rollout_file=resolve(config.intervention.rollout_file),
                student_template_root=resolve(
                    config.intervention.student_template_root
                ),
                env_file=resolve(config.intervention.env_file),
                student_max_steps=config.intervention.student_max_steps,
            )
            if config.intervention is not None
            else None
        ),
        compiler=(
            CompilerResourceConfig(
                parent_template_root=resolve(
                    config.compiler.parent_template_root
                ),
                env_file=resolve(config.compiler.env_file),
            )
            if config.compiler is not None
            else None
        ),
        candidate_review=(
            CandidateReviewResourceConfig(
                incumbent_report_dir=resolve(
                    config.candidate_review.incumbent_report_dir
                ),
                candidate_report_dir=resolve(
                    config.candidate_review.candidate_report_dir
                ),
                incumbent_rollout_file=resolve(
                    config.candidate_review.incumbent_rollout_file
                ),
                candidate_rollout_file=resolve(
                    config.candidate_review.candidate_rollout_file
                ),
                incumbent_template_root=resolve(
                    config.candidate_review.incumbent_template_root
                ),
                candidate_template_root=resolve(
                    config.candidate_review.candidate_template_root
                ),
            )
            if config.candidate_review is not None
            else None
        ),
    )


def _default_output_file(artifact: dict[str, Any]) -> Path:
    role_id = str(artifact["role"]["id"])
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return DEFAULT_RUN_ROOT / role_id / timestamp / "run.json"
