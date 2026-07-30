"""Formal Evolution Controller state, recovery, and routing tests."""

from __future__ import annotations

import json
import os
import shutil
import time
import unittest
from pathlib import Path
from uuid import uuid4

from search_harness.evolution.control.controller import EvolutionController
from search_harness.evolution.control.domain import (
    ControlState,
    EffectResult,
    EvolutionControlConfig,
    WorkItem,
    WorkKind,
)
from search_harness.evolution.control.effects import (
    LocalControlEffects,
    LocalControlEffectsConfig,
    _trial_paths,
)
from search_harness.evolution.control.journal import (
    ControlArtifactStore,
    ControlJournal,
)
from search_harness.evolution.control.policies import evaluate_promotion
from search_harness.evolution.control.transitions import (
    transition_completed,
)
from search_harness.versioning import (
    FileEdit,
    HarnessVersionStore,
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
                    "assignment": {
                        "example_id": "example-1",
                        "replicate_id": "r000",
                        "prefix_id": 1,
                    },
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
                    "iteration_id": "iteration-1",
                    "candidate_digest": "candidate-digest",
                    "validation": {"passed": True},
                },
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
                    "iteration_id": "iteration-1",
                    "candidate_digest": "candidate-digest",
                }
            )
        raise AssertionError(f"unexpected work kind: {work.kind}")


class ReviewPipelineRuntime:
    """Return one local trial review followed by one global evidence review."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def run(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        role = kwargs["template_root"].parent.name
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
        self.assertEqual(outcome.completed_work_count, 12)
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
                WorkKind.EVALUATE_CANDIDATE,
                WorkKind.REVIEW_CANDIDATE,
                WorkKind.PROMOTE_CANDIDATE,
            ],
        )
        events = controller.journal.read()
        self.assertEqual(events[-1].event_type, "work_transitioned")
        self.assertTrue(
            any(event.event_type == "version_advanced" for event in events)
        )

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
                "candidate_revision": 0,
                "iteration_id": "iteration-1",
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
                    "iteration_id": "iteration-1",
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
            payload={
                "incumbent_metrics": _metrics(
                    accuracy=0.5,
                    tokens=100,
                ),
                "candidate_metrics": _metrics(
                    accuracy=0.5,
                    tokens=100,
                ),
                "iteration_id": "iteration-1",
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
                    "iteration_id": "iteration-1",
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

    def test_promotion_gate_rejects_excessive_candidate_cost(self) -> None:
        """验证模型 accept 不能越过确定性 token 成本门禁。"""

        decision = evaluate_promotion(
            reviewer_recommendation="accept",
            incumbent_metrics=_metrics(accuracy=0.5, tokens=100),
            candidate_metrics=_metrics(accuracy=0.6, tokens=301),
            config=EvolutionControlConfig(
                max_total_token_ratio=3.0
            ),
        )

        self.assertFalse(decision.passed)
        self.assertEqual(decision.total_token_ratio, 3.01)

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
        self.store = HarnessVersionStore(self.run_dir / "checkpoint")
        baseline = (
            Path("harness_templates/actor/baseline/plugins").resolve()
        )
        self.store.initialize(baseline)

    def tearDown(self) -> None:
        resolved = self.run_dir.resolve()
        scratch = SCRATCH_ROOT.resolve()
        if resolved.parent != scratch:
            raise AssertionError("refusing to clean an unexpected test path")
        if resolved.exists():
            _remove_scratch(resolved)

    async def test_stage_candidate_is_idempotent_by_candidate_digest(
        self,
    ) -> None:
        """验证控制器重试不会为同一 Compiler 候选遗留重复 pending 事务。"""

        manifest = json.loads(
            (self.store.plugins_dir / "harness.json").read_text(
                encoding="utf-8"
            )
        )
        manifest["extensions"].append(
            {
                "instance_id": "controller_test_hook",
                "entrypoint": (
                    "extensions/controller_test_hook/plugin.py:build"
                ),
                "config": {},
                "evolution_policy": "mutable",
            }
        )
        changed_files = {
            "extensions/controller_test_hook/plugin.py": (
                "from __future__ import annotations\n"
                "\n"
                "from typing import Any\n"
                "\n"
                "from search_harness.core import BaseHook, HookContext, "
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
            first_result.outcome["iteration_id"],
            second_result.outcome["iteration_id"],
        )
        pending = [
            item
            for item in self.store.list_iterations()
            if item.status == "pending"
        ]
        self.assertEqual(len(pending), 1)
        self.store.resume_iteration(pending[0].iteration_id).reject(
            "test cleanup"
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
                    "instruction": "Ask the Actor to inspect the gap.",
                    "expected_effect": "The Actor searches again.",
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
        effects.runtime = runtime  # type: ignore[assignment]
        result = await effects.execute(
            work=WorkItem(
                work_id="review-pipeline",
                kind=WorkKind.REVIEW_EVIDENCE,
                subject_ref="generation:1",
                input_refs={
                    "hypothesis_artifact": str(hypothesis_file.resolve()),
                    "trial_001": str(trial_file.resolve()),
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
            runtime.calls[0]["template_root"].parent.name,
            "trial_reviewer",
        )
        self.assertEqual(
            runtime.calls[1]["role_input"]["trial_reviews"][0]["trial_ref"],
            "trial_001",
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
