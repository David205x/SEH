"""Model adapters for search harness runtimes."""

from .hook_backend import ProfiledHookModelBackend
from .openai_compatible import OpenAICompatibleConfig, OpenAICompatibleTextModel

__all__ = [
    "OpenAICompatibleConfig",
    "OpenAICompatibleTextModel",
    "ProfiledHookModelBackend",
]
