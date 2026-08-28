"""Replay persisted Distiller evidence through current and shadow protocols。"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from search_harness.evolution.research.resources.base import (
    TeacherResourceConfig,
)
from search_harness.evolution.research.roles.native_chat_runner import (
    NativeChatRoleRunner,
    TeacherRoleRunFailed,
)
from search_harness.evolution.research.shadow_task_inputs import (
    shadow_input_projection_digest,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEACHER_ROOT = PROJECT_ROOT / "harness_templates" / "teacher"


@dataclass(frozen=True)
class Arm:
    name: str
    role_id: str
    template_root: Path


ARMS = {
    "current": Arm(
        name="current",
        role_id="mechanism_distiller",
        template_root=TEACHER_ROOT / "mechanism_distiller",
    ),
    "shadow": Arm(
        name="shadow",
        role_id="shadow_mechanism_distiller",
        template_root=TEACHER_ROOT / "shadow_mechanism_distiller",
    ),
}


async def run(args: argparse.Namespace) -> dict[str, Any]:
    """Execute independent repetitions without modifying source Artifacts。"""

    if args.repetitions < 1:
        raise ValueError("repetitions must be positive")
    selected_arms = [ARMS[name] for name in (args.arm or list(ARMS))]
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    sources = [_load_source(path.resolve()) for path in args.source_artifact]
    protected_paths = _protected_paths(sources)
    initial_hashes = _hashes(protected_paths)
    template_hashes = {
        arm.name: _tree_digest(arm.template_root) for arm in selected_arms
    }
    _write_json(
        output_dir / "manifest.json",
        {
            "schema_version": 1,
            "sources": [str(item["path"]) for item in sources],
            "arms": [arm.name for arm in selected_arms],
            "repetitions": args.repetitions,
            "template_hashes": template_hashes,
            "protected_source_hashes": initial_hashes,
        },
    )

    results: list[dict[str, Any]] = []
    for source in sources:
        case_name = str(source["case_name"])
        for arm in selected_arms:
            tasks = [
                _run_once(
                    arm=arm,
                    source=source,
                    env_file=args.env_file.resolve(),
                    output_dir=output_dir,
                    repetition=repetition,
                )
                for repetition in range(1, args.repetitions + 1)
            ]
            batch = await asyncio.gather(*tasks)
            results.extend(batch)
            print(
                f"completed case={case_name} arm={arm.name} "
                f"runs={len(batch)}",
                flush=True,
            )

    final_hashes = _hashes(protected_paths)
    if final_hashes != initial_hashes:
        raise RuntimeError("source Artifact changed during shadow Distiller replay")
    final_template_hashes = {
        arm.name: _tree_digest(arm.template_root) for arm in selected_arms
    }
    if final_template_hashes != template_hashes:
        raise RuntimeError("Teacher Template changed during replay")
    summary = {
        "schema_version": 1,
        "manifest": str((output_dir / "manifest.json").resolve()),
        "source_hashes_preserved": True,
        "template_hashes_preserved": True,
        "results": results,
        "aggregates": _aggregate(results),
    }
    _write_json(output_dir / "summary.json", summary)
    return summary


async def _run_once(
    *,
    arm: Arm,
    source: dict[str, Any],
    env_file: Path,
    output_dir: Path,
    repetition: int,
) -> dict[str, Any]:
    runner = NativeChatRoleRunner(env_file=env_file)
    try:
        artifact = await runner.run(
            template_root=arm.template_root,
            role_id=arm.role_id,
            role_version=1,
            role_input=dict(source["role_input"]),
            resource_config=source["resources"],
        )
        status = "completed"
        error = None
    except TeacherRoleRunFailed as exc:
        artifact = exc.failure_artifact
        status = "failed"
        error = str(exc)
    case_name = str(source["case_name"])
    run_dir = output_dir / case_name / arm.name / f"run_{repetition:03d}"
    artifact_path = _write_json(run_dir / "role.json", artifact)
    mechanism = _mechanism(artifact, arm.name)
    mechanism_path = (
        _write_json(run_dir / "mechanism.json", mechanism)
        if mechanism is not None
        else None
    )
    projection_digests = (
        _shadow_projection_digests(mechanism)
        if mechanism is not None and arm.name == "shadow"
        else {}
    )
    provenance = (
        _shadow_provenance(
            source=source,
            role_artifact=artifact_path,
            mechanism=mechanism,
        )
        if mechanism is not None and arm.name == "shadow"
        else None
    )
    provenance_path = (
        _write_json(run_dir / "provenance.json", provenance)
        if provenance is not None
        else None
    )
    output = artifact.get("output")
    return {
        "case": case_name,
        "arm": arm.name,
        "repetition": repetition,
        "status": status,
        "error": error,
        "artifact": str(artifact_path),
        "mechanism_artifact": (
            str(mechanism_path) if mechanism_path is not None else None
        ),
        "provenance_artifact": (
            str(provenance_path) if provenance_path is not None else None
        ),
        "input_projection_digests": projection_digests,
        "output": output,
        "semantic_shape": _semantic_shape(output, mechanism, arm.name),
        "tool_names": [
            str(item.get("name"))
            for item in artifact.get("tool_calls", [])
            if isinstance(item, dict)
        ],
        "terminal_submit_attempts": sum(
            1
            for item in artifact.get("tool_calls", [])
            if isinstance(item, dict)
            and str(item.get("name", "")).startswith("submit_")
        ),
        "output_characters": len(
            json.dumps(output, ensure_ascii=False, separators=(",", ":"))
        ),
        "mechanism_characters": len(
            json.dumps(mechanism, ensure_ascii=False, separators=(",", ":"))
        ) if mechanism is not None else 0,
        "usage": _usage(artifact),
    }


def _load_source(path: Path) -> dict[str, Any]:
    artifact = _read_json(path)
    role_input = artifact.get("input")
    if not isinstance(role_input, dict):
        raise TypeError(f"Distiller Artifact lacks role input: {path}")
    raw_resources = artifact.get("resource_config")
    resources = TeacherResourceConfig.model_validate(
        raw_resources if isinstance(raw_resources, dict) else {}
    )
    if not resources.trial_files:
        raise ValueError(f"Distiller Artifact has no Trial files: {path}")
    case_name = path.parents[2].name + "_" + path.parent.name
    return {
        "path": path,
        "case_name": case_name,
        "role_input": role_input,
        "resources": resources,
    }


def _protected_paths(sources: list[dict[str, Any]]) -> list[Path]:
    paths = []
    for source in sources:
        paths.append(Path(source["path"]))
        resources = source["resources"]
        paths.extend(resources.trial_files)
    return sorted({path.resolve() for path in paths})


def _mechanism(
    artifact: dict[str, Any],
    arm: str,
) -> dict[str, Any] | None:
    output = artifact.get("output")
    if not isinstance(output, dict):
        return None
    if arm == "shadow":
        mechanism = output.get("mechanism")
        return dict(mechanism) if isinstance(mechanism, dict) else None
    ref = output.get("mechanism_ref")
    mechanisms = artifact.get("validated_mechanisms")
    if not isinstance(ref, str) or not isinstance(mechanisms, dict):
        return None
    mechanism = mechanisms.get(ref)
    return dict(mechanism) if isinstance(mechanism, dict) else None


def _semantic_shape(
    output: object,
    mechanism: dict[str, Any] | None,
    arm: str,
) -> dict[str, Any]:
    output = output if isinstance(output, dict) else {}
    if mechanism is None:
        return {
            "outcome": output.get("outcome", output.get("decision")),
            "effect_kind": None,
            "phases": [],
            "task_kinds": [],
            "evaluators": [],
            "state_names": [],
        }
    if arm == "shadow":
        phases = mechanism.get("phases")
        phases = phases if isinstance(phases, list) else []
        tasks = [
            item.get("task")
            for item in phases
            if isinstance(item, dict) and isinstance(item.get("task"), dict)
        ]
        effect = mechanism.get("effect")
        effect = effect if isinstance(effect, dict) else {}
        states = mechanism.get("state")
        states = states if isinstance(states, list) else []
        return {
            "outcome": output.get("outcome"),
            "effect_kind": effect.get("kind"),
            "phases": [item.get("phase") for item in phases],
            "task_kinds": [item.get("kind") for item in tasks],
            "evaluators": [item.get("evaluator") for item in tasks],
            "state_names": [
                item.get("name") for item in states if isinstance(item, dict)
            ],
        }
    rules = mechanism.get("phase_rules")
    rules = rules if isinstance(rules, list) else []
    return {
        "outcome": output.get("decision"),
        "effect_kind": mechanism.get("effect_goal", "task_outcome"),
        "phases": [item.get("phase") for item in rules if isinstance(item, dict)],
        "task_kinds": ["decision" for item in rules if isinstance(item, dict)],
        "evaluators": [
            item.get("decision_evaluator")
            for item in rules
            if isinstance(item, dict)
        ],
        "state_names": [],
    }


def _shadow_projection_digests(
    mechanism: dict[str, Any],
) -> dict[str, str]:
    states = mechanism.get("state")
    states = states if isinstance(states, list) else []
    state_types = {
        str(item.get("name")): str(item.get("value_type"))
        for item in states
        if isinstance(item, dict)
    }
    phases = mechanism.get("phases")
    phases = phases if isinstance(phases, list) else []
    digests = {}
    for item in phases:
        if not isinstance(item, dict):
            continue
        phase = item.get("phase")
        task = item.get("task")
        inputs = task.get("inputs") if isinstance(task, dict) else None
        if not isinstance(phase, str) or not isinstance(inputs, list):
            raise TypeError("shadow Mechanism phase lacks task inputs")
        digests[phase] = shadow_input_projection_digest(
            phase=phase,
            inputs=[entry for entry in inputs if isinstance(entry, dict)],
            state_types=state_types,
        )
    return digests


def _shadow_provenance(
    *,
    source: dict[str, Any],
    role_artifact: Path,
    mechanism: dict[str, Any],
) -> dict[str, Any]:
    source_path = Path(source["path"]).resolve()
    resources = source["resources"]
    return {
        "source_refs": [str(path.resolve()) for path in resources.trial_files],
        "coverage_ref": f"{source_path}#/input/coverage_summary",
        "evidence_review_ref": f"{source_path}#/input/review",
        "role_artifact_ref": str(role_artifact.resolve()),
        "mechanism_digest": _content_digest(mechanism),
    }


def _usage(artifact: dict[str, Any]) -> dict[str, int]:
    usage = artifact.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    return {
        key: int(value) if isinstance(value, int) else 0
        for key in (
            "requests",
            "input_tokens",
            "output_tokens",
            "total_tokens",
        )
        for value in (usage.get(key),)
    }


def _aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in results:
        key = f"{item['case']}::{item['arm']}"
        groups.setdefault(key, []).append(item)
    return {
        key: {
            "runs": len(items),
            "completed": sum(item["status"] == "completed" for item in items),
            "first_submit": sum(
                item["status"] == "completed"
                and item["terminal_submit_attempts"] == 1
                for item in items
            ),
            "mean_total_tokens": (
                sum(item["usage"]["total_tokens"] for item in items)
                / len(items)
            ),
            "mean_output_characters": (
                sum(item["output_characters"] for item in items) / len(items)
            ),
            "semantic_shapes": [item["semantic_shape"] for item in items],
        }
        for key, items in groups.items()
    }


def _hashes(paths: list[Path]) -> dict[str, str]:
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def _content_digest(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"JSON Artifact must be an object: {path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path.resolve()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-artifact",
        action="append",
        type=Path,
        required=True,
    )
    parser.add_argument("--arm", action="append", choices=tuple(ARMS))
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = asyncio.run(run(args))
    print(
        json.dumps(
            {
                "status": "completed",
                "result_count": len(summary["results"]),
                "output_dir": str(args.output_dir.resolve()),
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
