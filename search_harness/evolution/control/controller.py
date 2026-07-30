"""Persistent agenda executor for the evidence-driven Evolution Controller."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .domain import (
    ControlOutcome,
    ControlState,
    EffectResult,
    EvolutionControlConfig,
    WorkItem,
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


class EvolutionController:
    """Replay an event journal, execute one agenda item, and persist transitions."""

    def __init__(
        self,
        *,
        run_dir: Path,
        effects: ControlEffects,
        config: EvolutionControlConfig,
    ) -> None:
        self.run_dir = run_dir.resolve()
        self.effects = effects
        self.config = config
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
        self.journal.append_many(
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

    async def run(self) -> ControlOutcome:
        """Execute or resume the agenda until completion, pause, or error budget."""

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
            self.journal.append_many(entries)

        self._recover_interrupted_work()
        while True:
            self._drain_transitions()
            state = self._state()
            if state.status in {"paused", "completed"}:
                return self._outcome(state)

            reason = stop_reason(state, self.config)
            if reason is not None:
                self.journal.append("run_paused", {"reason": reason})
                return self._outcome(self._state())

            queued = state.queued
            if not queued:
                self.journal.append(
                    "run_completed",
                    {"reason": "Controller agenda drained."},
                )
                return self._outcome(self._state())

            record = queued[0]
            work = record.item
            self.journal.append("work_started", {"work_id": work.work_id})
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
                self.journal.append(
                    "work_failed",
                    {
                        "work_id": work.work_id,
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                )
                continue
            self.journal.append(
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
                self.journal.append(
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
                self.journal.append(
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
            self.journal.append_many(entries)

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
