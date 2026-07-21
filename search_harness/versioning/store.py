"""Git-backed storage for accepted Harness snapshots."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any

from .journal import IterationEvent, IterationJournal, IterationSession, IterationSummary
from .validation import HarnessValidator, ValidationReport, stage_files
from .workspace import CandidateWorkspace, HarnessSnapshot, content_digest


@dataclass(frozen=True)
class VersionRecord:
    """Metadata for one accepted Git commit."""

    version_id: str
    parent_version: str | None
    git_commit: str
    digest: str
    summary: str
    evaluation: Mapping[str, Any]
    iteration_id: str | None = None


class HarnessVersionStore:
    """Manage accepted Harness versions without persistent candidate copies."""

    def __init__(self, root: Path, *, validator: HarnessValidator | None = None) -> None:
        self.root = root.resolve()
        self.plugins_dir = self.root / "plugins"
        self.checkpoint_file = self.root / "checkpoint.json"
        self.metadata_dir = self.root / ".harness-store"
        self.index_file = self.metadata_dir / "versions.jsonl"
        self.iteration_file = self.metadata_dir / "iterations.jsonl"
        self.iteration_journal = IterationJournal(self.iteration_file)
        self.validator = validator or HarnessValidator()

    def initialize(
        self,
        plugins_root: Path,
        *,
        summary: str = "Initialize Harness baseline",
        evaluation: Mapping[str, Any] | None = None,
        env_file: Path | None = None,
        checkpoint_store_id: str | None = None,
    ) -> VersionRecord:
        """Import and commit the first accepted Harness version."""

        if not summary.strip():
            raise ValueError("version summary must not be empty")
        if (self.root / ".git").exists() or self.index_file.exists():
            raise FileExistsError(f"version store is already initialized: {self.root}")
        snapshot = HarnessSnapshot.from_directory(plugins_root, version_id="source")
        report = self.validator.validate_snapshot(snapshot, env_file=env_file)
        if not report.passed:
            raise ValueError(_format_validation_errors(report))

        self.root.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        selected_store_id = checkpoint_store_id or self.root.name
        if not selected_store_id.strip():
            raise ValueError("checkpoint_store_id must not be empty")
        self.checkpoint_file.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "checkpoint_store_id": selected_store_id,
                    "initialized_from": {
                        "template_root": str(plugins_root.resolve()),
                        "template_digest": snapshot.digest,
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        self._git("init")
        self._git("config", "user.name", "Search Harness Version Store")
        self._git("config", "user.email", "search-harness@local")
        self._git("config", "core.autocrlf", "false")
        self._write_plugins(snapshot.files)
        commit = self._commit(summary)
        record = VersionRecord(
            version_id="harness_v0001",
            parent_version=None,
            git_commit=commit,
            digest=snapshot.digest,
            summary=summary,
            evaluation=MappingProxyType(dict(evaluation or {})),
            iteration_id=None,
        )
        self._append_record(record)
        return record

    @property
    def checkpoint_store_id(self) -> str:
        """返回与磁盘位置无关的 Checkpoint Store 稳定身份。"""

        if not self.checkpoint_file.is_file():
            raise FileNotFoundError(
                f"Harness Checkpoint Store metadata is missing: {self.checkpoint_file}"
            )
        raw = json.loads(self.checkpoint_file.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or raw.get("schema_version") != 1:
            raise ValueError("invalid Harness Checkpoint Store metadata")
        store_id = raw.get("checkpoint_store_id")
        if not isinstance(store_id, str) or not store_id.strip():
            raise ValueError("checkpoint_store_id must be a non-empty string")
        return store_id

    def list_versions(self) -> tuple[VersionRecord, ...]:
        if not self.index_file.exists():
            return ()
        records: list[VersionRecord] = []
        for line in self.index_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            raw = json.loads(line)
            raw["evaluation"] = MappingProxyType(dict(raw.get("evaluation", {})))
            raw.setdefault("iteration_id", None)
            records.append(VersionRecord(**raw))
        return tuple(records)

    def resolve(self, version_id: str) -> HarnessSnapshot:
        """Load an accepted Git tree into an immutable in-memory snapshot."""

        record = self._find_record(version_id)
        listing = self._git_bytes(
            "ls-tree", "-r", "--name-only", record.git_commit, "--", "plugins"
        ).decode("utf-8")
        files: dict[PurePosixPath, bytes] = {}
        for tracked in listing.splitlines():
            if not tracked.startswith("plugins/"):
                continue
            relative = PurePosixPath(tracked.removeprefix("plugins/"))
            files[relative] = self._git_bytes("show", f"{record.git_commit}:{tracked}")
        digest = content_digest(files)
        if digest != record.digest:
            raise ValueError(f"stored digest mismatch for version {version_id}")
        return HarnessSnapshot(
            version_id=record.version_id,
            files=MappingProxyType(files),
            digest=digest,
            git_commit=record.git_commit,
        )

    def open_workspace(self, version_id: str) -> CandidateWorkspace:
        return CandidateWorkspace(self.resolve(version_id))

    def start_iteration(
        self,
        *,
        parent_version: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> IterationSession:
        """Start a durable, resumable attempt from the latest accepted version."""

        versions = self.list_versions()
        if not versions:
            raise RuntimeError("version store is not initialized")
        latest = versions[-1]
        selected = parent_version or latest.version_id
        if selected != latest.version_id:
            raise ValueError("iteration parent must be the latest accepted version")
        return self.iteration_journal.start(
            self,
            self.resolve(selected),
            metadata=metadata,
        )

    def resume_iteration(self, iteration_id: str) -> IterationSession:
        """Reconstruct a pending candidate by replaying its journaled patches."""

        summary = self.iteration_journal.get_summary(iteration_id)
        if summary.status == "pending":
            accepted = next(
                (record for record in self.list_versions() if record.iteration_id == iteration_id),
                None,
            )
            if accepted is not None:
                self.iteration_journal.append(
                    iteration_id,
                    "accepted",
                    {
                        "version_id": accepted.version_id,
                        "git_commit": accepted.git_commit,
                        "candidate_digest": accepted.digest,
                        "summary": accepted.summary,
                        "evaluation": dict(accepted.evaluation),
                        "recovered": True,
                    },
                )
        return self.iteration_journal.resume(self, iteration_id)

    def list_iterations(self) -> tuple[IterationSummary, ...]:
        return self.iteration_journal.list_summaries()

    def get_iteration_events(self, iteration_id: str) -> tuple[IterationEvent, ...]:
        """Return the append-only event stream for one iteration."""

        events = self.iteration_journal.events(iteration_id)
        if not events:
            raise KeyError(f"unknown iteration: {iteration_id}")
        return events

    def validate(
        self,
        workspace: CandidateWorkspace,
        *,
        env_file: Path | None = None,
    ) -> ValidationReport:
        return self.validator.validate(workspace, env_file=env_file)

    def accept(
        self,
        workspace: CandidateWorkspace,
        *,
        summary: str,
        evaluation: Mapping[str, Any] | None = None,
        env_file: Path | None = None,
        iteration_id: str | None = None,
    ) -> VersionRecord:
        """Validate, materialize and Git-commit one candidate atomically."""

        if workspace.digest == workspace.parent.digest:
            raise ValueError("cannot accept a Harness version without changes")
        versions = self.list_versions()
        if not versions:
            raise RuntimeError("version store is not initialized")
        latest = versions[-1]
        if workspace.parent.version_id != latest.version_id:
            raise ValueError("workspace parent must be the latest accepted version")
        accepted_parent = self.resolve(latest.version_id)
        if workspace.parent.digest != accepted_parent.digest:
            raise ValueError("workspace parent does not match the accepted version content")

        report = self.validate(workspace, env_file=env_file)
        if not report.passed:
            raise ValueError(_format_validation_errors(report))
        if report.revision != workspace.revision or report.candidate_digest != workspace.digest:
            raise RuntimeError("workspace changed during validation")

        previous_files = accepted_parent.files
        self._write_plugins(workspace.materialized_files())
        try:
            commit = self._commit(summary)
        except Exception:
            self._write_plugins(previous_files)
            self._git("restore", "--staged", "--worktree", "--", "plugins")
            raise
        version_id = f"harness_v{len(versions) + 1:04d}"
        record = VersionRecord(
            version_id=version_id,
            parent_version=workspace.parent.version_id,
            git_commit=commit,
            digest=workspace.digest,
            summary=summary,
            evaluation=MappingProxyType(dict(evaluation or {})),
            iteration_id=iteration_id,
        )
        self._append_record(record)
        return record

    @contextmanager
    def stage(self, source: HarnessSnapshot | CandidateWorkspace) -> Iterator[Path]:
        files = source.materialized_files() if isinstance(source, CandidateWorkspace) else source.files
        with stage_files(files) as root:
            yield root

    def _write_plugins(self, files: Mapping[PurePosixPath, bytes]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="plugins-next-", dir=self.root) as tmpdir:
            staged = Path(tmpdir) / "plugins"
            staged.mkdir()
            for relative, content in files.items():
                target = staged.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            backup = self.root / ".plugins-backup"
            if backup.exists():
                shutil.rmtree(backup)
            if self.plugins_dir.exists():
                self.plugins_dir.rename(backup)
            try:
                staged.rename(self.plugins_dir)
            except Exception:
                if backup.exists() and not self.plugins_dir.exists():
                    backup.rename(self.plugins_dir)
                raise
            if backup.exists():
                shutil.rmtree(backup)

    def _commit(self, summary: str) -> str:
        if not summary.strip():
            raise ValueError("version summary must not be empty")
        self._git("add", "-A", "--", "plugins")
        self._git("commit", "-m", summary)
        return self._git("rev-parse", "HEAD").strip()

    def _append_record(self, record: VersionRecord) -> None:
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "version_id": record.version_id,
            "parent_version": record.parent_version,
            "git_commit": record.git_commit,
            "digest": record.digest,
            "summary": record.summary,
            "evaluation": dict(record.evaluation),
            "iteration_id": record.iteration_id,
        }
        with self.index_file.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _find_record(self, version_id: str) -> VersionRecord:
        for record in self.list_versions():
            if record.version_id == version_id:
                return record
        raise KeyError(f"unknown Harness version: {version_id}")

    def _git(self, *args: str) -> str:
        return self._git_bytes(*args).decode("utf-8").strip()

    def _git_bytes(self, *args: str) -> bytes:
        try:
            completed = subprocess.run(
                ["git", *args],
                cwd=self.root,
                check=True,
                capture_output=True,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("Git executable is required by HarnessVersionStore") from exc
        except subprocess.CalledProcessError as exc:
            message = exc.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"git {' '.join(args)} failed: {message}") from exc
        return completed.stdout


def _format_validation_errors(report: ValidationReport) -> str:
    return "Harness validation failed: " + "; ".join(report.errors)
