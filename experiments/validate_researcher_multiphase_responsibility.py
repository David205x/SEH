"""A/B test a pluggable Researcher multi-phase responsibility prompt."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from search_harness.evolution.research.resources.base import (
    TeacherResourceConfig,
)
from search_harness.evolution.research.roles.contracts import (
    FailureDirection,
    InterventionHypothesis,
)
from search_harness.evolution.research.roles.native_chat_runner import (
    NativeChatRoleRunner,
    TeacherRoleRunFailed,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FORMAL_TEMPLATE = (
    PROJECT_ROOT / "harness_templates" / "teacher" / "hypothesis_researcher"
)
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "runs"
    / "experiments"
    / "20260817_researcher_multiphase_stateful"
)
PROMPT_MARKER = "## Boundary decision procedure"
RESPONSIBILITY_SECTION = """## Multi-phase contract discipline

Apply this section only when the selected hypothesis genuinely needs Trial
state or more than one phase directive. Do not add state, phases, or repeated
activations merely to satisfy this section; keep a sufficient single-phase
plan simple.

When one activation requires both a Trial-state update and a terminal context,
stage, or control action, write the instruction in executable order: first
update the named state values alone and wait for that Tool Result; then submit
the terminal action in a later Worker response. Never describe state as updated
only in an action reason. A later condition must name the exact prior state it
depends on and must re-check current phase-visible evidence.

Define every readiness transition by an observable evidence predicate over the
current result or context. A search count, reached phase, or completed action
does not by itself prove that an evidence obligation is satisfied. If the live
result does not meet the predicate, keep the obligation unresolved and specify
the bounded next action or safe final control. Make the complete causal chain,
including an unsupported-result branch, distinguishable in success and
falsifier evidence.

"""
STATEFUL_CASE_ADDENDUM = """## Controlled stateful delayed-control exercise

For this case only, test whether the hypothesis can preserve an early risk
observation without changing Student-visible context, then intervene only if
the Student fails to recover naturally. This measurement requirement makes a
two-phase Trial-state plan necessary; do not replace it with an equivalent
single-phase intervention.

Submit exactly two phase directives in this causal order:

1. At `post_tool`, when the first comparison search covers only one named
   entity and the other entity has not been queried, inspect the active result.
   Instruct the Worker to call `update_trial_state` alone with
   `one_sided_result_observed=true` and the generic
   `missing_entity_name`, wait for `TRIAL_STATE_UPDATED`, then call
   `continue_without_change` in a later response. Do not edit
   Student-visible context in this phase.
2. At `pre_final`, require both the exact prior Trial state and current
   phase-visible evidence that no later search targeted the recorded missing
   entity and that the candidate still resolves the comparison from one-sided
   evidence. Only then defer once with answer-neutral feedback requiring the
   missing search. Natural recovery must leave the final decision unchanged.

Use `post_tool` as the fork anchor. Define success and falsifier for the full
state hand-off and delayed-control path. Preserve every caveat in the supplied
Failure Direction; this controlled shape is not evidence that production
hypotheses should generally prefer Trial state.
"""


@dataclass(frozen=True)
class Case:
    """One frozen Failure Direction and its matching evaluation resources."""

    name: str
    source_run: Path
    failure_work: str
    prompt_addendum: str | None = None
    expected_phases: tuple[str, ...] = ()
    expected_state_keys: tuple[str, ...] = ()


CASES = (
    Case(
        name="one_sided_comparison",
        source_run=(
            PROJECT_ROOT
            / "runs"
            / "evolution"
            / "20260815_qwen3-8b_hook_feasibility"
        ),
        failure_work="analyze_failure-f84a7c940bac3611",
    ),
    Case(
        name="bundled_missing_relation",
        source_run=(
            PROJECT_ROOT
            / "runs"
            / "evolution"
            / "20260815_qwen3-8b_fullchain"
        ),
        failure_work="analyze_failure-983acdbb56e90bc7",
    ),
    Case(
        name="stateful_delayed_control",
        source_run=(
            PROJECT_ROOT
            / "runs"
            / "evolution"
            / "20260815_qwen3-8b_hook_feasibility"
        ),
        failure_work="analyze_failure-f84a7c940bac3611",
        prompt_addendum=STATEFUL_CASE_ADDENDUM,
        expected_phases=("post_tool", "pre_final"),
        expected_state_keys=(
            "one_sided_result_observed",
            "missing_entity_name",
        ),
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument(
        "--variant",
        action="append",
        choices=("baseline", "responsibility"),
    )
    parser.add_argument(
        "--case",
        action="append",
        choices=tuple(item.name for item in CASES),
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    if args.repetitions < 1:
        raise ValueError("repetitions must be positive")
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    templates_root = output_dir / "templates"
    templates = _prepare_templates(templates_root)
    selected_variants = args.variant or ["baseline", "responsibility"]
    selected_cases = [
        item for item in CASES if not args.case or item.name in args.case
    ]
    case_templates = _prepare_case_templates(
        templates_root / "case_overrides",
        base_templates=templates,
        cases=selected_cases,
        variants=selected_variants,
    )
    manifest = {
        "schema_version": 1,
        "repetitions": args.repetitions,
        "variants": {
            name: {
                "template_root": str(path),
                "system_prompt_sha256": _digest(
                    path / "prompt" / "system.md"
                ),
            }
            for name, path in templates.items()
            if name in selected_variants
        },
        "cases": [
            {
                "name": item.name,
                "source_run": str(item.source_run.resolve()),
                "failure_work": item.failure_work,
                "prompt_addendum_sha256": (
                    _text_digest(item.prompt_addendum)
                    if item.prompt_addendum is not None
                    else None
                ),
                "template_roots": {
                    variant: str(case_templates[(item.name, variant)])
                    for variant in selected_variants
                },
                "expected_phases": list(item.expected_phases),
                "expected_state_keys": list(item.expected_state_keys),
            }
            for item in selected_cases
        ],
    }
    _write_json(output_dir / "manifest.json", manifest)

    runner = NativeChatRoleRunner(env_file=args.env_file.resolve())
    results: list[dict[str, Any]] = []
    for case in selected_cases:
        failure, resources = _load_case(case)
        for variant in selected_variants:
            tasks = [
                _run_once(
                    runner=runner,
                    template_root=case_templates[(case.name, variant)],
                    failure=failure,
                    resources=resources,
                    output_path=(
                        output_dir
                        / variant
                        / case.name
                        / f"run_{repetition:03d}.json"
                    ),
                    variant=variant,
                    case_name=case.name,
                    repetition=repetition,
                    expected_phases=case.expected_phases,
                    expected_state_keys=case.expected_state_keys,
                )
                for repetition in range(1, args.repetitions + 1)
            ]
            batch = await asyncio.gather(*tasks)
            results.extend(batch)
            print(
                f"completed variant={variant} case={case.name} "
                f"runs={len(batch)}",
                flush=True,
            )

    _write_json(
        output_dir / "summary.json",
        {
            "schema_version": 1,
            "manifest": str((output_dir / "manifest.json").resolve()),
            "results": results,
        },
    )


async def _run_once(
    *,
    runner: NativeChatRoleRunner,
    template_root: Path,
    failure: FailureDirection,
    resources: TeacherResourceConfig,
    output_path: Path,
    variant: str,
    case_name: str,
    repetition: int,
    expected_phases: tuple[str, ...],
    expected_state_keys: tuple[str, ...],
) -> dict[str, Any]:
    try:
        artifact = await runner.run(
            template_root=template_root,
            role_id="hypothesis_researcher",
            role_version=1,
            role_input={
                "problem_direction": failure.model_dump(mode="json")
            },
            resource_config=resources,
        )
        hypothesis = InterventionHypothesis.model_validate(
            artifact.get("output")
        )
        _write_json(output_path, artifact)
        return _summary(
            artifact=artifact,
            hypothesis=hypothesis,
            artifact_path=output_path.resolve(),
            variant=variant,
            case_name=case_name,
            repetition=repetition,
            expected_phases=expected_phases,
            expected_state_keys=expected_state_keys,
        )
    except TeacherRoleRunFailed as exc:
        _write_json(output_path, exc.failure_artifact)
        return {
            "variant": variant,
            "case": case_name,
            "repetition": repetition,
            "status": "role_failed",
            "artifact": str(output_path.resolve()),
            "error": str(exc),
            "usage": exc.failure_artifact.get("usage"),
        }


def _summary(
    *,
    artifact: dict[str, Any],
    hypothesis: InterventionHypothesis,
    artifact_path: Path,
    variant: str,
    case_name: str,
    repetition: int,
    expected_phases: tuple[str, ...],
    expected_state_keys: tuple[str, ...],
) -> dict[str, Any]:
    output = hypothesis.model_dump(mode="json")
    phase_plan = output["phase_plan"]
    instructions = [str(item["instruction"]) for item in phase_plan]
    conditions = [
        str(item["activation_condition"]) for item in phase_plan
    ]
    combined = "\n".join([*instructions, *conditions]).lower()
    state_markers = _trial_state_markers(combined)
    state_keys = [key for key in expected_state_keys if key in combined]
    usage = artifact.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    return {
        "variant": variant,
        "case": case_name,
        "repetition": repetition,
        "status": "completed",
        "artifact": str(artifact_path),
        "fork_phase": output["fork_phase"],
        "phases": [str(item["phase"]) for item in phase_plan],
        "phase_count": len(phase_plan),
        "max_activations": [
            int(item["max_activations"]) for item in phase_plan
        ],
        "expected_phases": list(expected_phases),
        "phase_shape_matches": (
            not expected_phases
            or tuple(str(item["phase"]) for item in phase_plan)
            == expected_phases
        ),
        "expected_state_keys": list(expected_state_keys),
        "observed_state_keys": state_keys,
        "trial_state_markers": state_markers,
        "mentions_trial_state": bool(state_markers),
        "output": output,
        "tool_names": [
            str(item.get("name"))
            for item in artifact.get("tool_calls", [])
            if isinstance(item, dict)
        ],
        "usage": {
            "requests": usage.get("requests"),
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "total_tokens": usage.get("total_tokens"),
        },
    }


def _prepare_templates(root: Path) -> dict[str, Path]:
    if root.exists():
        baseline = root / "baseline"
        responsibility = root / "responsibility"
        baseline_prompt = baseline / "prompt" / "system.md"
        responsibility_prompt = responsibility / "prompt" / "system.md"
        if not baseline_prompt.is_file() or not responsibility_prompt.is_file():
            raise FileExistsError(
                "experiment template directory is incomplete and will not be "
                f"overwritten: {root}"
            )
        formal_prompt = (
            FORMAL_TEMPLATE / "prompt" / "system.md"
        ).read_text(encoding="utf-8")
        if baseline_prompt.read_text(encoding="utf-8") != formal_prompt:
            raise ValueError("existing baseline Prompt differs from formal Prompt")
        expected = _responsibility_prompt(formal_prompt)
        if responsibility_prompt.read_text(encoding="utf-8") != expected:
            raise ValueError(
                "existing responsibility Prompt differs from frozen variant"
            )
        return {
            "baseline": baseline.resolve(),
            "responsibility": responsibility.resolve(),
        }
    baseline = root / "baseline"
    responsibility = root / "responsibility"
    shutil.copytree(FORMAL_TEMPLATE, baseline)
    shutil.copytree(FORMAL_TEMPLATE, responsibility)
    prompt_path = responsibility / "prompt" / "system.md"
    prompt = prompt_path.read_text(encoding="utf-8")
    prompt_path.write_text(
        _responsibility_prompt(prompt),
        encoding="utf-8",
    )
    harness_path = responsibility / "harness.json"
    harness = _read_json(harness_path)
    harness["harness_id"] = (
        f"{harness['harness_id']}_multiphase_responsibility"
    )
    _write_json(harness_path, harness)
    return {
        "baseline": baseline.resolve(),
        "responsibility": responsibility.resolve(),
    }


def _prepare_case_templates(
    root: Path,
    *,
    base_templates: dict[str, Path],
    cases: list[Case],
    variants: list[str],
) -> dict[tuple[str, str], Path]:
    """为需要额外受控约束的 case 建立冻结 shadow Template。"""

    prepared: dict[tuple[str, str], Path] = {}
    for case in cases:
        for variant in variants:
            base = base_templates[variant]
            if case.prompt_addendum is None:
                prepared[(case.name, variant)] = base
                continue
            destination = root / case.name / variant
            expected_user_prompt = _case_user_prompt(
                (base / "prompt" / "user.md").read_text(encoding="utf-8"),
                case.prompt_addendum,
            )
            if destination.exists():
                user_prompt = destination / "prompt" / "user.md"
                system_prompt = destination / "prompt" / "system.md"
                if not user_prompt.is_file() or not system_prompt.is_file():
                    raise FileExistsError(
                        "case Template directory is incomplete and will not be "
                        f"overwritten: {destination}"
                    )
                if user_prompt.read_text(encoding="utf-8") != expected_user_prompt:
                    raise ValueError(
                        "existing case user Prompt differs from frozen variant: "
                        f"{destination}"
                    )
                if system_prompt.read_text(encoding="utf-8") != (
                    base / "prompt" / "system.md"
                ).read_text(encoding="utf-8"):
                    raise ValueError(
                        "existing case system Prompt differs from base variant: "
                        f"{destination}"
                    )
            else:
                shutil.copytree(base, destination)
                (destination / "prompt" / "user.md").write_text(
                    expected_user_prompt,
                    encoding="utf-8",
                )
            prepared[(case.name, variant)] = destination.resolve()
    return prepared


def _responsibility_prompt(prompt: str) -> str:
    if prompt.count(PROMPT_MARKER) != 1:
        raise ValueError("Researcher prompt boundary marker is not unique")
    return prompt.replace(
        PROMPT_MARKER,
        f"{RESPONSIBILITY_SECTION}{PROMPT_MARKER}",
    )


def _case_user_prompt(prompt: str, addendum: str) -> str:
    return f"{prompt.rstrip()}\n\n{addendum.strip()}\n"


def _trial_state_markers(text: str) -> list[str]:
    normalized = text.lower()
    markers = []
    if any(
        marker in normalized
        for marker in ("trial state", "trial-state", "trial_state")
    ):
        markers.append("trial_state")
    if "update_trial_state" in normalized:
        markers.append("update_trial_state")
    return markers


def _load_case(
    case: Case,
) -> tuple[FailureDirection, TeacherResourceConfig]:
    source_run = case.source_run.resolve()
    failure_artifact = _read_json(
        source_run / "artifacts" / case.failure_work / "role.json"
    )
    failure = FailureDirection.model_validate(failure_artifact.get("output"))
    incumbent = _only_directory(source_run / "artifacts", "evaluate_incumbent-")
    return failure, TeacherResourceConfig(
        report_dir=incumbent / "report",
        rollout_file=incumbent / "report_rollouts.jsonl",
        student_template_root=source_run / "version_store" / "template",
    )


def _only_directory(root: Path, prefix: str) -> Path:
    matches = sorted(
        path
        for path in root.iterdir()
        if path.is_dir() and path.name.startswith(prefix)
    )
    if len(matches) != 1:
        raise ValueError(f"expected one {prefix} directory, got {len(matches)}")
    return matches[0]


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _text_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path.resolve()


if __name__ == "__main__":
    asyncio.run(main())
