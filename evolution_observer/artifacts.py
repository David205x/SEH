"""将 WorkItem 引用的只读 Artifact 投影为通用轨迹内容块。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import (
    ContentBlock,
    ObservedTrajectory,
    ObservedWorkDetail,
    ObservedWorkItem,
)


class ArtifactProjector:
    """读取 Journal 已持久化的引用，不修改实验目录。"""

    def project(self, run_dir: Path, work: ObservedWorkItem) -> ObservedWorkDetail:
        """投影一个 WorkItem；没有对话产物时返回空轨迹列表。"""

        artifact_refs: dict[str, str] = {}
        artifact_errors: dict[str, str] = {}
        trajectories: list[ObservedTrajectory] = []
        seen_trajectory_sources: set[str] = set()
        if work.result_ref is None:
            return ObservedWorkDetail(
                work=work,
                trajectories=(),
                artifact_refs={},
                artifact_errors={},
                detail_message="该 WorkItem 尚未记录结果产物。",
            )

        effect_path = _resolve_reference(work.result_ref, run_dir)
        artifact_refs["effect"] = str(effect_path)
        try:
            effect = _read_json_object(effect_path)
        except (FileNotFoundError, ValueError) as exc:
            artifact_errors["effect"] = str(exc)
            return ObservedWorkDetail(
                work=work,
                trajectories=(),
                artifact_refs=artifact_refs,
                artifact_errors=artifact_errors,
                detail_message="结果引用无法读取；控制事件仍可审计。",
            )

        raw_refs = effect.get("artifact_refs")
        if isinstance(raw_refs, dict):
            for name, reference in raw_refs.items():
                if isinstance(name, str) and isinstance(reference, str):
                    artifact_refs[name] = str(
                        _resolve_reference(reference, run_dir, effect_path.parent)
                    )

        for name, reference in list(artifact_refs.items()):
            if name == "effect":
                continue
            artifact_path = Path(reference)
            try:
                artifact = _read_json_object(artifact_path)
            except (FileNotFoundError, ValueError) as exc:
                artifact_errors[name] = str(exc)
                continue
            trajectory = _role_trajectory(name, artifact_path, artifact)
            if trajectory is None:
                trajectory = _referenced_role_trajectory(
                    name,
                    artifact_path,
                    artifact,
                    run_dir,
                    artifact_refs,
                    artifact_errors,
                )
            if trajectory is not None:
                if trajectory.source_ref in seen_trajectory_sources:
                    continue
                seen_trajectory_sources.add(trajectory.source_ref)
                trajectories.append(trajectory)

        message = None
        if not trajectories:
            message = "该 WorkItem 有控制产物，但没有可转换为对话的 transcript。"
        return ObservedWorkDetail(
            work=work,
            trajectories=tuple(trajectories),
            artifact_refs=artifact_refs,
            artifact_errors=artifact_errors,
            detail_message=message,
        )

    def project_with_related_fallback(
        self,
        run_dir: Path,
        work: ObservedWorkItem,
        related_work: ObservedWorkItem,
    ) -> ObservedWorkDetail:
        """缺少自身对话时，投影直接关联 WorkItem 的角色轨迹。"""

        detail = self.project(run_dir, work)
        if detail.trajectories:
            return detail
        related = self.project(run_dir, related_work)
        if not related.trajectories:
            return detail
        return ObservedWorkDetail(
            work=work,
            trajectories=related.trajectories,
            artifact_refs={
                **detail.artifact_refs,
                **{
                    f"related.{name}": reference
                    for name, reference in related.artifact_refs.items()
                },
            },
            artifact_errors={
                **detail.artifact_errors,
                **{
                    f"related.{name}": error
                    for name, error in related.artifact_errors.items()
                },
            },
            detail_message=(
                f"对话来自触发该事件的父 WorkItem：{related_work.work_id}。"
            ),
        )


def _role_trajectory(
    reference_name: str,
    artifact_path: Path,
    artifact: dict[str, Any],
) -> ObservedTrajectory | None:
    transcript = artifact.get("transcript")
    if not isinstance(transcript, list):
        return None
    blocks = _transcript_blocks(transcript)
    if not blocks:
        return None

    role = artifact.get("role")
    role_id = role.get("id") if isinstance(role, dict) else None
    model = artifact.get("model")
    model_id = model.get("model_id") if isinstance(model, dict) else None
    provider = model.get("provider") if isinstance(model, dict) else None
    usage = artifact.get("usage")
    metadata = {
        "role_id": role_id,
        "model_id": model_id,
        "provider": provider,
        "usage": usage if isinstance(usage, dict) else {},
    }
    label = _trajectory_label(role_id, reference_name, artifact_path)
    summary_parts = [f"{len(blocks)} blocks"]
    if isinstance(model_id, str):
        summary_parts.append(model_id)
    return ObservedTrajectory(
        trajectory_id=reference_name,
        label=label,
        summary=" · ".join(summary_parts),
        source_ref=str(artifact_path),
        blocks=tuple(blocks),
        metadata=metadata,
    )


def _trajectory_label(
    role_id: object,
    reference_name: str,
    artifact_path: Path,
) -> str:
    label = str(role_id or reference_name).replace("_", " ").title()
    if not reference_name.startswith("conformance_finding_"):
        return label
    source_label = artifact_path.stem.replace("_", " ").title()
    return f"{label} · {source_label}"


def _referenced_role_trajectory(
    reference_name: str,
    artifact_path: Path,
    artifact: dict[str, Any],
    run_dir: Path,
    artifact_refs: dict[str, str],
    artifact_errors: dict[str, str],
) -> ObservedTrajectory | None:
    """解包 checkpoint finding 指向的角色会话产物。"""

    role_reference = artifact.get("role_artifact_ref")
    if not isinstance(role_reference, str):
        return None
    nested_name = f"{reference_name}.role"
    role_path = _resolve_reference(role_reference, run_dir, artifact_path.parent)
    artifact_refs[nested_name] = str(role_path)
    try:
        role_wrapper = _read_json_object(role_path)
    except (FileNotFoundError, ValueError) as exc:
        artifact_errors[nested_name] = str(exc)
        return None
    embedded_role = role_wrapper.get("role_artifact")
    role_artifact = embedded_role if isinstance(embedded_role, dict) else role_wrapper
    return _role_trajectory(nested_name, role_path, role_artifact)


def _transcript_blocks(transcript: list[object]) -> list[ContentBlock]:
    blocks: list[ContentBlock] = []
    tool_names: dict[str, str] = {}
    for item_index, raw_item in enumerate(transcript):
        if not isinstance(raw_item, dict):
            continue
        role = raw_item.get("role")
        role_name = role if isinstance(role, str) else None
        prefix = f"transcript-{item_index}"
        reasoning = raw_item.get("reasoning_content")
        if isinstance(reasoning, str) and reasoning.strip():
            blocks.append(
                ContentBlock(
                    block_id=f"{prefix}-reasoning",
                    block_type="reasoning",
                    role="assistant",
                    title="Reasoning",
                    content=reasoning,
                    default_collapsed=True,
                )
            )

        content = raw_item.get("content")
        if isinstance(content, str) and content.strip():
            block_type = "tool_result" if role_name == "tool" else "message"
            title = _message_title(role_name)
            metadata: dict[str, object] = {}
            tool_call_id = raw_item.get("tool_call_id")
            if isinstance(tool_call_id, str):
                metadata["tool_call_id"] = tool_call_id
                tool_name = tool_names.get(tool_call_id)
                if tool_name is not None:
                    title = f"Tool Result · {tool_name}"
                    metadata["tool_name"] = tool_name
            blocks.append(
                ContentBlock(
                    block_id=f"{prefix}-content",
                    block_type=block_type,
                    role=role_name,
                    title=title,
                    content=_format_content(content),
                    default_collapsed=role_name in {"system", "tool"},
                    metadata=metadata,
                )
            )

        tool_calls = raw_item.get("tool_calls")
        if isinstance(tool_calls, list):
            for call_index, raw_call in enumerate(tool_calls):
                if not isinstance(raw_call, dict):
                    continue
                function = raw_call.get("function")
                function_value = function if isinstance(function, dict) else {}
                name = function_value.get("name")
                tool_name = name if isinstance(name, str) else "unknown"
                call_id = raw_call.get("id")
                if isinstance(call_id, str):
                    tool_names[call_id] = tool_name
                blocks.append(
                    ContentBlock(
                        block_id=f"{prefix}-tool-{call_index}",
                        block_type="tool_call",
                        role="assistant",
                        title=f"Tool Call · {tool_name}",
                        content=_format_content(function_value.get("arguments")),
                        default_collapsed=False,
                        metadata={
                            "tool_name": tool_name,
                            "tool_call_id": call_id,
                        },
                    )
                )
    return blocks


def _message_title(role: str | None) -> str:
    return {
        "system": "System",
        "user": "User",
        "assistant": "Assistant",
        "tool": "Tool Result",
    }.get(role, "Message")


def _format_content(value: object) -> str:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(("{", "[")):
            try:
                return json.dumps(json.loads(stripped), ensure_ascii=False, indent=2)
            except json.JSONDecodeError:
                return value
        return value
    return json.dumps(value, ensure_ascii=False, indent=2)


def _resolve_reference(
    reference: str,
    run_dir: Path,
    base_dir: Path | None = None,
) -> Path:
    path = Path(reference)
    if path.is_absolute():
        return path.resolve()
    run_relative = (run_dir / path).resolve()
    if run_relative.is_file() or base_dir is None:
        return run_relative
    return (base_dir / path).resolve()


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"missing artifact: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON artifact: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"artifact must be a JSON object: {path}")
    return value
