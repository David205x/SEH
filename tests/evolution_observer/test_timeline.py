from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest import TestCase

from evolution_observer.timeline import (
    OpenAICompatibleTimelineSummarizer,
    TimelineEntry,
    TimelineGenerator,
    timeline_projection_from_runtime,
)


WORK_ROOT = Path(__file__).parents[2] / "runs" / "components" / "timeline_test"


class FakeSummarizer:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def summarize(self, entry: TimelineEntry) -> tuple[str, dict[str, object]]:
        self.calls.append(entry.entry_id)
        return f"概要：{entry.summary}", {"provider": "fake"}


class TimelineGeneratorTest(TestCase):
    def setUp(self) -> None:
        if WORK_ROOT.exists():
            shutil.rmtree(WORK_ROOT)
        (WORK_ROOT / "artifacts" / "evaluate-1").mkdir(parents=True)

    def tearDown(self) -> None:
        if WORK_ROOT.exists():
            shutil.rmtree(WORK_ROOT)

    def test_incrementally_projects_only_complete_new_format_events(self) -> None:
        self._write_run(schema_version=3)
        effect_path = WORK_ROOT / "artifacts" / "evaluate-1" / "effect.json"
        self._write_json(
            effect_path,
            {
                "outcome": {
                    "metrics": {
                        "answers": {
                            "accuracy": 0.8,
                            "example_count": 10,
                            "stable_correct_count": 8,
                            "stable_failure_count": 2,
                            "unstable_count": 0,
                        }
                    }
                },
                "artifact_refs": {},
                "usage": {"total_tokens": 100},
            },
        )
        events = [
            self._event(1, "run_started", {"run_id": "run-test"}),
            self._event(
                2,
                "work_scheduled",
                {
                    "work": {
                        "work_id": "evaluate-1",
                        "kind": "evaluate_incumbent",
                        "subject_ref": "generation:1:harness_v0001",
                        "payload": {"generation": 1},
                        "attempt": 1,
                    }
                },
            ),
            self._event(3, "work_started", {"work_id": "evaluate-1"}),
            self._event(
                4,
                "work_completed",
                {
                    "work_id": "evaluate-1",
                    "result_ref": "artifacts/evaluate-1/effect.json",
                    "total_tokens": 100,
                },
            ),
        ]
        self._write_events(events, tail='{"sequence": 5')
        summarizer = FakeSummarizer()
        generator = TimelineGenerator(summarizer)

        first = generator.update(WORK_ROOT)

        self.assertEqual(len(first), 2)
        self.assertEqual(
            [entry.source_event_sequences for entry in first],
            [(1,), (2, 3, 4)],
        )
        self.assertEqual(len(summarizer.calls), 2)
        self.assertEqual(first[1].facts["accuracy"], 0.8)

        events.append(
            self._event(
                5,
                "run_paused",
                {"reason": "manual verification"},
            )
        )
        self._write_events(events)
        second = generator.update(WORK_ROOT)

        self.assertEqual(len(second), 3)
        self.assertEqual(len(summarizer.calls), 3)
        self.assertEqual(second[-1].action, "run_paused")
        self.assertEqual(
            json.loads(
                (WORK_ROOT / "timeline" / "state.json").read_text(
                    encoding="utf-8"
                )
            )["last_control_sequence"],
            5,
        )
        entry_record = json.loads(
            (WORK_ROOT / "timeline" / "entries.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()[-1]
        )
        summary_record = json.loads(
            (WORK_ROOT / "timeline" / "summaries.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()[-1]
        )
        self.assertEqual(entry_record["entry_id"], summary_record["entry_id"])
        self.assertEqual(entry_record["source_event_sequences"], [5])
        self.assertIn("概要：Evolution Run 已暂停", summary_record["model_summary"])
        self.assertFalse((WORK_ROOT / "timeline" / "timeline.md").exists())

    def test_rejects_legacy_run_schema(self) -> None:
        self._write_run(schema_version=1)
        self._write_events([])

        with self.assertRaisesRegex(ValueError, "only supports.*schema_version 3"):
            TimelineGenerator().update(WORK_ROOT)

    def test_summary_profile_reuses_configured_credentials(self) -> None:
        env_file = WORK_ROOT / ".env"
        env_file.write_text("TEACHER_API_KEY=test-secret\n", encoding="utf-8")
        config_file = WORK_ROOT / "runtime.yaml"
        self._write_json(
            config_file,
            {
                "schema_version": 1,
                "models": {
                    "summary": {
                        "provider": "openai_compatible",
                        "credential_profile": "teacher",
                        "base_url": "https://example.invalid/v1",
                        "model_id": "summary-test",
                        "max_tokens": 128,
                        "thinking_mode": "disabled",
                    }
                },
            },
        )

        summarizer = OpenAICompatibleTimelineSummarizer.from_runtime_config(
            env_file=env_file,
            config_file=config_file,
        )

        self.assertEqual(summarizer.model.config.api_key, "test-secret")
        self.assertEqual(summarizer.model.config.model_id, "summary-test")
        self.assertIsNone(summarizer.model.config.thinking_mode)

    def test_runtime_config_can_disable_automatic_projection(self) -> None:
        config_file = WORK_ROOT / "runtime.yaml"
        self._write_json(
            config_file,
            {
                "schema_version": 1,
                "timeline": {"enabled": False, "model_summary": False},
            },
        )

        projection = timeline_projection_from_runtime(
            run_dir=WORK_ROOT,
            config_file=config_file,
        )

        self.assertIsNone(projection)

    def _write_run(self, *, schema_version: int) -> None:
        self._write_json(
            WORK_ROOT / "run.json",
            {"schema_version": schema_version, "run_id": "run-test"},
        )

    def _write_events(
        self,
        events: list[dict[str, object]],
        *,
        tail: str = "",
    ) -> None:
        content = "".join(
            json.dumps(event, ensure_ascii=False) + "\n" for event in events
        )
        (WORK_ROOT / "events.jsonl").write_text(
            content + tail,
            encoding="utf-8",
        )

    @staticmethod
    def _event(
        sequence: int,
        event_type: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        return {
            "sequence": sequence,
            "event_type": event_type,
            "payload": payload,
            "created_at": f"2026-08-04T00:00:{sequence:02d}+00:00",
        }

    @staticmethod
    def _write_json(path: Path, value: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
