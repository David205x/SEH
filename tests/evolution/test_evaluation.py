"""Controller-owned rollout and evaluation boundary tests."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase

from search_harness.evolution.control.evaluation_effects import (
    EvaluationEffects,
)
from search_harness.evolution.control.evaluation import (
    CandidateArtifact,
    EvaluationArtifact,
    LocalEvaluationBackend,
    LocalEvaluationConfig,
)
from search_harness.evolution.versioning import TemplateVersionStore


class RecordingEvaluationBackend(LocalEvaluationBackend):
    """Record selectors without executing model-backed rollouts."""

    def __init__(self, root: Path) -> None:
        super().__init__(
            store=TemplateVersionStore(root / "version_store"),
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
        """Accepted evaluation uses a version without a Candidate Attempt."""

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            backend = RecordingEvaluationBackend(root)
            backend.evaluate_accepted(
                version_id="harness_v0001",
                experience_file=root / "experience.jsonl",
                output_dir=root / "accepted_report",
            )

        self.assertEqual(backend.calls[0]["version_id"], "harness_v0001")
        self.assertIsNone(backend.calls[0]["candidate_attempt_id"])
        self.assertIsNone(
            backend.calls[0]["max_consecutive_identical_errors"]
        )

    def test_candidate_evaluation_selects_pending_candidate_attempt_and_error_limit(
        self,
    ) -> None:
        """Candidate evaluation preserves the pending selector and error fuse."""

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            backend = RecordingEvaluationBackend(root)
            candidate = CandidateArtifact(
                candidate_attempt_id="candidate_attempt_0001",
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
        self.assertEqual(
            backend.calls[0]["candidate_attempt_id"],
            "candidate_attempt_0001",
        )
        self.assertEqual(
            backend.calls[0]["max_consecutive_identical_errors"],
            4,
        )


class EvaluationEffectsTest(TestCase):
    def test_projects_comparable_incumbent_and_candidate_results(self) -> None:
        """Both evaluation routes use one Experience Set and token schema."""

        class Backend:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def evaluate_accepted(self, **values: object) -> EvaluationArtifact:
                self.calls.append(values)
                return self._artifact(values)

            def evaluate_candidate(self, **values: object) -> EvaluationArtifact:
                self.calls.append(values)
                return self._artifact(values)

            @staticmethod
            def _artifact(values: dict[str, object]) -> EvaluationArtifact:
                output_dir = values["output_dir"]
                assert isinstance(output_dir, Path)
                return EvaluationArtifact(
                    rollout_file=output_dir / "rollouts.jsonl",
                    report_dir=output_dir,
                    metrics={"tokens": {"total_tokens": 7}},
                )

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            backend = Backend()
            store = SimpleNamespace(
                list_versions=lambda: (
                    SimpleNamespace(version_id="harness_v0001"),
                )
            )
            effects = EvaluationEffects(
                store=store,  # type: ignore[arg-type]
                backend=backend,  # type: ignore[arg-type]
                experience_file=root / "experience.jsonl",
            )
            incumbent = effects.evaluate_incumbent(
                version_id="harness_v0001",
                work_dir=root / "incumbent",
            )
            candidate = effects.evaluate_candidate(
                candidate=CandidateArtifact(
                    candidate_attempt_id="candidate_attempt_0001",
                    parent_version="harness_v0001",
                    candidate_digest="digest",
                    compiler_log=root / "compiler.json",
                    summary="candidate",
                    validation_passed=True,
                ),
                work_dir=root / "candidate",
            )

        self.assertEqual(incumbent.usage["total_tokens"], 7)
        self.assertEqual(candidate.usage["total_tokens"], 7)
        self.assertIn("rollout_file", incumbent.artifact_refs)
        self.assertIn("candidate_rollout_file", candidate.artifact_refs)
        self.assertEqual(
            backend.calls[0]["experience_file"],
            backend.calls[1]["experience_file"],
        )
