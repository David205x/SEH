"""Actor Harness manifest lookup for the Critic."""

from __future__ import annotations

import json
from typing import Any

from search_harness.adapter.critic import CriticContext
from search_harness.core import ToolResult
from search_harness.framework.tooling import CallableTool, ToolDefinition, tool


class GetHarnessManifestTool:
    def __init__(self, critic: CriticContext) -> None:
        self._critic = critic
        self._tool = CallableTool.from_callable(self.get_harness_manifest)

    @property
    def name(self) -> str:
        return self._tool.name

    @property
    def definition(self) -> ToolDefinition:
        return self._tool.definition

    def run(self, arguments: dict[str, object]) -> ToolResult:
        return self._tool.run(arguments)

    @tool(name="get_harness_manifest")
    def get_harness_manifest(self) -> ToolResult:
        """Read the complete manifest of the Actor Harness under analysis."""

        payload = self._critic.get_harness_manifest()
        return ToolResult(name=self.name, content=json.dumps(payload, ensure_ascii=False))


def build(config: dict[str, Any], context: Any) -> GetHarnessManifestTool:
    if config:
        raise ValueError("get_harness_manifest does not accept configuration")
    if not isinstance(context.runtime_context, CriticContext):
        raise TypeError("get_harness_manifest requires a CriticContext")
    return GetHarnessManifestTool(context.runtime_context)
