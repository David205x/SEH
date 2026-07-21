"""Retriever-backed search tool."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from search_harness.core import ToolResult
from search_harness.runtime import get_env_value, parse_float, parse_int, read_env_file
from search_harness.framework.tooling import (
    CallableTool,
    ToolArg,
    ToolDefinition,
    get_tool_definition,
    tool,
)


RETRIEVER_URL_ENV = "RETRIEVER_URL"
RETRIEVER_TIMEOUT_ENV = "RETRIEVER_TIMEOUT"
REQUEST_TIMEOUT_ENV = "REQUEST_TIMEOUT"
RETRIEVER_TOPK_ENV = "RETRIEVER_TOPK"


@dataclass(frozen=True)
class RetrieverSearchConfig:
    """Configuration for the retriever-backed search tool."""

    url: str
    timeout: float = 5.0
    default_topk: int = 5

    def __post_init__(self) -> None:
        if not self.url.strip():
            raise ValueError("retriever url must not be empty")
        if self.timeout <= 0:
            raise ValueError("retriever timeout must be positive")
        if self.default_topk < 1:
            raise ValueError("retriever default_topk must be positive")

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> "RetrieverSearchConfig":
        """Load retriever settings from process environment and an optional .env file."""

        values = read_env_file(env_file)
        url = get_env_value(values, RETRIEVER_URL_ENV)
        if url is None:
            raise ValueError(f"{RETRIEVER_URL_ENV} is required")

        timeout = parse_float(
            get_env_value(values, RETRIEVER_TIMEOUT_ENV)
            or get_env_value(values, REQUEST_TIMEOUT_ENV),
            default=5.0,
            name=RETRIEVER_TIMEOUT_ENV,
        )
        default_topk = parse_int(
            get_env_value(values, RETRIEVER_TOPK_ENV),
            default=5,
            name=RETRIEVER_TOPK_ENV,
        )
        return cls(url=url, timeout=timeout, default_topk=default_topk)


class RetrieverSearchTool:
    """Retriever-backed ``search`` tool exposed to the actor."""

    def __init__(self, config: RetrieverSearchConfig) -> None:
        self.config = config
        self.calls: list[dict[str, Any]] = []
        self.failures: list[str] = []
        definition = get_tool_definition(self.search).with_default(
            "topk", self.config.default_topk
        )
        self._tool = CallableTool(definition=definition, func=self.search)

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> "RetrieverSearchTool":
        return cls(RetrieverSearchConfig.from_env(env_file=env_file))

    def reset_trace(self) -> None:
        self.calls.clear()
        self.failures.clear()

    @property
    def name(self) -> str:
        return self._tool.name

    @property
    def definition(self) -> ToolDefinition:
        """Return the generated declaration shared with prompt construction."""

        return self._tool.definition

    def run(self, arguments: dict[str, object]) -> ToolResult:
        """Execute the typed ``search`` function through its shared definition."""

        return self._tool.run(arguments)

    @tool(name="search")
    def search(
        self,
        query: Annotated[
            str,
            ToolArg("A concise, standalone query used to retrieve evidence."),
        ],
        topk: Annotated[
            int,
            ToolArg("Maximum number of passages to return.", minimum=1),
        ] = 5,
    ) -> ToolResult:
        """Retrieve evidence passages from the configured corpus."""

        request_payload = {
            "queries": [query.strip()],
            "topk": topk,
            "return_scores": False,
        }
        try:
            groups = self._post_retrieve(request_payload)
        except Exception as exc:
            return self._error(f"{type(exc).__name__}: {exc}")

        trace = {"request": request_payload, "results": groups}
        self.calls.append(trace)
        rendered = [
            {"query": query, "passages": passages}
            for query, passages in zip(request_payload["queries"], groups, strict=False)
        ]
        return ToolResult(
            name=self.name,
            content=json.dumps(rendered, ensure_ascii=False),
            metadata=trace,
        )

    def _post_retrieve(self, request_payload: dict[str, Any]) -> list[list[dict[str, str]]]:
        data = json.dumps(request_payload, ensure_ascii=False).encode("utf-8")
        request = urllib_request.Request(
            self.config.url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib_request.urlopen(request, timeout=self.config.timeout) as response:
                body = response.read().decode("utf-8")
        except urllib_error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code}: {body[:500]}") from exc
        return normalize_response(json.loads(body))

    def _error(self, message: str) -> ToolResult:
        self.failures.append(message)
        return ToolResult(
            name=self.name,
            content=f"RETRIEVER_ERROR: {message}",
            metadata={"error": message},
        )


def normalize_response(payload: dict[str, Any]) -> list[list[dict[str, str]]]:
    """Normalize retriever API response into grouped passage dictionaries."""

    groups = payload.get("result")
    if not isinstance(groups, list):
        raise ValueError("retriever response has no list field 'result'")

    normalized: list[list[dict[str, str]]] = []
    for group in groups:
        if not isinstance(group, list):
            raise ValueError("each retriever result group must be a list")

        documents: list[dict[str, str]] = []
        for item in group:
            if not isinstance(item, dict):
                continue
            document = item.get("document", item)
            if not isinstance(document, dict):
                continue
            contents = document.get("contents", "")
            if not isinstance(contents, str) or not contents.strip():
                continue
            documents.append(
                {
                    "id": str(document.get("id", item.get("id", ""))),
                    "contents": contents.strip(),
                }
            )
        normalized.append(documents)
    return normalized


def build(config: dict[str, Any], context: Any) -> RetrieverSearchTool:
    """Create the retriever tool from manifest values and the runtime context."""

    allowed = {"url", "timeout", "default_topk"}
    unknown = set(config) - allowed
    if unknown:
        raise ValueError(f"retriever_search has unsupported config keys: {sorted(unknown)}")

    if "url" not in config:
        base = RetrieverSearchConfig.from_env(context.env_file)
        values: dict[str, Any] = {
            "url": base.url,
            "timeout": base.timeout,
            "default_topk": base.default_topk,
        }
    else:
        values = dict(config)
    values.update(config)
    return RetrieverSearchTool(
        RetrieverSearchConfig(
            url=values["url"],
            timeout=values.get("timeout", 5.0),
            default_topk=values.get("default_topk", 5),
        )
    )
