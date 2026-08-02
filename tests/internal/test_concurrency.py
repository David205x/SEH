from __future__ import annotations

import time
from threading import Lock
from unittest import TestCase

from search_harness._internal import ordered_parallel_map


class OrderedParallelMapTest(TestCase):
    def test_yields_source_order_when_tasks_finish_out_of_order(self) -> None:
        """验证并发任务按输入顺序产出结果。"""

        completed: list[int] = []

        def worker(value: int) -> str:
            time.sleep((3 - value) * 0.01)
            return f"result-{value}"

        results = list(
            ordered_parallel_map(
                [0, 1, 2],
                worker,
                max_workers=3,
                on_complete=completed.append,
            )
        )

        self.assertEqual(results, ["result-0", "result-1", "result-2"])
        self.assertCountEqual(completed, [0, 1, 2])
        self.assertNotEqual(completed, [0, 1, 2])

    def test_bounds_simultaneous_workers(self) -> None:
        """验证执行中的任务数量不会超过 worker 上限。"""

        lock = Lock()
        active = 0
        peak = 0

        def worker(value: int) -> int:
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.01)
            with lock:
                active -= 1
            return value

        results = list(
            ordered_parallel_map(range(8), worker, max_workers=2, max_in_flight=3)
        )

        self.assertEqual(results, list(range(8)))
        self.assertLessEqual(peak, 2)

    def test_rejects_invalid_parallelism(self) -> None:
        """验证非法 worker 和提交窗口配置会立即失败。"""

        with self.assertRaisesRegex(ValueError, "max_workers"):
            list(ordered_parallel_map([], lambda item: item, max_workers=0))
        with self.assertRaisesRegex(ValueError, "max_in_flight"):
            list(
                ordered_parallel_map(
                    [], lambda item: item, max_workers=2, max_in_flight=1
                )
            )
