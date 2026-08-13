"""Validation and ephemeral staging for virtual Harness workspaces."""

from __future__ import annotations

import ast
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from search_harness.framework import (
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
from search_harness.framework.harness import STAGE_KEYS_BY_PHASE
from search_harness.framework import InMemoryTrajectoryRecorder
from search_harness.paths import COMPONENT_RUNS_ROOT
from search_harness.framework.harness import (
    BaseHook,
    HarnessManifest,
    assemble_harness_components,
    load_harness_manifest,
)

from .policy import (
    ComponentEvolutionPolicy,
    EvolutionPolicy,
    load_evolution_policy,
)
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
        root = Path(tmpdir) / "template"
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
            parent_manifest, parent_policy = _load_virtual_template(
                workspace.parent.files
            )
        except (OSError, TypeError, ValueError) as exc:
            errors.append(f"parent template configuration is invalid: {exc}")
            parent_manifest = None
            parent_policy = None
        try:
            candidate_manifest, candidate_policy = _load_virtual_template(files)
        except (OSError, TypeError, ValueError) as exc:
            errors.append(f"candidate template configuration is invalid: {exc}")
            candidate_manifest = None
            candidate_policy = None

        if parent_manifest is not None and parent_policy is not None:
            errors.extend(
                _fixed_path_errors(workspace, parent_manifest, parent_policy)
            )
        if all(
            item is not None
            for item in (
                parent_manifest,
                parent_policy,
                candidate_manifest,
                candidate_policy,
            )
        ):
            errors.extend(
                _template_policy_errors(
                    parent_manifest,
                    parent_policy,
                    candidate_manifest,
                    candidate_policy,
                )
            )

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
                with stage_files(files) as template_root:
                    assembled = assemble_harness_components(
                        template_root,
                        env_file=env_file,
                    )
                    hooks = _assembled_hooks(assembled.extensions)
                    contract_errors = _hook_contract_errors(hooks)
                    errors.extend(contract_errors)
                    if not contract_errors:
                        errors.extend(_hook_pipeline_errors(hooks))
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


def _load_virtual_template(
    files: Mapping[PurePosixPath, bytes],
) -> tuple[HarnessManifest, EvolutionPolicy]:
    with stage_files(files) as root:
        return load_harness_manifest(root), load_evolution_policy(root)


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
    parent_manifest: HarnessManifest,
    parent_policy: EvolutionPolicy,
) -> list[str]:
    protected_roots = {
        PurePosixPath(spec.entrypoint.partition(":")[0]).parent
        for spec in _manifest_components(parent_manifest).values()
        if parent_policy.components[spec.instance_id]
        is ComponentEvolutionPolicy.FIXED
    }
    errors: list[str] = []
    for changed in workspace.changed_paths:
        if any(changed == root or root in changed.parents for root in protected_roots):
            errors.append(f"fixed component file cannot be changed: {changed}")
    return errors


def _template_policy_errors(
    parent_manifest: HarnessManifest,
    parent_policy: EvolutionPolicy,
    candidate_manifest: HarnessManifest,
    candidate_policy: EvolutionPolicy,
) -> list[str]:
    errors: list[str] = []
    if candidate_manifest.harness_id != parent_manifest.harness_id:
        errors.append("harness_id cannot be changed")
    if parent_policy.harness_id != parent_manifest.harness_id:
        errors.append("parent Evolution Policy harness_id differs from Manifest")
    if candidate_policy.harness_id != candidate_manifest.harness_id:
        errors.append("candidate Evolution Policy harness_id differs from Manifest")
    parent_items = _component_map(parent_manifest)
    candidate_items = _component_map(candidate_manifest)
    errors.extend(_policy_coverage_errors(parent_items, parent_policy))
    errors.extend(_policy_coverage_errors(candidate_items, candidate_policy))
    for instance_id, (category, spec) in parent_items.items():
        current = candidate_items.get(instance_id)
        parent_value = parent_policy.components.get(instance_id)
        candidate_value = candidate_policy.components.get(instance_id)
        if current is not None and candidate_value is not parent_value:
            errors.append(
                f"component Evolution Policy cannot be changed: {instance_id}"
            )
        if parent_value is not ComponentEvolutionPolicy.FIXED:
            continue
        if current != (category, spec):
            errors.append(f"fixed component manifest cannot be changed: {instance_id}")
    for instance_id in candidate_items:
        if (
            instance_id not in parent_items
            and candidate_policy.components.get(instance_id)
            is not ComponentEvolutionPolicy.MUTABLE
        ):
            errors.append(f"new component must be mutable: {instance_id}")
    errors.extend(_component_directory_errors(candidate_manifest))
    return errors


def _component_map(manifest: HarnessManifest):
    result = {spec.instance_id: ("tool", spec) for spec in manifest.tools}
    result[manifest.prompt.instance_id] = ("prompt", manifest.prompt)
    result[manifest.output.instance_id] = ("output", manifest.output)
    result.update({spec.instance_id: ("extension", spec) for spec in manifest.extensions})
    return result


def _manifest_components(manifest: HarnessManifest):
    return {instance_id: spec for instance_id, (_, spec) in _component_map(manifest).items()}


def _policy_coverage_errors(
    components: dict[str, tuple[str, Any]],
    policy: EvolutionPolicy,
) -> list[str]:
    declared = set(components)
    governed = set(policy.components)
    errors = [
        f"Evolution Policy is missing component: {instance_id}"
        for instance_id in sorted(declared - governed)
    ]
    errors.extend(
        f"Evolution Policy references unknown component: {instance_id}"
        for instance_id in sorted(governed - declared)
    )
    return errors


def _component_directory_errors(manifest: HarnessManifest) -> list[str]:
    roots: dict[PurePosixPath, tuple[str, PurePosixPath]] = {}
    errors: list[str] = []
    groups = (
        ("tools", manifest.tools),
        ("prompt", (manifest.prompt,)),
        ("output", (manifest.output,)),
        ("extensions", manifest.extensions),
    )
    for expected_root, specs in groups:
        expected_parts = PurePosixPath(expected_root).parts
        for spec in specs:
            module = PurePosixPath(spec.entrypoint.partition(":")[0])
            if module.parts[: len(expected_parts)] != expected_parts:
                errors.append(
                    f"component '{spec.instance_id}' entrypoint must be under {expected_root}/"
                )
            owner_id, owner_module = roots.setdefault(
                module.parent,
                (spec.instance_id, module),
            )
            if owner_module != module:
                errors.append(
                    f"component directory {module.parent} is shared by '{owner_id}' and "
                    f"'{spec.instance_id}'"
                )
    return errors


def _assembled_hooks(extension_bindings: tuple[Any, ...]) -> tuple[BaseHook, ...]:
    hooks: list[BaseHook] = []
    for binding in extension_bindings:
        for component in binding.components:
            if not isinstance(component, BaseHook):
                raise TypeError(
                    f"extension '{binding.instance_id}' returned a non-Hook"
                )
            hooks.append(component)
    return tuple(hooks)


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
    """Exercise each Hook/phase alone for precise contract diagnostics."""

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
                    trajectory=trace,
                    stage_values=_validation_stage_values(phase),
                )
            except Exception as exc:
                errors.append(
                    f"Hook contract failed for {hook.hook_id} at {phase}: "
                    f"{type(exc).__name__}: {exc}"
                )
    return errors


def _hook_pipeline_errors(hooks: tuple[BaseHook, ...]) -> list[str]:
    """Exercise the assembled Hook Pipeline across one synthetic rollout."""

    try:
        pipeline = HookPipeline(
            hooks,
            model_backend=_ValidationHookModelBackend(),
        )
    except Exception as exc:
        return [
            "Hook pipeline construction failed: "
            f"{type(exc).__name__}: {exc}"
        ]

    state = AgentState(question="Validation question", max_steps=6)
    store = pipeline.begin_run(state)
    trace = _validation_trace()
    phase = "not_started"
    iteration = 0
    try:
        for iteration in range(1, 3):
            state.step = iteration
            phase = HookPhase.PRE_PROMPT
            pipeline.run_phase(
                phase,
                state=state,
                store=store,
                trajectory=trace,
            )

            phase = HookPhase.POST_PROMPT
            model_input = pipeline.run_phase(
                phase,
                state=state,
                store=store,
                trajectory=trace,
                stage_values={
                    "model_input": ModelInput.from_messages(
                        [ChatMessage(role="user", content="Validation question")]
                    )
                },
            )["model_input"]
            state.append_model_input(model_input)
            trace.record("model_input", state.step, model_input.to_dict())

            phase = HookPhase.POST_MODEL
            raw_output = pipeline.run_phase(
                phase,
                state=state,
                store=store,
                trajectory=trace,
                stage_values={
                    "raw_model_output": (
                        '<tool_call>{"name":"search","arguments":'
                        '{"query":"validation"}}</tool_call>'
                    )
                },
            )["raw_model_output"]
            state.append_model_output(raw_output)
            trace.record(
                "model_output",
                state.step,
                {"raw_output": raw_output},
            )

            tool_call = ToolCall(
                name="search",
                arguments={"query": f"validation {iteration}"},
            )
            phase = HookPhase.POST_PARSE
            parsed = pipeline.run_phase(
                phase,
                state=state,
                store=store,
                trajectory=trace,
                stage_values={
                    "parser_input": raw_output,
                    "parsed_output": ParsedOutput.for_tool_call(tool_call),
                },
            )["parsed_output"]
            state.append_parsed_output(parsed)
            trace.record("parsed_output", state.step, parsed.to_dict())

            phase = HookPhase.PRE_TOOL
            tool_call = pipeline.run_phase(
                phase,
                state=state,
                store=store,
                trajectory=trace,
                stage_values={"tool_call": tool_call},
            )["tool_call"]
            trace.record("tool_call", state.step, tool_call.to_dict())

            phase = HookPhase.POST_TOOL
            tool_result = pipeline.run_phase(
                phase,
                state=state,
                store=store,
                trajectory=trace,
                stage_values={
                    "tool_call": tool_call,
                    "tool_result": ToolResult(
                        name=tool_call.name,
                        content=f"validation result {iteration}",
                    ),
                },
            )["tool_result"]
            state.append_tool_interaction(tool_call, tool_result)
            state.append_conversation_message(
                ChatMessage(role="assistant", content=raw_output)
            )
            state.append_conversation_message(
                ChatMessage(role="user", content=tool_result.content)
            )
            trace.record("tool_result", state.step, tool_result.to_dict())

        for final_index in range(1, 3):
            iteration = final_index + 2
            state.step = iteration
            phase = HookPhase.PRE_PROMPT
            pipeline.run_phase(
                phase,
                state=state,
                store=store,
                trajectory=trace,
            )

            phase = HookPhase.POST_PROMPT
            model_input = pipeline.run_phase(
                phase,
                state=state,
                store=store,
                trajectory=trace,
                stage_values={
                    "model_input": ModelInput.from_messages(
                        [ChatMessage(role="user", content="Validation question")]
                    )
                },
            )["model_input"]
            state.append_model_input(model_input)
            trace.record("model_input", state.step, model_input.to_dict())

            phase = HookPhase.POST_MODEL
            raw_output = pipeline.run_phase(
                phase,
                state=state,
                store=store,
                trajectory=trace,
                stage_values={
                    "raw_model_output": "<final_answer>validation</final_answer>"
                },
            )["raw_model_output"]
            state.append_model_output(raw_output)
            trace.record(
                "model_output",
                state.step,
                {"raw_output": raw_output},
            )

            phase = HookPhase.POST_PARSE
            parsed = pipeline.run_phase(
                phase,
                state=state,
                store=store,
                trajectory=trace,
                stage_values={
                    "parser_input": raw_output,
                    "parsed_output": ParsedOutput.for_final_answer(
                        f"validation {final_index}"
                    ),
                },
            )["parsed_output"]
            state.append_parsed_output(parsed)
            trace.record("parsed_output", state.step, parsed.to_dict())
            candidate = f"validation {final_index}"
            trace.record(
                "final_answer_candidate",
                state.step,
                {"answer": candidate},
            )

            phase = HookPhase.PRE_FINAL
            decision = pipeline.run_phase(
                phase,
                state=state,
                store=store,
                trajectory=trace,
                stage_values={
                    "final_decision": FinalDecision.accept(candidate)
                },
            )["final_decision"]
            event_type = (
                "final_deferred"
                if decision.action.value == "defer"
                else "final_answer"
            )
            trace.record(event_type, state.step, decision.to_dict())

        for error_index in range(1, 3):
            iteration = error_index + 4
            state.step = iteration
            phase = HookPhase.ON_ERROR
            pipeline.run_phase(
                phase,
                state=state,
                store=store,
                trajectory=trace,
                stage_values={
                    "error": RuntimeError(
                        f"validation lifecycle error {error_index}"
                    )
                },
            )
    except Exception as exc:
        return [
            "Hook pipeline lifecycle failed "
            f"at iteration {iteration}, phase {phase}: "
            f"{type(exc).__name__}: {exc}"
        ]
    return []


def _validation_trace() -> InMemoryTrajectoryRecorder:
    """Build a short prior trajectory that exercises trace-reading Hook branches."""

    trace = InMemoryTrajectoryRecorder()
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
