"""Teacher Prompt 文件加载与 continuation 渲染测试。"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from search_harness.evolution.research.roles.prompting import load_prompt_spec


class TeacherPromptSpecTest(TestCase):
    def test_loads_and_renders_declared_continuation(self) -> None:
        scratch_root = Path("runs/components/prompting_tests")
        scratch_root.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=scratch_root) as directory:
            component_dir = Path(directory)
            (component_dir / "continuations").mkdir()
            (component_dir / "system.md").write_text("System", encoding="utf-8")
            (component_dir / "user.md").write_text(
                "{{role_input}}\n{{resource_context}}",
                encoding="utf-8",
            )
            (component_dir / "continuations/review.md").write_text(
                "Feedback:\n{{feedback_event}}",
                encoding="utf-8",
            )

            spec = load_prompt_spec(
                component_dir,
                {
                    "instructions": "system.md",
                    "user_template": "user.md",
                    "continuations": {"review": "continuations/review.md"},
                },
            )

        rendered = spec.render_continuation(
            "review",
            {"source": "review", "payload": {"decision": "revise"}},
        )
        self.assertIn('"decision": "revise"', rendered)
        self.assertNotIn("{{feedback_event}}", rendered)

    def test_rejects_continuation_without_feedback_placeholder(self) -> None:
        scratch_root = Path("runs/components/prompting_tests")
        scratch_root.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=scratch_root) as directory:
            component_dir = Path(directory)
            (component_dir / "system.md").write_text("System", encoding="utf-8")
            (component_dir / "user.md").write_text(
                "{{role_input}}\n{{resource_context}}",
                encoding="utf-8",
            )
            (component_dir / "review.md").write_text(
                "Feedback unavailable",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "exactly one"):
                load_prompt_spec(
                    component_dir,
                    {
                        "instructions": "system.md",
                        "user_template": "user.md",
                        "continuations": {"review": "review.md"},
                    },
                )
