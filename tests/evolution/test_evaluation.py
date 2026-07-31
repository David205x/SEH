"""Controller-owned rollout and evaluation boundary tests."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from search_harness.evolution.control.evaluation import (
    CandidateArtifact,
    EvaluationArtifact,
    LocalEvaluationBackend,
    LocalEvaluationConfig,
)
from search_harness.versioning import HarnessVersionStore


class RecordingEvaluationBackend(LocalEvaluationBackend):
    """Record selectors without executing model-backed rollouts."""

    def __init__(self, root: Path) -> None:
        super().__init__(
            store=HarnessVersionStore(root / "checkpoint"),
            config=LocalEvaluationConfig(
                candidate_error_streak_limit=4,
                show_progress=False,
            ),
        )
        self.calls: list[dict[str, object]] = []

    def _rollout_and_evaluate(self, **values: object) -> EvaluationArtifact:
        self.calls.append(values)
        output_dir = values["output_dir"]
        assert isinstance(output_dir, Path)
        return EvaluationArtifact(
            rollout_file=output_dir / "rollouts.jsonl",
            report_dir=output_dir,
            metrics={"answers": {"accuracy": 1.0}},
        )


class LocalEvaluationBackendTest(TestCase):
    def test_accepted_evaluation_selects_the_accepted_version(self) -> None:
        """Accepted evaluation uses a version selector and no iteration selector."""

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            backend = RecordingEvaluationBackend(root)
            backend.evaluate_accepted(
                version_id="harness_v0001",
                experience_file=root / "experience.jsonl",
                output_dir=root / "accepted_report",
            )

        self.assertEqual(backend.calls[0]["version_id"], "harness_v0001")
        self.assertIsNone(backend.calls[0]["iteration_id"])
        self.assertIsNone(
            backend.calls[0]["max_consecutive_identical_errors"]
        )

    def test_candidate_evaluation_selects_pending_iteration_and_error_limit(
        self,
    ) -> None:
        """Candidate evaluation preserves the pending selector and error fuse."""

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            backend = RecordingEvaluationBackend(root)
            candidate = CandidateArtifact(
                iteration_id="iteration_0001",
                parent_version="harness_v0001",
                candidate_digest="digest",
                compiler_log=root / "compiler.json",
                summary="candidate",
                validation_passed=True,
            )
            backend.evaluate_candidate(
                candidate=candidate,
                experience_file=root / "experience.jsonl",
                output_dir=root / "candidate_report",
            )

        self.assertIsNone(backend.calls[0]["version_id"])
        self.assertEqual(backend.calls[0]["iteration_id"], "iteration_0001")
        self.assertEqual(
            backend.calls[0]["max_consecutive_identical_errors"],
            4,
        )
