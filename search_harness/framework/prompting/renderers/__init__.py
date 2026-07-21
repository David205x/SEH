"""Prompt renderers independent from concrete prompt plugins."""

from .tagged_tools import render_tagged_tool_section

__all__ = ["render_tagged_tool_section"]
