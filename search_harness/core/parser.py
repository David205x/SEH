"""Simple tagged-output parser for the first research loop."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .types import ParsedOutput, ToolCall


@dataclass(frozen=True)
class _ActionBlock:
    """One top-level tagged action located in raw model output."""

    kind: str
    start: int
    end: int
    content: str


class TaggedOutputParser:
    """Parse model output with explicit tool and final-answer tags."""

    _open_pattern = re.compile(r"<(tool_call|final_answer)>")

    def parse(self, raw_output: str) -> ParsedOutput:
        action_blocks = self._find_action_blocks(raw_output)
        tool_blocks = [block for block in action_blocks if block.kind == "tool_call"]
        final_blocks = [block for block in action_blocks if block.kind == "final_answer"]
        inband_thinking = self._content_outside_actions(raw_output, action_blocks)

        if tool_blocks and final_blocks:
            return ParsedOutput.invalid(
                "output contains both tool_call and final_answer",
                inband_thinking=inband_thinking,
            )
        if len(tool_blocks) > 1:
            return ParsedOutput.invalid(
                "output contains multiple tool_call blocks",
                inband_thinking=inband_thinking,
            )
        if len(final_blocks) > 1:
            return ParsedOutput.invalid(
                "output contains multiple final_answer blocks",
                inband_thinking=inband_thinking,
            )
        if tool_blocks:
            return self._parse_tool_call(
                tool_blocks[0].content,
                inband_thinking=inband_thinking,
            )
        if final_blocks:
            answer = final_blocks[0].content.strip()
            if not answer:
                return ParsedOutput.invalid(
                    "final_answer block is empty",
                    inband_thinking=inband_thinking,
                )
            return ParsedOutput.for_final_answer(
                answer,
                inband_thinking=inband_thinking,
            )
        return ParsedOutput.invalid(
            "output contains no recognized action block",
            inband_thinking=inband_thinking,
        )

    def _find_action_blocks(self, raw_output: str) -> list[_ActionBlock]:
        """Find top-level actions while allowing tagged text inside tool JSON strings."""

        blocks: list[_ActionBlock] = []
        cursor = 0
        while opening := self._open_pattern.search(raw_output, cursor):
            kind = opening.group(1)
            content_start = opening.end()
            closing_tag = f"</{kind}>"
            closing_start = self._find_closing_boundary(
                raw_output,
                content_start=content_start,
                closing_tag=closing_tag,
                require_json=kind == "tool_call",
            )
            if closing_start is None:
                cursor = opening.end()
                continue
            end = closing_start + len(closing_tag)
            blocks.append(
                _ActionBlock(
                    kind=kind,
                    start=opening.start(),
                    end=end,
                    content=raw_output[content_start:closing_start],
                )
            )
            cursor = end
        return blocks

    @staticmethod
    def _find_closing_boundary(
        raw_output: str,
        *,
        content_start: int,
        closing_tag: str,
        require_json: bool,
    ) -> int | None:
        first_closing: int | None = None
        search_from = content_start
        while (closing := raw_output.find(closing_tag, search_from)) >= 0:
            if first_closing is None:
                first_closing = closing
            if not require_json:
                return closing
            try:
                json.loads(raw_output[content_start:closing].strip())
            except json.JSONDecodeError:
                search_from = closing + len(closing_tag)
                continue
            return closing
        return first_closing

    def _parse_tool_call(
        self,
        content: str,
        inband_thinking: str | None,
    ) -> ParsedOutput:
        try:
            payload = json.loads(content.strip())
        except json.JSONDecodeError as exc:
            return ParsedOutput.invalid(
                f"tool_call block is not valid JSON: {exc.msg}",
                inband_thinking=inband_thinking,
            )

        if not isinstance(payload, dict):
            return ParsedOutput.invalid(
                "tool_call JSON must be an object",
                inband_thinking=inband_thinking,
            )

        name = payload.get("name")
        arguments = payload.get("arguments", {})
        validation_error = self._validate_tool_payload(name, arguments)
        if validation_error:
            return ParsedOutput.invalid(
                validation_error,
                inband_thinking=inband_thinking,
            )

        return ParsedOutput.for_tool_call(
            ToolCall(name=str(name), arguments=dict(arguments)),
            inband_thinking=inband_thinking,
        )

    @staticmethod
    def _validate_tool_payload(name: Any, arguments: Any) -> str | None:
        if not isinstance(name, str) or not name.strip():
            return "tool_call.name must be a non-empty string"
        if not isinstance(arguments, dict):
            return "tool_call.arguments must be an object"
        return None

    @staticmethod
    def _content_outside_actions(
        raw_output: str,
        action_blocks: list[_ActionBlock],
    ) -> str | None:
        cursor = 0
        fragments: list[str] = []
        for block in action_blocks:
            fragments.append(raw_output[cursor : block.start])
            cursor = block.end
        fragments.append(raw_output[cursor:])
        inband_thinking = "".join(fragments).strip()
        return inband_thinking or None
