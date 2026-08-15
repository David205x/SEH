"""Deterministic, model-visible projections for Teacher query tools."""

from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


_VISIBLE = "STUDENT_VISIBLE"
_RUNTIME = "RUNTIME_ONLY"
_DERIVED = "DERIVED_VIEW"
_PREVIEW_LIMIT = 320


def render_evaluation_case(case: dict[str, Any]) -> str:
    """Render one Evaluation Case without Teacher/provider metadata."""

    replicates = case.get("replicates")
    replicate_items = replicates if isinstance(replicates, list) else []
    lines = [
        "# Evaluation Case",
        "",
        _table(
            ("field", "value"),
            (
                ("example_id", _value(case.get("example_id"))),
                ("stability", _value(case.get("stability"))),
                ("success_rate", _value(case.get("success_rate"))),
                (
                    "answer_consistency",
                    _value(case.get("answer_consistency")),
                ),
                ("run_status", _value(case.get("run_status"))),
                ("replicate_count", str(len(replicate_items))),
            ),
        ),
        "",
        "Question:",
        _exact_block("question", _value(case.get("question"))),
        "",
        "## Replicates",
        "",
        (
            "Note: `score` is the verdict; `assessment=unavailable` means a "
            "legacy Artifact omitted assessment text."
        ),
        "",
        _table(
            (
                "replicate",
                "score",
                "assessment",
                "answer",
                "status",
                "error",
                "steps",
                "tool_calls",
                "retriever_errors",
                "duplicate_queries",
                "input_tokens",
                "output_tokens",
                "total_tokens",
                "student_total_tokens",
                "hook_total_tokens",
            ),
            tuple(_replicate_row(item) for item in replicate_items),
        ),
    ]
    return "\n".join(lines).strip()


@dataclass(frozen=True)
class _BlockRevision:
    block_id: int
    revision: int
    role: str
    kind: str
    content: str
    visibility: str
    source_event: int | None

    @property
    def ref(self) -> str:
        return f"{self.block_id}@{self.revision}"

    def summary(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "role": self.role,
            "kind": self.kind,
            "characters": len(self.content),
            "content_state": "preview",
            "preview": _preview(self.content),
            "visibility": self.visibility,
            "sent_to_student": self.visibility == _VISIBLE,
        }


class TeacherTrajectoryView:
    """Build a stable block/revision view over one immutable Rollout record."""

    def __init__(
        self,
        record: dict[str, Any],
        *,
        case: dict[str, Any] | None = None,
        replicate_id: str | None = None,
    ) -> None:
        self.record = record
        self.case = case if isinstance(case, dict) else {}
        replicate = record.get("replicate")
        replicate = replicate if isinstance(replicate, dict) else {}
        self.replicate_id = replicate_id or str(
            replicate.get("replicate_id", "unavailable")
        )
        self._blocks: dict[tuple[int, int], _BlockRevision] = {}
        self._next_block_id = 1
        self._revisions: list[dict[str, Any]] = []
        self._events: list[dict[str, Any]] = []
        self._changes: list[dict[str, Any]] = []
        self._context_occurrences: list[tuple[int, _BlockRevision]] = []
        self._build()

    def render(self) -> str:
        """Render the default compact Trajectory Tool Output."""

        example = self.record.get("example")
        example = example if isinstance(example, dict) else {}
        run = self.record.get("run")
        run = run if isinstance(run, dict) else {}
        lines = [
            "# Student Trajectory",
            "",
            _table(
                ("field", "value"),
                (
                    ("example_id", _value(example.get("example_id"))),
                    ("replicate_id", self.replicate_id),
                    ("run_status", _value(run.get("status"))),
                    ("answer", _value(run.get("answer"))),
                    ("error", _value(run.get("error"))),
                ),
            ),
            "",
            "Question:",
            _exact_block(
                "question",
                _value(example.get("question") or run.get("question")),
            ),
            "",
            "## Context Revisions",
            "",
            _jsonl(self._revisions),
            "",
            "## Behavior Events",
            "",
            _jsonl(self._events),
            "",
            "## Extension Changes",
            "",
            _jsonl(self._changes),
        ]
        return "\n".join(lines).strip()

    def read_block(
        self,
        *,
        block_id: int,
        revision: int,
        offset: int,
        max_characters: int,
    ) -> str:
        """Return an exact unescaped slice of one referenced block."""

        block = self._require_block(block_id, revision)
        if offset < 0:
            raise ValueError("offset must be non-negative")
        if max_characters < 1:
            raise ValueError("max_characters must be positive")
        content = block.content[offset : offset + max_characters]
        end = offset + len(content)
        header = _table(
            ("field", "value"),
            (
                ("block_ref", block.ref),
                ("visibility", block.visibility),
                ("role", block.role),
                ("kind", block.kind),
                ("characters", str(len(block.content))),
                ("slice", f"{offset}:{end}"),
                (
                    "remaining_characters",
                    str(max(0, len(block.content) - end)),
                ),
            ),
        )
        return (
            f"# Context Block\n\n{header}\n\n"
            f"<context_block ref=\"{block.ref}\">\n"
            f"{content}\n"
            "</context_block>"
        )

    def search_runtime_blocks(
        self,
        query: str,
        *,
        max_matches: int,
    ) -> str:
        """Search exact Runtime-only contents without loading whole blocks."""

        needle = query.strip().casefold()
        if not needle:
            raise ValueError("query must not be empty")
        if max_matches < 1:
            raise ValueError("max_matches must be positive")
        matches: list[dict[str, Any]] = []
        for block in self._blocks.values():
            if block.visibility != _RUNTIME:
                continue
            haystack = block.content.casefold()
            start = 0
            while len(matches) < max_matches:
                index = haystack.find(needle, start)
                if index < 0:
                    break
                excerpt_start = max(0, index - 120)
                excerpt_end = min(
                    len(block.content),
                    index + len(query) + 120,
                )
                matches.append(
                    {
                        "block_ref": block.ref,
                        "offset": index,
                        "excerpt": block.content[excerpt_start:excerpt_end],
                        "visibility": _RUNTIME,
                    }
                )
                start = index + max(1, len(needle))
            if len(matches) >= max_matches:
                break
        return "# Runtime-only Block Matches\n\n" + _jsonl(matches)

    def render_change(self, change_id: str) -> str:
        """Render one deterministic Extension Change and its block directory."""

        change = next(
            (item for item in self._changes if item["change_id"] == change_id),
            None,
        )
        if change is None:
            available = ", ".join(item["change_id"] for item in self._changes)
            raise KeyError(
                f"unknown change_id {change_id}; available: {available or 'none'}"
            )
        references = [
            *change.get("source_refs", []),
            *change.get("effective_refs", []),
        ]
        blocks = [
            self._require_block(*_parse_block_ref(reference)).summary()
            for reference in references
        ]
        return "\n".join(
            (
                "# Extension Change",
                "",
                _jsonl([change]),
                "",
                "## Referenced Blocks",
                "",
                _jsonl(blocks),
            )
        )

    def _build(self) -> None:
        run = self.record.get("run")
        run = run if isinstance(run, dict) else {}
        trace = [
            event
            for event in run.get("trace", [])
            if isinstance(event, dict)
        ]
        self._build_context_revisions(trace)
        hook_purposes: dict[tuple[str, str], str] = {}
        for event in trace:
            event_type = event.get("event_type")
            payload = event.get("payload")
            payload = payload if isinstance(payload, dict) else {}
            event_index = _event_index(event)
            if event_type == "model_input":
                continue
            if event_type == "hook_model_output":
                key = (
                    str(payload.get("hook_id", "unavailable")),
                    str(payload.get("phase", "unavailable")),
                )
                hook_purposes[key] = _value(payload.get("purpose"))
                self._events.append(
                    {
                        "index": event_index,
                        "step": event.get("step"),
                        "event_type": event_type,
                        "visibility": _RUNTIME,
                        "hook_id": payload.get("hook_id"),
                        "phase": payload.get("phase"),
                        "purpose": payload.get("purpose"),
                        "raw_output": payload.get("raw_output"),
                    }
                )
                continue
            if event_type == "hook_applied":
                event_changes = self._project_hook_changes(
                    event,
                    purpose=hook_purposes.get(
                        (
                            str(payload.get("hook_id", "unavailable")),
                            str(payload.get("phase", "unavailable")),
                        )
                    ),
                )
                self._events.append(
                    {
                        "index": event_index,
                        "step": event.get("step"),
                        "event_type": event_type,
                        "visibility": _DERIVED,
                        "hook_id": payload.get("hook_id"),
                        "phase": payload.get("phase"),
                        "student_context_changed": (
                            "yes"
                            if any(
                                item["delivery_status"] == "verified"
                                and item["effect_kind"] != "unchanged"
                                for item in event_changes
                            )
                            else "no"
                        ),
                        "change_refs": [
                            item["change_id"] for item in event_changes
                        ],
                    }
                )
                continue
            projected = self._project_event(event)
            if projected is not None:
                self._events.append(projected)

    def _build_context_revisions(self, trace: list[dict[str, Any]]) -> None:
        previous_messages: list[dict[str, Any]] = []
        previous_refs: list[_BlockRevision] = []
        revision_number = 0
        for event in trace:
            if event.get("event_type") != "model_input":
                continue
            payload = event.get("payload")
            payload = payload if isinstance(payload, dict) else {}
            messages = payload.get("messages")
            if not isinstance(messages, list):
                continue
            normalized = [_normalize_message(item) for item in messages]
            current_refs, changed, removed = self._align_messages(
                previous_messages,
                previous_refs,
                normalized,
                event_index=_event_index(event),
            )
            revision_number += 1
            self._revisions.append(
                {
                    "revision": revision_number,
                    "model_input_event": _event_index(event),
                    "step": event.get("step"),
                    "visibility": _VISIBLE,
                    "order": [block.ref for block in current_refs],
                    "changed_blocks": [block.summary() for block in changed],
                    "removed_refs": [block.ref for block in removed],
                }
            )
            self._context_occurrences.extend(
                (_event_index(event), block) for block in current_refs
            )
            previous_messages = normalized
            previous_refs = current_refs

    def _align_messages(
        self,
        old_messages: list[dict[str, Any]],
        old_refs: list[_BlockRevision],
        new_messages: list[dict[str, Any]],
        *,
        event_index: int,
    ) -> tuple[
        list[_BlockRevision],
        list[_BlockRevision],
        list[_BlockRevision],
    ]:
        matcher = difflib.SequenceMatcher(
            None,
            [_message_signature(item) for item in old_messages],
            [_message_signature(item) for item in new_messages],
            autojunk=False,
        )
        current: list[_BlockRevision] = []
        changed: list[_BlockRevision] = []
        removed: list[_BlockRevision] = []
        for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes():
            if tag == "equal":
                current.extend(old_refs[old_start:old_end])
                continue
            if tag in {"replace", "delete"}:
                old_slice = old_refs[old_start:old_end]
            else:
                old_slice = []
            if tag in {"replace", "insert"}:
                new_slice = new_messages[new_start:new_end]
            else:
                new_slice = []
            paired = min(len(old_slice), len(new_slice))
            for index in range(paired):
                prior = old_slice[index]
                message = new_slice[index]
                block = self._add_block(
                    block_id=prior.block_id,
                    revision=prior.revision + 1,
                    role=message["role"],
                    kind=_message_kind(message),
                    content=message["content"],
                    visibility=_VISIBLE,
                    source_event=event_index,
                )
                current.append(block)
                changed.append(block)
            removed.extend(old_slice[paired:])
            for message in new_slice[paired:]:
                block = self._add_block(
                    role=message["role"],
                    kind=_message_kind(message),
                    content=message["content"],
                    visibility=_VISIBLE,
                    source_event=event_index,
                )
                current.append(block)
                changed.append(block)
        return current, changed, removed

    def _project_event(self, event: dict[str, Any]) -> dict[str, Any] | None:
        event_type = str(event.get("event_type", "unknown"))
        payload = event.get("payload")
        payload = payload if isinstance(payload, dict) else {}
        base = {
            "index": _event_index(event),
            "step": event.get("step"),
            "event_type": event_type,
        }
        if event_type == "model_output":
            metadata = payload.get("metadata")
            metadata = metadata if isinstance(metadata, dict) else {}
            reasoning = next(
                (
                    metadata.get(key)
                    for key in ("reasoning_content", "reasoning", "thinking")
                    if isinstance(metadata.get(key), str)
                    and metadata.get(key)
                ),
                None,
            )
            output = _content_text(payload.get("raw_output"))
            output_block = self._find_or_add_content_block(
                output,
                event_index=_event_index(event),
                role="assistant",
                kind="student_output",
            )
            projected = base | {
                "visibility": output_block.visibility,
                "student_output_ref": output_block.ref,
                "student_output_characters": len(output),
                "student_output_preview": _preview(output),
            }
            if isinstance(reasoning, str) and reasoning:
                reasoning_block = self._find_or_add_content_block(
                    reasoning,
                    event_index=_event_index(event),
                    role="assistant",
                    kind="native_reasoning",
                )
                projected.update(
                    {
                        "native_reasoning_ref": reasoning_block.ref,
                        "native_reasoning_characters": len(reasoning),
                        "native_reasoning_preview": _preview(reasoning),
                    }
                )
            else:
                projected["native_reasoning_ref"] = "none"
            return projected
        if event_type == "tool_result":
            content = _content_text(payload)
            block = self._find_or_add_content_block(
                content,
                event_index=_event_index(event),
                role="user",
                kind="tool_result",
            )
            return base | {
                "visibility": block.visibility,
                "name": payload.get("name"),
                "content_ref": block.ref,
                "characters": len(content),
                "preview": _preview(content),
            }
        kept_types = {
            "parsed_output",
            "tool_call",
            "tool_error",
            "hook_error",
            "final_answer_candidate",
            "final_deferred",
            "final_answer",
            "invalid_output",
            "invalid_output_feedback",
            "max_steps_reached",
        }
        if event_type not in kept_types:
            return None
        return base | {
            "visibility": _RUNTIME,
            "payload": _strip_duplicate_metadata(payload),
        }

    def _project_hook_changes(
        self,
        event: dict[str, Any],
        *,
        purpose: str | None,
    ) -> list[dict[str, Any]]:
        payload = event.get("payload")
        payload = payload if isinstance(payload, dict) else {}
        raw_changes = payload.get("changes")
        if not isinstance(raw_changes, list):
            return []
        projected: list[dict[str, Any]] = []
        for raw in raw_changes:
            if not isinstance(raw, dict):
                continue
            before = _content_text(raw.get("before"))
            after = _content_text(raw.get("after"))
            before_block = self._find_or_add_content_block(
                before,
                event_index=_event_index(event),
                role="user",
                kind=_change_kind(raw),
                prefer_after=False,
            )
            after_block = self._find_or_add_content_block(
                after,
                event_index=_event_index(event),
                role="user",
                kind=_change_kind(raw),
                prefer_after=True,
            )
            change_id = f"change_{len(self._changes) + 1:03d}"
            item = {
                "change_id": change_id,
                "hook_id": payload.get("hook_id"),
                "phase": payload.get("phase"),
                "effect_kind": _effect_kind(before, after),
                "target": raw.get("key", "unavailable"),
                "source_refs": [before_block.ref],
                "effective_refs": [after_block.ref],
                "delivery_status": (
                    "verified"
                    if after_block.visibility == _VISIBLE
                    else "not_delivered"
                ),
                "declared_purpose": purpose or "unavailable",
                "before_characters": len(before),
                "after_characters": len(after),
            }
            if max(len(before), len(after)) <= 800:
                item["diff"] = _compact_diff(before, after)
            else:
                item["before_preview"] = _preview(before)
                item["after_preview"] = _preview(after)
                item["size_ratio"] = (
                    round(len(after) / len(before), 4) if before else "n/a"
                )
            self._changes.append(item)
            projected.append(item)
        return projected

    def _find_or_add_content_block(
        self,
        content: str,
        *,
        event_index: int,
        role: str,
        kind: str,
        prefer_after: bool = True,
    ) -> _BlockRevision:
        candidates = [
            (context_event, block)
            for context_event, block in self._context_occurrences
            if block.content == content
        ]
        if candidates:
            if prefer_after:
                later = [item for item in candidates if item[0] > event_index]
                if later:
                    return min(later, key=lambda item: item[0])[1]
            return min(candidates, key=lambda item: abs(item[0] - event_index))[1]
        return self._add_block(
            role=role,
            kind=kind,
            content=content,
            visibility=_RUNTIME,
            source_event=event_index,
        )

    def _add_block(
        self,
        *,
        role: str,
        kind: str,
        content: str,
        visibility: str,
        source_event: int | None,
        block_id: int | None = None,
        revision: int = 1,
    ) -> _BlockRevision:
        assigned_id = block_id or self._next_block_id
        if block_id is None:
            self._next_block_id += 1
        block = _BlockRevision(
            block_id=assigned_id,
            revision=revision,
            role=role,
            kind=kind,
            content=content,
            visibility=visibility,
            source_event=source_event,
        )
        self._blocks[(assigned_id, revision)] = block
        return block

    def _require_block(self, block_id: int, revision: int) -> _BlockRevision:
        try:
            return self._blocks[(block_id, revision)]
        except KeyError as exc:
            available = ", ".join(
                block.ref for block in self._blocks.values()
            )
            raise KeyError(
                f"unknown block reference {block_id}@{revision}; "
                f"available: {available}"
            ) from exc


def render_student_capability_view(
    *,
    manifest: dict[str, Any],
    records: Iterable[dict[str, Any]],
) -> str:
    """Render only Student-observable capability registration facts."""

    first_prompt = _first_model_visible_prompt(records)
    tool_summaries = _tool_summaries(first_prompt)
    raw_tools = manifest.get("tools")
    tools = raw_tools if isinstance(raw_tools, list) else []
    tool_rows = []
    for item in tools:
        if not isinstance(item, dict):
            continue
        instance_id = _value(item.get("instance_id"))
        tool_rows.append(
            (
                instance_id,
                tool_summaries.get(instance_id, "unavailable"),
            )
        )
    raw_extensions = manifest.get("extensions")
    extensions = raw_extensions if isinstance(raw_extensions, list) else []
    extension_rows = []
    for item in extensions:
        if not isinstance(item, dict):
            continue
        phases = sorted(_find_named_values(item.get("config"), "phase"))
        extension_rows.append(
            (
                _value(item.get("instance_id")),
                ", ".join(phases) if phases else "unavailable",
                _phase_surfaces(phases),
            )
        )
    action_types = _accepted_action_types(first_prompt)
    lines = [
        "# Student Capability View",
        "",
        _table(
            ("field", "value"),
            (
                ("harness_id", _value(manifest.get("harness_id"))),
                (
                    "accepted_action_types",
                    ", ".join(action_types) if action_types else "unavailable",
                ),
                ("prompt_registered", "yes" if manifest.get("prompt") else "no"),
                ("output_registered", "yes" if manifest.get("output") else "no"),
            ),
        ),
        "",
        "## Model-visible Tools",
        "",
        _table(("tool", "capability"), tuple(tool_rows)),
        "",
        "## Registered Extensions",
        "",
        _table(
            ("extension", "phases", "possible_student_surface"),
            tuple(extension_rows),
        ),
        "",
        "Registration proves availability only; use Trajectory evidence for actual invocation and change.",
    ]
    return "\n".join(lines).strip()


def render_student_behavior_interface(
    *,
    manifest: dict[str, Any],
    record: dict[str, Any],
) -> str:
    """Render the declared Student-facing behavior interface without source code."""

    messages = _first_model_input_messages(record)
    prompt_messages = [
        item for item in messages if item.get("role") in {"system", "developer"}
    ]
    prompt_text = "\n\n".join(item.get("content", "") for item in prompt_messages)
    tool_summaries = _tool_summaries(prompt_text)
    raw_tools = manifest.get("tools")
    tools = raw_tools if isinstance(raw_tools, list) else []
    tool_rows = []
    for item in tools:
        if not isinstance(item, dict):
            continue
        instance_id = _value(item.get("instance_id"))
        tool_rows.append(
            (
                instance_id,
                tool_summaries.get(instance_id, "declared in exact prompt below"),
            )
        )
    raw_extensions = manifest.get("extensions")
    extensions = raw_extensions if isinstance(raw_extensions, list) else []
    extension_rows = []
    for item in extensions:
        if not isinstance(item, dict):
            continue
        config = item.get("config")
        phases = sorted(_find_named_values(config, "phase"))
        extension_rows.append(
            (
                _value(item.get("instance_id")),
                ", ".join(phases) if phases else "unavailable",
                _phase_surfaces(phases),
                _declared_purpose(config),
            )
        )
    feedback = _observed_invalid_feedback(record)
    output = manifest.get("output")
    output = output if isinstance(output, dict) else {}
    lines = [
        "# Student Behavior Interface",
        "",
        _table(
            ("field", "value"),
            (
                ("harness_id", _value(manifest.get("harness_id"))),
                ("output_component", _value(output.get("instance_id"))),
                (
                    "accepted_action_types",
                    ", ".join(_accepted_action_types(prompt_text))
                    or "unavailable",
                ),
                (
                    "observed_invalid_output_feedback",
                    feedback or "unavailable",
                ),
            ),
        ),
        "",
        "## Tool Index",
        "",
        _table(("tool", "model-visible declaration"), tuple(tool_rows)),
        "",
        "## Extension Interface",
        "",
        _table(
            ("extension", "phases", "read/write surface", "declared purpose"),
            tuple(extension_rows),
        ),
        "",
        "## Exact Model-visible Prompt",
        "",
    ]
    for order, message in enumerate(prompt_messages, start=1):
        lines.append(
            _exact_block(
                f"model_visible_prompt role={message.get('role')} order={order}",
                message.get("content", ""),
            )
        )
    return "\n".join(lines).strip()


def _replicate_row(replicate: object) -> tuple[str, ...]:
    item = replicate if isinstance(replicate, dict) else {}
    teacher = item.get("teacher")
    teacher = teacher if isinstance(teacher, dict) else {}
    execution = item.get("execution")
    execution = execution if isinstance(execution, dict) else {}
    tokens = execution.get("tokens")
    tokens = tokens if isinstance(tokens, dict) else {}
    if item.get("score_source") != "teacher":
        assessment: object = "n/a"
    elif "assessment" not in teacher:
        assessment = "unavailable"
    elif item.get("score") is None:
        assessment = teacher.get("assessment") or "unresolved"
    else:
        assessment = teacher.get("assessment") or "none"
    hook_tokens_present = "hook_total_tokens" in tokens
    return tuple(
        _cell(value)
        for value in (
            item.get("replicate_id"),
            item.get("score"),
            assessment,
            item.get("predicted_answer"),
            item.get("run_status"),
            item.get("runner_error"),
            execution.get("steps"),
            execution.get("tool_calls"),
            execution.get("retriever_errors"),
            execution.get("duplicate_queries"),
            _available_value(tokens, "input_tokens"),
            _available_value(tokens, "output_tokens"),
            _available_value(tokens, "total_tokens"),
            (
                _available_value(tokens, "student_total_tokens")
                if hook_tokens_present
                else "n/a"
            ),
            (
                _available_value(tokens, "hook_total_tokens")
                if hook_tokens_present
                else "n/a"
            ),
        )
    )


def _normalize_message(value: object) -> dict[str, str]:
    item = value if isinstance(value, dict) else {}
    return {
        "role": _value(item.get("role")),
        "content": _content_text(item.get("content")),
    }


def _message_signature(message: dict[str, str]) -> tuple[str, str]:
    return message["role"], message["content"]


def _message_kind(message: dict[str, str]) -> str:
    if message["role"] == "user" and message["content"].lstrip().startswith("["):
        return "tool_result_or_user_message"
    return "message"


def _content_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and isinstance(value.get("content"), str):
        return value["content"]
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _strip_duplicate_metadata(value: object) -> object:
    if isinstance(value, list):
        return [_strip_duplicate_metadata(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        if key == "omitted":
            continue
        if key == "metadata" and isinstance(item, dict):
            metadata = {
                meta_key: _strip_duplicate_metadata(meta_value)
                for meta_key, meta_value in item.items()
                if meta_key != "results"
            }
            if metadata:
                result[key] = metadata
            continue
        result[key] = _strip_duplicate_metadata(item)
    return result


def _change_kind(change: dict[str, Any]) -> str:
    key = str(change.get("key", "context"))
    return "tool_result" if "tool_result" in key else "context_change"


def _effect_kind(before: str, after: str) -> str:
    if before == after:
        return "unchanged"
    if not before and after:
        return "insert"
    if before and not after:
        return "delete"
    return "replace"


def _compact_diff(before: str, after: str) -> str:
    return "\n".join(
        difflib.unified_diff(
            before.splitlines(),
            after.splitlines(),
            fromfile="source",
            tofile="effective",
            lineterm="",
        )
    )


def _event_index(event: dict[str, Any]) -> int:
    value = event.get("index")
    return value if isinstance(value, int) else -1


def _parse_block_ref(reference: str) -> tuple[int, int]:
    block_id, separator, revision = reference.partition("@")
    if separator != "@":
        raise ValueError(f"invalid block reference: {reference}")
    return int(block_id), int(revision)


def _available_value(value: dict[str, Any], key: str) -> object:
    return value[key] if key in value else "unavailable"


def _first_model_input_messages(record: dict[str, Any]) -> list[dict[str, str]]:
    run = record.get("run")
    run = run if isinstance(run, dict) else {}
    for event in run.get("trace", []):
        if not isinstance(event, dict) or event.get("event_type") != "model_input":
            continue
        payload = event.get("payload")
        payload = payload if isinstance(payload, dict) else {}
        messages = payload.get("messages")
        if isinstance(messages, list):
            return [_normalize_message(item) for item in messages]
    return []


def _first_model_visible_prompt(records: Iterable[dict[str, Any]]) -> str:
    for record in records:
        messages = _first_model_input_messages(record)
        prompt = "\n\n".join(
            item["content"]
            for item in messages
            if item["role"] in {"system", "developer"}
        )
        if prompt:
            return prompt
    return ""


def _tool_summaries(prompt: str) -> dict[str, str]:
    pattern = re.compile(r"^- `([^`]+)`: (.+)$", re.MULTILINE)
    return {name: description.strip() for name, description in pattern.findall(prompt)}


def _accepted_action_types(prompt: str) -> list[str]:
    return list(
        dict.fromkeys(
            re.findall(
                r"<([A-Za-z][\w-]*)>[\s\S]*?</\1>",
                prompt,
            )
        )
    )


def _find_named_values(value: object, name: str) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key == name and isinstance(item, str) and item:
                found.add(item)
            elif key == f"{name}s" and isinstance(item, list):
                found.update(entry for entry in item if isinstance(entry, str))
            found.update(_find_named_values(item, name))
    elif isinstance(value, list):
        for item in value:
            found.update(_find_named_values(item, name))
    return found


def _phase_surfaces(phases: Iterable[str]) -> str:
    surfaces = {
        "post_prompt": "model input",
        "post_model": "model output",
        "post_parse": "parsed action",
        "pre_tool": "tool call/context",
        "post_tool": "tool result/context",
        "pre_final": "final decision/context",
    }
    values = [surfaces.get(phase, "unavailable") for phase in phases]
    return ", ".join(dict.fromkeys(values)) if values else "unavailable"


def _declared_purpose(config: object) -> str:
    if not isinstance(config, dict):
        return "unavailable"
    for key in ("purpose", "goal", "description"):
        value = config.get(key)
        if isinstance(value, str) and value.strip():
            return _preview(value)
    return "unavailable"


def _observed_invalid_feedback(record: dict[str, Any]) -> str | None:
    run = record.get("run")
    run = run if isinstance(run, dict) else {}
    values = []
    for event in run.get("trace", []):
        if not isinstance(event, dict):
            continue
        if event.get("event_type") != "invalid_output_feedback":
            continue
        payload = event.get("payload")
        values.append(_preview(_content_text(payload)))
    return " | ".join(values) if values else None


def load_json_object(path: Path) -> dict[str, Any]:
    """Read one UTF-8 JSON object for experiment scripts."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def render_evidence_reviewer_input(
    value: dict[str, Any],
    resource_context: dict[str, Any],
) -> str:
    """Render complete Evidence Reviewer facts in a dense mixed format."""

    hypothesis = value.get("hypothesis")
    hypothesis = hypothesis if isinstance(hypothesis, dict) else {}
    phases = hypothesis.get("phase_plan")
    phases = phases if isinstance(phases, list) else []
    phase_rows = tuple(
        (
            _value(item.get("phase")),
            _value(item.get("activation_condition")),
            _value(item.get("instruction")),
            _value(item.get("expected_effect")),
            _value(item.get("max_activations")),
        )
        for item in phases
        if isinstance(item, dict)
    )
    reviews = value.get("trial_reviews")
    reviews = reviews if isinstance(reviews, list) else []
    review_rows = tuple(
        (
            _value(item.get("trial_ref")),
            _value(item.get("predicate_observations")),
            _value(item.get("assessment")),
        )
        for item in reviews
        if isinstance(item, dict)
    )
    coverage = value.get("coverage_summary")
    coverage = coverage if isinstance(coverage, dict) else {}
    phase_coverage = coverage.get("phase_coverage")
    phase_coverage = phase_coverage if isinstance(phase_coverage, list) else []
    coverage_rows = tuple(
        (
            _value(item.get("phase")),
            _value(item.get("positive_count")),
            _value(item.get("negative_count")),
            _value(item.get("uncertain_count")),
            _value(item.get("positive_distinct_examples")),
            _value(item.get("negative_distinct_examples")),
            _value(item.get("intervention_applied_count")),
            _value(item.get("correct_non_intervention_count")),
        )
        for item in phase_coverage
        if isinstance(item, dict)
    )
    budget = value.get("budget")
    budget = budget if isinstance(budget, dict) else {}
    aggregate = value.get("aggregate_observations")
    aggregate = aggregate if isinstance(aggregate, dict) else {}
    aggregate_items = aggregate.get("items")
    aggregate_items = aggregate_items if isinstance(aggregate_items, list) else []
    aggregate_rows = tuple(
        (
            _value(item.get("trial_ref")),
            _value(item.get("example_id")),
            _value(item.get("source_status")),
            _value(item.get("branch_status")),
            _value(item.get("source_score")),
            _value(item.get("branch_score")),
            _value(item.get("source_full_tool_calls")),
            _value(item.get("branch_continuation_tool_calls")),
            _value(item.get("activated_phases")),
            _value(item.get("modified_phases")),
            _value(item.get("concrete_intervention_count")),
        )
        for item in aggregate_items
        if isinstance(item, dict)
    )
    return "\n\n".join(
        (
            "# Evidence Review Input",
            "## Frozen hypothesis phases\n"
            + _table(
                ("phase", "condition", "instruction", "expected effect", "max"),
                phase_rows,
            ),
            "## Hypothesis evaluation and boundary\n"
            + _jsonl(
                [
                    {
                        "evaluation": hypothesis.get("evaluation"),
                        "applicability": hypothesis.get("applicability"),
                        "special_evidence_obligations": hypothesis.get(
                            "special_evidence_obligations"
                        ),
                    }
                ]
            ),
            "## Independent Trial Reviews\n"
            + _table(("trial_ref", "predicate observations", "assessment"), review_rows),
            "## Coverage by phase\n"
            + _table(
                (
                    "phase",
                    "positive",
                    "negative",
                    "uncertain",
                    "positive examples",
                    "negative examples",
                    "applied",
                    "correct no-op",
                ),
                coverage_rows,
            ),
            "## Coverage requirements\n"
            + _jsonl(
                [
                    {
                        key: coverage.get(key)
                        for key in (
                            "required_distinct_examples",
                            "required_positive_per_phase",
                            "required_negative_per_phase",
                            "observed_distinct_examples",
                            "unmet_requirements",
                            "special_obligations",
                            "default_requirements_met",
                        )
                    }
                ]
            ),
            "## Budget\n"
            + _table(
                ("field", "value"),
                tuple((key, _value(item)) for key, item in budget.items()),
            ),
            "## Aggregate totals\n"
            + _jsonl(
                [
                    {
                        key: item
                        for key, item in aggregate.items()
                        if key != "items" and "model_calls" not in key
                    }
                ]
            ),
            "## Per-Trial deterministic facts\n"
            + _table(
                (
                    "trial_ref",
                    "example_id",
                    "source status",
                    "branch status",
                    "source score",
                    "branch score",
                    "source tools",
                    "branch tools",
                    "activated",
                    "modified",
                    "interventions",
                ),
                aggregate_rows,
            ),
            "## Prior obligation\n" + _value(value.get("prior_obligation")),
            "## Resource summary\n" + _jsonl([resource_context]),
            (
                "Treat Trial Reviews as evidence, deterministic aggregates as "
                "authoritative, and submit one aggregate structured review."
            ),
        )
    )


def render_mechanism_distiller_input(
    value: dict[str, Any],
    trial_payloads: dict[str, dict[str, Any]],
    resource_context: dict[str, Any],
) -> str:
    """Render all evidence needed for distillation as one coherent dossier."""

    reviews = value.get("trial_reviews")
    reviews = reviews if isinstance(reviews, list) else []
    review_by_ref = {
        str(review.get("trial_ref")): review
        for review in reviews
        if isinstance(review, dict) and review.get("trial_ref")
    }
    evidence_refs = value.get("evidence_refs")
    evidence_refs = evidence_refs if isinstance(evidence_refs, list) else []
    dossier_items = []
    directory_rows = []
    for trial_ref in evidence_refs:
        if not isinstance(trial_ref, str):
            continue
        payload = trial_payloads.get(trial_ref)
        payload = payload if isinstance(payload, dict) else {}
        review = review_by_ref.get(trial_ref, {})
        item = _distillation_trial_item(trial_ref, review, payload)
        dossier_items.append(item)
        directory_rows.append(_distillation_trial_row(item))
    unknown_reviews = sorted(set(review_by_ref) - set(evidence_refs))
    missing_trials = sorted(set(evidence_refs) - set(trial_payloads))
    if unknown_reviews or missing_trials:
        raise ValueError(
            "Distiller dossier references must match attached trials: "
            f"unknown_reviews={unknown_reviews}, missing_trials={missing_trials}"
        )
    mechanism_context = resource_context.get("mechanism_drafts")
    return "\n\n".join(
        (
            "# Distillation Evidence Dossier",
            (
                "This dossier is the complete default evidence view. It preserves "
                "the frozen research result, every independent Trial Review, the "
                "actual Student-visible intervention, deterministic execution facts, "
                "and measured outcomes. Use `get_distillation_trial_detail` only "
                "when a concrete conflict or ambiguity cannot be resolved here."
            ),
            "## Frozen hypothesis\n" + _jsonl([value.get("hypothesis")]),
            "## Authoritative Evidence Review\n" + _jsonl([value.get("review")]),
            "## Coverage and remaining budget\n"
            + _jsonl(
                [
                    {
                        "coverage_summary": value.get("coverage_summary"),
                        "budget": value.get("budget"),
                    }
                ]
            ),
            "## Attached evidence directory\n"
            + _table(
                (
                    "trial_ref",
                    "example",
                    "phase judgment",
                    "activation",
                    "modification",
                    "next decision",
                    "score change",
                ),
                tuple(directory_rows),
            ),
            (
                "## Complete per-Trial distillation evidence\n"
                "Each JSONL record contains the exact independent Review, exact "
                "Student-visible mutation content, deterministic phase effects, and "
                "measured outcome."
            )
            + "\n"
            + _jsonl(dossier_items),
            "## Capability constraints\n"
            + _jsonl([value.get("capability_constraints")]),
            "## Draft workspace\n" + _jsonl([mechanism_context]),
            (
                "Distill the smallest supported no-Teacher control path. Do not "
                "re-adjudicate settled evidence or read Trial details by default. "
                "Use the mechanism draft tools, run bounded Student model "
                "experiments only where they resolve a material authoring "
                "uncertainty, validate the exact draft, and then submit one "
                "structured result."
            ),
        )
    )


def render_distillation_trial_detail(value: dict[str, Any]) -> str:
    """Render a focused event catalog for exceptional Distiller verification."""

    source = value.get("source")
    source = source if isinstance(source, dict) else {}
    source_run = source.get("run")
    source_run = source_run if isinstance(source_run, dict) else {}
    branch_run = value.get("branch_run")
    branch_run = branch_run if isinstance(branch_run, dict) else {}
    return "\n\n".join(
        (
            "# Distillation Trial Detail",
            _table(
                ("field", "value"),
                (
                    ("trial_ref", _value(value.get("trial_ref"))),
                    (
                        "source selector",
                        _value(source.get("selector")),
                    ),
                    ("source status", _value(source_run.get("status"))),
                    ("branch status", _value(branch_run.get("status"))),
                ),
            ),
            "## Exact intervention changes\n"
            + _jsonl(value.get("context_changes") or []),
            "## Deterministic phase effects\n"
            + _jsonl(value.get("phase_effects") or []),
            "## Source event catalog\n"
            + _jsonl(source_run.get("events") or []),
            "## Worker event catalog\n"
            + _jsonl(value.get("worker_events") or []),
            "## Branch event catalog\n"
            + _jsonl(branch_run.get("events") or []),
            "## Outcome comparison\n" + _jsonl([value.get("comparison")]),
        )
    )


def _distillation_trial_item(
    trial_ref: str,
    review: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    source = payload.get("source")
    source = source if isinstance(source, dict) else {}
    source_run = source.get("source_run")
    source_run = source_run if isinstance(source_run, dict) else {}
    return {
        "trial_ref": trial_ref,
        "source": {
            "example_id": source.get("example_id"),
            "replicate_id": source.get("replicate_id"),
            "fork_step": source.get("fork_step"),
            "fork_phase": source.get("fork_phase"),
            "question": source_run.get("question"),
        },
        "independent_review": review,
        "worker_result": payload.get("worker_result"),
        "actual_intervention": _distillation_interventions(
            payload.get("context_changes")
        ),
        "activation_budgets": payload.get("activation_budgets"),
        "activation_counts": payload.get("activation_counts"),
        "deterministic_phase_effects": payload.get("phase_effects"),
        "outcome": _distillation_outcome(payload.get("comparison")),
    }


def _distillation_interventions(changes: object) -> list[dict[str, Any]]:
    if not isinstance(changes, list):
        return []
    projected = []
    for change in changes:
        if not isinstance(change, dict):
            continue
        action = change.get("action")
        action = action if isinstance(action, dict) else {}
        projected.append(
            {
                "scope": change.get("scope"),
                "phase": change.get("phase"),
                "action_kind": action.get("kind"),
                "payload": action.get("payload"),
                "reason": action.get("reason"),
            }
        )
    return projected


def _distillation_outcome(comparison: object) -> dict[str, Any] | None:
    if not isinstance(comparison, dict):
        return None
    return {
        "source": _distillation_run_outcome(comparison.get("source")),
        "branch": _distillation_run_outcome(comparison.get("branch")),
        "exact_match_delta": comparison.get("exact_match_delta"),
    }


def _distillation_run_outcome(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    execution = value.get("execution")
    execution = execution if isinstance(execution, dict) else {}
    static = value.get("static")
    static = static if isinstance(static, dict) else {}
    return {
        "status": value.get("status"),
        "score": value.get("score"),
        "score_source": value.get("score_source"),
        "static_decision": static.get("decision"),
        "exact_match": (static.get("metrics") or {}).get("exact_match")
        if isinstance(static.get("metrics"), dict)
        else None,
        "steps": execution.get("steps"),
        "tool_calls": execution.get("tool_calls"),
    }


def _distillation_trial_row(item: dict[str, Any]) -> tuple[str, ...]:
    review = item.get("independent_review")
    review = review if isinstance(review, dict) else {}
    observations = review.get("predicate_observations")
    observations = observations if isinstance(observations, list) else []
    judgment = ", ".join(
        f"{entry.get('phase')}:{entry.get('predicate_label')}/"
        f"{entry.get('phase_execution')}"
        for entry in observations
        if isinstance(entry, dict)
    )
    source = item.get("source")
    source = source if isinstance(source, dict) else {}
    worker = item.get("worker_result")
    worker = worker if isinstance(worker, dict) else {}
    effects = item.get("deterministic_phase_effects")
    effects = effects if isinstance(effects, list) else []
    next_decisions = [
        effect.get("next_model_decision")
        for effect in effects
        if isinstance(effect, dict) and effect.get("next_model_decision") is not None
    ]
    outcome = item.get("outcome")
    outcome = outcome if isinstance(outcome, dict) else {}
    source_outcome = outcome.get("source")
    source_outcome = source_outcome if isinstance(source_outcome, dict) else {}
    branch_outcome = outcome.get("branch")
    branch_outcome = branch_outcome if isinstance(branch_outcome, dict) else {}
    return (
        _value(item.get("trial_ref")),
        _value(source.get("example_id")),
        judgment or "unavailable",
        _value(worker.get("activated_phases")),
        _value(worker.get("modified_phases")),
        _value(next_decisions),
        f"{_value(source_outcome.get('score'))} -> "
        f"{_value(branch_outcome.get('score'))}",
    )


def _table(headers: tuple[str, ...], rows: tuple[tuple[str, ...], ...]) -> str:
    if not rows:
        rows = (tuple("none" for _ in headers),)
    header = "| " + " | ".join(_cell(item) for item in headers) + " |"
    divider = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(_cell(item) for item in row) + " |" for row in rows]
    return "\n".join((header, divider, *body))


def _jsonl(items: Iterable[object]) -> str:
    values = list(items)
    if not values:
        return "none"
    rendered = "\n".join(
        json.dumps(item, ensure_ascii=False, separators=(",", ":"))
        for item in values
    )
    return f"```jsonl\n{rendered}\n```"


def _exact_block(label: str, content: str) -> str:
    return f"<{label}>\n{content}\n</{label.split()[0]}>"


def _preview(value: str, limit: int = _PREVIEW_LIMIT) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _value(value: object) -> str:
    if value is None:
        return "none"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def _cell(value: object) -> str:
    return _value(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")
