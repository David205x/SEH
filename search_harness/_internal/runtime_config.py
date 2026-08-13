"""UTF-8 JSON runtime configuration shared by local adapters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


DEFAULT_RUNTIME_CONFIG = Path("config/runtime.yaml")


@dataclass(frozen=True)
class TeacherRoleBudget:
    """Generation, loop, and reasoning settings for one Teacher Role."""

    max_tokens: int
    max_turns: int
    thinking_mode: str | None = None

    def __post_init__(self) -> None:
        if self.max_tokens < 1:
            raise ValueError("Teacher Role max_tokens must be positive")
        if self.max_turns < 1:
            raise ValueError("Teacher Role max_turns must be positive")
        if self.thinking_mode not in {None, "enabled", "disabled"}:
            raise ValueError(
                "Teacher Role thinking_mode must be enabled, disabled, or None"
            )


_EVOLUTION_CONTROL_FIELDS = frozenset(
    {
        "max_generations",
        "max_trials_per_hypothesis",
        "trial_batch_size",
        "max_trial_assignments",
        "max_hypothesis_revisions",
        "max_mechanism_revisions",
        "max_compiler_revisions",
        "max_candidate_revisions",
        "max_work_retries",
        "max_work_items",
        "max_total_tokens",
        "min_accuracy_delta",
        "max_total_token_ratio",
    }
)

_EVOLUTION_EFFECT_FIELDS = frozenset(
    {
        "student_max_steps",
        "teacher_max_turns",
        "rollout_workers",
        "rollouts_per_example",
        "judge_workers",
        "candidate_error_streak_limit",
    }
)


def resolve_runtime_config(
    *,
    env_file: Path | None = None,
    config_file: Path | None = None,
) -> Path | None:
    """Resolve an explicit config or the config beside the active .env file."""

    if config_file is not None:
        return config_file
    base_dir = (
        env_file.resolve().parent
        if env_file is not None
        else Path.cwd()
    )
    candidate = base_dir / DEFAULT_RUNTIME_CONFIG
    return candidate if candidate.exists() else None


def read_runtime_config(
    *,
    env_file: Path | None = None,
    config_file: Path | None = None,
) -> dict[str, Any]:
    """Read and minimally validate one UTF-8 YAML runtime configuration."""

    path = resolve_runtime_config(env_file=env_file, config_file=config_file)
    if path is None:
        return {}
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid runtime config YAML {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise TypeError(f"runtime config must contain an object: {path}")
    schema_version = value.get("schema_version")
    if schema_version != 1:
        raise ValueError(
            f"unsupported runtime config schema_version: {schema_version}"
        )
    return value


def legacy_runtime_values(config: dict[str, Any]) -> dict[str, str]:
    """Project structured config into legacy setting names during migration."""

    values: dict[str, str] = {}
    models = _object(config, "models")
    for profile_name, raw_profile in models.items():
        if not isinstance(raw_profile, dict):
            raise TypeError(f"models.{profile_name} must be an object")
        prefix = str(profile_name).strip().upper()
        for field, suffix in {
            "base_url": "BASE_URL",
            "model_id": "MODEL_ID",
            "max_tokens": "MAX_TOKENS",
            "request_timeout": "REQUEST_TIMEOUT",
            "temperature": "TEMPERATURE",
            "seed": "SEED",
            "thinking_mode": "THINKING_MODE",
        }.items():
            if field in raw_profile:
                values[f"{prefix}_{suffix}"] = _string_value(
                    raw_profile[field]
                )

    for section_name, mapping in {
        "agent": {
            "max_steps": "MAX_AGENT_ITERS",
        },
        "retriever": {
            "url": "RETRIEVER_URL",
            "timeout": "RETRIEVER_TIMEOUT",
            "top_k": "RETRIEVER_TOPK",
        },
        "dataset": {
            "path": "DATASET_PATH",
            "output_dir": "OUTPUT_DIR",
            "file": "DATASET_FILE",
            "format": "DATASET_FORMAT",
            "filter_status": "DATASET_FILTER_STATUS",
            "jsonl_path": "DATASET_JSONL_PATH",
            "train_path": "SELF_HARNESS_SEARCH_TRAIN",
            "heldout_path": "SELF_HARNESS_SEARCH_HELDOUT",
        },
        "evaluation": {
            "workers": "WORKERS",
            "save_batch_size": "SAVE_BATCH_SIZE",
        },
    }.items():
        section = _object(config, section_name)
        for field, legacy_name in mapping.items():
            if field in section:
                values[legacy_name] = _string_value(section[field])

    timeouts = _object(config, "timeouts")
    for name, value in timeouts.items():
        values[f"{str(name).strip().upper()}_REQUEST_TIMEOUT"] = (
            _string_value(value)
        )
    return values


def teacher_role_budget(
    config: dict[str, Any],
    role_id: str,
    *,
    default_max_tokens: int,
    default_max_turns: int,
    default_thinking_mode: str | None = None,
) -> TeacherRoleBudget:
    """Resolve one explicit role budget with validated fallback values."""

    roles = _object(config, "teacher_roles")
    raw = roles.get(role_id, {})
    if not isinstance(raw, dict):
        raise TypeError(f"teacher_roles.{role_id} must be an object")
    return TeacherRoleBudget(
        max_tokens=_positive_int(
            raw.get("max_tokens", default_max_tokens),
            f"teacher_roles.{role_id}.max_tokens",
        ),
        max_turns=_positive_int(
            raw.get("max_turns", default_max_turns),
            f"teacher_roles.{role_id}.max_turns",
        ),
        thinking_mode=_thinking_mode(
            raw.get("thinking_mode", default_thinking_mode),
            f"teacher_roles.{role_id}.thinking_mode",
        ),
    )


def teacher_judge_thinking_mode(
    config: dict[str, Any],
    *,
    default: str | None = None,
) -> str | None:
    """Resolve the dedicated Teacher Judge reasoning mode."""

    judge = _object(config, "teacher_judge")
    unknown = set(judge) - {"thinking_mode"}
    if unknown:
        raise ValueError(
            f"teacher_judge contains unknown fields: {sorted(unknown)}"
        )
    return _thinking_mode(
        judge.get("thinking_mode", default),
        "teacher_judge.thinking_mode",
    )


def evolution_control_values(config: dict[str, Any]) -> dict[str, Any]:
    """Read the complete Evolution Controller hyperparameter set."""

    evolution = _object(config, "evolution")
    values = _exact_settings(
        evolution,
        "control",
        _EVOLUTION_CONTROL_FIELDS,
    )
    max_trials = _positive_int(
        values["max_trials_per_hypothesis"],
        "evolution.control.max_trials_per_hypothesis",
    )
    max_assignments = _positive_int(
        values["max_trial_assignments"],
        "evolution.control.max_trial_assignments",
    )
    batch_size = _positive_int(
        values["trial_batch_size"],
        "evolution.control.trial_batch_size",
    )
    if batch_size > max_trials:
        raise ValueError(
            "evolution.control.trial_batch_size must not exceed "
            "max_trials_per_hypothesis"
        )
    if max_assignments < max_trials:
        raise ValueError(
            "evolution.control.max_trial_assignments must be at least "
            "max_trials_per_hypothesis"
        )
    return values


def evolution_effect_values(config: dict[str, Any]) -> dict[str, Any]:
    """Read the complete Evolution effect execution hyperparameter set."""

    evolution = _object(config, "evolution")
    return _exact_settings(
        evolution,
        "effects",
        _EVOLUTION_EFFECT_FIELDS,
    )


def _object(value: dict[str, Any], name: str) -> dict[str, Any]:
    item = value.get(name, {})
    if not isinstance(item, dict):
        raise TypeError(f"runtime config field '{name}' must be an object")
    return item


def _thinking_mode(value: object, name: str) -> str | None:
    if value is None:
        return None
    if value not in {"enabled", "disabled"}:
        raise ValueError(f"{name} must be enabled or disabled")
    return str(value)


def _exact_settings(
    value: dict[str, Any],
    name: str,
    expected_fields: frozenset[str],
) -> dict[str, Any]:
    settings = _object(value, name)
    missing = expected_fields - set(settings)
    unknown = set(settings) - expected_fields
    if missing:
        raise ValueError(
            f"runtime config evolution.{name} is missing fields: "
            f"{sorted(missing)}"
        )
    if unknown:
        raise ValueError(
            f"runtime config evolution.{name} has unknown fields: "
            f"{sorted(unknown)}"
        )
    return dict(settings)


def _string_value(value: object) -> str:
    if value is None or isinstance(value, (dict, list)):
        raise TypeError("runtime setting must be a scalar value")
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _positive_int(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value
