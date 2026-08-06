"""按 Generation 的流程与路由预算投影测试。"""

import unittest

from evolution_observer.flow import project_generation_flows
from evolution_observer.models import ObservedEvent, ObservedWorkItem


class GenerationFlowTests(unittest.TestCase):
    """验证 Generation 隔离、最终状态和有效 reroute 计数。"""

    def test_projects_independent_generation_flows(self) -> None:
        works = [
            _work("eval-g1", "evaluate_incumbent", 1, 1),
            _work("analysis", "analyze_failure", 1, 2, "eval-g1"),
            _work("research-1", "research_hypothesis", 1, 3, "analysis"),
            _work("trial", "execute_trial", 1, 4, "research-1"),
            _work("review", "review_evidence", 1, 5, "trial"),
            _work("research-2", "research_hypothesis", 1, 6, "review"),
            _work("distill", "distill_mechanism", 1, 7, "research-2"),
            _work("compile-1", "compile_candidate", 1, 8, "distill"),
            _work("stage", "stage_candidate", 1, 9, "compile-1"),
            _work("compile-2", "compile_candidate", 1, 10, "stage"),
            _work("reject", "reject_candidate", 1, 11, "compile-2"),
            _work("compile-3", "compile_candidate", 1, 12, "reject"),
            _work("promote-failed", "promote_candidate", 1, 13, status="failed"),
            _work("promote-ok", "promote_candidate", 1, 14),
            _work("eval-g2", "evaluate_incumbent", 2, 15),
        ]
        metadata = {
            "control_config": {
                "max_hypothesis_revisions": 3,
                "max_trial_assignments": 4,
                "max_trials_per_hypothesis": 2,
                "max_mechanism_revisions": 2,
                "max_compiler_revisions": 2,
                "max_candidate_revisions": 2,
            }
        }

        flows = project_generation_flows(works, metadata, "paused")

        self.assertEqual([flow["generation"] for flow in flows], [1, 2])
        self.assertEqual(flows[0]["status"], "accepted")
        self.assertTrue(flows[0]["has_next_generation"])
        self.assertEqual(flows[1]["status"], "paused")
        generation_one = {
            node["kind"]: node for node in flows[0]["flow"]
        }
        self.assertEqual(generation_one["promote_candidate"]["status"], "completed")
        self.assertEqual(generation_one["promote_candidate"]["count"], 2)
        self.assertEqual(
            generation_one["research_hypothesis"]["budget"]["used"],
            1,
        )
        self.assertEqual(
            generation_one["research_hypothesis"]["budget"]["share"],
            1 / 3,
        )
        self.assertEqual(
            generation_one["compile_candidate"]["budget"]["used"],
            1,
        )
        self.assertEqual(
            generation_one["review_candidate"]["budget"]["used"],
            1,
        )
        generation_two = {
            node["kind"]: node for node in flows[1]["flow"]
        }
        self.assertEqual(generation_two["evaluate_incumbent"]["count"], 1)
        self.assertEqual(generation_two["analyze_failure"]["count"], 0)


def _work(
    work_id: str,
    kind: str,
    generation: int,
    sequence: int,
    parent_work_id: str | None = None,
    *,
    status: str = "completed",
) -> ObservedWorkItem:
    event = ObservedEvent(
        sequence=sequence,
        event_type=f"work_{status}",
        created_at_utc=f"2026-08-04T00:00:{sequence:02d}Z",
        payload={"work_id": work_id},
    )
    return ObservedWorkItem(
        work_id=work_id,
        kind=kind,
        category="teacher_role",
        subject_ref=None,
        parent_work_id=parent_work_id,
        attempt=1,
        generation=generation,
        status=status,
        events=[event],
    )
