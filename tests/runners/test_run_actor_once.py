from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from search_harness.core import AgentState
from search_harness.runners.run_actor_once import build_loop


BASELINE_PLUGINS_ROOT = Path(__file__).parents[2] / "harness_templates" / "actor" / "baseline" / "plugins"


class RunActorOnceTest(TestCase):
    def test_build_loop_assembles_the_configured_plugins_root(self) -> None:
        """Verifies the build loop assembles the configured plugins root contract."""
        with TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text(
                "\n".join(
                    [
                        "STUDENT_BASE_URL=http://example.test/v1",
                        "STUDENT_MODEL_ID=test-model",
                        "RETRIEVER_URL=http://example.test/retrieve",
                    ]
                ),
                encoding="utf-8",
            )
            loop = build_loop(
                env_file=env_file,
                model_role="student",
                plugins_root=BASELINE_PLUGINS_ROOT,
            )

        prompt = loop.prompt_builder.build(
            AgentState(question="Who wrote The Hobbit?", max_steps=2)
        )
        self.assertIn("`search`", prompt.messages[0].content)
        self.assertEqual(
            [hook.hook_id for hook in loop.hooks.hooks],
            [],
        )
