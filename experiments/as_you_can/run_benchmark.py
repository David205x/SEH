"""Run a deterministic local-qwen benchmark for one Harness Template."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from search_harness.datasets import DatasetConfig, create_dataset_loader
from search_harness.evaluation import HotpotQAEvaluator, evaluate_rollout_file, run_examples
from search_harness.evaluation.report import write_evaluation_report
from search_harness.integrations.openai_compatible import OpenAICompatibleConfig
from search_harness.runners.run_agent_once import run_agent_once


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"
DEFAULT_TRAIN_DATASET = Path(
    r"D:\_Project\Agent\corpus_filter\output\train\supported.jsonl"
)
DEFAULT_HELDOUT_DATASET = Path(
    r"D:\_Project\Agent\corpus_filter\output\dev\supported.jsonl"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument(
        "--dataset",
        choices=("train", "heldout"),
        default="train",
    )
    parser.add_argument("--dataset-path", type=Path)
    parser.add_argument("--limit", type=int, default=24)
    parser.add_argument("--selection-seed", type=int, default=20260814)
    parser.add_argument(
        "--ids-file",
        type=Path,
        help="Optional UTF-8 file with one example_id per line for targeted probes.",
    )
    parser.add_argument("--sampling-seed", type=int, default=42)
    parser.add_argument("--replicates", type=int, default=1)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-steps", type=int, default=20)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(__file__).resolve().parent / "artifacts" / "benchmarks",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.limit < 1:
        raise ValueError("limit must be positive")
    if args.dataset == "heldout" and "frozen" not in args.name.casefold():
        raise ValueError("heldout runs must include 'frozen' in --name")

    model_config = OpenAICompatibleConfig.from_env(args.env_file, prefix="STUDENT")
    normalized_model = model_config.model_id.casefold().replace("-", "").replace(":", "")
    if "qwen3" not in normalized_model or "8b" not in normalized_model:
        raise RuntimeError(
            "benchmark is restricted to the configured qwen3-8b Student model; "
            f"got {model_config.model_id!r}"
        )

    dataset_path = args.dataset_path or (
        DEFAULT_TRAIN_DATASET if args.dataset == "train" else DEFAULT_HELDOUT_DATASET
    )
    examples = list(create_dataset_loader(DatasetConfig(path=dataset_path)).iter_examples())
    if args.ids_file is None:
        selected = sorted(
            examples,
            key=lambda example: _selection_key(example.example_id, args.selection_seed),
        )[: args.limit]
    else:
        requested_ids = [
            line.strip()
            for line in args.ids_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        by_id = {example.example_id: example for example in examples}
        missing = [example_id for example_id in requested_ids if example_id not in by_id]
        if missing:
            raise ValueError(f"unknown example ids: {missing}")
        selected = [by_id[example_id] for example_id in requested_ids[: args.limit]]

    output_dir = args.output_root / args.name
    rollout_file = output_dir / "rollouts.jsonl"
    template_root = args.template.resolve()
    run_summary = run_examples(
        selected,
        lambda seed, question: run_agent_once(
            question,
            env_file=args.env_file,
            template_root=template_root,
            max_steps=args.max_steps,
            seed=seed,
        ),
        rollout_file,
        limit=len(selected),
        max_workers=args.workers,
        rollouts_per_example=args.replicates,
        base_seed=args.sampling_seed,
        harness_source={
            "source_type": "template_root",
            "template_root": str(template_root),
        },
        experiment_provenance={
            "dataset": args.dataset,
            "dataset_path": str(dataset_path.resolve()),
            "selection_seed": args.selection_seed,
            "ids_file": str(args.ids_file.resolve()) if args.ids_file else None,
            "sampling_seed": args.sampling_seed,
            "model": model_config.provenance(),
            "max_steps": args.max_steps,
        },
    )
    report = evaluate_rollout_file(
        rollout_file,
        HotpotQAEvaluator(),
        show_progress=True,
    )
    report_dir = output_dir / "evaluation"
    write_evaluation_report(report, report_dir)
    compact = _compact_summary(report, run_summary.runner_errors)
    (output_dir / "compact_summary.json").write_text(
        json.dumps(compact, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(compact, ensure_ascii=False, indent=2))


def _selection_key(example_id: str, seed: int) -> str:
    payload = f"{seed}:{example_id}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _compact_summary(report: dict[str, object], runner_errors: int) -> dict[str, object]:
    rollouts = report["rollouts"]
    if not isinstance(rollouts, list):
        raise TypeError("evaluation rollouts must be a list")
    exact_matches: list[int] = []
    token_f1: list[float] = []
    statuses: dict[str, int] = {}
    tool_calls: list[int] = []
    model_calls: list[int] = []
    total_tokens: list[int] = []
    for item in rollouts:
        static = item["static"]["metrics"]
        exact_matches.append(int(static.get("exact_match", 0)))
        token_f1.append(float(static.get("token_f1", 0.0)))
        status = item.get("run_status") or "runner_error"
        statuses[status] = statuses.get(status, 0) + 1
        execution = item["execution"]
        tool_calls.append(int(execution["tool_calls"]))
        model_calls.append(int(execution["model_calls"]))
        tokens = execution["tokens"].get("total_tokens")
        if isinstance(tokens, int):
            total_tokens.append(tokens)
    count = len(rollouts)
    return {
        "rollouts": count,
        "exact_match_rate": sum(exact_matches) / count if count else None,
        "mean_token_f1": sum(token_f1) / count if count else None,
        "completed_rate": statuses.get("completed", 0) / count if count else None,
        "status_counts": statuses,
        "runner_errors": runner_errors,
        "mean_tool_calls": sum(tool_calls) / count if count else None,
        "mean_model_calls": sum(model_calls) / count if count else None,
        "mean_total_tokens": (
            sum(total_tokens) / len(total_tokens) if total_tokens else None
        ),
    }


if __name__ == "__main__":
    main()
