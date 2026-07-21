"""Evolution Runner 的稳定数据契约。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from search_harness.adapter.critic import CriticResult
from search_harness.adapter.intervention import InterventionCoordinatorResult


RunStatus = Literal[
    "completed",
    "no_direction",
    "no_supported_strategy",
    "needs_clarification",
    "failed",
]


@dataclass(frozen=True)
class EvaluationArtifact:
    """一次固定 Experience Set 评估的持久化引用。"""

    rollout_file: Path
    report_dir: Path
    metrics: dict[str, Any]


@dataclass(frozen=True)
class CriticArtifact:
    """一次 Critic 调用的结构化结果与完整日志。"""

    log_file: Path
    result: CriticResult


@dataclass(frozen=True)
class InterventionArtifact:
    """一次 Coordinator 验证的问题方向、结论与完整日志。"""

    log_file: Path
    result: InterventionCoordinatorResult


@dataclass(frozen=True)
class CandidateArtifact:
    """Compiler 创建并校验后的 Version Store 候选。"""

    iteration_id: str
    parent_version: str
    candidate_digest: str
    compiler_log: Path
    summary: str
    validation_passed: bool
    validation: dict[str, Any] | None = None
    clarification: str | None = None


@dataclass(frozen=True)
class EvolutionOutcome:
    """一次 Evolution Runner 执行的终态摘要。"""

    status: RunStatus
    completed_iterations: int
    accepted_iterations: int
    latest_version: str
    reason: str


class EvolutionBackend(Protocol):
    """Runner 调度的模型、rollout 与评估能力边界。"""

    def evaluate_accepted(
        self, *, version_id: str, experience_file: Path, output_dir: Path
    ) -> EvaluationArtifact: ...

    def analyze_failures(
        self,
        *,
        version_id: str,
        evaluation: EvaluationArtifact,
        failed_attempts: tuple[dict[str, Any], ...],
        output_file: Path,
    ) -> CriticArtifact: ...

    def compile_candidate(
        self,
        *,
        parent_version: str,
        intervention: InterventionArtifact,
        output_file: Path,
        experience_file: Path | None = None,
    ) -> CandidateArtifact: ...

    def validate_direction(
        self,
        *,
        version_id: str,
        evaluation: EvaluationArtifact,
        critic: CriticArtifact,
        output_dir: Path,
    ) -> InterventionArtifact: ...

    def continue_direction(
        self,
        *,
        version_id: str,
        evaluation: EvaluationArtifact,
        critic: CriticArtifact,
        previous_intervention: InterventionArtifact,
        output_dir: Path,
    ) -> InterventionArtifact: ...

    def refine_direction(
        self,
        *,
        version_id: str,
        evaluation: EvaluationArtifact,
        critic: CriticArtifact,
        previous_intervention: InterventionArtifact,
        compiler_feedback: str,
        output_dir: Path,
    ) -> InterventionArtifact: ...

    def evaluate_candidate(
        self,
        *,
        candidate: CandidateArtifact,
        experience_file: Path,
        output_dir: Path,
    ) -> EvaluationArtifact: ...

    def review_candidate(
        self,
        *,
        candidate: CandidateArtifact,
        candidate_evaluation: EvaluationArtifact,
        parent_evaluation: EvaluationArtifact,
        output_file: Path,
    ) -> CriticArtifact: ...
