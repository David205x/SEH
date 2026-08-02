"""Model 调用的角色无关输入、输出与执行协议。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


_MESSAGE_ROLES = frozenset({"system", "user", "assistant", "tool"})


@dataclass(frozen=True)
class ChatMessage:
    """一条带 Message Role 的模型可见消息。"""

    role: str
    content: str

    def __post_init__(self) -> None:
        role = self.role.strip()
        if role not in _MESSAGE_ROLES:
            raise ValueError(f"unsupported chat role: {self.role}")
        object.__setattr__(self, "role", role)
        object.__setattr__(self, "content", str(self.content))

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass(frozen=True)
class ModelInput:
    """一次 Model 调用的 provider-ready 结构化输入。"""

    messages: tuple[ChatMessage, ...]

    def __post_init__(self) -> None:
        messages = tuple(self.messages)
        if not messages:
            raise ValueError("model input must contain at least one message")
        object.__setattr__(self, "messages", messages)

    @classmethod
    def from_messages(cls, messages: list[ChatMessage]) -> "ModelInput":
        return cls(messages=tuple(messages))

    def to_dict(self) -> dict[str, Any]:
        return {"messages": [message.to_dict() for message in self.messages]}


@dataclass(frozen=True)
class ModelResponse:
    """一次 Model 调用返回的内容、usage 与 Provider metadata。"""

    raw_output: str
    usage: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "raw_output", str(self.raw_output))
        object.__setattr__(self, "usage", dict(self.usage))
        object.__setattr__(self, "metadata", dict(self.metadata))


class Model(Protocol):
    """Agent Runner 使用的最小模型调用边界。"""

    def generate(self, model_input: ModelInput) -> ModelResponse:
        """执行一次模型调用并返回完整 Model Response。"""
