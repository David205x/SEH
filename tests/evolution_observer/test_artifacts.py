from __future__ import annotations

from pathlib import Path
from unittest import TestCase

from evolution_observer.artifacts import ArtifactProjector
from evolution_observer.models import ObservedWorkItem


FIXTURES = Path(__file__).parent / "artifact_fixtures" / "role_detail"


class ArtifactProjectorTest(TestCase):
    def test_projects_teacher_transcript_into_typed_blocks(self) -> None:
        """角色 transcript 应保留消息、推理和工具交互的阅读边界。"""

        detail = ArtifactProjector().project(
            FIXTURES,
            _work(result_ref="effect.json"),
        )

        self.assertEqual(len(detail.trajectories), 1)
        trajectory = detail.trajectories[0]
        self.assertEqual(trajectory.label, "Failure Analyst")
        self.assertEqual(
            [block.block_type for block in trajectory.blocks],
            ["message", "reasoning", "tool_call", "tool_result", "message"],
        )
        self.assertEqual(trajectory.blocks[3].title, "Tool Result · inspect_case")
        self.assertTrue(trajectory.blocks[0].default_collapsed)
        self.assertTrue(trajectory.blocks[1].default_collapsed)

    def test_keeps_control_only_work_as_empty_trajectory_list(self) -> None:
        """没有 transcript 的机制产物不能被伪造成模型对话。"""

        detail = ArtifactProjector().project(
            FIXTURES,
            _work(result_ref="control_effect.json"),
        )

        self.assertEqual(detail.trajectories, ())
        self.assertIn("没有可转换为对话", detail.detail_message)

    def test_follows_checkpoint_role_artifact_reference(self) -> None:
        """Conformance finding 包装应解包并去重共享的批次对话。"""

        detail = ArtifactProjector().project(
            FIXTURES,
            _work(result_ref="checkpoint_effect.json"),
        )

        self.assertEqual(len(detail.trajectories), 1)
        self.assertEqual(
            detail.trajectories[0].label,
            "Conformance Reviewer · Batch 001",
        )
        self.assertTrue(
            detail.trajectories[0].source_ref.endswith("batch_001.json")
        )
        self.assertIn("conformance_finding_001.role", detail.artifact_refs)

    def test_uses_related_role_trajectory_for_control_event(self) -> None:
        """Reject 等控制 WorkItem 可复用直接父角色的对话。"""

        detail = ArtifactProjector().project_with_related_fallback(
            FIXTURES,
            _work(result_ref="control_effect.json", kind="reject_candidate"),
            _work(result_ref="effect.json", kind="review_candidate"),
        )

        self.assertEqual(detail.work.kind, "reject_candidate")
        self.assertEqual(len(detail.trajectories), 1)
        self.assertEqual(detail.trajectories[0].label, "Failure Analyst")
        self.assertIn("related.failure_artifact", detail.artifact_refs)


def _work(*, result_ref: str, kind: str = "analyze_failure") -> ObservedWorkItem:
    return ObservedWorkItem(
        work_id=f"{kind}-fixture",
        kind=kind,
        category="teacher_role",
        subject_ref="generation:1:harness_v0001",
        parent_work_id=None,
        attempt=1,
        generation=1,
        status="completed",
        result_ref=result_ref,
    )
