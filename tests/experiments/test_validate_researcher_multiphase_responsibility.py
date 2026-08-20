"""Researcher 多 phase/state A/B 实验脚本测试。"""

from __future__ import annotations

import unittest

from experiments.validate_researcher_multiphase_responsibility import (
    CASES,
    _case_user_prompt,
    _trial_state_markers,
)


class ResearcherMultiphaseExperimentTest(unittest.TestCase):
    def test_trial_state_summary_ignores_plain_state_words(self) -> None:
        """验证普通动词 states 不再被误报为 Trial state。"""

        self.assertEqual(
            _trial_state_markers(
                "the answer states a conclusion; state precisely what is absent"
            ),
            [],
        )
        self.assertEqual(
            _trial_state_markers(
                "update_trial_state writes Trial state before the terminal action"
            ),
            ["trial_state", "update_trial_state"],
        )

    def test_stateful_case_freezes_required_contract_shape(self) -> None:
        """验证受控 case 明确要求双 phase 与两个状态键。"""

        case = next(item for item in CASES if item.name == "stateful_delayed_control")

        self.assertEqual(case.expected_phases, ("post_tool", "pre_final"))
        self.assertEqual(
            case.expected_state_keys,
            ("one_sided_result_observed", "missing_entity_name"),
        )
        self.assertIsNotNone(case.prompt_addendum)

    def test_case_prompt_addendum_has_one_terminal_newline(self) -> None:
        """验证冻结 case Prompt 拼接结果稳定且不累积空行。"""

        self.assertEqual(
            _case_user_prompt("base\n\n", "section\n"),
            "base\n\nsection\n",
        )


if __name__ == "__main__":
    unittest.main()
