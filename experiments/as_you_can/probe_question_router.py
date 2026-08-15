"""Probe a qwen3-8b-only structural router without running retrieval rollouts."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path

from search_harness.framework import ChatMessage, ModelInput
from search_harness.integrations.openai_compatible import (
    OpenAICompatibleConfig,
    OpenAICompatibleModel,
)


SYSTEM = """Classify only the reasoning structure of a factual question. Do not answer it.
Return exactly one JSON object: {"mode":"delegate"} or {"mode":"decompose"}.
- delegate: a direct one-relation lookup, or a comparison/shared-property question that must
  evaluate the same attribute for two explicitly given subjects.
- decompose: answering requires first resolving an intermediate entity/event/work/person and
  then retrieving a property or relation of that resolved bridge.
Examples: 'Which is older, A or B?' is delegate. 'Do A and B share a nationality?' is delegate.
'What city was the author of Book X born in?' is decompose. Never use world knowledge."""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rollouts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    config = OpenAICompatibleConfig.from_env(args.env_file, prefix="STUDENT")
    normalized = config.model_id.casefold().replace("-", "").replace(":", "")
    if "qwen3" not in normalized or "8b" not in normalized:
        raise RuntimeError(f"router probe requires qwen3-8b, got {config.model_id!r}")
    records = [
        json.loads(line)
        for line in args.rollouts.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    def classify(record: dict[str, object]) -> dict[str, object]:
        example = record["example"]
        response = OpenAICompatibleModel(config).generate(
            ModelInput.from_messages(
                [
                    ChatMessage(role="system", content=SYSTEM),
                    ChatMessage(role="user", content=str(example["question"])),
                ]
            )
        )
        mode = _parse_mode(response.raw_output)
        metadata = example.get("metadata") or {}
        expected = "delegate" if metadata.get("type") == "comparison" else "decompose"
        return {
            "example_id": example["example_id"],
            "question": example["question"],
            "expected_from_metadata": expected,
            "predicted": mode,
            "correct": mode == expected,
            "raw_output": response.raw_output,
            "usage": response.usage,
        }

    results: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(classify, record) for record in records]
        for future in as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda item: str(item["example_id"]))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in results),
        encoding="utf-8",
    )
    correct = sum(bool(item["correct"]) for item in results)
    predicted_delegate = sum(item["predicted"] == "delegate" for item in results)
    print(
        json.dumps(
            {
                "count": len(results),
                "accuracy": correct / len(results),
                "predicted_delegate": predicted_delegate,
            },
            indent=2,
        )
    )


def _parse_mode(raw: str) -> str:
    start = raw.find("{")
    if start < 0:
        raise ValueError("router output contains no JSON object")
    payload, _ = json.JSONDecoder().raw_decode(raw[start:])
    mode = payload.get("mode") if isinstance(payload, dict) else None
    if mode not in {"delegate", "decompose"}:
        raise ValueError(f"invalid router mode: {mode!r}")
    return mode


if __name__ == "__main__":
    main()
