"""Tests for the shadow Compiler authoring view and A/B metrics."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from experiments.run_compiler_authoring_ab import extract_metrics
from experiments.teacher_query_views.compiler import (
    render_shadow_compiler_input,
    render_shadow_hook_api_result,
)
from search_harness.evolution.research.resources.base import TeacherResourceConfig
from search_harness.evolution.research.roles.role_execution import prepare_role_run


_ROOT = Path(__file__).resolve().parents[2]
_SHADOW = _ROOT / "experiments" / "teacher_query_views" / "templates" / "compiler"
_HISTORICAL = (
    _ROOT
    / "runs"
    / "evolution"
    / "20260809_base"
    / "artifacts"
    / "compile_candidate-0f15228acedeb67a"
    / "role.json"
)


class CompilerAuthoringViewTest(unittest.TestCase):
    def test_shadow_template_keeps_formal_tool_surface(self) -> None:
        source = json.loads(_HISTORICAL.read_text(encoding="utf-8"))
        prepared = prepare_role_run(
            template_root=_SHADOW,
            role_input=source["input"],
            resource_config=TeacherResourceConfig.model_validate(
                source["resource_config"]
            ),
            role_id="compiler",
            role_version=1,
        )

        self.assertEqual(
            {
                "list_harness_files",
                "read_harness_file",
                "query_hook_api",
                "write_candidate_file",
                "delete_candidate_file",
                "finalize_candidate",
            },
            {tool.name for tool in prepared.spec.tools.tools},
        )
        rendered = prepared.rendered_input
        self.assertIn("# Compiler Implementation Brief", rendered)
        self.assertIn("model-gated POST_TOOL result guidance", rendered)
        self.assertIn("parts = first_line.split(maxsplit=1)", rendered)
        self.assertIn("_GUIDANCE.format(detail=detail)", rendered)
        self.assertIn('"harness_id":"baseline_search"', rendered)
        for constraint in source["input"]["implementation_constraints"]:
            self.assertIn(constraint, rendered)

    def test_packet_view_avoids_structured_and_native_contract_duplication(self) -> None:
        rendered = render_shadow_compiler_input(
            {
                "mechanism": {
                    "goal": "g",
                    "phase_rules": [
                        {
                            "phase": "post_tool",
                            "decision_evaluator": "deterministic",
                        }
                    ],
                },
                "implementation_constraints": ["preserve metadata"],
                "validation_feedback": [],
            },
            {
                "compiler": {
                    "capability_packet": {
                        "packet_version": 9,
                        "runtime_input_documents": [
                            {
                                "runtime_input_id": "tool",
                                "symbols": ["ToolResult"],
                                "native_reference": "class ToolResult: ...",
                            }
                        ],
                        "contracts": [
                            {"symbol": "ToolResult", "shape": "duplicate"},
                            {"symbol": "StateRef", "shape": "unique"},
                        ],
                        "authoring": {},
                    }
                }
            },
        )

        self.assertIn("class ToolResult: ...", rendered)
        self.assertNotIn('"shape":"duplicate"', rendered)
        self.assertIn('"shape":"unique"', rendered)

    def test_shadow_query_prefers_native_reference(self) -> None:
        rendered = render_shadow_hook_api_result(
            {
                "status": "resolved",
                "query": "ToolResult",
                "source": "hook_api",
                "remaining_unique_queries": 8,
                "contract": {"symbol": "ToolResult", "shape": "duplicate"},
                "native_reference": "class ToolResult:\n    content: str",
                "related_runtime_inputs": ["tool"],
            }
        )

        self.assertIn("class ToolResult:", rendered)
        self.assertNotIn("duplicate", rendered)


class CompilerABMetricTest(unittest.TestCase):
    def test_metrics_separate_queries_repairs_and_validation(self) -> None:
        artifact = {
            "output": {"decision": "submitted"},
            "resource_artifacts": {
                "compiler_candidate": {
                    "validation": {"passed": True},
                    "changed_files": {"extension.py": "pass\n"},
                }
            },
            "tool_calls": [
                {"name": "read_harness_file", "content": "source"},
                {
                    "name": "query_hook_api",
                    "content": '{"status": "rejected"}',
                },
                {"name": "finalize_candidate", "content": "repair_required"},
                {"name": "finalize_candidate", "content": "submitted"},
            ],
            "usage": {
                "requests": 4,
                "input_tokens": 100,
                "output_tokens": 20,
                "total_tokens": 120,
                "calls": [{"prompt_tokens": 30}],
            },
        }

        metrics = extract_metrics(artifact)

        self.assertTrue(metrics["validation_passed"])
        self.assertFalse(metrics["first_finalize_passed"])
        self.assertEqual(1, metrics["finalize_repairs"])
        self.assertEqual(1, metrics["api_rejected_calls"])


if __name__ == "__main__":
    unittest.main()
