"""Persistent agenda executor for the evidence-driven Evolution Controller."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Protocol

from .domain import (
    ControlOutcome,
    ControlState,
    EffectResult,
    EvolutionControlConfig,
    WorkItem,
    WorkKind,
    effect_total_tokens,
    project_events,
)
from .journal import ControlArtifactStore, ControlJournal
from .policies import stop_reason
from .transitions import (
    initial_work,
    retry_work,
    transition_completed,
)


class ControlEffects(Protocol):
    """Bounded side effects invoked by the deterministic controller."""

    async def execute(
        self,
        *,
        work: WorkItem,
        state: ControlState,
        work_dir: Path,
    ) -> EffectResult: ...


class ControlProjection(Protocol):
    """A derived Run view updated after durable Journal commits."""

    def update(self) -> None:
        """Reconcile the projection with the committed Control Journal."""


class EvolutionController:
    """Replay an event journal, execute one agenda item, and persist transitions."""

    def __init__(
        self,
        *,
        run_dir: Path,
        effects: ControlEffects,
        config: EvolutionControlConfig,
        projections: tuple[ControlProjection, ...] = (),
    ) -> None:
        self.run_dir = run_dir.resolve()
        self.effects = effects
        self.config = config
        self.projections = tuple(projections)
        self.journal = ControlJournal(self.run_dir / "events.jsonl")
        self.artifacts = ControlArtifactStore(self.run_dir / "artifacts")

    def initialize(
        self,
        *,
        run_id: str,
        initial_version: str,
    ) -> None:
        """Create the first durable agenda item for a new controller run."""

        if self.journal.read():
            raise FileExistsError(
                f"Evolution Controller run already exists: {self.run_dir}"
            )
        first = initial_work(run_id=run_id, version_id=initial_version)
        self._append_many(
            [
                (
                    "run_started",
                    {
                        "run_id": run_id,
                        "initial_version": initial_version,
                    },
                ),
                ("work_scheduled", {"work": first.to_dict()}),
            ]
        )

    async def run(
        self,
        *,
        stop_before: frozenset[WorkKind] = frozenset(),
    ) -> ControlOutcome:
        """Execute the agenda, optionally returning before selected work kinds."""

        self._update_projections()
        state = self._state()
        if state.status == "new":
            raise RuntimeError("Evolution Controller run is not initialized")
        if state.status == "completed":
            return self._outcome(state)
        if state.status == "paused":
            entries: list[tuple[str, dict[str, object]]] = []
            if (
                state.status_reason is not None
                and state.status_reason.startswith("work failed after ")
                and not state.queued
            ):
                failed = next(
                    (
                        state.works[work_id]
                        for work_id in reversed(state.work_order)
                        if state.works[work_id].status == "failed"
                    ),
                    None,
                )
                if failed is not None:
                    entries.append(
                        (
                            "work_scheduled",
                            {"work": retry_work(failed.item).to_dict()},
                        )
                    )
            entries.append(("run_resumed", {}))
            self._append_many(entries)

        self._recover_interrupted_work()
        while True:
            self._drain_transitions()
            state = self._state()
            if state.status in {"paused", "completed"}:
                return self._outcome(state)

            reason = stop_reason(state, self.config)
            if reason is not None:
                self._append("run_paused", {"reason": reason})
                return self._outcome(self._state())

            queued = state.queued
            if not queued:
                self._append(
                    "run_completed",
                    {"reason": "Controller agenda drained."},
                )
                return self._outcome(self._state())

            if queued[0].item.kind in stop_before:
                return self._outcome(state)

            record = queued[0]
            work = record.item
            self._append("work_started", {"work_id": work.work_id})
            try:
                result = await self.effects.execute(
                    work=work,
                    state=self._state(),
                    work_dir=self.artifacts.work_dir(work.work_id),
                )
                result_ref = self.artifacts.write_effect(
                    work.work_id,
                    result,
                )
            except Exception as exc:
                failure_ref = _persist_role_failure(
                    self.artifacts.work_dir(work.work_id),
                    exc,
                )
                failure_payload: dict[str, object] = {}
                if failure_ref is not None:
                    failure_payload["failure_artifact"] = str(failure_ref)
                failure_stage = _exception_failure_stage(exc)
                if failure_stage is not None:
                    failure_payload["failure_stage"] = failure_stage
                self._append(
                    "work_failed",
                    {
                        "work_id": work.work_id,
                        "error": f"{type(exc).__name__}: {exc}",
                        "total_tokens": _exception_total_tokens(exc),
                        **failure_payload,
                    },
                )
                continue
            self._append(
                "work_completed",
                {
                    "work_id": work.work_id,
                    "result_ref": str(result_ref),
                    "total_tokens": effect_total_tokens(result),
                },
            )

    def _recover_interrupted_work(self) -> None:
        state = self._state()
        for record in state.running:
            work_id = record.item.work_id
            if self.artifacts.has_effect(work_id):
                result = self.artifacts.load_effect(work_id)
                self._append(
                    "work_completed",
                    {
                        "work_id": work_id,
                        "result_ref": str(
                            self.artifacts.effect_path(work_id)
                        ),
                        "total_tokens": effect_total_tokens(result),
                    },
                )
            else:
                self._append(
                    "work_failed",
                    {
                        "work_id": work_id,
                        "error": (
                            "InterruptedExecution: controller stopped before "
                            "persisting the effect result"
                        ),
                    },
                )

    def _drain_transitions(self) -> None:
        while True:
            state = self._state()
            pending = state.pending_transitions
            if not pending or state.status in {"paused", "completed"}:
                return
            record = pending[0]
            item = record.item
            entries: list[tuple[str, dict[str, object]]] = []
            if record.status == "failed":
                if item.attempt <= self.config.max_work_retries:
                    entries.append(
                        (
                            "work_scheduled",
                            {"work": retry_work(item).to_dict()},
                        )
                    )
                else:
                    entries.append(
                        (
                            "run_paused",
                            {
                                "reason": (
                                    f"work failed after {item.attempt} "
                                    f"attempt(s): {item.kind.value}: "
                                    f"{record.error}"
                                )
                            },
                        )
                    )
            else:
                result = self.artifacts.load_effect(item.work_id)
                plan = transition_completed(
                    item=item,
                    result=result,
                    config=self.config,
                )
                if plan.version_advance is not None:
                    version_id, generation = plan.version_advance
                    entries.append(
                        (
                            "version_advanced",
                            {
                                "version_id": version_id,
                                "generation": generation,
                            },
                        )
                    )
                entries.extend(
                    (
                        "work_scheduled",
                        {"work": next_item.to_dict()},
                    )
                    for next_item in plan.next_items
                )
                if plan.complete_reason is not None:
                    entries.append(
                        (
                            "run_completed",
                            {"reason": plan.complete_reason},
                        )
                    )
            entries.append(
                (
                    "work_transitioned",
                    {"work_id": item.work_id},
                )
            )
            self._append_many(entries)

    def _append(self, event_type: str, payload: dict[str, object]) -> None:
        self.journal.append(event_type, payload)
        self._update_projections()

    def _append_many(
        self,
        entries: list[tuple[str, dict[str, object]]],
    ) -> None:
        self.journal.append_many(entries)
        self._update_projections()

    def _update_projections(self) -> None:
        for projection in self.projections:
            try:
                projection.update()
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                logging.getLogger(__name__).warning(
                    "Evolution Run projection %s update failed: %s: %s",
                    type(projection).__name__,
                    type(exc).__name__,
                    exc,
                )

    def _state(self) -> ControlState:
        return project_events(self.journal.read())

    @staticmethod
    def _outcome(state: ControlState) -> ControlOutcome:
        if state.current_version is None:
            raise RuntimeError("controller state lacks current_version")
        reason = state.status_reason or "Controller is still running."
        return ControlOutcome(
            status=state.status,
            reason=reason,
            current_version=state.current_version,
            generation=state.generation,
            completed_work_count=state.completed_work_count,
            total_tokens=state.total_tokens,
        )


def _persist_role_failure(work_dir: Path, exc: Exception) -> Path | None:
    artifact = getattr(exc, "failure_artifact", None)
    if not isinstance(artifact, dict):
        return None
    role = artifact.get("role")
    role_id = role.get("id") if isinstance(role, dict) else None
    safe_role_id = role_id if isinstance(role_id, str) and role_id else "teacher"
    path = work_dir / f"{safe_role_id}.failed.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path.resolve()


def _exception_total_tokens(exc: Exception) -> int:
    artifact = getattr(exc, "failure_artifact", None)
    if not isinstance(artifact, dict):
        return 0
    usage = artifact.get("usage")
    if not isinstance(usage, dict):
        return 0
    value = usage.get("total_tokens", 0)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        return 0
    return value


def _exception_failure_stage(exc: Exception) -> str | None:
    artifact = getattr(exc, "failure_artifact", None)
    if not isinstance(artifact, dict):
        return None
    stage = artifact.get("stage")
    return stage if isinstance(stage, str) and stage else None
