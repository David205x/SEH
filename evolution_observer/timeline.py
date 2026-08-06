"""从新格式 Evolution Run 增量生成可审计的行为时间线。"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Protocol
from urllib import parse as urllib_parse

from search_harness._internal import get_env_value, read_env_file, read_runtime_config
from search_harness.framework.agent import ChatMessage, ModelInput
from search_harness.integrations.openai_compatible import (
    OpenAICompatibleConfig,
    OpenAICompatibleModel,
)

from .journal import JournalProjector, ROLE_KINDS
from .models import ObservedEvent, ObservedWorkItem


TIMELINE_SCHEMA_VERSION = 2
ROLE_IDS = {
    "analyze_failure": "failure_analyst",
    "research_hypothesis": "hypothesis_researcher",
    "execute_trial": "intervention_worker",
    "distill_mechanism": "mechanism_distiller",
    "compile_candidate": "compiler",
    "verify_conformance": "conformance_reviewer",
    "review_candidate": "candidate_reviewer",
}
@dataclass(frozen=True)
class TimelineEntry:
    """一条由持久化事实投影出的用户可读行为。"""

    entry_id: str
    source_event_sequences: tuple[int, ...]
    created_at_utc: str
    category: str
    action: str
    summary: str
    actor: str | None = None
    outcome: str | None = None
    source_refs: tuple[str, ...] = ()
    facts: dict[str, Any] = field(default_factory=dict)
    model_summary: str | None = None
    summary_model: dict[str, Any] | None = None
    summary_error: str | None = None

    def to_entry_dict(self) -> dict[str, Any]:
        """转换为不包含展示概要的语义条目记录。"""

        return {
            "schema_version": TIMELINE_SCHEMA_VERSION,
            "entry_id": self.entry_id,
            "source_event_sequences": list(self.source_event_sequences),
            "created_at_utc": self.created_at_utc,
            "category": self.category,
            "actor": self.actor,
            "action": self.action,
            "outcome": self.outcome,
            "source_refs": list(self.source_refs),
            "facts": self.facts,
        }

    def to_summary_dict(self) -> dict[str, Any]:
        """转换为通过 entry_id 关联的独立概要记录。"""

        return {
            "schema_version": TIMELINE_SCHEMA_VERSION,
            "entry_id": self.entry_id,
            "summary": self.summary,
            "model_summary": self.model_summary,
            "summary_model": self.summary_model,
            "summary_error": self.summary_error,
        }

    @classmethod
    def from_dicts(
        cls,
        entry: dict[str, Any],
        summary: dict[str, Any],
    ) -> "TimelineEntry":
        """读取并关联本生成器写出的语义条目与概要。"""

        if entry.get("schema_version") != TIMELINE_SCHEMA_VERSION:
            raise ValueError("unsupported timeline entry schema_version")
        if summary.get("schema_version") != TIMELINE_SCHEMA_VERSION:
            raise ValueError("unsupported timeline summary schema_version")
        entry_id = _required_string(entry, "entry_id")
        if _required_string(summary, "entry_id") != entry_id:
            raise ValueError("timeline entry and summary IDs differ")
        source_sequences = entry.get("source_event_sequences", [])
        if not isinstance(source_sequences, list) or not all(
            isinstance(item, int) and not isinstance(item, bool) and item > 0
            for item in source_sequences
        ):
            raise TypeError("source_event_sequences must be a positive integer list")
        source_refs = entry.get("source_refs", [])
        facts = entry.get("facts", {})
        if not isinstance(source_refs, list) or not all(
            isinstance(item, str) for item in source_refs
        ):
            raise TypeError("timeline source_refs must be a string list")
        if not isinstance(facts, dict):
            raise TypeError("timeline facts must be an object")
        return cls(
            entry_id=entry_id,
            source_event_sequences=tuple(source_sequences),
            created_at_utc=_required_string(entry, "created_at_utc"),
            category=_required_string(entry, "category"),
            actor=_optional_string(entry.get("actor")),
            action=_required_string(entry, "action"),
            outcome=_optional_string(entry.get("outcome")),
            summary=_required_string(summary, "summary"),
            model_summary=_optional_string(summary.get("model_summary")),
            source_refs=tuple(source_refs),
            facts=dict(facts),
            summary_model=_optional_object(summary.get("summary_model")),
            summary_error=_optional_string(summary.get("summary_error")),
        )


class TimelineSummarizer(Protocol):
    """只改写既有确定性 summary 的可选边界。"""

    def summarize(self, entry: TimelineEntry) -> tuple[str, dict[str, Any]]:
        """返回简短概要和不含密钥的模型调用信息。"""


class OpenAICompatibleTimelineSummarizer:
    """使用 OpenAI-compatible Chat Completions 改写时间线概要。"""

    def __init__(self, model: OpenAICompatibleModel) -> None:
        self.model = model

    @classmethod
    def from_runtime_config(
        cls,
        *,
        env_file: Path | None = None,
        config_file: Path | None = None,
    ) -> "OpenAICompatibleTimelineSummarizer":
        """从 models.summary 构造概要模型，密钥可复用其他 profile。"""

        runtime = read_runtime_config(env_file=env_file, config_file=config_file)
        models = _required_object(runtime, "models")
        profile = _required_object(models, "summary")
        provider = _required_string(profile, "provider")
        if provider != "openai_compatible":
            raise ValueError(f"unsupported summary model provider: {provider}")

        credential_profile = str(profile.get("credential_profile", "summary"))
        env_values = read_env_file(env_file)
        api_key_name = f"{credential_profile.strip().upper()}_API_KEY"
        api_key = get_env_value(env_values, api_key_name) or ""
        base_url = _required_string(profile, "base_url")
        thinking_mode = _thinking_mode(profile.get("thinking_mode"))
        parsed_url = urllib_parse.urlparse(base_url)
        config = OpenAICompatibleConfig(
            base_url=base_url,
            model_id=_required_string(profile, "model_id"),
            api_key=api_key,
            max_tokens=_positive_int(profile.get("max_tokens", 512), "max_tokens"),
            timeout=_positive_number(
                profile.get("request_timeout", 120), "request_timeout"
            ),
            temperature=_number(profile.get("temperature", 0.1), "temperature"),
            seed=_optional_int(profile.get("seed"), "seed"),
            ollama_think=(
                thinking_mode == "enabled"
                if parsed_url.port == 11434 and thinking_mode is not None
                else None
            ),
            thinking_mode=(
                thinking_mode
                if (parsed_url.hostname or "").casefold() == "api.deepseek.com"
                else None
            ),
        )
        return cls(OpenAICompatibleModel(config))

    def summarize(self, entry: TimelineEntry) -> tuple[str, dict[str, Any]]:
        payload = {
            "category": entry.category,
            "actor": entry.actor,
            "action": entry.action,
            "outcome": entry.outcome,
            "summary": entry.summary,
            "facts": entry.facts,
        }
        model_input = ModelInput(
            messages=(
                ChatMessage(
                    role="system",
                    content=(
                        "将给定 Evolution Run 事件改写为一条简洁中文时间线。"
                        "只使用输入事实，不补充推断，不添加角色前缀，最多120字。"
                    ),
                ),
                ChatMessage(
                    role="user",
                    content=json.dumps(payload, ensure_ascii=False),
                ),
            )
        )
        response = self.model.generate(model_input)
        summary = " ".join(response.raw_output.strip().split())
        if not summary:
            raise ValueError("summary model returned empty text")
        if len(summary) > 240:
            raise ValueError("summary model returned more than 240 characters")
        return summary, {
            **self.model.config.provenance(),
            "usage": response.usage,
        }


class TimelineGenerator:
    """按 Journal sequence 增量维护 Evolution Run 行为时间线。"""

    def __init__(self, summarizer: TimelineSummarizer | None = None) -> None:
        self.summarizer = summarizer
        self.projector = JournalProjector()

    def update(self, run_dir: Path, *, rebuild: bool = False) -> list[TimelineEntry]:
        """投影当前所有完整 Journal 记录并持久化新增条目。"""

        run_dir = run_dir.resolve()
        run_id = _read_new_run_id(run_dir / "run.json")
        events, _ = self.projector.load_events(run_dir / "events.jsonl")
        timeline_dir = run_dir / "timeline"
        if rebuild:
            existing: list[TimelineEntry] = []
            last_sequence = 0
        else:
            existing, last_sequence = _load_projection(timeline_dir, run_id)

        journal_last_sequence = events[-1].sequence if events else 0
        if journal_last_sequence < last_sequence:
            raise ValueError("Control Journal is shorter than the timeline cursor")
        works = {
            work.work_id: work
            for work in self.projector.project_work_items(events)
        }
        known_ids = {entry.entry_id for entry in existing}
        additions: list[TimelineEntry] = []
        for event in events:
            if event.sequence <= last_sequence:
                continue
            for entry in _entries_for_event(event, works, run_dir):
                if entry.entry_id in known_ids:
                    continue
                additions.append(self._summarize(entry))
                known_ids.add(entry.entry_id)

        entries = [*existing, *additions]
        _write_projection(
            timeline_dir=timeline_dir,
            run_id=run_id,
            last_sequence=journal_last_sequence,
            entries=entries,
        )
        return entries

    def follow(
        self,
        run_dir: Path,
        *,
        interval_seconds: float = 2.0,
        rebuild: bool = False,
    ) -> None:
        """持续增量更新，直到调用者中断进程。"""

        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        first = True
        while True:
            self.update(run_dir, rebuild=rebuild and first)
            first = False
            time.sleep(interval_seconds)

    def _summarize(self, entry: TimelineEntry) -> TimelineEntry:
        if self.summarizer is None:
            return entry
        try:
            model_summary, metadata = self.summarizer.summarize(entry)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            return replace(
                entry,
                summary_error=f"{type(exc).__name__}: {exc}",
            )
        return replace(
            entry,
            model_summary=model_summary,
            summary_model=metadata,
        )


@dataclass(frozen=True)
class TimelineProjection:
    """绑定到一个 Evolution Run 的自动增量投影。"""

    run_dir: Path
    generator: TimelineGenerator

    def update(self) -> None:
        """将已经提交的 Control Journal 事件投影到 timeline/。"""

        self.generator.update(self.run_dir)


def timeline_projection_from_runtime(
    *,
    run_dir: Path,
    env_file: Path | None = None,
    config_file: Path | None = None,
) -> TimelineProjection | None:
    """按 timeline 配置装配自动投影；禁用时返回 None。"""

    runtime = read_runtime_config(env_file=env_file, config_file=config_file)
    raw_timeline = runtime.get("timeline", {})
    if not isinstance(raw_timeline, dict):
        raise TypeError("runtime config timeline must be an object")
    enabled = _boolean(raw_timeline.get("enabled", True), "timeline.enabled")
    if not enabled:
        return None
    model_summary = _boolean(
        raw_timeline.get("model_summary", False),
        "timeline.model_summary",
    )
    summarizer = (
        OpenAICompatibleTimelineSummarizer.from_runtime_config(
            env_file=env_file,
            config_file=config_file,
        )
        if model_summary
        else None
    )
    return TimelineProjection(
        run_dir=run_dir.resolve(),
        generator=TimelineGenerator(summarizer),
    )


def _entries_for_event(
    event: ObservedEvent,
    works: dict[str, ObservedWorkItem],
    run_dir: Path,
) -> list[TimelineEntry]:
    if event.event_type in {"run_started", "run_resumed", "run_paused", "run_completed"}:
        return [_run_entry(event)]
    if event.event_type == "version_advanced":
        version = _first_string(event.payload, "version_id", "current_version")
        return [
            _mechanism_entry(
                event,
                action="advance_version",
                outcome=version,
                summary=f"Accepted Template Version 推进至 {version or '新版本'}。",
                facts={"version_id": version},
            )
        ]
    if event.event_type == "work_scheduled":
        raw_work = event.payload.get("work")
        if isinstance(raw_work, dict) and _integer(raw_work.get("attempt")) > 1:
            work_id = _first_string(raw_work, "work_id")
            kind = _first_string(raw_work, "kind")
            return [
                _mechanism_entry(
                    event,
                    entry_id=f"journal:{event.sequence}:retry",
                    action="retry_work",
                    summary=f"重试 {kind or 'work'}（attempt {_integer(raw_work.get('attempt'))}）。",
                    facts={"work_id": work_id, "kind": kind, "attempt": raw_work.get("attempt")},
                )
            ]
        return []
    if event.event_type not in {"work_completed", "work_failed"}:
        return []

    work_id = _first_string(event.payload, "work_id")
    work = works.get(work_id or "")
    if work is None:
        raise ValueError(f"terminal work event has no scheduled work: {work_id}")
    if event.event_type == "work_failed":
        return [_failed_work_entry(event, work, run_dir)]
    return _completed_work_entries(event, work, run_dir)


def _completed_work_entries(
    event: ObservedEvent,
    work: ObservedWorkItem,
    run_dir: Path,
) -> list[TimelineEntry]:
    result_ref = _required_string(event.payload, "result_ref")
    effect_path = _resolve_ref(result_ref, run_dir)
    effect = _read_object(effect_path)
    outcome = _required_object(effect, "outcome")
    artifact_refs = _string_refs(effect.get("artifact_refs", {}))
    refs = _normalize_refs([result_ref, *artifact_refs.values()], run_dir)
    output = outcome.get("output") if isinstance(outcome.get("output"), dict) else outcome
    assert isinstance(output, dict)

    if work.kind == "review_evidence":
        entries: list[TimelineEntry] = []
        work_artifact_dir = effect_path.parent.resolve()
        for key, ref in artifact_refs.items():
            if not key.startswith("trial_review_"):
                continue
            path = _resolve_ref(ref, run_dir)
            try:
                path.relative_to(work_artifact_dir)
            except ValueError:
                continue
            entries.append(
                TimelineEntry(
                    entry_id=f"work:{work.work_id}:trial_reviewer:{key}",
                    source_event_sequences=_work_source_sequences(work, event),
                    created_at_utc=event.created_at_utc,
                    category="role",
                    actor="trial_reviewer",
                    action="review_trial",
                    outcome="completed",
                    summary="完成一次试验级证据审查，审查产物已持久化。",
                    source_refs=(_normalize_ref(ref, run_dir),),
                    facts={"artifact_key": key},
                )
            )
        summary, decision, facts = _role_summary("evidence_reviewer", output)
        entries.append(
            TimelineEntry(
                entry_id=f"work:{work.work_id}:evidence_reviewer",
                source_event_sequences=_work_source_sequences(work, event),
                created_at_utc=event.created_at_utc,
                category="role",
                actor="evidence_reviewer",
                action="review_evidence",
                outcome=decision,
                summary=summary,
                source_refs=refs,
                facts=facts,
            )
        )
        return entries

    if work.kind in ROLE_KINDS:
        actor = ROLE_IDS.get(work.kind, work.kind)
        summary, decision, facts = _role_summary(actor, output)
        return [
            TimelineEntry(
                entry_id=f"work:{work.work_id}:{actor}",
                source_event_sequences=_work_source_sequences(work, event),
                created_at_utc=event.created_at_utc,
                category="role",
                actor=actor,
                action=work.kind,
                outcome=decision,
                summary=summary,
                source_refs=refs,
                facts=facts,
            )
        ]

    summary, decision, facts = _mechanism_summary(work.kind, outcome)
    return [
        TimelineEntry(
            entry_id=f"work:{work.work_id}:mechanism",
            source_event_sequences=_work_source_sequences(work, event),
            created_at_utc=event.created_at_utc,
            category="mechanism",
            actor=None,
            action=work.kind,
            outcome=decision,
            summary=summary,
            source_refs=refs,
            facts=facts,
        )
    ]


def _failed_work_entry(
    event: ObservedEvent,
    work: ObservedWorkItem,
    run_dir: Path,
) -> TimelineEntry:
    error = _compact(str(event.payload.get("error", "unknown error")), 200)
    failure_ref = _first_string(event.payload, "failure_artifact")
    actor = (
        "evidence_reviewer"
        if work.kind == "review_evidence"
        else ROLE_IDS.get(work.kind)
    )
    category = "role" if actor else "mechanism"
    return TimelineEntry(
        entry_id=f"work:{work.work_id}:failed",
        source_event_sequences=_work_source_sequences(work, event),
        created_at_utc=event.created_at_utc,
        category=category,
        actor=actor,
        action=f"{work.kind}_failed",
        outcome="failed",
        summary=f"{work.kind} 执行失败：{error}",
        source_refs=(
            (_normalize_ref(failure_ref, run_dir),) if failure_ref else ()
        ),
        facts={"work_id": work.work_id, "kind": work.kind, "error": error},
    )


def _role_summary(actor: str, output: dict[str, Any]) -> tuple[str, str | None, dict[str, Any]]:
    decision = _first_string(output, "decision", "recommendation", "result_kind", "status")
    facts = _scalar_facts(output)
    if actor == "failure_analyst":
        pattern = _compact(str(output.get("pattern", "未提供失败模式")), 220)
        return f"识别失败模式：{pattern}", decision, {"pattern": pattern}
    if actor == "hypothesis_researcher":
        fork_phase = _first_string(output, "fork_phase")
        phases = _phase_names(output.get("phase_plan"))
        return (
            f"提出干预假设，fork phase 为 {fork_phase or '未指定'}"
            f"，计划阶段为 {_join(phases) or '未指定'}。",
            decision,
            {"fork_phase": fork_phase, "phases": phases},
        )
    if actor == "intervention_worker":
        modified = _string_list(output.get("modified_phases"))
        activated = _string_list(output.get("activated_phases"))
        return (
            f"执行干预，激活 {_join(activated) or '无'}；"
            f"实际修改 {_join(modified) or '无'}。",
            decision,
            {"activated_phases": activated, "modified_phases": modified},
        )
    if actor in {"trial_reviewer", "evidence_reviewer"}:
        obligation = _first_string(output, "next_obligation")
        summary = f"完成证据审查，结论为 {decision or '未标注'}。"
        if obligation:
            summary += f" 下一证据义务：{_compact(obligation, 140)}"
        facts.update({"next_obligation": obligation})
        return summary, decision, facts
    return (
        f"完成 {actor} 工作，结论为 {decision or '已产生产物'}。",
        decision,
        facts,
    )


def _mechanism_summary(kind: str, outcome: dict[str, Any]) -> tuple[str, str | None, dict[str, Any]]:
    output = outcome.get("output") if isinstance(outcome.get("output"), dict) else outcome
    assert isinstance(output, dict)
    status = _first_string(output, "status", "decision", "result_kind")
    facts = _scalar_facts(output)
    if kind in {"evaluate_incumbent", "evaluate_candidate"}:
        metrics = outcome.get("metrics")
        if not isinstance(metrics, dict):
            metrics = output.get("metrics")
        answers = metrics.get("answers") if isinstance(metrics, dict) else None
        answers = answers if isinstance(answers, dict) else {}
        accuracy = answers.get("accuracy")
        facts = {
            "accuracy": accuracy,
            "example_count": answers.get("example_count"),
            "stable_correct_count": answers.get("stable_correct_count"),
            "stable_failure_count": answers.get("stable_failure_count"),
            "unstable_count": answers.get("unstable_count"),
        }
        label = "基线" if kind == "evaluate_incumbent" else "Candidate"
        return (
            f"完成{label}评估：accuracy={_format_number(accuracy)}，"
            f"稳定正确 {facts['stable_correct_count']}，稳定失败 "
            f"{facts['stable_failure_count']}，不稳定 {facts['unstable_count']}。",
            status,
            facts,
        )
    if kind == "select_trial":
        assignment = output.get("assignment")
        assignment = assignment if isinstance(assignment, dict) else {}
        facts = _scalar_facts(assignment)
        return (
            "选择试验前缀："
            f"example={assignment.get('example_id', '未知')}，"
            f"replicate={assignment.get('replicate_id', '未知')}，"
            f"prefix={assignment.get('prefix_id', '未知')}。",
            status,
            facts,
        )
    return f"完成机制步骤 {kind}，结果为 {status or 'completed'}。", status, facts


def _run_entry(event: ObservedEvent) -> TimelineEntry:
    descriptions = {
        "run_started": "Evolution Run 已启动。",
        "run_resumed": "Evolution Run 从持久化状态恢复。",
        "run_paused": "Evolution Run 已暂停。",
        "run_completed": "Evolution Run 已完成。",
    }
    reason = _first_string(event.payload, "reason")
    summary = descriptions[event.event_type]
    if reason:
        summary = f"{summary[:-1]}：{_compact(reason, 160)}。"
    return _mechanism_entry(
        event,
        action=event.event_type,
        outcome=event.event_type.removeprefix("run_"),
        summary=summary,
        facts=_scalar_facts(event.payload),
    )


def _mechanism_entry(
    event: ObservedEvent,
    *,
    action: str,
    summary: str,
    outcome: str | None = None,
    facts: dict[str, Any] | None = None,
    entry_id: str | None = None,
) -> TimelineEntry:
    return TimelineEntry(
        entry_id=entry_id or f"journal:{event.sequence}:{action}",
        source_event_sequences=(event.sequence,),
        created_at_utc=event.created_at_utc,
        category="mechanism",
        actor=None,
        action=action,
        outcome=outcome,
        summary=summary,
        facts=facts or {},
    )


def _work_source_sequences(
    work: ObservedWorkItem,
    terminal_event: ObservedEvent,
) -> tuple[int, ...]:
    return tuple(
        event.sequence
        for event in work.events
        if event.sequence <= terminal_event.sequence
    )


def _load_projection(timeline_dir: Path, run_id: str) -> tuple[list[TimelineEntry], int]:
    state_path = timeline_dir / "state.json"
    entries_path = timeline_dir / "entries.jsonl"
    summaries_path = timeline_dir / "summaries.jsonl"
    projection_paths = (state_path, entries_path, summaries_path)
    if not any(path.exists() for path in projection_paths):
        return [], 0
    if not all(path.is_file() for path in projection_paths):
        raise ValueError(
            "timeline state.json, entries.jsonl, and summaries.jsonl "
            "must exist together"
        )
    state = _read_object(state_path)
    if state.get("schema_version") != TIMELINE_SCHEMA_VERSION:
        raise ValueError("unsupported timeline state schema_version")
    if state.get("run_id") != run_id:
        raise ValueError("timeline state belongs to another Evolution Run")
    last_sequence = _required_int(state, "last_control_sequence")
    raw_entries = _read_jsonl_objects(entries_path)
    raw_summaries = _read_jsonl_objects(summaries_path)
    if len(raw_entries) != len(raw_summaries):
        raise ValueError("timeline entry and summary counts differ")
    entries = [
        TimelineEntry.from_dicts(entry, summary)
        for entry, summary in zip(raw_entries, raw_summaries, strict=True)
    ]
    return entries, last_sequence


def _write_projection(
    *,
    timeline_dir: Path,
    run_id: str,
    last_sequence: int,
    entries: list[TimelineEntry],
) -> None:
    timeline_dir.mkdir(parents=True, exist_ok=True)
    entries_text = "".join(
        json.dumps(entry.to_entry_dict(), ensure_ascii=False) + "\n"
        for entry in entries
    )
    summaries_text = "".join(
        json.dumps(entry.to_summary_dict(), ensure_ascii=False) + "\n"
        for entry in entries
    )
    state = {
        "schema_version": TIMELINE_SCHEMA_VERSION,
        "run_id": run_id,
        "last_control_sequence": last_sequence,
        "entry_count": len(entries),
        "summary_count": len(entries),
    }
    _atomic_write(timeline_dir / "entries.jsonl", entries_text)
    _atomic_write(timeline_dir / "summaries.jsonl", summaries_text)
    _atomic_write(
        timeline_dir / "state.json",
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
    )
    for obsolete_name in ("events.jsonl", "timeline.md"):
        obsolete_path = timeline_dir / obsolete_name
        if obsolete_path.exists():
            obsolete_path.unlink()


def _read_jsonl_objects(path: Path) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
        if not isinstance(value, dict):
            raise TypeError(f"{path}:{line_number}: record must be an object")
        values.append(value)
    return values


def _atomic_write(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def _read_new_run_id(path: Path) -> str:
    run = _read_object(path)
    if run.get("schema_version") != 2:
        raise ValueError("timeline generator only supports Evolution Run schema_version 2")
    return _required_string(run, "run_id")


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise TypeError(f"JSON artifact must be an object: {path}")
    return value


def _resolve_ref(ref: str, run_dir: Path) -> Path:
    path = Path(ref)
    return path.resolve() if path.is_absolute() else (run_dir / path).resolve()


def _normalize_refs(refs: list[str], run_dir: Path) -> tuple[str, ...]:
    return tuple(dict.fromkeys(_normalize_ref(ref, run_dir) for ref in refs))


def _normalize_ref(ref: str, run_dir: Path) -> str:
    path = _resolve_ref(ref, run_dir)
    try:
        return path.relative_to(run_dir).as_posix()
    except ValueError:
        return str(path)


def _string_refs(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        raise TypeError("effect artifact_refs must be an object")
    refs: dict[str, str] = {}
    for key, ref in value.items():
        if not isinstance(ref, str):
            raise TypeError("effect artifact_refs values must be strings")
        refs[str(key)] = ref
    return refs


def _scalar_facts(value: dict[str, Any]) -> dict[str, Any]:
    return {
        str(key): item
        for key, item in value.items()
        if item is None or isinstance(item, (str, int, float, bool))
    }


def _compact(value: str, limit: int) -> str:
    compact = " ".join(value.split())
    return compact if len(compact) <= limit else compact[: limit - 1].rstrip() + "…"


def _join(values: list[str]) -> str:
    return "、".join(values)


def _string_list(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _phase_names(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    phases: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        phase = item.get("phase")
        if isinstance(phase, str):
            phases.append(phase)
    return phases


def _format_number(value: object) -> str:
    return f"{value:.4g}" if isinstance(value, (int, float)) and not isinstance(value, bool) else "未知"


def _first_string(value: dict[str, Any], *names: str) -> str | None:
    for name in names:
        item = value.get(name)
        if isinstance(item, str) and item.strip():
            return item.strip()
    return None


def _required_string(value: dict[str, Any], name: str) -> str:
    item = value.get(name)
    if not isinstance(item, str) or not item.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return item.strip()


def _required_object(value: dict[str, Any], name: str) -> dict[str, Any]:
    item = value.get(name)
    if not isinstance(item, dict):
        raise TypeError(f"{name} must be an object")
    return item


def _optional_object(value: object) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise TypeError("optional value must be an object")
    return dict(value)


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("optional value must be a string")
    return value


def _required_int(value: dict[str, Any], name: str) -> int:
    item = value.get(name)
    if not isinstance(item, int) or isinstance(item, bool) or item < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return item


def _integer(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _positive_int(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"summary model {name} must be a positive integer")
    return value


def _optional_int(value: object, name: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"summary model {name} must be an integer")
    return value


def _number(value: object, name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"summary model {name} must be a number")
    return float(value)


def _positive_number(value: object, name: str) -> float:
    number = _number(value, name)
    if number <= 0:
        raise ValueError(f"summary model {name} must be positive")
    return number


def _thinking_mode(value: object) -> str | None:
    if value is None:
        return None
    if value not in {"enabled", "disabled"}:
        raise ValueError("summary model thinking_mode must be enabled or disabled")
    return str(value)


def _boolean(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{name} must be a boolean")
    return value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("update", "follow"):
        item = subparsers.add_parser(command)
        item.add_argument("--run-dir", type=Path, required=True)
        item.add_argument("--env-file", type=Path, default=Path(".env"))
        item.add_argument("--config-file", type=Path)
        item.add_argument("--model-summary", action="store_true")
        item.add_argument("--rebuild", action="store_true")
        if command == "follow":
            item.add_argument("--interval", type=float, default=2.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Timeline CLI 入口。"""

    args = _build_parser().parse_args(argv)
    summarizer = None
    if args.model_summary:
        summarizer = OpenAICompatibleTimelineSummarizer.from_runtime_config(
            env_file=args.env_file,
            config_file=args.config_file,
        )
    generator = TimelineGenerator(summarizer)
    if args.command == "follow":
        try:
            generator.follow(
                args.run_dir,
                interval_seconds=args.interval,
                rebuild=args.rebuild,
            )
        except KeyboardInterrupt:
            return 0
    else:
        entries = generator.update(args.run_dir, rebuild=args.rebuild)
        print(f"timeline entries: {len(entries)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
