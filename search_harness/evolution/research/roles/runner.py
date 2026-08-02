"""Application boundary for executing one Agent Role."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from ..resources.base import TeacherResourceConfig


class RoleRunner(Protocol):
    """Validate and execute one Role invocation and return its artifact."""

    async def run(
        self,
        *,
        template_root: Path,
        role_input: dict[str, Any],
        resource_config: TeacherResourceConfig,
        role_id: str,
        role_version: int = 1,
    ) -> dict[str, Any]:
        """Execute one bounded Role invocation."""
