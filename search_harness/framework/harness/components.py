"""Harness Component 的最小角色无关协议。"""

from __future__ import annotations

from typing import Protocol

from ..tools import DefinedTool

from ..agent.types import (
    AgentState,
    HookModelRequest,
    HookModelResponse,
    ModelInput,
    ParsedOutput,
)


class HookModelBackend(Protocol):
    """Execute one environment-controlled model request for a hook."""

    def generate(self, request: HookModelRequest) -> HookModelResponse:
        """Generate one response without entering a nested AgentLoop."""


class PromptComponent(Protocol):
    """根据 Harness State 构造下一次 Model Input。"""

    def build(self, state: AgentState) -> ModelInput:
        """Render the current state into structured model input."""


class OutputComponent(Protocol):
    """把 Raw Model Output 解析为一个循环分支。"""

    def parse(self, raw_output: str) -> ParsedOutput:
        """Return a tool call, final answer, or invalid parse result."""


ToolComponent = DefinedTool

PromptBuilder = PromptComponent
OutputParser = OutputComponent
Tool = ToolComponent
