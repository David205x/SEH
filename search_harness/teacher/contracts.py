"""Teacher 角色的稳定输入输出协议。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class TeacherPayload(BaseModel):
    """所有 Teacher 模型协议共享的严格基类。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class FailureDirection(TeacherPayload):
    """Failure Analyst 提交的单个有界问题方向。"""

    pattern: str = Field(min_length=1, max_length=400)
    applicability: str = Field(min_length=1, max_length=300)
    caveats: list[str] = Field(min_length=1, max_length=3)
    evidence_refs: list[str] = Field(min_length=2, max_length=4)

    @model_validator(mode="after")
    def validate_evidence_refs(self) -> "FailureDirection":
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("failure direction evidence_refs must be unique")
        invalid = [
            reference
            for reference in self.evidence_refs
            if reference.count("/") != 1
            or any(not part.strip() for part in reference.split("/"))
        ]
        if invalid:
            raise ValueError(
                "failure direction evidence_refs must use "
                "example_id/replicate_id format"
            )
        return self


class HypothesisEvaluationSpec(TeacherPayload):
    """假设创建时预注册的单次 trial 观察协议。"""

    primary_signal: str = Field(min_length=1, max_length=200)
    success_condition: str = Field(min_length=1, max_length=250)
    falsifier: str = Field(min_length=1, max_length=250)
    secondary_metrics: list[
        Annotated[str, Field(min_length=1, max_length=160)]
    ] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def validate_secondary_metrics(self) -> "HypothesisEvaluationSpec":
        if len(set(self.secondary_metrics)) != len(self.secondary_metrics):
            raise ValueError("secondary_metrics must be unique")
        return self


HookPhaseName = Literal[
    "post_prompt",
    "post_model",
    "post_parse",
    "pre_tool",
    "post_tool",
    "pre_final",
]


class InterventionPhaseDirective(TeacherPayload):
    """一次分支实验中某个 Hook phase 的有界干预指导。"""

    phase: HookPhaseName
    activation_condition: str = Field(min_length=1, max_length=350)
    instruction: str = Field(min_length=1, max_length=600)
    expected_effect: str = Field(min_length=1, max_length=300)
    max_activations: int = Field(default=1, ge=1, le=4)


class InterventionHypothesis(TeacherPayload):
    """Hypothesis Researcher 提交的可证伪干预假设。"""

    fork_phase: HookPhaseName
    phase_plan: list[InterventionPhaseDirective] = Field(
        min_length=1,
        max_length=4,
    )
    evaluation: HypothesisEvaluationSpec
    applicability: str = Field(min_length=1, max_length=300)

    @model_validator(mode="before")
    @classmethod
    def normalize_single_phase_v2(cls, value: object) -> object:
        """把已持久化的 v2 单阶段假设投影为一项 phase plan。"""

        if not isinstance(value, dict) or "phase_plan" in value:
            return value
        legacy_fields = {
            "trigger",
            "trigger_phase",
            "intervention",
            "predicted_actor_response",
        }
        if not legacy_fields <= set(value):
            return value
        normalized = dict(value)
        phase = normalized.pop("trigger_phase")
        normalized["fork_phase"] = phase
        normalized["phase_plan"] = [
            {
                "phase": phase,
                "activation_condition": normalized.pop("trigger"),
                "instruction": normalized.pop("intervention"),
                "expected_effect": normalized.pop(
                    "predicted_actor_response"
                ),
                "max_activations": 1,
            }
        ]
        return normalized

    @model_validator(mode="after")
    def validate_phase_plan(self) -> "InterventionHypothesis":
        """保持计划可直接映射为一个 phase 到指导的运行时表。"""

        phases = [directive.phase for directive in self.phase_plan]
        if len(phases) != len(set(phases)):
            raise ValueError("intervention phase_plan phases must be unique")
        if self.phase_plan[0].phase != self.fork_phase:
            raise ValueError(
                "intervention fork_phase must match the first phase_plan item"
            )
        return self

    @property
    def trigger_phase(self) -> HookPhaseName:
        """返回旧调用方使用的单阶段恢复 phase。"""

        return self.fork_phase


EvidenceDecision = Literal["continue", "revise", "reject", "ready_to_distill"]
PhaseEvidenceStatus = Literal[
    "supported",
    "unsupported",
    "not_reached",
    "contaminated",
    "inconclusive",
]


class PhaseEvidenceFinding(TeacherPayload):
    """Reviewer 对一条 phase 指令的独立证据判定。"""

    phase: HookPhaseName
    status: PhaseEvidenceStatus
    assessment: str = Field(min_length=1, max_length=500)


class EvidenceReview(TeacherPayload):
    """Evidence Reviewer 对一个冻结假设的局部判断。"""

    decision: EvidenceDecision
    phase_findings: list[PhaseEvidenceFinding] = Field(
        default_factory=list,
        max_length=4,
    )
    assessment: str = Field(min_length=1, max_length=1200)
    key_risk: str | None = Field(default=None, max_length=500)
    next_obligation: str | None = Field(default=None, max_length=400)

    @field_validator("key_risk", "next_obligation", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        """把常见模型缺失值表示归一为真正的空值。"""

        if value is None or value == 0:
            return None
        if isinstance(value, str) and value.strip().lower() in {
            "",
            "0",
            "null",
            "none",
            "n/a",
        }:
            return None
        return value

    @model_validator(mode="after")
    def validate_obligation(self) -> "EvidenceReview":
        phases = [finding.phase for finding in self.phase_findings]
        if len(phases) != len(set(phases)):
            raise ValueError("evidence review phase_findings must be unique")
        if self.decision == "continue" and not self.next_obligation:
            raise ValueError(
                "continue evidence review requires next_obligation"
            )
        if (
            self.decision in {"reject", "ready_to_distill"}
            and self.next_obligation is not None
        ):
            raise ValueError(
                f"{self.decision} evidence review must not include "
                "next_obligation"
            )
        return self


DecisionEvaluator = Literal["deterministic", "hook_model"]


class MechanismPhaseRule(TeacherPayload):
    """一个可由 Actor Harness 实现的 phase 局部决策与动作。"""

    phase: HookPhaseName
    trigger_condition: str = Field(min_length=1)
    decision_inputs: list[str] = Field(min_length=1)
    decision_evaluator: DecisionEvaluator
    action: str = Field(min_length=1)
    activation_budget: int = Field(default=1, ge=1)


class MechanismSpec(TeacherPayload):
    """不依赖 Teacher 的实现无关机制规格。"""

    goal: str = Field(min_length=1)
    phase_rules: list[MechanismPhaseRule] = Field(
        min_length=1,
        max_length=4,
    )
    behavioral_pseudocode: str = Field(min_length=1, max_length=3000)
    state_scope: str = Field(min_length=1)
    fallback: str = Field(min_length=1)
    expected_behavior: str = Field(min_length=1)
    evidence_refs: list[str] = Field(min_length=1)
    required_capabilities: list[str] = Field(default_factory=list)
    prohibited_behaviors: list[str] = Field(default_factory=list)
    observability: list[str] = Field(default_factory=list)
    known_limits: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_single_phase_v1(cls, value: object) -> object:
        """把已有单阶段机制无损归一为一项 phase rule。"""

        if not isinstance(value, dict) or "phase_rules" in value:
            return value
        legacy_fields = {
            "trigger_phase",
            "trigger_condition",
            "decision_inputs",
            "action",
        }
        if not legacy_fields <= set(value):
            return value
        normalized = dict(value)
        phase_rule = {
            "phase": normalized.pop("trigger_phase"),
            "trigger_condition": normalized.pop("trigger_condition"),
            "decision_inputs": normalized.pop("decision_inputs"),
            "action": normalized.pop("action"),
            "activation_budget": normalized.pop(
                "activation_budget",
                1,
            ),
        }
        if "decision_evaluator" in normalized:
            phase_rule["decision_evaluator"] = normalized.pop(
                "decision_evaluator"
            )
        normalized["phase_rules"] = [phase_rule]
        return normalized

    @model_validator(mode="after")
    def validate_phase_rules(self) -> "MechanismSpec":
        """一个 extension 对同一 phase 只维护一条明确控制规则。"""

        phases = [rule.phase for rule in self.phase_rules]
        if len(phases) != len(set(phases)):
            raise ValueError("mechanism phase_rules phases must be unique")
        return self

    @property
    def trigger_phase(self) -> HookPhaseName:
        """兼容读取单阶段机制的 phase。"""

        return self._single_rule().phase

    @property
    def trigger_condition(self) -> str:
        """兼容读取单阶段机制的触发条件。"""

        return self._single_rule().trigger_condition

    @property
    def decision_inputs(self) -> list[str]:
        """兼容读取单阶段机制的决策输入。"""

        return list(self._single_rule().decision_inputs)

    @property
    def decision_evaluator(self) -> DecisionEvaluator:
        """兼容读取单阶段机制的判断器。"""

        return self._single_rule().decision_evaluator

    @property
    def action(self) -> str:
        """兼容读取单阶段机制的动作。"""

        return self._single_rule().action

    @property
    def activation_budget(self) -> int:
        """兼容读取单阶段机制的激活预算。"""

        return self._single_rule().activation_budget

    def _single_rule(self) -> MechanismPhaseRule:
        if len(self.phase_rules) != 1:
            raise ValueError(
                "single-phase compatibility property used for a "
                "multi-phase mechanism"
            )
        return self.phase_rules[0]


DistillationDecision = Literal[
    "distilled",
    "needs_evidence",
    "not_distillable",
]


class MechanismDistillation(TeacherPayload):
    """Mechanism Distiller 的窄终态输出。"""

    decision: DistillationDecision
    mechanism_ref: str | None = None
    rationale: str = Field(min_length=1)
    next_obligation: str | None = None

    @model_validator(mode="after")
    def validate_decision_fields(self) -> "MechanismDistillation":
        if self.decision == "distilled":
            if not self.mechanism_ref:
                raise ValueError("distilled result requires mechanism_ref")
            if self.next_obligation is not None:
                raise ValueError(
                    "distilled result must not include next_obligation"
                )
        if self.decision == "needs_evidence" and not self.next_obligation:
            raise ValueError("needs_evidence result requires next_obligation")
        return self


InterventionActionName = Literal[
    "append_user_message",
    "append_system_message",
    "replace_system_instruction",
    "defer_final_answer",
    "no_op",
]

InterventionResultKind = Literal[
    "executed",
    "unsuitable_assignment",
    "unsupported_hypothesis",
]


class InterventionWorkerResult(TeacherPayload):
    """程序从一个完整 prefix 分支提取的执行事实。"""

    result_kind: InterventionResultKind
    activated_phases: list[HookPhaseName] = Field(default_factory=list)
    modified_phases: list[HookPhaseName] = Field(default_factory=list)
    unmet_phases: list[HookPhaseName] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_phase_outcome(self) -> "InterventionWorkerResult":
        for field_name, phases in (
            ("activated_phases", self.activated_phases),
            ("modified_phases", self.modified_phases),
            ("unmet_phases", self.unmet_phases),
        ):
            if len(phases) != len(set(phases)):
                raise ValueError(
                    f"{field_name} must not contain duplicates"
                )
        if set(self.activated_phases) & set(self.unmet_phases):
            raise ValueError(
                "activated_phases and unmet_phases must be disjoint"
            )
        if not set(self.modified_phases) <= set(self.activated_phases):
            raise ValueError(
                "modified_phases must be a subset of activated_phases"
            )
        if self.result_kind == "executed" and not self.modified_phases:
            raise ValueError(
                "executed intervention requires at least one modified phase"
            )
        if (
            self.result_kind != "executed"
            and self.modified_phases
        ):
            raise ValueError(
                "non-executed intervention cannot contain modified phases"
            )
        return self


CompilerDecision = Literal["submitted", "needs_revision"]


class CompilerResult(TeacherPayload):
    """Compiler 的候选提交或局部修订请求。"""

    decision: CompilerDecision
    candidate_ref: str | None = None
    implementation_summary: str = Field(min_length=1)
    unresolved_risk: str | None = None

    @model_validator(mode="after")
    def validate_candidate_reference(self) -> "CompilerResult":
        if self.decision == "submitted" and not self.candidate_ref:
            raise ValueError("submitted Compiler result requires candidate_ref")
        if self.decision == "needs_revision" and self.candidate_ref is not None:
            raise ValueError(
                "needs_revision Compiler result must not include candidate_ref"
            )
        return self


CandidateRecommendation = Literal["accept", "revise", "reject"]


class CandidateReview(TeacherPayload):
    """Candidate Reviewer 的局部 promotion 建议。"""

    recommendation: CandidateRecommendation
    observed_effect: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    next_obligation: str | None = None
    revision_target: Literal[
        "evidence",
        "mechanism",
        "implementation",
    ] | None = None

    @model_validator(mode="after")
    def validate_recommendation(self) -> "CandidateReview":
        if self.recommendation == "revise":
            if not self.next_obligation:
                raise ValueError("revise review requires next_obligation")
            if self.revision_target is None:
                raise ValueError("revise review requires revision_target")
        elif (
            self.next_obligation is not None
            or self.revision_target is not None
        ):
            raise ValueError(
                f"{self.recommendation} review must not include revision fields"
            )
        return self


class FailureAnalystInput(TeacherPayload):
    """Failure Analyst 的模型可见任务输入。"""

    analysis_focus: str | None = Field(
        default=None,
        min_length=1,
        max_length=300,
    )


class HypothesisResearcherInput(TeacherPayload):
    """Hypothesis Researcher 的模型可见任务输入。"""

    problem_direction: FailureDirection


class TrialReviewerInput(TeacherPayload):
    """Trial Reviewer 的单条 Worker 轨迹审阅任务。"""

    hypothesis: InterventionHypothesis
    trial_ref: str = Field(min_length=1)


class TrialReview(TeacherPayload):
    """Trial Reviewer 对一条完整 Intervention 轨迹的事实分析。"""

    trial_ref: str = Field(min_length=1)
    assessment: str = Field(min_length=1, max_length=4000)


class EvidenceReviewerInput(TeacherPayload):
    """Evidence Reviewer 的模型可见任务输入。"""

    hypothesis: InterventionHypothesis
    aggregate_observations: dict[str, Any]
    trial_reviews: list[TrialReview] = Field(min_length=1)
    prior_obligation: str | None = None


class MechanismDistillerInput(TeacherPayload):
    """Mechanism Distiller 的模型可见任务输入。"""

    hypothesis: InterventionHypothesis
    review: EvidenceReview
    evidence_refs: list[str] = Field(min_length=1)
    capability_constraints: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_ready_review(self) -> "MechanismDistillerInput":
        if self.review.decision != "ready_to_distill":
            raise ValueError(
                "Mechanism Distiller requires a ready_to_distill evidence review"
            )
        return self


class InterventionWorkerInput(TeacherPayload):
    """Intervention Worker 的单分支试验任务。"""

    hypothesis: InterventionHypothesis
    trial_objective: str = Field(min_length=1)
    example_id: str = Field(min_length=1)
    replicate_id: str = Field(min_length=1)
    prefix_id: int = Field(ge=1)
    prohibited_content: list[str] = Field(default_factory=list)


class CompilerInput(TeacherPayload):
    """Compiler 的已验证机制与本轮修订约束。"""

    mechanism: MechanismSpec
    implementation_constraints: list[str] = Field(default_factory=list)
    validation_feedback: list[str] = Field(default_factory=list)


class CandidateReviewerInput(TeacherPayload):
    """Candidate Reviewer 的机制目标与确定性门禁摘要。"""

    mechanism: MechanismSpec
    validation_summary: dict[str, Any]
    implementation_summary: str = Field(min_length=1)
    unresolved_risk: str | None = None
    historical_experience: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class TeacherRoleDefinition:
    """代码内固定的角色输入和输出协议。"""

    role_id: str
    version: int
    input_type: type[TeacherPayload]
    output_contract_id: str
    output_contract_version: int
    output_type: type[TeacherPayload]


_ROLE_DEFINITIONS = {
    "failure_analyst": TeacherRoleDefinition(
        role_id="failure_analyst",
        version=1,
        input_type=FailureAnalystInput,
        output_contract_id="failure_direction",
        output_contract_version=1,
        output_type=FailureDirection,
    ),
    "hypothesis_researcher": TeacherRoleDefinition(
        role_id="hypothesis_researcher",
        version=1,
        input_type=HypothesisResearcherInput,
        output_contract_id="intervention_hypothesis",
        output_contract_version=3,
        output_type=InterventionHypothesis,
    ),
    "evidence_reviewer": TeacherRoleDefinition(
        role_id="evidence_reviewer",
        version=1,
        input_type=EvidenceReviewerInput,
        output_contract_id="evidence_review",
        output_contract_version=2,
        output_type=EvidenceReview,
    ),
    "trial_reviewer": TeacherRoleDefinition(
        role_id="trial_reviewer",
        version=1,
        input_type=TrialReviewerInput,
        output_contract_id="trial_review",
        output_contract_version=1,
        output_type=TrialReview,
    ),
    "mechanism_distiller": TeacherRoleDefinition(
        role_id="mechanism_distiller",
        version=1,
        input_type=MechanismDistillerInput,
        output_contract_id="mechanism_distillation",
        output_contract_version=1,
        output_type=MechanismDistillation,
    ),
    "intervention_worker": TeacherRoleDefinition(
        role_id="intervention_worker",
        version=1,
        input_type=InterventionWorkerInput,
        output_contract_id="intervention_worker_result",
        output_contract_version=3,
        output_type=InterventionWorkerResult,
    ),
    "compiler": TeacherRoleDefinition(
        role_id="compiler",
        version=1,
        input_type=CompilerInput,
        output_contract_id="compiler_result",
        output_contract_version=1,
        output_type=CompilerResult,
    ),
    "candidate_reviewer": TeacherRoleDefinition(
        role_id="candidate_reviewer",
        version=1,
        input_type=CandidateReviewerInput,
        output_contract_id="candidate_review",
        output_contract_version=2,
        output_type=CandidateReview,
    ),
}


def get_teacher_role(role_id: str, version: int) -> TeacherRoleDefinition:
    """按稳定 ID 和版本解析角色定义。"""

    definition = _ROLE_DEFINITIONS.get(role_id)
    if definition is None or definition.version != version:
        raise ValueError(f"unknown Teacher role contract: {role_id}@{version}")
    return definition
