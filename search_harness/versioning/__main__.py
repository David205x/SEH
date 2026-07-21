"""初始化和管理 Harness Checkpoint Store。"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from .store import HarnessVersionStore


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """解析 Harness Checkpoint Store CLI 参数。"""

    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    initialize = subparsers.add_parser(
        "init",
        help="Initialize a checkpoint store from a Harness template.",
    )
    initialize.add_argument("--template-root", type=Path, required=True)
    initialize.add_argument("--checkpoint-store", type=Path, required=True)
    initialize.add_argument("--env-file", type=Path, default=Path(".env"))
    initialize.add_argument("--checkpoint-store-id")
    initialize.add_argument(
        "--summary",
        default="Initialize Harness from template",
        help="Summary recorded on the initial accepted version.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    """执行 Harness Checkpoint Store 命令。"""

    args = parse_args(argv)
    if args.command == "init":
        _initialize(args)


def _initialize(args: argparse.Namespace) -> None:
    template_root = args.template_root.resolve()
    checkpoint_store = args.checkpoint_store.resolve()
    env_file = args.env_file.resolve()

    if not template_root.is_dir():
        raise FileNotFoundError(f"Harness template does not exist: {template_root}")
    if not (template_root / "harness.json").is_file():
        raise FileNotFoundError(
            f"Harness template has no harness.json: {template_root}"
        )

    store = HarnessVersionStore(checkpoint_store)
    record = store.initialize(
        template_root,
        summary=args.summary,
        env_file=env_file,
        checkpoint_store_id=args.checkpoint_store_id,
    )
    print(f"checkpoint store initialized: {store.root}")
    print(f"checkpoint_store_id: {store.checkpoint_store_id}")
    print(f"accepted version: {record.version_id}")
    print(f"template digest: {record.digest}")


if __name__ == "__main__":
    main()
