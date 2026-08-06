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


def _work(*, result_ref: str) -> ObservedWorkItem:
    return ObservedWorkItem(
        work_id="analyze_failure-fixture",
        kind="analyze_failure",
        category="teacher_role",
        subject_ref="generation:1:harness_v0001",
        parent_work_id=None,
        attempt=1,
        generation=1,
        status="completed",
        result_ref=result_ref,
    )
