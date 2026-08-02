"""Source-derived intervention capability catalog tests."""

from __future__ import annotations

import unittest
from typing import get_args

from search_harness.evolution.research.intervention.prefix import (
    recoverable_prefix_phases,
)
from search_harness.framework import HookPhase
from search_harness.evolution.research.roles.contracts import InterventionActionName
from search_harness.evolution.research.intervention.capabilities import (
    intervention_capabilities,
)


class InterventionCapabilityCatalogTest(unittest.TestCase):
    def test_catalog_matches_runtime_phase_and_action_contracts(self) -> None:
        """验证能力目录不会遗漏或虚构实际可恢复阶段与 Worker 动作。"""

        catalog = intervention_capabilities()

        self.assertEqual(
            [item["phase"] for item in catalog["phases"]],
            list(recoverable_prefix_phases()),
        )
        self.assertEqual(
            {item["name"] for item in catalog["actions"]},
            set(get_args(InterventionActionName)),
        )

    def test_catalog_exposes_observability_and_action_limits(self) -> None:
        """验证目录明确区分 trace-only reasoning 与可执行动作边界。"""

        catalog = intervention_capabilities()
        actions = {
            item["name"]: item for item in catalog["actions"]
        }

        self.assertEqual(
            catalog["observability"]["native_reasoning"],
            "trace_only_not_hook_visible",
        )
        self.assertEqual(
            actions["defer_final_answer"]["compatible_phases"],
            [HookPhase.PRE_FINAL],
        )
        self.assertEqual(
            actions["append_user_message"]["persistence"],
            "branch_prefix",
        )
        self.assertIn(
            "model_input.messages",
            catalog["observability"]["selected_prefix"],
        )
        self.assertTrue(
            catalog["execution"]["one_action_per_activation"]
        )
        self.assertTrue(
            catalog["execution"]["multiple_phases_per_trial"]
        )
        self.assertTrue(
            catalog["execution"][
                "same_worker_transcript_across_activations"
            ]
        )


if __name__ == "__main__":
    unittest.main()
