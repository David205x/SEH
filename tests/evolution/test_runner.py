from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from search_harness.adapter.critic import CriticResult, CriticReview
from search_harness.adapter.intervention import InterventionCoordinatorResult
from search_harness.core import AgentRun, AgentState
from search_harness.datasets import DatasetExample
from search_harness.evolution import EvolutionConfig, EvolutionRunner
from search_harness.evolution.backend import LocalEvolutionBackend, LocalEvolutionBackendConfig
from search_harness.evolution.progress import EvolutionProgressEvent
from search_harness.evolution.types import (
    CandidateArtifact,
    CriticArtifact,
    EvaluationArtifact,
    InterventionArtifact,
)
from search_harness.versioning import HarnessVersionStore


PROMPT_PLUGIN = '''from search_harness.core import ChatMessage, ModelInput

class Prompt:
    def build(self, state):
        return ModelInput.from_messages([ChatMessage(role="user", content=state.question)])

def build(config, context, tools):
    return Prompt()
'''

HOOK_PLUGIN = '''from search_harness.core import BaseHook, HookPhase

class Hook(BaseHook):
    def __init__(self):
        super().__init__(hook_id="candidate_hook", phases=frozenset({HookPhase.PRE_PROMPT}))

    def handle(self, context):
        return None

def build(config, context):
    return Hook()
'''


class FakeBackend:
    """在不调用模型的情况下驱动完整 Version Store 事务。"""

    def __init__(self, store: HarnessVersionStore, decisions: list[str]) -> None:
        self.store = store
        self.decisions = decisions
        self.review_calls = 0
        self.compile_calls = 0
        self.accepted_evaluation_calls = 0
        self.failure_memories: list[tuple[dict[str, object], ...]] = []

    def evaluate_accepted(self, *, version_id, experience_file, output_dir):
        self.accepted_evaluation_calls += 1
        return self._evaluation(output_dir, 0.5)

    def analyze_failures(
        self, *, version_id, evaluation, failed_attempts, output_file
    ):
        self.failure_memories.append(failed_attempts)
        result = CriticResult(
            analysis="Repeated issue",
            problem_directions=(
                {
                    "problem": "premature completion",
                    "observed_pattern": "Repeated cases stop before enough evidence.",
                    "excluded_causes": [],
                    "desired_behavior": "Continue until evidence is sufficient.",
                    "success_criteria": ["More evidence-complete answers."],
                    "constraints": [],
                },
            ),
        )
        _write_log(output_file, result)
        return CriticArtifact(output_file, result)

    def validate_direction(
        self, *, version_id, evaluation, critic, output_dir
    ):
        output_dir.mkdir(parents=True, exist_ok=True)
        log_file = output_dir / "coordinator.json"
        result = InterventionCoordinatorResult(
            analysis="Cross-case trials support the mechanism.",
            verdict="supported",
            selected_trial_id="trial_001",
            recommendation="Compile the validated strategy.",
        )
        log_file.write_text(
            json.dumps({"coordinator_result": result.to_dict()}),
            encoding="utf-8",
        )
        return InterventionArtifact(log_file=log_file, result=result)

    def compile_candidate(
        self, *, parent_version, intervention, output_file, experience_file=None
    ):
        self.compile_calls += 1
        session = self.store.start_iteration(parent_version=parent_version)
        session.add_extension(
            instance_id=f"candidate_hook_{self.compile_calls}",
            files={
                "plugin.py": HOOK_PLUGIN + f"\n# attempt {self.compile_calls}\n"
            },
        )
        report = session.validate()
        output_file.write_text("{}", encoding="utf-8")
        return CandidateArtifact(
            iteration_id=session.iteration_id,
            parent_version=parent_version,
            candidate_digest=session.digest,
            compiler_log=output_file,
            summary="Add candidate hook",
            validation_passed=report.passed,
            validation={"passed": report.passed},
        )

    def evaluate_candidate(self, *, candidate, experience_file, output_dir):
        return self._evaluation(output_dir, 0.6)

    def review_candidate(
        self,
        *,
        candidate,
        candidate_evaluation,
        parent_evaluation,
        output_file,
    ):
        self.review_calls += 1
        decision = self.decisions.pop(0)
        result = CriticResult(
            analysis="Semantic review",
            review=CriticReview(decision=decision, reason=f"Decision: {decision}"),
        )
        _write_log(output_file, result)
        return CriticArtifact(output_file, result)

    @staticmethod
    def _evaluation(output_dir: Path, accuracy: float) -> EvaluationArtifact:
        output_dir.mkdir(parents=True, exist_ok=True)
        rollout = output_dir.parent / f"{output_dir.name}.jsonl"
        rollout.write_text("{}\n", encoding="utf-8")
        (output_dir / "summary.json").write_text("{}", encoding="utf-8")
        return EvaluationArtifact(
            rollout_file=rollout,
            report_dir=output_dir,
            metrics={"answers": {"accuracy": accuracy}},
        )


class ClarifyingBackend(FakeBackend):
    """首次请求澄清，随后在 Coordinator 补证后生成有效候选。"""

    def __init__(self, store: HarnessVersionStore) -> None:
        super().__init__(store, ["accept"])
        self.refinement_feedback: list[str] = []

    def compile_candidate(
        self, *, parent_version, intervention, output_file, experience_file=None
    ):
        self.compile_calls += 1
        session = self.store.start_iteration(parent_version=parent_version)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text("{}", encoding="utf-8")
        if self.compile_calls == 1:
            return CandidateArtifact(
                iteration_id=session.iteration_id,
                parent_version=parent_version,
                candidate_digest=session.digest,
                compiler_log=output_file,
                summary="Need a generalized trial",
                validation_passed=False,
                clarification="Test the generic post-tool decision rule.",
            )
        session.add_extension(
            instance_id="candidate_hook_refined",
            files={"plugin.py": HOOK_PLUGIN + "\n# refined attempt\n"},
        )
        report = session.validate()
        return CandidateArtifact(
            iteration_id=session.iteration_id,
            parent_version=parent_version,
            candidate_digest=session.digest,
            compiler_log=output_file,
            summary="Add refined candidate hook",
            validation_passed=report.passed,
            validation={"passed": report.passed},
        )

    def refine_direction(
        self,
        *,
        version_id,
        evaluation,
        critic,
        previous_intervention,
        compiler_feedback,
        output_dir,
    ):
        self.refinement_feedback.append(compiler_feedback)
        return self.validate_direction(
            version_id=version_id,
            evaluation=evaluation,
            critic=critic,
            output_dir=output_dir,
        )


class ContinuingInterventionBackend(FakeBackend):
    """按脚本返回 Intervention 结论并记录续验继承关系。"""

    def __init__(
        self, store: HarnessVersionStore, verdicts: list[str]
    ) -> None:
        super().__init__(store, ["accept"])
        self.verdicts = verdicts
        self.continued_logs: list[Path] = []

    def validate_direction(self, *, version_id, evaluation, critic, output_dir):
        return self._intervention(output_dir)

    def continue_direction(
        self,
        *,
        version_id,
        evaluation,
        critic,
        previous_intervention,
        output_dir,
    ):
        self.continued_logs.append(previous_intervention.log_file)
        return self._intervention(output_dir)

    def _intervention(self, output_dir: Path) -> InterventionArtifact:
        output_dir.mkdir(parents=True, exist_ok=True)
        log_file = output_dir / "coordinator.json"
        verdict = self.verdicts.pop(0)
        result = InterventionCoordinatorResult(
            analysis=f"Scripted {verdict} result.",
            verdict=verdict,
            selected_trial_id="trial_001" if verdict == "supported" else None,
            recommendation="Continue testing the same generic mechanism.",
        )
        log_file.write_text(
            json.dumps({"coordinator_result": result.to_dict()}),
            encoding="utf-8",
        )
        return InterventionArtifact(log_file=log_file, result=result)


class RecordingReporter:
    """收集进度事件，供 Runner 编排测试断言。"""

    def __init__(self) -> None:
        self.events: list[EvolutionProgressEvent] = []

    def report(self, event: EvolutionProgressEvent) -> None:
        self.events.append(event)


class CompletedLoop:
    """Return scripted completed Compiler answers while recording repair tasks."""

    def __init__(self, outputs: list[str], tasks: list[str]) -> None:
        self._outputs = outputs
        self._tasks = tasks

    def run(self, task: str) -> AgentRun:
        self._tasks.append(task)
        state = AgentState(question=task, max_steps=1)
        state.finish_completed(self._outputs.pop(0))
        return AgentRun(state=state, trace=())


class CompletedActorLoop:
    """返回一个最小 completed Actor run 供候选 smoke 测试。"""

    def run(self, question: str) -> AgentRun:
        state = AgentState(question=question, max_steps=1)
        state.finish_completed("smoke answer")
        return AgentRun(state=state, trace=())


class FailingActorLoop:
    """模拟候选 Hook 在真实 rollout 中访问不存在属性。"""

    def run(self, question: str) -> AgentRun:
        del question
        raise AttributeError("FinalDecision has no attribute is_accepted")


class EvolutionRunnerTest(TestCase):
    def test_invalid_stored_critic_result_is_invalidated_and_rebuilt(self) -> None:
        """验证历史缺字段 Critic artifact 被审计失效后重新生成。"""

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            store = _store(root)
            backend = FakeBackend(store, ["accept"])
            runner = _runner(root, store, backend, max_iterations=1)
            runner.initialize(_examples())
            runner.journal.append(
                "failure_critic_completed",
                {
                    "log_file": str(root / "malformed_critic.json"),
                    "result": {
                        "analysis": "Incomplete persisted result",
                        "problem_directions": [
                            {
                                "problem": "premature completion",
                                "observed_pattern": "repeated",
                                "excluded_causes": [],
                                "desired_behavior": "continue",
                                "success_criteria": [],
                            }
                        ],
                        "evidence_requests": [],
                        "review": None,
                    },
                },
                iteration=1,
            )

            outcome = runner.run()
            events = runner.journal.events()

        self.assertEqual(outcome.status, "completed")
        self.assertTrue(
            any(event.event_type == "failure_critic_invalidated" for event in events)
        )
        self.assertEqual(len(backend.failure_memories), 1)

    def test_compiler_repairs_candidate_after_real_actor_smoke_failure(self) -> None:
        """验证真实 smoke 错误关闭事务、回灌 Compiler 并重新提交。"""

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            store = _store(root)
            parent = store.resolve("harness_v0001")
            intervention = _intervention_artifact(root, parent)
            manifest = json.loads(parent.read_text("harness.json"))
            manifest["extensions"] = [
                {
                    "instance_id": "candidate_hook",
                    "entrypoint": "extensions/candidate_hook/plugin.py:build",
                    "config": {},
                    "evolution_policy": "mutable",
                }
            ]
            answer = _compiler_answer(
                json.dumps(manifest, ensure_ascii=False, indent=2), HOOK_PLUGIN
            )
            outputs = [answer, answer]
            tasks: list[str] = []
            experience_file = root / "experience.jsonl"
            experience_file.write_text(
                "\n".join(json.dumps(item.to_dict()) for item in _examples()) + "\n",
                encoding="utf-8",
            )
            backend = LocalEvolutionBackend(
                store=store,
                config=LocalEvolutionBackendConfig(
                    compiler_plugins_root=root / "unused-compiler-plugins",
                    compiler_validation_repair_limit=1,
                ),
            )

            with (
                patch(
                    "search_harness.evolution.backend.build_compiler_loop",
                    side_effect=lambda **kwargs: CompletedLoop(outputs, tasks),
                ),
                patch(
                    "search_harness.evolution.backend.build_loop",
                    side_effect=[FailingActorLoop(), CompletedActorLoop()],
                ),
            ):
                candidate = backend.compile_candidate(
                    parent_version="harness_v0001",
                    intervention=intervention,
                    output_file=root / "compiler.json",
                    experience_file=experience_file,
                )
            log = json.loads((root / "compiler.json").read_text(encoding="utf-8"))
            summaries = store.list_iterations()

        self.assertTrue(candidate.validation_passed)
        self.assertEqual([item.status for item in summaries], ["rejected", "pending"])
        self.assertFalse(log["attempts"][0]["smoke"]["passed"])
        self.assertTrue(log["attempts"][1]["smoke"]["passed"])
        self.assertIn("real Actor smoke rollout", tasks[1])

    def test_compiler_retries_malformed_result_and_closes_failed_transaction(self) -> None:
        """验证协议损坏会落盘、拒绝旧事务并以新会话生成完整候选。"""

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            store = _store(root)
            parent = store.resolve("harness_v0001")
            intervention = _intervention_artifact(root, parent)
            manifest = json.loads(parent.read_text("harness.json"))
            manifest["extensions"] = [
                {
                    "instance_id": "candidate_hook",
                    "entrypoint": "extensions/candidate_hook/plugin.py:build",
                    "config": {},
                    "evolution_policy": "mutable",
                }
            ]
            outputs = [
                "```json\n{}\n```",
                _compiler_answer(
                    json.dumps(manifest, ensure_ascii=False, indent=2), HOOK_PLUGIN
                ),
            ]
            tasks: list[str] = []
            backend = LocalEvolutionBackend(
                store=store,
                config=LocalEvolutionBackendConfig(
                    compiler_plugins_root=root / "unused-compiler-plugins",
                    compiler_validation_repair_limit=1,
                ),
            )

            with patch(
                "search_harness.evolution.backend.build_compiler_loop",
                side_effect=lambda **kwargs: CompletedLoop(outputs, tasks),
            ):
                candidate = backend.compile_candidate(
                    parent_version="harness_v0001",
                    intervention=intervention,
                    output_file=root / "compiler.json",
                )
            log = json.loads((root / "compiler.json").read_text(encoding="utf-8"))
            summaries = store.list_iterations()

        self.assertTrue(candidate.validation_passed)
        self.assertEqual([item.status for item in summaries], ["rejected", "pending"])
        self.assertEqual(len(log["attempts"]), 2)
        self.assertIn("not valid JSON", log["attempts"][0]["result_error"])
        self.assertIn("invalid result payload", tasks[1])

    def test_compiler_repairs_failed_validation_against_original_parent(self) -> None:
        """验证 Compiler 接收静态校验错误，并以新事务替换无效候选。"""

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            store = _store(root)
            parent = store.resolve("harness_v0001")
            intervention = _intervention_artifact(root, parent)
            manifest = json.loads(parent.read_text("harness.json"))
            manifest["extensions"] = [
                {
                    "instance_id": "candidate_hook",
                    "entrypoint": "extensions/candidate_hook/plugin.py:build",
                    "config": {},
                    "evolution_policy": "mutable",
                }
            ]
            manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2)
            outputs = [
                _compiler_answer(manifest_text, "def build(:\n"),
                _compiler_answer(manifest_text, HOOK_PLUGIN),
            ]
            tasks: list[str] = []
            backend = LocalEvolutionBackend(
                store=store,
                config=LocalEvolutionBackendConfig(
                    compiler_plugins_root=root / "unused-compiler-plugins",
                    compiler_validation_repair_limit=1,
                ),
            )

            with patch(
                "search_harness.evolution.backend.build_compiler_loop",
                side_effect=lambda **kwargs: CompletedLoop(outputs, tasks),
            ):
                candidate = backend.compile_candidate(
                    parent_version="harness_v0001",
                    intervention=intervention,
                    output_file=root / "compiler.json",
                )
            log = json.loads((root / "compiler.json").read_text(encoding="utf-8"))
            iteration_statuses = [
                summary.status for summary in store.list_iterations()
            ]

        self.assertTrue(candidate.validation_passed)
        self.assertEqual(len(log["attempts"]), 2)
        self.assertFalse(log["attempts"][0]["validation"]["passed"])
        self.assertIn("Python compile failed", tasks[1])
        self.assertEqual(iteration_statuses, ["rejected", "pending"])

    def test_critic_acceptance_commits_candidate_and_resume_is_idempotent(self) -> None:
        """验证 Critic accept 是提交候选的唯一语义入口，终态恢复不重跑评审。"""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            store = _store(root)
            backend = FakeBackend(store, ["accept"])
            runner = _runner(root, store, backend, max_iterations=1)
            runner.initialize(_examples())

            first = runner.run()
            second = runner.run()

            self.assertEqual(first.status, "completed")
            self.assertEqual(first.accepted_iterations, 1)
            self.assertEqual(second.latest_version, "harness_v0002")
            self.assertEqual(backend.review_calls, 1)
            self.assertEqual(len(store.list_versions()), 2)
            decision = json.loads(
                (root / "evolution-run/iterations/0001/decision.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(decision["decision"], "accept")
            self.assertAlmostEqual(
                decision["metric_delta"]["answers"]["accuracy"], 0.1
            )

    def test_rejection_is_remembered_by_the_next_failure_analysis(self) -> None:
        """验证拒绝尝试不会入库，并以有界摘要传给下一轮 Critic。"""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            store = _store(root)
            backend = FakeBackend(store, ["reject", "accept"])
            runner = _runner(root, store, backend, max_iterations=2)
            runner.initialize(_examples())

            outcome = runner.run()

            self.assertEqual(outcome.accepted_iterations, 1)
            self.assertEqual(len(backend.failure_memories), 2)
            self.assertEqual(backend.accepted_evaluation_calls, 1)
            self.assertEqual(backend.failure_memories[0], ())
            self.assertEqual(
                backend.failure_memories[1][0]["reason"], "Decision: reject"
            )
            self.assertAlmostEqual(
                backend.failure_memories[1][0]["metric_delta"]["answers"]["accuracy"],
                0.1,
            )

    def test_resume_reconciles_accept_committed_before_runner_event(self) -> None:
        """验证 Git 提交后进程中断时可对账恢复，且不会重复调用 candidate review。"""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            store = _store(root)
            backend = FakeBackend(store, ["accept"])
            runner = _runner(root, store, backend, max_iterations=1)
            runner.initialize(_examples())

            def commit_then_crash(iteration, candidate, evaluation, review):
                session = store.resume_iteration(candidate.iteration_id)
                session.accept(
                    summary=candidate.summary,
                    evaluation={"metrics": evaluation.metrics},
                )
                raise RuntimeError("simulated crash after Version Store commit")

            with patch.object(runner, "_accept_candidate", side_effect=commit_then_crash):
                with self.assertRaisesRegex(RuntimeError, "simulated crash"):
                    runner.run()

            outcome = runner.run()

            self.assertEqual(outcome.latest_version, "harness_v0002")
            self.assertEqual(outcome.accepted_iterations, 1)
            self.assertEqual(backend.review_calls, 1)

    def test_reports_stages_decision_and_reused_terminal_run(self) -> None:
        """验证阶段、决策和终态恢复均产生可观察的结构化进度事件。"""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            store = _store(root)
            backend = FakeBackend(store, ["accept"])
            reporter = RecordingReporter()
            runner = _runner(
                root,
                store,
                backend,
                max_iterations=1,
                reporter=reporter,
            )
            runner.initialize(_examples())

            runner.run()
            runner.run()

            started_stages = {
                event.stage
                for event in reporter.events
                if event.event_type == "stage_started"
            }
            self.assertEqual(
                started_stages,
                {
                    "incumbent_evaluation",
                    "failure_critic",
                    "direction_intervention",
                    "compiler",
                    "candidate_evaluation",
                    "candidate_review",
                },
            )
            self.assertTrue(
                any(event.event_type == "decision" for event in reporter.events)
            )
            self.assertTrue(
                any(
                    event.message == "Evolution run already completed"
                    for event in reporter.events
                )
            )

    def test_compiler_clarification_returns_to_coordinator_before_retry(self) -> None:
        """验证 Compiler 反馈触发同轮补充实验，并重新编译而非结束 run。"""

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            store = _store(root)
            backend = ClarifyingBackend(store)
            runner = _runner(root, store, backend, max_iterations=1)
            runner.initialize(_examples())

            outcome = runner.run()
            iteration_statuses = [item.status for item in store.list_iterations()]
            event_types = [event.event_type for event in runner.journal.events()]

        self.assertEqual(outcome.status, "completed")
        self.assertEqual(outcome.accepted_iterations, 1)
        self.assertEqual(backend.compile_calls, 2)
        self.assertEqual(
            backend.refinement_feedback,
            ["Test the generic post-tool decision rule."],
        )
        self.assertEqual(
            iteration_statuses,
            ["rejected", "accepted"],
        )
        self.assertIn("compiler_clarification_requested", event_types)
        self.assertIn("direction_intervention_revised", event_types)

    def test_inconclusive_intervention_continues_until_supported(self) -> None:
        """验证 inconclusive 继承既有证据续验，成功后再进入 Compiler。"""

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            store = _store(root)
            backend = ContinuingInterventionBackend(
                store, ["inconclusive", "inconclusive", "supported"]
            )
            runner = _runner(root, store, backend, max_iterations=1)
            runner.initialize(_examples())

            outcome = runner.run()
            continuation_events = [
                event
                for event in runner.journal.events()
                if event.event_type == "direction_intervention_continued"
            ]

        self.assertEqual(outcome.status, "completed")
        self.assertEqual(outcome.accepted_iterations, 1)
        self.assertEqual(len(backend.continued_logs), 2)
        self.assertEqual(len(continuation_events), 2)
        self.assertEqual(
            backend.continued_logs[1],
            Path(continuation_events[0].payload["log_file"]),
        )

    def test_inconclusive_intervention_stops_after_continuation_limit(self) -> None:
        """验证续验预算耗尽后才以 no_supported_strategy 结束。"""

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            store = _store(root)
            backend = ContinuingInterventionBackend(
                store, ["inconclusive", "inconclusive", "inconclusive"]
            )
            runner = _runner(root, store, backend, max_iterations=1)
            runner.initialize(_examples())

            outcome = runner.run()

        self.assertEqual(outcome.status, "no_supported_strategy")
        self.assertEqual(len(backend.continued_logs), 2)
        self.assertEqual(backend.compile_calls, 0)


def _runner(
    root: Path,
    store: HarnessVersionStore,
    backend: FakeBackend,
    *,
    max_iterations: int,
    reporter: RecordingReporter | None = None,
) -> EvolutionRunner:
    return EvolutionRunner(
        run_dir=root / "evolution-run",
        store=store,
        backend=backend,
        config=EvolutionConfig(
            max_iterations=max_iterations,
            experience_limit=2,
            failure_memory_limit=3,
        ),
        progress_reporter=reporter,
    )


def _examples() -> list[DatasetExample]:
    return [
        DatasetExample(example_id="a", question="Question A?", answer="A"),
        DatasetExample(example_id="b", question="Question B?", answer="B"),
    ]


def _store(root: Path) -> HarnessVersionStore:
    store = HarnessVersionStore(root / "versions")
    store.initialize(_plugins_root(root))
    return store


def _plugins_root(root: Path) -> Path:
    plugins = root / "plugins-source"
    prompt = plugins / "prompts" / "base"
    prompt.mkdir(parents=True)
    (prompt / "plugin.py").write_text(PROMPT_PLUGIN, encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "harness_id": "test_harness",
        "tools": [],
        "prompt": {
            "instance_id": "base_prompt",
            "entrypoint": "prompts/base/plugin.py:build",
            "config": {},
            "evolution_policy": "fixed",
        },
        "extensions": [],
    }
    (plugins / "harness.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return plugins


def _write_log(path: Path, result: CriticResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"critic_result": result.to_dict()}, ensure_ascii=False),
        encoding="utf-8",
    )


def _intervention_artifact(root: Path, parent) -> InterventionArtifact:
    critic_log = root / "critic.json"
    critic_log.write_text("{}", encoding="utf-8")
    result = InterventionCoordinatorResult(
        analysis="Two cases support the same scheme.",
        verdict="supported",
        selected_trial_id="trial_001",
        recommendation="Add the validated post-tool guidance Hook.",
    )
    direction = {
        "problem": "premature completion",
        "observed_pattern": "answers stop after one retrieval",
        "excluded_causes": ["retriever outage"],
        "desired_behavior": "continue when evidence is incomplete",
        "success_criteria": ["more correct answers"],
        "constraints": ["bounded intervention"],
    }
    log_file = root / "coordinator.json"
    log_file.write_text(
        json.dumps(
            {
                "direction_source": {
                    "critic_log": str(critic_log),
                    "direction_index": 0,
                    "critic_analysis": "Repeated premature completion.",
                    "problem_direction": direction,
                    "critic_inputs": {
                        "harness_version": parent.version_id,
                        "harness_digest": parent.digest,
                        "iteration": None,
                    },
                },
                "coordinator_result": result.to_dict(),
                "trials": [
                    {
                        "trial_id": "trial_001",
                        "example_id": "a",
                        "status": "completed",
                        "hook_guidance": {"post_tool": "Continue if evidence is incomplete."},
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return InterventionArtifact(log_file=log_file, result=result)


def _compiler_answer(manifest: str, plugin: str) -> str:
    return json.dumps(
        {
            "summary": "Add candidate Hook",
            "edits": [
                {
                    "operation": "write",
                    "path": "extensions/candidate_hook/plugin.py",
                    "content": plugin,
                },
                {
                    "operation": "write",
                    "path": "harness.json",
                    "content": manifest,
                },
            ],
            "clarification": None,
        },
        ensure_ascii=False,
    )
