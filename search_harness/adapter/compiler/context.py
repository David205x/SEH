"""Read-only Compiler view of validated Intervention evidence and a parent Harness."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any

from search_harness.adapter.critic.types import validate_problem_direction
from search_harness.versioning import HarnessSnapshot, normalize_plugin_path

from .hook_authoring import get_hook_authoring_guide


@dataclass(frozen=True)
class CompilerContext:
    """Compiler-visible evidence and immutable parent Harness snapshot."""

    intervention_log: Path
    critic_log: Path
    direction_index: int
    critic_analysis: str
    problem_direction: Mapping[str, Any]
    coordinator_analysis: str
    coordinator_recommendation: str
    selected_trial: Mapping[str, Any]
    validation_trials: tuple[Mapping[str, Any], ...]
    critic_harness_version: str
    parent: HarnessSnapshot
    harness_manifest: Mapping[str, Any]

    @classmethod
    def from_intervention_log(
        cls,
        *,
        intervention_log: Path,
        parent: HarnessSnapshot,
    ) -> "CompilerContext":
        """Load one supported Coordinator strategy from a UTF-8 artifact."""

        path = intervention_log.resolve()
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise TypeError("Coordinator artifact must contain a JSON object")
        direction_source = raw.get("direction_source")
        if not isinstance(direction_source, Mapping):
            raise ValueError("Coordinator artifact has no direction_source")
        critic_harness_version = _validated_critic_parent(direction_source, parent)
        critic_log = direction_source.get("critic_log")
        direction_index = direction_source.get("direction_index")
        critic_analysis = direction_source.get("critic_analysis")
        if not isinstance(critic_log, str) or not critic_log.strip():
            raise ValueError("Coordinator direction is not bound to a Critic log")
        if not isinstance(direction_index, int) or direction_index < 0:
            raise ValueError("Coordinator direction_index must be non-negative")
        if not isinstance(critic_analysis, str) or not critic_analysis.strip():
            raise ValueError("Coordinator artifact has no Critic analysis")
        direction = _validated_direction(
            direction_source.get("problem_direction"), direction_index
        )
        result = raw.get("coordinator_result")
        if not isinstance(result, Mapping):
            raise ValueError("Coordinator artifact has no completed result")
        if result.get("verdict") != "supported":
            raise ValueError("Compiler requires a supported Coordinator verdict")
        coordinator_analysis = result.get("analysis")
        recommendation = result.get("recommendation")
        selected_trial_id = result.get("selected_trial_id")
        if not isinstance(coordinator_analysis, str) or not coordinator_analysis.strip():
            raise ValueError("Coordinator result has no analysis")
        if not isinstance(recommendation, str) or not recommendation.strip():
            raise ValueError("Coordinator result has no recommendation")
        if not isinstance(selected_trial_id, str) or not selected_trial_id.strip():
            raise ValueError("supported Coordinator result has no selected trial")
        trials = raw.get("trials")
        if not isinstance(trials, list) or not all(isinstance(item, dict) for item in trials):
            raise ValueError("Coordinator artifact trials must be an array of objects")
        selected_trial = next(
            (item for item in trials if item.get("trial_id") == selected_trial_id),
            None,
        )
        if selected_trial is None or selected_trial.get("status") != "completed":
            raise ValueError("Coordinator selected trial is missing or incomplete")
        manifest = json.loads(parent.read_text("harness.json"))
        if not isinstance(manifest, dict):
            raise TypeError("parent Harness manifest must contain a JSON object")
        return cls(
            intervention_log=path,
            critic_log=Path(critic_log).resolve(),
            direction_index=direction_index,
            critic_analysis=critic_analysis.strip(),
            problem_direction=direction,
            coordinator_analysis=coordinator_analysis.strip(),
            coordinator_recommendation=recommendation.strip(),
            selected_trial=MappingProxyType(dict(selected_trial)),
            validation_trials=tuple(MappingProxyType(dict(item)) for item in trials),
            critic_harness_version=critic_harness_version,
            parent=parent,
            harness_manifest=MappingProxyType(manifest),
        )

    def initial_context(self) -> dict[str, Any]:
        """Return validated strategy evidence and compact parent Harness metadata."""

        return {
            "parent_version": self.parent.version_id,
            "parent_digest": self.parent.digest,
            "critic_harness_version": self.critic_harness_version,
            "critic_analysis": self.critic_analysis,
            "direction_index": self.direction_index,
            "problem_direction": dict(self.problem_direction),
            "coordinator_analysis": self.coordinator_analysis,
            "coordinator_recommendation": self.coordinator_recommendation,
            "selected_trial": dict(self.selected_trial),
            "validation_trials": [dict(trial) for trial in self.validation_trials],
            "harness_manifest": dict(self.harness_manifest),
        }

    def list_harness_files(self) -> dict[str, Any]:
        """List parent Harness files without returning their contents."""

        return {
            "parent_version": self.parent.version_id,
            "files": [
                {"path": str(path), "size_bytes": len(content)}
                for path, content in sorted(
                    self.parent.files.items(), key=lambda item: str(item[0])
                )
            ],
        }

    def read_harness_file(self, path: str) -> dict[str, Any]:
        """Read one UTF-8 parent Harness file by plugins-relative path."""

        normalized = normalize_plugin_path(path)
        try:
            content = self.parent.files[normalized].decode("utf-8")
        except KeyError as exc:
            raise KeyError(f"Harness file not found: {normalized}") from exc
        except UnicodeDecodeError as exc:
            raise ValueError(f"Harness file is not UTF-8 text: {normalized}") from exc
        return {"path": str(normalized), "content": content}

    def get_harness_component(self, component_id: str) -> dict[str, Any]:
        """Read one manifest component and every UTF-8 file in its directory."""

        category, spec = _find_component(self.harness_manifest, component_id)
        entrypoint = spec.get("entrypoint")
        if not isinstance(entrypoint, str):
            raise ValueError("Harness component entrypoint must be a string")
        component_dir = PurePosixPath(entrypoint.partition(":")[0]).parent
        files: dict[str, str] = {}
        for path, content in sorted(self.parent.files.items(), key=lambda item: str(item[0])):
            if component_dir not in path.parents:
                continue
            files[str(path)] = content.decode("utf-8")
        return {
            "category": category,
            "component_id": component_id,
            "manifest": dict(spec),
            "files": files,
        }

    def get_hook_authoring_guide(self, topic: str) -> dict[str, Any]:
        """Return one versioned slice of the Hook extension API."""

        return get_hook_authoring_guide(topic)


def _find_component(
    manifest: Mapping[str, Any], component_id: str
) -> tuple[str, Mapping[str, Any]]:
    for category in ("tools", "extensions"):
        raw = manifest.get(category, [])
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict) and item.get("instance_id") == component_id:
                    return category, item
    prompt = manifest.get("prompt")
    if isinstance(prompt, dict) and prompt.get("instance_id") == component_id:
        return "prompts", prompt
    raise KeyError(f"Harness component not found: {component_id}")


def _validated_direction(value: object, index: int) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"Critic problem direction {index} must be an object")
    return MappingProxyType(validate_problem_direction(value, index=index))


def _validated_critic_parent(
    direction_source: Mapping[str, Any], parent: HarnessSnapshot
) -> str:
    """Require Intervention evidence to derive from this accepted parent snapshot."""

    inputs = direction_source.get("critic_inputs")
    if not isinstance(inputs, Mapping):
        raise ValueError("Coordinator artifact has no Critic provenance inputs")
    harness_version = inputs.get("harness_version")
    harness_digest = inputs.get("harness_digest")
    if not isinstance(harness_version, str) or not harness_version.strip():
        raise ValueError("Critic log inputs have no harness_version")
    if not isinstance(harness_digest, str) or not harness_digest.strip():
        raise ValueError("Critic log inputs have no harness_digest")
    if inputs.get("iteration") is not None:
        raise ValueError(
            "Critic log reviews a pending iteration and cannot compile against an "
            "accepted parent"
        )
    if harness_version != parent.version_id:
        raise ValueError(
            "Intervention parent mismatch: "
            f"log={harness_version}, compiler={parent.version_id}"
        )
    if harness_digest != parent.digest:
        raise ValueError(
            "Intervention parent digest mismatch: "
            f"log={harness_digest}, compiler={parent.digest}"
        )
    return harness_version
