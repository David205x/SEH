"""Intervention value probe 的信息边界与配对协议测试。"""

from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from experiments.intervention_value_probe import (
    build_review_bundle,
    prepare_worker_brief,
    run_paired_experiment,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRATCH_ROOT = (
    PROJECT_ROOT / "runs" / "components" / "intervention" / "_test_scratch"
)


class InterventionValueProbeTest(unittest.TestCase):
    def setUp(self) -> None:
        """创建仓库内的隔离实验夹具目录。"""

        shutil.rmtree(SCRATCH_ROOT, ignore_errors=True)
        SCRATCH_ROOT.mkdir(parents=True)

    def tearDown(self) -> None:
        """清理测试产生的仓库内临时产物。"""

        shutil.rmtree(SCRATCH_ROOT, ignore_errors=True)

    def test_prepare_omits_golden_answer_from_worker_brief(self) -> None:
        """验证 Worker 只能看到问题、前缀和干预能力，不能看到答案。"""

        rollout_file = SCRATCH_ROOT / "rollout.jsonl"
        _write_jsonl(rollout_file, [_rollout_record()])
        request_file = SCRATCH_ROOT / "request.json"
        _write_json(
            request_file,
            {
                "hypothesis": _hypothesis(),
                "trial_objective": "Test one evidence-gap message.",
                "rollout_file": str(rollout_file),
                "actor_plugins_root": str(
                    PROJECT_ROOT
                    / "harness_templates"
                    / "actor"
                    / "baseline"
                    / "plugins"
                ),
                "env_file": str(PROJECT_ROOT / ".env"),
                "cases": [{"example_id": "example-1", "replicate_id": "r000"}],
            },
        )

        brief_file = prepare_worker_brief(request_file, SCRATCH_ROOT / "prepared")
        brief_text = brief_file.read_text(encoding="utf-8")
        brief = json.loads(brief_text)

        self.assertNotIn("golden_answer", brief_text)
        self.assertNotIn("secret", brief_text)
        self.assertEqual(brief["cases"][0]["boundary"]["phase"], "post_tool")

    def test_run_rejects_worker_plan_with_missing_case(self) -> None:
        """验证 Worker 计划必须与 brief 中的案例身份完整对齐。"""

        brief_file = SCRATCH_ROOT / "brief.json"
        _write_json(
            brief_file,
            {
                "hypothesis": _hypothesis(),
                "trial_objective": "Test one evidence-gap message.",
                "prohibited_content": [],
                "resources": {
                    "rollout_file": "unused.jsonl",
                    "actor_plugins_root": "unused",
                    "env_file": ".env",
                    "actor_max_steps": 4,
                },
                "cases": [
                    {
                        "example_id": "example-1",
                        "replicate_id": "r000",
                        "prefix_id": 5,
                    }
                ],
            },
        )
        plan_file = SCRATCH_ROOT / "plan.json"
        _write_json(
            plan_file,
            {
                "mechanism_summary": "Test a bounded evidence-gap reminder.",
                "trials": [
                    {
                        "example_id": "different-example",
                        "replicate_id": "r000",
                        "action": "append_user_message",
                        "content": "Resolve the remaining visible evidence gap.",
                        "rationale": "Tests whether the Actor continues searching.",
                    }
                ],
            },
        )

        with self.assertRaisesRegex(ValueError, "identities do not match"):
            run_paired_experiment(
                brief_file,
                plan_file,
                SCRATCH_ROOT / "execution",
            )

    def test_review_joins_hidden_answer_after_execution(self) -> None:
        """验证答案和静态评分只在 Reviewer bundle 阶段加入。"""

        experiment_file = SCRATCH_ROOT / "experiment.json"
        _write_json(
            experiment_file,
            {
                "mechanism_summary": "Evidence-gap message.",
                "records": [
                    {
                        "example_id": "example-1",
                        "replicate_id": "r000",
                        "worker_action": {"action": "append_user_message"},
                        "control": {
                            "answer": "wrong",
                            "tool_calls": 1,
                        },
                        "treatment": {
                            "answer": "secret",
                            "tool_calls": 2,
                        },
                        "control_artifact": "control.json",
                        "treatment_artifact": "treatment.json",
                    }
                ],
            },
        )
        report_dir = SCRATCH_ROOT / "report"
        _write_jsonl(
            report_dir / "per_example.jsonl",
            [
                {
                    "example_id": "example-1",
                    "question": "Test question?",
                    "golden_answer": "secret",
                    "success_rate": 0.0,
                }
            ],
        )

        output_file = SCRATCH_ROOT / "review.json"
        build_review_bundle(experiment_file, report_dir, output_file)
        review = json.loads(output_file.read_text(encoding="utf-8"))

        self.assertEqual(review["aggregate"]["control_exact_match"], 0)
        self.assertEqual(review["aggregate"]["treatment_exact_match"], 1)
        self.assertEqual(review["aggregate"]["exact_match_delta"], 1)
        self.assertEqual(
            review["aggregate"]["treatment_mean_continuation_tool_calls"],
            2,
        )

    def test_source_control_retains_original_answer_without_generation(self) -> None:
        """验证 pre-final 试验可直接使用原结果作为零续跑 control。"""

        rollout_file = SCRATCH_ROOT / "rollout.jsonl"
        _write_jsonl(rollout_file, [_rollout_record()])
        brief_file = SCRATCH_ROOT / "brief.json"
        _write_json(
            brief_file,
            {
                "hypothesis": _hypothesis(),
                "trial_objective": "Defer one unsupported answer.",
                "prohibited_content": [],
                "resources": {
                    "rollout_file": str(rollout_file),
                    "actor_plugins_root": str(
                        PROJECT_ROOT
                        / "harness_templates"
                        / "actor"
                        / "baseline"
                        / "plugins"
                    ),
                    "env_file": str(PROJECT_ROOT / ".env"),
                    "actor_max_steps": 4,
                    "control_mode": "source",
                },
                "cases": [
                    {
                        "example_id": "example-1",
                        "replicate_id": "r000",
                        "prefix_id": 5,
                    }
                ],
            },
        )
        plan_file = SCRATCH_ROOT / "plan.json"
        _write_json(
            plan_file,
            {
                "mechanism_summary": "Defer an unsupported final answer once.",
                "trials": [
                    {
                        "example_id": "example-1",
                        "replicate_id": "r000",
                        "action": "append_user_message",
                        "content": "Resolve the remaining evidence gap.",
                        "rationale": "Tests a bounded continuation.",
                    }
                ],
            },
        )
        treatment = {
            "comparison": {
                "branch": {
                    "status": "completed",
                    "answer": "new answer",
                    "error": None,
                    "model_calls": 1,
                    "tool_calls": 1,
                }
            }
        }

        with patch(
            "experiments.intervention_value_probe._run_branch",
            return_value=treatment,
        ):
            experiment_file = run_paired_experiment(
                brief_file,
                plan_file,
                SCRATCH_ROOT / "execution",
            )
        experiment = json.loads(experiment_file.read_text(encoding="utf-8"))
        control = experiment["records"][0]["control"]

        self.assertEqual(control["answer"], "wrong")
        self.assertEqual(control["model_calls"], 0)
        self.assertEqual(control["tool_calls"], 0)


def _hypothesis() -> dict[str, str]:
    return {
        "trigger": "After partial search evidence.",
        "intervention": "Point out the remaining evidence gap.",
        "expected_effect": "The Actor performs another retrieval.",
        "falsifier": "The Actor finalizes without resolving the gap.",
        "applicability": "Multi-hop questions with partial evidence.",
    }


def _rollout_record() -> dict:
    return {
        "example": {
            "example_id": "example-1",
            "question": "Test question?",
            "answer": "secret",
        },
        "replicate": {"replicate_id": "r000"},
        "run": {
            "status": "completed",
            "answer": "wrong",
            "trace": [
                {
                    "index": 1,
                    "step": 1,
                    "event_type": "model_input",
                    "payload": {
                        "messages": [
                            {"role": "system", "content": "Use search."},
                            {"role": "user", "content": "Test question?"},
                        ]
                    },
                },
                {
                    "index": 2,
                    "step": 1,
                    "event_type": "model_output",
                    "payload": {
                        "raw_output": (
                            '<tool_call>{"name":"search","arguments":'
                            '{"query":"test"}}</tool_call>'
                        )
                    },
                },
                {
                    "index": 3,
                    "step": 1,
                    "event_type": "parsed_output",
                    "payload": {"kind": "tool_call"},
                },
                {
                    "index": 4,
                    "step": 1,
                    "event_type": "tool_call",
                    "payload": {
                        "name": "search",
                        "arguments": {"query": "test"},
                    },
                },
                {
                    "index": 5,
                    "step": 1,
                    "event_type": "tool_result",
                    "payload": {
                        "name": "search",
                        "content": "Partial evidence.",
                        "metadata": {},
                    },
                },
            ],
        },
    }


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(f"{json.dumps(row, ensure_ascii=False)}\n" for row in rows),
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
