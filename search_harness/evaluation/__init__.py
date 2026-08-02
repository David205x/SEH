"""Offline task evaluation and experiment reporting."""

from .hotpotqa import HotpotQAEvaluator
from .judge import TeacherBinaryJudge
from .report import evaluate_rollout_file, write_evaluation_report
from .rollouts import (
    DatasetRunSummary,
    HarnessRunSource,
    open_harness_source,
    run_examples,
)
from .types import EvaluationCase, StaticDecision, TaskEvaluator, TeacherJudgment

__all__ = [
    "EvaluationCase",
    "DatasetRunSummary",
    "HarnessRunSource",
    "HotpotQAEvaluator",
    "StaticDecision",
    "TaskEvaluator",
    "TeacherBinaryJudge",
    "TeacherJudgment",
    "evaluate_rollout_file",
    "open_harness_source",
    "run_examples",
    "write_evaluation_report",
]
