from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from search_harness.adapter.intervention import (
    InterventionCoordinatorConfig,
    InterventionCoordinatorContext,
    InterventionCoordinatorRunner,
)
from search_harness.core import ModelInput
from search_harness.paths import INTERVENTION_COORDINATOR_TEMPLATE_ROOT

from .test_prefix import _rollout_record, _write_rollout


PROBLEM_DIRECTION = {
    "problem": "Actor stops before retrieving a requested attribute.",
    "observed_pattern": "Repeated incomplete answers after entity discovery.",
    "excluded_causes": ["retriever outage"],
    "desired_behavior": "Continue until each requested attribute has evidence.",
    "success_criteria": ["Improved resolved scores across distinct cases"],
    "constraints": ["Avoid unconditional extra searches"],
}


@dataclass
class SequenceModel:
    outputs: list[str]

    def __post_init__(self) -> None:
        self.inputs: list[ModelInput] = []

    def generate(self, model_input: ModelInput) -> str:
        self.inputs.append(model_input)
        if not self.outputs:
            raise AssertionError("coordinator model received too many calls")
        return self.outputs.pop(0)


class FakeWorkerRunner:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def run(self, **arguments: object) -> dict[str, object]:
        self.calls.append(dict(arguments))
        return {
            "artifact_file": "worker-trial/intervention.json",
            "comparison": {
                "source": {"static": {"decision": "needs_teacher"}},
                "branch": {"static": {"decision": "pass"}},
                "exact_match_delta": 1,
            },
            "worker_summary": "The context rewrite corrected this case.",
            "intervention_changes": [
                {"action": {"kind": "replace_model_input"}}
            ],
        }


class FailingWorkerRunner:
    def run(self, **arguments: object) -> dict[str, object]:
        del arguments
        raise TimeoutError("teacher request timed out")


class InterventionCoordinatorTest(TestCase):
    def test_coordinates_one_worker_trial_and_persists_ledger(self) -> None:
        """验证 Coordinator 可检查案例、委托 Worker 并选择账本中的方案。"""

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            rollout_file = root / "rollout.jsonl"
            _write_rollout(rollout_file)
            coordinator_model = SequenceModel(
                outputs=[
                    '<tool_call>{"name":"inspect_intervention_case",'
                    '"arguments":{"example_id":"example-1",'
                    '"replicate_id":"r000"}}</tool_call>',
                    '<tool_call>{"name":"run_worker_trial","arguments":{'
                    '"example_id":"example-1","replicate_id":"r000",'
                    '"intent":"Force evidence verification.",'
                    '"prefix_id":5,'
                    '"hook_phases":["post_tool","pre_final"],'
                    '"hook_instructions":["Rewrite the context.",'
                    '"Reject unsupported answers."]}}</tool_call>',
                    '<final_answer>{"analysis":"The trial corrected this case.",'
                    '"verdict":"supported",'
                    '"selected_trial_id":"trial_001",'
                    '"recommendation":"Test this scheme on more intersection questions."}'
                    "</final_answer>",
                ]
            )
            worker = FakeWorkerRunner()
            runner = InterventionCoordinatorRunner(
                InterventionCoordinatorConfig(
                    plugins_root=INTERVENTION_COORDINATOR_TEMPLATE_ROOT,
                    output_root=root / "coordinator-runs",
                    max_steps=5,
                    max_trials=2,
                ),
                coordinator_model=coordinator_model,
                worker_runner=worker,
            )

            artifact = runner.run(
                rollout_file=rollout_file,
                example_id="example-1",
                problem_direction=PROBLEM_DIRECTION,
            )
            persisted = json.loads(
                Path(artifact["artifact_file"]).read_text(encoding="utf-8")
            )

        self.assertEqual(len(worker.calls), 1)
        self.assertEqual(
            worker.calls[0]["hook_guidance"],
            {
                "post_tool": "Rewrite the context.",
                "pre_final": "Reject unsupported answers.",
            },
        )
        self.assertEqual(artifact["coordinator_result"]["selected_trial_id"], "trial_001")
        self.assertEqual(artifact["trials"][0]["trial_id"], "trial_001")
        self.assertEqual(artifact["trials"][0]["prefix_id"], 5)
        self.assertEqual(
            artifact["trials"][0]["resolved_boundary"],
            {"step": 1, "phase": "post_tool", "event_index": 6},
        )
        self.assertEqual(persisted["trials"], artifact["trials"])
        inspected = coordinator_model.inputs[1].messages[-1].content
        self.assertIn('"trace_summary"', inspected)
        self.assertIn('"prefix_timeline"', inspected)
        self.assertNotIn('"source_run"', inspected)
        self.assertNotIn("J. R. R. Tolkien", inspected)

    def test_context_rejects_misaligned_hook_arrays_and_trial_overflow(self) -> None:
        """验证 Hook 组合按位置配对，且 Coordinator 不能越过 trial 预算。"""

        with TemporaryDirectory() as tmpdir:
            rollout_file = Path(tmpdir) / "rollout.jsonl"
            _write_rollout(rollout_file)
            worker = FakeWorkerRunner()
            context = InterventionCoordinatorContext(
                rollout_file=rollout_file,
                example_id="example-1",
                report_dir=None,
                worker_runner=worker,
                max_trials=1,
                problem_direction=PROBLEM_DIRECTION,
            )

            with self.assertRaisesRegex(ValueError, "equal length"):
                context.run_worker_trial(
                    example_id="example-1",
                    replicate_id="r000",
                    intent="bad plan",
                    prefix_id=5,
                    hook_phases=["post_tool"],
                    hook_instructions=[],
                )
            context.run_worker_trial(
                example_id="example-1",
                replicate_id="r000",
                intent="valid plan",
                prefix_id=5,
                hook_phases=["post_tool"],
                hook_instructions=["Rewrite context."],
            )
            with self.assertRaisesRegex(RuntimeError, "budget exhausted"):
                context.run_worker_trial(
                    example_id="example-1",
                    replicate_id="r000",
                    intent="second plan",
                    prefix_id=5,
                    hook_phases=["post_tool"],
                    hook_instructions=["Try again."],
                )

    def test_worker_failure_becomes_observable_trial_result(self) -> None:
        """验证单个 Worker 失败进入账本而不终止 Coordinator 的推理循环。"""

        with TemporaryDirectory() as tmpdir:
            rollout_file = Path(tmpdir) / "rollout.jsonl"
            _write_rollout(rollout_file)
            context = InterventionCoordinatorContext(
                rollout_file=rollout_file,
                example_id="example-1",
                report_dir=None,
                worker_runner=FailingWorkerRunner(),
                max_trials=2,
                problem_direction=PROBLEM_DIRECTION,
            )

            result = context.run_worker_trial(
                example_id="example-1",
                replicate_id="r000",
                intent="test a fragile scheme",
                prefix_id=5,
                hook_phases=["post_tool"],
                hook_instructions=["Rewrite context."],
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"], "TimeoutError: teacher request timed out")
        self.assertEqual(context.trials[0]["trial_id"], "trial_001")

    def test_rejects_unknown_prefix_before_starting_worker(self) -> None:
        """验证无效目录序号在 Worker 启动前被拒绝且不写入 trial 账本。"""

        with TemporaryDirectory() as tmpdir:
            rollout_file = Path(tmpdir) / "rollout.jsonl"
            _write_rollout(rollout_file)
            worker = FakeWorkerRunner()
            context = InterventionCoordinatorContext(
                rollout_file=rollout_file,
                example_id="example-1",
                report_dir=None,
                worker_runner=worker,
                max_trials=2,
                problem_direction=PROBLEM_DIRECTION,
            )

            with self.assertRaisesRegex(ValueError, "available range"):
                context.run_worker_trial(
                    example_id="example-1",
                    replicate_id="r000",
                    intent="invalid boundary",
                    prefix_id=99,
                    hook_phases=["post_tool"],
                    hook_instructions=["Rewrite context."],
                )

        self.assertEqual(worker.calls, [])
        self.assertEqual(context.trials, ())

    def test_lists_and_seed_samples_from_evaluation_failure_pool(self) -> None:
        """验证 Coordinator 可分页查看并可复现选择失败样本且不暴露 golden。"""

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            rollout_file = root / "rollout.jsonl"
            report_dir = root / "evaluation"
            _write_pool_rollout(rollout_file)
            _write_report(report_dir, rollout_file)
            coordinator_model = SequenceModel(
                outputs=[
                    '<tool_call>{"name":"list_failed_cases","arguments":{'
                    '"page":1,"page_size":10}}</tool_call>',
                    '<tool_call>{"name":"sample_failed_case","arguments":{'
                    '"seed":17}}</tool_call>',
                    '<tool_call>{"name":"inspect_intervention_case",'
                    '"arguments":{"example_id":"example-2",'
                    '"replicate_id":"r000"}}</tool_call>',
                    '<final_answer>{"analysis":"One failed case was selected.",'
                    '"verdict":"inconclusive",'
                    '"selected_trial_id":null,'
                    '"recommendation":"Prepare a trial next."}</final_answer>',
                ]
            )
            artifact = InterventionCoordinatorRunner(
                InterventionCoordinatorConfig(
                    plugins_root=INTERVENTION_COORDINATOR_TEMPLATE_ROOT,
                    output_root=root / "coordinator-runs",
                    max_steps=5,
                    max_trials=2,
                ),
                coordinator_model=coordinator_model,
                worker_runner=FakeWorkerRunner(),
            ).run(report_dir=report_dir, problem_direction=PROBLEM_DIRECTION)
            sampling_context = InterventionCoordinatorContext(
                rollout_file=rollout_file,
                example_id=None,
                report_dir=report_dir,
                worker_runner=FakeWorkerRunner(),
                max_trials=1,
                problem_direction=PROBLEM_DIRECTION,
            )
            first_sample = sampling_context.sample_failed_case(seed=17)
            second_sample = sampling_context.sample_failed_case(seed=17)

        list_result = coordinator_model.inputs[1].messages[-1].content
        sample_result = coordinator_model.inputs[2].messages[-1].content
        self.assertIn('"total_items": 2', list_result)
        self.assertIn('"example_id":', sample_result)
        self.assertNotIn("J. R. R. Tolkien", list_result)
        self.assertIn(artifact["source"]["example_id"], {"example-1", "example-2"})
        self.assertEqual(artifact["source"]["failed_case_count"], 2)
        self.assertEqual(first_sample["example_id"], second_sample["example_id"])

    def test_compiler_feedback_requires_new_positive_trial_before_support(self) -> None:
        """验证 PRE_FINAL 阻止 Coordinator 无新增证据地重提 supported。"""

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            rollout_file = root / "rollout.jsonl"
            report_dir = root / "evaluation"
            _write_pool_rollout(rollout_file)
            _write_report(report_dir, rollout_file)
            previous_log = root / "previous-coordinator.json"
            previous_log.write_text(
                json.dumps(
                    {
                        "trials": [
                            _positive_trial("trial_001", "example-1"),
                            _positive_trial("trial_002", "example-2"),
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            coordinator_model = SequenceModel(
                outputs=[
                    '<final_answer>{"analysis":"The old trials still pass.",'
                    '"verdict":"supported","selected_trial_id":"trial_001",'
                    '"recommendation":"Compile the previous mechanism."}</final_answer>',
                    '<final_answer>{"analysis":"No new generic trial was run.",'
                    '"verdict":"inconclusive","selected_trial_id":null,'
                    '"recommendation":"Run the Compiler-requested generic trial."}'
                    "</final_answer>",
                ]
            )
            artifact = InterventionCoordinatorRunner(
                InterventionCoordinatorConfig(
                    plugins_root=INTERVENTION_COORDINATOR_TEMPLATE_ROOT,
                    output_root=root / "coordinator-runs",
                    max_steps=3,
                    max_trials=2,
                ),
                coordinator_model=coordinator_model,
                worker_runner=FakeWorkerRunner(),
            ).run(
                report_dir=report_dir,
                problem_direction=PROBLEM_DIRECTION,
                previous_intervention_log=previous_log,
                compiler_feedback="Test a generic post-tool decision rule.",
            )
            feedback = coordinator_model.inputs[1].messages[-1].content

        self.assertEqual(artifact["coordinator_result"]["verdict"], "inconclusive")
        self.assertEqual(artifact["revision_source"]["prior_trial_count"], 2)
        self.assertEqual(artifact["revision_source"]["new_trial_count"], 0)
        self.assertIn("Compiler requested clarification", feedback)

    def test_malformed_final_is_deferred_with_schema_feedback(self) -> None:
        """验证 PRE_FINAL 将错误 JSON 反馈给 Coordinator 后允许其自我修正。"""

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            rollout_file = root / "rollout.jsonl"
            _write_rollout(rollout_file)
            model = SequenceModel(
                outputs=[
                    '<final_answer>{"analysis":"broken",}</final_answer>',
                    '<final_answer>{"analysis":"Corrected format.",'
                    '"verdict":"inconclusive","selected_trial_id":null,'
                    '"recommendation":"Run a generic trial."}</final_answer>',
                ]
            )

            artifact = InterventionCoordinatorRunner(
                InterventionCoordinatorConfig(
                    plugins_root=INTERVENTION_COORDINATOR_TEMPLATE_ROOT,
                    output_root=root / "coordinator-runs",
                    max_steps=3,
                    max_trials=1,
                ),
                coordinator_model=model,
                worker_runner=FakeWorkerRunner(),
            ).run(
                rollout_file=rollout_file,
                example_id="example-1",
                problem_direction=PROBLEM_DIRECTION,
            )

        self.assertEqual(artifact["coordinator_result"]["verdict"], "inconclusive")
        self.assertEqual(len(model.inputs), 2)
        self.assertIn("required Coordinator JSON schema", model.inputs[1].messages[-1].content)

    def test_incomplete_run_persists_failure_artifact(self) -> None:
        """验证 Coordinator 达到步数上限时仍保存 AgentRun、trial ledger 和错误。"""

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            rollout_file = root / "rollout.jsonl"
            _write_rollout(rollout_file)
            runner = InterventionCoordinatorRunner(
                InterventionCoordinatorConfig(
                    plugins_root=INTERVENTION_COORDINATOR_TEMPLATE_ROOT,
                    output_root=root / "coordinator-runs",
                    max_steps=1,
                    max_trials=1,
                ),
                coordinator_model=SequenceModel(
                    ['<final_answer>{"analysis":"broken",}</final_answer>']
                ),
                worker_runner=FakeWorkerRunner(),
            )

            with self.assertRaisesRegex(RuntimeError, "log written to"):
                runner.run(
                    rollout_file=rollout_file,
                    example_id="example-1",
                    problem_direction=PROBLEM_DIRECTION,
                )
            artifact_file = next((root / "coordinator-runs").glob("*/coordinator.json"))
            persisted = json.loads(artifact_file.read_text(encoding="utf-8"))

        self.assertIsNotNone(persisted["run"])
        self.assertIsNotNone(persisted["result_error"])
        self.assertEqual(persisted["trials"], [])


def _write_pool_rollout(rollout_file: Path) -> None:
    first = _rollout_record()
    second = _rollout_record()
    second["example"]["example_id"] = "example-2"
    second["example"]["question"] = "Who authored The Hobbit?"
    second["run"]["question"] = "Who authored The Hobbit?"
    rollout_file.write_text(
        json.dumps(first, ensure_ascii=False)
        + "\n"
        + json.dumps(second, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )


def _positive_trial(trial_id: str, example_id: str) -> dict[str, object]:
    return {
        "trial_id": trial_id,
        "example_id": example_id,
        "status": "completed",
        "hook_guidance": {"post_tool": "Check whether another relation is missing."},
        "comparison": {"branch": {"score": 1}},
    }


def _write_report(report_dir: Path, rollout_file: Path) -> None:
    report_dir.mkdir(parents=True)
    cases = [
        {
            "example_id": "example-1",
            "question": "Who wrote The Hobbit?",
            "golden_answer": "J. R. R. Tolkien",
            "predicted_answer": "Shakespeare",
            "run_status": "completed",
            "static": {
                "decision": "needs_teacher",
                "metrics": {"exact_match": 0, "token_f1": 0.0},
                "reason": None,
            },
            "teacher": {"score": 0},
            "score": 0,
            "score_source": "teacher",
        },
        {
            "example_id": "passed-example",
            "question": "A passed question",
            "golden_answer": "answer",
            "predicted_answer": "answer",
            "run_status": "completed",
            "static": {
                "decision": "pass",
                "metrics": {"exact_match": 1, "token_f1": 1.0},
                "reason": None,
            },
            "teacher": None,
            "score": 1,
            "score_source": "static",
        },
        {
            "example_id": "example-2",
            "question": "Who authored The Hobbit?",
            "golden_answer": "J. R. R. Tolkien",
            "predicted_answer": "Christopher Marlowe",
            "run_status": "completed",
            "static": {
                "decision": "needs_teacher",
                "metrics": {"exact_match": 0, "token_f1": 0.0},
                "reason": None,
            },
            "teacher": {"score": 0},
            "score": 0,
            "score_source": "teacher",
        },
    ]
    (report_dir / "per_example.jsonl").write_text(
        "".join(json.dumps(case, ensure_ascii=False) + "\n" for case in cases),
        encoding="utf-8",
    )
    (report_dir / "summary.json").write_text(
        json.dumps({"source_file": str(rollout_file)}, ensure_ascii=False),
        encoding="utf-8",
    )
