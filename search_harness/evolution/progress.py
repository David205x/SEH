"""Evolution Runner 的结构化进度通知与 logging 输出。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from tqdm import tqdm


@dataclass(frozen=True)
class EvolutionProgressEvent:
    """一个不参与状态恢复、仅供人类观察的进度事件。"""

    event_type: str
    message: str
    iteration: int | None = None
    total_iterations: int | None = None
    stage: str | None = None
    elapsed_seconds: float | None = None
    details: dict[str, Any] = field(default_factory=dict)


class EvolutionProgressReporter(Protocol):
    """Evolution Runner 的可替换进度输出边界。"""

    def report(self, event: EvolutionProgressEvent) -> None: ...


class LoggingProgressReporter:
    """将结构化进度事件投影为简洁的 INFO 日志。"""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self.logger = logger or logging.getLogger("search_harness.evolution")

    def report(self, event: EvolutionProgressEvent) -> None:
        prefix = ""
        if event.iteration is not None and event.total_iterations is not None:
            prefix = f"[Iteration {event.iteration}/{event.total_iterations}] "
        suffixes: list[str] = []
        if event.elapsed_seconds is not None:
            suffixes.append(f"elapsed={event.elapsed_seconds:.1f}s")
        suffixes.extend(
            f"{key}={_render_value(value)}"
            for key, value in event.details.items()
            if value is not None
        )
        suffix = f" | {', '.join(suffixes)}" if suffixes else ""
        self.logger.info("%s%s%s", prefix, event.message, suffix)


class TqdmLoggingHandler(logging.Handler):
    """使用 ``tqdm.write`` 输出日志，避免破坏动态进度条。"""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            tqdm.write(self.format(record))
        except Exception:
            self.handleError(record)


def _render_value(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)
