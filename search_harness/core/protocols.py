"""Protocols for replaceable core loop boundaries."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .types import (
    AgentState,
    HookModelRequest,
    HookModelResponse,
    ModelInput,
    ParsedOutput,
    ToolResult,
)


class ModelClient(Protocol):
    """Minimal model boundary used by the core loop."""

    def generate(self, model_input: ModelInput) -> str:
        """Generate one model response from structured chat messages."""


class HookModelBackend(Protocol):
    """Execute one environment-controlled model request for a hook."""

    def generate(self, request: HookModelRequest) -> HookModelResponse:
        """Generate one response without entering a nested AgentLoop."""


@runtime_checkable
class ModelResponseMetadataProvider(Protocol):
    """Optional provider capability for traceable native response metadata."""

    def get_last_generation_metadata(self) -> dict[str, Any]:
        """Return JSON-compatible metadata for the most recent generation."""


class PromptBuilder(Protocol):
    """Build the prompt for the next model call."""

    def build(self, state: AgentState) -> ModelInput:
        """Render the current state into structured model input."""


class OutputParser(Protocol):
    """Parse raw model output into a loop branch."""

    def parse(self, raw_output: str) -> ParsedOutput:
        """Return a tool call, final answer, or invalid parse result."""


class Tool(Protocol):
    """A callable tool registered in the tool runtime."""

    name: str

    def run(self, arguments: dict[str, object]) -> ToolResult:
        """Execute the tool with parsed model arguments."""
