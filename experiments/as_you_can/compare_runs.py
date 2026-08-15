"""Compare two Teacher-judged runs, including paired and stratified metrics."""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import NormalDist


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    baseline = _load(args.baseline)
    candidate = _load(args.candidate)
    if set(baseline) != set(candidate):
        raise ValueError("run example sets differ")

    rows: list[dict[str, object]] = []
    for example_id in baseline:
        left = baseline[example_id]
        right = candidate[example_id]
        metadata = left.get("metadata") or {}
        rows.append(
            {
                "example_id": example_id,
                "level": metadata.get("level"),
                "type": metadata.get("type"),
                "baseline_score": left["score"],
                "candidate_score": right["score"],
                "baseline_em": left["exact_match"],
                "candidate_em": right["exact_match"],
            }
        )

    report = {
        "overall": _summarize(rows),
        "by_type": _stratify(rows, "type"),
        "by_level": _stratify(rows, "level"),
        "paired_semantic": _paired(rows, "baseline_score", "candidate_score"),
        "paired_exact_match": _paired(rows, "baseline_em", "candidate_em"),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


def _load(root: Path) -> dict[str, dict[str, object]]:
    rollouts = {
        record["example"]["example_id"]: record
        for record in _read_jsonl(root / "rollouts.jsonl")
    }
    judged = {
        record["example_id"]: record
        for record in _read_jsonl(root / "evaluation_teacher" / "per_rollout.jsonl")
    }
    loaded: dict[str, dict[str, object]] = {}
    for example_id, record in judged.items():
        static = record["static"]["metrics"]
        loaded[example_id] = {
            "score": record["score"],
            "exact_match": int(static.get("exact_match", 0)),
            "metadata": rollouts[example_id]["example"].get("metadata") or {},
        }
    return loaded


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _summarize(rows: list[dict[str, object]]) -> dict[str, object]:
    count = len(rows)
    return {
        "count": count,
        "baseline_semantic_accuracy": _mean(rows, "baseline_score"),
        "candidate_semantic_accuracy": _mean(rows, "candidate_score"),
        "baseline_exact_match": _mean(rows, "baseline_em"),
        "candidate_exact_match": _mean(rows, "candidate_em"),
    }


def _stratify(
    rows: list[dict[str, object]], field: str
) -> dict[str, dict[str, object]]:
    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        groups[str(row.get(field))].append(row)
    return {key: _summarize(value) for key, value in sorted(groups.items())}


def _mean(rows: list[dict[str, object]], field: str) -> float | None:
    values = [row[field] for row in rows if row[field] in {0, 1}]
    return sum(values) / len(values) if values else None


def _paired(
    rows: list[dict[str, object]], baseline_field: str, candidate_field: str
) -> dict[str, object]:
    gains = sum(
        row[baseline_field] == 0 and row[candidate_field] == 1 for row in rows
    )
    losses = sum(
        row[baseline_field] == 1 and row[candidate_field] == 0 for row in rows
    )
    discordant = gains + losses
    two_sided_p = None
    if discordant:
        tail = sum(
            math.comb(discordant, index)
            for index in range(0, min(gains, losses) + 1)
        ) / (2**discordant)
        two_sided_p = min(1.0, 2 * tail)
    return {
        "candidate_gains": gains,
        "candidate_losses": losses,
        "ties": len(rows) - discordant,
        "exact_mcnemar_two_sided_p": two_sided_p,
    }


if __name__ == "__main__":
    main()
