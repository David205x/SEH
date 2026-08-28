"""Check TASK-007 v3 Experience Summarizer contracts and resources."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from search_harness.evolution.research.experience_summary import (  # noqa: E402
    MAX_EVIDENCE_RESULT_CHARACTERS,
    MAX_EVIDENCE_TOOL_CALLS,
    build_experience_summary_request,
)
from search_harness.evolution.research.resources.base import (  # noqa: E402
    TeacherResourceConfig,
)
from search_harness.evolution.research.roles.contracts import (  # noqa: E402
    ExperienceSummary,
    ExperienceSummaryInput,
)
from search_harness.evolution.research.roles.role_execution import (  # noqa: E402
    prepare_role_run,
    validate_role_output,
)


TEMPLATE_ROOT = (
    PROJECT_ROOT / "harness_templates" / "teacher" / "experience_summarizer"
)


def run_check() -> dict[str, Any]:
    """Run deterministic contract checks without a Teacher API call."""

    request = build_experience_summary_request(
        trigger="hook_feasibility.needs_research_revision",
        direction="Test the frozen Hook model's single-entity negative boundary.",
        attempt="Repeated valid real-prefix probes used both thinking modes.",
        evidence={
            "hook_review": {
                "outcome": (
                    "The Hook model crossed the expected-negative boundary."
                ),
                "comparison": (
                    "Identical valid negatives flipped across repetitions and "
                    "both disabled-thinking negatives were labeled positive."
                ),
                "boundary_facts": [
                    {
                        "kind": "reference_validity",
                        "status": "confirmed",
                        "statement": "The frozen contract labels these cases negative.",
                    },
                    {
                        "kind": "input_validity",
                        "status": "confirmed",
                        "statement": "Every probe used a valid frozen real prefix.",
                    },
                    {
                        "kind": "implementation_fidelity",
                        "status": "confirmed",
                        "statement": "The contract projection was faithful.",
                    },
                ],
            }
        },
        evidence_views={
            "hook_review": {
                "upstream_contract": [
                    {
                        "selector": "decision_contract",
                        "content": "DETAIL_SENTINEL: frozen three-label boundary.",
                    }
                ],
                "decision_trace": [
                    {
                        "selector": "trial_002",
                        "content": "Expected negative; observed negative then positive.",
                    }
                ],
            }
        },
        source_context={
            "classification": "provisional_negative",
            "decision_role": "hook_feasibility_reviewer",
            "decision": "needs_research_revision",
            "next_work_kinds": ["research_hypothesis"],
            "terminal_reason": None,
            "causal_neighbors": [
                "hook_feasibility_reviewer",
                "hypothesis_researcher",
                "student_or_hook_model",
            ],
        },
    )
    prepared = prepare_role_run(
        template_root=TEMPLATE_ROOT,
        role_input=request.role_input.model_dump(mode="json"),
        resource_config=TeacherResourceConfig(
            experience_summary=request.resources
        ),
        role_id="experience_summarizer",
        role_version=3,
    )
    _require(
        list(ExperienceSummaryInput.model_fields)
        == ["trigger", "route_target_role", "direction", "attempt", "evidence"],
        "ExperienceSummaryInput is not the approved five-field view",
    )
    _require(
        request.role_input.route_target_role == "hypothesis_researcher",
        "route target was not derived from actual next work",
    )
    _require(
        "DETAIL_SENTINEL" not in prepared.rendered_input,
        "program-only evidence leaked into the Initial Input",
    )
    _require(
        '"attribution_context"' in prepared.rendered_input
        and '"revision_families"' in prepared.rendered_input,
        "Evolution attribution context is absent from the Model Input",
    )
    _require(
        '"evidence_directory"' in prepared.rendered_input
        and '"trial_002"' in prepared.rendered_input,
        "authorized evidence directory is absent from the Model Input",
    )
    tools = prepared.spec.tools.tools
    _require(
        [item.name for item in tools] == ["inspect_experience_evidence"],
        "Experience Summarizer must expose exactly one evidence tool",
    )
    first = tools[0].run(
        {
            "evidence_ref": "hook_review",
            "view": "decision_trace",
            "selectors": ["trial_002"],
        }
    )
    tool_payload = json.loads(first.content)
    _require(
        len(first.content) <= MAX_EVIDENCE_RESULT_CHARACTERS,
        "evidence tool result exceeded its character budget",
    )
    for _ in range(MAX_EVIDENCE_TOOL_CALLS - 1):
        tools[0].run(
            {
                "evidence_ref": "hook_review",
                "view": "decision_trace",
                "selectors": [],
            }
        )
    overflow_error = None
    try:
        tools[0].run(
            {
                "evidence_ref": "hook_review",
                "view": "decision_trace",
                "selectors": [],
            }
        )
    except ValueError as exc:
        overflow_error = str(exc)
    _require(
        overflow_error is not None and "limit exceeded" in overflow_error,
        "the twenty-call evidence hard fuse did not reject call 21",
    )
    validate_role_output(
        ExperienceSummary.model_validate(
            {
                "items": [
                    {
                        "experience_type": "student_capability",
                        "decision_scope": (
                            "additional_retrieval_need_before_final_answer"
                        ),
                        "capability_area": "question_entity_structure",
                        "observed_limitation": (
                            "Treats an explicit single-entity negative as "
                            "requiring more retrieval, reversing the expected "
                            "decision boundary."
                        ),
                        "conditions": (
                            "thinking_mode disabled: repeated errors; enabled: "
                            "the same input flipped across repetitions."
                        ),
                        "elicitation_scope": "fixed_prompt",
                        "evidence_refs": ["hook_review"],
                    }
                ]
            }
        ),
        prepared.resources,
    )
    validate_role_output(ExperienceSummary(), prepared.resources)

    return {
        "schema_version": "3.0",
        "check_id": "CHECK-STAGE-002-EXPERIENCE-SUMMARY",
        "status": "passed",
        "scope": "development_check_only",
        "role_version": 3,
        "output_contract_version": 3,
        "input_fields": list(ExperienceSummaryInput.model_fields),
        "tools": [item.name for item in tools],
        "inspected_view": tool_payload["view"],
        "assertions": {
            "compact_structured_input": True,
            "actual_transition_route": True,
            "global_and_local_attribution_context": True,
            "program_evidence_hidden_until_tool_call": True,
            "evidence_directory_is_content_free": True,
            "bounded_tool_result": True,
            "twenty_call_hard_fuse": True,
            "capability_direction_teacher_priority": True,
            "capability_is_an_atomic_semantic_observation": True,
            "prompt_coverage_defaults_to_fixed": True,
            "authorized_output_evidence": True,
            "empty_summary_allowed": True,
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
        default=PROJECT_ROOT
        / "cvpr_workspace"
        / "analysis"
        / "stage_002_experience_summary_check_v3.json",
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
