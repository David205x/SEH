"""Direction Summarizer terminal output adapter."""

from __future__ import annotations

from typing import Any

from search_harness.evolution.research.roles.spec import TeacherOutputSpec


def build(config: dict[str, Any], context: Any) -> TeacherOutputSpec:
    del context
    if config:
        raise ValueError("role_contract output does not accept configuration")
    return TeacherOutputSpec()
