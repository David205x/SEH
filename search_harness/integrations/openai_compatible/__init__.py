"""OpenAI-compatible Model 与 Hook Model Backend 集成。"""

from .hook_backend import ProfiledHookModelBackend
from .model import OpenAICompatibleConfig, OpenAICompatibleModel
from .tool_runner import (
    NativeToolCall,
    NativeToolRunResult,
    NativeToolRunExhausted,
    NativeToolRunFailure,
    NativeToolTurn,
    OpenAICompatibleClient,
    OpenAICompatibleSyncClient,
    OpenAICompatibleToolSession,
    OpenAICompatibleToolRunner,
    PendingNativeToolCall,
)

__all__ = [
    "NativeToolCall",
    "NativeToolRunResult",
    "NativeToolRunExhausted",
    "NativeToolRunFailure",
    "NativeToolTurn",
    "OpenAICompatibleClient",
    "OpenAICompatibleConfig",
    "OpenAICompatibleModel",
    "OpenAICompatibleSyncClient",
    "OpenAICompatibleToolSession",
    "OpenAICompatibleToolRunner",
    "PendingNativeToolCall",
    "ProfiledHookModelBackend",
]
