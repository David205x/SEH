"""Check TASK-006 minimal Teacher Role scope and audit-only provenance."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import fields
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from search_harness.evolution.research.resources.base import (  # noqa: E402
    EvaluationEvidenceStore,
    TeacherResources,
    TrialEvidenceStore,
)
from search_harness.evolution.research.roles.loader import (  # noqa: E402
    load_teacher_agent_spec,
)
from search_harness.evolution.research.roles.provenance import (  # noqa: E402
    TeacherRoleScope,
    base_prompt_digest,
    input_view_digest,
    model_input_view,
    teacher_role_scope,
)
from search_harness.evolution.research.roles.spec import (  # noqa: E402
    TeacherPromptSpec,
)


TEACHER_ROOT = PROJECT_ROOT / "harness_templates" / "teacher"
HEX_DIGEST = re.compile(r"^[0-9a-f]{64}$")


def run_check() -> dict[str, Any]:
    """Assemble every active Teacher template without making model requests."""

    resources = _resources()
    role_results: list[dict[str, Any]] = []
    for template_root in sorted(
        path
        for path in TEACHER_ROOT.iterdir()
        if path.is_dir() and not path.name.startswith("__")
    ):
        role_id = template_root.name
        spec = load_teacher_agent_spec(
            template_root,
            runtime_context=resources,
            role_id=role_id,
        )
        prompt_digest = base_prompt_digest(spec.prompt)
        _require_digest(prompt_digest, f"{role_id} base prompt")
        scope = teacher_role_scope(
            role_id=spec.role.role_id,
            role_contract_version=spec.role.version,
            model={
                "provider": "development_check",
                "model_id": "teacher-check",
                "temperature": 0.2,
            },
        )
        model_view = model_input_view(
            messages=[
                {"role": "system", "content": spec.prompt.instructions},
                {"role": "user", "content": "compact check input"},
            ],
            tools=spec.tools.tools,
        )
        view_digest = input_view_digest([model_view])
        _require_digest(view_digest, f"{role_id} input view")
        role_results.append(
            {
                "role_id": scope.role_id,
                "role_contract_version": scope.role_contract_version,
                "model_provider": scope.model_provider,
                "model_id": scope.model_id,
                "base_prompt_digest": prompt_digest,
                "input_view_digest": view_digest,
            }
        )

    _check_scope_is_minimal()
    _check_digest_boundaries()
    _check_no_rejected_identity_fields()
    return {
        "schema_version": "1.0",
        "check_id": "CHECK-STAGE-001-ROLE-IDENTITY",
        "status": "passed",
        "scope": "development_check_only",
        "teacher_roles": role_results,
        "scope_fields": [item.name for item in fields(TeacherRoleScope)],
        "assertions": {
            "all_templates_assembled": True,
            "hard_scope_is_minimal": True,
            "digests_are_audit_only": True,
            "model_input_snapshot_is_detached": True,
            "no_duplicate_role_identity_object": True,
            "no_input_or_tool_contract_scope": True,
            "external_api_called": False,
        },
    }


def _resources() -> TeacherResources:
    evaluation = EvaluationEvidenceStore(
        report_dir=Path("report"),
        rollout_file=Path("rollout.jsonl"),
        summary={},
        cases={},
        rollouts={},
        student_template_root=Path("components"),
        harness_manifest={
            "harness_id": "student",
            "tools": [],
            "extensions": [],
        },
    )
    return TeacherResources(
        evaluation=evaluation,
        trials=TrialEvidenceStore(trials={"trial_001": {}}),
        intervention=object(),  # type: ignore[arg-type]
        compiler=object(),  # type: ignore[arg-type]
        candidate_review=object(),  # type: ignore[arg-type]
    )


def _check_scope_is_minimal() -> None:
    actual = {item.name for item in fields(TeacherRoleScope)}
    expected = {
        "role_id",
        "role_contract_version",
        "model_provider",
        "model_id",
    }
    if actual != expected:
        raise AssertionError(
            f"TeacherRoleScope fields differ: {sorted(actual)}"
        )


def _check_digest_boundaries() -> None:
    prompt = TeacherPromptSpec(
        instructions="Inspect evidence.",
        user_template="{{role_input}}\n{{resource_context}}",
    )
    clone = TeacherPromptSpec(
        instructions="Inspect evidence.",
        user_template="{{role_input}}\n{{resource_context}}",
    )
    if base_prompt_digest(prompt) != base_prompt_digest(clone):
        raise AssertionError("equal Prompt content produced different digests")

    messages = [
        {"role": "system", "content": "base"},
        {"role": "user", "content": "compact"},
    ]
    view = model_input_view(messages=messages, tools=())
    before = input_view_digest([view])
    messages[-1]["content"] = "outside mutation"
    if before != input_view_digest([view]):
        raise AssertionError("Model Input view was not detached")
    changed = model_input_view(
        messages=[
            {"role": "system", "content": "base"},
            {"role": "user", "content": "changed compact input"},
        ],
        tools=(),
    )
    if before == input_view_digest([changed]):
        raise AssertionError("changed Model Input retained the same digest")


def _check_no_rejected_identity_fields() -> None:
    sources = [
        PROJECT_ROOT
        / "search_harness"
        / "evolution"
        / "research"
        / "roles"
        / "provenance.py",
        PROJECT_ROOT
        / "search_harness"
        / "evolution"
        / "research"
        / "roles"
        / "role_execution.py",
        PROJECT_ROOT
        / "search_harness"
        / "evolution"
        / "research"
        / "intervention"
        / "role_runner.py",
    ]
    forbidden = (
        '"role_identity"',
        "input_contract_id",
        "tool_contract_digest",
        "tool_contract_version",
    )
    for source in sources:
        text = source.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                raise AssertionError(f"forbidden field {token} in {source}")


def _require_digest(value: str, label: str) -> None:
    if HEX_DIGEST.fullmatch(value) is None:
        raise AssertionError(f"{label} is not a SHA-256 content digest")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT
        / "cvpr_workspace"
        / "analysis"
        / "stage_001_role_identity_check.json",
    )
    args = parser.parse_args()
    result = run_check()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
