"""Student tagged Output Component。"""

from __future__ import annotations

from typing import Any

from search_harness.framework.harness import TaggedOutputParser


def build(config: dict[str, Any], context: Any) -> TaggedOutputParser:
    """构造与迁移前行为相同的 tagged output parser。"""

    del context
    if config:
        raise ValueError("tagged_output does not accept configuration")
    return TaggedOutputParser()
