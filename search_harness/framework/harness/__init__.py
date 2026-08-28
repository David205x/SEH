"""Harness Component、Lifecycle 与单次运行状态。"""

from .assembly import (
    AssembledHarnessComponents,
    ComponentFactoryContext,
    ResolvedExtension,
    assemble_harness_components,
)
from .components import (
    HookModelBackend,
    OutputComponent,
    OutputParser,
    PromptBuilder,
    PromptComponent,
    ToolComponent,
)
from .lifecycle import BaseHook, HookPhase, HookPipeline, STAGE_KEYS_BY_PHASE
from .prompt_products import (
    HOOK_PROMPT_PROJECTOR_ID,
    HOOK_PROMPT_PROJECTOR_VERSION,
    HookEditOperation,
    HookPromptInput,
    HookPromptOutput,
    HookPromptProduct,
    call_prompt_product,
    render_hook_prompt_user_message,
)
from .loading import ComponentLoader
from .manifest import (
    ComponentDeclaration,
    HarnessManifest,
    load_harness_manifest,
)
from .runtime import Harness, HarnessInstance
from .state import HookContext, HookStateView, StateAccessError, StateRef
from .tagged_output import TaggedOutputParser
from .topology import describe_harness

__all__ = [
    "AssembledHarnessComponents",
    "BaseHook",
    "ComponentDeclaration",
    "ComponentFactoryContext",
    "HookContext",
    "HookStateView",
    "HookModelBackend",
    "HookPhase",
    "HookPipeline",
    "HOOK_PROMPT_PROJECTOR_ID",
    "HOOK_PROMPT_PROJECTOR_VERSION",
    "HookEditOperation",
    "HookPromptInput",
    "HookPromptOutput",
    "HookPromptProduct",
    "HarnessManifest",
    "Harness",
    "HarnessInstance",
    "ComponentLoader",
    "OutputParser",
    "OutputComponent",
    "PromptBuilder",
    "PromptComponent",
    "ResolvedExtension",
    "StateAccessError",
    "StateRef",
    "STAGE_KEYS_BY_PHASE",
    "call_prompt_product",
    "render_hook_prompt_user_message",
    "TaggedOutputParser",
    "ToolComponent",
    "assemble_harness_components",
    "describe_harness",
    "load_harness_manifest",
]
