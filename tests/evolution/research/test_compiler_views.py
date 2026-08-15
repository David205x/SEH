"""Tests for production Compiler model-visible views."""

from __future__ import annotations

import unittest

from search_harness.evolution.research.compiler_views import (
    render_compiler_capability_packet,
    render_compiler_resource_context,
    render_hook_api_result,
)


class CompilerViewTest(unittest.TestCase):
    def test_packet_does_not_repeat_topic_contracts(self) -> None:
        rendered = render_compiler_capability_packet(
            {
                "selection": {
                    "strategy": "phase_scoped",
                    "phase_rules": [
                        {
                            "phase": "post_tool",
                            "guards": ["duplicate mechanism guard"],
                            "decision_contract": {"positive_rule": "duplicate"},
                            "exact_decision_inputs": ["stage.tool_result"],
                            "semantic_decision_inputs": ["missing evidence"],
                            "runtime_inputs": ["tool"],
                        }
                    ],
                },
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
                "catalog_versions": {"hook_api": 1},
            }
        )

        self.assertIn("class ToolResult: ...", rendered)
        self.assertNotIn('"shape":"duplicate"', rendered)
        self.assertIn('"shape":"unique"', rendered)
        self.assertNotIn("duplicate mechanism guard", rendered)
        self.assertNotIn("positive_rule", rendered)

    def test_api_query_prefers_native_reference(self) -> None:
        rendered = render_hook_api_result(
            {
                "status": "resolved",
                "query_kind": "symbol",
                "query": "ToolResult",
                "source": "exact_query",
                "remaining_unique_queries": 8,
                "contract": {"symbol": "ToolResult", "shape": "duplicate"},
                "native_reference": "class ToolResult:\n    content: str",
                "related_runtime_inputs": ["tool"],
            }
        )

        self.assertIn("class ToolResult:", rendered)
        self.assertNotIn("duplicate", rendered)

    def test_continuation_view_includes_exact_changed_files(self) -> None:
        rendered = render_compiler_resource_context(
            {
                "compiler": {
                    "harness_id": "baseline",
                    "continuation": {
                        "candidate_digest": "abc",
                        "changed_paths": ["extensions/example.py"],
                    },
                    "continuation_changed_files": {
                        "extensions/example.py": "VALUE = 1\n",
                    },
                    "capability_packet": {
                        "selection": {},
                        "contracts": [],
                        "runtime_input_documents": [],
                        "authoring": {},
                    },
                }
            }
        )

        self.assertIn("<candidate_file", rendered)
        self.assertIn("extensions/example.py", rendered)
        self.assertIn("VALUE = 1", rendered)
        self.assertNotIn("parent_template_root", rendered)


if __name__ == "__main__":
    unittest.main()
