"""Small UTF-8 .env reader used by runtime adapters."""

from __future__ import annotations

import os
from pathlib import Path

from .runtime_config import legacy_runtime_values, read_runtime_config


EnvValues = dict[str, str]


def read_env_file(env_file: Path | None = None) -> EnvValues:
    """Read runtime config defaults and secret/override .env values."""

    path = env_file if env_file is not None else Path.cwd() / ".env"
    values = legacy_runtime_values(read_runtime_config(env_file=path))
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        values[key] = value.strip().strip("'\"")
    return values


def get_env_value(values: EnvValues, name: str) -> str | None:
    """Return process environment override or value loaded from .env."""

    return os.environ.get(name) or values.get(name)


def parse_float(value: str | None, default: float, name: str) -> float:
    """Parse a positive float setting."""

    if value is None:
        return default
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a float") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be positive")
    return parsed


def parse_int(value: str | None, default: int, name: str) -> int:
    """Parse a positive integer setting."""

    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if parsed < 1:
        raise ValueError(f"{name} must be positive")
    return parsed
