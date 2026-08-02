"""OpenAI-compatible Model 与 Hook Model Backend 集成。"""

from .hook_backend import ProfiledHookModelBackend
from .model import OpenAICompatibleConfig, OpenAICompatibleModel
from .tool_runner import (
    NativeToolCall,
    NativeToolRunResult,
    OpenAICompatibleClient,
    OpenAICompatibleToolRunner,
)

__all__ = [
    "NativeToolCall",
    "NativeToolRunResult",
    "OpenAICompatibleClient",
    "OpenAICompatibleConfig",
    "OpenAICompatibleModel",
    "OpenAICompatibleToolRunner",
    "ProfiledHookModelBackend",
]
