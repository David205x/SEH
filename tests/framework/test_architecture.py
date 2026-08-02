from __future__ import annotations

import ast
from pathlib import Path
from unittest import TestCase


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRAMEWORK_ROOT = PROJECT_ROOT / "search_harness" / "framework"
FORBIDDEN_DEPENDENCIES = (
    "search_harness.datasets",
    "search_harness.evaluation",
    "search_harness.evolution",
    "search_harness.integrations",
)


class FrameworkArchitectureTest(TestCase):
    def test_framework_does_not_import_application_or_provider_modules(self) -> None:
        """The extractable framework boundary only depends inward."""

        violations: list[str] = []
        for path in FRAMEWORK_ROOT.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            for node in ast.walk(tree):
                imported = _absolute_imports(node)
                for name in imported:
                    if name.startswith(FORBIDDEN_DEPENDENCIES):
                        relative = path.relative_to(PROJECT_ROOT).as_posix()
                        violations.append(f"{relative}:{node.lineno}: {name}")

        self.assertEqual(violations, [])


def _absolute_imports(node: ast.AST) -> tuple[str, ...]:
    if isinstance(node, ast.Import):
        return tuple(alias.name for alias in node.names)
    if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
        return (node.module,)
    return ()
