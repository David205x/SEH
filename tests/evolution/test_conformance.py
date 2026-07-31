"""Mechanism Conformance Replay selection and aggregation tests."""

from __future__ import annotations

import shutil
import unittest
from pathlib import Path
from uuid import uuid4

from search_harness.datasets import DatasetExample
from search_harness.evolution.conformance import (
    ConformanceCase,
    aggregate_conformance,
)
from search_harness.teacher.contracts import ConformanceFinding


SCRATCH_ROOT = Path("runs/components/conformance_tests")


class ConformanceAggregationTest(unittest.TestCase):
    def setUp(self) -> None:
        """创建位于项目 runs 下的隔离测试目录。"""

        self.root = SCRATCH_ROOT / uuid4().hex
        self.root.mkdir(parents=True)

    def tearDown(self) -> None:
        """只清理本测试创建的 runs 子目录。"""

        resolved = self.root.resolve()
        if resolved.parent != SCRATCH_ROOT.resolve():
            raise AssertionError("refusing to clean unexpected test path")
        if resolved.exists():
            shutil.rmtree(resolved)

    def test_passes_when_each_example_has_one_faithful_replicate(
        self,
    ) -> None:
        """验证每题至少一次 faithful 且无硬失败时 suite 通过。"""

        cases = (_case("example-1"), _case("example-2"))
        findings = [
            _finding("example-1", 0, "faithful"),
            _finding("example-1", 1, "not_observed"),
            _finding("example-1", 2, "inconclusive"),
            _finding("example-2", 0, "not_observed"),
            _finding("example-2", 1, "faithful"),
            _finding("example-2", 2, "not_observed"),
        ]

        summary = aggregate_conformance(
            cases=cases,
            findings=findings,
            finding_refs=[f"finding-{index}" for index in range(6)],
        )

        self.assertEqual(summary.decision, "pass")
        self.assertEqual(
            summary.per_example["example-1"]["faithful_count"],
            1,
        )

    def test_revises_when_any_runtime_or_implementation_failure_exists(
        self,
    ) -> None:
        """验证单条 runtime/mismatch 会阻止进入全量 evaluation。"""

        cases = (_case("example-1"),)
        findings = [
            _finding("example-1", 0, "faithful"),
            _finding("example-1", 1, "implementation_mismatch"),
            _finding("example-1", 2, "not_observed"),
        ]

        summary = aggregate_conformance(
            cases=cases,
            findings=findings,
            finding_refs=["finding-0", "finding-1", "finding-2"],
        )

        self.assertEqual(summary.decision, "revise_implementation")
        self.assertIn(
            "Repair implementation_mismatch.",
            summary.compiler_feedback,
        )

    def test_revises_when_one_example_has_no_faithful_replicate(
        self,
    ) -> None:
        """验证 faithful 不能由其他 intervention example 全局替代。"""

        cases = (_case("example-1"), _case("example-2"))
        findings = [
            _finding("example-1", 0, "faithful"),
            _finding("example-1", 1, "not_observed"),
            _finding("example-1", 2, "not_observed"),
            _finding("example-2", 0, "not_observed"),
            _finding("example-2", 1, "inconclusive"),
            _finding("example-2", 2, "not_observed"),
        ]

        summary = aggregate_conformance(
            cases=cases,
            findings=findings,
            finding_refs=[f"finding-{index}" for index in range(6)],
        )

        self.assertEqual(summary.decision, "revise_implementation")
        self.assertFalse(summary.per_example["example-2"]["passed"])


def _case(example_id: str) -> ConformanceCase:
    return ConformanceCase(
        example=DatasetExample(
            example_id=example_id,
            question=f"Question for {example_id}?",
        ),
        trial_refs=(f"trial-{example_id}",),
        reference_observations=({"trial_ref": f"trial-{example_id}"},),
    )


def _finding(
    example_id: str,
    replicate_index: int,
    verdict: str,
) -> ConformanceFinding:
    return ConformanceFinding(
        trial_refs=[f"trial-{example_id}"],
        candidate_run_ref=f"{example_id}/r{replicate_index:03d}",
        verdict=verdict,
        observed_phases=["pre_final"] if verdict == "faithful" else [],
        assessment=f"Observed {verdict}.",
        repair_obligation=(
            None
            if verdict == "faithful"
            else f"Repair {verdict}."
        ),
    )
