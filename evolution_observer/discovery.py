"""直接子目录范围内的 Evolution Run 发现。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from .models import RunListing


class RunDiscovery:
    """以只读方式发现指定根目录下的实验目录。"""

    def __init__(self, runs_root: Path) -> None:
        self.runs_root = runs_root.resolve()

    def list_runs(self) -> list[RunListing]:
        """列出全部直接子目录；无法读取者也保留在列表中。"""

        if not self.runs_root.exists():
            return []
        if not self.runs_root.is_dir():
            raise ValueError(f"runs root is not a directory: {self.runs_root}")

        listings = [self._inspect_directory(path) for path in self.runs_root.iterdir() if path.is_dir()]
        return sorted(listings, key=lambda item: item.directory_name.lower())

    def resolve_run(self, directory_name: str) -> Path:
        """解析由观察器列表产生的目录名，拒绝路径穿越。"""

        if not directory_name or Path(directory_name).name != directory_name:
            raise ValueError("run identifier must be a direct child directory name")
        candidate = (self.runs_root / directory_name).resolve()
        try:
            candidate.relative_to(self.runs_root)
        except ValueError as exc:
            raise ValueError("run identifier must stay inside runs root") from exc
        if not candidate.is_dir():
            raise FileNotFoundError(f"run directory does not exist: {directory_name}")
        return candidate

    def read_run_metadata(self, directory_name: str) -> dict[str, object]:
        """读取一个有效 Run 的 `run.json` 对象。"""

        run_dir = self.resolve_run(directory_name)
        return _read_run_json(run_dir / "run.json")

    def _inspect_directory(self, directory: Path) -> RunListing:
        modified_at = datetime.fromtimestamp(directory.stat().st_mtime, tz=UTC).isoformat()
        try:
            _read_run_json(directory / "run.json")
        except (OSError, ValueError) as exc:
            return RunListing(
                directory_name=directory.name,
                modified_at_utc=modified_at,
                read_status="unreadable",
                error_summary=str(exc),
            )
        return RunListing(
            directory_name=directory.name,
            modified_at_utc=modified_at,
            read_status="readable",
        )


def _read_run_json(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise ValueError("missing run.json")
    try:
        with path.open("r", encoding="utf-8") as file:
            value = json.load(file)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid run.json: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise ValueError("run.json must contain an object")
    return value
