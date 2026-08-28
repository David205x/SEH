"""Evidence Reviewer debug-fragment accounting tests."""

from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
from types import SimpleNamespace

from experiments.run_evidence_reviewer_fragment import (
    _EvidenceAccountingEffects,
    _RecordingRoleRunner,
    parse_args,
)
from search_harness.evolution.control.domain import (
    ControlState,
    EffectResult,
    WorkKind,
)


class _FakeEffects:
    async def execute(self, **kwargs: object) -> EffectResult:
        del kwargs
        return EffectResult(
            outcome={
                "output": {"decision": "continue"},
                "trial_reviews": [{"trial_ref": "trial_001"}],
            },
            artifact_refs={"reviewer_artifact": "reviewer.json"},
            usage={"total_tokens": 20},
        )


class _FakeRoleRunner:
    async def run(self, **kwargs: object) -> dict[str, object]:
        return {"role_id": kwargs["role_id"]}


class EvidenceReviewerFragmentTest(unittest.TestCase):
    def test_parse_args_accepts_stored_run(self) -> None:
        args = parse_args(["--run-dir", "runs/debug_fragments/example"])

        self.assertEqual(
            args.run_dir,
            Path("runs/debug_fragments/example"),
        )
        self.assertIsNone(args.env_file)

    def test_adds_pending_trial_review_usage_to_effect(self) -> None:
        effects = _EvidenceAccountingEffects(
            inner=_FakeEffects(),  # type: ignore[arg-type]
            stage_path=Path("trial_review_stage.json"),
            stage={
                "trial_reviews": [{"trial_ref": "trial_001"}],
                "usage": {"total_tokens": 100},
            },
        )
        work = SimpleNamespace(kind=WorkKind.REVIEW_EVIDENCE)

        result = asyncio.run(
            effects.execute(
                work=work,  # type: ignore[arg-type]
                state=ControlState(),
                work_dir=Path("review"),
            )
        )

        self.assertEqual(result.usage["total_tokens"], 120)
        self.assertEqual(
            result.artifact_refs["trial_review_stage_artifact"],
            str(Path("trial_review_stage.json").resolve()),
        )

    def test_records_delegated_role_ids(self) -> None:
        runner = _RecordingRoleRunner(_FakeRoleRunner())

        result = asyncio.run(runner.run(role_id="evidence_reviewer"))

        self.assertEqual(result["role_id"], "evidence_reviewer")
        self.assertEqual(runner.role_ids, ["evidence_reviewer"])


if __name__ == "__main__":
    unittest.main()
