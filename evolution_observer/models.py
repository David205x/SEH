"""观察器的只读投影数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RunListing:
    """观察根目录下一个直接子目录的展示信息。"""

    directory_name: str
    modified_at_utc: str
    read_status: str
    error_summary: str | None = None

    def to_dict(self) -> dict[str, object]:
        """转换为 API 响应。"""

        return {
            "directory_name": self.directory_name,
            "modified_at_utc": self.modified_at_utc,
            "read_status": self.read_status,
            "error_summary": self.error_summary,
        }


@dataclass(frozen=True)
class ObservedEvent:
    """一条未经语义改写的 Control Journal 事件。"""

    sequence: int
    event_type: str
    created_at_utc: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, object]:
        """转换为 API 响应。"""

        return {
            "sequence": self.sequence,
            "event_type": self.event_type,
            "created_at_utc": self.created_at_utc,
            "payload": self.payload,
        }


@dataclass
class ObservedWorkItem:
    """由同一 Work ID 的 Journal 事件投影出的业务进展项。"""

    work_id: str
    kind: str
    category: str
    subject_ref: str | None
    parent_work_id: str | None
    attempt: int | None
    generation: int | None
    status: str = "queued"
    started_at_utc: str | None = None
    ended_at_utc: str | None = None
    total_tokens: int | None = None
    result_ref: str | None = None
    error: str | None = None
    events: list[ObservedEvent] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """转换为 API 响应，原始事件保留为可展开的审计内容。"""

        return {
            "work_id": self.work_id,
            "kind": self.kind,
            "category": self.category,
            "subject_ref": self.subject_ref,
            "parent_work_id": self.parent_work_id,
            "attempt": self.attempt,
            "generation": self.generation,
            "status": self.status,
            "started_at_utc": self.started_at_utc,
            "ended_at_utc": self.ended_at_utc,
            "total_tokens": self.total_tokens,
            "result_ref": self.result_ref,
            "error": self.error,
            "events": [event.to_dict() for event in self.events],
        }


@dataclass(frozen=True)
class ContentBlock:
    """一段可独立折叠和筛选的轨迹内容。"""

    block_id: str
    block_type: str
    role: str | None
    title: str
    content: str
    default_collapsed: bool
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """转换为前端内容块协议。"""

        return {
            "block_id": self.block_id,
            "block_type": self.block_type,
            "role": self.role,
            "title": self.title,
            "content": self.content,
            "default_collapsed": self.default_collapsed,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class ObservedTrajectory:
    """一个可选取查看的模型或角色轨迹。"""

    trajectory_id: str
    label: str
    summary: str
    source_ref: str
    blocks: tuple[ContentBlock, ...]
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """转换为前端轨迹协议。"""

        return {
            "trajectory_id": self.trajectory_id,
            "label": self.label,
            "summary": self.summary,
            "source_ref": self.source_ref,
            "blocks": [block.to_dict() for block in self.blocks],
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class ObservedWorkDetail:
    """一个 WorkItem 的控制事件和可阅读产物投影。"""

    work: ObservedWorkItem
    trajectories: tuple[ObservedTrajectory, ...]
    artifact_refs: dict[str, str]
    artifact_errors: dict[str, str]
    detail_message: str | None

    def to_dict(self) -> dict[str, object]:
        """转换为详情页 API 响应。"""

        return {
            "work": self.work.to_dict(),
            "trajectories": [trajectory.to_dict() for trajectory in self.trajectories],
            "artifact_refs": self.artifact_refs,
            "artifact_errors": self.artifact_errors,
            "detail_message": self.detail_message,
        }
