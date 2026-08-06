from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from search_harness.framework.harness import (
    ComponentDeclaration,
    ComponentFactoryContext,
    ComponentLoader,
)


BASELINE_TEMPLATE_ROOT = (
    Path(__file__).parents[2] / "harness_templates" / "student" / "baseline"
)
RETRIEVER_ENTRYPOINT = "tools/retriever_search/component.py:build"


class RetrieverSearchToolTest(TestCase):
    def test_loads_config_from_env_file(self) -> None:
        """Verifies the loads config from env file contract."""
        with TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text(
                "\n".join(
                    [
                        "RETRIEVER_URL=http://example.test/retrieve",
                        "REQUEST_TIMEOUT=7.5",
                        "RETRIEVER_TOPK=9",
                    ]
                ),
                encoding="utf-8",
            )

            tool = _build_retriever({}, env_file=env_file)

        self.assertEqual(tool.config.url, "http://example.test/retrieve")
        self.assertEqual(tool.config.timeout, 7.5)
        self.assertEqual(tool.config.default_topk, 9)

    def test_retriever_timeout_overrides_global_request_timeout(self) -> None:
        """Verifies the retriever timeout overrides global request timeout contract."""
        with TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text(
                "\n".join(
                    [
                        "RETRIEVER_URL=http://example.test/retrieve",
                        "REQUEST_TIMEOUT=5",
                        "RETRIEVER_TIMEOUT=30",
                    ]
                ),
                encoding="utf-8",
            )

            tool = _build_retriever({}, env_file=env_file)

        self.assertEqual(tool.config.timeout, 30.0)

    def test_posts_retrieval_request_and_renders_grouped_passages(self) -> None:
        """Verifies the posts retrieval request and renders grouped passages contract."""
        server = _RetrieverTestServer()
        try:
            tool = _build_retriever(
                {"url": server.url, "timeout": 5, "default_topk": 3}
            )

            result = tool.run({"query": "hobbit author", "topk": 2})
        finally:
            server.close()

        self.assertEqual(
            server.requests,
            [{"queries": ["hobbit author"], "topk": 2, "return_scores": False}],
        )
        self.assertEqual(json.loads(result.content), server.rendered_results)
        self.assertEqual(result.metadata["request"], server.requests[0])

    def test_returns_tool_observation_for_invalid_arguments(self) -> None:
        """Verifies the returns tool observation for invalid arguments contract."""
        tool = _build_retriever(
            {"url": "http://example.test/retrieve", "timeout": 5, "default_topk": 3}
        )

        result = tool.run({"query": "hobbit", "topk": 0})

        self.assertEqual(
            result.content,
            "TOOL_INPUT_ERROR: tool 'search' argument 'topk' must be >= 1",
        )
        self.assertEqual(tool.failures, [])

    def test_definition_is_generated_from_the_search_method(self) -> None:
        """Verifies the definition is generated from the search method contract."""
        tool = _build_retriever(
            {"url": "http://example.test/retrieve", "timeout": 5, "default_topk": 7}
        )

        self.assertEqual(tool.definition.name, "search")
        self.assertEqual(
            tool.definition.description,
            "Retrieve evidence passages from the configured corpus.",
        )
        self.assertEqual(
            tool.definition.to_json_schema(),
            {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "A concise, standalone query used to retrieve evidence.",
                    },
                    "topk": {
                        "type": "integer",
                        "description": "Maximum number of passages to return.",
                        "minimum": 1,
                        "default": 7,
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        )


def _build_retriever(config: dict[str, object], env_file: Path | None = None):
    spec = ComponentDeclaration(
        instance_id="search",
        entrypoint=RETRIEVER_ENTRYPOINT,
        config=dict(config),
    )
    factory = ComponentLoader(BASELINE_TEMPLATE_ROOT).load_factory(spec)
    return factory(
        dict(config),
        ComponentFactoryContext(
            template_root=BASELINE_TEMPLATE_ROOT,
            env_file=env_file,
        ),
    )


class _RetrieverTestServer:
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []
        self.rendered_results = [
            {
                "query": "hobbit author",
                "passages": [
                    {
                        "id": "doc-1",
                        "contents": "The Hobbit is a fantasy novel by J. R. R. Tolkien.",
                    }
                ],
            }
        ]

        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                raw_body = self.rfile.read(length).decode("utf-8")
                payload = json.loads(raw_body)
                outer.requests.append(payload)

                response = {
                    "result": [
                        [
                            {
                                "document": {
                                    "id": "doc-1",
                                    "contents": "The Hobbit is a fantasy novel by J. R. R. Tolkien.",
                                }
                            }
                        ]
                    ]
                }
                body = json.dumps(response, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                return None

        self._server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._server.server_port}/retrieve"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
