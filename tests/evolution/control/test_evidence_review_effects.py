"""Evidence Review effect coverage handoff tests."""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from search_harness.evolution.control.evidence_review_effects import (
    EvidenceReviewBatchFailed,
    EvidenceReviewEffects,
)


class _RoleRunner:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def run(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        role_id = kwargs["role_id"]
        role_input = kwargs["role_input"]
        if role_id == "trial_reviewer":
            return {
                "input": role_input,
                "output": {
                    "trial_ref": role_input["trial_ref"],
                    "predicate_observations": [
                        {
                            "phase": "post_tool",
                            "predicate_label": "positive",
                            "decisive_observation": "The fact was absent.",
                            "phase_execution": "intervention_applied",
                            "observed_effect": "The Student searched again.",
                            "outcome_evidence": "The score remained zero.",
                        }
                    ],
                    "assessment": "The intervention produced another search.",
                },
                "usage": {"total_tokens": 10},
            }
        coverage = role_input["coverage_summary"]
        if coverage["default_requirements_met"]:
            raise AssertionError("one trial must not satisfy default coverage")
        return {
            "input": role_input,
            "output": {
                "decision": "continue",
                "phase_findings": [
                    {
                        "phase": "post_tool",
                        "status": "supported",
                        "assessment": "One positive effect was observed.",
                    }
                ],
                "assessment": "More cross-case evidence is required.",
                "key_risk": "The result may be case-specific.",
                "next_obligation": "Collect a negative control.",
            },
            "usage": {"total_tokens": 20},
        }


class _ReviewFailure(RuntimeError):
    def __init__(self) -> None:
        super().__init__("aggregate review failed")
        self.failure_artifact = {"usage": {"total_tokens": 20}}


class _FailingAggregateRunner(_RoleRunner):
    async def run(self, **kwargs: Any) -> dict[str, Any]:
        if kwargs["role_id"] == "evidence_reviewer":
            raise _ReviewFailure()
        return await super().run(**kwargs)


class EvidenceReviewEffectsTest(unittest.IsolatedAsyncioTestCase):
    async def test_can_stop_after_independent_trial_reviews(self) -> None:
        runner = _RoleRunner()
        effect = EvidenceReviewEffects(
            role_runner=runner,  # type: ignore[arg-type]
            trial_reviewer_template_root=Path("trial_reviewer"),
            evidence_reviewer_template_root=Path("evidence_reviewer"),
            judge_workers=3,
        )
        with tempfile.TemporaryDirectory(
            dir=Path(__file__).resolve().parent
        ) as directory:
            root = Path(directory)
            trial_path = root / "trial_001" / "trial.json"
            trial_path.parent.mkdir()
            trial_path.write_text(
                json.dumps(_trial_artifact()),
                encoding="utf-8",
            )

            result = await effect.review(
                hypothesis=_hypothesis(),
                trial_paths=[trial_path],
                persisted_trial_reviews={},
                budget={},
                prior_obligation=None,
                work_dir=root / "review",
                trial_reviews_only=True,
            )

            self.assertEqual(
                [call["role_id"] for call in runner.calls],
                ["trial_reviewer"],
            )
            self.assertEqual(result.usage["total_tokens"], 10)
            self.assertEqual(len(result.outcome["trial_reviews"]), 1)
            self.assertNotIn("coverage_summary", result.outcome)
            self.assertTrue(
                Path(
                    result.artifact_refs[
                        "trial_review_001_artifact"
                    ]
                ).is_file()
            )

    async def test_failure_counts_completed_reviews_and_allows_reuse(self) -> None:
        runner = _FailingAggregateRunner()
        effect = EvidenceReviewEffects(
            role_runner=runner,  # type: ignore[arg-type]
            trial_reviewer_template_root=Path("trial_reviewer"),
            evidence_reviewer_template_root=Path("evidence_reviewer"),
            judge_workers=3,
        )
        with tempfile.TemporaryDirectory(
            dir=Path(__file__).resolve().parent
        ) as directory:
            root = Path(directory)
            trial_path = root / "trial_001" / "trial.json"
            trial_path.parent.mkdir()
            trial_path.write_text(
                json.dumps(_trial_artifact()),
                encoding="utf-8",
            )
            work_dir = root / "review"
            with self.assertRaises(_ReviewFailure) as raised:
                await effect.review(
                    hypothesis=_hypothesis(),
                    trial_paths=[trial_path],
                    persisted_trial_reviews={},
                    budget=_budget(),
                    prior_obligation=None,
                    work_dir=work_dir,
                )

            self.assertEqual(
                raised.exception.failure_artifact["usage"]["total_tokens"],
                30,
            )
            checkpoint = next(
                (root / "evidence_review_checkpoints").rglob(
                    "trial_review_001.json"
                )
            )
            self.assertTrue(checkpoint.is_file())

            retry_runner = _RoleRunner()
            result = await EvidenceReviewEffects(
                role_runner=retry_runner,  # type: ignore[arg-type]
                trial_reviewer_template_root=Path("trial_reviewer"),
                evidence_reviewer_template_root=Path("evidence_reviewer"),
                judge_workers=3,
            ).review(
                hypothesis=_hypothesis(),
                trial_paths=[trial_path],
                persisted_trial_reviews={1: checkpoint},
                budget=_budget(),
                prior_obligation=None,
                work_dir=work_dir,
            )

            self.assertEqual(
                [call["role_id"] for call in retry_runner.calls],
                ["evidence_reviewer"],
            )
            self.assertEqual(result.usage["total_tokens"], 20)

    async def test_persists_structured_reviews_and_coverage_summary(
        self,
    ) -> None:
        runner = _RoleRunner()
        effect = EvidenceReviewEffects(
            role_runner=runner,  # type: ignore[arg-type]
            trial_reviewer_template_root=Path("trial_reviewer"),
            evidence_reviewer_template_root=Path("evidence_reviewer"),
            judge_workers=3,
        )
        with tempfile.TemporaryDirectory(
            dir=Path(__file__).resolve().parent
        ) as directory:
            root = Path(directory)
            trial_path = root / "trial_001" / "trial.json"
            trial_path.parent.mkdir()
            trial_path.write_text(
                json.dumps(_trial_artifact()),
                encoding="utf-8",
            )

            result = await effect.review(
                hypothesis=_hypothesis(),
                trial_paths=[trial_path],
                persisted_trial_reviews={},
                budget=_budget(),
                prior_obligation=None,
                work_dir=root / "review",
            )

            self.assertFalse(
                result.outcome["coverage_summary"][
                    "default_requirements_met"
                ]
            )
            self.assertEqual(
                result.outcome["trial_reviews"][0][
                    "predicate_observations"
                ][0]["predicate_label"],
                "positive",
            )
            coverage_path = Path(
                result.artifact_refs["coverage_summary_artifact"]
            )
            self.assertTrue(coverage_path.is_file())
            self.assertEqual(
                runner.calls[-1]["role_input"]["coverage_summary"],
                result.outcome["coverage_summary"],
            )
            self.assertEqual(result.usage["total_tokens"], 30)

    async def test_reviews_trials_concurrently_and_aggregates_in_input_order(
        self,
    ) -> None:
        """Trial Reviewer 并发完成时仍按 Trial 输入顺序交给总评。"""

        class ConcurrentRunner(_RoleRunner):
            def __init__(self) -> None:
                super().__init__()
                self.active = 0
                self.max_active = 0
                self.started = 0
                self.all_started = asyncio.Event()

            async def run(self, **kwargs: Any) -> dict[str, Any]:
                if kwargs["role_id"] == "trial_reviewer":
                    self.active += 1
                    self.started += 1
                    self.max_active = max(self.max_active, self.active)
                    if self.started == 3:
                        self.all_started.set()
                    await asyncio.wait_for(
                        self.all_started.wait(),
                        timeout=1,
                    )
                    self.active -= 1
                return await super().run(**kwargs)

        runner = ConcurrentRunner()
        effect = EvidenceReviewEffects(
            role_runner=runner,  # type: ignore[arg-type]
            trial_reviewer_template_root=Path("trial_reviewer"),
            evidence_reviewer_template_root=Path("evidence_reviewer"),
            judge_workers=3,
        )
        with tempfile.TemporaryDirectory(
            dir=Path(__file__).resolve().parent
        ) as directory:
            root = Path(directory)
            trial_paths = _write_trials(root, 3)
            result = await effect.review(
                hypothesis=_hypothesis(),
                trial_paths=trial_paths,
                persisted_trial_reviews={},
                budget={**_budget(), "trials_used": 3, "trials_remaining": 2},
                prior_obligation=None,
                work_dir=root / "review",
            )

        self.assertEqual(runner.max_active, 3)
        self.assertEqual(
            [item["trial_ref"] for item in result.outcome["trial_reviews"]],
            ["trial_001", "trial_002", "trial_003"],
        )
        self.assertEqual(
            runner.calls[-1]["role_input"]["trial_reviews"],
            result.outcome["trial_reviews"],
        )

    async def test_trial_review_retry_reuses_parallel_checkpoints(self) -> None:
        """单条 Reviewer 失败后，重试只重新调用未完成的 Trial Review。"""

        class OneReviewFailure(RuntimeError):
            def __init__(self) -> None:
                super().__init__("transient Trial Review failure")
                self.failure_artifact = {"usage": {"total_tokens": 7}}

        class RecoveringRunner(_RoleRunner):
            def __init__(self) -> None:
                super().__init__()
                self.failed = False
                self.trial_calls: list[str] = []

            async def run(self, **kwargs: Any) -> dict[str, Any]:
                if kwargs["role_id"] == "trial_reviewer":
                    trial_ref = str(kwargs["role_input"]["trial_ref"])
                    self.trial_calls.append(trial_ref)
                    if trial_ref == "trial_002" and not self.failed:
                        self.failed = True
                        raise OneReviewFailure()
                return await super().run(**kwargs)

        runner = RecoveringRunner()
        effect = EvidenceReviewEffects(
            role_runner=runner,  # type: ignore[arg-type]
            trial_reviewer_template_root=Path("trial_reviewer"),
            evidence_reviewer_template_root=Path("evidence_reviewer"),
            judge_workers=3,
        )
        with tempfile.TemporaryDirectory(
            dir=Path(__file__).resolve().parent
        ) as directory:
            root = Path(directory)
            trial_paths = _write_trials(root, 3)
            values = {
                "hypothesis": _hypothesis(),
                "trial_paths": trial_paths,
                "persisted_trial_reviews": {},
                "budget": {
                    **_budget(),
                    "trials_used": 3,
                    "trials_remaining": 2,
                },
                "prior_obligation": None,
            }
            with self.assertRaises(EvidenceReviewBatchFailed) as raised:
                await effect.review(
                    **values,
                    work_dir=root / "attempt-one",
                )
            result = await effect.review(
                **values,
                work_dir=root / "attempt-two",
            )

        self.assertEqual(
            raised.exception.failure_artifact["usage"]["total_tokens"],
            27,
        )
        self.assertEqual(
            runner.trial_calls,
            [
                "trial_001",
                "trial_002",
                "trial_003",
                "trial_002",
            ],
        )
        self.assertEqual(result.usage["total_tokens"], 30)


def _hypothesis() -> dict[str, Any]:
    return {
        "fork_phase": "post_tool",
        "phase_plan": [
            {
                "phase": "post_tool",
                "activation_condition": "The required fact is absent.",
                "instruction": "Ask for another search.",
                "expected_effect": "The Student searches again.",
                "max_activations": 1,
            }
        ],
        "evaluation": {
            "primary_signal": "next_action",
            "success_condition": "Another search occurs.",
            "falsifier": "No search occurs.",
        },
        "applicability": "Retrieval tasks with missing evidence.",
    }


def _budget() -> dict[str, Any]:
    return {
        "max_trials_per_hypothesis": 5,
        "trials_used": 1,
        "trials_remaining": 4,
        "max_trial_assignments": 12,
        "assignments_used": 1,
        "assignments_remaining": 11,
        "conclusion_required": False,
    }


def _trial_artifact() -> dict[str, Any]:
    return {
        "input": {"example_id": "example_1"},
        "output": {
            "activated_phases": ["post_tool"],
            "modified_phases": ["post_tool"],
            "unmet_phases": [],
        },
        "resource_artifacts": {
            "intervention_trial": {
                "activation_counts": {"post_tool": 1},
                "context_changes": [],
                "comparison": {
                    "source": {"status": "completed", "execution": {}},
                    "branch": {"status": "completed", "execution": {}},
                },
            }
        },
    }


def _write_trials(root: Path, count: int) -> list[Path]:
    paths = []
    for index in range(1, count + 1):
        path = root / f"trial_{index:03d}" / "trial.json"
        path.parent.mkdir()
        artifact = _trial_artifact()
        artifact["input"]["example_id"] = f"example_{index}"
        path.write_text(json.dumps(artifact), encoding="utf-8")
        paths.append(path)
    return paths


if __name__ == "__main__":
    unittest.main()
