"""Controlled state access for registry hooks."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
from typing import Any

from .components import HookModelBackend
from ..agent.types import (
    AgentState,
    HookModelRequest,
    HookModelResponse,
    ModelInput,
    FinalDecision,
    FinalDecisionAction,
    ParsedOutput,
    TrajectoryEvent,
    ToolCall,
    ToolResult,
)
from .prompt_products import (
    HookPromptOutput,
    HookPromptProduct,
    call_prompt_product,
)


class StateAccessError(RuntimeError):
    """Raised when a hook reads or writes state outside its contract."""


_MISSING = object()


@dataclass(frozen=True)
class StateRef:
    """Declaration for persistent extension or shared state.

    ``core.*`` and ``stage.*`` are managed by the loop and cannot be declared
    here. ``shared.*`` is intentionally readable by every hook; ``writers``
    makes its mutation contract explicit. ``extension.<hook_id>.*`` is private
    in ownership, though still readable for cross-hook coordination.
    """

    key: str
    owner: str
    value_type: type[Any] | tuple[type[Any], ...] | None = None
    writers: frozenset[str] = frozenset()
    default: Any = _MISSING

    def __post_init__(self) -> None:
        if not self.key.startswith(("shared.", "extension.")):
            raise ValueError("state ref key must start with shared. or extension.")
        if not self.owner.strip():
            raise ValueError("state ref owner must not be empty")
        if self.key.startswith("extension."):
            parts = self.key.split(".", maxsplit=2)
            if len(parts) < 3 or parts[1] != self.owner:
                raise ValueError(
                    "extension state key must use extension.<owner>.<name>"
                )


@dataclass(frozen=True)
class StateChange:
    """One committed hook mutation, including its full before and after values."""

    key: str
    before: Any
    after: Any

    def to_trace_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "before": _to_trace_value(self.before),
            "after": _to_trace_value(self.after),
        }


@dataclass(frozen=True)
class HookStateView:
    """Read/write transaction exposed to a single hook invocation."""

    _store: "HookStateStore"
    _hook_id: str
    _phase: str
    _writable_stage_keys: frozenset[str]
    _pending: dict[str, Any]

    def get(self, key: str, default: Any = _MISSING) -> Any:
        """Read any visible core, stage, shared, or extension value.

        Returned mutable objects are copied so hooks must use ``set`` to make
        modifications auditable.
        """

        if key in self._pending:
            return deepcopy(self._pending[key])
        return self._store.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Stage a permitted state replacement for atomic commit."""

        self._store.validate_write(
            key=key,
            value=value,
            hook_id=self._hook_id,
            phase=self._phase,
            writable_stage_keys=self._writable_stage_keys,
        )
        self._pending[key] = deepcopy(value)


@dataclass(frozen=True)
class HookContext:
    """Context passed to one hook invocation."""

    hook_id: str
    phase: str
    state: HookStateView
    trajectory: tuple[TrajectoryEvent, ...] = ()
    _model_backend: HookModelBackend | None = None

    def call_model(self, request: HookModelRequest) -> HookModelResponse:
        """Call an allowed small-model profile through the traced runtime."""

        if self._model_backend is None:
            raise RuntimeError(f"hook {self.hook_id} has no model runtime")
        return self._model_backend.generate(request)

    def call_prompt_product(
        self,
        product: HookPromptProduct,
    ) -> HookPromptOutput:
        """Call one exact managed Prompt Product on the current Hook state."""

        return call_prompt_product(self, product)


class HookStateStore:
    """Per-rollout state store with immutable core projections and transactions."""

    def __init__(self, agent_state: AgentState, refs: dict[str, StateRef]) -> None:
        self._agent_state = agent_state
        self._refs = dict(refs)
        self._stage_values: dict[str, Any] = {}
        self._stage_types: dict[str, type[Any]] = {}

        for ref in self._refs.values():
            if ref.default is not _MISSING and ref.key not in agent_state.hook_state:
                agent_state.hook_state[ref.key] = deepcopy(ref.default)

    def open_stage(self, values: dict[str, Any]) -> None:
        """Install the current phase's temporary, loop-owned input/output slots."""

        self._stage_values = {f"stage.{name}": deepcopy(value) for name, value in values.items()}
        self._stage_types = {
            f"stage.{name}": type(value) for name, value in values.items()
        }

    def close_stage(self) -> None:
        self._stage_values = {}
        self._stage_types = {}

    def get(self, key: str, default: Any = _MISSING) -> Any:
        if key == "core":
            return deepcopy(self._agent_state.to_dict())
        if key.startswith("core."):
            field = key.removeprefix("core.")
            payload = self._agent_state.to_dict()
            if field in payload:
                return deepcopy(payload[field])
        elif key in self._stage_values:
            return deepcopy(self._stage_values[key])
        elif key in self._agent_state.hook_state:
            return deepcopy(self._agent_state.hook_state[key])

        if default is not _MISSING:
            return deepcopy(default)
        raise KeyError(f"state key is not available: {key}")

    def commit(
        self,
        pending: dict[str, Any],
    ) -> list[StateChange]:
        """Commit a fully validated hook transaction and return its changes."""

        changes: list[StateChange] = []
        for key, value in pending.items():
            before = self.get(key, None)
            after = deepcopy(value)
            if before != after:
                changes.append(StateChange(key=key, before=before, after=after))
            if key.startswith("stage."):
                self._stage_values[key] = after
            else:
                self._agent_state.hook_state[key] = after
        return changes

    def current_stage_values(self) -> dict[str, Any]:
        return {
            key.removeprefix("stage."): deepcopy(value)
            for key, value in self._stage_values.items()
        }

    def validate_write(
        self,
        *,
        key: str,
        value: Any,
        hook_id: str,
        phase: str,
        writable_stage_keys: frozenset[str],
    ) -> None:
        if key.startswith("core.") or key == "core":
            raise StateAccessError(f"{hook_id} cannot modify loop-owned key {key}")

        if key.startswith("stage."):
            if key not in self._stage_values:
                raise StateAccessError(
                    f"{hook_id} cannot modify inactive stage key {key} in {phase}"
                )
            if key not in writable_stage_keys:
                raise StateAccessError(
                    f"{hook_id} did not declare write access to {key}"
                )
            expected_type = self._stage_types[key]
            if not isinstance(value, expected_type):
                raise TypeError(
                    f"{key} must remain {expected_type.__name__}, got {type(value).__name__}"
                )
            if key == "stage.final_decision":
                current = self._stage_values[key]
                if (
                    isinstance(current, FinalDecision)
                    and current.action is FinalDecisionAction.DEFER
                    and value.action is FinalDecisionAction.ACCEPT
                ):
                    raise StateAccessError(
                        f"{hook_id} cannot change a deferred final decision to accept"
                    )
            return

        ref = self._refs.get(key)
        if ref is None:
            raise StateAccessError(f"{hook_id} cannot modify undeclared key {key}")
        if hook_id not in ref.writers:
            raise StateAccessError(f"{hook_id} cannot modify state key {key}")
        if ref.value_type is not None and not isinstance(value, ref.value_type):
            expected = _type_name(ref.value_type)
            raise TypeError(f"{key} must be {expected}, got {type(value).__name__}")


def _type_name(value_type: type[Any] | tuple[type[Any], ...]) -> str:
    if isinstance(value_type, tuple):
        return " | ".join(item.__name__ for item in value_type)
    return value_type.__name__


def _to_trace_value(value: Any) -> Any:
    """Convert core values to JSON-compatible trace payloads without truncation."""

    if isinstance(value, (ModelInput, ParsedOutput, ToolCall, ToolResult)):
        return value.to_dict()
    if isinstance(value, tuple):
        return [_to_trace_value(item) for item in value]
    if isinstance(value, list):
        return [_to_trace_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _to_trace_value(item) for key, item in value.items()}
    if isinstance(value, BaseException):
        return {"type": type(value).__name__, "message": str(value)}
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return _to_trace_value(asdict(value))
    return deepcopy(value)
