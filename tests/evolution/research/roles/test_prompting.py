"""Teacher Prompt 文件加载与 continuation 渲染测试。"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from search_harness.evolution.research.roles.contracts import EvidenceReview
from search_harness.evolution.research.roles.prompting import load_prompt_spec


PROJECT_ROOT = Path(__file__).resolve().parents[4]


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

    def test_evidence_revision_prompt_preserves_existing_protocol(self) -> None:
        """Reviewer 在自由文本字段内按稳定顺序交接修订约束。"""

        prompt = (
            PROJECT_ROOT
            / "harness_templates"
            / "teacher"
            / "evidence_reviewer"
            / "prompt"
            / "system.md"
        ).read_text(encoding="utf-8")

        labels = (
            "Observed failure:",
            "Required revision:",
            "Must preserve:",
            "Claim limit:",
        )
        positions = [prompt.index(label) for label in labels]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("existing free-text fields", prompt)
        self.assertIn("leave\n`next_obligation` empty", prompt)
        self.assertEqual(
            set(EvidenceReview.model_fields),
            {
                "decision",
                "phase_findings",
                "assessment",
                "key_risk",
                "next_obligation",
            },
        )

    def test_researcher_revision_prompt_uses_feedback_before_trials(self) -> None:
        """Researcher 优先应用 Reviewer 结论并按需逐层读取 Trial。"""

        prompt_root = (
            PROJECT_ROOT
            / "harness_templates"
            / "teacher"
            / "hypothesis_researcher"
            / "prompt"
        )
        combined = "\n".join(
            [
                (prompt_root / "system.md").read_text(encoding="utf-8"),
                (prompt_root / "continuations" / "evidence_reviewer.md")
                .read_text(encoding="utf-8"),
            ]
        )

        self.assertIn("feedback is sufficient", combined)
        tool_positions = [
            combined.index(tool)
            for tool in (
                "`list_trial_evidence`",
                "`get_trial_evidence`",
                "`get_trial_event`",
            )
        ]
        self.assertEqual(tool_positions, sorted(tool_positions))
        self.assertIn("never copy case answers", combined)
        self.assertIn("When the decision is `revise`", combined)
        self.assertIn("without inventing missing labels", combined)
