from __future__ import annotations

import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from search_harness.versioning import HarnessVersionStore
from search_harness.versioning.__main__ import main


PROMPT_PLUGIN = '''from search_harness.core import ChatMessage, ModelInput

class Prompt:
    def build(self, state):
        return ModelInput.from_messages([ChatMessage(role="user", content=state.question)])

def build(config, context, tools):
    return Prompt()
'''


class VersioningCliTest(TestCase):
    def test_initializes_checkpoint_store_from_template(self) -> None:
        """验证 CLI 从模板创建首个 accepted Harness 版本并记录来源。"""

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            template_root = _make_template(root)
            checkpoint_store = root / "checkpoints" / "experiment_actor"
            output = StringIO()

            with redirect_stdout(output):
                main(
                    [
                        "init",
                        "--template-root",
                        str(template_root),
                        "--checkpoint-store",
                        str(checkpoint_store),
                        "--env-file",
                        str(root / ".env"),
                        "--checkpoint-store-id",
                        "experiment_actor",
                    ]
                )

            store = HarnessVersionStore(checkpoint_store)
            record = store.list_versions()[-1]
            checkpoint = json.loads(
                (checkpoint_store / "checkpoint.json").read_text(encoding="utf-8")
            )

        self.assertEqual(record.version_id, "harness_v0001")
        self.assertEqual(checkpoint["checkpoint_store_id"], "experiment_actor")
        self.assertEqual(
            checkpoint["initialized_from"]["template_root"],
            str(template_root.resolve()),
        )
        self.assertIn("accepted version: harness_v0001", output.getvalue())


def _make_template(base: Path) -> Path:
    template_root = base / "template" / "plugins"
    prompt_dir = template_root / "prompts" / "base"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "plugin.py").write_text(PROMPT_PLUGIN, encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "harness_id": "test_harness",
        "tools": [],
        "prompt": {
            "instance_id": "base_prompt",
            "entrypoint": "prompts/base/plugin.py:build",
            "config": {},
            "evolution_policy": "fixed",
        },
        "extensions": [],
    }
    (template_root / "harness.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    return template_root
