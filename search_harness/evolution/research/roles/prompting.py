"""Teacher Prompt Component 的共享加载辅助。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .spec import TeacherPromptSpec


def load_prompt_spec(component_dir: Path, config: dict[str, Any]) -> TeacherPromptSpec:
    """从 Component 目录内的 UTF-8 文件构造 PromptSpec。"""

    allowed = {"instructions", "user_template", "continuations"}
    unknown = set(config) - allowed
    if unknown:
        raise ValueError(f"Teacher prompt has unsupported config: {sorted(unknown)}")
    instructions_path = _resolve_local(
        component_dir,
        _require_path(config, "instructions"),
    )
    user_template_path = _resolve_local(
        component_dir,
        _require_path(config, "user_template"),
    )
    continuation_templates = _load_continuation_templates(component_dir, config)
    return TeacherPromptSpec(
        instructions=instructions_path.read_text(encoding="utf-8").strip(),
        user_template=user_template_path.read_text(encoding="utf-8").strip(),
        continuation_templates=continuation_templates,
    )


def _load_continuation_templates(
    component_dir: Path,
    config: dict[str, Any],
) -> dict[str, str]:
    raw_templates = config.get("continuations", {})
    if not isinstance(raw_templates, dict):
        raise TypeError("Teacher prompt config 'continuations' must be an object")
    templates: dict[str, str] = {}
    for source, relative_path in raw_templates.items():
        if not isinstance(source, str) or not source.strip():
            raise TypeError("Teacher continuation source must be a non-empty string")
        if not isinstance(relative_path, str) or not relative_path.strip():
            raise TypeError(
                f"Teacher continuation path must be a non-empty string: {source}"
            )
        path = _resolve_local(component_dir, relative_path)
        templates[source] = path.read_text(encoding="utf-8").strip()
    return templates


def _require_path(config: dict[str, Any], field: str) -> str:
    value = config.get(field)
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"Teacher prompt config '{field}' must be a non-empty string")
    return value


def _resolve_local(root: Path, relative_path: str) -> Path:
    base = root.resolve()
    path = (base / relative_path).resolve()
    if path != base and base not in path.parents:
        raise ValueError(
            f"Teacher prompt path escapes component directory: {relative_path}"
        )
    if not path.is_file():
        raise FileNotFoundError(f"Teacher prompt file does not exist: {path}")
    return path
