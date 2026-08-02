"""Deterministic source-quality checks applied only to Compiler candidates."""

from __future__ import annotations

import ast
from pathlib import PurePosixPath

from search_harness.evolution.versioning import CandidateWorkspace


def review_compiler_candidate(workspace: CandidateWorkspace) -> list[str]:
    """Return actionable authoring-policy errors for changed Python files."""

    errors = []
    for path in workspace.changed_paths:
        if path.suffix != ".py" or not workspace.exists(path):
            continue
        try:
            tree = ast.parse(workspace.read_text(path), filename=str(path))
        except SyntaxError:
            # HarnessValidator owns syntax diagnostics and reports richer context.
            continue
        errors.extend(_review_tree(path, tree))
    return errors


def _review_tree(path: PurePosixPath, tree: ast.Module) -> list[str]:
    errors = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Delete) and any(
            isinstance(target, ast.Name)
            and target.id in {"config", "context"}
            for target in node.targets
        ):
            errors.append(
                _error(
                    path,
                    node.lineno,
                    "factory arguments must not be consumed by a dummy del statement",
                )
            )
        if (
            isinstance(node, ast.ExceptHandler)
            and isinstance(node.type, ast.Name)
            and node.type.id in {"Exception", "BaseException"}
        ):
            errors.append(
                _error(
                    path,
                    node.lineno,
                    f"broad exception handler '{node.type.id}' is forbidden",
                )
            )
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != "build" or not _has_parameter(node, "config"):
            continue
        if not _loads_name(node, "config"):
            errors.append(
                _error(
                    path,
                    node.lineno,
                    "Component Factory must validate or consume its config mapping",
                )
            )
    stage_keys = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    required_types = {
        "stage.tool_call": "ToolCall",
        "stage.tool_result": "ToolResult",
        "stage.model_input": "ModelInput",
    }
    for stage_key, expected_type in required_types.items():
        if stage_key not in stage_keys:
            continue
        if not _has_isinstance_check(tree, expected_type):
            errors.append(
                _error(
                    path,
                    1,
                    f"{stage_key} must be checked with isinstance(..., "
                    f"{expected_type}) before field access",
                )
            )
    return errors


def _has_parameter(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    name: str,
) -> bool:
    parameters = (
        *node.args.posonlyargs,
        *node.args.args,
        *node.args.kwonlyargs,
    )
    return any(parameter.arg == name for parameter in parameters)


def _loads_name(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    name: str,
) -> bool:
    return any(
        isinstance(item, ast.Name)
        and isinstance(item.ctx, ast.Load)
        and item.id == name
        for item in ast.walk(node)
    )


def _has_isinstance_check(tree: ast.Module, expected_type: str) -> bool:
    for item in ast.walk(tree):
        if not isinstance(item, ast.Call):
            continue
        if not isinstance(item.func, ast.Name) or item.func.id != "isinstance":
            continue
        if len(item.args) < 2:
            continue
        type_arg = item.args[1]
        if isinstance(type_arg, ast.Name) and type_arg.id == expected_type:
            return True
        if isinstance(type_arg, ast.Tuple) and any(
            isinstance(value, ast.Name) and value.id == expected_type
            for value in type_arg.elts
        ):
            return True
    return False


def _error(path: PurePosixPath, line: int, message: str) -> str:
    return f"Compiler review failed for {path}:{line}: {message}"
