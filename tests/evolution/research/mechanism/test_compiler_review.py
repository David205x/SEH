"""Compiler 候选专属源码审查测试。"""

from __future__ import annotations

import unittest
from pathlib import Path

from search_harness.evolution.research.mechanism.review import review_compiler_candidate
from search_harness.evolution.versioning import CandidateWorkspace, HarnessSnapshot


PROJECT_ROOT = Path(__file__).resolve().parents[4]
BASELINE_TEMPLATE = PROJECT_ROOT / "harness_templates" / "student" / "baseline"


class CompilerCandidateReviewTest(unittest.TestCase):
    def test_review_rejects_hidden_factory_and_exception_defects(self) -> None:
        """验证审查器拒绝未使用配置、dummy del 和宽泛异常捕获。"""

        workspace = _workspace()
        workspace.write_text(
            "extensions/probe/component.py",
            (
                "def build(config, context):\n"
                "    del context\n"
                "    try:\n"
                "        return object()\n"
                "    except Exception:\n"
                "        return None\n"
            ),
        )

        errors = review_compiler_candidate(workspace)

        self.assertEqual(len(errors), 3)
        self.assertTrue(any("consume its config" in item for item in errors))
        self.assertTrue(any("dummy del" in item for item in errors))
        self.assertTrue(any("broad exception" in item for item in errors))

    def test_review_accepts_explicit_factory_policy(self) -> None:
        """验证显式配置校验和具体异常处理满足作者规范。"""

        workspace = _workspace()
        workspace.write_text(
            "extensions/probe/component.py",
            (
                "def build(config, context):\n"
                "    if config:\n"
                "        raise ValueError('probe does not accept config')\n"
                "    try:\n"
                "        return context['factory']()\n"
                "    except KeyError:\n"
                "        return None\n"
            ),
        )

        self.assertEqual(review_compiler_candidate(workspace), [])

    def test_review_leaves_syntax_diagnostics_to_harness_validator(self) -> None:
        """验证语法错误不会使 Compiler 专属审查器提前崩溃。"""

        workspace = _workspace()
        workspace.write_text(
            "extensions/probe/component.py",
            "def build(:\n",
        )

        self.assertEqual(review_compiler_candidate(workspace), [])

    def test_review_requires_stage_value_type_checks(self) -> None:
        """验证 Hook 在访问可空 stage 值前必须执行显式类型检查。"""

        workspace = _workspace()
        workspace.write_text(
            "extensions/probe/component.py",
            (
                "def handle(context):\n"
                "    result = context.state.get('stage.tool_result')\n"
                "    return result.content\n"
            ),
        )

        errors = review_compiler_candidate(workspace)

        self.assertEqual(len(errors), 1)
        self.assertIn("ToolResult", errors[0])


def _workspace() -> CandidateWorkspace:
    parent = HarnessSnapshot.from_directory(
        BASELINE_TEMPLATE,
        version_id="parent",
    )
    return CandidateWorkspace(parent)
