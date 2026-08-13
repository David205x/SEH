"""Evolution Experiment Observer 的只读本地 HTTP 服务。"""

from __future__ import annotations

import json
import logging
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .artifacts import ArtifactProjector
from .discovery import RunDiscovery
from .flow import (
    filter_node_events,
    node_work_kinds,
    project_generation_flows,
)
from .journal import JournalProjector
from .statistics import project_run_statistics


LOGGER = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / "static"
ASSET_DIR = Path(__file__).parent / "asset"
mimetypes.add_type("font/otf", ".otf")


class ObserverService:
    """协调只读发现与 Journal 投影，不持久化任何状态。"""

    def __init__(self, runs_root: Path) -> None:
        self.discovery = RunDiscovery(runs_root)
        self.journal = JournalProjector()
        self.artifacts = ArtifactProjector()

    def list_runs(self) -> dict[str, object]:
        return {"runs": [item.to_dict() for item in self.discovery.list_runs()]}

    def overview(self, run_name: str) -> dict[str, object]:
        metadata = self.discovery.read_run_metadata(run_name)
        events, pending_tail = self._events(run_name)
        works = self.journal.project_work_items(events)
        generations = [work.generation for work in works if work.generation is not None]
        run_status = self.journal.run_status(events)
        generation_flows = project_generation_flows(
            works,
            metadata,
            run_status,
        )
        return {
            "directory_name": run_name,
            "run_metadata": metadata,
            "journal_status": run_status,
            "last_event_at_utc": events[-1].created_at_utc if events else None,
            "pending_journal_tail": pending_tail,
            "generation": max(generations) if generations else None,
            "completed_generation_count": _completed_generation_count(works),
            "flow": generation_flows[-1]["flow"] if generation_flows else [],
            "generation_flows": generation_flows,
            "recent_works": [work.to_dict() for work in works[:5]],
            "work_counts": _work_counts(works),
            "statistics": project_run_statistics(
                self.discovery.resolve_run(run_name),
                events,
                works,
                metadata,
            ),
        }

    def works(
        self,
        run_name: str,
        category: str | None,
        status: str | None,
        node_kind: str | None,
        generation: int | None,
    ) -> dict[str, object]:
        events, pending_tail = self._events(run_name)
        works = self.journal.project_work_items(events)
        selected_kinds = (
            node_work_kinds(node_kind)
            if node_kind is not None
            else None
        )
        filtered = [
            work
            for work in works
            if (category is None or work.category == category)
            and (status is None or work.status == status)
            and (selected_kinds is None or work.kind in selected_kinds)
            and (generation is None or work.generation == generation)
        ]
        return {
            "works": [work.to_dict() for work in filtered],
            "pending_journal_tail": pending_tail,
        }

    def journal_events(
        self,
        run_name: str,
        node_kind: str | None,
        generation: int | None,
    ) -> dict[str, object]:
        events, pending_tail = self._events(run_name)
        if node_kind is not None:
            works = self.journal.project_work_items(events)
            events = filter_node_events(
                events,
                works,
                node_kind,
                generation,
            )
        return {
            "events": [event.to_dict() for event in reversed(events)],
            "pending_journal_tail": pending_tail,
        }

    def work_detail(self, run_name: str, work_id: str) -> dict[str, object]:
        """返回一个 WorkItem 的控制事件与可阅读 Artifact。"""

        run_dir = self.discovery.resolve_run(run_name)
        events, _ = self._events(run_name)
        works = self.journal.project_work_items(events)
        work = next((item for item in works if item.work_id == work_id), None)
        if work is None:
            raise FileNotFoundError(f"missing WorkItem: {work_id}")
        return self.artifacts.project(run_dir, work).to_dict()

    def refresh_state(self, run_name: str) -> dict[str, object]:
        events, pending_tail = self._events(run_name)
        return {
            "last_sequence": events[-1].sequence if events else None,
            "last_event_at_utc": events[-1].created_at_utc if events else None,
            "pending_journal_tail": pending_tail,
        }

    def _events(self, run_name: str):
        run_dir = self.discovery.resolve_run(run_name)
        return self.journal.load_events(run_dir / "events.jsonl")


def serve(*, runs_root: Path, port: int) -> None:
    """在固定 loopback 地址启动服务。"""

    if not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    service = ObserverService(runs_root)
    server = ThreadingHTTPServer(("127.0.0.1", port), _handler_for(service))
    print(f"Evolution Experiment Observer: http://127.0.0.1:{port}")
    print(f"Runs root: {service.discovery.runs_root}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nEvolution Experiment Observer stopped.")
    finally:
        server.server_close()


def _handler_for(service: ObserverService) -> type[BaseHTTPRequestHandler]:
    class ObserverRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            try:
                response = self._api_response(parsed.path, parsed.query)
                if response is not None:
                    self._send_json(response)
                    return
                self._send_static(parsed.path)
            except FileNotFoundError as exc:
                self._send_error_json(HTTPStatus.NOT_FOUND, str(exc))
            except ValueError as exc:
                self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            except Exception:
                LOGGER.exception("unexpected observer request failure")
                self._send_error_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    "internal server error",
                )

        def _api_response(self, path: str, query: str) -> dict[str, object] | None:
            if path == "/api/runs":
                return service.list_runs()
            segments = [unquote(item) for item in path.split("/") if item]
            if len(segments) == 5 and segments[:2] == ["api", "runs"]:
                run_name, endpoint, item_id = segments[2], segments[3], segments[4]
                if endpoint == "works":
                    return service.work_detail(run_name, item_id)
            if len(segments) != 4 or segments[:2] != ["api", "runs"]:
                return None
            run_name, endpoint = segments[2], segments[3]
            if endpoint == "overview":
                return service.overview(run_name)
            if endpoint == "works":
                params = _query_params(query)
                return service.works(
                    run_name,
                    params.get("category"),
                    params.get("status"),
                    params.get("node"),
                    _optional_positive_int(params.get("generation")),
                )
            if endpoint == "journal":
                params = _query_params(query)
                return service.journal_events(
                    run_name,
                    params.get("node"),
                    _optional_positive_int(params.get("generation")),
                )
            if endpoint == "refresh-state":
                return service.refresh_state(run_name)
            return None

        def _send_static(self, request_path: str) -> None:
            if request_path.startswith("/asset/"):
                root = ASSET_DIR
                relative = request_path.removeprefix("/asset/")
            else:
                root = STATIC_DIR
                relative = (
                    "index.html"
                    if request_path in {"", "/"}
                    else request_path.lstrip("/")
                )
            candidate = (root / relative).resolve()
            try:
                candidate.relative_to(root.resolve())
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

    return ObserverRequestHandler


def _query_params(query: str) -> dict[str, str]:
    parsed = parse_qs(query, keep_blank_values=True)
    return {key: values[0] for key, values in parsed.items() if values}


def _optional_positive_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        number = int(value)
    except ValueError as exc:
        raise ValueError(f"expected a positive integer, got {value!r}") from exc
    if number < 1:
        raise ValueError(f"expected a positive integer, got {value!r}")
    return number


def _work_counts(works) -> dict[str, int]:
    counts: dict[str, int] = {}
    for work in works:
        counts[work.status] = counts.get(work.status, 0) + 1
    return counts


def _completed_generation_count(works) -> int:
    generations = {
        work.generation
        for work in works
        if work.kind == "promote_candidate"
        and work.status == "completed"
        and work.generation is not None
    }
    return len(generations)
