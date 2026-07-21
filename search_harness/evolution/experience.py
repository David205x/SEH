"""固定 Experience Set 的物化与读取。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path

from search_harness.datasets import DatasetExample


def materialize_experience_set(
    examples: Iterable[DatasetExample], path: Path, *, limit: int
) -> tuple[tuple[DatasetExample, ...], str]:
    """按源顺序固定前 ``limit`` 条样本，并返回内容摘要。"""

    if limit < 1:
        raise ValueError("experience set limit must be positive")
    selected: list[DatasetExample] = []
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for example in examples:
            if len(selected) >= limit:
                break
            selected.append(example)
            file.write(json.dumps(example.to_dict(), ensure_ascii=False) + "\n")
    if len(selected) < limit:
        raise ValueError(
            f"experience set contains only {len(selected)} examples; requested {limit}"
        )
    return tuple(selected), file_digest(path)


def load_experience_set(path: Path) -> tuple[DatasetExample, ...]:
    """从已物化的 UTF-8 JSONL 恢复规范样本。"""

    examples: list[DatasetExample] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        raw = json.loads(line)
        if not isinstance(raw, dict):
            raise TypeError(f"{path}:{line_number}: example must be an object")
        examples.append(
            DatasetExample(
                example_id=str(raw["example_id"]),
                question=str(raw["question"]),
                answer=raw.get("answer"),
                metadata=dict(raw.get("metadata", {})),
                source_path=raw.get("source_path"),
                line_number=raw.get("line_number"),
            )
        )
    if not examples:
        raise ValueError(f"experience set is empty: {path}")
    return tuple(examples)


def file_digest(path: Path) -> str:
    """计算 artifact 原始字节的 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()
