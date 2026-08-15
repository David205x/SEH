"""Teacher Judge configuration and task-rubric tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from search_harness.evaluation import (
    EvaluationCase,
    HotpotQAEvaluator,
    build_teacher_judge_model,
)
from search_harness.evaluation.judge import TeacherBinaryJudge
from search_harness.framework.agent import ModelResponse


class TeacherJudgeTest(unittest.TestCase):
    def test_hotpotqa_prompt_states_strict_semantic_boundaries(self) -> None:
        prompt = HotpotQAEvaluator().build_teacher_prompt(
            EvaluationCase(
                example_id="example",
                question="Approximately how many people live there?",
                golden_answer="100",
                predicted_answer="101",
            )
        )

        self.assertIn("Multiple mutually contradictory answer entities", prompt)
        self.assertIn("stage name and legal name", prompt)
        self.assertIn("Geographic parent/child", prompt)
        self.assertIn("broader/narrower", prompt)
        self.assertIn("numeric tolerance is exactly 0", prompt)
        self.assertIn("reference's intended referent", prompt)
        self.assertNotIn("Return exactly one JSON object", prompt)

    def test_teacher_judge_uses_dedicated_thinking_switch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_dir = root / "config"
            config_dir.mkdir()
            (config_dir / "runtime.yaml").write_text(
                "schema_version: 1\n"
                "models:\n"
                "  teacher:\n"
                "    base_url: https://api.deepseek.com\n"
                "    model_id: teacher-test\n"
                "    max_tokens: 128\n"
                "    thinking_mode: enabled\n"
                "teacher_judge:\n"
                "  thinking_mode: disabled\n",
                encoding="utf-8",
            )
            env_file = root / ".env"
            env_file.write_text("TEACHER_API_KEY=test\n", encoding="utf-8")

            model = build_teacher_judge_model(env_file=env_file)

        self.assertEqual("disabled", model.config.thinking_mode)

    def test_unknown_provider_does_not_receive_thinking_extension(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_dir = root / "config"
            config_dir.mkdir()
            (config_dir / "runtime.yaml").write_text(
                "schema_version: 1\n"
                "models:\n"
                "  teacher:\n"
                "    base_url: https://provider.invalid/v1\n"
                "    model_id: teacher-test\n"
                "    max_tokens: 128\n"
                "    thinking_mode: enabled\n"
                "teacher_judge:\n"
                "  thinking_mode: disabled\n",
                encoding="utf-8",
            )
            env_file = root / ".env"
            env_file.write_text("TEACHER_API_KEY=test\n", encoding="utf-8")

            model = build_teacher_judge_model(env_file=env_file)

        self.assertIsNone(model.config.thinking_mode)

    def test_formal_judge_adds_its_own_output_contract(self) -> None:
        model = _RecordingModel()
        judgment = TeacherBinaryJudge(model, HotpotQAEvaluator()).judge(
            EvaluationCase(
                example_id="example",
                question="Where?",
                golden_answer="England",
                predicted_answer="United Kingdom",
            )
        )

        self.assertEqual(0, judgment.score)
        self.assertEqual("A broader location is not an alias.", judgment.assessment)
        prompt = model.model_input.messages[-1].content
        self.assertEqual(0, prompt.count("Return exactly one JSON object"))
        self.assertIn("score-and-assessment object", prompt)

    def test_teacher_judge_rejects_incomplete_output_contract(self) -> None:
        model = _RecordingModel(raw_output='{"score": 0}')
        judgment = TeacherBinaryJudge(model, HotpotQAEvaluator()).judge(
            EvaluationCase(
                example_id="example",
                question="Where?",
                golden_answer="England",
                predicted_answer="United Kingdom",
            )
        )

        self.assertIsNone(judgment.score)
        self.assertIsNone(judgment.assessment)
        self.assertIn("only score and assessment", judgment.error)


class _RecordingModel:
    def __init__(
        self,
        raw_output: str = (
            '{"score": 0, "assessment": '
            '"A broader location is not an alias."}'
        ),
    ) -> None:
        self.model_input = None
        self.raw_output = raw_output

    def generate(self, model_input):
        self.model_input = model_input
        return ModelResponse(raw_output=self.raw_output)


if __name__ == "__main__":
    unittest.main()
