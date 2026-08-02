"""Generate a bounded, source-derived Hook capability packet for one mechanism."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from search_harness.evolution.research.mechanism.capabilities import (
    build_compiler_capability_packet,
)
from search_harness.evolution.research.roles.contracts import MechanismSpec


def build_capability_packet(mechanism: dict[str, Any]) -> dict[str, Any]:
    """Build the production packet from a serialized mechanism."""

    return build_compiler_capability_packet(
        MechanismSpec.model_validate(mechanism)
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request_file", type=Path)
    parser.add_argument("output_file", type=Path)
    parser.add_argument(
        "--augmented-request-file",
        type=Path,
        help="Optionally write a Compiler request carrying the packet as context.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    request = json.loads(args.request_file.read_text(encoding="utf-8"))
    mechanism = request["input"]["mechanism"]
    packet = build_capability_packet(mechanism)
    compact_packet = json.dumps(
        packet,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    args.output_file.parent.mkdir(parents=True, exist_ok=True)
    args.output_file.write_text(
        json.dumps(packet, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if args.augmented_request_file is not None:
        request["input"]["implementation_constraints"].append(
            "PROGRAM_CAPABILITY_PACKET=" + compact_packet
        )
        args.augmented_request_file.parent.mkdir(parents=True, exist_ok=True)
        args.augmented_request_file.write_text(
            json.dumps(request, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(
        f"packet written to {args.output_file} "
        f"({args.output_file.stat().st_size} bytes, "
        f"{len(compact_packet)} compact JSON characters)"
    )


if __name__ == "__main__":
    main()
