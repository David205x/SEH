"""Shadow Intervention Worker query views used only by A/B experiments."""

from __future__ import annotations

from typing import Annotated, Any

from search_harness.evolution.research.intervention.worker import (
    InterventionWorker,
    _ActivationTools,
)
from search_harness.framework import ToolResult
from search_harness.framework.tools import (
    CallableTool,
    ToolArg,
    ToolSet,
    tool,
)


class ShadowInterventionWorker(InterventionWorker):
    """Keep formal Worker semantics while replacing read-only query views."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            **kwargs,
            activation_tool_set_factory=_shadow_activation_tools,
        )


def _shadow_activation_tools(activation: object) -> ToolSet:
    formal = _ActivationTools(activation)  # type: ignore[arg-type]
    replacement = _ShadowContextTools(activation)
    query_tools = {
        "inspect_editable_context": replacement.inspect_editable_context,
        "inspect_context_block": replacement.inspect_context_block,
    }
    tools = []
    for item in formal.tool_set.tools:
        if item.name == "inspect_active_observation":
            continue
        replacement_tool = query_tools.get(item.name)
        tools.append(replacement_tool or item)
    return ToolSet(tools)


class _ShadowContextTools:
    def __init__(self, activation: object) -> None:
        self._activation = activation
        self.inspect_editable_context = CallableTool.from_callable(
            self._inspect_editable_context
        )
        self.inspect_context_block = CallableTool.from_callable(
            self._inspect_context_block
        )

    @property
    def _snapshot(self) -> dict[str, Any]:
        snapshot = getattr(self._activation, "snapshot", None)
        if not isinstance(snapshot, dict):
            raise TypeError("shadow Intervention activation has no snapshot")
        return snapshot

    @tool(name="inspect_editable_context")
    def _inspect_editable_context(self) -> ToolResult:
        """List editable Student context blocks as a compact ordered table."""

        value = self._snapshot.get("editable_context")
        blocks = value if isinstance(value, list) else []
        lines = [
            f"Editable Student context: {len(blocks)} blocks",
            "| id | kind | role | chars | preview |",
            "|---:|---|---|---:|---|",
        ]
        for block in blocks:
            if not isinstance(block, dict):
                continue
            lines.append(
                "| {block_id} | {kind} | {role} | {characters} | {summary} |".format(
                    block_id=block.get("block_id", "unavailable"),
                    kind=_cell(block.get("kind")),
                    role=_cell(block.get("role")),
                    characters=block.get("characters", "unavailable"),
                    summary=_cell(block.get("summary")),
                )
            )
        return ToolResult(
            name="inspect_editable_context",
            content="\n".join(lines),
            metadata={"view_experiment": "teacher_query_views_v1"},
        )

    @tool(name="inspect_context_block")
    def _inspect_context_block(
        self,
        block_id: Annotated[
            int,
            ToolArg(
                "Numeric block ID from inspect_editable_context.",
                minimum=1,
            ),
        ],
    ) -> ToolResult:
        """Read one exact Student-visible block without JSON string escaping."""

        value = self._snapshot.get("_editable_context_blocks")
        blocks = value if isinstance(value, list) else []
        block = next(
            (
                item
                for item in blocks
                if isinstance(item, dict) and item.get("block_id") == block_id
            ),
            None,
        )
        if block is None:
            return ToolResult(
                name="inspect_context_block",
                content=(
                    "TOOL_INPUT_ERROR\n"
                    "code: unknown_block_id\n"
                    f"block_id: {block_id}"
                ),
                metadata={
                    "error": f"unknown block_id {block_id}",
                    "error_type": "input_validation",
                    "view_experiment": "teacher_query_views_v1",
                },
            )
        content = block.get("content")
        exact = content if isinstance(content, str) else str(content or "")
        rendered = (
            f"Block {block_id} | kind={block.get('kind', 'unavailable')} | "
            f"role={block.get('role', 'unavailable')} | characters={len(exact)}\n"
            "--- BEGIN EXACT CONTENT ---\n"
            f"{exact}\n"
            "--- END EXACT CONTENT ---"
        )
        return ToolResult(
            name="inspect_context_block",
            content=rendered,
            metadata={"view_experiment": "teacher_query_views_v1"},
        )


def _cell(value: object) -> str:
    return str(value if value is not None else "unavailable").replace(
        "|", "\\|"
    ).replace("\n", " ")
