"""Role-dispatching CLI for the offline Adapter Harness."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> None:
    """Dispatch remaining command-line arguments to one Adapter role."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=("critic", "compiler"), nargs="?")
    if not arguments:
        parser.print_help()
        return
    if arguments[0] in {"-h", "--help"}:
        parser.parse_args(arguments)
        return
    role = arguments.pop(0)
    if role not in {"critic", "compiler"}:
        parser.error(f"invalid role: {role}")
    if role == "critic":
        from .critic.run import main as run_role
    else:
        from .compiler.run import main as run_role
    run_role(arguments)


if __name__ == "__main__":
    main()
