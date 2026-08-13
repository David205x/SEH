"""A/B test formal and shadow Mechanism Distiller evidence views."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from statistics import mean
from typing import Any, Sequence

from search_harness.evolution.research.resources.base import TeacherResourceConfig
from search_harness.evolution.research.roles.native_chat_runner import (
    NativeChatRoleRunner,
    TeacherRoleRunFailed,
)


_ROOT = Path(__file__).resolve().parents[1]
_FORMAL = _ROOT / "harness_templates" / "teacher" / "mechanism_distiller"
_SHADOW = (
    _ROOT
    / "experiments"
    / "teacher_query_views"
    / "templates"
    / "mechanism_distiller"
)
_DRAFT_TOOLS = frozenset(
    {
        "create_mechanism_draft",
        "add_mechanism_phase",
        "complete_mechanism_draft",
        "set_mechanism_constraints",
        "probe_mechanism_evaluators",
        "validate_mechanism_draft",
    }
)
_EVIDENCE_TOOLS = frozenset(
    {
        "list_trial_evidence",
        "get_trial_evidence",
        "get_trial_event",
        "get_distillation_trial_detail",
    }
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--distiller-artifact",
        action="append",
        type=Path,
        default=[],
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--repetitions", type=int, default=3)
    return parser.parse_args(argv)


async def run_ab(args: argparse.Namespace) -> dict[str, Any]:
    sources = list(args.distiller_artifact)
    if not sources:
        raise ValueError("at least one Distiller artifact is required")
    if args.repetitions < 1:
        raise ValueError("repetitions must be positive")
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    hashes_before = _source_hashes(sources)
    cases = []
    for case_index, source_path in enumerate(sources, start=1):
        source = _read_json(source_path)
        pairs = []
        for repetition in range(1, args.repetitions + 1):
            formal, shadow = await asyncio.gather(
                _run_variant(
                    source=source,
                    template_root=_FORMAL,
                    env_file=args.env_file,
                    artifact_path=(
                        output_dir
                        / f"case_{case_index:02d}_mechanism_distiller"
                        / f"formal_{repetition:02d}.json"
                    ),
                ),
                _run_variant(
                    source=source,
                    template_root=_SHADOW,
                    env_file=args.env_file,
                    artifact_path=(
                        output_dir
                        / f"case_{case_index:02d}_mechanism_distiller"
                        / f"shadow_{repetition:02d}.json"
                    ),
                ),
            )
            pairs.append(
                {"repetition": repetition, "formal": formal, "shadow": shadow}
            )
        aggregate = {
            variant: _aggregate([item[variant]["metrics"] for item in pairs])
            for variant in ("formal", "shadow")
        }
        cases.append(
            {
                "case": f"case_{case_index:02d}_mechanism_distiller",
                "source_artifact": str(source_path.resolve()),
                "input_trial_count": len(
                    (source.get("input") or {}).get("trial_reviews", [])
                ),
                "runs": pairs,
                "aggregate": aggregate,
                "comparison": _comparison(aggregate),
            }
        )
    hashes_after = _source_hashes(sources)
    summary = {
        "schema_version": 1,
        "experiment": "mechanism_distiller_dossier_ab_v1",
        "pairing": (
            "Formal and shadow use the same saved Role Input, Resource Config, "
            "API configuration, role budget, output contract, draft tools and "
            "Hook evaluator backend. The shadow replaces repeated generic Trial "
            "queries with one complete Distillation Evidence Dossier and one "
            "exception-only detail tool."
        ),
        "cases": cases,
        "source_hashes_before": hashes_before,
        "source_hashes_after": hashes_after,
        "source_artifacts_unchanged": hashes_before == hashes_after,
    }
    _write_json(output_dir / "summary.json", summary)
    return summary


async def _run_variant(
    *,
    source: dict[str, Any],
    template_root: Path,
    env_file: Path,
    artifact_path: Path,
) -> dict[str, Any]:
    role = source.get("role")
    role = role if isinstance(role, dict) else {}
    try:
        artifact = await NativeChatRoleRunner(env_file=env_file).run(
            template_root=template_root,
            role_input=_required_object(source, "input"),
            resource_config=TeacherResourceConfig.model_validate(
                _required_object(source, "resource_config")
            ),
            role_id="mechanism_distiller",
            role_version=int(role.get("version", 1)),
        )
    except TeacherRoleRunFailed as exc:
        artifact = exc.failure_artifact
    _write_json(artifact_path, artifact)
    return {
        "artifact": str(artifact_path.resolve()),
        "metrics": extract_metrics(artifact),
        "output_summary": _output_summary(artifact),
    }


def extract_metrics(artifact: dict[str, Any]) -> dict[str, Any]:
    usage = artifact.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    calls = [item for item in artifact.get("tool_calls", []) if isinstance(item, dict)]
    terminal = [
        item for item in calls if item.get("name") == "submit_mechanism_distillation"
    ]
    evidence = [item for item in calls if item.get("name") in _EVIDENCE_TOOLS]
    draft = [item for item in calls if item.get("name") in _DRAFT_TOOLS]
    first_call = (usage.get("calls") or [{}])[0]
    return {
        "completed": artifact.get("output") is not None,
        "first_submit_passed": len(terminal) == 1 and artifact.get("output") is not None,
        "terminal_retries": max(0, len(terminal) - 1),
        "evidence_query_calls": len(evidence),
        "evidence_result_characters": sum(
            len(str(item.get("content", ""))) for item in evidence
        ),
        "detail_query_calls": sum(
            item.get("name") == "get_distillation_trial_detail" for item in evidence
        ),
        "draft_tool_calls": len(draft),
        "tool_errors": sum(_is_error(item.get("content")) for item in calls),
        "first_prompt_tokens": first_call.get("prompt_tokens"),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "requests": usage.get("requests"),
    }


def _output_summary(artifact: dict[str, Any]) -> dict[str, Any] | None:
    output = artifact.get("output")
    if not isinstance(output, dict):
        return None
    mechanisms = artifact.get("validated_mechanisms")
    mechanisms = mechanisms if isinstance(mechanisms, dict) else {}
    mechanism_ref = output.get("mechanism_ref")
    mechanism = mechanisms.get(mechanism_ref)
    mechanism = mechanism if isinstance(mechanism, dict) else None
    return {
        "decision": output.get("decision"),
        "mechanism_ref": mechanism_ref,
        "mechanism": mechanism,
        "rationale": output.get("rationale"),
        "next_obligation": output.get("next_obligation"),
    }


def _aggregate(values: list[dict[str, Any]]) -> dict[str, Any]:
    numeric = tuple(
        key
        for key in values[0]
        if key not in {"completed", "first_submit_passed"}
    )
    return {
        "runs": len(values),
        "completed": sum(bool(item["completed"]) for item in values),
        "first_submit_passed": sum(bool(item["first_submit_passed"]) for item in values),
        "means": {
            key: round(mean(float(item[key]) for item in values if item[key] is not None), 2)
            for key in numeric
            if any(item[key] is not None for item in values)
        },
    }


def _comparison(aggregate: dict[str, Any]) -> dict[str, Any]:
    formal = aggregate["formal"]
    shadow = aggregate["shadow"]
    return {
        "completed_rate": {
            "formal": formal["completed"] / formal["runs"],
            "shadow": shadow["completed"] / shadow["runs"],
        },
        "first_submit_pass_rate": {
            "formal": formal["first_submit_passed"] / formal["runs"],
            "shadow": shadow["first_submit_passed"] / shadow["runs"],
        },
        "total_token_ratio": _ratio(
            shadow["means"].get("total_tokens"),
            formal["means"].get("total_tokens"),
        ),
    }


def _source_hashes(sources: list[Path]) -> dict[str, str]:
    paths = set(sources)
    for source_path in sources:
        source = _read_json(source_path)
        for trial_file in (_required_object(source, "resource_config")).get(
            "trial_files", []
        ):
            paths.add(Path(trial_file))
    return {str(path.resolve()): _digest(path) for path in sorted(paths)}


def _is_error(content: object) -> bool:
    text = str(content or "").lower()
    return any(
        marker in text
        for marker in (
            "validation failed",
            "invalid json",
            "tool_input_error",
            "same fields still fail",
        )
    )


def _ratio(numerator: object, denominator: object) -> float | None:
    if not isinstance(numerator, (int, float)) or not isinstance(
        denominator, (int, float)
    ):
        return None
    if denominator == 0:
        return None
    return round(numerator / denominator, 4)


def _required_object(value: dict[str, Any], key: str) -> dict[str, Any]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise TypeError(f"artifact {key} must be an object")
    return item


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    summary = asyncio.run(run_ab(parse_args()))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
