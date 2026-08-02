"""Initialize a Template Version Store from one Harness Template."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from .store import TemplateVersionStore


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m search_harness version-store",
        description=__doc__,
    )
    commands = parser.add_subparsers(dest="command", required=True)
    initialize = commands.add_parser(
        "init",
        help="Create the first Accepted Template Version.",
    )
    initialize.add_argument("--template-root", type=Path, required=True)
    initialize.add_argument("--version-store", type=Path, required=True)
    initialize.add_argument("--env-file", type=Path, default=Path(".env"))
    initialize.add_argument("--version-store-id")
    initialize.add_argument(
        "--summary",
        default="Initialize Harness Template",
        help="Summary recorded on the initial Accepted Template Version.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    store = TemplateVersionStore(args.version_store)
    record = store.initialize(
        args.template_root,
        summary=args.summary,
        env_file=args.env_file,
        version_store_id=args.version_store_id,
    )
    print(f"version store initialized: {store.root}")
    print(f"version_store_id: {store.version_store_id}")
    print(f"accepted version: {record.version_id}")
    print(f"template digest: {record.digest}")
