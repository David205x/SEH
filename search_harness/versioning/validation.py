"""Validation and ephemeral staging for virtual Harness workspaces."""

from __future__ import annotations

import ast
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from search_harness.core import (
    AgentState,
    ChatMessage,
    FinalDecision,
    HookModelResponse,
    HookPhase,
    HookPipeline,
    ModelInput,
    ParsedOutput,
    ToolCall,
    ToolResult,
)
from search_harness.core.hooks import STAGE_KEYS_BY_PHASE
from search_harness.core.trace import InMemoryTraceRecorder
from search_harness.paths import COMPONENT_RUNS_ROOT
from search_harness.registry import EvolutionPolicy, HarnessManifest, build_harness, load_manifest

from .workspace import CandidateWorkspace, HarnessSnapshot


@dataclass(frozen=True)
class ValidationReport:
    """Auditable result tied to one exact workspace revision and digest."""

    passed: bool
    parent_version: str
    revision: int
    candidate_digest: str
    added_paths: tuple[str, ...]
    modified_paths: tuple[str, ...]
    removed_paths: tuple[str, ...]
    errors: tuple[str, ...]


@contextmanager
def stage_files(
    files: Mapping[PurePosixPath, bytes],
) -> Iterator[Path]:
    """Materialize virtual files only for APIs that require filesystem imports."""

    staging_root = (COMPONENT_RUNS_ROOT / "_staging").resolve()
    staging_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="search-harness-",
        dir=staging_root,
    ) as tmpdir:
        root = Path(tmpdir) / "plugins"
        root.mkdir()
        for relative, content in files.items():
            target = root.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        yield root


class HarnessValidator:
    """Enforce parent fixed boundaries, syntax, schema and runtime assembly."""

    def validate(
        self,
        workspace: CandidateWorkspace,
        *,
        env_file: Path | None = None,
    ) -> ValidationReport:
        files = workspace.materialized_files()
        added, modified, removed = _classify_changes(workspace)
        errors: list[str] = []

        try:
            parent_manifest = _load_virtual_manifest(workspace.parent.files)
        except (OSError, TypeError, ValueError) as exc:
            errors.append(f"parent manifest is invalid: {exc}")
            parent_manifest = None
        try:
            candidate_manifest = _load_virtual_manifest(files)
        except (OSError, TypeError, ValueError) as exc:
            errors.append(f"candidate manifest is invalid: {exc}")
            candidate_manifest = None

        if parent_manifest is not None:
            errors.extend(_fixed_path_errors(workspace, parent_manifest))
        if parent_manifest is not None and candidate_manifest is not None:
            errors.extend(_manifest_policy_errors(parent_manifest, candidate_manifest))

        for path, content in files.items():
            if path.suffix != ".py":
                continue
            try:
                source = content.decode("utf-8")
                compile(source, str(path), "exec")
                if path in added or path in modified:
                    errors.extend(_python_review_errors(path, source))
            except (SyntaxError, UnicodeDecodeError) as exc:
                errors.append(f"Python compile failed for {path}: {exc}")

        if not errors:
            try:
                with stage_files(files) as plugins_root:
                    harness = build_harness(plugins_root, env_file=env_file)
                    errors.extend(_hook_contract_errors(harness.hooks.hooks))
            except Exception as exc:
                errors.append(f"Harness assembly failed: {type(exc).__name__}: {exc}")

        return ValidationReport(
            passed=not errors,
            parent_version=workspace.parent.version_id,
            revision=workspace.revision,
            candidate_digest=workspace.digest,
            added_paths=tuple(str(path) for path in added),
            modified_paths=tuple(str(path) for path in modified),
            removed_paths=tuple(str(path) for path in removed),
            errors=tuple(errors),
        )

    def validate_snapshot(
        self,
        snapshot: HarnessSnapshot,
        *,
        env_file: Path | None = None,
    ) -> ValidationReport:
        return self.validate(CandidateWorkspace(snapshot), env_file=env_file)


def _load_virtual_manifest(files: Mapping[PurePosixPath, bytes]) -> HarnessManifest:
    with stage_files(files) as root:
        return load_manifest(root)


def _classify_changes(
    workspace: CandidateWorkspace,
) -> tuple[list[PurePosixPath], list[PurePosixPath], list[PurePosixPath]]:
    current = workspace.materialized_files()
    parent = workspace.parent.files
    added = sorted(set(current) - set(parent), key=str)
    removed = sorted(set(parent) - set(current), key=str)
    modified = sorted(
        (path for path in set(current) & set(parent) if current[path] != parent[path]),
        key=str,
    )
    return added, modified, removed


def _fixed_path_errors(
    workspace: CandidateWorkspace,
    parent: HarnessManifest,
) -> list[str]:
    protected_roots = {
        PurePosixPath(spec.entrypoint.partition(":")[0]).parent
        for spec in (*parent.tools, parent.prompt, *parent.extensions)
        if spec.evolution_policy is EvolutionPolicy.FIXED
    }
    errors: list[str] = []
    for changed in workspace.changed_paths:
        if any(changed == root or root in changed.parents for root in protected_roots):
            errors.append(f"fixed component file cannot be changed: {changed}")
    return errors


def _manifest_policy_errors(
    parent: HarnessManifest,
    candidate: HarnessManifest,
) -> list[str]:
    errors: list[str] = []
    if candidate.harness_id != parent.harness_id:
        errors.append("harness_id cannot be changed")
    parent_items = _component_map(parent)
    candidate_items = _component_map(candidate)
    for instance_id, (category, spec) in parent_items.items():
        current = candidate_items.get(instance_id)
        if current is not None and current[1].evolution_policy is not spec.evolution_policy:
            errors.append(f"component evolution_policy cannot be changed: {instance_id}")
        if spec.evolution_policy is not EvolutionPolicy.FIXED:
            continue
        if current != (category, spec):
            errors.append(f"fixed component manifest cannot be changed: {instance_id}")
    for instance_id, (_, spec) in candidate_items.items():
        if instance_id not in parent_items and spec.evolution_policy is not EvolutionPolicy.MUTABLE:
            errors.append(f"new component must be mutable: {instance_id}")
    errors.extend(_component_directory_errors(candidate))
    return errors


def _component_map(manifest: HarnessManifest):
    result = {spec.instance_id: ("tool", spec) for spec in manifest.tools}
    result[manifest.prompt.instance_id] = ("prompt", manifest.prompt)
    result.update({spec.instance_id: ("extension", spec) for spec in manifest.extensions})
    return result


def _component_directory_errors(manifest: HarnessManifest) -> list[str]:
    roots: dict[PurePosixPath, str] = {}
    errors: list[str] = []
    groups = (
        ("tools", manifest.tools),
        ("prompts", (manifest.prompt,)),
        ("extensions", manifest.extensions),
    )
    for expected_root, specs in groups:
        for spec in specs:
            module = PurePosixPath(spec.entrypoint.partition(":")[0])
            if not module.parts or module.parts[0] != expected_root:
                errors.append(
                    f"component '{spec.instance_id}' entrypoint must be under {expected_root}/"
                )
            owner = roots.setdefault(module.parent, spec.instance_id)
            if owner != spec.instance_id:
                errors.append(
                    f"component directory {module.parent} is shared by '{owner}' and "
                    f"'{spec.instance_id}'"
                )
    return errors


class _ValidationHookModelBackend:
    """Return deterministic JSON without making network calls during validation."""

    def generate(self, request: Any) -> HookModelResponse:
        del request
        return HookModelResponse(
            raw_output=(
                '{"sufficient": true, "instruction": null, '
                '"decision": "continue", "status": "completed"}'
            )
        )


def _hook_contract_errors(hooks: tuple[Any, ...]) -> list[str]:
    """Exercise each subscribed phase against representative non-empty trace."""

    errors: list[str] = []
    for hook in hooks:
        for phase in HookPhase.ALL:
            if phase not in hook.phases:
                continue
            state = AgentState(question="Validation question", max_steps=2, step=1)
            pipeline = HookPipeline(
                (hook,), model_backend=_ValidationHookModelBackend()
            )
            store = pipeline.begin_run(state)
            trace = _validation_trace()
            try:
                pipeline.run_phase(
                    phase,
                    state=state,
                    store=store,
                    trace=trace,
                    stage_values=_validation_stage_values(phase),
                )
            except Exception as exc:
                errors.append(
                    f"Hook contract failed for {hook.hook_id} at {phase}: "
                    f"{type(exc).__name__}: {exc}"
                )
    return errors


def _validation_trace() -> InMemoryTraceRecorder:
    """Build a short prior trajectory that exercises trace-reading Hook branches."""

    trace = InMemoryTraceRecorder()
    trace.record(
        "model_input",
        1,
        ModelInput.from_messages(
            [ChatMessage(role="user", content="Validation question")]
        ).to_dict(),
    )
    trace.record(
        "model_output",
        1,
        {"content": '<tool_call>{"name":"search","arguments":{"query":"validation"}}</tool_call>'},
    )
    trace.record(
        "tool_call",
        1,
        ToolCall(name="search", arguments={"query": "validation"}).to_dict(),
    )
    trace.record(
        "tool_result",
        1,
        ToolResult(name="search", content="validation result").to_dict(),
    )
    trace.record(
        "final_deferred",
        1,
        {"feedback": "Collect direct evidence before answering."},
    )
    return trace


def _validation_stage_values(phase: str) -> dict[str, Any]:
    values = {
        "stage.model_input": ModelInput.from_messages(
            [ChatMessage(role="user", content="Validation question")]
        ),
        "stage.raw_model_output": "<final_answer>validation</final_answer>",
        "stage.parser_input": "<final_answer>validation</final_answer>",
        "stage.parsed_output": ParsedOutput.for_final_answer("validation"),
        "stage.tool_call": ToolCall(name="search", arguments={"query": "validation"}),
        "stage.tool_result": ToolResult(name="search", content="validation result"),
        "stage.final_decision": FinalDecision.accept("validation"),
        "stage.error": RuntimeError("validation error"),
    }
    return {
        key.removeprefix("stage."): values[key]
        for key in STAGE_KEYS_BY_PHASE[phase]
    }


_FORBIDDEN_DYNAMIC_ATTRIBUTE_CALLS = frozenset(
    {"getattr", "hasattr", "setattr", "delattr"}
)


def _python_review_errors(path: PurePosixPath, source: str) -> list[str]:
    """Reject dynamic attribute access that hides invalid Harness API assumptions."""

    tree = ast.parse(source, filename=str(path))
    errors: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id not in _FORBIDDEN_DYNAMIC_ATTRIBUTE_CALLS:
            continue
        errors.append(
            f"Python review failed for {path}:{node.lineno}: "
            f"dynamic attribute builtin '{node.func.id}' is forbidden"
        )
    return errors
