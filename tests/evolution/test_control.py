"""Formal Evolution Controller state, recovery, and routing tests."""

from __future__ import annotations

import json
import os
import shutil
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from search_harness.evolution.control.controller import EvolutionController
from search_harness.evolution.control.conformance_effects import (
    ConformanceBatchFailed,
    ConformanceEffects,
)
from search_harness.evolution.control.domain import (
    ControlState,
    EffectResult,
    EvolutionControlConfig,
    WorkItem,
    WorkKind,
    project_events,
)
from search_harness.evolution.control.effects import (
    LocalControlEffects,
    LocalControlEffectsConfig,
    _trial_paths,
    _uses_legacy_mechanism_contract,
)
from search_harness.evolution.control.journal import (
    ControlArtifactStore,
    ControlJournal,
)
from search_harness.evolution.control.policies import evaluate_promotion
from search_harness.evolution.control.transitions import (
    transition_completed,
)
from search_harness.evolution.control.evaluation import CandidateArtifact
from search_harness.evolution.research.roles.contracts import MechanismSpec
from search_harness.evolution.versioning import (
    FileEdit,
    TemplateVersionStore,
)


SCRATCH_ROOT = Path("runs/components/controller_tests")


class HappyPathEffects:
    """Return one valid local result for every work kind."""

    def __init__(self) -> None:
        self.calls: list[WorkItem] = []

    async def execute(
        self,
        *,
        work: WorkItem,
        state: ControlState,
        work_dir: Path,
    ) -> EffectResult:
        self.calls.append(work)
        artifact = str((work_dir / "role.json").resolve())
        if work.kind == WorkKind.EVALUATE_INCUMBENT:
            return EffectResult(
                outcome={"metrics": _metrics(accuracy=0.5, tokens=100)},
                artifact_refs={
                    "report_dir": artifact,
                    "rollout_file": artifact,
                },
                usage={"total_tokens": 100},
            )
        if work.kind == WorkKind.ANALYZE_FAILURE:
            return EffectResult(
                outcome={"output": {"pattern": "premature finalization"}},
                artifact_refs={"failure_artifact": artifact},
                usage={"total_tokens": 10},
            )
        if work.kind == WorkKind.RESEARCH_HYPOTHESIS:
            return EffectResult(
                outcome={"output": {"trigger_phase": "pre_final"}},
                artifact_refs={"hypothesis_artifact": artifact},
                usage={"total_tokens": 10},
            )
        if work.kind == WorkKind.SELECT_TRIAL:
            return EffectResult(
                outcome={
                    "status": "selected",
                    "selection_mode": "fresh",
                    "assignments": [
                        {
                            "example_id": "example-1",
                            "replicate_id": "r000",
                            "prefix_id": 1,
                        }
                    ],
                    "assignment_count": 1,
                    "used_assignments": ["example-1/r000/1"],
                }
            )
        if work.kind == WorkKind.EXECUTE_TRIAL:
            return EffectResult(
                outcome={
                    "output": {
                        "result_kind": "executed",
                        "action": "defer_final_answer",
                    }
                },
                artifact_refs={
                    "worker_artifact": artifact,
                },
                usage={"total_tokens": 10},
            )
        if work.kind == WorkKind.REVIEW_EVIDENCE:
            return EffectResult(
                outcome={
                    "output": {
                        "decision": "ready_to_distill",
                        "next_obligation": None,
                    }
                },
                artifact_refs={"reviewer_artifact": artifact},
                usage={"total_tokens": 10},
            )
        if work.kind == WorkKind.DISTILL_MECHANISM:
            return EffectResult(
                outcome={
                    "output": {
                        "decision": "distilled",
                        "mechanism_ref": "mechanism_001",
                    }
                },
                artifact_refs={
                    "distiller_artifact": artifact,
                    "mechanism_file": artifact,
                },
                usage={"total_tokens": 10},
            )
        if work.kind == WorkKind.COMPILE_CANDIDATE:
            return EffectResult(
                outcome={
                    "output": {
                        "decision": "submitted",
                        "implementation_summary": "Add a bounded Hook.",
                    }
                },
                artifact_refs={"compiler_artifact": artifact},
                usage={"total_tokens": 10},
            )
        if work.kind == WorkKind.STAGE_CANDIDATE:
            return EffectResult(
                outcome={
                    "status": "valid",
                    "candidate_attempt_id": "candidate_attempt-1",
                    "candidate_digest": "candidate-digest",
                    "validation": {"passed": True},
                },
            )
        if work.kind == WorkKind.VERIFY_CONFORMANCE:
            return EffectResult(
                outcome={
                    "decision": "pass",
                    "summary": {
                        "decision": "pass",
                        "finding_counts": {"faithful": 3},
                        "per_example": {
                            "example-1": {
                                "faithful_count": 3,
                                "passed": True,
                            }
                        },
                        "compiler_feedback": [],
                        "finding_refs": [],
                    },
                },
                artifact_refs={
                    "conformance_summary_artifact": artifact,
                    "conformance_rollout_file": artifact,
                },
                usage={"total_tokens": 10},
            )
        if work.kind == WorkKind.EVALUATE_CANDIDATE:
            return EffectResult(
                outcome={"metrics": _metrics(accuracy=0.6, tokens=120)},
                artifact_refs={
                    "candidate_report_dir": artifact,
                    "candidate_rollout_file": artifact,
                },
                usage={"total_tokens": 120},
            )
        if work.kind == WorkKind.REVIEW_CANDIDATE:
            return EffectResult(
                outcome={
                    "output": {
                        "recommendation": "accept",
                        "observed_effect": "Accuracy improved.",
                        "reason": "The mechanism is supported.",
                        "next_obligation": None,
                        "revision_target": None,
                    }
                },
                artifact_refs={
                    "candidate_reviewer_artifact": artifact,
                },
                usage={"total_tokens": 10},
            )
        if work.kind == WorkKind.PROMOTE_CANDIDATE:
            return EffectResult(
                outcome={
                    "version_id": "harness_v0002",
                    "candidate_attempt_id": "candidate_attempt-1",
                    "candidate_digest": "candidate-digest",
                }
            )
        raise AssertionError(f"unexpected work kind: {work.kind}")


class RecordingProjection:
    """Record commit notifications without interpreting Controller state."""

    def __init__(self, *, fail_first: bool = False) -> None:
        self.calls = 0
        self.fail_first = fail_first

    def update(self) -> None:
        self.calls += 1
        if self.fail_first and self.calls == 1:
            raise RuntimeError("projection unavailable")


class ReviewPipelineRuntime:
    """Return one local trial review followed by one global evidence review."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def run(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        role = kwargs["role_id"]
        if role == "trial_reviewer":
            output = {
                "trial_ref": kwargs["role_input"]["trial_ref"],
                "assessment": "The full trajectory supports the effect.",
            }
        elif role == "evidence_reviewer":
            output = {
                "decision": "ready_to_distill",
                "phase_findings": [
                    {
                        "phase": "post_tool",
                        "status": "supported",
                        "assessment": "The local effect was observed.",
                    }
                ],
                "assessment": "The evidence supports distillation.",
                "key_risk": None,
                "next_obligation": None,
            }
        else:
            raise AssertionError(f"unexpected Teacher role: {role}")
        return {
            "input": kwargs["role_input"],
            "output": output,
            "usage": {"total_tokens": 5},
        }


class LegacyControlArtifactTest(unittest.TestCase):
    def test_legacy_mechanism_requires_redistillation_before_compile(self) -> None:
        self.assertTrue(
            _uses_legacy_mechanism_contract(
                {
                    "phase_rules": [
                        {
                            "phase": "post_tool",
                            "trigger_condition": "Evidence is missing.",
                        }
                    ]
                }
            )
        )
        self.assertFalse(
            _uses_legacy_mechanism_contract(
                {
                    "phase_rules": [
                        {
                            "phase": "post_tool",
                            "decision_contract": {"predicate": "Question?"},
                        }
                    ]
                }
            )
        )

    def test_reads_legacy_attempt_names_without_rewriting_file(self) -> None:
        root = SCRATCH_ROOT / f"legacy-{uuid4().hex}"
        journal_path = root / "events.jsonl"
        artifact_store = ControlArtifactStore(root / "artifacts")
        try:
            journal_path.parent.mkdir(parents=True, exist_ok=True)
            legacy_events = [
                {
                    "sequence": 1,
                    "event_type": "run_started",
                    "payload": {
                        "run_id": "legacy-run",
                        "initial_version": "harness_v0001",
                    },
                    "created_at": "2026-01-01T00:00:00+00:00",
                },
                {
                    "sequence": 2,
                    "event_type": "work_scheduled",
                    "payload": {
                        "work": {
                            "work_id": "legacy-work",
                            "kind": "verify_conformance",
                            "subject_ref": "legacy-subject",
                            "payload": {"iteration_id": "iteration_legacy"},
                        }
                    },
                    "created_at": "2026-01-01T00:00:01+00:00",
                },
            ]
            journal_path.write_text(
                "".join(
                    json.dumps(event, ensure_ascii=False) + "\n"
                    for event in legacy_events
                ),
                encoding="utf-8",
            )
            effect_path = artifact_store.effect_path("legacy-work")
            effect_path.parent.mkdir(parents=True, exist_ok=True)
            effect_path.write_text(
                json.dumps(
                    {
                        "outcome": {"iteration_id": "iteration_legacy"},
                        "artifact_refs": {},
                        "usage": {},
                    }
                ),
                encoding="utf-8",
            )

            events = ControlJournal(journal_path).read()
            effect = artifact_store.load_effect("legacy-work")

            work = events[1].payload["work"]
            self.assertEqual(
                work["payload"]["candidate_attempt_id"],
                "iteration_legacy",
            )
            self.assertEqual(
                effect.outcome["candidate_attempt_id"],
                "iteration_legacy",
            )
            self.assertIn(
                "iteration_id",
                journal_path.read_text(encoding="utf-8"),
            )
        finally:
            if root.exists():
                shutil.rmtree(root)


class EvolutionControllerTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        SCRATCH_ROOT.mkdir(parents=True, exist_ok=True)
        self.run_dir = SCRATCH_ROOT / uuid4().hex

    def tearDown(self) -> None:
        resolved = self.run_dir.resolve()
        scratch = SCRATCH_ROOT.resolve()
        if resolved.parent != scratch:
            raise AssertionError("refusing to clean an unexpected test path")
        if resolved.exists():
            _remove_scratch(resolved)

    async def test_runs_full_agenda_and_advances_version(self) -> None:
        """验证七角色、评估、门禁和晋升按事件议程组成闭环。"""

        effects = HappyPathEffects()
        controller = EvolutionController(
            run_dir=self.run_dir,
            effects=effects,
            config=EvolutionControlConfig(max_generations=1),
        )
        controller.initialize(
            run_id="run-1",
            initial_version="harness_v0001",
        )

        outcome = await controller.run()

        self.assertEqual(outcome.status, "completed")
        self.assertEqual(outcome.current_version, "harness_v0002")
        self.assertEqual(outcome.completed_work_count, 13)
        self.assertEqual(
            [item.kind for item in effects.calls],
            [
                WorkKind.EVALUATE_INCUMBENT,
                WorkKind.ANALYZE_FAILURE,
                WorkKind.RESEARCH_HYPOTHESIS,
                WorkKind.SELECT_TRIAL,
                WorkKind.EXECUTE_TRIAL,
                WorkKind.REVIEW_EVIDENCE,
                WorkKind.DISTILL_MECHANISM,
                WorkKind.COMPILE_CANDIDATE,
                WorkKind.STAGE_CANDIDATE,
                WorkKind.VERIFY_CONFORMANCE,
                WorkKind.EVALUATE_CANDIDATE,
                WorkKind.REVIEW_CANDIDATE,
                WorkKind.PROMOTE_CANDIDATE,
            ],
        )
        evidence_work = next(
            item
            for item in effects.calls
            if item.kind == WorkKind.REVIEW_EVIDENCE
        )
        self.assertEqual(
            evidence_work.payload["trial_budget"],
            {
                "max_trials_per_hypothesis": 4,
                "trial_batch_size": 3,
                "max_trial_assignments": 12,
            },
        )
        events = controller.journal.read()
        self.assertEqual(events[-1].event_type, "work_transitioned")
        self.assertTrue(
            any(event.event_type == "version_advanced" for event in events)
        )

    async def test_stops_before_work_without_persisting_pause(self) -> None:
        """调试边界保留正式队列，并可由普通 run 继续。"""

        effects = HappyPathEffects()
        controller = EvolutionController(
            run_dir=self.run_dir,
            effects=effects,
            config=EvolutionControlConfig(max_generations=1),
        )
        controller.initialize(
            run_id="run-stop-before-distiller",
            initial_version="harness_v0001",
        )

        stopped = await controller.run(
            stop_before=frozenset({WorkKind.DISTILL_MECHANISM})
        )

        self.assertEqual(stopped.status, "running")
        state = project_events(controller.journal.read())
        self.assertEqual(len(state.queued), 1)
        self.assertIs(
            state.queued[0].item.kind,
            WorkKind.DISTILL_MECHANISM,
        )
        self.assertFalse(
            any(
                event.event_type in {"run_paused", "run_completed"}
                for event in controller.journal.read()
            )
        )
        self.assertNotIn(
            WorkKind.DISTILL_MECHANISM,
            [item.kind for item in effects.calls],
        )

        completed = await controller.run()

        self.assertEqual(completed.status, "completed")
        self.assertIn(
            WorkKind.DISTILL_MECHANISM,
            [item.kind for item in effects.calls],
        )

    async def test_calls_evidence_reviewer_once_for_a_three_trial_batch(
        self,
    ) -> None:
        """Evidence Reviewer 调用次数按批次而不是按成功 Trial 增长。"""

        class BatchedHappyPathEffects(HappyPathEffects):
            async def execute(
                self,
                *,
                work: WorkItem,
                state: ControlState,
                work_dir: Path,
            ) -> EffectResult:
                if work.kind not in {
                    WorkKind.SELECT_TRIAL,
                    WorkKind.EXECUTE_TRIAL,
                }:
                    return await super().execute(
                        work=work,
                        state=state,
                        work_dir=work_dir,
                    )
                self.calls.append(work)
                if work.kind == WorkKind.EXECUTE_TRIAL:
                    assignments = work.payload["pending_assignments"]
                    return EffectResult(
                        outcome={
                            "results": [
                                {
                                    "assignment_key": (
                                        f"{assignment['example_id']}/"
                                        f"{assignment['replicate_id']}/"
                                        f"{assignment['prefix_id']}"
                                    ),
                                    "output": {"result_kind": "executed"},
                                    "artifact_key": (
                                        f"worker_artifact_{index:03d}"
                                    ),
                                }
                                for index, assignment in enumerate(
                                    assignments,
                                    start=1,
                                )
                            ]
                        },
                        artifact_refs={
                            f"worker_artifact_{index:03d}": (
                                f"trial-{index}.json"
                            )
                            for index in range(1, len(assignments) + 1)
                        },
                    )
                assignments = [
                    {
                        "example_id": f"example-{index}",
                        "replicate_id": "r000",
                        "prefix_id": 1,
                    }
                    for index in range(1, 4)
                ]
                return EffectResult(
                    outcome={
                        "status": "selected",
                        "selection_mode": "fresh",
                        "assignments": assignments,
                        "assignment_count": 3,
                        "used_assignments": [
                            f"example-{index}/r000/1"
                            for index in range(1, 4)
                        ],
                    }
                )

        effects = BatchedHappyPathEffects()
        controller = EvolutionController(
            run_dir=self.run_dir,
            effects=effects,
            config=EvolutionControlConfig(max_generations=1),
        )
        controller.initialize(
            run_id="run-batched-review",
            initial_version="harness_v0001",
        )

        outcome = await controller.run()

        self.assertEqual(outcome.status, "completed")
        self.assertEqual(
            sum(item.kind == WorkKind.EXECUTE_TRIAL for item in effects.calls),
            1,
        )
        self.assertEqual(
            sum(item.kind == WorkKind.REVIEW_EVIDENCE for item in effects.calls),
            1,
        )

    async def test_updates_projection_after_commits_without_controlling_run(
        self,
    ) -> None:
        projection = RecordingProjection(fail_first=True)
        controller = EvolutionController(
            run_dir=self.run_dir,
            effects=HappyPathEffects(),
            config=EvolutionControlConfig(max_generations=1),
            projections=(projection,),
        )

        with self.assertLogs(
            "search_harness.evolution.control.controller",
            level="WARNING",
        ):
            controller.initialize(
                run_id="run-with-projection",
                initial_version="harness_v0001",
            )
        outcome = await controller.run()

        self.assertEqual(outcome.status, "completed")
        self.assertGreater(projection.calls, 1)
        calls_after_completion = projection.calls

        repeated_outcome = await controller.run()

        self.assertEqual(repeated_outcome.status, "completed")
        self.assertEqual(projection.calls, calls_after_completion + 1)

    async def test_retries_failed_effect_without_replaying_completed_work(
        self,
    ) -> None:
        """验证局部 effect 失败只重试当前 WorkItem。"""

        effects = FailFailureAnalysisOnce()
        controller = EvolutionController(
            run_dir=self.run_dir,
            effects=effects,
            config=EvolutionControlConfig(max_work_retries=1),
        )
        controller.initialize(
            run_id="run-retry",
            initial_version="harness_v0001",
        )

        outcome = await controller.run()

        self.assertEqual(outcome.status, "completed")
        incumbent_calls = [
            item
            for item in effects.calls
            if item.kind == WorkKind.EVALUATE_INCUMBENT
        ]
        analysis_calls = [
            item
            for item in effects.calls
            if item.kind == WorkKind.ANALYZE_FAILURE
        ]
        self.assertEqual(len(incumbent_calls), 1)
        self.assertEqual([item.attempt for item in analysis_calls], [1, 2])

    async def test_persists_teacher_failure_artifact_before_pausing(self) -> None:
        effects = FailWithRoleArtifact()
        controller = EvolutionController(
            run_dir=self.run_dir,
            effects=effects,
            config=EvolutionControlConfig(max_work_retries=0),
        )
        controller.initialize(
            run_id="run-role-failure",
            initial_version="harness_v0001",
        )

        outcome = await controller.run()

        self.assertEqual(outcome.status, "paused")
        failures = list(
            (self.run_dir / "artifacts").rglob("evidence_reviewer.failed.json")
        )
        self.assertEqual(len(failures), 1)
        artifact = json.loads(failures[0].read_text(encoding="utf-8"))
        self.assertEqual(artifact["status"], "failed")
        failed_events = [
            event
            for event in controller.journal.read()
            if event.event_type == "work_failed"
        ]
        self.assertEqual(
            failed_events[-1].payload["failure_artifact"],
            str(failures[0].resolve()),
        )
        self.assertEqual(failed_events[-1].payload["total_tokens"], 7)
        self.assertEqual(outcome.total_tokens, 107)

    def test_candidate_revision_target_routes_after_durable_rejection(
        self,
    ) -> None:
        """验证 Reviewer 修订先关闭 pending 候选，再返回明确职责层。"""

        review_work = WorkItem(
            work_id="review-candidate",
            kind=WorkKind.REVIEW_CANDIDATE,
            subject_ref="generation:1",
            input_refs={"compiler_artifact": "compiler.json"},
            payload={
                "incumbent_metrics": _metrics(
                    accuracy=0.5,
                    tokens=100,
                ),
                "candidate_metrics": _metrics(
                    accuracy=0.55,
                    tokens=120,
                ),
                "validation_summary": {"passed": True},
                "candidate_revision": 0,
                "candidate_attempt_id": "candidate_attempt-1",
            },
        )
        review_result = EffectResult(
            outcome={
                "output": {
                    "recommendation": "revise",
                    "observed_effect": "The mechanism is promising.",
                    "reason": "The implementation trigger is too broad.",
                    "next_obligation": "Narrow the Hook trigger.",
                    "revision_target": "implementation",
                }
            }
        )

        reject_plan = transition_completed(
            item=review_work,
            result=review_result,
            config=EvolutionControlConfig(),
        )
        reject_work = reject_plan.next_items[0]
        compile_plan = transition_completed(
            item=reject_work,
            result=EffectResult(
                outcome={
                    "status": "rejected",
                    "candidate_attempt_id": "candidate_attempt-1",
                }
            ),
            config=EvolutionControlConfig(),
        )

        self.assertEqual(
            reject_work.kind,
            WorkKind.REJECT_CANDIDATE,
        )
        self.assertEqual(
            compile_plan.next_items[0].kind,
            WorkKind.COMPILE_CANDIDATE,
        )
        self.assertEqual(
            compile_plan.next_items[0].payload[
                "implementation_constraints"
            ],
            ["Narrow the Hook trigger."],
        )

    def test_candidate_mechanism_revision_carries_obligation(
        self,
    ) -> None:
        """验证机制层能收到 Candidate Reviewer 的具体修订义务。"""

        review_work = WorkItem(
            work_id="review-mechanism",
            kind=WorkKind.REVIEW_CANDIDATE,
            subject_ref="generation:1",
            input_refs={
                "compiler_candidate_file": "candidate_workspace.json"
            },
            payload={
                "incumbent_metrics": _metrics(
                    accuracy=0.5,
                    tokens=100,
                ),
                "candidate_metrics": _metrics(
                    accuracy=0.5,
                    tokens=100,
                ),
                "validation_summary": {"passed": True},
                "candidate_attempt_id": "candidate_attempt-1",
            },
        )
        review_result = EffectResult(
            outcome={
                "output": {
                    "recommendation": "revise",
                    "observed_effect": "The trigger never activated.",
                    "reason": "The mechanism assumed unavailable evidence.",
                    "next_obligation": "Use only observable trigger inputs.",
                    "revision_target": "mechanism",
                }
            }
        )

        reject_work = transition_completed(
            item=review_work,
            result=review_result,
            config=EvolutionControlConfig(),
        ).next_items[0]
        mechanism_work = transition_completed(
            item=reject_work,
            result=EffectResult(
                outcome={
                    "status": "rejected",
                    "candidate_attempt_id": "candidate_attempt-1",
                }
            ),
            config=EvolutionControlConfig(),
        ).next_items[0]

        self.assertEqual(
            mechanism_work.kind,
            WorkKind.DISTILL_MECHANISM,
        )
        self.assertEqual(
            mechanism_work.payload["capability_constraints"],
            ["Use only observable trigger inputs."],
        )
        self.assertNotIn(
            "compiler_candidate_file",
            mechanism_work.input_refs,
        )

    def test_candidate_reject_starts_new_research_attempt(self) -> None:
        """验证真正拒绝只放弃当前方向，并复用 incumbent 开始新研究。"""

        review_work = WorkItem(
            work_id="review-reject",
            kind=WorkKind.REVIEW_CANDIDATE,
            subject_ref="generation:1",
            input_refs={
                "report_dir": "incumbent-report",
                "rollout_file": "incumbent-rollouts.jsonl",
                "candidate_report_dir": "candidate-report",
                "mechanism_file": "mechanism.json",
            },
            payload={
                "generation": 1,
                "version_id": "harness_v0001",
                "research_attempt": 1,
                "incumbent_metrics": _metrics(accuracy=0.5, tokens=100),
                "candidate_metrics": _metrics(accuracy=0.5, tokens=150),
                "validation_summary": {"passed": True},
                "candidate_attempt_id": "candidate_attempt-1",
                "trial_count": 3,
                "compiler_revision": 2,
            },
        )
        review_result = EffectResult(
            outcome={
                "output": {
                    "recommendation": "reject",
                    "observed_effect": "The mechanism over-triggered.",
                    "reason": "The research direction causes broad regressions.",
                    "next_obligation": None,
                    "revision_target": None,
                }
            }
        )

        reject_work = transition_completed(
            item=review_work,
            result=review_result,
            config=EvolutionControlConfig(),
        ).next_items[0]
        next_plan = transition_completed(
            item=reject_work,
            result=EffectResult(
                outcome={
                    "status": "rejected",
                    "candidate_attempt_id": "candidate_attempt-1",
                }
            ),
            config=EvolutionControlConfig(),
        )

        next_work = next_plan.next_items[0]
        self.assertEqual(next_work.kind, WorkKind.ANALYZE_FAILURE)
        self.assertEqual(next_work.payload["research_attempt"], 2)
        self.assertEqual(next_work.payload["generation"], 1)
        self.assertEqual(next_work.payload["version_id"], "harness_v0001")
        self.assertIn(
            "different bounded failure pattern",
            next_work.payload["analysis_focus"],
        )
        self.assertLessEqual(len(next_work.payload["analysis_focus"]), 300)
        self.assertNotIn("trial_count", next_work.payload)
        self.assertNotIn("compiler_revision", next_work.payload)
        self.assertEqual(
            next_work.input_refs,
            {
                "report_dir": "incumbent-report",
                "rollout_file": "incumbent-rollouts.jsonl",
            },
        )

    def test_promotion_gate_reject_starts_new_research_attempt(self) -> None:
        """验证 Reviewer accept 被门禁拒绝后也重新选择研究方向。"""

        review_work = WorkItem(
            work_id="review-gate-reject",
            kind=WorkKind.REVIEW_CANDIDATE,
            subject_ref="generation:1",
            input_refs={
                "report_dir": "incumbent-report",
                "rollout_file": "incumbent-rollouts.jsonl",
            },
            payload={
                "generation": 1,
                "version_id": "harness_v0001",
                "research_attempt": 1,
                "incumbent_metrics": _metrics(accuracy=0.5, tokens=100),
                "candidate_metrics": _metrics(accuracy=0.6, tokens=400),
                "validation_summary": {"passed": True},
                "candidate_attempt_id": "candidate_attempt-1",
            },
        )
        reject_work = transition_completed(
            item=review_work,
            result=EffectResult(
                outcome={
                    "output": {
                        "recommendation": "accept",
                        "observed_effect": "Accuracy improved.",
                        "reason": "The mechanism is effective.",
                        "next_obligation": None,
                        "revision_target": None,
                    }
                }
            ),
            config=EvolutionControlConfig(max_total_token_ratio=3.0),
        ).next_items[0]
        next_work = transition_completed(
            item=reject_work,
            result=EffectResult(
                outcome={
                    "status": "rejected",
                    "candidate_attempt_id": "candidate_attempt-1",
                }
            ),
            config=EvolutionControlConfig(max_total_token_ratio=3.0),
        ).next_items[0]

        self.assertEqual(next_work.kind, WorkKind.ANALYZE_FAILURE)
        self.assertIn("token ratio", next_work.payload["analysis_focus"])
        self.assertNotIn(
            "mechanism is effective",
            next_work.payload["analysis_focus"],
        )

    def test_unchanged_rejected_candidate_skips_validation_revision(self) -> None:
        """验证重复被拒 digest 不消耗 Compiler validation revision。"""

        plan = transition_completed(
            item=WorkItem(
                work_id="stage-unchanged-rejected",
                kind=WorkKind.STAGE_CANDIDATE,
                subject_ref="generation:1",
                input_refs={
                    "report_dir": "incumbent-report",
                    "rollout_file": "incumbent-rollouts.jsonl",
                    "compiler_artifact": "compiler.json",
                    "mechanism_file": "mechanism.json",
                },
                payload={
                    "generation": 1,
                    "version_id": "harness_v0001",
                    "research_attempt": 1,
                    "incumbent_metrics": _metrics(accuracy=0.5, tokens=100),
                    "compiler_revision": 4,
                },
            ),
            result=EffectResult(
                outcome={
                    "status": "unchanged_rejected_candidate",
                    "candidate_attempt_id": "candidate_attempt-1",
                    "candidate_digest": "candidate-digest",
                    "rejection_reason": "Conformance replay failed.",
                    "prior_validation": {"passed": True, "errors": []},
                }
            ),
            config=EvolutionControlConfig(),
        )

        next_work = plan.next_items[0]
        self.assertEqual(next_work.kind, WorkKind.ANALYZE_FAILURE)
        self.assertEqual(next_work.payload["research_attempt"], 2)
        self.assertNotIn("compiler_revision", next_work.payload)
        self.assertNotIn("validation_feedback", next_work.payload)
        self.assertNotIn("compiler_artifact", next_work.input_refs)

    def test_compiler_routes_explicit_upstream_decisions(self) -> None:
        """验证 Compiler 的证据与机制请求返回对应职责层。"""

        base_work = WorkItem(
            work_id="compile-upstream",
            kind=WorkKind.COMPILE_CANDIDATE,
            subject_ref="generation:1",
            input_refs={
                "compiler_candidate_file": "candidate_workspace.json",
                "mechanism_file": "mechanism.json",
            },
            payload={
                "trial_count": 1,
                "assignment_count": 1,
                "mechanism_revision": 0,
            },
        )
        evidence_plan = transition_completed(
            item=base_work,
            result=EffectResult(
                outcome={
                    "output": {
                        "decision": "needs_evidence",
                        "implementation_summary": "Evidence is incomplete.",
                        "next_obligation": "Add a negative predicate example.",
                    }
                }
            ),
            config=EvolutionControlConfig(),
        )
        mechanism_plan = transition_completed(
            item=base_work,
            result=EffectResult(
                outcome={
                    "output": {
                        "decision": "implementation_blocked",
                        "implementation_summary": "The predicate is ambiguous.",
                        "next_obligation": "Define the uncertain label.",
                    }
                }
            ),
            config=EvolutionControlConfig(),
        )

        evidence_work = evidence_plan.next_items[0]
        self.assertEqual(evidence_work.kind, WorkKind.SELECT_TRIAL)
        self.assertEqual(
            evidence_work.payload["prior_obligation"],
            "Add a negative predicate example.",
        )
        self.assertNotIn("compiler_candidate_file", evidence_work.input_refs)
        mechanism_work = mechanism_plan.next_items[0]
        self.assertEqual(mechanism_work.kind, WorkKind.DISTILL_MECHANISM)
        self.assertEqual(
            mechanism_work.payload["capability_constraints"],
            ["Define the uncertain label."],
        )

    def test_promotion_gate_rejects_excessive_candidate_cost(self) -> None:
        """验证模型 accept 不能越过确定性 token 成本门禁。"""

        decision = evaluate_promotion(
            reviewer_recommendation="accept",
            validation_summary={"passed": True},
            incumbent_metrics=_metrics(accuracy=0.5, tokens=100),
            candidate_metrics=_metrics(accuracy=0.6, tokens=301),
            config=EvolutionControlConfig(
                max_total_token_ratio=3.0
            ),
        )

        self.assertFalse(decision.passed)
        self.assertEqual(decision.total_token_ratio, 3.01)

    def test_conformance_failure_rejects_candidate_and_routes_compiler(
        self,
    ) -> None:
        """验证 replay 脱敏义务经持久拒绝后返回 Compiler。"""

        work = WorkItem(
            work_id="verify-conformance",
            kind=WorkKind.VERIFY_CONFORMANCE,
            subject_ref="generation:1",
            input_refs={
                "compiler_artifact": "compiler.json",
                "compiler_candidate_file": "candidate_workspace.json",
                "conformance_rollout_file": "replay.jsonl",
                "trial_001": "trial.json",
            },
            payload={
                "candidate_attempt_id": "candidate_attempt-1",
                "candidate_revision": 0,
            },
        )
        result = EffectResult(
            outcome={
                "decision": "revise",
                "summary": {
                    "decision": "revise",
                    "finding_counts": {"not_observed": 3},
                    "recommended_route": "implementation",
                    "route_feedback": {
                        "implementation": [
                            "Ensure the pre_final Hook produces an observable "
                            "action."
                        ]
                    },
                    "per_example": {
                        "example-1": {
                            "faithful_count": 0,
                            "passed": False,
                        }
                    },
                    "compiler_feedback": [
                        "Ensure the pre_final Hook produces an observable "
                        "action."
                    ],
                    "finding_refs": [],
                },
            },
        )

        reject_work = transition_completed(
            item=work,
            result=result,
            config=EvolutionControlConfig(),
        ).next_items[0]
        compile_work = transition_completed(
            item=reject_work,
            result=EffectResult(
                outcome={
                    "status": "rejected",
                    "candidate_attempt_id": "candidate_attempt-1",
                }
            ),
            config=EvolutionControlConfig(),
        ).next_items[0]

        self.assertEqual(reject_work.kind, WorkKind.REJECT_CANDIDATE)
        self.assertEqual(compile_work.kind, WorkKind.COMPILE_CANDIDATE)
        self.assertEqual(
            compile_work.payload["implementation_constraints"],
            [
                "Ensure the pre_final Hook produces an observable action."
            ],
        )
        self.assertNotIn(
            "conformance_rollout_file",
            compile_work.input_refs,
        )
        self.assertEqual(
            compile_work.input_refs["compiler_candidate_file"],
            "candidate_workspace.json",
        )

    def test_conformance_mechanism_diagnosis_routes_to_distiller(self) -> None:
        """Reviewer-owned ambiguous-spec diagnosis bypasses Compiler repair."""

        work = WorkItem(
            work_id="verify-conformance-mechanism",
            kind=WorkKind.VERIFY_CONFORMANCE,
            subject_ref="generation:1",
            input_refs={
                "compiler_artifact": "compiler.json",
                "compiler_candidate_file": "candidate_workspace.json",
                "mechanism_file": "mechanism.json",
            },
            payload={
                "candidate_attempt_id": "candidate_attempt-1",
                "candidate_revision": 0,
            },
        )
        result = EffectResult(
            outcome={
                "decision": "revise",
                "summary": {
                    "decision": "revise",
                    "finding_counts": {"inconclusive": 3},
                    "recommended_route": "mechanism",
                    "route_feedback": {
                        "mechanism": [
                            "Define the positive and uncertain boundary."
                        ]
                    },
                    "per_example": {},
                    "finding_refs": [],
                },
            },
        )

        reject_work = transition_completed(
            item=work,
            result=result,
            config=EvolutionControlConfig(),
        ).next_items[0]
        next_work = transition_completed(
            item=reject_work,
            result=EffectResult(
                outcome={
                    "status": "rejected",
                    "candidate_attempt_id": "candidate_attempt-1",
                }
            ),
            config=EvolutionControlConfig(),
        ).next_items[0]

        self.assertEqual(next_work.kind, WorkKind.DISTILL_MECHANISM)
        self.assertEqual(
            next_work.payload["capability_constraints"],
            ["Define the positive and uncertain boundary."],
        )
        self.assertNotIn("compiler_candidate_file", next_work.input_refs)

    def test_conformance_passes_to_full_candidate_evaluation(self) -> None:
        """验证每题存在 faithful 且无硬失败时才启动全量评估。"""

        plan = transition_completed(
            item=WorkItem(
                work_id="verify-conformance-pass",
                kind=WorkKind.VERIFY_CONFORMANCE,
                subject_ref="generation:1",
                payload={"candidate_attempt_id": "candidate_attempt-1"},
            ),
            result=EffectResult(
                outcome={
                    "decision": "pass",
                    "summary": {
                        "decision": "pass",
                        "finding_counts": {"faithful": 1},
                        "per_example": {
                            "example-1": {
                                "faithful_count": 1,
                                "passed": True,
                            }
                        },
                        "compiler_feedback": [],
                        "finding_refs": [],
                    },
                }
            ),
            config=EvolutionControlConfig(),
        )

        self.assertEqual(
            plan.next_items[0].kind,
            WorkKind.EVALUATE_CANDIDATE,
        )

    def test_execute_trial_rejects_removed_result_kind(self) -> None:
        """验证 Worker 不能再绕过 Trial Review 回流 Researcher。"""

        with self.assertRaisesRegex(
            ValueError,
            "unknown Intervention Worker result: invalid_result",
        ):
            transition_completed(
                item=WorkItem(
                    work_id="execute-unsupported",
                    kind=WorkKind.EXECUTE_TRIAL,
                    subject_ref="generation:1",
                ),
                result=EffectResult(
                    outcome={
                        "output": {
                            "result_kind": "invalid_result",
                        }
                    }
                ),
                config=EvolutionControlConfig(),
            )

    def test_batch_assignments_execute_in_order_before_one_review(self) -> None:
        """批次顺序消费 executed/unsuitable Assignment 后只进入一次总评。"""

        assignments = [
            {
                "example_id": f"example-{index}",
                "replicate_id": "r000",
                "prefix_id": 1,
            }
            for index in range(1, 4)
        ]
        selected_plan = transition_completed(
            item=WorkItem(
                work_id="select-batch",
                kind=WorkKind.SELECT_TRIAL,
                subject_ref="generation:1",
                payload={
                    "trial_count": 0,
                    "assignment_count": 0,
                    "used_assignments": [],
                },
            ),
            result=EffectResult(
                outcome={
                    "status": "selected",
                    "selection_mode": "fresh",
                    "assignments": assignments,
                    "assignment_count": 3,
                    "used_assignments": [
                        f"example-{index}/r000/1" for index in range(1, 4)
                    ],
                }
            ),
            config=EvolutionControlConfig(),
        )
        first = selected_plan.next_items[0]
        self.assertEqual(first.payload["assignment"], assignments[0])
        self.assertEqual(first.payload["pending_assignments"], assignments)

        second_plan = transition_completed(
            item=first,
            result=EffectResult(
                outcome={"output": {"result_kind": "executed"}},
                artifact_refs={"worker_artifact": "trial-one.json"},
            ),
            config=EvolutionControlConfig(),
        )
        second = WorkItem.from_dict(second_plan.next_items[0].to_dict())
        self.assertEqual(second.kind, WorkKind.EXECUTE_TRIAL)
        self.assertEqual(second.payload["assignment"], assignments[1])
        self.assertEqual(second.payload["trial_count"], 1)

        third_plan = transition_completed(
            item=second,
            result=EffectResult(
                outcome={
                    "output": {"result_kind": "unsuitable_assignment"}
                }
            ),
            config=EvolutionControlConfig(),
        )
        third = third_plan.next_items[0]
        self.assertEqual(third.kind, WorkKind.EXECUTE_TRIAL)
        self.assertEqual(third.payload["assignment"], assignments[2])
        self.assertEqual(third.payload["trial_count"], 1)

        review_plan = transition_completed(
            item=third,
            result=EffectResult(
                outcome={"output": {"result_kind": "executed"}},
                artifact_refs={"worker_artifact": "trial-three.json"},
            ),
            config=EvolutionControlConfig(),
        )
        review = review_plan.next_items[0]
        self.assertEqual(review.kind, WorkKind.REVIEW_EVIDENCE)
        self.assertEqual(review.payload["trial_count"], 2)
        self.assertEqual(review.input_refs["trial_001"], "trial-one.json")
        self.assertEqual(review.input_refs["trial_002"], "trial-three.json")
        for field in (
            "assignment",
            "pending_assignments",
            "batch_assignment_count",
            "batch_executed_count",
        ):
            self.assertNotIn(field, review.payload)

    def test_parallel_trial_batch_commits_once_in_assignment_order(self) -> None:
        """并发 Effect 的有序结果通过一次 Transition 进入 Evidence Review。"""

        assignments = [
            {
                "example_id": f"example-{index}",
                "replicate_id": "r000",
                "prefix_id": 1,
            }
            for index in range(1, 4)
        ]
        execute = transition_completed(
            item=WorkItem(
                work_id="select-parallel-batch",
                kind=WorkKind.SELECT_TRIAL,
                subject_ref="generation:1",
                payload={
                    "trial_count": 0,
                    "assignment_count": 0,
                    "used_assignments": [],
                },
            ),
            result=EffectResult(
                outcome={
                    "status": "selected",
                    "selection_mode": "fresh",
                    "assignments": assignments,
                    "assignment_count": 3,
                    "used_assignments": [
                        f"example-{index}/r000/1" for index in range(1, 4)
                    ],
                }
            ),
            config=EvolutionControlConfig(),
        ).next_items[0]
        review = transition_completed(
            item=execute,
            result=EffectResult(
                outcome={
                    "results": [
                        {
                            "assignment_key": f"example-{index}/r000/1",
                            "output": {
                                "result_kind": (
                                    "unsuitable_assignment"
                                    if index == 2
                                    else "executed"
                                )
                            },
                            "artifact_key": f"worker_artifact_{index:03d}",
                        }
                        for index in range(1, 4)
                    ]
                },
                artifact_refs={
                    f"worker_artifact_{index:03d}": f"trial-{index}.json"
                    for index in range(1, 4)
                },
            ),
            config=EvolutionControlConfig(),
        ).next_items[0]

        self.assertEqual(review.kind, WorkKind.REVIEW_EVIDENCE)
        self.assertEqual(review.payload["trial_count"], 2)
        self.assertEqual(review.input_refs["trial_001"], "trial-1.json")
        self.assertEqual(review.input_refs["trial_002"], "trial-3.json")
        self.assertNotIn("pending_assignments", review.payload)

    def test_selected_batch_cannot_exceed_remaining_trial_budget(self) -> None:
        """Controller 独立拒绝越过剩余 Trial 预算的 Selector 输出。"""

        assignments = [
            {
                "example_id": f"example-{index}",
                "replicate_id": "r000",
                "prefix_id": 1,
            }
            for index in range(1, 3)
        ]
        with self.assertRaisesRegex(ValueError, "remaining Trial budget"):
            transition_completed(
                item=WorkItem(
                    work_id="select-over-trial-budget",
                    kind=WorkKind.SELECT_TRIAL,
                    subject_ref="generation:1",
                    payload={
                        "trial_count": 3,
                        "assignment_count": 0,
                        "used_assignments": [],
                    },
                ),
                result=EffectResult(
                    outcome={
                        "status": "selected",
                        "selection_mode": "fresh",
                        "assignments": assignments,
                        "assignment_count": 2,
                        "used_assignments": [
                            f"example-{index}/r000/1"
                            for index in range(1, 3)
                        ],
                    }
                ),
                config=EvolutionControlConfig(),
            )

    def test_empty_batch_reselects_without_evidence_review(self) -> None:
        """整批 Assignment 均不适用时继续选择且不调度空 Evidence Review。"""

        assignments = [
            {
                "example_id": "example-1",
                "replicate_id": "r000",
                "prefix_id": 1,
            },
            {
                "example_id": "example-2",
                "replicate_id": "r000",
                "prefix_id": 1,
            },
        ]
        first = transition_completed(
            item=WorkItem(
                work_id="select-empty-batch",
                kind=WorkKind.SELECT_TRIAL,
                subject_ref="generation:1",
                payload={"trial_count": 0, "assignment_count": 0},
            ),
            result=EffectResult(
                outcome={
                    "status": "selected",
                    "selection_mode": "fresh",
                    "assignments": assignments,
                    "assignment_count": 2,
                    "used_assignments": [
                        "example-1/r000/1",
                        "example-2/r000/1",
                    ],
                }
            ),
            config=EvolutionControlConfig(),
        ).next_items[0]
        second = transition_completed(
            item=first,
            result=EffectResult(
                outcome={
                    "output": {"result_kind": "unsuitable_assignment"}
                }
            ),
            config=EvolutionControlConfig(),
        ).next_items[0]
        next_plan = transition_completed(
            item=second,
            result=EffectResult(
                outcome={
                    "output": {"result_kind": "unsuitable_assignment"}
                }
            ),
            config=EvolutionControlConfig(),
        )

        self.assertEqual(next_plan.next_items[0].kind, WorkKind.SELECT_TRIAL)
        self.assertEqual(next_plan.next_items[0].payload["trial_count"], 0)

    def test_revised_hypothesis_resets_batch_and_old_evidence_refs(self) -> None:
        """Researcher 提交新版后清空旧 Trial、Coverage、计数与批次队列。"""

        plan = transition_completed(
            item=WorkItem(
                work_id="research-revision-reset",
                kind=WorkKind.RESEARCH_HYPOTHESIS,
                subject_ref="generation:1",
                input_refs={
                    "rollout_file": "rollouts.jsonl",
                    "report_dir": "report",
                    "failure_artifact": "failure.json",
                    "hypothesis_artifact": "old-hypothesis.json",
                    "trial_001": "old-trial.json",
                    "trial_review_001_artifact": "old-review.json",
                    "coverage_summary_artifact": "old-coverage.json",
                },
                payload={
                    "hypothesis_revision": 1,
                    "trial_count": 1,
                    "assignment_count": 2,
                    "used_assignments": ["example-1/r000/1"],
                    "prior_obligation": "Old obligation",
                    "assignment": {"example_id": "example-2"},
                    "pending_assignments": [{"example_id": "example-2"}],
                    "batch_assignment_count": 1,
                    "batch_executed_count": 0,
                    "research_continuation": {"feedback_source": "review"},
                },
            ),
            result=EffectResult(
                outcome={"output": {"fork_phase": "post_tool"}},
                artifact_refs={"hypothesis_artifact": "new-hypothesis.json"},
            ),
            config=EvolutionControlConfig(),
        )

        selected = plan.next_items[0]
        self.assertEqual(selected.kind, WorkKind.SELECT_TRIAL)
        self.assertEqual(
            selected.input_refs,
            {
                "rollout_file": "rollouts.jsonl",
                "report_dir": "report",
                "failure_artifact": "failure.json",
                "hypothesis_artifact": "new-hypothesis.json",
            },
        )
        self.assertEqual(selected.payload["trial_count"], 0)
        self.assertEqual(selected.payload["assignment_count"], 0)
        self.assertEqual(selected.payload["used_assignments"], [])
        self.assertIsNone(selected.payload["prior_obligation"])
        self.assertEqual(selected.payload["pending_assignments"], [])
        self.assertEqual(selected.payload["batch_assignment_count"], 0)
        self.assertEqual(selected.payload["batch_executed_count"], 0)
        self.assertEqual(selected.payload["hypothesis_revision"], 1)

    def test_promotion_gate_rejects_runner_errors_without_crashing(self) -> None:
        """验证 runner_error 与缺失 token 被表示为门禁失败而非异常。"""

        candidate = _metrics(accuracy=0.0, tokens=0)
        candidate["tokens"]["total_tokens"] = None
        candidate["execution"]["status_counts"] = {"runner_error": 3}
        decision = evaluate_promotion(
            reviewer_recommendation="revise",
            validation_summary={"passed": True},
            incumbent_metrics=_metrics(accuracy=0.5, tokens=100),
            candidate_metrics=candidate,
            config=EvolutionControlConfig(),
        )

        self.assertFalse(decision.passed)
        self.assertIsNone(decision.total_token_ratio)
        self.assertIn(
            "candidate execution contains runner errors: 3",
            decision.reasons,
        )
        self.assertIn(
            "candidate total token count is unavailable",
            decision.reasons,
        )

    def test_review_with_failed_candidate_routes_to_rejection(self) -> None:
        """验证异常候选仍可携带 Reviewer 修订义务进入拒绝流程。"""

        candidate = _metrics(accuracy=0.0, tokens=0)
        candidate["tokens"]["total_tokens"] = None
        candidate["execution"]["status_counts"] = {"runner_error": 3}
        work = WorkItem(
            work_id="review-runner-error",
            kind=WorkKind.REVIEW_CANDIDATE,
            subject_ref="generation:1",
            payload={
                "incumbent_metrics": _metrics(
                    accuracy=0.5,
                    tokens=100,
                ),
                "candidate_metrics": candidate,
                "validation_summary": {"passed": True},
                "candidate_attempt_id": "candidate_attempt-1",
            },
        )
        result = EffectResult(
            outcome={
                "output": {
                    "recommendation": "revise",
                    "observed_effect": "All sampled rollouts failed.",
                    "reason": "The Hook accessed an invalid trace field.",
                    "next_obligation": "Use TrajectoryEvent.event_type.",
                    "revision_target": "implementation",
                }
            }
        )

        plan = transition_completed(
            item=work,
            result=result,
            config=EvolutionControlConfig(),
        )

        self.assertEqual(plan.next_items[0].kind, WorkKind.REJECT_CANDIDATE)
        self.assertEqual(
            plan.next_items[0].payload["after_rejection"]["target"],
            "implementation",
        )

    def test_promotion_uses_separate_safety_and_effect_gates(self) -> None:
        """验证安全阈值允许小幅回撤，而 Reviewer 独立决定效果是否值得接受。"""

        accepted = evaluate_promotion(
            reviewer_recommendation="accept",
            validation_summary={"passed": True},
            incumbent_metrics=_metrics(accuracy=0.50, tokens=100),
            candidate_metrics=_metrics(accuracy=0.49, tokens=110),
            config=EvolutionControlConfig(),
        )
        reviewer_rejected = evaluate_promotion(
            reviewer_recommendation="reject",
            validation_summary={"passed": True},
            incumbent_metrics=_metrics(accuracy=0.50, tokens=100),
            candidate_metrics=_metrics(accuracy=0.60, tokens=110),
            config=EvolutionControlConfig(),
        )

        self.assertTrue(accepted.safety_passed)
        self.assertTrue(accepted.effect_passed)
        self.assertTrue(accepted.passed)
        self.assertTrue(reviewer_rejected.safety_passed)
        self.assertFalse(reviewer_rejected.effect_passed)
        self.assertFalse(reviewer_rejected.passed)

    def test_promotion_safety_gate_blocks_invalid_or_regressed_candidate(
        self,
    ) -> None:
        """验证 Reviewer accept 不能越过 validation 与严重 accuracy 回退。"""

        decision = evaluate_promotion(
            reviewer_recommendation="accept",
            validation_summary={"passed": False},
            incumbent_metrics=_metrics(accuracy=0.50, tokens=100),
            candidate_metrics=_metrics(accuracy=0.45, tokens=100),
            config=EvolutionControlConfig(),
        )

        self.assertFalse(decision.safety_passed)
        self.assertTrue(decision.effect_passed)
        self.assertFalse(decision.passed)
        self.assertIn(
            "candidate validation did not pass",
            decision.safety_reasons,
        )
        self.assertTrue(
            any(
                reason.startswith(
                    "accuracy regression exceeds the configured safety limit"
                )
                for reason in decision.safety_reasons
            )
        )

    async def test_recovers_persisted_effect_after_controller_interruption(
        self,
    ) -> None:
        """验证 effect 落盘后即使事件未提交也不会重复执行。"""

        effects = HappyPathEffects()
        controller = EvolutionController(
            run_dir=self.run_dir,
            effects=effects,
            config=EvolutionControlConfig(),
        )
        controller.initialize(
            run_id="run-recover",
            initial_version="harness_v0001",
        )
        state = controller._state()
        first = state.queued[0].item
        controller.journal.append(
            "work_started",
            {"work_id": first.work_id},
        )
        artifacts = ControlArtifactStore(
            self.run_dir / "artifacts"
        )
        artifacts.write_effect(
            first.work_id,
            EffectResult(
                outcome={"metrics": _metrics(accuracy=0.5, tokens=100)},
                artifact_refs={
                    "report_dir": "report",
                    "rollout_file": "rollout",
                },
                usage={"total_tokens": 100},
            ),
        )

        outcome = await controller.run()

        self.assertEqual(outcome.status, "completed")
        self.assertFalse(
            any(
                item.kind == WorkKind.EVALUATE_INCUMBENT
                for item in effects.calls
            )
        )
        completed = [
            event
            for event in ControlJournal(
                self.run_dir / "events.jsonl"
            ).read()
            if event.event_type == "work_completed"
            and event.payload.get("work_id") == first.work_id
        ]
        self.assertEqual(len(completed), 1)

    async def test_explicit_resume_retries_exhausted_failed_work(
        self,
    ) -> None:
        """验证修复外部条件后可从已耗尽的局部失败项继续。"""

        effects = RecoverableFailureEffects()
        controller = EvolutionController(
            run_dir=self.run_dir,
            effects=effects,
            config=EvolutionControlConfig(max_work_retries=0),
        )
        controller.initialize(
            run_id="run-resume",
            initial_version="harness_v0001",
        )

        paused = await controller.run()
        effects.available = True
        completed = await controller.run()

        self.assertEqual(paused.status, "paused")
        self.assertEqual(completed.status, "completed")
        analysis_calls = [
            item
            for item in effects.calls
            if item.kind == WorkKind.ANALYZE_FAILURE
        ]
        self.assertEqual([item.attempt for item in analysis_calls], [1, 2])


class LocalControlEffectsTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        SCRATCH_ROOT.mkdir(parents=True, exist_ok=True)
        self.run_dir = SCRATCH_ROOT / uuid4().hex
        self.store = TemplateVersionStore(self.run_dir / "version_store")
        baseline = Path("harness_templates/student/baseline").resolve()
        self.store.initialize(baseline)

    def tearDown(self) -> None:
        resolved = self.run_dir.resolve()
        scratch = SCRATCH_ROOT.resolve()
        if resolved.parent != scratch:
            raise AssertionError("refusing to clean an unexpected test path")
        if resolved.exists():
            _remove_scratch(resolved)

    async def test_failure_analyst_uses_shared_teacher_assembly(self) -> None:
        """正式 Controller 路由显式绑定 Role 并使用新 Template Root。"""

        class RecordingRuntime:
            def __init__(self) -> None:
                self.calls: list[dict[str, Any]] = []

            async def run(self, **kwargs: Any) -> dict[str, Any]:
                self.calls.append(kwargs)
                return {
                    "output": {
                        "pattern": "The Student finalizes after one retrieval.",
                        "applicability": "Evidence requires a second retrieval.",
                        "caveats": ["Prevalence is not established."],
                        "evidence_refs": ["example-1/r000", "example-2/r000"],
                    },
                    "usage": {"total_tokens": 10},
                }

        effects = LocalControlEffects(
            store=self.store,
            config=LocalControlEffectsConfig(
                experience_file=self.run_dir / "experience.jsonl",
                show_progress=False,
            ),
        )
        runtime = RecordingRuntime()
        effects.role_runner = runtime  # type: ignore[assignment]

        await effects.execute(
            work=WorkItem(
                work_id="analyze-shared-assembly",
                kind=WorkKind.ANALYZE_FAILURE,
                subject_ref="generation:1",
                input_refs={
                    "report_dir": str(self.run_dir / "report"),
                    "rollout_file": str(self.run_dir / "rollouts.jsonl"),
                },
            ),
            state=ControlState(
                current_version="harness_v0001",
                status="running",
            ),
            work_dir=self.run_dir / "analysis",
        )

        call = runtime.calls[0]
        self.assertEqual(call["template_root"].name, "failure_analyst")
        self.assertEqual(call["role_id"], "failure_analyst")
        self.assertEqual(call["role_version"], 1)

    async def test_execute_trial_dispatches_whole_batch_with_rollout_limit(
        self,
    ) -> None:
        """Local Effect 将 pending batch 一次性交给受限并发执行器。"""

        class RecordingInterventionEffects:
            def __init__(self) -> None:
                self.calls: list[dict[str, Any]] = []

            async def execute_batch(self, **values: Any) -> EffectResult:
                self.calls.append(values)
                return EffectResult(outcome={"results": []})

        hypothesis_file = self.run_dir / "hypothesis.json"
        hypothesis_file.write_text(
            json.dumps({"output": {"fork_phase": "post_tool"}}),
            encoding="utf-8",
        )
        rollout_file = self.run_dir / "rollouts.jsonl"
        rollout_file.write_text("", encoding="utf-8")
        assignments = [
            {
                "example_id": f"example-{index}",
                "replicate_id": "r000",
                "prefix_id": 1,
            }
            for index in range(1, 3)
        ]
        effects = LocalControlEffects(
            store=self.store,
            config=LocalControlEffectsConfig(
                experience_file=self.run_dir / "experience.jsonl",
                rollout_workers=2,
                show_progress=False,
            ),
        )
        intervention = RecordingInterventionEffects()
        with patch.object(
            effects,
            "_intervention_effects",
            return_value=intervention,
        ):
            await effects.execute(
                work=WorkItem(
                    work_id="execute-parallel-trials",
                    kind=WorkKind.EXECUTE_TRIAL,
                    subject_ref="generation:1",
                    input_refs={
                        "hypothesis_artifact": str(hypothesis_file),
                        "rollout_file": str(rollout_file),
                    },
                    payload={
                        "assignment": assignments[0],
                        "pending_assignments": assignments,
                    },
                ),
                state=ControlState(
                    current_version="harness_v0001",
                    status="running",
                ),
                work_dir=self.run_dir / "execute-parallel-trials",
            )

        self.assertEqual(len(intervention.calls), 1)
        self.assertEqual(intervention.calls[0]["assignments"], assignments)
        self.assertEqual(intervention.calls[0]["max_workers"], 2)

    async def test_stage_candidate_is_idempotent_by_candidate_digest(
        self,
    ) -> None:
        """验证控制器重试不会为同一 Compiler 候选遗留重复 pending 事务。"""

        manifest = json.loads(
            (self.store.template_dir / "harness.json").read_text(
                encoding="utf-8"
            )
        )
        manifest["extensions"].append(
            {
                "instance_id": "controller_test_hook",
                "entrypoint": (
                    "extensions/controller_test_hook/component.py:build"
                ),
                "config": {},
            }
        )
        policy = json.loads(
            (self.store.template_dir / "evolution.json").read_text(
                encoding="utf-8"
            )
        )
        policy["components"]["controller_test_hook"] = "mutable"
        changed_files = {
            "extensions/controller_test_hook/component.py": (
                "from __future__ import annotations\n"
                "\n"
                "from typing import Any\n"
                "\n"
                "from search_harness.framework import BaseHook, HookContext, "
                "HookPhase\n"
                "\n"
                "\n"
                "class ControllerTestHook(BaseHook):\n"
                "    def __init__(self) -> None:\n"
                "        super().__init__(\n"
                "            hook_id=\"controller_test_hook\",\n"
                "            phases=frozenset({HookPhase.POST_PROMPT}),\n"
                "        )\n"
                "\n"
                "    def handle(self, context: HookContext) -> None:\n"
                "        return None\n"
                "\n"
                "\n"
                "def build(\n"
                "    config: dict[str, Any], context: Any\n"
                ") -> ControllerTestHook:\n"
                "    if config:\n"
                "        raise ValueError(\"config must be empty\")\n"
                "    return ControllerTestHook()\n"
            ),
            "harness.json": (
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
            ),
            "evolution.json": (
                json.dumps(policy, ensure_ascii=False, indent=2) + "\n"
            ),
        }
        workspace = self.store.open_workspace("harness_v0001")
        workspace.apply_patch(
            FileEdit("write", path, content)
            for path, content in changed_files.items()
        )
        compiler_artifact = self.run_dir / "compiler.json"
        compiler_artifact.write_text(
            json.dumps(
                {
                    "output": {
                        "decision": "submitted",
                        "candidate_ref": "candidate_001",
                        "implementation_summary": "Add a no-op test Hook.",
                        "unresolved_risk": None,
                    },
                    "resource_artifacts": {
                        "compiler_candidate": {
                            "candidate_digest": workspace.digest,
                            "validation": {"passed": True},
                            "changed_files": changed_files,
                        }
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        effects = LocalControlEffects(
            store=self.store,
            config=LocalControlEffectsConfig(
                experience_file=self.run_dir / "experience.jsonl",
                env_file=Path(".env"),
                show_progress=False,
            ),
        )
        state = ControlState(
            current_version="harness_v0001",
            status="running",
        )
        first = WorkItem(
            work_id="stage-first",
            kind=WorkKind.STAGE_CANDIDATE,
            subject_ref="generation:1",
            input_refs={
                "compiler_artifact": str(compiler_artifact.resolve())
            },
        )
        second = WorkItem(
            work_id="stage-retry",
            kind=WorkKind.STAGE_CANDIDATE,
            subject_ref="generation:1",
            input_refs={
                "compiler_artifact": str(compiler_artifact.resolve())
            },
            attempt=2,
        )

        first_result = await effects.execute(
            work=first,
            state=state,
            work_dir=self.run_dir / "first",
        )
        second_result = await effects.execute(
            work=second,
            state=state,
            work_dir=self.run_dir / "second",
        )

        self.assertEqual(first_result.outcome["status"], "valid")
        self.assertEqual(
            first_result.outcome["candidate_attempt_id"],
            second_result.outcome["candidate_attempt_id"],
        )
        pending = [
            item
            for item in self.store.list_candidate_attempts()
            if item.status == "pending"
        ]
        self.assertEqual(len(pending), 1)
        self.store.resume_candidate_attempt(pending[0].candidate_attempt_id).reject(
            "test cleanup"
        )
        repeated_rejected = await effects.execute(
            work=WorkItem(
                work_id="stage-rejected-digest",
                kind=WorkKind.STAGE_CANDIDATE,
                subject_ref="generation:1",
                input_refs={
                    "compiler_artifact": str(compiler_artifact.resolve())
                },
            ),
            state=state,
            work_dir=self.run_dir / "rejected",
        )
        self.assertEqual(
            repeated_rejected.outcome["status"],
            "unchanged_rejected_candidate",
        )
        self.assertEqual(
            repeated_rejected.outcome["candidate_attempt_id"],
            pending[0].candidate_attempt_id,
        )
        self.assertEqual(
            repeated_rejected.outcome["prior_validation"]["passed"],
            True,
        )

    async def test_candidate_version_effects_promote_and_reject(
        self,
    ) -> None:
        """Candidate Version effects preserve accept and reject transactions."""

        attempt = self.store.start_candidate_attempt(
            parent_version="harness_v0001"
        )
        manifest = json.loads(
            (self.store.template_dir / "harness.json").read_text(
                encoding="utf-8"
            )
        )
        manifest["extensions"].append(
            {
                "instance_id": "promotion_test_hook",
                "entrypoint": (
                    "extensions/promotion_test_hook/"
                    "component.py:build"
                ),
                "config": {},
            }
        )
        policy = json.loads(
            (self.store.template_dir / "evolution.json").read_text(
                encoding="utf-8"
            )
        )
        policy["components"]["promotion_test_hook"] = "mutable"
        attempt.apply_patch(
            [
                FileEdit(
                    "write",
                    "extensions/promotion_test_hook/component.py",
                    (
                        "from search_harness.framework import "
                        "BaseHook, HookPhase\n\n"
                        "class PromotionTestHook(BaseHook):\n"
                        "    def __init__(self):\n"
                        "        super().__init__(\n"
                        "            hook_id='promotion_test_hook',\n"
                        "            phases=frozenset({HookPhase.POST_PROMPT}),\n"
                        "        )\n\n"
                        "    def handle(self, context):\n"
                        "        return None\n\n"
                        "def build(config, context):\n"
                        "    return PromotionTestHook()\n"
                    ),
                ),
                FileEdit(
                    "write",
                    "harness.json",
                    json.dumps(manifest, ensure_ascii=False, indent=2)
                    + "\n",
                ),
                FileEdit(
                    "write",
                    "evolution.json",
                    json.dumps(policy, ensure_ascii=False, indent=2)
                    + "\n",
                ),
            ]
        )
        validation = attempt.validate(env_file=Path(".env"))
        self.assertTrue(validation.passed, validation.errors)

        compiler_artifact = self.run_dir / "compiler-promote.json"
        compiler_artifact.write_text(
            json.dumps(
                {
                    "output": {
                        "decision": "submitted",
                        "candidate_ref": "candidate-promote",
                        "implementation_summary": "Mechanical test edit.",
                        "unresolved_risk": None,
                    }
                }
            ),
            encoding="utf-8",
        )
        effects = LocalControlEffects(
            store=self.store,
            config=LocalControlEffectsConfig(
                experience_file=self.run_dir / "experience.jsonl",
                show_progress=False,
            ),
        )
        promoted = await effects.execute(
            work=WorkItem(
                work_id="promote-candidate",
                kind=WorkKind.PROMOTE_CANDIDATE,
                subject_ref="generation:1",
                input_refs={
                    "compiler_artifact": str(
                        compiler_artifact.resolve()
                    )
                },
                payload={
                    "candidate_attempt_id": attempt.candidate_attempt_id,
                    "candidate_metrics": {"accuracy": 0.8},
                    "candidate_review": {
                        "recommendation": "accept",
                    },
                    "promotion_gate": {"passed": True},
                },
            ),
            state=ControlState(
                current_version="harness_v0001",
                status="running",
            ),
            work_dir=self.run_dir / "promotion",
        )
        self.assertEqual(promoted.outcome["version_id"], "harness_v0002")
        promoted_retry = await effects.execute(
            work=WorkItem(
                work_id="promote-candidate-retry",
                kind=WorkKind.PROMOTE_CANDIDATE,
                subject_ref="generation:1",
                payload={"candidate_attempt_id": attempt.candidate_attempt_id},
                attempt=2,
            ),
            state=ControlState(
                current_version="harness_v0002",
                status="running",
            ),
            work_dir=self.run_dir / "promotion-retry",
        )
        self.assertEqual(promoted_retry.outcome, promoted.outcome)

        rejected_attempt = self.store.start_candidate_attempt(
            parent_version="harness_v0002"
        )
        rejected = await effects.execute(
            work=WorkItem(
                work_id="reject-candidate",
                kind=WorkKind.REJECT_CANDIDATE,
                subject_ref="generation:2",
                payload={
                    "candidate_attempt_id": rejected_attempt.candidate_attempt_id,
                    "candidate_metrics": {"accuracy": 0.7},
                    "candidate_review": {
                        "reason": "Candidate regressed.",
                    },
                    "promotion_gate": {
                        "passed": False,
                        "reasons": ["Accuracy floor failed."],
                    },
                },
            ),
            state=ControlState(
                current_version="harness_v0002",
                status="running",
            ),
            work_dir=self.run_dir / "rejection",
        )
        self.assertEqual(rejected.outcome["status"], "rejected")
        rejected_retry = await effects.execute(
            work=WorkItem(
                work_id="reject-candidate-retry",
                kind=WorkKind.REJECT_CANDIDATE,
                subject_ref="generation:2",
                payload={"candidate_attempt_id": rejected_attempt.candidate_attempt_id},
                attempt=2,
            ),
            state=ControlState(
                current_version="harness_v0002",
                status="running",
            ),
            work_dir=self.run_dir / "rejection-retry",
        )
        self.assertEqual(rejected_retry.outcome, rejected.outcome)
        summaries = {
            item.candidate_attempt_id: item
            for item in self.store.list_candidate_attempts()
        }
        self.assertEqual(
            summaries[rejected_attempt.candidate_attempt_id].status,
            "rejected",
        )

    async def test_conformance_effect_batches_three_independent_findings(
        self,
    ) -> None:
        """验证每个 Example 完整运行三次并在一次审查中独立判定。"""

        experience_file = self.run_dir / "experience.jsonl"
        experience_file.write_text(
            json.dumps(
                {
                    "example_id": "example-1",
                    "question": "Test question?",
                    "answer": "answer",
                    "metadata": {},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        mechanism_file = self.run_dir / "mechanism.json"
        mechanism_file.write_text(
            json.dumps(
                {
                    "goal": "Delay one premature final answer.",
                    "phase_rules": [
                        {
                            "phase": "pre_final",
                            "trigger_condition": "First final answer.",
                            "decision_inputs": ["candidate_answer"],
                            "runtime_inputs": ["final_decision"],
                            "decision_evaluator": "deterministic",
                            "action": "Defer once.",
                            "activation_budget": 1,
                        }
                    ],
                    "behavioral_pseudocode": (
                        "ON pre_final: DEFER once; then ACCEPT."
                    ),
                    "state_scope": "rollout-local",
                    "fallback": "Accept later final answers.",
                    "expected_behavior": "One visible deferral.",
                    "evidence_refs": ["trial_001"],
                }
            ),
            encoding="utf-8",
        )
        trial_file = self.run_dir / "trial_001" / "trial.json"
        trial_file.parent.mkdir()
        trial_file.write_text(
            json.dumps(
                {
                    "input": {"example_id": "example-1"},
                    "resource_artifacts": {
                        "intervention_trial": {
                            "phase_plan": [{"phase": "pre_final"}],
                            "activation_counts": {"pre_final": 1},
                            "context_changes": [],
                            "phase_effects": [],
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        class ReplayBackend:
            def rollout_candidate_examples(
                self,
                *,
                output_file: Path,
                **_: Any,
            ) -> dict[str, Any]:
                records = [
                    {
                        "example": {
                            "example_id": "example-1",
                            "question": "Test question?",
                        },
                        "replicate": {
                            "replicate_id": f"r{index:03d}",
                            "index": index,
                        },
                        "run": {
                            "status": "completed",
                            "trace": [],
                        },
                    }
                    for index in range(3)
                ]
                output_file.parent.mkdir(parents=True, exist_ok=True)
                output_file.write_text(
                    "".join(
                        json.dumps(record) + "\n"
                        for record in records
                    ),
                    encoding="utf-8",
                )
                return {
                    "requested_examples": 1,
                    "requested_rollouts": 3,
                    "processed_rollouts": 3,
                    "runner_errors": 0,
                }

            def evaluate_existing_rollouts(
                self,
                *,
                rollout_file: Path,
                output_dir: Path,
            ) -> dict[str, Any]:
                records = [
                    {
                        "example_id": "example-1",
                        "replicate_id": f"r{index:03d}",
                        "score": 1,
                        "score_source": "static",
                        "teacher": None,
                        "run_status": "completed",
                    }
                    for index in range(3)
                ]
                output_dir.mkdir(parents=True, exist_ok=True)
                (output_dir / "per_rollout.jsonl").write_text(
                    "".join(json.dumps(item) + "\n" for item in records),
                    encoding="utf-8",
                )
                return {"rollouts": records}

        class ConformanceRuntime:
            def __init__(self) -> None:
                self.calls: list[dict[str, Any]] = []

            async def run(self, **kwargs: Any) -> dict[str, Any]:
                self.calls.append(kwargs)
                role_input = kwargs["role_input"]
                trajectories = role_input["candidate_trajectory_views"]
                return {
                    "output": {
                        "findings": [
                            {
                                "replicate_id": item["replicate_id"],
                                "verdict": (
                                    "faithful"
                                    if item["replicate_id"] == "r000"
                                    else "not_observed"
                                ),
                                "observed_phases": (
                                    ["pre_final"]
                                    if item["replicate_id"] == "r000"
                                    else []
                                ),
                                "assessment": (
                                    "The mechanism was faithfully observed."
                                    if item["replicate_id"] == "r000"
                                    else "The mechanism was not observed."
                                ),
                                "repair_obligation": (
                                    None
                                    if item["replicate_id"] == "r000"
                                    else "Make the activation observable."
                                ),
                                "failure_layer": (
                                    None
                                    if item["replicate_id"] == "r000"
                                    else "integration"
                                ),
                                "decisive_input_summary": (
                                    None
                                    if item["replicate_id"] == "r000"
                                    else "No declared phase behavior was observable."
                                ),
                                "recommended_route": (
                                    None
                                    if item["replicate_id"] == "r000"
                                    else "implementation"
                                ),
                                "local_efficacy": "neutral",
                                "local_efficacy_assessment": (
                                    "The scored outcome was preserved."
                                ),
                            }
                            for item in trajectories
                        ]
                    },
                    "usage": {"total_tokens": 5},
                }

        effects = LocalControlEffects(
            store=self.store,
            config=LocalControlEffectsConfig(
                experience_file=experience_file,
                env_file=Path(".env"),
                judge_workers=3,
                show_progress=False,
            ),
        )
        effects.backend = ReplayBackend()  # type: ignore[assignment]
        runtime = ConformanceRuntime()
        effects.role_runner = runtime  # type: ignore[assignment]
        candidate = CandidateArtifact(
            candidate_attempt_id="candidate_attempt-1",
            parent_version="harness_v0001",
            candidate_digest="digest",
            compiler_log=self.run_dir / "compiler.json",
            summary="test candidate",
            validation_passed=True,
            validation={"passed": True},
        )
        with patch.object(
            effects,
            "_candidate_artifact",
            return_value=candidate,
        ):
            result = await effects.execute(
                work=WorkItem(
                    work_id="verify-conformance",
                    kind=WorkKind.VERIFY_CONFORMANCE,
                    subject_ref="generation:1",
                    input_refs={
                        "mechanism_file": str(mechanism_file.resolve()),
                        "trial_001": str(trial_file.resolve()),
                    },
                    payload={"candidate_attempt_id": "candidate_attempt-1"},
                ),
                state=ControlState(
                    current_version="harness_v0001",
                    status="running",
                ),
                work_dir=self.run_dir / "conformance",
            )

        self.assertEqual(result.outcome["decision"], "pass")
        self.assertEqual(len(runtime.calls), 1)
        self.assertIn(
            "candidate_trajectory_views",
            runtime.calls[0]["role_input"],
        )
        self.assertNotIn(
            "candidate_trajectory",
            runtime.calls[0]["role_input"],
        )
        self.assertEqual(result.usage["total_tokens"], 5)
        self.assertTrue(
            Path(
                result.artifact_refs["conformance_summary_artifact"]
            ).is_file()
        )
        finding = json.loads(
            Path(
                result.artifact_refs["conformance_finding_001"]
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            finding["output"]["candidate_run_ref"],
            "example-1/r000",
        )
        batch_artifact = json.loads(
            Path(finding["role_artifact_ref"]).read_text(encoding="utf-8")
        )
        self.assertNotIn(
            "candidate_run_ref",
            batch_artifact["role_artifact"]["output"],
        )

    async def test_conformance_retry_reuses_rollout_after_batch_failure(
        self,
    ) -> None:
        """验证 batch 审查失败后复用 rollout 并重试该 Example。"""

        experience_file = self.run_dir / "checkpoint_experience.jsonl"
        experience_file.write_text(
            json.dumps(
                {
                    "example_id": "example-checkpoint",
                    "question": "Checkpoint question?",
                    "answer": "answer",
                    "metadata": {},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        trial_file = self.run_dir / "checkpoint_trial" / "trial.json"
        trial_file.parent.mkdir()
        trial_file.write_text(
            json.dumps(
                {
                    "input": {"example_id": "example-checkpoint"},
                    "resource_artifacts": {
                        "intervention_trial": {
                            "phase_plan": [{"phase": "pre_final"}],
                            "activation_counts": {"pre_final": 1},
                            "context_changes": [],
                            "phase_effects": [],
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        mechanism = MechanismSpec.model_validate(
            {
                "goal": "Delay one premature final answer.",
                "phase_rules": [
                    {
                        "phase": "pre_final",
                        "trigger_condition": "First final answer.",
                        "decision_inputs": ["candidate_answer"],
                        "runtime_inputs": ["final_decision"],
                        "decision_evaluator": "deterministic",
                        "action": "Defer once.",
                        "activation_budget": 1,
                    }
                ],
                "behavioral_pseudocode": (
                    "ON pre_final: DEFER once; then ACCEPT."
                ),
                "state_scope": "rollout-local",
                "fallback": "Accept later final answers.",
                "expected_behavior": "One visible deferral.",
                "evidence_refs": ["trial_001"],
            }
        )

        class ReplayBackend:
            def __init__(self) -> None:
                self.calls = 0

            def rollout_candidate_examples(
                self,
                *,
                output_file: Path,
                **_: object,
            ) -> dict[str, object]:
                self.calls += 1
                records = [
                    {
                        "example": {
                            "example_id": "example-checkpoint",
                            "question": "Checkpoint question?",
                        },
                        "replicate": {
                            "replicate_id": f"r{index:03d}",
                            "index": index,
                        },
                        "run": {"status": "completed", "trace": []},
                    }
                    for index in range(3)
                ]
                output_file.parent.mkdir(parents=True, exist_ok=True)
                output_file.write_text(
                    "".join(json.dumps(item) + "\n" for item in records),
                    encoding="utf-8",
                )
                return {"processed_rollouts": 3}

            def evaluate_existing_rollouts(
                self,
                *,
                rollout_file: Path,
                output_dir: Path,
            ) -> dict[str, object]:
                records = [
                    {
                        "example_id": "example-checkpoint",
                        "replicate_id": f"r{index:03d}",
                        "score": 1,
                        "score_source": "static",
                        "teacher": None,
                        "run_status": "completed",
                    }
                    for index in range(3)
                ]
                output_dir.mkdir(parents=True, exist_ok=True)
                (output_dir / "per_rollout.jsonl").write_text(
                    "".join(json.dumps(item) + "\n" for item in records),
                    encoding="utf-8",
                )
                return {"rollouts": records}

        class OneFindingFailure(RuntimeError):
            def __init__(self) -> None:
                super().__init__("transient review failure")
                self.failure_artifact = {
                    "status": "failed",
                    "role": {"id": "conformance_reviewer", "version": 1},
                    "transcript": [
                        {"role": "assistant", "content": "partial review"}
                    ],
                    "usage": {"total_tokens": 7},
                }

        class RecoveringRuntime:
            def __init__(self) -> None:
                self.calls: list[tuple[str, ...]] = []
                self.failed = False

            async def run(self, **kwargs: object) -> dict[str, object]:
                role_input = kwargs["role_input"]
                assert isinstance(role_input, dict)
                trajectories = role_input["candidate_trajectory_views"]
                assert isinstance(trajectories, list)
                replicate_ids = tuple(
                    str(item["replicate_id"])
                    for item in trajectories
                    if isinstance(item, dict)
                )
                self.calls.append(replicate_ids)
                if not self.failed:
                    self.failed = True
                    raise OneFindingFailure()
                return {
                    "output": {
                        "findings": [
                            {
                                "replicate_id": replicate_id,
                                "verdict": "faithful",
                                "observed_phases": ["pre_final"],
                                "assessment": "The declared phase was observed.",
                                "repair_obligation": None,
                                "local_efficacy": "neutral",
                                "local_efficacy_assessment": (
                                    "The scored outcome was preserved."
                                ),
                            }
                            for replicate_id in replicate_ids
                        ]
                    },
                    "usage": {"total_tokens": 5},
                }

        backend = ReplayBackend()
        runtime = RecoveringRuntime()
        effects = ConformanceEffects(
            backend=backend,  # type: ignore[arg-type]
            role_runner=runtime,  # type: ignore[arg-type]
            experience_file=experience_file,
            reviewer_template_root=Path(
                "harness_templates/teacher/conformance_reviewer"
            ),
            judge_workers=3,
        )
        candidate = CandidateArtifact(
            candidate_attempt_id="candidate-checkpoint",
            parent_version="harness_v0001",
            candidate_digest="checkpoint-digest",
            compiler_log=self.run_dir / "compiler.json",
            summary="checkpoint candidate",
            validation_passed=True,
        )
        artifact_root = self.run_dir / "checkpoint_artifacts"

        with self.assertRaises(ConformanceBatchFailed) as raised:
            await effects.verify(
                mechanism=mechanism,
                trial_files=[trial_file],
                candidate=candidate,
                work_dir=artifact_root / "verify-attempt-1",
            )

        failure = raised.exception.failure_artifact
        self.assertEqual(failure["stage"], "review_findings")
        self.assertEqual(
            failure["usage"]["total_tokens"],
            7,
            failure,
        )
        finding_failure = json.loads(
            Path(
                failure["finding_failures"][0]["failure_artifact"]
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            finding_failure["role_artifact"]["transcript"][0]["content"],
            "partial review",
        )

        result = await effects.verify(
            mechanism=mechanism,
            trial_files=[trial_file],
            candidate=candidate,
            work_dir=artifact_root / "verify-attempt-2",
        )

        self.assertEqual(result.outcome["decision"], "pass")
        self.assertEqual(result.usage["total_tokens"], 5)
        self.assertEqual(backend.calls, 1)
        self.assertEqual(
            runtime.calls,
            [("r000", "r001", "r002"), ("r000", "r001", "r002")],
        )

    async def test_review_evidence_uses_independent_trial_review_first(
        self,
    ) -> None:
        """验证正式 effect 先独立审一条轨迹，再把审阅作为总评输入。"""

        hypothesis = {
            "fork_phase": "post_tool",
            "phase_plan": [
                {
                    "phase": "post_tool",
                    "activation_condition": "Partial evidence is visible.",
                    "instruction": "Ask the Student to inspect the gap.",
                    "expected_effect": "The Student searches again.",
                    "max_activations": 1,
                }
            ],
            "evaluation": {
                "primary_signal": "next_decision",
                "success_condition": "A useful follow-up occurs.",
                "falsifier": "No behavior changes.",
                "secondary_metrics": [],
            },
            "applicability": "Partial-evidence retrieval cases.",
        }
        hypothesis_file = self.run_dir / "hypothesis.json"
        hypothesis_file.write_text(
            json.dumps({"output": hypothesis}),
            encoding="utf-8",
        )
        trial_file = self.run_dir / "trial_001" / "trial.json"
        trial_file.parent.mkdir()
        trial_file.write_text(
            json.dumps(
                {
                    "output": {
                        "result_kind": "executed",
                        "activated_phases": ["post_tool"],
                        "modified_phases": ["post_tool"],
                        "unmet_phases": [],
                    },
                    "resource_artifacts": {
                        "intervention_trial": {
                            "activation_counts": {"post_tool": 1},
                            "context_changes": [
                                {
                                    "phase": "post_tool",
                                    "action": {
                                        "kind": "append_context_message"
                                    },
                                }
                            ],
                            "comparison": {
                                "source": {
                                    "status": "completed",
                                    "execution": {
                                        "model_calls": 2,
                                        "tool_calls": 1,
                                    },
                                },
                                "branch": {
                                    "status": "completed",
                                    "execution": {
                                        "model_calls": 3,
                                        "tool_calls": 2,
                                    },
                                },
                            },
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        effects = LocalControlEffects(
            store=self.store,
            config=LocalControlEffectsConfig(
                experience_file=self.run_dir / "experience.jsonl",
                show_progress=False,
            ),
        )
        runtime = ReviewPipelineRuntime()
        effects.role_runner = runtime  # type: ignore[assignment]
        result = await effects.execute(
            work=WorkItem(
                work_id="review-pipeline",
                kind=WorkKind.REVIEW_EVIDENCE,
                subject_ref="generation:1",
                input_refs={
                    "hypothesis_artifact": str(hypothesis_file.resolve()),
                    "trial_001": str(trial_file.resolve()),
                },
                payload={
                    "trial_count": 1,
                    "assignment_count": 1,
                    "trial_budget": {
                        "max_trials_per_hypothesis": 4,
                        "max_trial_assignments": 12,
                    },
                },
            ),
            state=ControlState(
                current_version="harness_v0001",
                status="running",
            ),
            work_dir=self.run_dir / "review",
        )

        self.assertEqual(len(runtime.calls), 2)
        self.assertEqual(
            runtime.calls[0]["template_root"].name,
            "trial_reviewer",
        )
        self.assertEqual(
            runtime.calls[1]["role_input"]["trial_reviews"][0]["trial_ref"],
            "trial_001",
        )
        self.assertEqual(
            runtime.calls[1]["role_input"]["budget"]["trials_remaining"],
            3,
        )
        self.assertEqual(
            runtime.calls[1]["resource_config"].trial_files,
            [],
        )
        self.assertEqual(
            result.outcome["output"]["decision"],
            "ready_to_distill",
        )
        second_trial = self.run_dir / "trial_002" / "trial.json"
        second_trial.parent.mkdir()
        second_trial.write_text(
            trial_file.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        await effects.execute(
            work=WorkItem(
                work_id="review-pipeline-continued",
                kind=WorkKind.REVIEW_EVIDENCE,
                subject_ref="generation:1",
                input_refs={
                    "hypothesis_artifact": str(hypothesis_file.resolve()),
                    "trial_001": str(trial_file.resolve()),
                    "trial_002": str(second_trial.resolve()),
                    **result.artifact_refs,
                },
                payload={
                    "trial_count": 2,
                    "assignment_count": 2,
                    "trial_budget": {
                        "max_trials_per_hypothesis": 4,
                        "max_trial_assignments": 12,
                    },
                },
            ),
            state=ControlState(
                current_version="harness_v0001",
                status="running",
            ),
            work_dir=self.run_dir / "review-continued",
        )
        self.assertEqual(len(runtime.calls), 4)
        self.assertEqual(
            runtime.calls[2]["role_input"]["trial_ref"],
            "trial_002",
        )

    def test_trial_paths_ignore_non_index_alias(self) -> None:
        """验证同一 trial 的便利别名不会作为第二份 Reviewer 证据。"""

        work = WorkItem(
            work_id="review",
            kind=WorkKind.REVIEW_EVIDENCE,
            subject_ref="generation:1",
            input_refs={
                "trial_file": "trial.json",
                "trial_001": "trial.json",
            },
        )

        self.assertEqual(
            _trial_paths(work),
            [Path("trial.json").resolve()],
        )


class _RoleFailure(RuntimeError):
    def __init__(self) -> None:
        super().__init__("structured output exhausted")
        self.failure_artifact = {
            "schema_version": 1,
            "status": "failed",
            "role": {"id": "evidence_reviewer", "version": 1},
            "transcript": [{"role": "assistant", "content": "partial"}],
            "usage": {"total_tokens": 7},
        }


class FailWithRoleArtifact(HappyPathEffects):
    async def execute(
        self,
        *,
        work: WorkItem,
        state: ControlState,
        work_dir: Path,
    ) -> EffectResult:
        if work.kind == WorkKind.ANALYZE_FAILURE:
            raise _RoleFailure()
        return await super().execute(work=work, state=state, work_dir=work_dir)


class FailFailureAnalysisOnce(HappyPathEffects):
    def __init__(self) -> None:
        super().__init__()
        self.failed = False

    async def execute(
        self,
        *,
        work: WorkItem,
        state: ControlState,
        work_dir: Path,
    ) -> EffectResult:
        if work.kind == WorkKind.ANALYZE_FAILURE and not self.failed:
            self.calls.append(work)
            self.failed = True
            raise RuntimeError("transient Teacher failure")
        return await super().execute(
            work=work,
            state=state,
            work_dir=work_dir,
        )


class RecoverableFailureEffects(HappyPathEffects):
    def __init__(self) -> None:
        super().__init__()
        self.available = False

    async def execute(
        self,
        *,
        work: WorkItem,
        state: ControlState,
        work_dir: Path,
    ) -> EffectResult:
        if work.kind == WorkKind.ANALYZE_FAILURE and not self.available:
            self.calls.append(work)
            raise RuntimeError("Teacher service unavailable")
        return await super().execute(
            work=work,
            state=state,
            work_dir=work_dir,
        )


def _metrics(*, accuracy: float, tokens: int) -> dict[str, object]:
    return {
        "answers": {"accuracy": accuracy},
        "execution": {
            "completed_rate": 1.0,
            "status_counts": {"completed": 1},
        },
        "tokens": {"total_tokens": tokens},
    }


def _remove_scratch(path: Path) -> None:
    def make_writable_and_retry(
        operation: Any,
        value: str,
        error: tuple[type[BaseException], BaseException, object],
    ) -> None:
        os.chmod(value, 0o700)
        operation(value)

    for attempt in range(5):
        try:
            shutil.rmtree(path, onerror=make_writable_and_retry)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.1)


if __name__ == "__main__":
    unittest.main()
