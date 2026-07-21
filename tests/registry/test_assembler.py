from __future__ import annotations

import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from search_harness.registry import (
    EvolutionPolicy,
    build_harness,
    load_manifest,
)


BASELINE_PLUGINS_ROOT = Path(__file__).parents[2] / "harness_templates" / "actor" / "baseline" / "plugins"
PROBE_HOOK = '''from search_harness.core import BaseHook, HookPhase

class ProbeHook(BaseHook):
    def __init__(self):
        super().__init__(hook_id="probe", phases=frozenset({HookPhase.PRE_PROMPT}))

    def handle(self, context):
        return None

def build(config, context):
    return ProbeHook()
'''


class HarnessAssemblerTest(TestCase):
    def test_concurrent_assembly_isolated_by_plugin_import_session(self) -> None:
        """验证并发 Loop 构造不会竞争 synthetic plugin package。"""

        with TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text(
                "RETRIEVER_URL=http://example.test/retrieve\n",
                encoding="utf-8",
            )

            def assemble(_: int) -> tuple[str, tuple[str, ...]]:
                components = build_harness(
                    BASELINE_PLUGINS_ROOT, env_file=env_file
                )
                return (
                    components.manifest.harness_id,
                    tuple(hook.hook_id for hook in components.hooks.hooks),
                )

            with ThreadPoolExecutor(max_workers=4) as executor:
                results = list(executor.map(assemble, range(12)))

        self.assertEqual(
            results,
            [("baseline_search", ())] * 12,
        )

    def test_loads_baseline_manifest_and_assembles_components(self) -> None:
        """Verifies the loads baseline manifest and assembles components contract."""
        with TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text(
                "RETRIEVER_URL=http://example.test/retrieve\n",
                encoding="utf-8",
            )
            components = build_harness(BASELINE_PLUGINS_ROOT, env_file=env_file)

        self.assertEqual(components.manifest.harness_id, "baseline_search")
        self.assertEqual(components.tools.definitions[0].name, "search")
        self.assertEqual(
            [hook.hook_id for hook in components.hooks.hooks],
            [],
        )
        self.assertEqual(
            components.manifest.tools[0].evolution_policy,
            EvolutionPolicy.FIXED,
        )
        self.assertEqual(
            components.manifest.prompt.evolution_policy,
            EvolutionPolicy.FIXED,
        )

    def test_manifest_rejects_entrypoint_outside_plugins_root(self) -> None:
        """Verifies the manifest rejects entrypoint outside plugins root contract."""
        with TemporaryDirectory() as tmpdir:
            plugins_root = Path(tmpdir)
            (plugins_root / "harness.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "harness_id": "invalid",
                        "tools": [],
                        "prompt": {
                            "instance_id": "prompt",
                            "entrypoint": "../outside.py:build",
                            "config": {},
                            "evolution_policy": "fixed",
                        },
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "inside the plugins root"):
                load_manifest(plugins_root)

    def test_manifest_controls_enabled_extension_instances(self) -> None:
        """Verifies the manifest controls enabled extension instances contract."""
        with TemporaryDirectory() as tmpdir:
            plugins_root = Path(tmpdir) / "plugins"
            shutil.copytree(BASELINE_PLUGINS_ROOT, plugins_root)
            manifest_path = plugins_root / "harness.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            plugin = plugins_root / "extensions" / "probe" / "plugin.py"
            plugin.parent.mkdir(parents=True)
            plugin.write_text(PROBE_HOOK, encoding="utf-8")
            manifest["extensions"].append(
                {
                    "instance_id": "probe",
                    "entrypoint": "extensions/probe/plugin.py:build",
                    "enabled": False,
                    "config": {},
                    "evolution_policy": "mutable",
                }
            )
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            env_file = Path(tmpdir) / ".env"
            env_file.write_text(
                "RETRIEVER_URL=http://example.test/retrieve\n",
                encoding="utf-8",
            )

            disabled = build_harness(plugins_root, env_file=env_file)
            manifest["extensions"][0]["enabled"] = True
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            enabled = build_harness(plugins_root, env_file=env_file)

        self.assertEqual(
            [hook.hook_id for hook in disabled.hooks.hooks],
            [],
        )
        self.assertEqual([hook.hook_id for hook in enabled.hooks.hooks], ["probe"])
