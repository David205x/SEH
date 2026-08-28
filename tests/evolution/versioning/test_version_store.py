from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from search_harness.framework.harness import assemble_harness_components
from search_harness.evolution.versioning import (
    CandidateWorkspace,
    FileEdit,
    HarnessSnapshot,
    TemplateVersionStore,
)


PROMPT_COMPONENT = '''from search_harness.framework import ChatMessage, ModelInput

class Prompt:
    def build(self, state):
        return ModelInput.from_messages(
            [ChatMessage(role="user", content=state.question)]
        )

def build(config, context, tools):
    return Prompt()
'''

OUTPUT_COMPONENT = '''from search_harness.framework.harness import TaggedOutputParser

def build(config, context):
    return TaggedOutputParser()
'''

HOOK_HELPER = '''from search_harness.framework import BaseHook, HookPhase

class AddedHook(BaseHook):
    def __init__(self):
        super().__init__(hook_id="added_hook", phases=frozenset({HookPhase.PRE_PROMPT}))

    def handle(self, context):
        pass
'''

HOOK_COMPONENT = '''from .hook_impl import AddedHook

def build(config, context):
    return AddedHook()
'''

INVALID_STAGE_HOOK = '''from search_harness.framework import BaseHook, HookPhase

class InvalidStageHook(BaseHook):
    def __init__(self):
        super().__init__(
            hook_id="invalid_stage",
            phases=frozenset({HookPhase.POST_TOOL}),
        )

    def handle(self, context):
        context.state.get("stage.model_input")

def build(config, context):
    return InvalidStageHook()
'''

INVALID_ATTRIBUTE_HOOK = '''from search_harness.framework import BaseHook, HookPhase

class InvalidAttributeHook(BaseHook):
    def __init__(self):
        super().__init__(
            hook_id="invalid_attribute",
            phases=frozenset({HookPhase.PRE_FINAL}),
        )

    def handle(self, context):
        decision = context.state.get("stage.final_decision")
        if decision.is_accepted:
            return

def build(config, context):
    return InvalidAttributeHook()
'''

DYNAMIC_ATTRIBUTE_HOOK = '''from search_harness.framework import BaseHook, HookPhase

class DynamicAttributeHook(BaseHook):
    def __init__(self):
        super().__init__(
            hook_id="dynamic_attribute",
            phases=frozenset({HookPhase.PRE_PROMPT}),
        )

    def handle(self, context):
        getattr(context, "missing", None)

def build(config, context):
    return DynamicAttributeHook()
'''

INVALID_TRACE_ATTRIBUTE_HOOK = '''\
from search_harness.framework import BaseHook, HookPhase

class InvalidTraceAttributeHook(BaseHook):
    def __init__(self):
        super().__init__(
            hook_id="invalid_trace_attribute",
            phases=frozenset({HookPhase.POST_PROMPT}),
        )

    def handle(self, context):
        for event in context.trajectory:
            if event.kind == "final_deferred":
                return

def build(config, context):
    return InvalidTraceAttributeHook()
'''

DUPLICATE_PIPELINE_HOOK = '''\
from search_harness.framework import BaseHook, HookPhase

class DuplicatePipelineHook(BaseHook):
    def __init__(self):
        super().__init__(
            hook_id="shared_pipeline_id",
            phases=frozenset({HookPhase.PRE_PROMPT}),
        )

    def handle(self, context):
        pass

def build(config, context):
    return DuplicatePipelineHook()
'''

SECOND_INVOCATION_FAILURE_HOOK = '''\
from search_harness.framework import BaseHook, HookPhase, StateRef

_COUNT = StateRef(
    key="extension.second_invocation.count",
    owner="second_invocation",
    value_type=int,
    writers=frozenset({"second_invocation"}),
    default=0,
)

class SecondInvocationHook(BaseHook):
    def __init__(self):
        super().__init__(
            hook_id="second_invocation",
            phases=frozenset({HookPhase.POST_TOOL}),
            state_refs=(_COUNT,),
        )

    def handle(self, context):
        count = context.state.get(_COUNT.key)
        if count >= 1:
            raise RuntimeError("second post_tool invocation failed")
        context.state.set(_COUNT.key, count + 1)

def build(config, context):
    return SecondInvocationHook()
'''

CROSS_PHASE_STATE_FAILURE_HOOK = '''\
from search_harness.framework import BaseHook, HookPhase, StateRef

_READY = StateRef(
    key="extension.cross_phase.ready",
    owner="cross_phase",
    value_type=bool,
    writers=frozenset({"cross_phase"}),
    default=False,
)

class CrossPhaseStateHook(BaseHook):
    def __init__(self):
        super().__init__(
            hook_id="cross_phase",
            phases=frozenset({HookPhase.POST_TOOL, HookPhase.PRE_FINAL}),
            state_refs=(_READY,),
        )

    def handle(self, context):
        if context.phase == HookPhase.POST_TOOL:
            context.state.set(_READY.key, True)
            return
        if context.state.get(_READY.key):
            raise RuntimeError("post_tool state reached pre_final")

def build(config, context):
    return CrossPhaseStateHook()
'''


class CandidateWorkspaceTest(TestCase):
    def test_transaction_rolls_back_all_file_changes(self) -> None:
        """Verifies the transaction rolls back all file changes contract."""
        with TemporaryDirectory() as tmpdir:
            root = _make_template_root(Path(tmpdir))
            snapshot = HarnessSnapshot.from_directory(root)
            workspace = CandidateWorkspace(snapshot)

            with self.assertRaisesRegex(RuntimeError, "abort"):
                with workspace.transaction():
                    workspace.write_text(
                        "extensions/example/component.py",
                        "value = 1\n",
                    )
                    workspace.write_text("harness.json", "{}")
                    raise RuntimeError("abort")

            self.assertEqual(workspace.changed_paths, ())
            self.assertEqual(workspace.digest, snapshot.digest)

    def test_add_extension_writes_separate_mutable_policy(self) -> None:
        """Verifies the add extension always writes mutable policy contract."""
        with TemporaryDirectory() as tmpdir:
            root = _make_template_root(Path(tmpdir))
            workspace = CandidateWorkspace(HarnessSnapshot.from_directory(root))

            workspace.add_extension(
                instance_id="added_hook",
                files={"component.py": HOOK_COMPONENT, "hook_impl.py": HOOK_HELPER},
            )
            manifest = json.loads(workspace.read_text("harness.json"))
            policy = json.loads(workspace.read_text("evolution.json"))

        self.assertNotIn("evolution_policy", manifest["extensions"][0])
        self.assertEqual(policy["components"]["added_hook"], "mutable")

    def test_file_patch_is_atomic_when_one_edit_fails(self) -> None:
        """Verifies the file patch is atomic when one edit fails contract."""
        with TemporaryDirectory() as tmpdir:
            root = _make_template_root(Path(tmpdir))
            workspace = CandidateWorkspace(HarnessSnapshot.from_directory(root))

            with self.assertRaises(FileNotFoundError):
                workspace.apply_patch(
                    (
                        FileEdit(
                            "write",
                            "extensions/new/helper.py",
                            "VALUE = 1\n",
                        ),
                        FileEdit(
                            "delete",
                            "extensions/missing/component.py",
                        ),
                    )
                )

            self.assertFalse(
                workspace.exists("extensions/new/helper.py")
            )
            self.assertEqual(workspace.changed_paths, ())


class TemplateVersionStoreTest(TestCase):
    def test_writes_current_version_store_metadata_schema(self) -> None:
        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            store = TemplateVersionStore(base / "versions")
            store.initialize(
                _make_template_root(base),
                version_store_id="test_store",
            )
            metadata = json.loads(
                store.metadata_file.read_text(encoding="utf-8")
            )

        self.assertEqual(metadata["schema_version"], 3)
        self.assertEqual(metadata["version_store_id"], "test_store")
        self.assertNotIn("checkpoint_store_id", metadata)

    def test_rejects_previous_version_store_metadata_schema(self) -> None:
        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            store = TemplateVersionStore(base / "versions")
            store.initialize(_make_template_root(base))
            store.metadata_file.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "version_store_id": "old_store",
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                _ = store.version_store_id

    def test_accepts_and_resolves_multifile_extension(self) -> None:
        """Verify accepting a multi-file extension does not copy its candidate."""
        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            template_root = _make_template_root(base)
            store = TemplateVersionStore(base / "versions")
            first = store.initialize(template_root)
            workspace = store.open_workspace(first.version_id)
            workspace.add_extension(
                instance_id="added_hook",
                files={"component.py": HOOK_COMPONENT, "hook_impl.py": HOOK_HELPER},
            )

            report = store.validate(workspace)
            self.assertTrue(report.passed, report.errors)
            second = store.accept(
                workspace,
                summary="Add a multi-file hook",
                evaluation={"accuracy": 0.5},
            )
            old_snapshot = store.resolve(first.version_id)
            new_snapshot = store.resolve(second.version_id)
            with store.stage(new_snapshot) as staged:
                assembled = assemble_harness_components(staged)

        self.assertEqual(first.version_id, "harness_v0001")
        self.assertEqual(second.parent_version, first.version_id)
        self.assertEqual(dict(second.evaluation), {"accuracy": 0.5})
        self.assertNotIn(
            Path("extensions/added_hook/component.py").as_posix(),
            {str(path) for path in old_snapshot.files},
        )
        self.assertIn(
            "extensions/added_hook/component.py",
            {str(path) for path in new_snapshot.files},
        )
        self.assertEqual(
            [
                hook.hook_id
                for binding in assembled.extensions
                for hook in binding.components
            ],
            ["added_hook"],
        )

    def test_validation_rejects_fixed_files_and_new_fixed_components(self) -> None:
        """Verify validation rejects fixed files and new fixed components."""
        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            store = TemplateVersionStore(base / "versions")
            first = store.initialize(_make_template_root(base))

            fixed_edit = store.open_workspace(first.version_id)
            fixed_edit.write_text(
                "prompt/component.py",
                "broken = True\n",
            )
            fixed_report = store.validate(fixed_edit)

            new_fixed = store.open_workspace(first.version_id)
            manifest = json.loads(new_fixed.read_text("harness.json"))
            manifest["extensions"].append(
                {
                    "instance_id": "forbidden",
                    "entrypoint": (
                        "extensions/forbidden/component.py:build"
                    ),
                    "enabled": False,
                    "config": {},
                }
            )
            new_fixed.write_text(
                "extensions/forbidden/component.py",
                "def build(config, context):\n    return ()\n",
            )
            new_fixed.write_text("harness.json", json.dumps(manifest))
            policy = json.loads(new_fixed.read_text("evolution.json"))
            policy["components"]["forbidden"] = "fixed"
            new_fixed.write_text("evolution.json", json.dumps(policy))
            policy_report = store.validate(new_fixed)

        self.assertFalse(fixed_report.passed)
        self.assertTrue(
            any("fixed component file" in item for item in fixed_report.errors)
        )
        self.assertFalse(policy_report.passed)
        self.assertTrue(
            any(
                "new component must be mutable" in item
                for item in policy_report.errors
            )
        )

    def test_validation_reports_python_syntax_errors(self) -> None:
        """Verifies the validation reports python syntax errors contract."""
        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            store = TemplateVersionStore(base / "versions")
            first = store.initialize(_make_template_root(base))
            workspace = store.open_workspace(first.version_id)
            workspace.add_extension(
                instance_id="invalid",
                files={"component.py": "def build(:\n    pass\n"},
                enabled=False,
            )

            report = store.validate(workspace)

        self.assertFalse(report.passed)
        self.assertTrue(any("Python compile failed" in item for item in report.errors))

    def test_validation_rejects_stage_access_outside_subscribed_phase(self) -> None:
        """验证候选 Hook 不能读取当前 phase 不存在的 stage 状态。"""

        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            store = TemplateVersionStore(base / "versions")
            first = store.initialize(_make_template_root(base))
            workspace = store.open_workspace(first.version_id)
            workspace.add_extension(
                instance_id="invalid_stage",
                files={"component.py": INVALID_STAGE_HOOK},
            )

            report = store.validate(workspace)

        self.assertFalse(report.passed)
        self.assertTrue(
            any(
                "Hook contract failed for invalid_stage at post_tool" in error
                and "stage.model_input" in error
                for error in report.errors
            ),
            report.errors,
        )

    def test_validation_reports_any_hook_phase_exception(self) -> None:
        """验证 Hook 使用不存在的运行时属性时 deterministic validation 失败。"""

        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            store = TemplateVersionStore(base / "versions")
            first = store.initialize(_make_template_root(base))
            workspace = store.open_workspace(first.version_id)
            workspace.add_extension(
                instance_id="invalid_attribute",
                files={"component.py": INVALID_ATTRIBUTE_HOOK},
            )

            report = store.validate(workspace)

        self.assertFalse(report.passed)
        self.assertTrue(
            any(
                "Hook contract failed for invalid_attribute at pre_final" in error
                and "is_accepted" in error
                for error in report.errors
            ),
            report.errors,
        )

    def test_validation_exercises_hook_against_non_empty_trace(self) -> None:
        """验证契约 smoke 能发现仅在遍历历史事件时暴露的错误属性。"""

        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            store = TemplateVersionStore(base / "versions")
            first = store.initialize(_make_template_root(base))
            workspace = store.open_workspace(first.version_id)
            workspace.add_extension(
                instance_id="invalid_trace_attribute",
                files={"component.py": INVALID_TRACE_ATTRIBUTE_HOOK},
            )

            report = store.validate(workspace)

        self.assertFalse(report.passed)
        self.assertTrue(
            any(
                "Hook contract failed for invalid_trace_attribute at post_prompt"
                in error
                and "kind" in error
                for error in report.errors
            ),
            report.errors,
        )

    def test_validation_rejects_combined_pipeline_hook_id_conflict(self) -> None:
        """验证单个 Hook 合法但完整 Pipeline 的重复 ID 会被拒绝。"""

        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            store = TemplateVersionStore(base / "versions")
            first = store.initialize(_make_template_root(base))
            workspace = store.open_workspace(first.version_id)
            workspace.add_extension(
                instance_id="pipeline_hook_one",
                files={"component.py": DUPLICATE_PIPELINE_HOOK},
            )
            workspace.add_extension(
                instance_id="pipeline_hook_two",
                files={"component.py": DUPLICATE_PIPELINE_HOOK},
            )

            report = store.validate(workspace)

        self.assertFalse(report.passed)
        self.assertTrue(
            any(
                "Hook pipeline construction failed" in error
                and "duplicate hook_id" in error
                for error in report.errors
            ),
            report.errors,
        )

    def test_validation_reuses_rollout_state_across_phase_invocations(self) -> None:
        """验证 lifecycle smoke 会复用状态并重复执行订阅 phase。"""

        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            store = TemplateVersionStore(base / "versions")
            first = store.initialize(_make_template_root(base))
            workspace = store.open_workspace(first.version_id)
            workspace.add_extension(
                instance_id="second_invocation",
                files={"component.py": SECOND_INVOCATION_FAILURE_HOOK},
            )

            report = store.validate(workspace)

        self.assertFalse(report.passed)
        self.assertTrue(
            any(
                "Hook pipeline lifecycle failed" in error
                and "iteration 2, phase post_tool" in error
                and "second post_tool invocation failed" in error
                for error in report.errors
            ),
            report.errors,
        )

    def test_validation_carries_state_between_lifecycle_phases(self) -> None:
        """验证 tool branch 写入的状态会进入后续 final branch。"""

        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            store = TemplateVersionStore(base / "versions")
            first = store.initialize(_make_template_root(base))
            workspace = store.open_workspace(first.version_id)
            workspace.add_extension(
                instance_id="cross_phase",
                files={"component.py": CROSS_PHASE_STATE_FAILURE_HOOK},
            )

            report = store.validate(workspace)

        self.assertFalse(report.passed)
        self.assertTrue(
            any(
                "Hook pipeline lifecycle failed" in error
                and "iteration 3, phase pre_final" in error
                and "post_tool state reached pre_final" in error
                for error in report.errors
            ),
            report.errors,
        )

    def test_validation_rejects_dynamic_attribute_builtins(self) -> None:
        """验证候选源码不能用动态属性访问掩盖错误接口假设。"""

        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            store = TemplateVersionStore(base / "versions")
            first = store.initialize(_make_template_root(base))
            workspace = store.open_workspace(first.version_id)
            workspace.add_extension(
                instance_id="dynamic_attribute",
                files={"component.py": DYNAMIC_ATTRIBUTE_HOOK},
            )

            report = store.validate(workspace)

        self.assertFalse(report.passed)
        self.assertTrue(
            any(
                "dynamic attribute builtin 'getattr' is forbidden" in error
                for error in report.errors
            ),
            report.errors,
        )


class CandidateAttemptJournalTest(TestCase):
    def test_writes_candidate_attempt_events_and_records_as_current_schema(
        self,
    ) -> None:
        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            store = TemplateVersionStore(base / "versions")
            store.initialize(_make_template_root(base))
            attempt = store.start_candidate_attempt()
            event = json.loads(
                store.candidate_attempt_file.read_text(encoding="utf-8")
            )
            record = json.loads(
                store.index_file.read_text(encoding="utf-8")
            )

        self.assertEqual(event["schema_version"], 3)
        self.assertEqual(
            event["candidate_attempt_id"],
            attempt.candidate_attempt_id,
        )
        self.assertNotIn("iteration_id", event)
        self.assertEqual(record["schema_version"], 3)
        self.assertIn("candidate_attempt_id", record)
        self.assertNotIn("iteration_id", record)

    def test_rejects_previous_candidate_attempt_schema(self) -> None:
        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            store = TemplateVersionStore(base / "versions")
            first = store.initialize(_make_template_root(base))
            parent = store.resolve(first.version_id)
            old_id = "candidate_attempt_old"
            store.candidate_attempt_file.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "candidate_attempt_id": old_id,
                        "sequence": 0,
                        "event_type": "started",
                        "timestamp": "2026-01-01T00:00:00+00:00",
                        "payload": {
                            "parent_version": first.version_id,
                            "parent_digest": parent.digest,
                            "metadata": {},
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                store.resume_candidate_attempt(old_id)

    def test_rejects_previous_version_record_schema(self) -> None:
        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            store = TemplateVersionStore(base / "versions")
            store.initialize(_make_template_root(base))
            record = json.loads(store.index_file.read_text(encoding="utf-8"))
            record["schema_version"] = 2
            store.index_file.write_text(
                json.dumps(record) + "\n",
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                store.list_versions()

    def test_resumes_patch_without_losing_candidate_attempt_history(self) -> None:
        """Verify resuming and accepting preserves Candidate Attempt history."""
        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            store_root = base / "versions"
            store = TemplateVersionStore(store_root)
            first = store.initialize(_make_template_root(base))
            attempt = store.start_candidate_attempt(
                metadata={"experiment": "resume-test"}
            )
            attempt.add_extension(
                instance_id="added_hook",
                files={"component.py": HOOK_COMPONENT, "hook_impl.py": HOOK_HELPER},
            )
            candidate_attempt_id = attempt.candidate_attempt_id
            candidate_digest = attempt.digest

            reopened = TemplateVersionStore(store_root)
            resumed = reopened.resume_candidate_attempt(candidate_attempt_id)
            self.assertEqual(resumed.parent_version, first.version_id)
            self.assertEqual(resumed.digest, candidate_digest)
            self.assertIn(
                "AddedHook",
                resumed.read_text(
                    "extensions/added_hook/hook_impl.py"
                ),
            )
            report = resumed.validate()
            self.assertTrue(report.passed, report.errors)
            accepted = resumed.accept(summary="Accept resumed hook")
            summary = reopened.list_candidate_attempts()[0]

        self.assertEqual(summary.status, "accepted")
        self.assertEqual(summary.patch_count, 1)
        self.assertEqual(summary.accepted_version, accepted.version_id)
        self.assertEqual(accepted.candidate_attempt_id, candidate_attempt_id)

    def test_rejected_attempt_remains_auditable_but_cannot_resume(self) -> None:
        """Verify a rejected Candidate Attempt remains auditable."""
        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            store = TemplateVersionStore(base / "versions")
            store.initialize(_make_template_root(base))
            attempt = store.start_candidate_attempt()
            attempt.apply_patch(
                (
                    FileEdit(
                        "write",
                        "extensions/note.txt",
                        "candidate\n",
                    ),
                )
            )
            attempt.reject("No measurable improvement", evaluation={"accuracy": 0.0})
            summary = store.list_candidate_attempts()[0]

            with self.assertRaisesRegex(RuntimeError, "already rejected"):
                store.resume_candidate_attempt(attempt.candidate_attempt_id)

        self.assertEqual(summary.status, "rejected")
        self.assertEqual(summary.rejection_reason, "No measurable improvement")
        self.assertEqual(summary.patch_count, 1)

    def test_workspace_rolls_back_when_patch_cannot_be_journaled(self) -> None:
        """Verifies the workspace rolls back when patch cannot be journaled contract."""
        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            store = TemplateVersionStore(base / "versions")
            first = store.initialize(_make_template_root(base))
            attempt = store.start_candidate_attempt()
            parent_digest = store.resolve(first.version_id).digest

            with patch.object(
                store.candidate_attempt_journal,
                "append_patch",
                side_effect=OSError("disk unavailable"),
            ):
                with self.assertRaisesRegex(OSError, "disk unavailable"):
                    attempt.apply_patch(
                        (
                            FileEdit(
                                "write",
                                "extensions/note.txt",
                                "candidate\n",
                            ),
                        )
                    )

            summary = store.list_candidate_attempts()[0]

        self.assertEqual(attempt.digest, parent_digest)
        self.assertFalse(attempt.exists("extensions/note.txt"))
        self.assertEqual(summary.patch_count, 0)


def _make_template_root(base: Path) -> Path:
    root = base / "template-source"
    prompt_dir = root / "prompt"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "component.py").write_text(PROMPT_COMPONENT, encoding="utf-8")
    output_dir = root / "output"
    output_dir.mkdir(parents=True)
    (output_dir / "component.py").write_text(OUTPUT_COMPONENT, encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "harness_id": "test_harness",
        "tools": [],
        "prompt": {
            "instance_id": "base_prompt",
            "entrypoint": "prompt/component.py:build",
            "config": {},
        },
        "output": {
            "instance_id": "tagged_output",
            "entrypoint": "output/component.py:build",
            "config": {},
        },
        "extensions": [],
    }
    (root / "harness.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    (root / "evolution.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "harness_id": "test_harness",
                "components": {
                    "base_prompt": "fixed",
                    "tagged_output": "fixed",
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return root
