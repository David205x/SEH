"""Assemble core-loop dependencies from one external plugin root."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from search_harness.core import BaseHook, HookPipeline, PromptBuilder
from search_harness.framework.tooling import DefinedTool, ToolSet
from search_harness.models import ProfiledHookModelBackend

from .manifest import HarnessManifest, load_manifest
from .plugin_importer import load_factory, plugin_import_session


@dataclass(frozen=True)
class PluginContext:
    """Stable runtime context passed to manifest-declared component factories."""

    plugins_root: Path
    env_file: Path | None = None
    runtime_context: object | None = None


@dataclass(frozen=True)
class HarnessComponents:
    """Resolved components consumed by the core AgentLoop constructor."""

    manifest: HarnessManifest
    tools: ToolSet
    prompt_builder: PromptBuilder
    hooks: HookPipeline
    extension_bindings: tuple["ResolvedExtension", ...] = ()


@dataclass(frozen=True)
class ResolvedExtension:
    """Manifest extension instance and the ordered Hooks it produced."""

    instance_id: str
    hooks: tuple[BaseHook, ...]


def build_harness(
    plugins_root: Path,
    *,
    env_file: Path | None = None,
    runtime_context: object | None = None,
    model_seed: int | None = None,
) -> HarnessComponents:
    """Resolve a plugin root into prompt, tools, and hooks outside core."""

    root = plugins_root.resolve()
    manifest = load_manifest(root)
    context = PluginContext(
        plugins_root=root,
        env_file=env_file,
        runtime_context=runtime_context,
    )
    with plugin_import_session():
        tools = ToolSet(_build_tools(root, manifest, context))
        prompt_builder = _build_prompt(root, manifest, context, tools)
        hook_instances, extension_bindings = _build_hooks(root, manifest, context)
    hook_model_backend = (
        ProfiledHookModelBackend(env_file=env_file, seed=model_seed)
        if any(hook.model_profiles for hook in hook_instances)
        else None
    )
    hooks = HookPipeline(hook_instances, model_backend=hook_model_backend)
    return HarnessComponents(
        manifest=manifest,
        tools=tools,
        prompt_builder=prompt_builder,
        hooks=hooks,
        extension_bindings=extension_bindings,
    )


def _build_tools(
    root: Path,
    manifest: HarnessManifest,
    context: PluginContext,
) -> tuple[DefinedTool, ...]:
    tools: list[DefinedTool] = []
    for spec in manifest.tools:
        if not spec.enabled:
            continue
        tool = load_factory(root, spec)(dict(spec.config), context)
        if not _is_tool(tool):
            raise TypeError(f"tool plugin '{spec.instance_id}' returned an invalid tool")
        tools.append(tool)
    return tuple(tools)


def _build_prompt(
    root: Path,
    manifest: HarnessManifest,
    context: PluginContext,
    tools: ToolSet,
) -> PromptBuilder:
    spec = manifest.prompt
    if not spec.enabled:
        raise ValueError("prompt component cannot be disabled")
    prompt_builder = load_factory(root, spec)(dict(spec.config), context, tools)
    if not hasattr(prompt_builder, "build") or not callable(prompt_builder.build):
        raise TypeError("prompt plugin must return a PromptBuilder")
    return prompt_builder


def _build_hooks(
    root: Path,
    manifest: HarnessManifest,
    context: PluginContext,
) -> tuple[tuple[BaseHook, ...], tuple[ResolvedExtension, ...]]:
    hooks: list[BaseHook] = []
    bindings: list[ResolvedExtension] = []
    for spec in manifest.extensions:
        if not spec.enabled:
            continue
        produced = load_factory(root, spec)(dict(spec.config), context)
        instances = (produced,) if isinstance(produced, BaseHook) else tuple(produced)
        for hook in instances:
            if not isinstance(hook, BaseHook):
                raise TypeError(
                    f"extension plugin '{spec.instance_id}' returned a non-hook instance"
                )
            hooks.append(hook)
        bindings.append(
            ResolvedExtension(instance_id=spec.instance_id, hooks=instances)
        )
    return tuple(hooks), tuple(bindings)


def _is_tool(value: Any) -> bool:
    return (
        hasattr(value, "name")
        and isinstance(value.name, str)
        and hasattr(value, "definition")
        and hasattr(value, "run")
        and callable(value.run)
    )
