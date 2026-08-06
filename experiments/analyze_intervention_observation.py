"""Repeat one recorded Intervention Worker assignment for stability analysis."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any, Sequence

from search_harness.evolution.research.intervention.role_runner import (
    InterventionRoleRunner,
)
from search_harness.evolution.research.resources.base import TeacherResourceConfig


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-artifact", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--max-turns", type=int, default=20)
    return parser.parse_args(argv)


async def _run_once(
    *,
    source: dict[str, Any],
    max_turns: int,
) -> dict[str, Any]:
    runner = InterventionRoleRunner(
        max_steps_per_activation=max_turns,
        teacher_judge=False,
    )
    return await runner.run(
        template_root=Path(source["template_root"]),
        role_input=source["input"],
        resource_config=TeacherResourceConfig.model_validate(
            source["resource_config"]
        ),
        role_id="intervention_worker",
        role_version=1,
    )


def _summary(artifact: dict[str, Any]) -> dict[str, Any]:
    trial = artifact["resource_artifacts"]["intervention_trial"]
    actions = [
        {
            "phase": change.get("phase"),
            "kind": change.get("action", {}).get("kind"),
            "reason": change.get("action", {}).get("reason"),
        }
        for change in trial["context_changes"]
    ]
    model_turns = sum(
        event.get("event_type") == "worker_model_output"
        for event in trial["worker_trace"]
    )
    return {
        "output": artifact["output"],
        "actions": actions,
        "worker_model_turns": model_turns,
        "worker_tool_calls": len(artifact["tool_calls"]),
        "usage": artifact["usage"],
    }


async def async_main(args: argparse.Namespace) -> None:
    if args.repeats < 1:
        raise ValueError("repeats must be positive")
    source = json.loads(
        args.source_artifact.read_text(encoding="utf-8")
    )
    artifacts = await asyncio.gather(
        *(
            _run_once(source=source, max_turns=args.max_turns)
            for _ in range(args.repeats)
        )
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for index, artifact in enumerate(artifacts, start=1):
        (args.output_dir / f"run_{index:02d}.json").write_text(
            json.dumps(artifact, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    (args.output_dir / "summary.json").write_text(
        json.dumps(
            [_summary(artifact) for artifact in artifacts],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main(argv: Sequence[str] | None = None) -> None:
    asyncio.run(async_main(parse_args(argv)))


if __name__ == "__main__":
    main()
