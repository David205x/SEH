from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from search_harness.registry import build_harness
from search_harness.versioning import (
    CandidateWorkspace,
    FileEdit,
    HarnessSnapshot,
    HarnessVersionStore,
)


PROMPT_PLUGIN = '''from search_harness.core import ChatMessage, ModelInput

class Prompt:
    def build(self, state):
        return ModelInput.from_messages([ChatMessage(role="user", content=state.question)])

def build(config, context, tools):
    return Prompt()
'''

HOOK_HELPER = '''from search_harness.core import BaseHook, HookPhase

class AddedHook(BaseHook):
    def __init__(self):
        super().__init__(hook_id="added_hook", phases=frozenset({HookPhase.PRE_PROMPT}))

    def handle(self, context):
        pass
'''

HOOK_PLUGIN = '''from .hook_impl import AddedHook

def build(config, context):
    return AddedHook()
'''

INVALID_STAGE_HOOK = '''from search_harness.core import BaseHook, HookPhase

class InvalidStageHook(BaseHook):
    def __init__(self):
        super().__init__(hook_id="invalid_stage", phases=frozenset({HookPhase.POST_TOOL}))

    def handle(self, context):
        context.state.get("stage.model_input")

def build(config, context):
    return InvalidStageHook()
'''

INVALID_ATTRIBUTE_HOOK = '''from search_harness.core import BaseHook, HookPhase

class InvalidAttributeHook(BaseHook):
    def __init__(self):
        super().__init__(hook_id="invalid_attribute", phases=frozenset({HookPhase.PRE_FINAL}))

    def handle(self, context):
        decision = context.state.get("stage.final_decision")
        if decision.is_accepted:
            return

def build(config, context):
    return InvalidAttributeHook()
'''

DYNAMIC_ATTRIBUTE_HOOK = '''from search_harness.core import BaseHook, HookPhase

class DynamicAttributeHook(BaseHook):
    def __init__(self):
        super().__init__(hook_id="dynamic_attribute", phases=frozenset({HookPhase.PRE_PROMPT}))

    def handle(self, context):
        getattr(context, "missing", None)

def build(config, context):
    return DynamicAttributeHook()
'''


class CandidateWorkspaceTest(TestCase):
    def test_transaction_rolls_back_all_file_changes(self) -> None:
        """Verifies the transaction rolls back all file changes contract."""
        with TemporaryDirectory() as tmpdir:
            root = _make_plugins_root(Path(tmpdir))
            snapshot = HarnessSnapshot.from_directory(root)
            workspace = CandidateWorkspace(snapshot)

            with self.assertRaisesRegex(RuntimeError, "abort"):
                with workspace.transaction():
                    workspace.write_text("extensions/example/plugin.py", "value = 1\n")
                    workspace.write_text("harness.json", "{}")
                    raise RuntimeError("abort")

            self.assertEqual(workspace.changed_paths, ())
            self.assertEqual(workspace.digest, snapshot.digest)

    def test_add_extension_always_writes_mutable_policy(self) -> None:
        """Verifies the add extension always writes mutable policy contract."""
        with TemporaryDirectory() as tmpdir:
            root = _make_plugins_root(Path(tmpdir))
            workspace = CandidateWorkspace(HarnessSnapshot.from_directory(root))

            workspace.add_extension(
                instance_id="added_hook",
                files={"plugin.py": HOOK_PLUGIN, "hook_impl.py": HOOK_HELPER},
            )
            manifest = json.loads(workspace.read_text("harness.json"))

        self.assertEqual(manifest["extensions"][0]["evolution_policy"], "mutable")

    def test_file_patch_is_atomic_when_one_edit_fails(self) -> None:
        """Verifies the file patch is atomic when one edit fails contract."""
        with TemporaryDirectory() as tmpdir:
            root = _make_plugins_root(Path(tmpdir))
            workspace = CandidateWorkspace(HarnessSnapshot.from_directory(root))

            with self.assertRaises(FileNotFoundError):
                workspace.apply_patch(
                    (
                        FileEdit("write", "extensions/new/helper.py", "VALUE = 1\n"),
                        FileEdit("delete", "extensions/missing/plugin.py"),
                    )
                )

            self.assertFalse(workspace.exists("extensions/new/helper.py"))
            self.assertEqual(workspace.changed_paths, ())


class HarnessVersionStoreTest(TestCase):
    def test_accepts_and_resolves_multifile_extension_without_copying_candidate(self) -> None:
        """Verifies the accepts and resolves multifile extension without copying candidate contract."""
        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            plugins_root = _make_plugins_root(base)
            store = HarnessVersionStore(base / "versions")
            first = store.initialize(plugins_root)
            workspace = store.open_workspace(first.version_id)
            workspace.add_extension(
                instance_id="added_hook",
                files={"plugin.py": HOOK_PLUGIN, "hook_impl.py": HOOK_HELPER},
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
                assembled = build_harness(staged)

        self.assertEqual(first.version_id, "harness_v0001")
        self.assertEqual(second.parent_version, first.version_id)
        self.assertEqual(dict(second.evaluation), {"accuracy": 0.5})
        self.assertNotIn(
            Path("extensions/added_hook/plugin.py").as_posix(),
            {str(path) for path in old_snapshot.files},
        )
        self.assertIn("extensions/added_hook/plugin.py", {str(path) for path in new_snapshot.files})
        self.assertEqual([hook.hook_id for hook in assembled.hooks.hooks], ["added_hook"])

    def test_validation_rejects_fixed_files_and_new_fixed_components(self) -> None:
        """Verifies the validation rejects fixed files and new fixed components contract."""
        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            store = HarnessVersionStore(base / "versions")
            first = store.initialize(_make_plugins_root(base))

            fixed_edit = store.open_workspace(first.version_id)
            fixed_edit.write_text("prompts/base/plugin.py", "broken = True\n")
            fixed_report = store.validate(fixed_edit)

            new_fixed = store.open_workspace(first.version_id)
            manifest = json.loads(new_fixed.read_text("harness.json"))
            manifest["extensions"].append(
                {
                    "instance_id": "forbidden",
                    "entrypoint": "extensions/forbidden/plugin.py:build",
                    "enabled": False,
                    "config": {},
                    "evolution_policy": "fixed",
                }
            )
            new_fixed.write_text(
                "extensions/forbidden/plugin.py",
                "def build(config, context):\n    return ()\n",
            )
            new_fixed.write_text("harness.json", json.dumps(manifest))
            policy_report = store.validate(new_fixed)

        self.assertFalse(fixed_report.passed)
        self.assertTrue(any("fixed component file" in item for item in fixed_report.errors))
        self.assertFalse(policy_report.passed)
        self.assertTrue(any("new component must be mutable" in item for item in policy_report.errors))

    def test_validation_reports_python_syntax_errors(self) -> None:
        """Verifies the validation reports python syntax errors contract."""
        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            store = HarnessVersionStore(base / "versions")
            first = store.initialize(_make_plugins_root(base))
            workspace = store.open_workspace(first.version_id)
            workspace.add_extension(
                instance_id="invalid",
                files={"plugin.py": "def build(:\n    pass\n"},
                enabled=False,
            )

            report = store.validate(workspace)

        self.assertFalse(report.passed)
        self.assertTrue(any("Python compile failed" in item for item in report.errors))

    def test_validation_rejects_stage_access_outside_subscribed_phase(self) -> None:
        """验证候选 Hook 不能读取当前 phase 不存在的 stage 状态。"""

        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            store = HarnessVersionStore(base / "versions")
            first = store.initialize(_make_plugins_root(base))
            workspace = store.open_workspace(first.version_id)
            workspace.add_extension(
                instance_id="invalid_stage",
                files={"plugin.py": INVALID_STAGE_HOOK},
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
            store = HarnessVersionStore(base / "versions")
            first = store.initialize(_make_plugins_root(base))
            workspace = store.open_workspace(first.version_id)
            workspace.add_extension(
                instance_id="invalid_attribute",
                files={"plugin.py": INVALID_ATTRIBUTE_HOOK},
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

    def test_validation_rejects_dynamic_attribute_builtins(self) -> None:
        """验证候选源码不能用动态属性访问掩盖错误接口假设。"""

        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            store = HarnessVersionStore(base / "versions")
            first = store.initialize(_make_plugins_root(base))
            workspace = store.open_workspace(first.version_id)
            workspace.add_extension(
                instance_id="dynamic_attribute",
                files={"plugin.py": DYNAMIC_ATTRIBUTE_HOOK},
            )

            report = store.validate(workspace)

        self.assertFalse(report.passed)
        self.assertTrue(
            any("dynamic attribute builtin 'getattr' is forbidden" in error for error in report.errors),
            report.errors,
        )


class IterationJournalTest(TestCase):
    def test_resumes_patch_and_accepts_without_losing_iteration_history(self) -> None:
        """Verifies the resumes patch and accepts without losing iteration history contract."""
        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            store_root = base / "versions"
            store = HarnessVersionStore(store_root)
            first = store.initialize(_make_plugins_root(base))
            session = store.start_iteration(metadata={"experiment": "resume-test"})
            session.add_extension(
                instance_id="added_hook",
                files={"plugin.py": HOOK_PLUGIN, "hook_impl.py": HOOK_HELPER},
            )
            iteration_id = session.iteration_id
            candidate_digest = session.digest

            reopened = HarnessVersionStore(store_root)
            resumed = reopened.resume_iteration(iteration_id)
            self.assertEqual(resumed.parent_version, first.version_id)
            self.assertEqual(resumed.digest, candidate_digest)
            self.assertIn("AddedHook", resumed.read_text("extensions/added_hook/hook_impl.py"))
            report = resumed.validate()
            self.assertTrue(report.passed, report.errors)
            accepted = resumed.accept(summary="Accept resumed hook")
            summary = reopened.list_iterations()[0]

        self.assertEqual(summary.status, "accepted")
        self.assertEqual(summary.patch_count, 1)
        self.assertEqual(summary.accepted_version, accepted.version_id)
        self.assertEqual(accepted.iteration_id, iteration_id)

    def test_rejected_iteration_remains_auditable_but_cannot_resume(self) -> None:
        """Verifies the rejected iteration remains auditable but cannot resume contract."""
        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            store = HarnessVersionStore(base / "versions")
            store.initialize(_make_plugins_root(base))
            session = store.start_iteration()
            session.apply_patch(
                (FileEdit("write", "extensions/note.txt", "candidate\n"),)
            )
            session.reject("No measurable improvement", evaluation={"accuracy": 0.0})
            summary = store.list_iterations()[0]

            with self.assertRaisesRegex(RuntimeError, "already rejected"):
                store.resume_iteration(session.iteration_id)

        self.assertEqual(summary.status, "rejected")
        self.assertEqual(summary.rejection_reason, "No measurable improvement")
        self.assertEqual(summary.patch_count, 1)

    def test_workspace_rolls_back_when_patch_cannot_be_journaled(self) -> None:
        """Verifies the workspace rolls back when patch cannot be journaled contract."""
        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            store = HarnessVersionStore(base / "versions")
            first = store.initialize(_make_plugins_root(base))
            session = store.start_iteration()
            parent_digest = store.resolve(first.version_id).digest

            with patch.object(
                store.iteration_journal,
                "append_patch",
                side_effect=OSError("disk unavailable"),
            ):
                with self.assertRaisesRegex(OSError, "disk unavailable"):
                    session.apply_patch(
                        (FileEdit("write", "extensions/note.txt", "candidate\n"),)
                    )

            summary = store.list_iterations()[0]

        self.assertEqual(session.digest, parent_digest)
        self.assertFalse(session.exists("extensions/note.txt"))
        self.assertEqual(summary.patch_count, 0)


def _make_plugins_root(base: Path) -> Path:
    root = base / "plugins-source"
    prompt_dir = root / "prompts" / "base"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "plugin.py").write_text(PROMPT_PLUGIN, encoding="utf-8")
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
    (root / "harness.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    return root
