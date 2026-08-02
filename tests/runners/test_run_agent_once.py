from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from search_harness.framework import AgentState
from search_harness.runners.run_agent_once import build_agent_and_runner


BASELINE_TEMPLATE_ROOT = (
    Path(__file__).parents[2] / "harness_templates" / "student" / "baseline"
)


class RunAgentOnceTest(TestCase):
    def test_build_loop_assembles_the_configured_template_root(self) -> None:
        """Verifies the build loop assembles the configured Template root."""
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
            agent, _ = build_agent_and_runner(
                env_file=env_file,
                model_role="student",
                template_root=BASELINE_TEMPLATE_ROOT,
            )

        prompt = agent.harness.prompt.build(
            AgentState(question="Who wrote The Hobbit?", max_steps=2)
        )
        self.assertIn("`search`", prompt.messages[0].content)
        self.assertEqual(
            [hook.hook_id for hook in agent.harness.lifecycle.hooks],
            [],
        )
        self.assertEqual(
            type(agent.harness.output).__name__,
            "TaggedOutputParser",
        )
