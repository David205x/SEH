"""Compare current and shadow Distillers on one queued formal WorkItem."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

from search_harness.evolution.control.domain import (
    EffectResult,
    EvolutionControlConfig,
    WorkItem,
    WorkKind,
    project_events,
)
from search_harness.evolution.control.effects import (
    LocalControlEffects,
    LocalControlEffectsConfig,
)
from search_harness.evolution.control.journal import ControlJournal
from search_harness.evolution.research.resources.base import (
    TeacherResourceConfig,
)
from search_harness.evolution.research.roles.native_chat_runner import (
    NativeChatRoleRunner,
    TeacherRoleRunFailed,
)
from search_harness.evolution.versioning import TemplateVersionStore


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SHADOW_TEMPLATE = (
    PROJECT_ROOT / "harness_templates" / "teacher" / "shadow_mechanism_distiller"
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse queued-Run Distiller comparison arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--env-file", type=Path)
    return parser.parse_args(argv)


async def compare_distillers(args: argparse.Namespace) -> dict[str, Any]:
    """Run both Distillers without completing the queued Controller work."""

    run_dir = args.run_dir.resolve()
    output_dir = args.output_dir.resolve()
    if output_dir.exists():
        raise FileExistsError(f"Comparison output already exists: {output_dir}")
    payload = _read_object(run_dir / "run.json")
    if payload.get("schema_version") != 3:
        raise ValueError("Distiller comparison requires Run schema v3")
    state = project_events(
        ControlJournal(run_dir / "events.jsonl").read()
    )
    work = _queued_distiller(state)
    protected = _distiller_source_files(work)
    source_hashes = _hashes(protected)

    stored_effects = _required_object(payload, "effects_config")
    if args.env_file is not None:
        stored_effects["env_file"] = str(args.env_file.resolve())
    stored_effects["show_progress"] = False
    effects_config = LocalControlEffectsConfig(
        **{
            **stored_effects,
            "experience_file": Path(
                _required_string(stored_effects, "experience_file")
            ),
            "env_file": Path(
                _required_string(stored_effects, "env_file")
            ),
        }
    )
    store = TemplateVersionStore(
        Path(_required_string(payload, "version_store"))
    )
    expected_store_id = _required_string(payload, "version_store_id")
    if store.version_store_id != expected_store_id:
        raise ValueError(
            "Evolution Run version_store_id does not match Version Store: "
            f"{expected_store_id} != {store.version_store_id}"
        )
    EvolutionControlConfig(
        **_required_object(payload, "control_config")
    )

    output_dir.mkdir(parents=True)
    current_dir = output_dir / "current"
    local_effects = LocalControlEffects(store=store, config=effects_config)
    current_artifact, current_result = await _run_current(
        effects=local_effects,
        work=work,
        state=state,
        work_dir=current_dir,
    )
    current_path = _write_json(
        current_dir / "comparison_role.json",
        current_artifact,
    )

    shadow_dir = output_dir / "shadow"
    shadow_artifact = await _run_shadow(
        current_artifact=current_artifact,
        env_file=effects_config.env_file,
    )
    shadow_path = _write_json(
        shadow_dir / "role.json",
        shadow_artifact,
    )
    if shadow_artifact.get("input") != current_artifact.get("input"):
        raise RuntimeError("Distiller arms received different Role Inputs")
    if shadow_artifact.get("resource_config") != current_artifact.get(
        "resource_config"
    ):
        raise RuntimeError("Distiller arms received different resources")

    final_hashes = _hashes(protected)
    if final_hashes != source_hashes:
        raise RuntimeError("Source Artifacts changed during Distiller comparison")
    summary = {
        "schema_version": 1,
        "run_dir": str(run_dir),
        "queued_work_id": work.work_id,
        "source_hashes_preserved": True,
        "arms": {
            "current": _arm_summary(
                artifact=current_artifact,
                artifact_path=current_path,
                effect=current_result,
                shadow=False,
            ),
            "shadow": _arm_summary(
                artifact=shadow_artifact,
                artifact_path=shadow_path,
                effect=None,
                shadow=True,
            ),
        },
    }
    _write_json(output_dir / "summary.json", summary)
    return summary


async def _run_current(
    *,
    effects: LocalControlEffects,
    work: WorkItem,
    state: Any,
    work_dir: Path,
) -> tuple[dict[str, Any], EffectResult | None]:
    try:
        result = await effects.execute(
            work=work,
            state=state,
            work_dir=work_dir,
        )
    except TeacherRoleRunFailed as exc:
        return exc.failure_artifact, None
    artifact = _read_object(work_dir / "role.json")
    _write_json(work_dir / "effect.json", result.to_dict())
    return artifact, result


async def _run_shadow(
    *,
    current_artifact: dict[str, Any],
    env_file: Path,
) -> dict[str, Any]:
    role_input = _required_object(current_artifact, "input")
    resources = TeacherResourceConfig.model_validate(
        _required_object(current_artifact, "resource_config")
    )
    runner = NativeChatRoleRunner(env_file=env_file)
    try:
        return await runner.run(
            template_root=SHADOW_TEMPLATE,
            role_id="shadow_mechanism_distiller",
            role_version=1,
            role_input=role_input,
            resource_config=resources,
        )
    except TeacherRoleRunFailed as exc:
        return exc.failure_artifact


def _queued_distiller(state: Any) -> WorkItem:
    if state.status != "running" or len(state.queued) != 1:
        raise RuntimeError(
            "Run must contain exactly one queued Distiller WorkItem"
        )
    work = state.queued[0].item
    if work.kind is not WorkKind.DISTILL_MECHANISM:
        raise RuntimeError(
            f"Run is not waiting for Distiller: {work.kind.value}"
        )
    return work


def _distiller_source_files(work: WorkItem) -> list[Path]:
    keys = ["hypothesis_artifact", "reviewer_artifact"]
    keys.extend(
        key
        for key in sorted(work.input_refs)
        if key.startswith("trial_") and key[6:].isdigit()
    )
    paths = [Path(work.input_refs[key]).resolve() for key in keys]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Distiller source files are missing: {missing}")
    return paths


def _arm_summary(
    *,
    artifact: dict[str, Any],
    artifact_path: Path,
    effect: EffectResult | None,
    shadow: bool,
) -> dict[str, Any]:
    output = artifact.get("output")
    output = output if isinstance(output, dict) else {}
    mechanism = _mechanism(artifact, shadow=shadow)
    usage = artifact.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    tool_calls = artifact.get("tool_calls")
    tool_calls = tool_calls if isinstance(tool_calls, list) else []
    return {
        "status": "failed" if artifact.get("status") == "failed" else "completed",
        "artifact": str(artifact_path),
        "outcome": output.get("outcome" if shadow else "decision"),
        "output": output,
        "mechanism": mechanism,
        "semantic_shape": _semantic_shape(mechanism, shadow=shadow),
        "tool_names": [
            str(item.get("name"))
            for item in tool_calls
            if isinstance(item, dict)
        ],
        "terminal_submit_attempts": sum(
            isinstance(item, dict)
            and str(item.get("name", "")).startswith("submit_")
            for item in tool_calls
        ),
        "usage": {
            name: int(usage.get(name, 0))
            if isinstance(usage.get(name, 0), int)
            else 0
            for name in (
                "requests",
                "input_tokens",
                "output_tokens",
                "total_tokens",
            )
        },
        "effect": effect.to_dict() if effect is not None else None,
    }


def _mechanism(
    artifact: dict[str, Any],
    *,
    shadow: bool,
) -> dict[str, Any] | None:
    output = artifact.get("output")
    if not isinstance(output, dict):
        return None
    if shadow:
        mechanism = output.get("mechanism")
        return dict(mechanism) if isinstance(mechanism, dict) else None
    ref = output.get("mechanism_ref")
    mechanisms = artifact.get("validated_mechanisms")
    if not isinstance(ref, str) or not isinstance(mechanisms, dict):
        return None
    mechanism = mechanisms.get(ref)
    return dict(mechanism) if isinstance(mechanism, dict) else None


def _semantic_shape(
    mechanism: dict[str, Any] | None,
    *,
    shadow: bool,
) -> dict[str, Any]:
    if mechanism is None:
        return {
            "effect_kind": None,
            "phases": [],
            "evaluators": [],
            "state_names": [],
        }
    if shadow:
        phases = mechanism.get("phases")
        phases = phases if isinstance(phases, list) else []
        effect = mechanism.get("effect")
        effect = effect if isinstance(effect, dict) else {}
        state = mechanism.get("state")
        state = state if isinstance(state, list) else []
        return {
            "effect_kind": effect.get("kind"),
            "phases": [
                item.get("phase") for item in phases if isinstance(item, dict)
            ],
            "evaluators": [
                item.get("task", {}).get("evaluator")
                for item in phases
                if isinstance(item, dict) and isinstance(item.get("task"), dict)
            ],
            "state_names": [
                item.get("name") for item in state if isinstance(item, dict)
            ],
        }
    rules = mechanism.get("phase_rules")
    rules = rules if isinstance(rules, list) else []
    return {
        "effect_kind": mechanism.get("effect_goal"),
        "phases": [
            item.get("phase") for item in rules if isinstance(item, dict)
        ],
        "evaluators": [
            item.get("decision_evaluator")
            for item in rules
            if isinstance(item, dict)
        ],
        "state_names": [],
    }


def _hashes(paths: list[Path]) -> dict[str, str]:
    return {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
    }


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected a JSON object: {path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path.resolve()


def _required_object(value: dict[str, Any], name: str) -> dict[str, Any]:
    item = value.get(name)
    if not isinstance(item, dict):
        raise TypeError(f"{name} must be an object")
    return dict(item)


def _required_string(value: dict[str, Any], name: str) -> str:
    item = value.get(name)
    if not isinstance(item, str) or not item.strip():
        raise TypeError(f"{name} must be a non-empty string")
    return item


def main(argv: Sequence[str] | None = None) -> None:
    """Run both Distillers and print their normalized comparison."""

    args = parse_args(argv)
    summary = asyncio.run(compare_distillers(args))
    for name, arm in summary["arms"].items():
        usage = arm["usage"]
        print(
            f"{name}: status={arm['status']}, outcome={arm['outcome']}, "
            f"requests={usage['requests']}, tokens={usage['total_tokens']}"
        )
    print(f"summary={args.output_dir.resolve() / 'summary.json'}")


if __name__ == "__main__":
    main()
