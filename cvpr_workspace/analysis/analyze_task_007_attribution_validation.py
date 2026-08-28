"""Analyze structural compliance and prepare manual TASK-007 quality review."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    suite = _read_json(args.cases.resolve())
    run_dir = args.run_dir.resolve()
    summary = _read_json(run_dir / "summary.json")
    cases = {
        _required_string(case, "case_id"): case
        for case in _required_list(suite, "cases")
    }
    records: list[dict[str, Any]] = []
    type_sets: dict[str, list[list[str]]] = defaultdict(list)

    for result in _required_list(summary, "results"):
        case_id = _required_string(result, "case_id")
        case = cases[case_id]
        artifact = _read_json(Path(_required_string(result, "artifact")))
        projection = _read_json(
            Path(_required_string(result, "input_projection"))
        )
        output = artifact.get("output")
        items = output.get("items", []) if isinstance(output, dict) else []
        actual_types = [
            str(item.get("experience_type"))
            for item in items
            if isinstance(item, dict)
        ]
        type_sets[case_id].append(actual_types)
        rubric = _required_object(case, "rubric")
        expected_types = _string_list(rubric, "expected_types")
        expected_capabilities = rubric.get("expected_capabilities", [])
        if not isinstance(expected_capabilities, list):
            raise TypeError("expected_capabilities must be a list")
        expected_teacher_role_id = rubric.get("expected_teacher_role_id")
        tool_calls = _experience_tool_calls(artifact.get("tool_calls"))
        successful_calls = [call for call in tool_calls if call["succeeded"]]
        failed_calls = [call for call in tool_calls if not call["succeeded"]]
        views = [call.get("view") for call in tool_calls]
        successful_views = [call.get("view") for call in successful_calls]
        expectation = _required_string(rubric, "tool_expectation")
        tool_expectation_passed = (
            (expectation == "required" and bool(successful_calls))
            or (expectation == "none" and not tool_calls)
            or expectation == "optional"
        )
        acceptable_views = set(_string_list(rubric, "acceptable_views"))
        call_keys = [
            (call.get("evidence_ref"), call.get("view"))
            for call in tool_calls
        ]
        duplicate_reads = len(call_keys) != len(set(call_keys))
        teacher_items = [
            item
            for item in items
            if isinstance(item, dict)
            and item.get("experience_type") == "teacher_work"
        ]
        teacher_subject_passed = (
            expected_teacher_role_id is None
            or (
                len(teacher_items) == 1
                and teacher_items[0].get("teacher_role_id")
                == expected_teacher_role_id
            )
        )
        output_limits_passed = all(_output_limits(item) for item in items)
        capability_items = [
            item
            for item in items
            if isinstance(item, dict)
            and item.get("experience_type") == "student_capability"
        ]
        capability_fact_shape_passed = all(
            _capability_fact_shape(item) for item in capability_items
        )
        actual_capabilities = [
            {
                "decision_scope": item.get("decision_scope"),
                "capability_area": item.get("capability_area"),
                "elicitation_scope": item.get("elicitation_scope"),
            }
            for item in capability_items
        ]
        capability_contract_passed = (
            actual_capabilities == expected_capabilities
            if expected_capabilities
            else True
        )
        projection_rows = projection.get("artifact_projection")
        projection_provenance_passed = (
            isinstance(projection_rows, list)
            and bool(projection_rows)
            and all(_valid_projection_row(row) for row in projection_rows)
        )
        records.append(
            {
                "case_id": case_id,
                "repetition": result.get("repetition"),
                "status": result.get("status"),
                "artifact": result.get("artifact"),
                "input_projection": result.get("input_projection"),
                "expected_types": expected_types,
                "actual_types": actual_types,
                "type_contract_passed": actual_types == expected_types,
                "expected_teacher_role_id": expected_teacher_role_id,
                "teacher_subject_passed": teacher_subject_passed,
                "output_limits_passed": output_limits_passed,
                "capability_fact_shape_passed": capability_fact_shape_passed,
                "expected_capabilities": expected_capabilities,
                "actual_capabilities": actual_capabilities,
                "capability_contract_passed": capability_contract_passed,
                "projection_provenance_passed": projection_provenance_passed,
                "tool_call_count": len(tool_calls),
                "successful_tool_call_count": len(successful_calls),
                "failed_tool_call_count": len(failed_calls),
                "tool_views": views,
                "successful_tool_views": successful_views,
                "tool_expectation": expectation,
                "tool_expectation_passed": tool_expectation_passed,
                "tool_views_passed": all(view in acceptable_views for view in views),
                "duplicate_evidence_reads": duplicate_reads,
                "tool_fuse_not_reached": len(tool_calls) < 20,
                "tool_protocol_passed": (
                    not failed_calls
                    and not duplicate_reads
                    and len(tool_calls) < 20
                ),
                "output": output,
                "primary_layers": rubric.get("primary_layers"),
                "required_concepts": rubric.get("required_concepts"),
                "forbidden_attributions": rubric.get("forbidden_attributions"),
            }
        )

    stability = {
        case_id: {
            "type_sets": values,
            "type_stable": all(value == values[0] for value in values[1:]),
        }
        for case_id, values in type_sets.items()
        if len(values) > 1
    }
    audit = {
        "schema_version": "1.0",
        "suite_id": suite.get("suite_id"),
        "run_count": len(records),
        "completed_count": sum(
            record["status"] == "completed" for record in records
        ),
        "failed_count": sum(record["status"] == "failed" for record in records),
        "type_contract_pass_count": sum(
            record["type_contract_passed"] for record in records
        ),
        "teacher_subject_pass_count": sum(
            record["teacher_subject_passed"] for record in records
        ),
        "output_limits_pass_count": sum(
            record["output_limits_passed"] for record in records
        ),
        "capability_fact_shape_pass_count": sum(
            record["capability_fact_shape_passed"] for record in records
        ),
        "capability_contract_pass_count": sum(
            record["capability_contract_passed"] for record in records
        ),
        "projection_provenance_pass_count": sum(
            record["projection_provenance_passed"] for record in records
        ),
        "tool_expectation_pass_count": sum(
            record["tool_expectation_passed"] for record in records
        ),
        "tool_view_pass_count": sum(
            record["tool_views_passed"] for record in records
        ),
        "tool_protocol_pass_count": sum(
            record["tool_protocol_passed"] for record in records
        ),
        "stability": stability,
        "records": records,
    }
    _write_json(run_dir / "structural_audit.json", audit)
    (run_dir / "quality_review_template.md").write_text(
        _render_review(records, stability),
        encoding="utf-8",
    )


def _experience_tool_calls(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    calls: list[dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, dict):
            continue
        name = raw.get("name") or raw.get("tool_name")
        function = raw.get("function")
        if name is None and isinstance(function, dict):
            name = function.get("name")
        if name != "inspect_experience_evidence":
            continue
        arguments = raw.get("arguments", {})
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}
        arguments = arguments if isinstance(arguments, dict) else {}
        calls.append(
            {
                "evidence_ref": arguments.get("evidence_ref"),
                "view": arguments.get("view"),
                "selectors": arguments.get("selectors"),
                "succeeded": not bool(
                    isinstance(raw.get("metadata"), dict)
                    and raw["metadata"].get("error_type")
                ),
            }
        )
    return calls


def _render_review(
    records: list[dict[str, Any]],
    stability: dict[str, dict[str, Any]],
) -> str:
    lines = [
        "# TASK-007 真实归因质量人工审计模板",
        "",
        "每个 Run 需对 causal attribution、route discipline、evidence fidelity、actionability 和 applicability 分别填写 pass/partial/fail，并引用具体输出文本。",
        "",
    ]
    for record in records:
        lines.extend(
            [
                f"## {record['case_id']} / run {record['repetition']}",
                "",
                f"- Artifact: `{record['artifact']}`",
                f"- Input projection: `{record['input_projection']}`; passed: "
                f"`{record['projection_provenance_passed']}`",
                f"- Expected primary layers: `{record['primary_layers']}`",
                f"- Expected types: `{record['expected_types']}`",
                f"- Actual types: `{record['actual_types']}`",
                f"- Expected Teacher subject: "
                f"`{record['expected_teacher_role_id']}`; passed: "
                f"`{record['teacher_subject_passed']}`",
                f"- Tool views: `{record['tool_views']}`; successful: "
                f"`{record['successful_tool_views']}`; failed calls: "
                f"`{record['failed_tool_call_count']}`",
                f"- Duplicate reads: `{record['duplicate_evidence_reads']}`; "
                f"fuse not reached: `{record['tool_fuse_not_reached']}`",
                f"- Capability conditional fact shape: "
                f"`{record['capability_fact_shape_passed']}`",
                f"- Expected capability keys: "
                f"`{record['expected_capabilities']}`",
                f"- Actual capability keys: `{record['actual_capabilities']}`; "
                f"passed: `{record['capability_contract_passed']}`",
                f"- Required concepts: `{record['required_concepts']}`",
                f"- Forbidden attributions: `{record['forbidden_attributions']}`",
                f"- Output: `{json.dumps(record['output'], ensure_ascii=False)}`",
                "- causal attribution: TODO",
                "- route discipline: TODO",
                "- evidence fidelity: TODO",
                "- actionability: TODO",
                "- applicability: TODO",
                "- overall: TODO",
                "- notes: TODO",
                "",
            ]
        )
    lines.extend(["## Anchor 稳定性", ""])
    for case_id, value in stability.items():
        lines.append(
            f"- `{case_id}`: type_sets=`{value['type_sets']}`, "
            f"type_stable=`{value['type_stable']}`; semantic stability: TODO"
        )
    lines.append("")
    return "\n".join(lines)


def _valid_projection_row(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    return (
        isinstance(value.get("target_field"), str)
        and isinstance(value.get("artifact_path"), str)
        and isinstance(value.get("json_pointer"), str)
        and value.get("operation") in {"copy_text", "copy_json"}
        and isinstance(value.get("copied_value"), str)
        and bool(value.get("copied_value"))
    )


def _output_limits(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    if item.get("experience_type") == "student_capability":
        observed = item.get("observed_limitation")
        conditions = item.get("conditions")
        return (
            isinstance(observed, str)
            and len(observed) <= 300
            and isinstance(conditions, str)
            and len(conditions) <= 220
        )
    lesson = item.get("lesson")
    applicability = item.get("applicability")
    return (
        isinstance(lesson, str)
        and len(lesson) <= 500
        and isinstance(applicability, str)
        and len(applicability) <= 300
    )


def _capability_fact_shape(item: dict[str, Any]) -> bool:
    observed = item.get("observed_limitation")
    conditions = item.get("conditions")
    if not isinstance(observed, str) or not isinstance(conditions, str):
        return False
    if item.get("decision_scope") != (
        "additional_retrieval_need_before_final_answer"
    ):
        return False
    if item.get("capability_area") not in {
        "question_entity_structure",
        "query_coverage",
        "explicit_evidence_support",
        "answer_commitment",
    }:
        return False
    if item.get("elicitation_scope") not in {
        "fixed_prompt",
        "limited_variants",
        "targeted_variants",
    }:
        return False
    normalized = f"{observed} {conditions}".lower()
    forbidden = (
        "do not ",
        "should ",
        "must ",
        "researcher",
        "compiler",
        "reviewer",
        "candidate",
        "trial_",
        "prompt text",
    )
    return not any(term in normalized for term in forbidden)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"JSON file must contain an object: {path}")
    return value


def _required_string(value: dict[str, Any], field: str) -> str:
    item = value.get(field)
    if not isinstance(item, str) or not item.strip():
        raise TypeError(f"{field} must be a non-empty string")
    return item


def _required_list(value: dict[str, Any], field: str) -> list[Any]:
    item = value.get(field)
    if not isinstance(item, list):
        raise TypeError(f"{field} must be a list")
    return item


def _required_object(value: dict[str, Any], field: str) -> dict[str, Any]:
    item = value.get(field)
    if not isinstance(item, dict):
        raise TypeError(f"{field} must be an object")
    return item


def _string_list(value: dict[str, Any], field: str) -> list[str]:
    items = _required_list(value, field)
    if not all(isinstance(item, str) for item in items):
        raise TypeError(f"{field} must contain only strings")
    return items


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
