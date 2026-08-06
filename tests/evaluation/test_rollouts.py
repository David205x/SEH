from __future__ import annotations

import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
from unittest import TestCase

from search_harness.framework import RunResult, AgentState
from search_harness.datasets import DatasetExample
from search_harness.evaluation.rollouts import open_harness_source, run_examples
from search_harness.evolution.versioning import FileEdit, TemplateVersionStore


BASELINE_TEMPLATE_ROOT = (
    Path(__file__).parents[2] / "harness_templates" / "student" / "baseline"
)
_CANDIDATE_HOOK = '''from search_harness.framework import BaseHook, HookPhase

class CandidateHook(BaseHook):
    def __init__(self):
        super().__init__(
            hook_id="candidate_hook",
            phases=frozenset({HookPhase.PRE_PROMPT}),
        )

    def handle(self, context):
        return None

def build(config, context):
    return CandidateHook()
'''


class DatasetRunnerTest(TestCase):
    def test_runs_requested_examples_and_writes_full_jsonl_records(self) -> None:
        """Verify requested examples produce complete JSONL records."""
        examples = [_example("one"), _example("two"), _example("three")]
        questions: list[str] = []

        with TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / "rollouts.jsonl"
            summary = run_examples(
                examples=examples,
                run_agent=lambda seed, question: _RecordingLoop(questions).run(
                    question
                ),
                output_file=output_file,
                limit=2,
                show_progress=False,
                harness_source={"version_id": "harness_v0001"},
                experiment_provenance={"model": {"seed": 17}},
            )
            records = [
                json.loads(line)
                for line in output_file.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(questions, ["question one", "question two"])
        self.assertEqual(summary.processed, 2)
        self.assertEqual(summary.runner_errors, 0)
        self.assertEqual(
            [record["example"]["example_id"] for record in records],
            ["one", "two"],
        )
        self.assertEqual(records[0]["run"]["answer"], "answer for question one")
        self.assertEqual(records[0]["harness"]["version_id"], "harness_v0001")
        self.assertEqual(records[0]["provenance"]["model"]["seed"], 17)
        self.assertIn("trace", records[0]["run"])

    def test_records_runner_error_and_continues_by_default(self) -> None:
        """Verifies the records runner error and continues by default contract."""
        examples = [_example("one"), _example("two")]
        attempts = 0

        def run_agent(seed: int | None, question: str) -> RunResult:
            del seed
            nonlocal attempts
            attempts += 1
            return _RecordingLoop([], fail=attempts == 1).run(question)

        with TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / "rollouts.jsonl"
            summary = run_examples(
                examples=examples,
                run_agent=run_agent,
                output_file=output_file,
                limit=2,
                show_progress=False,
            )
            records = [
                json.loads(line)
                for line in output_file.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(summary.processed, 2)
        self.assertEqual(summary.runner_errors, 1)
        self.assertEqual(records[0]["runner_error"]["type"], "RuntimeError")
        self.assertEqual(records[1]["run"]["answer"], "answer for question two")

    def test_stops_after_consecutive_identical_runner_errors(self) -> None:
        """验证候选批次遇到连续同类 runner error 时提前止损。"""

        examples = [_example(str(index)) for index in range(10)]

        with TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / "rollouts.jsonl"
            summary = run_examples(
                examples=examples,
                run_agent=lambda seed, question: _RecordingLoop(
                    [], fail=True
                ).run(question),
                output_file=output_file,
                limit=len(examples),
                show_progress=False,
                max_consecutive_identical_errors=3,
            )
            records = [
                json.loads(line)
                for line in output_file.read_text(
                    encoding="utf-8"
                ).splitlines()
            ]

        self.assertEqual(summary.processed, 3)
        self.assertEqual(summary.runner_errors, 3)
        self.assertTrue(summary.stopped_early)
        self.assertIn(
            "consecutive identical runner error limit reached",
            summary.stop_reason or "",
        )
        self.assertEqual(len(records), 3)

    def test_success_resets_consecutive_runner_error_streak(self) -> None:
        """验证成功 rollout 会重置同类错误连续计数。"""

        attempts = 0

        def run_agent(seed: int | None, question: str) -> RunResult:
            del seed
            nonlocal attempts
            attempts += 1
            return _RecordingLoop(
                [], fail=attempts in {1, 2, 4, 5}
            ).run(question)

        with TemporaryDirectory() as tmpdir:
            summary = run_examples(
                examples=[_example(str(index)) for index in range(5)],
                run_agent=run_agent,
                output_file=Path(tmpdir) / "rollouts.jsonl",
                limit=5,
                show_progress=False,
                max_consecutive_identical_errors=3,
            )

        self.assertEqual(summary.processed, 5)
        self.assertEqual(summary.runner_errors, 4)
        self.assertFalse(summary.stopped_early)

    def test_parallel_rollouts_preserve_dataset_order_and_worker_bound(self) -> None:
        """验证并发 rollout 有界执行且 JSONL 保持数据集顺序。"""

        examples = [_example(str(index)) for index in range(6)]
        lock = Lock()
        active = 0
        peak = 0

        class DelayedLoop:
            def run(self, question: str) -> RunResult:
                nonlocal active, peak
                with lock:
                    active += 1
                    peak = max(peak, active)
                time.sleep((7 - int(question.rsplit(" ", 1)[1])) * 0.005)
                with lock:
                    active -= 1
                state = AgentState(question=question, max_steps=1)
                state.finish_completed(f"answer for {question}")
                return RunResult(state=state, trace=())

        with TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / "rollouts.jsonl"
            summary = run_examples(
                examples=examples,
                run_agent=lambda seed, question: DelayedLoop().run(question),
                output_file=output_file,
                limit=len(examples),
                show_progress=False,
                max_workers=2,
            )
            records = [
                json.loads(line)
                for line in output_file.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(summary.processed, 6)
        self.assertEqual(
            [record["example"]["example_id"] for record in records],
            [str(index) for index in range(6)],
        )
        self.assertEqual(peak, 2)

    def test_repeats_with_ordered_replicates_and_derived_seeds(self) -> None:
        """验证 N 次 rollout 保持复合身份、顺序和可复现 seed 计划。"""

        seen_seeds: list[int | None] = []

        def run_agent(seed: int | None, question: str) -> RunResult:
            seen_seeds.append(seed)
            return _RecordingLoop([]).run(question)

        with TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / "rollouts.jsonl"
            summary = run_examples(
                examples=[_example("one"), _example("two")],
                run_agent=run_agent,
                output_file=output_file,
                limit=2,
                show_progress=False,
                rollouts_per_example=3,
                base_seed=42,
                max_workers=2,
            )
            records = [
                json.loads(line)
                for line in output_file.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(summary.processed, 6)
        self.assertEqual(summary.requested_rollouts, 6)
        self.assertEqual(
            [
                (record["example"]["example_id"], record["replicate"]["replicate_id"])
                for record in records
            ],
            [
                ("one", "r000"),
                ("one", "r001"),
                ("one", "r002"),
                ("two", "r000"),
                ("two", "r001"),
                ("two", "r002"),
            ],
        )
        self.assertCountEqual(seen_seeds, [42, 43, 44, 42, 43, 44])

    def test_stages_validated_candidate_attempt_for_full_context(self) -> None:
        """Verify a validated Candidate Attempt stays staged for the context."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            env_file = root / ".env"
            env_file.write_text(
                "RETRIEVER_URL=http://example.test/retrieve\n",
                encoding="utf-8",
            )
            store_root = root / "versions"
            store = TemplateVersionStore(store_root)
            store.initialize(BASELINE_TEMPLATE_ROOT, env_file=env_file)
            attempt = store.start_candidate_attempt()
            attempt.add_extension(
                instance_id="candidate_hook",
                files={"component.py": _CANDIDATE_HOOK},
            )
            candidate_path = "extensions/candidate_hook/component.py"
            source = attempt.read_text(candidate_path)
            attempt.apply_patch(
                (FileEdit("write", candidate_path, f"{source}\n# candidate marker\n"),)
            )

            with open_harness_source(
                version_store=store_root,
                candidate_attempt_id=attempt.candidate_attempt_id,
                env_file=env_file,
            ) as (template_root, harness_source):
                staged_root = template_root
                staged_source = (template_root / candidate_path).read_text(
                    encoding="utf-8"
                )
                self.assertIn("# candidate marker", staged_source)
                self.assertEqual(
                    harness_source.source_type,
                    "pending_candidate_attempt",
                )
                self.assertEqual(
                    harness_source.candidate_attempt_id,
                    attempt.candidate_attempt_id,
                )
                self.assertEqual(harness_source.candidate_digest, attempt.digest)
                self.assertTrue(template_root.exists())

            self.assertFalse(staged_root.exists())
            events = store.get_candidate_attempt_events(attempt.candidate_attempt_id)
            self.assertEqual(events[-1].event_type, "validation_completed")
            self.assertTrue(events[-1].payload["passed"])


class _RecordingLoop:
    def __init__(self, questions: list[str], fail: bool = False) -> None:
        self.questions = questions
        self.fail = fail

    def run(self, question: str) -> RunResult:
        self.questions.append(question)
        if self.fail:
            raise RuntimeError("model unavailable")
        state = AgentState(question=question, max_steps=1)
        state.finish_completed(f"answer for {question}")
        return RunResult(state=state, trace=())


def _example(example_id: str) -> DatasetExample:
    return DatasetExample(example_id=example_id, question=f"question {example_id}")
