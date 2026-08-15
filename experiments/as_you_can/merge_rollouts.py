"""Merge disjoint rollout shards and record one canonical merged provenance."""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("inputs", type=Path, nargs="+")
    args = parser.parse_args()

    records: dict[tuple[str, int], dict[str, object]] = {}
    canonical_provenance: dict[str, object] | None = None
    for path in args.inputs:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if canonical_provenance is None:
                canonical_provenance = deepcopy(record["provenance"])
            replicate = record.get("replicate", {})
            if not isinstance(replicate, dict):
                raise TypeError("replicate must be an object")
            key = (
                str(record["example"]["example_id"]),
                int(replicate.get("index", 0)),
            )
            if key in records:
                raise ValueError(f"duplicate rollout key: {key}")
            records[key] = record

    if canonical_provenance is None:
        raise ValueError("no rollout records found")
    canonical_provenance["ids_file"] = None
    canonical_provenance["merged_shards"] = [str(path.resolve()) for path in args.inputs]
    for record in records.values():
        record["provenance"] = deepcopy(canonical_provenance)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records.values():
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"merged {len(records)} rollouts into {args.output}")


if __name__ == "__main__":
    main()
