"""Deterministic runtime guards that do not alter answer semantics."""

from __future__ import annotations

from typing import Any

from search_harness.framework import BaseHook, HookContext, HookPhase, ToolCall


class ForceTopKHook(BaseHook):
    def __init__(self, topk: int) -> None:
        self._topk = topk
        super().__init__(
            hook_id="force_topk",
            phases=frozenset({HookPhase.PRE_TOOL}),
            writable_stage_keys=frozenset({"stage.tool_call"}),
        )

    def handle(self, context: HookContext) -> None:
        call = context.state.get("stage.tool_call")
        if not isinstance(call, ToolCall):
            raise TypeError("stage.tool_call must be a ToolCall")
        if call.name != "search":
            return
        arguments = dict(call.arguments)
        arguments["topk"] = self._topk
        context.state.set("stage.tool_call", ToolCall(name=call.name, arguments=arguments))


class ProtocolRepairHook(BaseHook):
    def __init__(self) -> None:
        super().__init__(
            hook_id="protocol_repair",
            phases=frozenset({HookPhase.POST_MODEL}),
            writable_stage_keys=frozenset({"stage.raw_model_output"}),
        )

    def handle(self, context: HookContext) -> None:
        raw = context.state.get("stage.raw_model_output")
        core = context.state.get("core")
        if not isinstance(raw, str) or not isinstance(core, dict):
            raise TypeError("protocol repair requires output and core state")
        text = raw.strip()
        if "<tool_call>" in text or "<final_answer>" in text:
            return
        if not core.get("tool_interactions") or not text:
            return
        if len(text) <= 300 and len(text.split()) <= 40 and not text.startswith("{"):
            context.state.set("stage.raw_model_output", f"<final_answer>{text}</final_answer>")


def build(config: dict[str, Any], context: Any) -> tuple[BaseHook, BaseHook]:
    del context
    unknown = set(config) - {"topk"}
    if unknown:
        raise ValueError(f"unsupported runtime guard config keys: {sorted(unknown)}")
    topk = config.get("topk", 10)
    if not isinstance(topk, int) or topk < 1:
        raise ValueError("topk must be a positive integer")
    return ForceTopKHook(topk), ProtocolRepairHook()
