"""角色无关的 Agent 组合、运行与 Model 协议。"""

from .agent import Agent
from .model import ChatMessage, Model, ModelInput, ModelResponse
from .runner import LoopRunner
from .types import (
    AgentState,
    FinalDecision,
    FinalDecisionAction,
    HookModelRequest,
    HookModelResponse,
    ParsedOutput,
    ParsedOutputKind,
    RunResult,
    RunStatus,
)

__all__ = [
    "Agent",
    "AgentState",
    "ChatMessage",
    "FinalDecision",
    "FinalDecisionAction",
    "HookModelRequest",
    "HookModelResponse",
    "LoopRunner",
    "Model",
    "ModelInput",
    "ModelResponse",
    "ParsedOutput",
    "ParsedOutputKind",
    "RunResult",
    "RunStatus",
]
