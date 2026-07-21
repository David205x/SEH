"""Core agent loop primitives."""

from .hook_state import HookContext, StateAccessError, StateRef
from .hooks import BaseHook, HookPhase, HookPipeline
from .loop import AgentLoop
from .parser import TaggedOutputParser
from .protocols import (
    HookModelBackend,
    ModelClient,
    ModelResponseMetadataProvider,
    OutputParser,
    PromptBuilder,
    Tool,
)
from .tools import ToolRuntime
from .types import (
    AgentRun,
    AgentState,
    ChatMessage,
    FinalDecision,
    FinalDecisionAction,
    HookModelRequest,
    HookModelResponse,
    ModelInput,
    ParsedOutput,
    ParsedOutputKind,
    RunStatus,
    ToolCall,
    ToolInteraction,
    ToolResult,
    TraceEvent,
)

__all__ = [
    "AgentLoop",
    "AgentRun",
    "AgentState",
    "BaseHook",
    "ChatMessage",
    "FinalDecision",
    "FinalDecisionAction",
    "HookPipeline",
    "HookContext",
    "HookModelBackend",
    "HookModelRequest",
    "HookModelResponse",
    "HookPhase",
    "ModelClient",
    "ModelResponseMetadataProvider",
    "ModelInput",
    "OutputParser",
    "ParsedOutput",
    "ParsedOutputKind",
    "PromptBuilder",
    "RunStatus",
    "StateAccessError",
    "StateRef",
    "TaggedOutputParser",
    "Tool",
    "ToolCall",
    "ToolInteraction",
    "ToolResult",
    "ToolRuntime",
    "TraceEvent",
]
