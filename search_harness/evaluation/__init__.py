"""Offline task evaluation and experiment reporting."""

from .hotpotqa import HotpotQAEvaluator
from .judge import TeacherBinaryJudge
from .report import evaluate_rollout_file, write_evaluation_report
from .types import EvaluationCase, StaticDecision, TaskEvaluator, TeacherJudgment

__all__ = [
    "EvaluationCase",
    "HotpotQAEvaluator",
    "StaticDecision",
    "TaskEvaluator",
    "TeacherBinaryJudge",
    "TeacherJudgment",
    "evaluate_rollout_file",
    "write_evaluation_report",
]
