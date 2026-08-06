"""Read-only HTTP server and data model for the local trace visualizer."""

from __future__ import annotations

import json
import logging
import mimetypes
from collections.abc import Mapping
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, urlparse

from search_harness.framework.harness import (
    assemble_harness_components,
    describe_harness,
)
from search_harness.paths import (
    COMPONENT_RUNS_ROOT,
    DEFAULT_CHECKPOINT_STORE,
)
from search_harness.versioning import (
    HarnessVersionStore,
    VersionRecord,
    load_evolution_policy,
)


LOGGER = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / "static"
TRACE_SUFFIXES = {".json", ".jsonl"}


@dataclass(frozen=True)
class TraceFile:
    """A trace file visible in the local browser."""

    path: str
    size_bytes: int

    def to_dict(self) -> dict[str, object]:
        return {"path": self.path, "size_bytes": self.size_bytes}


class TraceStore:
    """Safely list and load JSON/JSONL files from one configured directory."""

    def __init__(self, traces_dir: Path) -> None:
        self.traces_dir = traces_dir.resolve()

    def list_files(self) -> list[TraceFile]:
        if not self.traces_dir.exists():
            return []
        if not self.traces_dir.is_dir():
            raise ValueError(f"trace path is not a directory: {self.traces_dir}")

        files = [
            TraceFile(
                path=path.relative_to(self.traces_dir).as_posix(),
                size_bytes=path.stat().st_size,
            )
            for path in self.traces_dir.rglob("*")
            if path.is_file()
            and path.suffix.lower() in TRACE_SUFFIXES
            and path.name not in {"run.json", "summary.json", "per_example.jsonl"}
            and "evaluation" not in path.relative_to(self.traces_dir).parts
        ]
        return sorted(files, key=lambda item: item.path.lower())

    def load_file(self, relative_path: str) -> dict[str, object]:
        path = self._resolve_trace_path(relative_path)
        if path.suffix.lower() == ".jsonl":
            values = _read_jsonl(path)
            format_name = "jsonl"
        else:
            values = _read_json(path)
            format_name = "json"

        raw_entries = values if isinstance(values, list) else [values]
        entries = [_normalize_entry(value, index) for index, value in enumerate(raw_entries)]
        return {
            "source": path.relative_to(self.traces_dir).as_posix(),
            "format": format_name,
            "entries": entries,
        }

    def _resolve_trace_path(self, relative_path: str) -> Path:
        candidate = (self.traces_dir / relative_path).resolve()
        try:
            candidate.relative_to(self.traces_dir)
        except ValueError as exc:
            raise ValueError("trace path must stay inside traces directory") from exc
        if candidate.suffix.lower() not in TRACE_SUFFIXES:
            raise ValueError("trace file must end in .json or .jsonl")
        if not candidate.is_file():
            raise FileNotFoundError(f"trace file does not exist: {relative_path}")
        return candidate


class ReportStore:
    """Safely expose generated evaluation report directories to the browser."""

    def __init__(self, reports_dir: Path) -> None:
        self.reports_dir = reports_dir.resolve()

    def list_reports(self) -> list[TraceFile]:
        if not self.reports_dir.exists():
            return []
        if not self.reports_dir.is_dir():
            raise ValueError(f"report path is not a directory: {self.reports_dir}")
        reports = []
        for summary in self.reports_dir.rglob("summary.json"):
            if not (summary.parent / "per_example.jsonl").is_file():
                continue
            reports.append(
                TraceFile(
                    path=summary.parent.relative_to(self.reports_dir).as_posix(),
                    size_bytes=summary.stat().st_size,
                )
            )
        return sorted(reports, key=lambda item: item.path.lower())

    def load_report(self, relative_path: str) -> dict[str, object]:
        report_dir = self._resolve_report_path(relative_path)
        summary = _read_json(report_dir / "summary.json")
        items = _read_jsonl(report_dir / "per_example.jsonl")
        if not isinstance(summary, dict):
            raise ValueError("report summary must be an object")
        return {"source": relative_path, "summary": summary, "items": items}

    def _resolve_report_path(self, relative_path: str) -> Path:
        candidate = (self.reports_dir / relative_path).resolve()
        try:
            candidate.relative_to(self.reports_dir)
        except ValueError as exc:
            raise ValueError("report path must stay inside reports directory") from exc
        if not candidate.is_dir():
            raise FileNotFoundError(f"report does not exist: {relative_path}")
        if not (candidate / "summary.json").is_file() or not (candidate / "per_example.jsonl").is_file():
            raise ValueError("report requires summary.json and per_example.jsonl")
        return candidate


class HarnessEvolutionStore:
    """Read-only projection of one configured Harness Version Store."""

    def __init__(
        self,
        store_dir: Path | None,
        *,
        env_file: Path | None = Path(".env"),
    ) -> None:
        self.store_dir = store_dir.resolve() if store_dir is not None else None
        self.env_file = env_file.resolve() if env_file is not None else None

    def overview(self) -> dict[str, object]:
        if self.store_dir is None:
            return {"configured": False, "versions": [], "iterations": []}
        store = HarnessVersionStore(self.store_dir)
        return {
            "configured": True,
            "root": str(self.store_dir),
            "initialized": (self.store_dir / ".git").is_dir()
            and store.index_file.is_file(),
            "versions": [_version_to_dict(item) for item in store.list_versions()],
            "iterations": [
                {
                    "iteration_id": item.iteration_id,
                    "parent_version": item.parent_version,
                    "status": item.status,
                    "candidate_digest": item.candidate_digest,
                    "patch_count": item.patch_count,
                    "accepted_version": item.accepted_version,
                    "rejection_reason": item.rejection_reason,
                }
                for item in store.list_iterations()
            ],
        }

    def load_iteration(self, iteration_id: str) -> dict[str, object]:
        store = self._require_store()
        summary = next(
            (item for item in store.list_iterations() if item.iteration_id == iteration_id),
            None,
        )
        if summary is None:
            raise FileNotFoundError(f"iteration does not exist: {iteration_id}")
        events = store.get_iteration_events(iteration_id)
        return {
            "summary": {
                "iteration_id": summary.iteration_id,
                "parent_version": summary.parent_version,
                "status": summary.status,
                "candidate_digest": summary.candidate_digest,
                "patch_count": summary.patch_count,
                "accepted_version": summary.accepted_version,
                "rejection_reason": summary.rejection_reason,
            },
            "events": [
                {
                    "schema_version": event.schema_version,
                    "sequence": event.sequence,
                    "event_type": event.event_type,
                    "timestamp": event.timestamp,
                    "payload": dict(event.payload),
                }
                for event in events
            ],
        }

    def load_version(self, version_id: str) -> dict[str, object]:
        store = self._require_store()
        record = next(
            (item for item in store.list_versions() if item.version_id == version_id),
            None,
        )
        if record is None:
            raise FileNotFoundError(f"Harness version does not exist: {version_id}")
        snapshot = store.resolve(version_id)
        parent = store.resolve(record.parent_version) if record.parent_version else None
        added, modified, removed = _snapshot_changes(snapshot.files, parent.files if parent else {})
        try:
            manifest = json.loads(snapshot.read_text("harness.json"))
        except (KeyError, UnicodeDecodeError, json.JSONDecodeError):
            manifest = None
        return {
            "version": _version_to_dict(record),
            "manifest": manifest,
            "files": [
                {"path": str(path), "size_bytes": len(content)}
                for path, content in sorted(snapshot.files.items(), key=lambda item: str(item[0]))
            ],
            "changes": {
                "added": added,
                "modified": modified,
                "removed": removed,
            },
        }

    def load_topology(self, version_id: str) -> dict[str, object]:
        """Assemble one accepted snapshot and project its declared topology."""

        store = self._require_store()
        snapshot = store.resolve(version_id)
        with store.stage(snapshot) as template_root:
            components = assemble_harness_components(
                template_root,
                env_file=self.env_file,
            )
            policy = load_evolution_policy(template_root)
        return {
            "version_id": version_id,
            "digest": snapshot.digest,
            "topology": describe_harness(
                components,
                component_policies={
                    instance_id: value.value
                    for instance_id, value in policy.components.items()
                },
            ),
        }

    def _require_store(self) -> HarnessVersionStore:
        if self.store_dir is None:
            raise ValueError("Harness Checkpoint Store directory is not configured")
        store = HarnessVersionStore(self.store_dir)
        if not (self.store_dir / ".git").is_dir() or not store.index_file.is_file():
            raise FileNotFoundError(
                f"Harness Checkpoint Store is not initialized: {self.store_dir}"
            )
        return store


def serve(
    host: str,
    port: int,
    student_runs_dir: Path = COMPONENT_RUNS_ROOT / "student",
    evaluation_runs_dir: Path = COMPONENT_RUNS_ROOT,
    checkpoint_store: Path | None = DEFAULT_CHECKPOINT_STORE,
    env_file: Path | None = Path(".env"),
) -> None:
    """Serve the visualizer until interrupted."""

    if not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    store = TraceStore(student_runs_dir)
    report_store = ReportStore(evaluation_runs_dir)
    evolution_store = HarnessEvolutionStore(
        checkpoint_store,
        env_file=env_file,
    )
    server = ThreadingHTTPServer(
        (host, port),
        _handler_for(
            store,
            report_store,
            evolution_store,
        ),
    )
    print(f"Trace visualizer: http://{host}:{port}")
    print(f"Student runs directory: {store.traces_dir}")
    print(f"Evaluation runs directory: {report_store.reports_dir}")
    if evolution_store.store_dir is not None:
        print(f"Harness Checkpoint Store: {evolution_store.store_dir}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nTrace visualizer stopped.")
    finally:
        server.server_close()


def _handler_for(
    store: TraceStore,
    report_store: ReportStore,
    evolution_store: HarnessEvolutionStore,
) -> type[BaseHTTPRequestHandler]:
    class TraceRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/api/files":
                    self._send_json({"files": [item.to_dict() for item in store.list_files()]})
                    return
                if parsed.path == "/api/file":
                    query = parse_qs(parsed.query)
                    relative_path = query.get("path", [""])[0]
                    if not relative_path:
                        raise ValueError("query parameter 'path' is required")
                    self._send_json(store.load_file(relative_path))
                    return
                if parsed.path == "/api/reports":
                    self._send_json({"reports": [item.to_dict() for item in report_store.list_reports()]})
                    return
                if parsed.path == "/api/report":
                    query = parse_qs(parsed.query)
                    relative_path = query.get("path", [""])[0]
                    if not relative_path:
                        raise ValueError("query parameter 'path' is required")
                    self._send_json(report_store.load_report(relative_path))
                    return
                if parsed.path == "/api/harness-store":
                    self._send_json(evolution_store.overview())
                    return
                if parsed.path == "/api/harness-iteration":
                    query = parse_qs(parsed.query)
                    iteration_id = query.get("id", [""])[0]
                    if not iteration_id:
                        raise ValueError("query parameter 'id' is required")
                    self._send_json(evolution_store.load_iteration(iteration_id))
                    return
                if parsed.path == "/api/harness-version":
                    query = parse_qs(parsed.query)
                    version_id = query.get("id", [""])[0]
                    if not version_id:
                        raise ValueError("query parameter 'id' is required")
                    self._send_json(evolution_store.load_version(version_id))
                    return
                if parsed.path == "/api/harness-topology":
                    query = parse_qs(parsed.query)
                    version_id = query.get("id", [""])[0]
                    if not version_id:
                        raise ValueError("query parameter 'id' is required")
                    self._send_json(evolution_store.load_topology(version_id))
                    return
                self._send_static(parsed.path)
            except FileNotFoundError as exc:
                self._send_error_json(HTTPStatus.NOT_FOUND, str(exc))
            except ValueError as exc:
                self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            except Exception:
                LOGGER.exception("unexpected visualizer request failure")
                self._send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, "internal server error")

        def _send_static(self, request_path: str) -> None:
            relative = "index.html" if request_path in {"", "/"} else request_path.lstrip("/")
            candidate = (STATIC_DIR / relative).resolve()
            try:
                candidate.relative_to(STATIC_DIR.resolve())
            except ValueError:
                self._send_error_json(HTTPStatus.NOT_FOUND, "asset not found")
                return
            if not candidate.is_file():
                self._send_error_json(HTTPStatus.NOT_FOUND, "asset not found")
                return
            content = candidate.read_bytes()
            content_type, _ = mimetypes.guess_type(candidate.name)
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type or "application/octet-stream")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def _send_json(self, payload: dict[str, object]) -> None:
            content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def _send_error_json(self, status: HTTPStatus, message: str) -> None:
            content = json.dumps({"error": message}, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, format: str, *args: object) -> None:
            LOGGER.info("%s - %s", self.address_string(), format % args)

    return TraceRequestHandler


def _read_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _read_jsonl(path: Path) -> list[object]:
    values: list[object] = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, raw_line in enumerate(file, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                values.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSONL record") from exc
    return values


def _normalize_entry(value: object, index: int) -> dict[str, object]:
    if not isinstance(value, dict):
        return {
            "index": index,
            "label": f"Entry {index + 1}",
            "run": None,
            "runner_error": {"type": "InvalidTrace", "message": "entry must be an object"},
        }

    example = value.get("example")
    is_batch_record = any(key in value for key in ("example", "run", "runner_error"))
    run = value.get("run") if is_batch_record else value
    runner_error = value.get("runner_error")
    if not isinstance(example, dict):
        example = None
    if not isinstance(runner_error, dict):
        runner_error = None

    label = _entry_label(index, example, run)
    return {
        "index": index,
        "label": label,
        "example": example,
        "run": run if isinstance(run, dict) else None,
        "runner_error": runner_error,
    }


def _entry_label(index: int, example: dict[str, object] | None, run: object) -> str:
    if example is not None:
        example_id = example.get("example_id")
        if isinstance(example_id, str) and example_id:
            return example_id
    if isinstance(run, dict):
        question = run.get("question")
        if isinstance(question, str) and question:
            return question[:80]
    return f"Trace {index + 1}"


def _version_to_dict(record: VersionRecord) -> dict[str, object]:
    return {
        "version_id": record.version_id,
        "parent_version": record.parent_version,
        "git_commit": record.git_commit,
        "digest": record.digest,
        "summary": record.summary,
        "evaluation": dict(record.evaluation),
        "iteration_id": record.iteration_id,
    }


def _snapshot_changes(
    current: Mapping[PurePosixPath, bytes],
    parent: Mapping[PurePosixPath, bytes],
) -> tuple[list[str], list[str], list[str]]:
    current_paths = set(current)
    parent_paths = set(parent)
    added = sorted((str(path) for path in current_paths - parent_paths), key=str.lower)
    removed = sorted((str(path) for path in parent_paths - current_paths), key=str.lower)
    modified = sorted(
        (str(path) for path in current_paths & parent_paths if current[path] != parent[path]),
        key=str.lower,
    )
    return added, modified, removed
