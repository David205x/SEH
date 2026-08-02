"""Manifest 声明的 Harness Component Factory 显式加载器。"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from threading import RLock
from types import ModuleType
from pathlib import Path
from typing import Any, Protocol


_IMPORT_LOCK = RLock()


class ComponentDeclaration(Protocol):
    """Component Loader 所需的最小声明视图。"""

    entrypoint: str


class ComponentLoader:
    """从一个 Template Root 加载显式声明的 Component Factory。"""

    def __init__(self, template_root: Path) -> None:
        self.template_root = template_root.resolve()

    @contextmanager
    def session(self) -> Iterator[None]:
        """串行化一次完整 Assembly 使用的 synthetic package。"""

        with _IMPORT_LOCK:
            yield

    def load_factory(
        self,
        declaration: ComponentDeclaration,
    ) -> Callable[..., Any]:
        """加载一个显式声明的 factory，不扫描 Template Root。"""

        with _IMPORT_LOCK:
            return self._load_factory(declaration)

    def _load_factory(
        self,
        declaration: ComponentDeclaration,
    ) -> Callable[..., Any]:
        module_path_text, _, factory_name = declaration.entrypoint.partition(":")
        root = self.template_root
        entrypoint = declaration.entrypoint
        module_path = (root / module_path_text).resolve()
        if root not in module_path.parents:
            raise ValueError(f"component entrypoint escapes template root: {entrypoint}")
        if not module_path.is_file():
            raise FileNotFoundError(f"component module does not exist: {module_path}")

        component_dir = module_path.parent
        digest = hashlib.sha256(str(component_dir).encode("utf-8")).hexdigest()[:16]
        package_name = f"_search_harness_component_{digest}"
        _clear_package(package_name)
        package = ModuleType(package_name)
        package.__path__ = [str(component_dir)]
        package.__package__ = package_name
        sys.modules[package_name] = package

        module_name = f"{package_name}.{module_path.stem}"
        module_spec = importlib.util.spec_from_file_location(module_name, module_path)
        if module_spec is None or module_spec.loader is None:
            raise ImportError(f"cannot load component module: {module_path}")
        module = importlib.util.module_from_spec(module_spec)
        sys.modules[module_name] = module
        try:
            module_spec.loader.exec_module(module)
        except Exception:
            _clear_package(package_name)
            raise
        factory = getattr(module, factory_name, None)
        if not callable(factory):
            raise TypeError(f"component factory is not callable: {entrypoint}")
        return factory


def _clear_package(package_name: str) -> None:
    """Discard a prior synthetic package so sibling imports cannot go stale."""

    for module_name in tuple(sys.modules):
        if module_name == package_name or module_name.startswith(f"{package_name}."):
            sys.modules.pop(module_name, None)
