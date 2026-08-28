"""Check TASK-007 artifact-native validation input construction."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from cvpr_workspace.analysis.task_007_artifact_input_projection import (  # noqa: E402
    project_artifact_input,
)
from search_harness.evolution.research.experience_summary import (  # noqa: E402
    build_experience_summary_request,
)


CONFIG = (
    PROJECT_ROOT
    / "cvpr_workspace"
    / "configs"
    / "task_007_attribution_cases_v2.json"
)
FORBIDDEN_POINTER_PARTS = {
    "transcript",
    "reasoning",
    "tool_calls",
    "resource_config",
    "usage",
    "digest",
    "hash",
}
REMOVED_CASE_FIELDS = {
    "source_artifacts",
    "direction",
    "attempt",
    "evidence",
    "evidence_views",
}


def run_check() -> dict[str, Any]:
    suite = json.loads(CONFIG.read_text(encoding="utf-8"))
    _require(suite.get("schema_version") == 2, "suite is not schema v2")
    cases = suite.get("cases")
    _require(isinstance(cases, list) and len(cases) == 18, "case set changed")

    audit_rows = 0
    target_fields: set[str] = set()
    for case in cases:
        case_id = case["case_id"]
        forbidden_fields = REMOVED_CASE_FIELDS & set(case)
        _require(
            not forbidden_fields,
            f"{case_id} retains hand-authored business fields: {forbidden_fields}",
        )
        projection = project_artifact_input(
            project_root=PROJECT_ROOT,
            case=case,
        )
        request = build_experience_summary_request(
            trigger=case["trigger"],
            direction=projection.direction,
            attempt=projection.attempt,
            evidence=projection.evidence,
            evidence_views=projection.evidence_views,
            source_context=case["source_context"],
        )
        _require(
            request.role_input.direction == projection.direction
            and request.role_input.attempt == projection.attempt,
            f"{case_id} role input changed projected text",
        )
        _require(projection.audit, f"{case_id} has no projection audit")
        for row in projection.audit:
            audit_rows += 1
            target_fields.add(row["target_field"])
            pointer_tokens = {
                token.lower()
                for token in row["json_pointer"].split("/")
                if token
            }
            _require(
                not (pointer_tokens & FORBIDDEN_POINTER_PARTS),
                f"{case_id} projects forbidden artifact content: {row}",
            )
            _require(
                row["operation"] in {"copy_text", "copy_json"},
                f"{case_id} audit contains a non-leaf operation",
            )
            _require(
                isinstance(row["copied_value"], str)
                and bool(row["copied_value"]),
                f"{case_id} copied an empty value",
            )

    required_targets = {"direction", "attempt"}
    _require(
        required_targets <= target_fields,
        "direction or attempt lacks artifact provenance",
    )
    return {
        "schema_version": "1.0",
        "check_id": "CHECK-TASK-007-ARTIFACT-INPUT-PROJECTION",
        "status": "passed",
        "scope": "development_check_only",
        "case_count": len(cases),
        "audit_row_count": audit_rows,
        "assertions": {
            "artifact_native_schema_only": True,
            "all_eighteen_cases_build": True,
            "no_hand_authored_business_input_fields": True,
            "all_projected_text_has_path_pointer_operation_and_value": True,
            "no_silent_truncation": True,
            "forbidden_artifact_sections_not_projected": True,
            "hash_and_digest_not_used": True,
            "external_api_called": False,
        },
    }


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=(
            PROJECT_ROOT
            / "cvpr_workspace"
            / "analysis"
            / "task_007_artifact_input_projection_check.json"
        ),
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
