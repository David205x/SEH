"""Immutable Harness snapshots and transactional in-memory candidate workspaces."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Literal


_DELETED = object()


def normalize_plugin_path(path: str | PurePosixPath) -> PurePosixPath:
    """Validate one plugins-root-relative, POSIX-style file path."""

    text = str(path)
    if not text or "\\" in text:
        raise ValueError("plugin paths must be non-empty POSIX-style relative paths")
    normalized = PurePosixPath(text)
    if normalized.is_absolute() or normalized == PurePosixPath("."):
        raise ValueError("plugin path must be relative to the plugins root")
    if any(part in {"", ".", ".."} for part in normalized.parts):
        raise ValueError("plugin path must not contain empty, '.' or '..' parts")
    return normalized


def content_digest(files: Mapping[PurePosixPath, bytes]) -> str:
    """Return a stable digest for a complete virtual plugins tree."""

    digest = hashlib.sha256()
    for path in sorted(files, key=str):
        digest.update(str(path).encode("utf-8"))
        digest.update(b"\0")
        digest.update(files[path])
        digest.update(b"\0")
    return digest.hexdigest()


@dataclass(frozen=True)
class HarnessSnapshot:
    """One immutable accepted Harness tree held in memory."""

    version_id: str
    files: Mapping[PurePosixPath, bytes]
    digest: str
    git_commit: str | None = None

    @classmethod
    def from_directory(
        cls,
        plugins_root: Path,
        *,
        version_id: str = "unversioned",
        git_commit: str | None = None,
    ) -> HarnessSnapshot:
        root = plugins_root.resolve()
        files: dict[PurePosixPath, bytes] = {}
        for path in sorted(root.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            relative = PurePosixPath(path.relative_to(root).as_posix())
            files[relative] = path.read_bytes()
        immutable = MappingProxyType(files)
        return cls(
            version_id=version_id,
            files=immutable,
            digest=content_digest(immutable),
            git_commit=git_commit,
        )

    def read_bytes(self, path: str | PurePosixPath) -> bytes:
        return self.files[normalize_plugin_path(path)]

    def read_text(self, path: str | PurePosixPath) -> str:
        return self.read_bytes(path).decode("utf-8")


@dataclass(frozen=True)
class FileEdit:
    """One model-facing text-file operation within a transactional patch."""

    operation: Literal["write", "delete"]
    path: str
    content: str | None = None

    def __post_init__(self) -> None:
        normalize_plugin_path(self.path)
        if self.operation == "write" and not isinstance(self.content, str):
            raise ValueError("write edit requires string content")
        if self.operation == "delete" and self.content is not None:
            raise ValueError("delete edit must not contain content")


class CandidateWorkspace:
    """A parent snapshot plus an atomic, in-memory file overlay."""

    def __init__(self, parent: HarnessSnapshot) -> None:
        self.parent = parent
        self._overlay: dict[PurePosixPath, bytes | object] = {}
        self._revision = 0

    @property
    def revision(self) -> int:
        return self._revision

    @property
    def changed_paths(self) -> tuple[PurePosixPath, ...]:
        return tuple(sorted(self._overlay, key=str))

    def exists(self, path: str | PurePosixPath) -> bool:
        normalized = normalize_plugin_path(path)
        value = self._overlay.get(normalized)
        if value is _DELETED:
            return False
        return value is not None or normalized in self.parent.files

    def read_bytes(self, path: str | PurePosixPath) -> bytes:
        normalized = normalize_plugin_path(path)
        value = self._overlay.get(normalized)
        if value is _DELETED:
            raise FileNotFoundError(str(normalized))
        if isinstance(value, bytes):
            return value
        try:
            return self.parent.files[normalized]
        except KeyError as exc:
            raise FileNotFoundError(str(normalized)) from exc

    def read_text(self, path: str | PurePosixPath) -> str:
        return self.read_bytes(path).decode("utf-8")

    def write_bytes(self, path: str | PurePosixPath, content: bytes) -> None:
        normalized = normalize_plugin_path(path)
        if not isinstance(content, bytes):
            raise TypeError("workspace binary content must be bytes")
        self._overlay[normalized] = content
        self._revision += 1

    def write_text(self, path: str | PurePosixPath, content: str) -> None:
        if not isinstance(content, str):
            raise TypeError("workspace text content must be a string")
        self.write_bytes(path, content.encode("utf-8"))

    def delete(self, path: str | PurePosixPath) -> None:
        normalized = normalize_plugin_path(path)
        if not self.exists(normalized):
            raise FileNotFoundError(str(normalized))
        self._overlay[normalized] = _DELETED
        self._revision += 1

    def materialized_files(self) -> Mapping[PurePosixPath, bytes]:
        files = dict(self.parent.files)
        for path, value in self._overlay.items():
            if value is _DELETED:
                files.pop(path, None)
            else:
                if not isinstance(value, bytes):
                    raise TypeError("invalid workspace overlay value")
                files[path] = value
        return MappingProxyType(files)

    @property
    def digest(self) -> str:
        return content_digest(self.materialized_files())

    @contextmanager
    def transaction(self) -> Iterator[CandidateWorkspace]:
        """Commit all enclosed mutations together or restore the prior overlay."""

        overlay_before = dict(self._overlay)
        revision_before = self._revision
        try:
            yield self
        except Exception:
            self._overlay = overlay_before
            self._revision = revision_before
            raise

    def add_extension(
        self,
        *,
        instance_id: str,
        files: Mapping[str, str],
        entrypoint: str = "plugin.py:build",
        config: Mapping[str, Any] | None = None,
        enabled: bool = True,
    ) -> None:
        """Create a mutable extension and its files as one transaction."""

        if not instance_id.strip() or "/" in instance_id or "\\" in instance_id:
            raise ValueError("extension instance_id must be a non-empty path segment")
        if not files:
            raise ValueError("new extension must contain at least one file")
        with self.transaction():
            manifest = json.loads(self.read_text("harness.json"))
            all_components = [
                *manifest.get("tools", []),
                manifest.get("prompt", {}),
                *manifest.get("extensions", []),
            ]
            if any(item.get("instance_id") == instance_id for item in all_components):
                raise ValueError(f"duplicate component instance_id: {instance_id}")

            component_root = PurePosixPath("extensions") / instance_id
            for relative_text, content in files.items():
                relative = normalize_plugin_path(relative_text)
                target = component_root / relative
                if self.exists(target):
                    raise FileExistsError(str(target))
                self.write_text(target, content)

            module_path, separator, factory_name = entrypoint.partition(":")
            if separator != ":" or not module_path or not factory_name:
                raise ValueError("entrypoint must use relative_file.py:factory_name")
            full_entrypoint = f"{component_root.as_posix()}/{module_path}:{factory_name}"
            manifest.setdefault("extensions", []).append(
                {
                    "instance_id": instance_id,
                    "entrypoint": full_entrypoint,
                    "enabled": enabled,
                    "config": dict(config or {}),
                    "evolution_policy": "mutable",
                }
            )
            self.write_text(
                "harness.json",
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            )

    def apply_patch(self, edits: Iterable[FileEdit]) -> None:
        """Apply a complete file patch, rolling back every edit on failure."""

        operations = tuple(edits)
        if not operations:
            raise ValueError("patch must contain at least one file edit")
        with self.transaction():
            for edit in operations:
                if edit.operation == "write":
                    if edit.content is None:
                        raise ValueError("write edit requires content")
                    self.write_text(edit.path, edit.content)
                elif edit.operation == "delete":
                    self.delete(edit.path)
                else:
                    raise ValueError(f"unsupported file edit operation: {edit.operation}")
