"""Controller Intervention trial effect tests."""

from __future__ import annotations

import asyncio
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest import IsolatedAsyncioTestCase

from search_harness.evolution.control.intervention_effects import (
    InterventionBatchFailed,
    InterventionEffects,
)
from search_harness.evolution.research.roles.contracts import (
    FailureDirection,
    InterventionHypothesis,
)

from tests.evolution.research.intervention.test_prefix import (
    _rollout_record,
)
from tests.evolution.research.intervention.test_role_runner import _hypothesis


class _RecordingInterventionRoleRunner:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def run(self, **values: Any) -> dict[str, Any]:
        self.calls.append(values)
        artifact = _worker_artifact("executed")
        artifact["input"] = values["role_input"]
        return artifact


class InterventionEffectsTest(IsolatedAsyncioTestCase):
    async def test_selects_prefix_and_executes_frozen_assignment(self) -> None:
        """Selection and execution preserve the registered trial objective."""

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            rollout_file = root / "rollouts.jsonl"
            _write_rollout_pool(
                rollout_file,
                [("example-1", "r000", 1), ("example-1", "r001", 1)],
            )
            runner = _RecordingInterventionRoleRunner()
            effects = InterventionEffects(
                role_runner=runner,  # type: ignore[arg-type]
                worker_template_root=root / "worker",
                student_template_root=root / "student",
                env_file=root / ".env",
                student_max_steps=4,
            )
            hypothesis = InterventionHypothesis.model_validate(
                _hypothesis()
            )
            selected = effects.select_trial(
                failure=FailureDirection(
                    pattern="The Student stops after partial evidence.",
                    applicability="Search trajectories with a missing fact.",
                    caveats=["Prevalence is unknown."],
                    evidence_refs=[
                        "example-1/r000",
                        "example-1/r001",
                    ],
                ),
                hypothesis=hypothesis,
                rollout_file=rollout_file,
                used_assignments=set(),
                assignment_count=0,
                trial_batch_size=1,
                remaining_trial_budget=4,
                remaining_assignment_budget=12,
                prior_obligation="Cover the abandonment case.",
                work_dir=root / "selection",
            )
            assignment = selected.outcome["assignments"][0]
            executed = await effects.execute_trial(
                assignment=assignment,
                hypothesis=hypothesis.model_dump(mode="json"),
                rollout_file=rollout_file,
                work_dir=root / "trial",
            )

        self.assertEqual(assignment["prefix_id"], 5)
        self.assertEqual(
            assignment["trial_objective"],
            " | ".join(
                [
                    hypothesis.evaluation.primary_signal,
                    hypothesis.evaluation.success_condition,
                    hypothesis.evaluation.falsifier,
                    "Cover the abandonment case.",
                ]
            ),
        )
        self.assertEqual(executed.outcome["output"]["result_kind"], "executed")
        intervention = runner.calls[0]["resource_config"].intervention
        self.assertEqual(intervention.rollout_file, rollout_file)
        self.assertEqual(intervention.student_max_steps, 4)

    def test_selects_fresh_examples_before_replicates_in_stable_order(self) -> None:
        """Analyst refs 优先，随后按冻结 rollout 顺序横向覆盖 example。"""

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            rollout_file = root / "rollouts.jsonl"
            _write_rollout_pool(
                rollout_file,
                [
                    ("example-1", "r000", 1),
                    ("example-1", "r001", 1),
                    ("example-2", "r000", 1),
                    ("example-3", "r000", 1),
                ],
            )
            effects = _effects(root)
            selected = effects.select_trial(
                failure=_failure(["example-2/r000", "example-1/r001"]),
                hypothesis=InterventionHypothesis.model_validate(_hypothesis()),
                rollout_file=rollout_file,
                used_assignments=set(),
                assignment_count=0,
                trial_batch_size=3,
                remaining_trial_budget=3,
                remaining_assignment_budget=3,
                prior_obligation=None,
                work_dir=root / "selection",
            )

        identities = [
            (item["example_id"], item["replicate_id"])
            for item in selected.outcome["assignments"]
        ]
        self.assertEqual(
            identities,
            [
                ("example-2", "r000"),
                ("example-1", "r001"),
                ("example-3", "r000"),
            ],
        )
        self.assertEqual(selected.outcome["selection_mode"], "fresh")

    def test_reuse_batch_spreads_new_replicates_across_examples(self) -> None:
        """无 fresh example 时优先为不同既有 example 各取一个新 replicate。"""

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            rollout_file = root / "rollouts.jsonl"
            _write_rollout_pool(
                rollout_file,
                [
                    ("example-1", "r000", 1),
                    ("example-1", "r001", 2),
                    ("example-2", "r000", 1),
                    ("example-2", "r001", 2),
                ],
            )
            selected = _effects(root).select_trial(
                failure=_failure(["example-1/r000", "example-2/r000"]),
                hypothesis=InterventionHypothesis.model_validate(_hypothesis()),
                rollout_file=rollout_file,
                used_assignments={
                    "example-1/r000/5",
                    "example-2/r000/5",
                },
                assignment_count=2,
                trial_batch_size=2,
                remaining_trial_budget=2,
                remaining_assignment_budget=2,
                prior_obligation=None,
                work_dir=root / "selection",
            )

        identities = [
            (item["example_id"], item["replicate_id"])
            for item in selected.outcome["assignments"]
        ]
        self.assertEqual(
            identities,
            [("example-1", "r001"), ("example-2", "r001")],
        )
        self.assertEqual(selected.outcome["selection_mode"], "reuse")

    def test_fresh_plus_replicate_batch_is_reported_as_fresh(self) -> None:
        """只要批次扩展 example coverage，混入 replicate 后仍标记 fresh。"""

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            rollout_file = root / "rollouts.jsonl"
            _write_rollout_pool(
                rollout_file,
                [
                    ("example-new", "r000", 1),
                    ("example-old", "r000", 1),
                    ("example-old", "r001", 1),
                ],
            )
            selected = _effects(root).select_trial(
                failure=_failure(
                    ["example-new/r000", "example-old/r001"]
                ),
                hypothesis=InterventionHypothesis.model_validate(_hypothesis()),
                rollout_file=rollout_file,
                used_assignments={"example-old/r000/5"},
                assignment_count=1,
                trial_batch_size=2,
                remaining_trial_budget=2,
                remaining_assignment_budget=2,
                prior_obligation=None,
                work_dir=root / "selection",
            )

        self.assertEqual(
            [
                (item["example_id"], item["replicate_id"])
                for item in selected.outcome["assignments"]
            ],
            [("example-new", "r000"), ("example-old", "r001")],
        )
        self.assertEqual(selected.outcome["selection_mode"], "fresh")

    def test_prefix_fallback_is_not_mistaken_for_new_replicate(self) -> None:
        """同 replicate 的其他 prefix 仅在新 replicate 阶段之后作为 fallback。"""

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            rollout_file = root / "rollouts.jsonl"
            _write_rollout_pool(
                rollout_file,
                [
                    ("example-1", "r000", 2),
                    ("example-1", "r001", 1),
                    ("example-2", "r000", 1),
                    ("example-2", "r001", 1),
                ],
            )
            selected = _effects(root).select_trial(
                failure=_failure(["example-1/r000", "example-2/r000"]),
                hypothesis=InterventionHypothesis.model_validate(_hypothesis()),
                rollout_file=rollout_file,
                used_assignments={
                    "example-1/r000/5",
                    "example-2/r000/5",
                },
                assignment_count=2,
                trial_batch_size=3,
                remaining_trial_budget=3,
                remaining_assignment_budget=3,
                prior_obligation=None,
                work_dir=root / "selection",
            )

        identities = [
            (item["example_id"], item["replicate_id"])
            for item in selected.outcome["assignments"]
        ]
        self.assertEqual(
            identities[:2],
            [("example-1", "r001"), ("example-2", "r001")],
        )
        self.assertEqual(identities[2], ("example-1", "r000"))
        self.assertEqual(selected.outcome["selection_mode"], "reuse")

    def test_pure_prefix_fallback_is_reported_as_reuse(self) -> None:
        """同 replicate 的剩余 prefix 不扩展 example coverage。"""

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            rollout_file = root / "rollouts.jsonl"
            _write_rollout_pool(
                rollout_file,
                [
                    ("example-1", "r000", 2),
                    ("example-2", "r000", 2),
                ],
            )
            selected = _effects(root).select_trial(
                failure=_failure(["example-1/r000", "example-2/r000"]),
                hypothesis=InterventionHypothesis.model_validate(_hypothesis()),
                rollout_file=rollout_file,
                used_assignments={
                    "example-1/r000/5",
                    "example-2/r000/5",
                },
                assignment_count=2,
                trial_batch_size=1,
                remaining_trial_budget=1,
                remaining_assignment_budget=1,
                prior_obligation=None,
                work_dir=root / "selection",
            )

        self.assertEqual(
            selected.outcome["assignments"][0]["replicate_id"],
            "r000",
        )
        self.assertEqual(selected.outcome["selection_mode"], "reuse")

    def test_batch_size_is_limited_by_both_remaining_budgets(self) -> None:
        """Selector 不得越过 Trial 或 Assignment 的剩余预算。"""

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            rollout_file = root / "rollouts.jsonl"
            _write_rollout_pool(
                rollout_file,
                [(f"example-{index}", "r000", 1) for index in range(1, 5)],
            )
            selected = _effects(root).select_trial(
                failure=_failure(["example-1/r000", "example-2/r000"]),
                hypothesis=InterventionHypothesis.model_validate(_hypothesis()),
                rollout_file=rollout_file,
                used_assignments=set(),
                assignment_count=4,
                trial_batch_size=4,
                remaining_trial_budget=3,
                remaining_assignment_budget=2,
                prior_obligation=None,
                work_dir=root / "selection",
            )

        self.assertEqual(len(selected.outcome["assignments"]), 2)
        self.assertEqual(selected.outcome["assignment_count"], 6)

    def test_same_frozen_state_produces_the_same_batch(self) -> None:
        """相同冻结输入和状态生成完全相同的批次与顺序。"""

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            rollout_file = root / "rollouts.jsonl"
            _write_rollout_pool(
                rollout_file,
                [(f"example-{index}", "r000", 1) for index in range(1, 4)],
            )
            values = {
                "failure": _failure(["example-2/r000", "example-1/r000"]),
                "hypothesis": InterventionHypothesis.model_validate(_hypothesis()),
                "rollout_file": rollout_file,
                "used_assignments": set(),
                "assignment_count": 0,
                "trial_batch_size": 3,
                "remaining_trial_budget": 3,
                "remaining_assignment_budget": 3,
                "prior_obligation": None,
            }
            first = _effects(root).select_trial(
                **values,
                work_dir=root / "first",
            )
            second = _effects(root).select_trial(
                **values,
                work_dir=root / "second",
            )

        self.assertEqual(first.outcome, second.outcome)

    def test_returns_exhausted_after_all_exact_assignments_are_used(self) -> None:
        """完整 Assignment key 已使用后不会重复选择其他身份层级。"""

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            rollout_file = root / "rollouts.jsonl"
            _write_rollout_pool(
                rollout_file,
                [("example-1", "r000", 1), ("example-2", "r000", 1)],
            )
            exhausted = _effects(root).select_trial(
                failure=_failure(["example-1/r000", "example-2/r000"]),
                hypothesis=InterventionHypothesis.model_validate(_hypothesis()),
                rollout_file=rollout_file,
                used_assignments={
                    "example-1/r000/5",
                    "example-2/r000/5",
                },
                assignment_count=2,
                trial_batch_size=2,
                remaining_trial_budget=2,
                remaining_assignment_budget=2,
                prior_obligation=None,
                work_dir=root / "selection",
            )

        self.assertEqual(exhausted.outcome["status"], "exhausted")
        self.assertEqual(exhausted.outcome["assignments"], [])

    async def test_executes_trial_batch_concurrently_and_keeps_input_order(
        self,
    ) -> None:
        """并发完成顺序不改变批次结果和 artifact key 的输入顺序。"""

        class ConcurrentRunner:
            def __init__(self) -> None:
                self.active = 0
                self.max_active = 0
                self.started = 0
                self.all_started = asyncio.Event()

            async def run(self, **values: Any) -> dict[str, Any]:
                self.active += 1
                self.started += 1
                self.max_active = max(self.max_active, self.active)
                if self.started == 3:
                    self.all_started.set()
                await asyncio.wait_for(self.all_started.wait(), timeout=1)
                self.active -= 1
                artifact = _worker_artifact("executed")
                artifact["input"] = values["role_input"]
                return artifact

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            rollout_file = root / "rollouts.jsonl"
            _write_rollout_pool(
                rollout_file,
                [
                    ("example-1", "r000", 1),
                    ("example-2", "r000", 1),
                    ("example-3", "r000", 1),
                ],
            )
            runner = ConcurrentRunner()
            effects = InterventionEffects(
                role_runner=runner,  # type: ignore[arg-type]
                worker_template_root=root / "worker",
                student_template_root=root / "student",
                env_file=root / ".env",
                student_max_steps=4,
            )
            assignments = _assignments(3)
            result = await effects.execute_batch(
                assignments=assignments,
                hypothesis=_hypothesis(),
                rollout_file=rollout_file,
                max_workers=3,
                work_dir=root / "attempt-one",
            )

        self.assertEqual(runner.max_active, 3)
        self.assertEqual(
            [item["assignment_key"] for item in result.outcome["results"]],
            [f"example-{index}/r000/5" for index in range(1, 4)],
        )
        self.assertEqual(
            list(result.artifact_refs),
            [
                "worker_artifact_001",
                "worker_artifact_002",
                "worker_artifact_003",
            ],
        )

    async def test_trial_batch_retry_reuses_completed_checkpoints(self) -> None:
        """并发批次失败后只重跑未形成完整 checkpoint 的 Assignment。"""

        class OneFailure(RuntimeError):
            def __init__(self) -> None:
                super().__init__("transient Intervention failure")
                self.failure_artifact = {"usage": {"total_tokens": 7}}

        class RecoveringRunner:
            def __init__(self) -> None:
                self.calls: list[str] = []
                self.failed = False

            async def run(self, **values: Any) -> dict[str, Any]:
                role_input = values["role_input"]
                example_id = str(role_input["example_id"])
                self.calls.append(example_id)
                if example_id == "example-2" and not self.failed:
                    self.failed = True
                    raise OneFailure()
                artifact = _worker_artifact("executed")
                artifact["input"] = role_input
                return artifact

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            rollout_file = root / "rollouts.jsonl"
            _write_rollout_pool(
                rollout_file,
                [
                    ("example-1", "r000", 1),
                    ("example-2", "r000", 1),
                    ("example-3", "r000", 1),
                ],
            )
            runner = RecoveringRunner()
            effects = InterventionEffects(
                role_runner=runner,  # type: ignore[arg-type]
                worker_template_root=root / "worker",
                student_template_root=root / "student",
                env_file=root / ".env",
                student_max_steps=4,
            )
            values = {
                "assignments": _assignments(3),
                "hypothesis": _hypothesis(),
                "rollout_file": rollout_file,
                "max_workers": 3,
            }
            with self.assertRaises(InterventionBatchFailed) as raised:
                await effects.execute_batch(
                    **values,
                    work_dir=root / "attempt-one",
                )
            result = await effects.execute_batch(
                **values,
                work_dir=root / "attempt-two",
            )

        self.assertEqual(
            raised.exception.failure_artifact["usage"]["total_tokens"],
            7,
        )
        self.assertEqual(
            runner.calls,
            ["example-1", "example-2", "example-3", "example-2"],
        )
        self.assertEqual(len(result.outcome["results"]), 3)


def _effects(root: Path) -> InterventionEffects:
    return InterventionEffects(
        role_runner=_RecordingInterventionRoleRunner(),  # type: ignore[arg-type]
        worker_template_root=root / "worker",
        student_template_root=root / "student",
        env_file=root / ".env",
        student_max_steps=4,
    )


def _failure(evidence_refs: list[str]) -> FailureDirection:
    return FailureDirection(
        pattern="The Student stops after partial evidence.",
        applicability="Search trajectories with a missing fact.",
        caveats=["Prevalence is unknown."],
        evidence_refs=evidence_refs,
    )


def _assignments(count: int) -> list[dict[str, Any]]:
    return [
        {
            "trial_objective": "Observe the frozen primary signal.",
            "example_id": f"example-{index}",
            "replicate_id": "r000",
            "prefix_id": 5,
            "prohibited_content": [],
        }
        for index in range(1, count + 1)
    ]


def _write_rollout_pool(
    path: Path,
    identities: list[tuple[str, str, int]],
) -> None:
    records: list[dict[str, Any]] = []
    for example_id, replicate_id, post_tool_prefix_count in identities:
        record = deepcopy(_rollout_record())
        record["example"]["example_id"] = example_id
        record["replicate"] = {"replicate_id": replicate_id}
        for offset in range(1, post_tool_prefix_count):
            record["run"]["trace"].append(
                {
                    "index": 11 + offset,
                    "step": 2 + offset,
                    "event_type": "tool_result",
                    "payload": {
                        "name": "search",
                        "content": f"extra evidence {offset}",
                        "metadata": {},
                    },
                }
            )
        records.append(record)
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )


def _worker_artifact(result_kind: str) -> dict[str, Any]:
    return {
        "output": {
            "result_kind": result_kind,
            "activated_phases": ["post_tool"],
            "modified_phases": ["post_tool"],
            "unmet_phases": [],
        },
        "resource_artifacts": {
            "intervention_trial": {
                "activation_counts": {"post_tool": 1},
                "context_changes": [],
                "comparison": {
                    "source": {"status": "completed"},
                    "branch": {"status": "completed"},
                },
            }
        },
        "usage": {"total_tokens": 0},
    }
