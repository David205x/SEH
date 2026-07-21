from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from search_harness.registry import ComponentSpec, EvolutionPolicy
from search_harness.registry.plugin_importer import load_factory


class PluginImporterTest(TestCase):
    def test_factory_can_use_relative_imports_inside_component_directory(self) -> None:
        """Verifies the factory can use relative imports inside component directory contract."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            component = root / "extensions" / "example"
            component.mkdir(parents=True)
            (component / "helper.py").write_text(
                'VALUE = "loaded from sibling"\n',
                encoding="utf-8",
            )
            (component / "plugin.py").write_text(
                "from .helper import VALUE\n\n"
                "def build(config, context):\n"
                "    return VALUE\n",
                encoding="utf-8",
            )
            spec = ComponentSpec(
                instance_id="example",
                entrypoint="extensions/example/plugin.py:build",
                config={},
                evolution_policy=EvolutionPolicy.MUTABLE,
            )

            factory = load_factory(root, spec)

        self.assertEqual(factory({}, None), "loaded from sibling")

    def test_reload_discards_stale_relative_imports(self) -> None:
        """Verifies the reload discards stale relative imports contract."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            component = root / "extensions" / "example"
            component.mkdir(parents=True)
            helper = component / "helper.py"
            helper.write_text('VALUE = "first"\n', encoding="utf-8")
            (component / "plugin.py").write_text(
                "from .helper import VALUE\n\n"
                "def build(config, context):\n"
                "    return VALUE\n",
                encoding="utf-8",
            )
            spec = ComponentSpec(
                instance_id="example",
                entrypoint="extensions/example/plugin.py:build",
                config={},
                evolution_policy=EvolutionPolicy.MUTABLE,
            )
            first = load_factory(root, spec)({}, None)
            helper.write_text('VALUE = "second value"\n', encoding="utf-8")
            second = load_factory(root, spec)({}, None)

        self.assertEqual(first, "first")
        self.assertEqual(second, "second value")
