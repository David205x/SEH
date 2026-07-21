from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase

from search_harness.adapter.critic.run import _build_context, parse_args
from search_harness.versioning import FileEdit, HarnessVersionStore


BASELINE_PLUGINS_ROOT = (
    Path(__file__).parents[3] / "harness_templates" / "actor" / "baseline" / "plugins"
)
_CANDIDATE_HOOK = '''from search_harness.core import BaseHook, HookPhase

class CandidateHook(BaseHook):
    def __init__(self):
        super().__init__(hook_id="candidate_hook", phases=frozenset({HookPhase.PRE_PROMPT}))

    def handle(self, context):
        return None

def build(config, context):
    return CandidateHook()
'''


class CriticRunTest(TestCase):
    def test_parse_args_accepts_pending_iteration_source(self) -> None:
        """Verifies the parse args accepts pending iteration source contract."""
        args = parse_args(
            [
                "report",
                "--checkpoint-store",
                "versions",
                "--iteration-id",
                "iteration-1",
            ]
        )

        self.assertEqual(args.iteration_id, "iteration-1")
        self.assertIsNone(args.harness_version)

    def test_builds_pending_primary_and_defaults_comparison_to_parent(self) -> None:
        """Verifies the builds pending primary and defaults comparison to parent contract."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            env_file = root / ".env"
            env_file.write_text(
                "RETRIEVER_URL=http://example.test/retrieve\n",
                encoding="utf-8",
            )
            store_root = root / "versions"
            store = HarnessVersionStore(store_root)
            baseline = store.initialize(BASELINE_PLUGINS_ROOT, env_file=env_file)
            session = store.start_iteration()
            session.add_extension(
                instance_id="candidate_hook",
                files={"plugin.py": _CANDIDATE_HOOK},
            )
            component_path = "extensions/candidate_hook/plugin.py"
            source = session.read_text(component_path)
            session.apply_patch(
                (FileEdit("write", component_path, f"{source}\n# review candidate\n"),)
            )
            candidate_report = _write_report(
                root,
                name="candidate",
                score=1,
                harness={
                    "source_type": "pending_iteration",
                    "parent_version": session.parent_version,
                    "iteration_id": session.iteration_id,
                    "candidate_digest": session.digest,
                    "revision": session.revision,
                },
            )
            parent_report = _write_report(
                root,
                name="parent",
                score=0,
                harness={
                    "source_type": "accepted_version",
                    "checkpoint_store": str(store.root),
                    "checkpoint_store_id": store.checkpoint_store_id,
                    "version_id": baseline.version_id,
                    "candidate_digest": baseline.digest,
                },
            )
            args = SimpleNamespace(
                report_dir=candidate_report,
                rollout_file=None,
                actor_plugins_root=None,
                checkpoint_store=store_root,
                harness_version=None,
                iteration_id=session.iteration_id,
                compare_report_dir=parent_report,
                compare_rollout_file=None,
                compare_actor_plugins_root=None,
                compare_harness_version=None,
            )

            context, actor_source, iteration = _build_context(args)

        self.assertEqual(context.harness_version, f"pending:{session.iteration_id}")
        self.assertEqual(context.comparison.harness_version, "harness_v0001")
        self.assertEqual(
            context.get_comparison_summary()["transitions"]["primary_only_correct"],
            1,
        )
        self.assertIn(
            "# review candidate",
            context.get_harness_component(
                "extensions", "candidate_hook"
            )["files"][component_path],
        )
        self.assertEqual(actor_source, str(store.root))
        self.assertEqual(iteration["iteration_id"], session.iteration_id)
        self.assertEqual(iteration["candidate_digest"], session.digest)

    def test_rejects_comparison_rollout_from_another_accepted_version(self) -> None:
        """Verifies the rejects comparison rollout from another accepted version contract."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            env_file = root / ".env"
            env_file.write_text(
                "RETRIEVER_URL=http://example.test/retrieve\n",
                encoding="utf-8",
            )
            store = HarnessVersionStore(root / "versions")
            baseline = store.initialize(BASELINE_PLUGINS_ROOT, env_file=env_file)
            primary_report = _write_report(
                root,
                name="primary",
                score=1,
                harness=_accepted_harness(store, baseline.version_id, baseline.digest),
            )
            comparison_report = _write_report(
                root,
                name="comparison",
                score=0,
                harness=_accepted_harness(store, "harness_v9999", baseline.digest),
            )
            args = SimpleNamespace(
                report_dir=primary_report,
                rollout_file=None,
                actor_plugins_root=None,
                checkpoint_store=store.root,
                harness_version=baseline.version_id,
                iteration_id=None,
                compare_report_dir=comparison_report,
                compare_rollout_file=None,
                compare_actor_plugins_root=None,
                compare_harness_version=baseline.version_id,
            )

            with self.assertRaisesRegex(
                ValueError, "comparison rollout case-1/r000 version mismatch"
            ):
                _build_context(args)

    def test_rejects_primary_rollout_from_another_accepted_version(self) -> None:
        """Verifies the rejects primary rollout from another accepted version contract."""

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            env_file = root / ".env"
            env_file.write_text(
                "RETRIEVER_URL=http://example.test/retrieve\n",
                encoding="utf-8",
            )
            store = HarnessVersionStore(root / "versions")
            baseline = store.initialize(BASELINE_PLUGINS_ROOT, env_file=env_file)
            primary_report = _write_report(
                root,
                name="primary",
                score=1,
                harness=_accepted_harness(store, "harness_v9999", baseline.digest),
            )
            args = SimpleNamespace(
                report_dir=primary_report,
                rollout_file=None,
                actor_plugins_root=None,
                checkpoint_store=store.root,
                harness_version=baseline.version_id,
                iteration_id=None,
                compare_report_dir=None,
                compare_rollout_file=None,
                compare_actor_plugins_root=None,
                compare_harness_version=None,
            )

            with self.assertRaisesRegex(
                ValueError, "primary rollout case-1/r000 version mismatch"
            ):
                _build_context(args)


def _write_report(
    root: Path,
    *,
    name: str,
    score: int,
    harness: dict[str, object] | None,
) -> Path:
    report_dir = root / f"{name}-report"
    report_dir.mkdir()
    rollout_file = root / f"{name}.jsonl"
    record: dict[str, object] = {
        "example": {"example_id": "case-1", "question": "Question?"},
        "run": {"status": "completed", "answer": "Answer", "trace": []},
    }
    if harness is not None:
        record["harness"] = harness
    rollout_file.write_text(
        f"{json.dumps(record)}\n",
        encoding="utf-8",
    )
    summary = {
        "schema_version": 1,
        "source_file": str(rollout_file),
        "metrics": {"answers": {"accuracy": float(score)}},
    }
    case = {
        "example_id": "case-1",
        "question": "Question?",
        "golden_answer": "Answer",
        "predicted_answer": "Answer" if score else "Wrong",
        "run_status": "completed",
        "runner_error": None,
        "static": {"decision": "pass" if score else "needs_teacher"},
        "teacher": None,
        "score": score,
        "score_source": "static" if score else "teacher",
        "execution": {"tool_calls": 1, "retriever_errors": 0},
    }
    (report_dir / "summary.json").write_text(
        json.dumps(summary),
        encoding="utf-8",
    )
    (report_dir / "per_example.jsonl").write_text(
        f"{json.dumps(case)}\n",
        encoding="utf-8",
    )
    return report_dir


def _accepted_harness(
    store: HarnessVersionStore,
    version_id: str,
    digest: str,
) -> dict[str, object]:
    return {
        "source_type": "accepted_version",
        "checkpoint_store": str(store.root),
        "checkpoint_store_id": store.checkpoint_store_id,
        "version_id": version_id,
        "candidate_digest": digest,
    }
