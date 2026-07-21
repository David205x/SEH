"""Manifest-driven assembly of external Harness plugin roots."""

from .assembler import HarnessComponents, PluginContext, ResolvedExtension, build_harness
from .topology import describe_harness
from .manifest import ComponentSpec, EvolutionPolicy, HarnessManifest, load_manifest

__all__ = [
    "ComponentSpec",
    "EvolutionPolicy",
    "HarnessComponents",
    "HarnessManifest",
    "PluginContext",
    "ResolvedExtension",
    "build_harness",
    "describe_harness",
    "load_manifest",
]
