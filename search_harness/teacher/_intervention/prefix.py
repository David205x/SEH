"""Rebuild model-visible context at an inclusive rollout lifecycle boundary."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from search_harness.core import (
    AgentState,
    ChatMessage,
    FinalDecision,
    HookPhase,
    ModelInput,
    ParsedOutput,
    ParsedOutputKind,
    ToolCall,
    ToolResult,
)
from search_harness.datasets import stable_example_id

from .types import PrefixSelector, ReconstructedPrefix


_BOUNDARY_EVENT = {
    HookPhase.POST_PROMPT: "model_input",
    HookPhase.POST_MODEL: "model_output",
    HookPhase.POST_PARSE: "parsed_output",
    HookPhase.PRE_TOOL: "tool_call",
    HookPhase.POST_TOOL: "tool_result",
    HookPhase.PRE_FINAL: "final_answer_candidate",
}
_EVENT_BOUNDARY = {event_type: phase for phase, event_type in _BOUNDARY_EVENT.items()}


def recoverable_prefix_phases() -> tuple[str, ...]:
    """Return lifecycle phases with reconstructable Actor-visible prefixes."""

    return tuple(_BOUNDARY_EVENT)


class PrefixPromptBuilder:
    """Continue an Actor from a fixed structured prefix."""

    def __init__(self, prefix: ModelInput) -> None:
        self._prefix = prefix

    def build(self, state: AgentState) -> ModelInput:
        messages = [*self._prefix.messages, *state.conversation_messages]
        return ModelInput(messages=tuple(messages))


def load_reconstructed_prefix(selector: PrefixSelector) -> ReconstructedPrefix:
    """Load one rollout case and reconstruct the model input at its boundary."""

    source = selector.rollout_file.resolve()
    record = load_rollout_record(
        source, selector.example_id, selector.replicate_id
    )
    example = _require_object(record, "example")
    run = _require_object(record, "run")
    trace = _require_list(run, "trace")
    boundary = _find_boundary(trace, step=selector.step, phase=selector.phase)
    retained = tuple(
        _require_event(event) for event in trace if _event_index(event) <= boundary["index"]
    )
    model_input = _rebuild_model_input(retained, boundary)
    return ReconstructedPrefix(
        selector=PrefixSelector(
            rollout_file=source,
            example_id=selector.example_id,
            replicate_id=selector.replicate_id,
            step=selector.step,
            phase=selector.phase,
        ),
        example=dict(example),
        source_run=dict(run),
        model_input=model_input,
        stage_values=_stage_values(retained, selector.step, selector.phase, model_input),
        retained_trace=retained,
        source_record=dict(record),
    )


def load_rollout_record(
    rollout_file: Path, example_id: str, replicate_id: str
) -> dict[str, Any]:
    """Load one uniquely identified rollout record from UTF-8 JSON or JSONL."""

    source = rollout_file.resolve()
    return dict(_find_record(_read_records(source), example_id, replicate_id))


def list_rollout_references(rollout_file: Path) -> tuple[str, ...]:
    """List stable example/replicate references in source-file order."""

    references: list[str] = []
    for record in _read_records(rollout_file.resolve()):
        example = record.get("example")
        if not isinstance(example, dict):
            raise ValueError("rollout record lacks example object")
        question = str(example.get("question") or "")
        example_id = stable_example_id(
            example.get("example_id"),
            question,
        )
        replicate = record.get("replicate")
        replicate_id = (
            replicate.get("replicate_id")
            if isinstance(replicate, dict)
            else "r000"
        )
        if not isinstance(replicate_id, str) or not replicate_id.strip():
            raise ValueError("rollout replicate_id must be a non-empty string")
        references.append(f"{example_id}/{replicate_id}")
    if len(references) != len(set(references)):
        raise ValueError("rollout file contains duplicate references")
    return tuple(references)


def summarize_rollout_example(
    rollout_file: Path, example_id: str
) -> dict[str, Any]:
    """Return a golden-free logical-example summary and replicate directory."""

    matches: list[dict[str, Any]] = []
    selected_question: str | None = None
    for record in _read_records(rollout_file.resolve()):
        example = record.get("example")
        if not isinstance(example, dict):
            continue
        question = str(example.get("question") or "")
        if stable_example_id(example.get("example_id"), question) != example_id:
            continue
        selected_question = question
        replicate = record.get("replicate")
        replicate_id = (
            replicate.get("replicate_id")
            if isinstance(replicate, dict)
            else "r000"
        )
        run = record.get("run") if isinstance(record.get("run"), dict) else {}
        matches.append(
            {
                "replicate_id": replicate_id,
                "sampling_seed": (
                    replicate.get("sampling_seed")
                    if isinstance(replicate, dict)
                    else None
                ),
                "run_status": run.get("status"),
                "predicted_answer": run.get("answer"),
            }
        )
    if not matches:
        raise KeyError(f"rollout example_id not found: {example_id}")
    replicate_ids = [item["replicate_id"] for item in matches]
    if len(replicate_ids) != len(set(replicate_ids)):
        raise ValueError(f"rollout contains duplicate replicate IDs: {example_id}")
    return {
        "example_id": example_id,
        "question": selected_question,
        "requested_rollouts": len(matches),
        "replicates": matches,
    }


def build_prefix_timeline(record: dict[str, Any]) -> list[dict[str, Any]]:
    """List reconstructable model-context boundaries in source trace order."""

    run = _require_object(record, "run")
    trace = _require_list(run, "trace")
    timeline = []
    for event in (_require_event(item) for item in trace):
        phase = _EVENT_BOUNDARY.get(event["event_type"])
        if phase is None:
            continue
        timeline.append(
            {
                "prefix_id": len(timeline) + 1,
                "step": event["step"],
                "phase": phase,
                "event_index": event["index"],
                "state_summary": _boundary_summary(phase, _event_payload(event)),
            }
        )
    return timeline


def resolve_prefix_boundary(
    record: dict[str, Any], prefix_id: int
) -> dict[str, Any]:
    """Resolve one trajectory-local prefix ID to its exact lifecycle boundary."""

    timeline = build_prefix_timeline(record)
    if prefix_id < 1:
        raise ValueError("prefix_id must be positive")
    if prefix_id > len(timeline):
        raise ValueError(
            f"prefix_id is not selectable; available range is 1..{len(timeline)}"
        )
    return dict(timeline[prefix_id - 1])


def _read_records(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"rollout file does not exist: {path}")
    if path.suffix.casefold() == ".jsonl":
        records: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"invalid rollout JSONL at {path}:{line_number}: {exc.msg}"
                    ) from exc
                if not isinstance(value, dict):
                    raise TypeError(f"rollout record at {path}:{line_number} must be an object")
                records.append(value)
        return records

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid rollout JSON at {path}: {exc.msg}") from exc
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list) and all(isinstance(item, dict) for item in value):
        return list(value)
    raise TypeError("rollout JSON must be an object or an array of objects")


def _find_record(
    records: list[dict[str, Any]], example_id: str, replicate_id: str
) -> dict[str, Any]:
    matches = []
    for record in records:
        example = record.get("example")
        if not isinstance(example, dict):
            continue
        question = str(example.get("question") or "")
        current_id = stable_example_id(example.get("example_id"), question)
        replicate = record.get("replicate")
        current_replicate_id = (
            replicate.get("replicate_id")
            if isinstance(replicate, dict)
            else "r000"
        )
        if current_id == example_id and current_replicate_id == replicate_id:
            matches.append(record)
    if not matches:
        raise KeyError(f"rollout identity not found: {example_id}/{replicate_id}")
    if len(matches) > 1:
        raise ValueError(
            f"rollout contains duplicate identity: {example_id}/{replicate_id}"
        )
    return matches[0]


def _find_boundary(
    trace: list[Any], *, step: int, phase: str
) -> dict[str, Any]:
    events = [_require_event(event) for event in trace]
    event_type = _BOUNDARY_EVENT.get(phase)
    candidates = []
    if event_type is not None:
        candidates = [
            event
            for event in events
            if event["step"] == step and event["event_type"] == event_type
        ]
    else:
        candidates = [
            event
            for event in events
            if event["step"] == step
            and event["event_type"] == "hook_applied"
            and _event_payload(event).get("phase") == phase
        ]
    if not candidates:
        raise KeyError(f"rollout boundary not found: step={step}, phase={phase}")
    return candidates[-1]


def _rebuild_model_input(
    retained: tuple[dict[str, Any], ...], boundary: dict[str, Any]
) -> ModelInput:
    model_events = [
        event
        for event in retained
        if event["event_type"] == "model_input" and event["index"] <= boundary["index"]
    ]
    if not model_events:
        raise ValueError("prefix boundary has no preceding model_input")
    model_event = model_events[-1]
    messages = _messages_from_payload(_event_payload(model_event))

    following = [
        event
        for event in retained
        if model_event["index"] < event["index"] <= boundary["index"]
    ]
    outputs = [event for event in following if event["event_type"] == "model_output"]
    if outputs:
        raw_output = _event_payload(outputs[-1]).get("raw_output")
        if not isinstance(raw_output, str):
            raise TypeError("model_output.raw_output must be a string")
        messages.append(ChatMessage(role="assistant", content=raw_output))

    tool_results = [event for event in following if event["event_type"] == "tool_result"]
    if tool_results:
        content = _event_payload(tool_results[-1]).get("content")
        if not isinstance(content, str):
            raise TypeError("tool_result.content must be a string")
        messages.append(ChatMessage(role="user", content=content))
    return ModelInput.from_messages(messages)


def _stage_values(
    retained: tuple[dict[str, Any], ...],
    step: int,
    phase: str,
    model_input: ModelInput,
) -> dict[str, Any]:
    step_events = [event for event in retained if event["step"] == step]
    payloads = {event["event_type"]: _event_payload(event) for event in step_events}
    if phase == HookPhase.POST_PROMPT:
        return {"model_input": model_input}
    if phase == HookPhase.POST_MODEL:
        return {"raw_model_output": _required_string(payloads, "model_output", "raw_output")}
    if phase == HookPhase.POST_PARSE:
        raw = _required_string(payloads, "model_output", "raw_output")
        return {
            "parser_input": raw,
            "parsed_output": _parsed_output(payloads.get("parsed_output")),
        }
    if phase == HookPhase.PRE_TOOL:
        return {"tool_call": _tool_call(payloads.get("tool_call"))}
    if phase == HookPhase.POST_TOOL:
        return {
            "tool_call": _tool_call(payloads.get("tool_call")),
            "tool_result": _tool_result(payloads.get("tool_result")),
        }
    if phase == HookPhase.PRE_FINAL:
        candidate = _required_string(
            payloads, "final_answer_candidate", "answer"
        )
        return {"final_decision": FinalDecision.accept(candidate)}
    return {}


def _messages_from_payload(payload: dict[str, Any]) -> list[ChatMessage]:
    values = payload.get("messages")
    if not isinstance(values, list) or not values:
        raise TypeError("model_input.messages must be a non-empty list")
    messages = []
    for value in values:
        if not isinstance(value, dict):
            raise TypeError("model_input message must be an object")
        messages.append(ChatMessage(role=str(value.get("role", "")), content=str(value.get("content", ""))))
    return messages


def _parsed_output(payload: Any) -> ParsedOutput:
    if not isinstance(payload, dict):
        raise TypeError("parsed_output payload must be an object")
    kind = ParsedOutputKind(str(payload.get("kind")))
    thinking = payload.get("inband_thinking")
    if kind is ParsedOutputKind.TOOL_CALL:
        return ParsedOutput.for_tool_call(_tool_call(payload.get("tool_call")), thinking)
    if kind is ParsedOutputKind.FINAL_ANSWER:
        return ParsedOutput.for_final_answer(str(payload.get("final_answer", "")), thinking)
    return ParsedOutput.invalid(str(payload.get("error") or "invalid output"), thinking)


def _tool_call(payload: Any) -> ToolCall:
    if not isinstance(payload, dict):
        raise TypeError("tool_call payload must be an object")
    arguments = payload.get("arguments", {})
    if not isinstance(arguments, dict):
        raise TypeError("tool_call.arguments must be an object")
    return ToolCall(name=str(payload.get("name", "")), arguments=arguments)


def _tool_result(payload: Any) -> ToolResult:
    if not isinstance(payload, dict):
        raise TypeError("tool_result payload must be an object")
    metadata = payload.get("metadata", {})
    if not isinstance(metadata, dict):
        raise TypeError("tool_result.metadata must be an object")
    return ToolResult(
        name=str(payload.get("name", "")),
        content=str(payload.get("content", "")),
        metadata=metadata,
    )


def _boundary_summary(phase: str, payload: dict[str, Any]) -> str:
    if phase == HookPhase.POST_PROMPT:
        messages = payload.get("messages")
        count = len(messages) if isinstance(messages, list) else 0
        return f"Model input assembled with {count} messages; generation is next."
    if phase == HookPhase.POST_MODEL:
        return f"Model generation completed: {_preview(payload.get('raw_output'))}"
    if phase == HookPhase.POST_PARSE:
        kind = payload.get("kind")
        return f"Model output parsed as {kind}."
    if phase == HookPhase.PRE_TOOL:
        return (
            f"Tool call prepared: {payload.get('name')}"
            f"({_preview(payload.get('arguments'))})."
        )
    if phase == HookPhase.POST_TOOL:
        return (
            f"Tool result available to the continuation: "
            f"{_preview(payload.get('content'))}"
        )
    if phase == HookPhase.PRE_FINAL:
        return f"Final answer candidate prepared: {_preview(payload.get('answer'))}"
    raise ValueError(f"unsupported prefix phase: {phase}")


def _preview(value: Any, limit: int = 240) -> str:
    if isinstance(value, str):
        text = " ".join(value.split())
    else:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...[truncated {len(text) - limit} chars]"


def _required_string(
    payloads: dict[str, dict[str, Any]], event_type: str, field: str
) -> str:
    value = payloads.get(event_type, {}).get(field)
    if not isinstance(value, str):
        raise TypeError(f"{event_type}.{field} must be a string")
    return value


def _require_object(value: dict[str, Any], key: str) -> dict[str, Any]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise TypeError(f"rollout record {key} must be an object")
    return item


def _require_list(value: dict[str, Any], key: str) -> list[Any]:
    item = value.get(key)
    if not isinstance(item, list):
        raise TypeError(f"rollout record {key} must be a list")
    return item


def _require_event(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError("trace event must be an object")
    if not isinstance(value.get("index"), int) or not isinstance(value.get("step"), int):
        raise TypeError("trace event index and step must be integers")
    if not isinstance(value.get("event_type"), str):
        raise TypeError("trace event_type must be a string")
    _event_payload(value)
    return dict(value)


def _event_index(event: Any) -> int:
    return int(_require_event(event)["index"])


def _event_payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload")
    if not isinstance(payload, dict):
        raise TypeError("trace event payload must be an object")
    return payload
