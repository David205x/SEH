"""角色无关的 Harness Component 装配流程。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..tools import DefinedTool, ToolSet
from .loading import ComponentLoader
from .manifest import ComponentDeclaration, HarnessManifest, load_harness_manifest


@dataclass(frozen=True)
class ComponentFactoryContext:
    """Component Factory 可读取的最小运行依赖。"""

    template_root: Path
    env_file: Path | None = None
    runtime_context: object | None = None


@dataclass(frozen=True)
class ResolvedExtension:
    """一个 Extension 声明及其产生的有序对象。"""

    instance_id: str
    components: tuple[object, ...]


@dataclass(frozen=True)
class AssembledHarnessComponents:
    """共享 Assembly 已解析但尚未绑定具体 Runner 的组件。"""

    manifest: HarnessManifest
    tools: ToolSet
    prompt: object
    output: object
    extensions: tuple[ResolvedExtension, ...]


def assemble_harness_components(
    template_root: Path,
    *,
    env_file: Path | None = None,
    runtime_context: object | None = None,
) -> AssembledHarnessComponents:
    """按 Tool、Prompt、Output、Extension 顺序执行 Component Factory。"""

    root = template_root.resolve()
    manifest = load_harness_manifest(root)
    context = ComponentFactoryContext(
        template_root=root,
        env_file=env_file,
        runtime_context=runtime_context,
    )
    loader = ComponentLoader(root)
    with loader.session():
        tools = ToolSet(_build_tools(loader, manifest, context))
        prompt = _build_component(
            loader,
            manifest.prompt,
            context,
            tools,
        )
        output = _build_component(loader, manifest.output, context)
        extensions = _build_extensions(loader, manifest, context)
    return AssembledHarnessComponents(
        manifest=manifest,
        tools=tools,
        prompt=prompt,
        output=output,
        extensions=extensions,
    )


def _build_tools(
    loader: ComponentLoader,
    manifest: HarnessManifest,
    context: ComponentFactoryContext,
) -> tuple[DefinedTool, ...]:
    tools: list[DefinedTool] = []
    for declaration in manifest.tools:
        if not declaration.enabled:
            continue
        tool = _build_component(loader, declaration, context)
        if not _is_tool(tool):
            raise TypeError(
                f"tool component '{declaration.instance_id}' returned an invalid tool"
            )
        tools.append(tool)
    return tuple(tools)


def _build_extensions(
    loader: ComponentLoader,
    manifest: HarnessManifest,
    context: ComponentFactoryContext,
) -> tuple[ResolvedExtension, ...]:
    resolved: list[ResolvedExtension] = []
    for declaration in manifest.extensions:
        if not declaration.enabled:
            continue
        produced = _build_component(loader, declaration, context)
        components = (
            tuple(produced)
            if isinstance(produced, (list, tuple))
            else (produced,)
        )
        resolved.append(
            ResolvedExtension(
                instance_id=declaration.instance_id,
                components=components,
            )
        )
    return tuple(resolved)


def _build_component(
    loader: ComponentLoader,
    declaration: ComponentDeclaration,
    context: ComponentFactoryContext,
    *factory_dependencies: object,
) -> Any:
    factory = loader.load_factory(declaration)
    return factory(
        dict(declaration.config),
        context,
        *factory_dependencies,
    )


def _is_tool(value: Any) -> bool:
    return (
        hasattr(value, "name")
        and isinstance(value.name, str)
        and hasattr(value, "definition")
        and hasattr(value, "run")
        and callable(value.run)
    )
