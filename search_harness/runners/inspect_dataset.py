"""Inspect dataset loading without running a Student Agent."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from search_harness.datasets import (
    DatasetConfig,
    create_dataset_loader,
    dataset_loader_from_env,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--dataset-path", type=Path)
    parser.add_argument("--dataset-format")
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()

    if args.limit < 1:
        raise ValueError("--limit must be positive")

    if args.dataset_path is not None:
        if args.dataset_format is None:
            config = DatasetConfig(path=args.dataset_path)
        else:
            config = DatasetConfig(
                path=args.dataset_path,
                format_name=args.dataset_format,
            )
        loader = create_dataset_loader(config)
    else:
        loader = dataset_loader_from_env(env_file=args.env_file)

    examples = loader.load(limit=args.limit)
    print(f"loaded {len(examples)} example(s)")
    for example in examples:
        print(json.dumps(example.to_dict(), ensure_ascii=False))
