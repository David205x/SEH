"""Bounded concurrency helpers for independent ordered batch items."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from typing import TypeVar


_InputT = TypeVar("_InputT")
_OutputT = TypeVar("_OutputT")


def ordered_parallel_map(
    items: Iterable[_InputT],
    worker: Callable[[_InputT], _OutputT],
    *,
    max_workers: int,
    max_in_flight: int | None = None,
    on_complete: Callable[[int], None] | None = None,
) -> Iterator[_OutputT]:
    """Execute independent items concurrently and yield in source order.

    ``max_in_flight`` bounds submitted but not yet yielded work. Completion
    callbacks run in the consuming thread and may therefore update tqdm safely.
    """

    if max_workers < 1:
        raise ValueError("max_workers must be positive")
    window = max_in_flight or max_workers
    if window < max_workers:
        raise ValueError("max_in_flight must be at least max_workers")

    if max_workers == 1:
        for index, item in enumerate(items):
            result = worker(item)
            if on_complete is not None:
                on_complete(index)
            yield result
        return

    source = enumerate(items)
    pending: dict[Future[_OutputT], int] = {}
    completed: dict[int, Future[_OutputT]] = {}
    next_index = 0
    exhausted = False

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        while pending or not exhausted:
            while not exhausted and len(pending) + len(completed) < window:
                try:
                    index, item = next(source)
                except StopIteration:
                    exhausted = True
                    break
                pending[executor.submit(worker, item)] = index

            if pending:
                done, _ = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    index = pending.pop(future)
                    completed[index] = future
                    if on_complete is not None:
                        on_complete(index)

            while next_index in completed:
                future = completed.pop(next_index)
                try:
                    result = future.result()
                except Exception:
                    for outstanding in pending:
                        outstanding.cancel()
                    raise
                next_index += 1
                yield result
