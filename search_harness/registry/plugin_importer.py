"""Explicit loading of plugin factories declared by a Harness manifest."""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from threading import RLock
from types import ModuleType
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .manifest import ComponentSpec


_IMPORT_LOCK = RLock()


@contextmanager
def plugin_import_session() -> Iterator[None]:
    """Serialize one complete plugin assembly using synthetic packages."""

    with _IMPORT_LOCK:
        yield


def load_factory(plugins_root: Path, spec: ComponentSpec) -> Callable[..., Any]:
    """Load one manifest-declared factory without scanning the plugins root."""

    with _IMPORT_LOCK:
        return _load_factory(plugins_root, spec)


def _load_factory(plugins_root: Path, spec: ComponentSpec) -> Callable[..., Any]:
    """Load one factory while holding the synthetic-package import lock."""

    module_path_text, _, factory_name = spec.entrypoint.partition(":")
    root = plugins_root.resolve()
    module_path = (root / module_path_text).resolve()
    if root not in module_path.parents:
        raise ValueError(f"plugin entrypoint escapes plugins root: {spec.entrypoint}")
    if not module_path.is_file():
        raise FileNotFoundError(f"plugin module does not exist: {module_path}")

    component_dir = module_path.parent
    digest = hashlib.sha256(str(component_dir).encode("utf-8")).hexdigest()[:16]
    package_name = f"_search_harness_plugin_{digest}"
    _clear_package(package_name)
    package = ModuleType(package_name)
    package.__path__ = [str(component_dir)]
    package.__package__ = package_name
    sys.modules[package_name] = package

    module_name = f"{package_name}.{module_path.stem}"
    module_spec = importlib.util.spec_from_file_location(module_name, module_path)
    if module_spec is None or module_spec.loader is None:
        raise ImportError(f"cannot load plugin module: {module_path}")
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[module_name] = module
    try:
        module_spec.loader.exec_module(module)
    except Exception:
        _clear_package(package_name)
        raise
    factory = getattr(module, factory_name, None)
    if not callable(factory):
        raise TypeError(f"plugin factory is not callable: {spec.entrypoint}")
    return factory


def _clear_package(package_name: str) -> None:
    """Discard a prior synthetic package so sibling imports cannot go stale."""

    for module_name in tuple(sys.modules):
        if module_name == package_name or module_name.startswith(f"{package_name}."):
            sys.modules.pop(module_name, None)
