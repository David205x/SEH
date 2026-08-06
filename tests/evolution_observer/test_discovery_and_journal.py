from __future__ import annotations

from pathlib import Path
from unittest import TestCase

from evolution_observer.discovery import RunDiscovery
from evolution_observer.journal import JournalProjector
from evolution_observer.models import ObservedEvent


FIXTURES = Path(__file__).parent / "fixtures"


class DiscoveryAndJournalTest(TestCase):
    def test_lists_readable_and_unreadable_directories(self) -> None:
        """保留不可读取实验，避免观察器掩盖产物问题。"""

        listings = RunDiscovery(FIXTURES).list_runs()

        self.assertEqual([item.directory_name for item in listings], ["broken_run", "valid_run"])
        self.assertEqual(listings[0].read_status, "unreadable")
        self.assertIn("invalid run.json", listings[0].error_summary)
        self.assertEqual(listings[1].read_status, "readable")

    def test_projects_work_and_defers_partial_final_journal_line(self) -> None:
        """半写入尾行不是失败，已完成 Journal 仍可用于展示。"""

        projector = JournalProjector()
        events, pending_tail = projector.load_events(FIXTURES / "valid_run" / "events.jsonl")
        works = projector.project_work_items(events)

        self.assertTrue(pending_tail)
        self.assertEqual(projector.run_status(events), "paused")
        self.assertEqual(len(works), 1)
        self.assertEqual(works[0].kind, "evaluate_incumbent")
        self.assertEqual(works[0].category, "mechanism")
        self.assertEqual(works[0].status, "completed")
        self.assertEqual(works[0].total_tokens, 42)

    def test_rejects_run_path_traversal(self) -> None:
        """Run 标识不能脱离观察根目录。"""

        discovery = RunDiscovery(FIXTURES)

        with self.assertRaisesRegex(ValueError, "direct child"):
            discovery.resolve_run("../outside")

    def test_uses_latest_run_terminal_state_after_resume(self) -> None:
        """早期 pause 不能覆盖 resume 后最终写入的 completed 状态。"""

        events = [
            ObservedEvent(1, "run_started", "2026-08-03T08:00:00+00:00", {}),
            ObservedEvent(2, "run_paused", "2026-08-03T08:01:00+00:00", {}),
            ObservedEvent(3, "run_resumed", "2026-08-03T08:02:00+00:00", {}),
            ObservedEvent(4, "run_completed", "2026-08-03T08:03:00+00:00", {}),
        ]

        self.assertEqual(JournalProjector().run_status(events), "completed")
