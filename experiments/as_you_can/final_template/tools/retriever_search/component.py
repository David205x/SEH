"""Retriever-backed search Tool Component."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from search_harness._internal import get_env_value, parse_float, parse_int, read_env_file
from search_harness.framework.tools import (
    CallableTool,
    ToolArg,
    ToolDefinition,
    ToolResult,
    get_tool_definition,
    tool,
)


@dataclass(frozen=True)
class RetrieverConfig:
    """Runtime configuration for the corpus retriever."""

    url: str
    timeout: float = 5.0
    default_topk: int = 5

    def __post_init__(self) -> None:
        if not self.url.strip():
            raise ValueError("retriever url must not be empty")
        if self.timeout <= 0 or self.default_topk < 1:
            raise ValueError("invalid retriever limits")

    @classmethod
    def from_env(cls, env_file: Path | None) -> "RetrieverConfig":
        values = read_env_file(env_file)
        url = get_env_value(values, "RETRIEVER_URL")
        if url is None:
            raise ValueError("RETRIEVER_URL is required")
        return cls(
            url=url,
            timeout=parse_float(
                get_env_value(values, "RETRIEVER_TIMEOUT")
                or get_env_value(values, "REQUEST_TIMEOUT"),
                default=5.0,
                name="RETRIEVER_TIMEOUT",
            ),
            default_topk=parse_int(
                get_env_value(values, "RETRIEVER_TOPK"),
                default=5,
                name="RETRIEVER_TOPK",
            ),
        )


class RetrieverSearchTool:
    """Expose the configured corpus retriever as `search`."""

    def __init__(self, config: RetrieverConfig) -> None:
        self.config = config
        definition = get_tool_definition(self.search).with_default(
            "topk", config.default_topk
        )
        self._tool = CallableTool(definition=definition, func=self.search)

    @property
    def name(self) -> str:
        return self._tool.name

    @property
    def definition(self) -> ToolDefinition:
        return self._tool.definition

    def run(self, arguments: dict[str, object]) -> ToolResult:
        return self._tool.run(arguments)

    @tool(name="search")
    def search(
        self,
        query: Annotated[str, ToolArg("A concise, standalone evidence query.")],
        topk: Annotated[int, ToolArg("Passages to return.", minimum=1)] = 5,
    ) -> ToolResult:
        """Retrieve evidence passages from the configured corpus."""

        payload = {"queries": [query.strip()], "topk": topk, "return_scores": False}
        request = urllib_request.Request(
            self.config.url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib_request.urlopen(request, timeout=self.config.timeout) as response:
                groups = _normalize(json.loads(response.read().decode("utf-8")))
        except urllib_error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            return _error_result(self.name, f"HTTP {exc.code}: {body[:500]}")
        except Exception as exc:
            return _error_result(self.name, f"{type(exc).__name__}: {exc}")
        rendered = [
            {"query": query, "passages": passages}
            for query, passages in zip(payload["queries"], groups, strict=False)
        ]
        return ToolResult(
            name=self.name,
            content=json.dumps(rendered, ensure_ascii=False),
            metadata={"request": payload, "results": groups},
        )


def _normalize(payload: dict[str, Any]) -> list[list[dict[str, str]]]:
    groups = payload.get("result")
    if not isinstance(groups, list):
        raise ValueError("retriever response has no list field 'result'")
    normalized: list[list[dict[str, str]]] = []
    for group in groups:
        if not isinstance(group, list):
            raise ValueError("retriever result group must be a list")
        documents: list[dict[str, str]] = []
        for item in group:
            if not isinstance(item, dict):
                continue
            document = item.get("document", item)
            if not isinstance(document, dict):
                continue
            contents = document.get("contents", "")
            if isinstance(contents, str) and contents.strip():
                documents.append(
                    {
                        "id": str(document.get("id", item.get("id", ""))),
                        "contents": contents.strip(),
                    }
                )
        normalized.append(documents)
    return normalized


def _error_result(name: str, message: str) -> ToolResult:
    return ToolResult(
        name=name,
        content=f"RETRIEVER_ERROR: {message}",
        metadata={"error": message},
    )


def build(config: dict[str, Any], context: Any) -> RetrieverSearchTool:
    """Build the retriever from local manifest values and environment settings."""

    allowed = {"url", "timeout", "default_topk"}
    unknown = set(config) - allowed
    if unknown:
        raise ValueError(f"unsupported retriever config keys: {sorted(unknown)}")
    base = RetrieverConfig.from_env(context.env_file)
    return RetrieverSearchTool(
        RetrieverConfig(
            url=config.get("url", base.url),
            timeout=config.get("timeout", base.timeout),
            default_topk=config.get("default_topk", base.default_topk),
        )
    )
