"""Teacher prompt plugin 的共享加载辅助。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .spec import TeacherPromptSpec


def load_prompt_spec(plugin_dir: Path, config: dict[str, Any]) -> TeacherPromptSpec:
    """从插件目录内的 UTF-8 文件构造 PromptSpec。"""

    allowed = {"instructions", "user_template"}
    unknown = set(config) - allowed
    if unknown:
        raise ValueError(f"Teacher prompt has unsupported config: {sorted(unknown)}")
    instructions_path = _resolve_local(
        plugin_dir,
        _require_path(config, "instructions"),
    )
    user_template_path = _resolve_local(
        plugin_dir,
        _require_path(config, "user_template"),
    )
    return TeacherPromptSpec(
        instructions=instructions_path.read_text(encoding="utf-8").strip(),
        user_template=user_template_path.read_text(encoding="utf-8").strip(),
    )


def _require_path(config: dict[str, Any], field: str) -> str:
    value = config.get(field)
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"Teacher prompt config '{field}' must be a non-empty string")
    return value


def _resolve_local(root: Path, relative_path: str) -> Path:
    base = root.resolve()
    path = (base / relative_path).resolve()
    if path != base and base not in path.parents:
        raise ValueError(f"Teacher prompt path escapes plugin directory: {relative_path}")
    if not path.is_file():
        raise FileNotFoundError(f"Teacher prompt file does not exist: {path}")
    return path

