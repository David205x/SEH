from __future__ import annotations

import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
from unittest import TestCase

from search_harness.evaluation import (
    HotpotQAEvaluator,
    StaticDecision,
    TeacherJudgment,
)
from search_harness.evaluation.types import StaticEvaluation
from search_harness.evaluation.run_evaluation import _default_output_dir
from search_harness.evaluation.report import evaluate_rollout_file, write_evaluation_report


class _Judge:
    def judge(self, case) -> TeacherJudgment:
        del case
        return TeacherJudgment(score=1, raw_output='{"score": 1}')


class EvaluationReportTest(TestCase):
    def test_default_output_keeps_student_artifacts_together(self) -> None:
        """Verifies Student rollout evaluation remains inside the same component run."""

        rollout = Path("runs/components/student/example/rollout.jsonl")

        self.assertEqual(
            _default_output_dir(rollout),
            Path("runs/components/student/example/evaluation"),
        )

    def test_default_output_isolates_external_evaluator_runs(self) -> None:
        """Verifies external rollout evaluation gets a standalone component run."""

        output_dir = _default_output_dir(Path("external/rollout.jsonl"))

        self.assertEqual(output_dir.parts[:3], ("runs", "components", "evaluator"))
        self.assertEqual(output_dir.name, "evaluation")

    def test_evaluates_static_and_teacher_scored_answers(self) -> None:
        """Verifies the evaluates static and teacher scored answers contract."""
        with TemporaryDirectory() as tmpdir:
            input_file = Path(tmpdir) / "rollouts.jsonl"
            input_file.write_text(
                "\n".join(
                    [
                        json.dumps(_record("one", "The Hobbit", "the hobbit")),
                        json.dumps(_record("two", "J. R. R. Tolkien", "Tolkien")),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            report = evaluate_rollout_file(
                input_file,
                HotpotQAEvaluator(),
                _Judge(),
                show_progress=False,
            )

        self.assertEqual(report["metrics"]["answers"]["correct_count"], 2)
        self.assertEqual(report["metrics"]["answers"]["static_pass_count"], 1)
        self.assertEqual(report["metrics"]["answers"]["teacher_judged_count"], 1)
        self.assertEqual(report["rollouts"][1]["score_source"], "teacher")
        self.assertEqual(report["metrics"]["tokens"]["total_tokens"], 14)
        self.assertEqual(report["metrics"]["tokens"]["student_total_tokens"], 14)

    def test_reports_hook_model_tokens_separately(self) -> None:
        """Verifies the reports hook model tokens separately contract."""
        record = _record("one", "answer", "answer")
        record["run"]["trace"].append(
            {
                "event_type": "hook_model_output",
                "payload": {
                    "metadata": {
                        "usage": {
                            "prompt_tokens": 5,
                            "completion_tokens": 2,
                            "total_tokens": 7,
                        }
                    }
                },
            }
        )
        with TemporaryDirectory() as tmpdir:
            input_file = Path(tmpdir) / "rollouts.jsonl"
            input_file.write_text(json.dumps(record) + "\n", encoding="utf-8")
            report = evaluate_rollout_file(
                input_file,
                HotpotQAEvaluator(),
                show_progress=False,
            )

        tokens = report["metrics"]["tokens"]
        self.assertEqual(tokens["total_tokens"], 14)
        self.assertEqual(tokens["student_total_tokens"], 7)
        self.assertEqual(tokens["hook_total_tokens"], 7)

    def test_writes_summary_and_per_example_records(self) -> None:
        """Verifies the writes summary and per example records contract."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_file = root / "rollouts.jsonl"
            input_file.write_text(
                json.dumps(_record("one", "answer", "answer")) + "\n",
                encoding="utf-8",
            )
            report = evaluate_rollout_file(
                input_file,
                HotpotQAEvaluator(),
                show_progress=False,
            )
            output_dir = root / "report"

            write_evaluation_report(report, output_dir)

            summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
            items = (output_dir / "per_example.jsonl").read_text(encoding="utf-8").splitlines()
            rollouts = (output_dir / "per_rollout.jsonl").read_text(encoding="utf-8").splitlines()
            markdown_exists = (output_dir / "summary.md").exists()

        self.assertEqual(summary["metrics"]["answers"]["accuracy"], 1.0)
        self.assertEqual(len(items), 1)
        self.assertEqual(len(rollouts), 1)
        self.assertTrue(markdown_exists)

    def test_aggregates_replicates_into_question_stability(self) -> None:
        """验证单次判定按 example_id 聚合为稳定性与 replicate 目录。"""

        records = [
            _record("one", "answer", prediction)
            for prediction in ("answer", "wrong", "answer")
        ]
        for index, record in enumerate(records):
            record["replicate"] = {
                "replicate_id": f"r{index:03d}",
                "index": index,
                "sampling_seed": 42 + index,
            }
        with TemporaryDirectory() as tmpdir:
            input_file = Path(tmpdir) / "rollouts.jsonl"
            input_file.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )
            report = evaluate_rollout_file(
                input_file, _ExactBinaryEvaluator(), show_progress=False
            )

        item = report["items"][0]
        self.assertEqual(item["stability"], "unstable")
        self.assertAlmostEqual(item["success_rate"], 2 / 3)
        self.assertEqual(item["failed_replicate_ids"], ["r001"])
        self.assertEqual(len(item["replicates"]), 3)
        self.assertEqual(report["metrics"]["answers"]["unstable_rate"], 1.0)

    def test_copies_shared_rollout_provenance_to_report(self) -> None:
        """Verifies the copies shared rollout provenance to report contract."""
        record = _record("one", "answer", "answer")
        record["provenance"] = {"model": {"model_id": "test", "seed": 3}}
        with TemporaryDirectory() as tmpdir:
            input_file = Path(tmpdir) / "rollouts.jsonl"
            input_file.write_text(json.dumps(record) + "\n", encoding="utf-8")
            report = evaluate_rollout_file(
                input_file,
                HotpotQAEvaluator(),
                show_progress=False,
            )

        self.assertEqual(report["provenance"]["model"]["seed"], 3)

    def test_aggregates_runner_errors_without_execution_state(self) -> None:
        """验证 runner error 记录可参与汇总而不会中断整批评估。"""
        record = _record("one", "answer", "")
        record["run"] = None
        record["runner_error"] = {"type": "KeyError", "message": "missing state"}
        with TemporaryDirectory() as tmpdir:
            input_file = Path(tmpdir) / "rollouts.jsonl"
            input_file.write_text(json.dumps(record) + "\n", encoding="utf-8")
            report = evaluate_rollout_file(
                input_file,
                HotpotQAEvaluator(),
                show_progress=False,
            )

        execution = report["metrics"]["execution"]
        self.assertEqual(execution["status_counts"], {"runner_error": 1})
        self.assertEqual(execution["mean_duplicate_queries"], 0)

    def test_parallel_teacher_judging_preserves_item_order(self) -> None:
        """验证 Teacher 并发使用线程独立实例并保持报告顺序。"""

        tracker = _JudgeTracker()
        with TemporaryDirectory() as tmpdir:
            input_file = Path(tmpdir) / "rollouts.jsonl"
            input_file.write_text(
                "\n".join(
                    json.dumps(_record(str(index), "gold", "prediction"))
                    for index in range(6)
                )
                + "\n",
                encoding="utf-8",
            )
            report = evaluate_rollout_file(
                input_file,
                _NeedsTeacherEvaluator(),
                teacher_judge_factory=lambda: _TrackingJudge(tracker),
                judge_workers=4,
                show_progress=False,
            )

        self.assertEqual(
            [item["example_id"] for item in report["items"]],
            [str(index) for index in range(6)],
        )
        self.assertTrue(all(item["score"] == 1 for item in report["items"]))
        self.assertGreater(tracker.peak, 1)
        self.assertLessEqual(tracker.peak, 4)
        self.assertGreater(tracker.instances, 1)
        self.assertEqual(report["evaluation_config"]["judge_workers"], 4)

    def test_parallel_judging_rejects_one_shared_judge(self) -> None:
        """验证并发 Teacher 不能复用带可变响应状态的 Judge。"""

        with TemporaryDirectory() as tmpdir:
            input_file = Path(tmpdir) / "rollouts.jsonl"
            input_file.write_text(
                json.dumps(_record("one", "gold", "prediction")) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "teacher_judge_factory"):
                evaluate_rollout_file(
                    input_file,
                    _NeedsTeacherEvaluator(),
                    teacher_judge=_Judge(),
                    judge_workers=2,
                    show_progress=False,
                )


def _record(example_id: str, golden: str, prediction: str) -> dict[str, object]:
    return {
        "example": {
            "example_id": example_id,
            "question": "Who wrote it?",
            "answer": golden,
        },
        "run": {
            "answer": prediction,
            "status": "completed",
            "state": {
                "step": 2,
                "model_outputs": ["one", "two"],
                "tool_interactions": [
                    {
                        "tool_call": {"arguments": {"query": "author"}},
                        "tool_result": {"metadata": {}},
                    }
                ],
            },
            "trace": [
                {
                    "event_type": "model_output",
                    "payload": {
                        "metadata": {
                            "usage": {
                                "prompt_tokens": 3,
                                "completion_tokens": 4,
                                "total_tokens": 7,
                            }
                        }
                    },
                }
            ],
        },
    }


class _NeedsTeacherEvaluator:
    task_name = "needs_teacher"

    def evaluate_static(self, case) -> StaticEvaluation:
        del case
        return StaticEvaluation(decision=StaticDecision.NEEDS_TEACHER)

    def build_teacher_prompt(self, case) -> str:
        return case.example_id


class _ExactBinaryEvaluator:
    task_name = "exact_binary"

    def evaluate_static(self, case) -> StaticEvaluation:
        decision = (
            StaticDecision.PASS
            if case.predicted_answer == case.golden_answer
            else StaticDecision.AUTOMATIC_ZERO
        )
        return StaticEvaluation(decision=decision)

    def build_teacher_prompt(self, case) -> str:
        return case.example_id


class _JudgeTracker:
    def __init__(self) -> None:
        self.lock = Lock()
        self.active = 0
        self.peak = 0
        self.instances = 0


class _TrackingJudge:
    def __init__(self, tracker: _JudgeTracker) -> None:
        self.tracker = tracker
        with tracker.lock:
            tracker.instances += 1

    def judge(self, case) -> TeacherJudgment:
        with self.tracker.lock:
            self.tracker.active += 1
            self.tracker.peak = max(self.tracker.peak, self.tracker.active)
        time.sleep((7 - int(case.example_id)) * 0.005)
        with self.tracker.lock:
            self.tracker.active -= 1
        return TeacherJudgment(score=1, raw_output='{"score": 1}')
