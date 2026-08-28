"""Program-managed Prompt Products callable from one Hook invocation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
from typing import Any, Literal, Mapping, TYPE_CHECKING

from ..agent.types import ChatMessage, HookModelRequest, ModelInput

if TYPE_CHECKING:
    from .state import HookContext


HOOK_PROMPT_PROJECTOR_ID = "ordered_hook_state_json_v1"
HOOK_PROMPT_PROJECTOR_VERSION = 1
HookPromptKind = Literal["decision", "generation", "structured_edit"]
HookPromptAdapter = Literal["tri_label", "raw_text", "structured_edit"]


@dataclass(frozen=True)
class HookPromptInput:
    """One stable model-visible name assembled from ordered Hook state sources."""

    name: str
    sources: tuple[str, ...]

    def __post_init__(self) -> None:
        name = self.name.strip()
        sources = tuple(source.strip() for source in self.sources)
        if not name:
            raise ValueError("Hook Prompt input name must not be empty")
        if not sources or any(not source for source in sources):
            raise ValueError("Hook Prompt input sources must not be empty")
        if len(sources) != len(set(sources)):
            raise ValueError("Hook Prompt input sources must be unique")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "sources", sources)


@dataclass(frozen=True)
class HookEditOperation:
    """One structurally validated edit proposed by a managed Prompt Product."""

    operation: Literal["insert", "replace", "delete"]
    block_id: int | None = None
    anchor_block_id: int | None = None
    position: Literal["before", "after"] | None = None
    role: Literal["system", "user", "assistant", "tool"] | None = None
    content: str | None = None

    def __post_init__(self) -> None:
        if self.block_id is not None and (
            not isinstance(self.block_id, int)
            or isinstance(self.block_id, bool)
            or self.block_id < 1
        ):
            raise ValueError("block_id must be a positive integer")
        if self.anchor_block_id is not None and (
            not isinstance(self.anchor_block_id, int)
            or isinstance(self.anchor_block_id, bool)
            or self.anchor_block_id < 1
        ):
            raise ValueError("anchor_block_id must be a positive integer")
        if self.operation == "delete":
            if self.block_id is None or any(
                value is not None
                for value in (
                    self.anchor_block_id,
                    self.position,
                    self.role,
                    self.content,
                )
            ):
                raise ValueError("delete requires only block_id")
            return
        if self.operation == "replace":
            if (
                self.block_id is None
                or not isinstance(self.content, str)
                or any(
                    value is not None
                    for value in (
                        self.anchor_block_id,
                        self.position,
                        self.role,
                    )
                )
            ):
                raise ValueError("replace requires block_id and content")
            return
        if (
            self.anchor_block_id is None
            or self.position not in {"before", "after"}
            or self.role not in {"system", "user", "assistant", "tool"}
            or not isinstance(self.content, str)
            or self.block_id is not None
        ):
            raise ValueError(
                "insert requires anchor_block_id, position, role and content"
            )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "HookEditOperation":
        allowed = {
            "operation",
            "block_id",
            "anchor_block_id",
            "position",
            "role",
            "content",
        }
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(
                f"Hook edit operation has unsupported fields: {sorted(unknown)}"
            )
        return cls(**dict(value))


@dataclass(frozen=True)
class HookPromptProduct:
    """One immutable Prompt, projection and invocation contract."""

    product_ref: str
    phase: str
    task_kind: HookPromptKind
    inputs: tuple[HookPromptInput, ...]
    prompt: str
    thinking_mode: Literal["enabled", "disabled"]
    response_adapter: HookPromptAdapter
    task_digest: str
    input_projection_digest: str
    prompt_digest: str
    model_profile: str = "student"

    def __post_init__(self) -> None:
        if not self.product_ref.strip():
            raise ValueError("Hook Prompt Product ref must not be empty")
        if not self.phase.strip():
            raise ValueError("Hook Prompt Product phase must not be empty")
        if not self.inputs:
            raise ValueError("Hook Prompt Product inputs must not be empty")
        if len({item.name for item in self.inputs}) != len(self.inputs):
            raise ValueError("Hook Prompt Product input names must be unique")
        prompt = self.prompt
        if not prompt.strip():
            raise ValueError("Hook Prompt Product prompt must not be empty")
        expected_adapter = {
            "decision": "tri_label",
            "generation": "raw_text",
            "structured_edit": "structured_edit",
        }[self.task_kind]
        if self.response_adapter != expected_adapter:
            raise ValueError(
                f"{self.task_kind} Prompt Product requires {expected_adapter}"
            )
        if _text_digest(prompt) != self.prompt_digest:
            raise ValueError("Hook Prompt Product prompt digest does not match")
        for digest in (
            self.task_digest,
            self.input_projection_digest,
            self.prompt_digest,
        ):
            if len(digest) != 64 or any(
                character not in "0123456789abcdef" for character in digest
            ):
                raise ValueError("Hook Prompt Product digests must be sha256 hex")
        model_profile = self.model_profile.strip()
        if not model_profile:
            raise ValueError("Hook Prompt Product model profile must not be empty")
        object.__setattr__(self, "prompt", prompt)
        object.__setattr__(self, "model_profile", model_profile)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "HookPromptProduct":
        payload = dict(value)
        raw_inputs = payload.pop("inputs", None)
        if not isinstance(raw_inputs, list):
            raise TypeError("Hook Prompt Product inputs must be an array")
        return cls(
            inputs=tuple(
                HookPromptInput(
                    name=str(item["name"]),
                    sources=tuple(str(source) for source in item["sources"]),
                )
                for item in raw_inputs
            ),
            **payload,
        )


@dataclass(frozen=True)
class HookPromptOutput:
    """Normalized semantic value returned by one managed Prompt Product."""

    kind: HookPromptKind
    value: str | tuple[HookEditOperation, ...] | None


def call_prompt_product(
    context: "HookContext",
    product: HookPromptProduct,
) -> HookPromptOutput:
    """Call the exact Prompt Product on its frozen current-phase projection.

    The caller controls lifecycle guards and applies the returned value to the
    Mechanism target. Prompt text, Hook state sources, thinking mode and response
    adaptation remain program-managed.
    """

    if context.phase != product.phase:
        raise ValueError(
            f"Prompt Product {product.product_ref} is bound to {product.phase}, "
            f"not {context.phase}"
        )
    projection = _project_inputs(context, product)
    response = context.call_model(
        HookModelRequest(
            profile=product.model_profile,
            purpose=f"prompt_product:{product.product_ref}",
            model_input=ModelInput.from_messages(
                (
                    ChatMessage(role="system", content=product.prompt),
                    ChatMessage(
                        role="user",
                        content=render_hook_prompt_user_message(projection),
                    ),
                )
            ),
            thinking_mode=product.thinking_mode,
        )
    )
    return _adapt_output(product, response.raw_output)


def render_hook_prompt_user_message(projection: Mapping[str, Any]) -> str:
    """Render the shared Prompt Research and runtime user-message envelope."""

    return (
        "Apply the frozen Hook task to this exact model-visible input. "
        "Use no hidden trajectory facts.\n"
        + json.dumps(
            dict(projection),
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )


def _project_inputs(
    context: "HookContext",
    product: HookPromptProduct,
) -> dict[str, Any]:
    return {
        "projector_id": HOOK_PROMPT_PROJECTOR_ID,
        "projection_digest": product.input_projection_digest,
        "phase": product.phase,
        "inputs": [
            {
                "name": item.name,
                "sources": [
                    {
                        "source": source,
                        "value": _json_value(context.state.get(source)),
                    }
                    for source in item.sources
                ],
            }
            for item in product.inputs
        ],
    }


def _adapt_output(
    product: HookPromptProduct,
    raw_output: str,
) -> HookPromptOutput:
    if product.response_adapter == "tri_label":
        label = raw_output.strip().casefold()
        return HookPromptOutput(
            kind="decision",
            value=(
                label
                if label in {"positive", "negative", "uncertain"}
                else "uncertain"
            ),
        )
    if product.response_adapter == "raw_text":
        text = raw_output.strip()
        return HookPromptOutput(kind="generation", value=text or None)
    try:
        payload = json.loads(raw_output)
        operations = payload.get("operations")
        if not isinstance(operations, list) or not operations:
            raise ValueError("structured edit requires non-empty operations")
        parsed = tuple(
            HookEditOperation.from_dict(item)
            for item in operations
            if isinstance(item, dict)
        )
        if len(parsed) != len(operations):
            raise TypeError("structured edit operations must be objects")
    except (json.JSONDecodeError, TypeError, ValueError):
        parsed = None
    return HookPromptOutput(kind="structured_edit", value=parsed)


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Enum):
        return _json_value(value.value)
    if is_dataclass(value):
        return _json_value(asdict(value))
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return _json_value(to_dict())
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    raise TypeError(
        "Hook Prompt Product projector cannot serialize "
        f"{type(value).__name__}"
    )


def _text_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
