"""Control Journal 的增量安全读取和 WorkItem 投影。"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .models import ObservedEvent, ObservedWorkItem


ROLE_KINDS = {
    "analyze_failure",
    "research_hypothesis",
    "execute_trial",
    "review_evidence",
    "distill_mechanism",
    "compile_candidate",
    "verify_conformance",
    "review_candidate",
}

MECHANISM_KINDS = {
    "evaluate_incumbent",
    "select_trial",
    "stage_candidate",
    "evaluate_candidate",
    "promote_candidate",
    "reject_candidate",
}


class JournalProjector:
    """将 append-only Journal 转化为仅供展示的投影。"""

    def load_events(self, journal_path: Path) -> tuple[list[ObservedEvent], bool]:
        """读取事件；仅允许正在写入的最后一行不完整。"""

        if not journal_path.is_file():
            raise FileNotFoundError(f"missing events.jsonl: {journal_path}")

        events: list[ObservedEvent] = []
        pending_tail = False
        lines = journal_path.read_text(encoding="utf-8").splitlines()
        for index, raw_line in enumerate(lines, start=1):
            if not raw_line.strip():
                continue
            try:
                value = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                if index == len(lines):
                    pending_tail = True
                    break
                raise ValueError(f"events.jsonl:{index}: invalid JSONL record") from exc
            events.append(_parse_event(value, index))
        return events, pending_tail

    def project_work_items(self, events: Iterable[ObservedEvent]) -> list[ObservedWorkItem]:
        """聚合同一 Work ID 的生命周期事件，同时保留原始事件。"""

        works: dict[str, ObservedWorkItem] = {}
        for event in events:
            work_id = _event_work_id(event)
            if work_id is None:
                continue
            work = works.get(work_id)
            if event.event_type == "work_scheduled":
                work = _scheduled_work(event)
                works[work_id] = work
            elif work is None:
                work = ObservedWorkItem(
                    work_id=work_id,
                    kind="unknown",
                    category="unknown",
                    subject_ref=None,
                    parent_work_id=None,
                    attempt=None,
                    generation=None,
                )
                works[work_id] = work
            _apply_event(work, event)

        return sorted(
            works.values(),
            key=lambda item: item.events[-1].sequence if item.events else -1,
            reverse=True,
        )

    def run_status(self, events: Iterable[ObservedEvent]) -> str:
        """从明确的 Journal 终态推导 Run 展示状态。"""

        for event in reversed(list(events)):
            if event.event_type == "run_completed":
                return "completed"
            if event.event_type == "run_failed":
                return "failed"
            if event.event_type == "run_paused":
                return "paused"
            if event.event_type in {"run_started", "run_resumed"}:
                return "running"
        return "running"


def work_category(kind: str) -> str:
    """返回页面使用的 Teacher Role/机制/未知分组。"""

    if kind in ROLE_KINDS:
        return "teacher_role"
    if kind in MECHANISM_KINDS:
        return "mechanism"
    return "unknown"


def _parse_event(value: object, line_number: int) -> ObservedEvent:
    if not isinstance(value, dict):
        raise ValueError(f"events.jsonl:{line_number}: event must be an object")
    sequence = value.get("sequence")
    event_type = value.get("event_type")
    created_at = value.get("created_at")
    payload = value.get("payload")
    if not isinstance(sequence, int) or not isinstance(event_type, str) or not isinstance(created_at, str):
        raise ValueError(f"events.jsonl:{line_number}: missing required event fields")
    if not isinstance(payload, dict):
        raise ValueError(f"events.jsonl:{line_number}: payload must be an object")
    return ObservedEvent(sequence, event_type, created_at, payload)


def _event_work_id(event: ObservedEvent) -> str | None:
    if event.event_type == "work_scheduled":
        work = event.payload.get("work")
        if isinstance(work, dict) and isinstance(work.get("work_id"), str):
            return work["work_id"]
        return None
    work_id = event.payload.get("work_id")
    return work_id if isinstance(work_id, str) else None


def _scheduled_work(event: ObservedEvent) -> ObservedWorkItem:
    raw_work = event.payload["work"]
    assert isinstance(raw_work, dict)
    payload = raw_work.get("payload")
    work_payload = payload if isinstance(payload, dict) else {}
    kind = raw_work.get("kind") if isinstance(raw_work.get("kind"), str) else "unknown"
    generation = work_payload.get("generation")
    return ObservedWorkItem(
        work_id=raw_work["work_id"],
        kind=kind,
        category=work_category(kind),
        subject_ref=raw_work.get("subject_ref") if isinstance(raw_work.get("subject_ref"), str) else None,
        parent_work_id=raw_work.get("parent_work_id") if isinstance(raw_work.get("parent_work_id"), str) else None,
        attempt=raw_work.get("attempt") if isinstance(raw_work.get("attempt"), int) else None,
        generation=generation if isinstance(generation, int) else None,
    )


def _apply_event(work: ObservedWorkItem, event: ObservedEvent) -> None:
    work.events.append(event)
    if event.event_type == "work_scheduled":
        work.status = "queued"
    elif event.event_type == "work_started":
        work.status = "running"
        work.started_at_utc = event.created_at_utc
    elif event.event_type == "work_completed":
        work.status = "completed"
        work.ended_at_utc = event.created_at_utc
        work.result_ref = _string_or_none(event.payload.get("result_ref"))
        work.total_tokens = _int_or_none(event.payload.get("total_tokens"))
    elif event.event_type == "work_failed":
        work.status = "failed"
        work.ended_at_utc = event.created_at_utc
        work.error = _string_or_none(event.payload.get("error"))


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) else None
