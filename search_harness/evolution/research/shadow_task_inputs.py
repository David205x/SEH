"""Shadow Phase Task 使用的固定 source projector 与内容指纹。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any

from search_harness.framework import (
    HOOK_PROMPT_PROJECTOR_ID,
    HOOK_PROMPT_PROJECTOR_VERSION,
)
from search_harness.framework.harness import STAGE_KEYS_BY_PHASE

from .mechanism.hook_api import list_hook_api_symbols, query_hook_api


SHADOW_TASK_INPUT_PROJECTOR_VERSION = HOOK_PROMPT_PROJECTOR_VERSION
SHADOW_TASK_INPUT_PROJECTOR_ID = HOOK_PROMPT_PROJECTOR_ID


def shadow_phase_task_digest(*, phase: str, task: Mapping[str, Any]) -> str:
    """Bind one Prompt Product to the exact frozen Phase Task."""

    return _content_digest(
        {
            "phase": phase,
            "task": dict(task),
        }
    )


def shadow_task_source_catalog() -> dict[str, Any]:
    """Return every fixed core/stage source and its projector semantics。"""

    sources: dict[str, dict[str, Any]] = {}
    page = 1
    while True:
        result = list_hook_api_symbols(page=page, page_size=50)
        for item in result["items"]:
            if item.get("kind") != "state_key":
                continue
            symbol = str(item["symbol"])
            contract = query_hook_api(symbol)
            category = str(item.get("category"))
            sources[symbol] = {
                "value_type": contract.get("type"),
                "category": category,
                "description": contract.get("note"),
                "phases": (
                    "all"
                    if category == "core"
                    else [
                        phase
                        for phase, keys in STAGE_KEYS_BY_PHASE.items()
                        if symbol in keys
                    ]
                ),
                "projector_id": SHADOW_TASK_INPUT_PROJECTOR_ID,
            }
        if page >= int(result["total_pages"]):
            break
        page += 1
    return {
        "catalog_version": result["catalog_version"],
        "projector_version": SHADOW_TASK_INPUT_PROJECTOR_VERSION,
        "projector_id": SHADOW_TASK_INPUT_PROJECTOR_ID,
        "sources": sources,
        "declared_state_source": "state.<name>",
    }


def shadow_input_projection_digest(
    *,
    phase: str,
    inputs: Iterable[Mapping[str, Any]],
    state_types: Mapping[str, str] | None = None,
) -> str:
    """Bind one ordered Task Input projection to source contracts。"""

    catalog = shadow_task_source_catalog()
    state_types = dict(state_types or {})
    normalized_inputs = []
    for item in inputs:
        name = _required_string(item, "name")
        raw_sources = item.get("sources")
        if not isinstance(raw_sources, list) or not raw_sources:
            raise TypeError("shadow projection sources must be a non-empty list")
        sources = []
        for raw_source in raw_sources:
            if not isinstance(raw_source, str) or not raw_source:
                raise TypeError("shadow projection source must be a string")
            if raw_source.startswith("state."):
                state_name = raw_source.removeprefix("state.")
                value_type = state_types.get(state_name)
                if value_type is None:
                    raise ValueError(
                        f"shadow projection state is undeclared: {raw_source}"
                    )
                contract = {
                    "source": raw_source,
                    "value_type": value_type,
                    "category": "state",
                    "phases": "all",
                    "projector_id": SHADOW_TASK_INPUT_PROJECTOR_ID,
                }
            else:
                raw_contract = catalog["sources"].get(raw_source)
                if not isinstance(raw_contract, dict):
                    raise ValueError(
                        f"shadow projection source is unavailable: {raw_source}"
                    )
                contract = {"source": raw_source, **raw_contract}
                phases = contract.get("phases")
                if phases != "all" and phase not in phases:
                    raise ValueError(
                        f"shadow projection source {raw_source} is unavailable "
                        f"at {phase}"
                    )
            sources.append(contract)
        normalized_inputs.append({"name": name, "sources": sources})
    payload = {
        "projector_version": SHADOW_TASK_INPUT_PROJECTOR_VERSION,
        "projector_id": SHADOW_TASK_INPUT_PROJECTOR_ID,
        "phase": phase,
        "inputs": normalized_inputs,
    }
    return _content_digest(payload)


def project_shadow_task_inputs(
    *,
    phase: str,
    inputs: Iterable[Mapping[str, Any]],
    get_state: Callable[[str], Any],
    state_types: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Project exact runtime values into the Prompt/Hook shared JSON view。"""

    input_list = [dict(item) for item in inputs]
    digest = shadow_input_projection_digest(
        phase=phase,
        inputs=input_list,
        state_types=state_types,
    )
    projected = []
    for item in input_list:
        projected.append(
            {
                "name": _required_string(item, "name"),
                "sources": [
                    {
                        "source": source,
                        "value": _json_value(get_state(source)),
                    }
                    for source in item["sources"]
                ],
            }
        )
    return {
        "projector_id": SHADOW_TASK_INPUT_PROJECTOR_ID,
        "projection_digest": digest,
        "phase": phase,
        "inputs": projected,
    }


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Enum):
        return _json_value(value.value)
    if is_dataclass(value):
        return _json_value(asdict(value))
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return _json_value(to_dict())
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    raise TypeError(
        "shadow task input projector cannot serialize "
        f"{type(value).__name__}"
    )


def _required_string(value: Mapping[str, Any], name: str) -> str:
    item = value.get(name)
    if not isinstance(item, str) or not item:
        raise TypeError(f"shadow projection {name} must be a string")
    return item


def _content_digest(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
