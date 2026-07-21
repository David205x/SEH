"""Evaluate one rollout JSONL file and write a structured report directory."""

from __future__ import annotations

import argparse
from pathlib import Path

from search_harness.models import OpenAICompatibleTextModel
from search_harness.paths import COMPONENT_RUNS_ROOT, new_component_run_dir

from .hotpotqa import HotpotQAEvaluator
from .judge import TeacherBinaryJudge
from .report import evaluate_rollout_file, write_evaluation_report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_file", type=Path, help="UTF-8 rollout JSONL file.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Report directory; default: Actor run evaluation or a new evaluator run.",
    )
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument(
        "--teacher-judge",
        action="store_true",
        help="Use TEACHER_* for non-exact answer scoring.",
    )
    parser.add_argument(
        "--judge-workers",
        type=int,
        default=8,
        help="Maximum concurrent TEACHER_* judgments; default: 8.",
    )
    args = parser.parse_args()

    evaluator = HotpotQAEvaluator()
    judge_factory = None
    if args.teacher_judge:
        judge_factory = lambda: TeacherBinaryJudge(
            OpenAICompatibleTextModel.from_env(
                args.env_file, prefix="TEACHER"
            ),
            evaluator,
        )
    output_dir = args.output_dir or _default_output_dir(args.input_file)
    report = evaluate_rollout_file(
        args.input_file,
        evaluator,
        teacher_judge_factory=judge_factory,
        judge_workers=args.judge_workers,
    )
    write_evaluation_report(report, output_dir)
    print(f"evaluation report written to: {output_dir}")


def _default_output_dir(input_file: Path) -> Path:
    """将 Actor 评估就地聚合，其余输入放入独立 Evaluator run。"""

    actor_runs_root = (COMPONENT_RUNS_ROOT / "actor").resolve()
    try:
        input_file.resolve().relative_to(actor_runs_root)
    except ValueError:
        return new_component_run_dir("evaluator") / "evaluation"
    return input_file.parent / "evaluation"


if __name__ == "__main__":
    main()
