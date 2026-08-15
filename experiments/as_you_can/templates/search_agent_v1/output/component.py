"""Tagged output parser Component."""

from __future__ import annotations

from typing import Any

from search_harness.framework.harness import TaggedOutputParser


def build(config: dict[str, Any], context: Any) -> TaggedOutputParser:
    del context
    if config:
        raise ValueError("tagged output does not accept configuration")
    return TaggedOutputParser()
