from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from search_harness.framework.harness import (
    assemble_harness_components,
    load_harness_manifest,
)


TOOL_COMPONENT = '''
from dataclasses import dataclass

from search_harness.framework.tools import ToolDefinition, ToolResult

@dataclass
class ProbeTool:
    name: str = "probe"
    definition: ToolDefinition = ToolDefinition(
        name="probe",
        description="Probe tool.",
        parameters=(),
    )

    def run(self, arguments):
        return ToolResult(name=self.name, content="ok")

def build(config, context):
    return ProbeTool()
'''

PROMPT_COMPONENT = '''
def build(config, context, tools):
    return {"kind": "prompt", "tool_names": [tool.name for tool in tools.tools]}
'''

OUTPUT_COMPONENT = '''
def build(config, context):
    return {"kind": "output", "format": config["format"]}
'''

EXTENSION_COMPONENT = '''
def build(config, context):
    return ("first", "second")
'''


class HarnessAssemblyTest(TestCase):
    def test_manifest_rejects_evolution_policy(self) -> None:
        """Harness Manifest 不接受 Evolution 应用字段。"""

        with TemporaryDirectory(dir=Path("runs/components")) as directory:
            root = Path(directory)
            self._write_manifest(root)
            path = root / "harness.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["prompt"]["evolution_policy"] = "fixed"
            path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "unsupported fields"):
                load_harness_manifest(root)

    def test_assembles_all_component_kinds_in_one_shared_path(self) -> None:
        """共享 Assembly 为不同 Runner 提供同一组已加载组件。"""

        with TemporaryDirectory(dir=Path("runs/components")) as directory:
            root = Path(directory)
            self._write_component(root / "components/tools/probe.py", TOOL_COMPONENT)
            self._write_component(root / "components/prompts/probe.py", PROMPT_COMPONENT)
            self._write_component(root / "components/outputs/probe.py", OUTPUT_COMPONENT)
            self._write_component(
                root / "components/extensions/probe.py",
                EXTENSION_COMPONENT,
            )
            self._write_manifest(root)

            assembled = assemble_harness_components(root)

        self.assertEqual(assembled.manifest.harness_id, "probe_harness")
        self.assertEqual(assembled.prompt["tool_names"], ["probe"])
        self.assertEqual(assembled.output["format"], "tagged")
        self.assertEqual(
            assembled.extensions[0].components,
            ("first", "second"),
        )

    @staticmethod
    def _write_component(path: Path, source: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")

    @staticmethod
    def _write_manifest(root: Path) -> None:
        payload = {
            "schema_version": 1,
            "harness_id": "probe_harness",
            "tools": [
                {
                    "instance_id": "probe_tool",
                    "entrypoint": "components/tools/probe.py:build",
                    "config": {},
                }
            ],
            "prompt": {
                "instance_id": "probe_prompt",
                "entrypoint": "components/prompts/probe.py:build",
                "config": {},
            },
            "output": {
                "instance_id": "probe_output",
                "entrypoint": "components/outputs/probe.py:build",
                "config": {"format": "tagged"},
            },
            "extensions": [
                {
                    "instance_id": "probe_extension",
                    "entrypoint": "components/extensions/probe.py:build",
                    "config": {},
                }
            ],
        }
        (root / "harness.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
