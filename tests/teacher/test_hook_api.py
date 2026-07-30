"""新版 Compiler 的源码驱动 Hook API 目录测试。"""

from __future__ import annotations

import inspect
import unittest

from search_harness.core import HookContext
from search_harness.teacher.hook_api import (
    list_hook_api_symbols,
    query_hook_api,
)
from search_harness.teacher.hook_authoring import get_hook_authoring_guide


class HookApiCatalogTest(unittest.TestCase):
    def test_query_uses_current_source_signature_and_docstring(self) -> None:
        """验证公开方法说明由当前源码签名和 docstring 动态生成。"""

        result = query_hook_api("HookContext.call_model")

        self.assertEqual(
            result["summary"],
            inspect.getdoc(HookContext.call_model),
        )
        self.assertEqual(
            result["signature"],
            "call_model(request: HookModelRequest) -> HookModelResponse",
        )
        self.assertTrue(result["generated_from_source"])

    def test_private_and_unlisted_members_are_hidden(self) -> None:
        """验证反射不会向 Compiler 泄露内部属性或未承诺的方法。"""

        context = query_hook_api("HookContext")
        field_names = {item["symbol"] for item in context["fields"]}

        self.assertNotIn("HookContext._model_backend", field_names)
        with self.assertRaisesRegex(ValueError, "internal and not exposed"):
            query_hook_api("HookContext._model_backend")
        with self.assertRaisesRegex(ValueError, "not part of the public"):
            query_hook_api("HookContext.to_dict")

    def test_state_key_reports_phase_type_and_stability(self) -> None:
        """验证 stage 状态查询给出精确类型、时机与稳定性。"""

        result = query_hook_api("stage.tool_result")

        self.assertEqual(result["type"], "ToolResult")
        self.assertEqual(result["phases"], ["post_tool"])
        self.assertEqual(result["stability"], "stable")
        self.assertEqual(result["shape"], "closed")

    def test_public_constant_and_enum_value_are_directly_queryable(self) -> None:
        """验证 Compiler 可精确查询 phase 常量与枚举值。"""

        phase = query_hook_api("HookPhase.POST_TOOL")
        decision = query_hook_api("FinalDecisionAction.DEFER")

        self.assertEqual(phase["value"], "post_tool")
        self.assertEqual(decision["value"], "defer")

    def test_open_member_is_distinguished_from_closed_owner(self) -> None:
        """验证开放 metadata 不会削弱 ToolResult 其他字段的闭合契约。"""

        owner = query_hook_api("ToolResult")
        member = query_hook_api("ToolResult.metadata")

        self.assertEqual(owner["shape"], "closed")
        self.assertEqual(member["shape"], "open")
        self.assertEqual(member["type"], "dict[str, Any]")

    def test_catalog_lists_only_public_query_roots(self) -> None:
        """验证分类列表提供可分页入口且不包含 core 内部实现类。"""

        result = list_hook_api_symbols(
            category="hook",
            page=1,
            page_size=50,
        )
        symbols = {item["symbol"] for item in result["items"]}

        self.assertIn("BaseHook", symbols)
        self.assertIn("HookContext", symbols)
        self.assertNotIn("HookPipeline", symbols)
        self.assertNotIn("HookStateStore", symbols)

    def test_authoring_guide_points_compiler_to_exact_api_queries(self) -> None:
        """验证语义指南要求先发现并查询精确源码契约。"""

        index = get_hook_authoring_guide("index")
        implementation = get_hook_authoring_guide("implementation")

        self.assertTrue(
            any("query_hook_api" in item for item in index["api_discovery"])
        )
        self.assertIn("ToolResult", implementation["public_core_imports"])


if __name__ == "__main__":
    unittest.main()
