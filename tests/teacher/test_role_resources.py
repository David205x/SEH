"""剩余三个 Teacher v2 角色的受控资源测试。"""

from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from search_harness.teacher.contracts import (
    InterventionHypothesis,
    InterventionWorkerInput,
)
from search_harness.teacher.role_resources import (
    CandidateComparisonStore,
    CandidateReviewResourceConfig,
    CompilerResourceConfig,
    CompilerWorkspaceStore,
    InterventionBranchStore,
    InterventionResourceConfig,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRATCH_ROOT = (
    PROJECT_ROOT / "runs" / "components" / "teacher" / "_test_scratch"
)
BASELINE_PLUGINS = (
    PROJECT_ROOT / "harness_templates" / "actor" / "baseline" / "plugins"
)


class TeacherRoleResourceTest(unittest.TestCase):
    def setUp(self) -> None:
        """为资源协议测试创建仓库内、可清理的独立目录。"""

        shutil.rmtree(SCRATCH_ROOT, ignore_errors=True)
        SCRATCH_ROOT.mkdir(parents=True)

    def tearDown(self) -> None:
        """清理测试创建的本地运行产物。"""

        shutil.rmtree(SCRATCH_ROOT, ignore_errors=True)

    def test_worker_binds_prefix_and_persists_student_branch(self) -> None:
        """验证 Worker 绑定恢复点、执行一次动作并保存 Student 分支。"""

        rollout_file = SCRATCH_ROOT / "rollout.jsonl"
        _write_jsonl(rollout_file, [_rollout_record(answer="wrong")])
        store = InterventionBranchStore(
            InterventionResourceConfig(
                rollout_file=rollout_file,
                actor_plugins_root=BASELINE_PLUGINS,
                env_file=PROJECT_ROOT / ".env",
                actor_max_steps=5,
            )
        )
        task = InterventionWorkerInput(
            hypothesis=InterventionHypothesis(
                trigger="A valid search result contains only partial evidence.",
                trigger_phase="post_tool",
                intervention="Ask the Actor to identify the missing relation.",
                predicted_actor_response=(
                    "The Actor continues rather than finalizing."
                ),
                evaluation={
                    "primary_signal": "tool_call_after_intervention",
                    "success_condition": "One additional tool call occurs.",
                    "falsifier": "The Actor immediately finalizes.",
                    "secondary_metrics": ["answer_score"],
                },
                applicability="Search tasks with partial evidence.",
            ),
            trial_objective="Test one generic continuation instruction.",
            example_id="example-1",
            replicate_id="r000",
            prefix_id=5,
            prohibited_content=["golden answer"],
        )
        store.bind(task)

        branch_result = SimpleNamespace(
            to_dict=lambda: {
                "status": "completed",
                "answer": "branch answer",
                "error": None,
                "trace": [],
            }
        )
        loop = SimpleNamespace(run=lambda _question: branch_result)
        with patch(
            "search_harness.teacher.role_resources.AgentLoop",
            return_value=loop,
        ):
            result = store.run_branch(
                action="append_user_message",
                content="Identify the missing relation before answering.",
                rationale="This directly tests evidence-gap recognition.",
            )

        self.assertEqual(result["trial_id"], "trial_001")
        self.assertEqual(store.timeline()["selected_prefix_id"], 5)
        self.assertEqual(
            store.artifact()["student_model"]["role"],
            "student",
        )
        store.validate_result(
            action="append_user_message",
            content="Identify the missing relation before answering.",
            rationale="This directly tests evidence-gap recognition.",
        )

    def test_compiler_requires_validation_before_submission(self) -> None:
        """验证 Compiler 候选只有在当前 revision 校验通过后才能提交。"""

        store = CompilerWorkspaceStore.load(
            CompilerResourceConfig(
                parent_plugins_root=BASELINE_PLUGINS,
                env_file=PROJECT_ROOT / ".env",
            )
        )
        store.write_file(
            path="candidate_note.txt",
            content="candidate transaction marker\n",
        )

        with self.assertRaisesRegex(ValueError, "pass validation"):
            store.submit(summary="Add a candidate marker.")

        validation = store.validate()
        self.assertTrue(validation["passed"], validation["errors"])
        submitted = store.submit(summary="Add a candidate marker.")
        self.assertEqual(submitted["candidate_ref"], "candidate_001")
        self.assertIn(
            "candidate_note.txt",
            store.resolve("candidate_001")["changed_files"],
        )

    def test_compiler_finalizer_returns_compact_transaction_result(self) -> None:
        """验证 finalizer 自动校验提交且仅返回紧凑事务结果。"""

        store = CompilerWorkspaceStore.load(
            CompilerResourceConfig(
                parent_plugins_root=BASELINE_PLUGINS,
                env_file=PROJECT_ROOT / ".env",
            )
        )
        store.write_file(
            path="candidate_note.txt",
            content="candidate transaction marker\n",
        )

        result = store.finalize(summary="Add a candidate marker.")

        self.assertEqual(result["status"], "submitted")
        self.assertEqual(result["candidate_ref"], "candidate_001")
        self.assertTrue(result["validation_passed"])
        self.assertNotIn("diff", result)
        self.assertIsNotNone(store.artifact())

    def test_compiler_finalizer_reports_authoring_policy_errors(self) -> None:
        """验证 finalizer 将 Compiler 专属代码缺陷返回给模型修复。"""

        store = CompilerWorkspaceStore.load(
            CompilerResourceConfig(
                parent_plugins_root=BASELINE_PLUGINS,
                env_file=PROJECT_ROOT / ".env",
            )
        )
        store.write_file(
            path="invalid_factory.py",
            content=(
                "def build(config, context):\n"
                "    del config\n"
                "    del context\n"
                "    try:\n"
                "        return object()\n"
                "    except Exception:\n"
                "        return None\n"
            ),
        )

        result = store.finalize(summary="Add an invalid factory.")

        self.assertEqual(result["status"], "repair_required")
        self.assertGreaterEqual(len(result["errors"]), 3)
        self.assertIsNone(store.artifact())

    def test_compiler_exact_api_query_enforces_packet_and_budget(self) -> None:
        """验证 exact query 拒绝 packet 重复并硬限制四个唯一符号。"""

        store = CompilerWorkspaceStore.load(
            CompilerResourceConfig(
                parent_plugins_root=BASELINE_PLUGINS,
                env_file=PROJECT_ROOT / ".env",
            )
        )
        store.bind_capability_packet(
            {
                "contracts": [
                    {
                        "symbol": "HookContext",
                        "fields": [
                            {"symbol": "HookContext.trace"},
                        ],
                    }
                ]
            }
        )

        packet_hit = store.query_hook_api("HookContext.trace")
        first = store.query_hook_api("ToolResult")
        duplicate = store.query_hook_api("ToolResult")
        unknown = store.query_hook_api("MissingPublicSymbol")
        third = store.query_hook_api("TraceEvent")
        fourth = store.query_hook_api("ParsedOutput")
        exhausted = store.query_hook_api("ChatMessage")

        self.assertEqual(packet_hit["reason"], "already_in_packet")
        self.assertNotIn("contract", packet_hit)
        self.assertEqual(first["status"], "resolved")
        self.assertIn("contract", first)
        self.assertEqual(duplicate["reason"], "already_queried")
        self.assertNotIn("contract", duplicate)
        self.assertEqual(unknown["reason"], "unknown_symbol")
        self.assertNotIn("contract", unknown)
        self.assertEqual(third["status"], "resolved")
        self.assertEqual(fourth["status"], "resolved")
        self.assertEqual(exhausted["reason"], "query_budget_exhausted")
        self.assertNotIn("contract", exhausted)
        self.assertEqual(
            store.queried_symbols,
            {
                "ToolResult",
                "MissingPublicSymbol",
                "TraceEvent",
                "ParsedOutput",
            },
        )

    def test_compiler_api_query_requires_bound_packet(self) -> None:
        """验证程序遗漏 packet 绑定时 exact query 立即失败。"""

        store = CompilerWorkspaceStore.load(
            CompilerResourceConfig(
                parent_plugins_root=BASELINE_PLUGINS,
                env_file=PROJECT_ROOT / ".env",
            )
        )

        with self.assertRaisesRegex(RuntimeError, "must be bound"):
            store.query_hook_api("TraceEvent")

    def test_candidate_review_pairs_example_and_replicate(self) -> None:
        """验证 Reviewer 按相同 example/replicate 比较改进与完整轨迹。"""

        incumbent_report, incumbent_rollout = _write_report(
            "incumbent",
            success_rate=0.0,
            answer="wrong",
        )
        candidate_report, candidate_rollout = _write_report(
            "candidate",
            success_rate=1.0,
            answer="right",
        )
        store = CandidateComparisonStore.load(
            CandidateReviewResourceConfig(
                incumbent_report_dir=incumbent_report,
                candidate_report_dir=candidate_report,
                incumbent_rollout_file=incumbent_rollout,
                candidate_rollout_file=candidate_rollout,
            )
        )

        changes = store.list_changes(page=1, page_size=10, change="improved")
        self.assertEqual(changes["total_items"], 1)
        self.assertEqual(changes["items"][0]["example_id"], "example-1")
        self.assertFalse(store.harness_diff()["available"])
        with self.assertRaisesRegex(ValueError, "paired Actor trajectory"):
            store.validate_review()
        paired = store.get_paired_trajectory(
            example_id="example-1",
            replicate_id="r000",
        )
        self.assertEqual(paired["incumbent"]["run"]["answer"], "wrong")
        self.assertEqual(paired["candidate"]["run"]["answer"], "right")
        store.validate_review()


def _write_report(
    name: str,
    *,
    success_rate: float,
    answer: str,
) -> tuple[Path, Path]:
    report_dir = SCRATCH_ROOT / name / "report"
    report_dir.mkdir(parents=True)
    rollout_file = SCRATCH_ROOT / name / "rollout.jsonl"
    _write_jsonl(rollout_file, [_rollout_record(answer=answer)])
    (report_dir / "summary.json").write_text(
        json.dumps(
            {
                "source_file": str(rollout_file.resolve()),
                "metrics": {"answers": {"accuracy": success_rate}},
            }
        ),
        encoding="utf-8",
    )
    _write_jsonl(
        report_dir / "per_example.jsonl",
        [
            {
                "example_id": "example-1",
                "question": "Test question?",
                "success_rate": success_rate,
                "stability": (
                    "stable_correct"
                    if success_rate == 1.0
                    else "stable_failure"
                ),
                "run_status": "completed",
                "replicates": [
                    {
                        "replicate_id": "r000",
                        "score": int(success_rate),
                        "run_status": "completed",
                        "predicted_answer": answer,
                        "runner_error": None,
                        "execution": {},
                    }
                ],
            }
        ],
    )
    return report_dir, rollout_file


def _rollout_record(*, answer: str) -> dict:
    return {
        "example": {
            "example_id": "example-1",
            "question": "Test question?",
        },
        "replicate": {"replicate_id": "r000"},
        "run": {
            "question": "Test question?",
            "status": "completed",
            "answer": answer,
            "error": None,
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
                            '<tool_use>{"name":"search","arguments":'
                            '{"query":"test"}}</tool_use>'
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


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            f"{json.dumps(row, ensure_ascii=False)}\n"
            for row in rows
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
