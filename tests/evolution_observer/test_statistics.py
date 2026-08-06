"""首页实验统计投影测试。"""

from pathlib import Path
import unittest

from evolution_observer.models import ObservedEvent, ObservedWorkItem
from evolution_observer.statistics import project_run_statistics


FIXTURE_DIR = Path(__file__).parent / "statistics_fixtures"


class RunStatisticsTests(unittest.TestCase):
    """验证记录缺失语义与可归因用量。"""

    def test_projects_recorded_usage_and_stage_time(self) -> None:
        events = [
            _event(1, "2026-08-04T00:00:00Z"),
            _event(2, "2026-08-04T00:02:00Z"),
        ]
        works = [
            _work(
                work_id="evaluation",
                kind="evaluate_incumbent",
                category="mechanism",
                total_tokens=120,
                result_ref="evaluation_effect.json",
                started_at="2026-08-04T00:00:00Z",
                ended_at="2026-08-04T00:00:30Z",
            ),
            _work(
                work_id="teacher",
                kind="analyze_failure",
                category="teacher_role",
                total_tokens=50,
                result_ref="teacher_effect.json",
                started_at="2026-08-04T00:00:30Z",
                ended_at="2026-08-04T00:01:30Z",
            ),
        ]

        statistics = project_run_statistics(FIXTURE_DIR, events, works)

        self.assertEqual(statistics["total_tokens"], 170)
        self.assertEqual(statistics["recorded_model_calls"], 5)
        self.assertEqual(statistics["recorded_cached_tokens"], 30)
        self.assertEqual(
            statistics["token_sources"],
            {
                "student": 100,
                "teacher_role": 50,
                "teacher_judge": None,
                "hook_model": 20,
                "unclassified": 0,
            },
        )
        self.assertEqual(statistics["elapsed_seconds"], 120.0)
        self.assertEqual(statistics["current_generation_seconds"], 90.0)
        self.assertEqual(statistics["average_generation_seconds"], 90.0)
        self.assertEqual(statistics["stage_time"]["evaluation"]["seconds"], 30.0)
        self.assertEqual(statistics["stage_time"]["research"]["seconds"], 60.0)
        self.assertEqual(
            statistics["role_breakdown"][0],
            {
                "kind": "analyze_failure",
                "label": "Failure Analyst",
                "seconds": 60.0,
                "work_count": 1,
                "tokens": 50,
                "calls": 2,
                "cached_tokens": 30,
                "time_share": 1.0,
                "token_share": 1.0,
                "cache_share": 0.6,
            },
        )
        time_roles = {
            row["kind"]: row
            for row in statistics["role_time_breakdown"]
        }
        self.assertEqual(time_roles["evaluate_incumbent"]["seconds"], 30.0)
        self.assertEqual(time_roles["evaluate_incumbent"]["work_count"], 1)
        self.assertEqual(
            statistics["role_turns"]["run"][0],
            {
                "role_id": "failure_analyst",
                "label": "Failure Analyst",
                "sample_count": 1,
                "minimum": 2,
                "q1": 2.0,
                "median": 2.0,
                "mean": 2.0,
                "q3": 2.0,
                "maximum": 2,
                "turn_limit": 8,
                "limit_values": [8],
            },
        )
        self.assertEqual(
            statistics["evolution_metrics"],
            [
                {
                    "generation": 1,
                    "source": "incumbent",
                    "work_id": "evaluation",
                    "mean_turns": 2.5,
                    "token_minimum": 40.0,
                    "token_mean": 60.0,
                    "token_maximum": 80.0,
                    "matching_accuracy": 0.5,
                    "teacher_judge_accuracy": 0.75,
                    "stability": 0.8,
                }
            ],
        )

    def test_projects_one_preferred_evaluation_per_generation(self) -> None:
        works = [
            _work(
                work_id="g1-incumbent",
                kind="evaluate_incumbent",
                category="mechanism",
                total_tokens=120,
                result_ref="evaluation_effect.json",
                started_at="2026-08-04T00:00:00Z",
                ended_at="2026-08-04T00:00:30Z",
                generation=1,
            ),
            _work(
                work_id="g1-candidate",
                kind="evaluate_candidate",
                category="mechanism",
                total_tokens=120,
                result_ref="evaluation_effect.json",
                started_at="2026-08-04T00:00:30Z",
                ended_at="2026-08-04T00:01:00Z",
                generation=1,
            ),
            _work(
                work_id="g2-incumbent",
                kind="evaluate_incumbent",
                category="mechanism",
                total_tokens=120,
                result_ref="evaluation_effect.json",
                started_at="2026-08-04T00:01:00Z",
                ended_at="2026-08-04T00:01:30Z",
                generation=2,
            ),
        ]

        points = project_run_statistics(FIXTURE_DIR, [], works)[
            "evolution_metrics"
        ]

        self.assertEqual(
            [(point["generation"], point["source"]) for point in points],
            [(1, "candidate"), (2, "incumbent")],
        )


def _event(sequence: int, created_at: str) -> ObservedEvent:
    return ObservedEvent(
        sequence=sequence,
        event_type="observer_test",
        created_at_utc=created_at,
        payload={},
    )


def _work(
    *,
    work_id: str,
    kind: str,
    category: str,
    total_tokens: int,
    result_ref: str,
    started_at: str,
    ended_at: str,
    generation: int = 1,
) -> ObservedWorkItem:
    return ObservedWorkItem(
        work_id=work_id,
        kind=kind,
        category=category,
        subject_ref=None,
        parent_work_id=None,
        attempt=1,
        generation=generation,
        status="completed",
        started_at_utc=started_at,
        ended_at_utc=ended_at,
        total_tokens=total_tokens,
        result_ref=result_ref,
    )
