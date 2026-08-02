"""Registry hook dispatch with controlled shared state."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from .state import HookContext, HookStateStore, StateRef
from .components import HookModelBackend
from ..agent.types import AgentState, HookModelRequest, HookModelResponse
from ..trajectory import InMemoryTrajectoryRecorder


class HookPhase:
    """Stable extension points exposed by the core loop."""

    PRE_PROMPT = "pre_prompt"
    POST_PROMPT = "post_prompt"
    POST_MODEL = "post_model"
    POST_PARSE = "post_parse"
    PRE_TOOL = "pre_tool"
    POST_TOOL = "post_tool"
    PRE_FINAL = "pre_final"
    ON_ERROR = "on_error"

    ALL = frozenset(
        {
            PRE_PROMPT,
            POST_PROMPT,
            POST_MODEL,
            POST_PARSE,
            PRE_TOOL,
            POST_TOOL,
            PRE_FINAL,
            ON_ERROR,
        }
    )


STAGE_KEYS_BY_PHASE: dict[str, frozenset[str]] = {
    HookPhase.PRE_PROMPT: frozenset(),
    HookPhase.POST_PROMPT: frozenset({"stage.model_input"}),
    HookPhase.POST_MODEL: frozenset({"stage.raw_model_output"}),
    HookPhase.POST_PARSE: frozenset(
        {"stage.parser_input", "stage.parsed_output"}
    ),
    HookPhase.PRE_TOOL: frozenset({"stage.tool_call"}),
    HookPhase.POST_TOOL: frozenset({"stage.tool_call", "stage.tool_result"}),
    HookPhase.PRE_FINAL: frozenset({"stage.final_decision"}),
    HookPhase.ON_ERROR: frozenset({"stage.error"}),
}


@dataclass
class BaseHook(ABC):
    """Abstract, phase-declared contract for one registered hook instance."""

    hook_id: str
    phases: frozenset[str]
    state_refs: tuple[StateRef, ...] = ()
    writable_stage_keys: frozenset[str] = frozenset()
    model_profiles: frozenset[str] = frozenset()
    max_model_calls_per_invocation: int = 1

    def __post_init__(self) -> None:
        if not self.hook_id.strip():
            raise ValueError("hook_id must not be empty")
        if not self.phases:
            raise ValueError("hook must subscribe to at least one phase")
        unknown = self.phases - HookPhase.ALL
        if unknown:
            raise ValueError(f"hook has unknown phases: {sorted(unknown)}")
        available_stage_keys = frozenset().union(
            *(STAGE_KEYS_BY_PHASE[phase] for phase in self.phases)
        )
        invalid_writes = self.writable_stage_keys - available_stage_keys
        if invalid_writes:
            raise ValueError(
                "hook declares stage write access unavailable in its phases: "
                f"{sorted(invalid_writes)}"
            )
        normalized_profiles = frozenset(
            profile.strip().casefold() for profile in self.model_profiles
        )
        if "" in normalized_profiles:
            raise ValueError("hook model profile must not be empty")
        if self.max_model_calls_per_invocation < 1:
            raise ValueError("hook max_model_calls_per_invocation must be positive")
        object.__setattr__(self, "model_profiles", normalized_profiles)

    @abstractmethod
    def handle(self, context: HookContext) -> None:
        """Observe or transform state when ``context.phase`` is triggered."""


class HookPipeline:
    """Dispatch registered hooks in order and record every invocation."""

    def __init__(
        self,
        hooks: Iterable[BaseHook] = (),
        *,
        model_backend: HookModelBackend | None = None,
    ) -> None:
        self._hooks = tuple(hooks)
        self._refs = self._build_ref_registry(self._hooks)
        self._model_backend = model_backend

    @property
    def hooks(self) -> tuple[BaseHook, ...]:
        return self._hooks

    def extended(self, hooks: Iterable[BaseHook]) -> "HookPipeline":
        """Return a pipeline with additional Hooks and the same model backend."""

        return HookPipeline(
            (*self._hooks, *tuple(hooks)),
            model_backend=self._model_backend,
        )

    def begin_run(self, state: AgentState) -> HookStateStore:
        """Create a fresh per-rollout store while retaining declared defaults."""

        return HookStateStore(state, self._refs)

    def run_phase(
        self,
        phase: str,
        *,
        state: AgentState,
        store: HookStateStore,
        trajectory: InMemoryTrajectoryRecorder,
        stage_values: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run subscribed hooks and return the possibly transformed stage values."""

        if phase not in HookPhase.ALL:
            raise ValueError(f"unknown hook phase: {phase}")
        store.open_stage(stage_values or {})
        try:
            for hook in self._hooks:
                if phase not in hook.phases:
                    continue
                pending: dict[str, Any] = {}
                context = HookContext(
                    hook_id=hook.hook_id,
                    phase=phase,
                    state=self._build_view(store, hook, phase, pending),
                    trajectory=trajectory.events,
                    _model_backend=_TracedHookModelBackend(
                        backend=self._model_backend,
                        trajectory=trajectory,
                        step=state.step,
                        hook=hook,
                        phase=phase,
                    ),
                )
                try:
                    hook.handle(context)
                    changes = store.commit(pending)
                except Exception as exc:
                    trajectory.record(
                        "hook_error",
                        state.step,
                        {
                            "phase": phase,
                            "hook_id": hook.hook_id,
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        },
                    )
                    raise
                trajectory.record(
                    "hook_applied",
                    state.step,
                    {
                        "phase": phase,
                        "hook_id": hook.hook_id,
                        "changes": [change.to_trace_dict() for change in changes],
                    },
                )
            return store.current_stage_values()
        finally:
            store.close_stage()

    @staticmethod
    def _build_ref_registry(hooks: tuple[BaseHook, ...]) -> dict[str, StateRef]:
        hook_ids: set[str] = set()
        refs: dict[str, StateRef] = {}
        for hook in hooks:
            if hook.hook_id in hook_ids:
                raise ValueError(f"duplicate hook_id: {hook.hook_id}")
            hook_ids.add(hook.hook_id)
            for ref in hook.state_refs:
                existing = refs.get(ref.key)
                if existing is not None and existing != ref:
                    raise ValueError(f"conflicting StateRef declaration for {ref.key}")
                refs[ref.key] = ref
        return refs

    @staticmethod
    def _build_view(
        store: HookStateStore,
        hook: BaseHook,
        phase: str,
        pending: dict[str, Any],
    ):
        from .state import HookStateView

        return HookStateView(
            _store=store,
            _hook_id=hook.hook_id,
            _phase=phase,
            _writable_stage_keys=hook.writable_stage_keys,
            _pending=pending,
        )


class _TracedHookModelBackend:
    """Invocation-bound permission and Trajectory wrapper around a model backend."""

    def __init__(
        self,
        *,
        backend: HookModelBackend | None,
        trajectory: InMemoryTrajectoryRecorder,
        step: int,
        hook: BaseHook,
        phase: str,
    ) -> None:
        self._backend = backend
        self._trajectory = trajectory
        self._step = step
        self._hook = hook
        self._phase = phase
        self._call_count = 0

    def generate(self, request: HookModelRequest) -> HookModelResponse:
        base_payload = {
            "hook_id": self._hook.hook_id,
            "phase": self._phase,
            "profile": request.profile,
            "purpose": request.purpose,
            "model_input": request.model_input.to_dict(),
        }
        try:
            if request.profile not in self._hook.model_profiles:
                raise PermissionError(
                    f"hook {self._hook.hook_id} cannot call model profile "
                    f"{request.profile!r}"
                )
            self._call_count += 1
            if self._call_count > self._hook.max_model_calls_per_invocation:
                raise RuntimeError(
                    f"hook {self._hook.hook_id} exceeded its per-invocation "
                    "model call limit"
                )
            if self._backend is None:
                raise RuntimeError("hook model backend is not configured")
            response = self._backend.generate(request)
            if not isinstance(response, HookModelResponse):
                raise TypeError("hook model backend must return HookModelResponse")
        except Exception as exc:
            self._trajectory.record(
                "hook_model_error",
                self._step,
                {
                    **base_payload,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
            raise
        self._trajectory.record(
            "hook_model_output",
            self._step,
            {**base_payload, **response.to_dict()},
        )
        return response
