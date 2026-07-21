"""Render tool declarations for the tagged-text actor baseline."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from search_harness.framework.tooling import ToolDefinition, ToolParameter


def render_tagged_tool_section(tools: Iterable[ToolDefinition]) -> str:
    """Render the enabled tools without coupling the template to their fields."""

    definitions = tuple(tools)
    if not definitions:
        return "No tools are available for this rollout."

    blocks = ["Available tools:"]
    for definition in definitions:
        blocks.append(f"- `{definition.name}`: {definition.description}")
        if not definition.parameters:
            blocks.append("  Arguments: none.")
            continue
        blocks.append("  Arguments:")
        for parameter in definition.parameters:
            blocks.append(f"  - {_render_parameter(parameter)}")
    return "\n".join(blocks)


def _render_parameter(parameter: ToolParameter) -> str:
    schema = parameter.to_json_schema()
    constraints = _render_constraints(schema, parameter.required)
    return f"`{parameter.name}` ({', '.join(constraints)}): {parameter.description}"


def _render_constraints(schema: dict[str, Any], required: bool) -> list[str]:
    constraints = [str(schema["type"]), "required" if required else "optional"]
    if "default" in schema:
        constraints.append(f"default={schema['default']!r}")
    if "minimum" in schema:
        constraints.append(f"minimum={schema['minimum']}")
    if "maximum" in schema:
        constraints.append(f"maximum={schema['maximum']}")
    if "enum" in schema:
        constraints.append(f"choices={schema['enum']!r}")
    return constraints
