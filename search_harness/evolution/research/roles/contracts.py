"""Teacher 角色的稳定输入输出协议。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from search_harness.framework.harness import STAGE_KEYS_BY_PHASE

from ..mechanism.hook_api import query_hook_api
from ..mechanism.runtime_inputs import RuntimeInputId


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


class HypothesisEvidenceObligation(TeacherPayload):
    """Researcher 为当前假设补充的一项特有证据义务。"""

    obligation: str = Field(min_length=1, max_length=300)
    rationale: str = Field(min_length=1, max_length=300)


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
    activation_condition: str = Field(min_length=1, max_length=400)
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
    applicability: str = Field(min_length=1, max_length=600)
    special_evidence_obligations: list[HypothesisEvidenceObligation] = Field(
        default_factory=list,
        max_length=2,
    )

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
            "predicted_student_response",
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
                    "predicted_student_response"
                ),
                "max_activations": 1,
            }
        ]
        return normalized

    @model_validator(mode="after")
    def validate_phase_plan(self) -> "InterventionHypothesis":
        """保持干预阶段唯一并可映射为运行时指导表。"""

        phases = [directive.phase for directive in self.phase_plan]
        if len(phases) != len(set(phases)):
            raise ValueError("intervention phase_plan phases must be unique")
        obligations = [
            item.obligation for item in self.special_evidence_obligations
        ]
        if len(obligations) != len(set(obligations)):
            raise ValueError("special evidence obligations must be unique")
        return self

    @property
    def trigger_phase(self) -> HookPhaseName:
        """返回旧调用方使用的单阶段恢复 phase。"""

        return self.fork_phase


ResearchSchemeAction = Literal[
    "revise_current",
    "start_new",
    "reanalyse_failure",
]


class HypothesisResearcherResult(TeacherPayload):
    """Researcher lineage decision and its optional complete hypothesis."""

    scheme_action: ResearchSchemeAction
    hypothesis: InterventionHypothesis | None = None

    @model_validator(mode="after")
    def validate_action_payload(self) -> "HypothesisResearcherResult":
        has_hypothesis = self.hypothesis is not None
        if self.scheme_action == "reanalyse_failure" and has_hypothesis:
            raise ValueError(
                "reanalyse_failure must not submit an intervention hypothesis"
            )
        if self.scheme_action != "reanalyse_failure" and not has_hypothesis:
            raise ValueError(
                f"{self.scheme_action} requires a complete hypothesis"
            )
        return self


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
    assessment: str = Field(min_length=1, max_length=600)


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
DecisionLabel = Literal["positive", "negative", "uncertain"]


class MechanismDecisionEvidence(TeacherPayload):
    """支持判定边界的去案例化正例、负例和不确定类。"""

    positive: list[str] = Field(min_length=1, max_length=4)
    negative: list[str] = Field(min_length=1, max_length=4)
    uncertain: list[str] = Field(default_factory=list, max_length=4)


class MechanismDecisionContract(TeacherPayload):
    """一个 phase 中可被实现和独立探测的单一判定任务。"""

    predicate: str = Field(min_length=1)
    positive_rule: str = Field(min_length=1)
    negative_rule: str = Field(min_length=1)
    uncertain_rule: str = Field(min_length=1)
    output_labels: list[DecisionLabel] = Field(min_length=3, max_length=3)
    evidence_coverage: MechanismDecisionEvidence

    @model_validator(mode="after")
    def validate_output_labels(self) -> "MechanismDecisionContract":
        expected = ["positive", "negative", "uncertain"]
        if self.output_labels != expected:
            raise ValueError(
                "decision contract output_labels must be exactly "
                "positive, negative, uncertain in that order"
            )
        return self


class MechanismPhaseFallback(TeacherPayload):
    """一个 phase 对非触发、不确定和预算耗尽的明确行为。"""

    negative: str = Field(min_length=1)
    uncertain: str = Field(min_length=1)
    budget_exhausted: str = Field(min_length=1)


class MechanismPhaseRule(TeacherPayload):
    """一个可由 Student Harness 实现的 phase 局部决策与动作。"""

    phase: HookPhaseName
    guards: list[str] = Field(default_factory=list)
    decision_contract: MechanismDecisionContract
    decision_inputs: list[str] = Field(min_length=1)
    runtime_inputs: list[RuntimeInputId] = Field(min_length=1)
    decision_evaluator: DecisionEvaluator
    action: str = Field(min_length=1)
    fallback: MechanismPhaseFallback
    activation_budget: int = Field(default=1, ge=1)

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_rule(cls, value: object) -> object:
        """把历史自由文本触发和回退投影到结构化 phase 协议。"""

        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        trigger = normalized.pop("trigger_condition", None)
        if "decision_contract" not in normalized and isinstance(trigger, str):
            normalized["decision_contract"] = {
                "predicate": trigger,
                "positive_rule": trigger,
                "negative_rule": (
                    "The observable decision inputs establish that the "
                    "predicate is false."
                ),
                "uncertain_rule": (
                    "The observable decision inputs cannot establish either "
                    "the positive or negative rule."
                ),
                "output_labels": ["positive", "negative", "uncertain"],
                "evidence_coverage": {
                    "positive": [trigger],
                    "negative": [
                        "The observable inputs establish that the legacy "
                        "predicate is false."
                    ],
                    "uncertain": [
                        "Legacy artifact has no structured boundary evidence."
                    ],
                },
            }
        fallback = normalized.get("fallback")
        if isinstance(fallback, str):
            normalized["fallback"] = {
                "negative": fallback,
                "uncertain": fallback,
                "budget_exhausted": fallback,
            }
        return normalized

    @field_validator("runtime_inputs")
    @classmethod
    def validate_runtime_inputs(
        cls,
        value: list[RuntimeInputId],
    ) -> list[RuntimeInputId]:
        """拒绝重复 Topic，避免 Packet 重复加载相同文档。"""

        if len(value) != len(set(value)):
            raise ValueError("mechanism runtime_inputs must be unique")
        return value


MechanismEffectGoal = Literal[
    "task_outcome",
    "behavioral_intermediate",
]


class MechanismSpec(TeacherPayload):
    """不依赖 Teacher 的实现无关机制规格。"""

    goal: str = Field(min_length=1)
    effect_goal: MechanismEffectGoal = "task_outcome"
    phase_rules: list[MechanismPhaseRule] = Field(
        min_length=1,
        max_length=4,
    )
    behavioral_pseudocode: str = Field(min_length=1, max_length=3000)
    state_scope: str = Field(min_length=1)
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
        legacy_fallback = normalized.pop(
            "fallback",
            "Leave the current phase decision unchanged.",
        )
        phase_rule = {
            "phase": normalized.pop("trigger_phase"),
            "trigger_condition": normalized.pop("trigger_condition"),
            "decision_inputs": normalized.pop("decision_inputs"),
            "action": normalized.pop("action"),
            "fallback": legacy_fallback,
            "activation_budget": normalized.pop(
                "activation_budget",
                1,
            ),
        }
        if "runtime_inputs" in normalized:
            phase_rule["runtime_inputs"] = normalized.pop("runtime_inputs")
        if "decision_evaluator" in normalized:
            phase_rule["decision_evaluator"] = normalized.pop(
                "decision_evaluator"
            )
        normalized["phase_rules"] = [phase_rule]
        return normalized

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_phase_rules(cls, value: object) -> object:
        """仅在读取历史 artifact 时补齐旧 phase rule 的结构化边界。"""

        if not isinstance(value, dict) or "phase_rules" not in value:
            return value
        normalized = dict(value)
        shared_fallback = normalized.pop(
            "fallback",
            "Leave the current phase decision unchanged.",
        )
        rules = normalized.get("phase_rules")
        if not isinstance(rules, list):
            return normalized
        converted = []
        for raw_rule in rules:
            if not isinstance(raw_rule, dict):
                converted.append(raw_rule)
                continue
            rule = dict(raw_rule)
            trigger = rule.pop("trigger_condition", None)
            if "decision_contract" not in rule and isinstance(trigger, str):
                rule["decision_contract"] = {
                    "predicate": trigger,
                    "positive_rule": trigger,
                    "negative_rule": (
                        "The observable decision inputs establish that the "
                        "predicate is false."
                    ),
                    "uncertain_rule": (
                        "The observable decision inputs cannot establish "
                        "either the positive or negative rule."
                    ),
                    "output_labels": [
                        "positive",
                        "negative",
                        "uncertain",
                    ],
                    "evidence_coverage": {
                        "positive": [trigger],
                        "negative": [
                            "The observable inputs establish that the legacy "
                            "predicate is false."
                        ],
                        "uncertain": [
                            "Legacy artifact has no structured boundary evidence."
                        ],
                    },
                }
            if "fallback" not in rule:
                rule["fallback"] = {
                    "negative": str(shared_fallback),
                    "uncertain": str(shared_fallback),
                    "budget_exhausted": str(shared_fallback),
                }
            elif isinstance(rule["fallback"], str):
                fallback = rule["fallback"]
                rule["fallback"] = {
                    "negative": fallback,
                    "uncertain": fallback,
                    "budget_exhausted": fallback,
                }
            converted.append(rule)
        normalized["phase_rules"] = converted
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

        return self._single_rule().decision_contract.predicate

    @property
    def decision_inputs(self) -> list[str]:
        """兼容读取单阶段机制的决策输入。"""

        return list(self._single_rule().decision_inputs)

    @property
    def runtime_inputs(self) -> list[RuntimeInputId]:
        """兼容读取单阶段机制的受控运行时输入主题。"""

        return list(self._single_rule().runtime_inputs)

    @property
    def decision_evaluator(self) -> DecisionEvaluator:
        """兼容读取单阶段机制的判断器。"""

        return self._single_rule().decision_evaluator

    @property
    def action(self) -> str:
        """兼容读取单阶段机制的动作。"""

        return self._single_rule().action

    @property
    def fallback(self) -> str:
        """兼容读取单阶段机制的统一不确定回退描述。"""

        return self._single_rule().fallback.uncertain

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


ShadowDistillationOutcome = Literal[
    "distilled",
    "needs_evidence",
    "not_distillable",
]
ShadowEffectKind = Literal["task_outcome", "behavioral_intermediate"]
ShadowDecisionEvaluator = Literal["deterministic", "hook_model"]
ShadowStateValueType = Literal["bool", "int", "str", "json_object"]


class ShadowEffectSpec(TeacherPayload):
    """Shadow Mechanism 的效果目标与可观察成功条件。"""

    kind: ShadowEffectKind
    success: str = Field(min_length=1, max_length=1200)


class ShadowTaskInput(TeacherPayload):
    """一个 Phase Task 的语义名称与受控 runtime sources。"""

    name: str = Field(min_length=1, max_length=120)
    sources: list[Annotated[str, Field(min_length=1, max_length=120)]] = Field(
        min_length=1,
        max_length=8,
    )

    @model_validator(mode="after")
    def validate_sources(self) -> "ShadowTaskInput":
        if len(self.sources) != len(set(self.sources)):
            raise ValueError("shadow task input sources must be unique")
        if any(
            not source.startswith(("core.", "stage.", "state."))
            for source in self.sources
        ):
            raise ValueError(
                "shadow task input sources must use core.*, stage.*, or state.*"
            )
        return self


class ShadowDecisionTask(TeacherPayload):
    """返回三值控制标签的 phase-local task。"""

    kind: Literal["decision"]
    evaluator: ShadowDecisionEvaluator
    inputs: list[ShadowTaskInput] = Field(min_length=1, max_length=8)
    positive: str = Field(min_length=1, max_length=1200)
    negative: str = Field(min_length=1, max_length=1200)
    uncertain: str = Field(min_length=1, max_length=1200)

    @model_validator(mode="after")
    def validate_task(self) -> "ShadowDecisionTask":
        names = [item.name for item in self.inputs]
        if len(names) != len(set(names)):
            raise ValueError("shadow decision input names must be unique")
        boundaries = {
            self.positive.casefold(),
            self.negative.casefold(),
            self.uncertain.casefold(),
        }
        if len(boundaries) != 3:
            raise ValueError("shadow decision boundaries must be distinct")
        return self


class ShadowGenerationTask(TeacherPayload):
    """由 Hook model 生成供 phase action 使用的自然语言文本。"""

    kind: Literal["generation"]
    evaluator: Literal["hook_model"]
    inputs: list[ShadowTaskInput] = Field(min_length=1, max_length=8)
    output_name: str = Field(min_length=1, max_length=80)
    requirement: str = Field(min_length=1, max_length=1600)

    @model_validator(mode="after")
    def validate_task(self) -> "ShadowGenerationTask":
        names = [item.name for item in self.inputs]
        if len(names) != len(set(names)):
            raise ValueError("shadow generation input names must be unique")
        if not self.output_name.isidentifier():
            raise ValueError(
                "shadow generation output_name must be an identifier"
            )
        return self


ShadowPhaseTask = Annotated[
    ShadowDecisionTask | ShadowGenerationTask,
    Field(discriminator="kind"),
]


class ShadowFallbackPolicy(TeacherPayload):
    """非成功 task 结果与 phase budget 耗尽时的行为。"""

    default: str = Field(min_length=1, max_length=800)
    uncertain: str | None = Field(default=None, min_length=1, max_length=800)
    exhausted: str | None = Field(default=None, min_length=1, max_length=800)

    @model_validator(mode="after")
    def validate_actions(self) -> "ShadowFallbackPolicy":
        actions = {
            "default": self.default,
            "uncertain": self.uncertain,
            "exhausted": self.exhausted,
        }
        for name, action in actions.items():
            if action is None:
                continue
            if (
                action != "continue_without_change"
                and not re.search(
                    r"\bstate\.[A-Za-z_][A-Za-z0-9_]*\b",
                    action,
                )
            ):
                raise ValueError(
                    f"shadow fallback {name} must be "
                    "continue_without_change or update declared state"
                )
        for name in ("uncertain", "exhausted"):
            action = actions[name]
            if action is not None and action == self.default:
                raise ValueError(
                    f"shadow fallback {name} must be null when it "
                    "inherits default"
                )
        return self


class ShadowStateSpec(TeacherPayload):
    """一个 rollout-local 的有类型 Mechanism state。"""

    name: str = Field(min_length=1, max_length=80)
    value_type: ShadowStateValueType
    initial: Any

    @model_validator(mode="after")
    def validate_initial(self) -> "ShadowStateSpec":
        if not self.name.isidentifier():
            raise ValueError("shadow state name must be an identifier")
        valid = {
            "bool": isinstance(self.initial, bool),
            "int": (
                isinstance(self.initial, int)
                and not isinstance(self.initial, bool)
            ),
            "str": isinstance(self.initial, str),
            "json_object": isinstance(self.initial, dict),
        }[self.value_type]
        if not valid:
            raise ValueError(
                "shadow state initial value does not match value_type"
            )
        return self


class ShadowPhaseSpec(TeacherPayload):
    """一个最小 phase-local task、成功动作与 fallback。"""

    phase: HookPhaseName
    guards: list[Annotated[str, Field(min_length=1, max_length=500)]] = Field(
        default_factory=list,
        max_length=8,
    )
    task: ShadowPhaseTask
    on_success: str = Field(min_length=1, max_length=2000)
    fallback: ShadowFallbackPolicy
    activation_limit: int = Field(ge=1, le=20)

    @model_validator(mode="after")
    def validate_phase(self) -> "ShadowPhaseSpec":
        if len(self.guards) != len(set(self.guards)):
            raise ValueError("shadow phase guards must be unique")
        if (
            isinstance(self.task, ShadowGenerationTask)
            and self.task.output_name not in self.on_success
        ):
            raise ValueError(
                "shadow generation on_success must reference output_name"
            )
        return self


def _validate_shadow_source_at_phase(source: str, phase: str) -> None:
    contract = query_hook_api(source)
    if contract.get("kind") != "state_key":
        raise ValueError(
            f"shadow task input source must be a state key: {source}"
        )
    if source.startswith("stage.") and source not in (
        STAGE_KEYS_BY_PHASE.get(phase, frozenset())
    ):
        raise ValueError(f"shadow source {source} is unavailable at {phase}")


class ShadowMechanismSpec(TeacherPayload):
    """新协议下最小、低冗余且实现无关的 Mechanism。"""

    effect: ShadowEffectSpec
    phases: list[ShadowPhaseSpec] = Field(min_length=1, max_length=4)
    state: list[ShadowStateSpec] = Field(default_factory=list, max_length=12)
    constraints: list[
        Annotated[str, Field(min_length=1, max_length=800)]
    ] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def validate_mechanism(self) -> "ShadowMechanismSpec":
        phase_order = {
            name: index
            for index, name in enumerate(
                (
                    "post_prompt",
                    "post_model",
                    "post_parse",
                    "pre_tool",
                    "post_tool",
                    "pre_final",
                )
            )
        }
        phases = [item.phase for item in self.phases]
        if len(phases) != len(set(phases)):
            raise ValueError("shadow mechanism phases must be unique")
        if phases != sorted(phases, key=phase_order.__getitem__):
            raise ValueError(
                "shadow mechanism phases must follow Harness lifecycle order"
            )
        state_names = [item.name for item in self.state]
        if len(state_names) != len(set(state_names)):
            raise ValueError("shadow mechanism state names must be unique")
        if len(self.constraints) != len(set(self.constraints)):
            raise ValueError("shadow mechanism constraints must be unique")
        declared_state = set(state_names)
        referenced_state: set[str] = set()
        for phase in self.phases:
            for item in phase.task.inputs:
                for source in item.sources:
                    if source.startswith("state."):
                        state_name = source.removeprefix("state.")
                        referenced_state.add(state_name)
                        if state_name not in declared_state:
                            raise ValueError(
                                "shadow task input references undeclared state: "
                                f"{source}"
                            )
                        continue
                    _validate_shadow_source_at_phase(source, phase.phase)
            text_fields = [
                *phase.guards,
                phase.on_success,
                phase.fallback.default,
                phase.fallback.uncertain or "",
                phase.fallback.exhausted or "",
            ]
            for text in text_fields:
                for source in re.findall(
                    r"\b(?:core|stage)\.[A-Za-z_][A-Za-z0-9_]*\b",
                    text,
                ):
                    _validate_shadow_source_at_phase(source, phase.phase)
                referenced_state.update(
                    re.findall(r"\bstate\.([A-Za-z_][A-Za-z0-9_]*)\b", text)
                )
        for constraint in self.constraints:
            referenced_state.update(
                re.findall(
                    r"\bstate\.([A-Za-z_][A-Za-z0-9_]*)\b",
                    constraint,
                )
            )
        unknown_state = referenced_state - declared_state
        if unknown_state:
            raise ValueError(
                "shadow mechanism text references undeclared state: "
                f"{sorted(unknown_state)}"
            )
        unused_state = declared_state - referenced_state
        if unused_state:
            raise ValueError(
                "shadow mechanism declares unused state: "
                f"{sorted(unused_state)}"
            )
        return self


class ShadowDistillationResult(TeacherPayload):
    """Shadow Distiller 的路由结果及可选内嵌 Mechanism。"""

    outcome: ShadowDistillationOutcome
    mechanism: ShadowMechanismSpec | None = None
    obligation: str | None = Field(default=None, min_length=1, max_length=1000)

    @field_validator("obligation")
    @classmethod
    def reject_null_sentinel(cls, value: str | None) -> str | None:
        if value is not None and value.casefold() in {"null", "none", "n/a"}:
            raise ValueError("shadow obligation must use JSON null")
        return value

    @model_validator(mode="after")
    def validate_outcome(self) -> "ShadowDistillationResult":
        if self.outcome == "distilled":
            if self.mechanism is None:
                raise ValueError("distilled shadow result requires mechanism")
            if self.obligation is not None:
                raise ValueError(
                    "distilled shadow result must not include obligation"
                )
            return self
        if self.mechanism is not None:
            raise ValueError(
                f"{self.outcome} shadow result must not include mechanism"
            )
        if self.obligation is None:
            raise ValueError(
                f"{self.outcome} shadow result requires obligation"
            )
        return self


class ShadowDistillationSubmission(TeacherPayload):
    """Model-facing shallow commit for one program-assembled Mechanism."""

    outcome: ShadowDistillationOutcome
    mechanism_ref: str | None = Field(
        default=None,
        min_length=1,
        max_length=120,
    )
    obligation: str | None = Field(default=None, min_length=1, max_length=1000)

    @field_validator("obligation")
    @classmethod
    def reject_null_sentinel(cls, value: str | None) -> str | None:
        if value is not None and value.casefold() in {"null", "none", "n/a"}:
            raise ValueError("shadow obligation must use JSON null")
        return value

    @model_validator(mode="after")
    def validate_outcome(self) -> "ShadowDistillationSubmission":
        if self.outcome == "distilled":
            if self.mechanism_ref is None:
                raise ValueError(
                    "distilled shadow submission requires mechanism_ref"
                )
            if self.obligation is not None:
                raise ValueError(
                    "distilled shadow submission must not include obligation"
                )
            return self
        if self.mechanism_ref is not None:
            raise ValueError(
                f"{self.outcome} shadow submission must not include "
                "mechanism_ref"
            )
        if self.obligation is None:
            raise ValueError(
                f"{self.outcome} shadow submission requires obligation"
            )
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
        if self.result_kind == "executed" and not self.activated_phases:
            raise ValueError(
                "executed trial requires at least one reached phase"
            )
        if (
            self.result_kind != "executed"
            and self.modified_phases
        ):
            raise ValueError(
                "non-executed intervention cannot contain modified phases"
            )
        return self


CompilerDecision = Literal[
    "submitted",
    "needs_mechanism_revision",
    "needs_evidence",
    "implementation_blocked",
]


class CompilerResult(TeacherPayload):
    """Compiler 的候选提交或局部修订请求。"""

    decision: CompilerDecision
    candidate_ref: str | None = None
    implementation_summary: str = Field(min_length=1)
    unresolved_risk: str | None = None
    next_obligation: str | None = Field(default=None, max_length=500)

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_decision(cls, value: object) -> object:
        """把历史 needs_revision 结果映射为明确的机制修订。"""

        if not isinstance(value, dict) or value.get("decision") != "needs_revision":
            return value
        normalized = dict(value)
        normalized["decision"] = "needs_mechanism_revision"
        normalized.setdefault(
            "next_obligation",
            normalized.get("implementation_summary"),
        )
        return normalized

    @model_validator(mode="after")
    def validate_candidate_reference(self) -> "CompilerResult":
        if self.decision == "submitted":
            if not self.candidate_ref:
                raise ValueError("submitted Compiler result requires candidate_ref")
            if self.next_obligation is not None:
                raise ValueError(
                    "submitted Compiler result must not include next_obligation"
                )
        else:
            if self.candidate_ref is not None:
                raise ValueError(
                    f"{self.decision} Compiler result must not include "
                    "candidate_ref"
                )
            if not self.next_obligation:
                raise ValueError(
                    f"{self.decision} Compiler result requires next_obligation"
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


PredicateObservationLabel = Literal["positive", "negative", "uncertain"]
PhaseExecutionStatus = Literal[
    "intervention_applied",
    "correct_non_intervention",
    "not_reached",
    "invalid_execution",
    "inconclusive",
]


class TrialPredicateObservation(TeacherPayload):
    """一条 Trial 对单个 phase activation predicate 的结构化观察。"""

    phase: HookPhaseName
    predicate_label: PredicateObservationLabel
    decisive_observation: str = Field(min_length=1, max_length=500)
    phase_execution: PhaseExecutionStatus
    observed_effect: str | None = Field(default=None, max_length=500)
    outcome_evidence: str | None = Field(default=None, max_length=500)

    @field_validator("observed_effect", "outcome_evidence", mode="before")
    @classmethod
    def normalize_optional_evidence(cls, value: object) -> object:
        """把模型常用的空文本表示归一为空值。"""

        if value is None:
            return None
        if isinstance(value, str) and value.strip().lower() in {
            "",
            "null",
            "none",
            "n/a",
        }:
            return None
        return value


class TrialReview(TeacherPayload):
    """Trial Reviewer 对一条完整 Intervention 轨迹的事实分析。"""

    trial_ref: str = Field(min_length=1)
    predicate_observations: list[TrialPredicateObservation] = Field(
        default_factory=list,
        max_length=4,
    )
    assessment: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def validate_predicate_observations(self) -> "TrialReview":
        phases = [item.phase for item in self.predicate_observations]
        if len(phases) != len(set(phases)):
            raise ValueError("trial predicate observation phases must be unique")
        return self


class PhaseEvidenceCoverage(TeacherPayload):
    """程序聚合的单 phase 正例、负例和不确定观察覆盖。"""

    phase: HookPhaseName
    positive_count: int = Field(ge=0)
    negative_count: int = Field(ge=0)
    uncertain_count: int = Field(ge=0)
    positive_distinct_examples: int = Field(ge=0)
    negative_distinct_examples: int = Field(ge=0)
    intervention_applied_count: int = Field(ge=0)
    correct_non_intervention_count: int = Field(ge=0)


class EvidenceCoverageSummary(TeacherPayload):
    """Evidence Reviewer 可见的程序维护证据覆盖摘要。"""

    required_distinct_examples: int = Field(ge=1)
    required_positive_per_phase: int = Field(ge=1)
    required_negative_per_phase: int = Field(ge=1)
    observed_distinct_examples: int = Field(ge=0)
    phase_coverage: list[PhaseEvidenceCoverage] = Field(max_length=4)
    unmet_requirements: list[str]
    special_obligations: list[HypothesisEvidenceObligation] = Field(
        default_factory=list,
        max_length=2,
    )
    default_requirements_met: bool


class EvidenceReviewBudget(TeacherPayload):
    """Teacher Role 可见的当前假设试验预算状态。"""

    max_trials_per_hypothesis: int = Field(ge=1)
    trials_used: int = Field(ge=0)
    trials_remaining: int = Field(ge=0)
    max_trial_assignments: int = Field(ge=1)
    assignments_used: int = Field(ge=0)
    assignments_remaining: int = Field(ge=0)
    conclusion_required: bool

    @model_validator(mode="after")
    def validate_budget_state(self) -> "EvidenceReviewBudget":
        if self.trials_used > self.max_trials_per_hypothesis:
            raise ValueError("trials_used exceeds the configured maximum")
        if self.assignments_used > self.max_trial_assignments:
            raise ValueError("assignments_used exceeds the configured maximum")
        if self.trials_remaining != (
            self.max_trials_per_hypothesis - self.trials_used
        ):
            raise ValueError("trials_remaining is inconsistent")
        if self.assignments_remaining != (
            self.max_trial_assignments - self.assignments_used
        ):
            raise ValueError("assignments_remaining is inconsistent")
        expected_conclusion = (
            self.trials_remaining == 0
            or self.assignments_remaining == 0
        )
        if self.conclusion_required != expected_conclusion:
            raise ValueError("conclusion_required is inconsistent")
        return self


class EvidenceReviewerInput(TeacherPayload):
    """Evidence Reviewer 的模型可见任务输入。"""

    hypothesis: InterventionHypothesis
    aggregate_observations: dict[str, Any]
    trial_reviews: list[TrialReview] = Field(min_length=1)
    coverage_summary: EvidenceCoverageSummary | None = None
    budget: EvidenceReviewBudget
    trial_selection_capabilities: dict[str, list[str]] = Field(
        default_factory=dict
    )
    prior_obligation: str | None = None


class MechanismDistillerInput(TeacherPayload):
    """Mechanism Distiller 的模型可见任务输入。"""

    hypothesis: InterventionHypothesis
    review: EvidenceReview
    trial_reviews: list[TrialReview] = Field(min_length=1)
    coverage_summary: EvidenceCoverageSummary
    evidence_refs: list[str] = Field(min_length=1)
    budget: EvidenceReviewBudget
    capability_constraints: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_ready_review(self) -> "MechanismDistillerInput":
        if self.review.decision != "ready_to_distill":
            raise ValueError(
                "Mechanism Distiller requires a ready_to_distill evidence review"
            )
        return self


ShadowPromptResearchOutcome = Literal["ready", "not_feasible"]
HookPromptThinkingMode = Literal["enabled", "disabled"]
HookPromptResponseAdapter = Literal[
    "tri_label",
    "raw_text",
    "structured_edit",
]


class ShadowPromptResearcherInput(TeacherPayload):
    """One frozen stateless Hook-model phase and its reviewed Trials."""

    mechanism: ShadowMechanismSpec
    phase: HookPhaseName
    trial_reviews: list[TrialReview] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_scope(self) -> "ShadowPromptResearcherInput":
        if self.mechanism.state:
            raise ValueError(
                "Shadow Prompt Researcher currently supports stateless "
                "mechanisms only"
            )
        if len(self.mechanism.phases) != 1:
            raise ValueError(
                "Shadow Prompt Researcher currently supports one phase only"
            )
        selected = self.mechanism.phases[0]
        if selected.phase != self.phase:
            raise ValueError(
                "Shadow Prompt Researcher phase does not match mechanism"
            )
        if selected.task.evaluator != "hook_model":
            raise ValueError(
                "Shadow Prompt Researcher requires a hook_model task"
            )
        review_phases = {
            observation.phase
            for review in self.trial_reviews
            for observation in review.predicate_observations
        }
        if self.phase not in review_phases:
            raise ValueError(
                "Shadow Prompt Researcher lacks reviewed cases for phase"
            )
        return self


class ShadowHookPromptProduct(TeacherPayload):
    """Frozen Prompt and runtime adapter bound to one exact Phase Task."""

    phase: HookPhaseName
    task_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_projection_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    prompt: str = Field(min_length=1, max_length=6000)
    thinking_mode: HookPromptThinkingMode
    response_adapter: HookPromptResponseAdapter


class ShadowPromptResearchSubmission(TeacherPayload):
    """Model-facing selection of one actually reviewed Prompt probe."""

    outcome: ShadowPromptResearchOutcome
    prompt: str | None = Field(default=None, min_length=1, max_length=6000)
    thinking_mode: HookPromptThinkingMode | None = None
    selected_probe_ref: str | None = Field(
        default=None,
        min_length=1,
        max_length=120,
    )
    obligation: str | None = Field(default=None, min_length=1, max_length=800)

    @model_validator(mode="after")
    def validate_outcome(self) -> "ShadowPromptResearchSubmission":
        selected = (
            self.prompt is not None,
            self.thinking_mode is not None,
            self.selected_probe_ref is not None,
        )
        if self.outcome == "ready":
            if not all(selected):
                raise ValueError(
                    "ready Prompt Research submission requires prompt, "
                    "thinking_mode and selected_probe_ref"
                )
            if self.obligation is not None:
                raise ValueError(
                    "ready Prompt Research submission must not include "
                    "obligation"
                )
            return self
        if any(selected):
            raise ValueError(
                "not_feasible Prompt Research submission must not include "
                "a selected Prompt"
            )
        if self.obligation is None:
            raise ValueError(
                "not_feasible Prompt Research submission requires obligation"
            )
        return self


class ShadowPromptResearchResult(TeacherPayload):
    """Public Prompt Research result with program-owned product identity."""

    outcome: ShadowPromptResearchOutcome
    product: ShadowHookPromptProduct | None = None
    obligation: str | None = Field(default=None, min_length=1, max_length=800)

    @model_validator(mode="after")
    def validate_outcome(self) -> "ShadowPromptResearchResult":
        if self.outcome == "ready":
            if self.product is None:
                raise ValueError("ready Prompt Research result requires product")
            if self.obligation is not None:
                raise ValueError(
                    "ready Prompt Research result must not include obligation"
                )
            return self
        if self.product is not None:
            raise ValueError(
                "not_feasible Prompt Research result must not include product"
            )
        if self.obligation is None:
            raise ValueError(
                "not_feasible Prompt Research result requires obligation"
            )
        return self


class ShadowCompilerInput(TeacherPayload):
    """Shadow Mechanism plus exact managed Prompt Products for compilation."""

    mechanism: ShadowMechanismSpec
    prompt_products: list[ShadowHookPromptProduct] = Field(
        default_factory=list,
        max_length=4,
    )
    implementation_constraints: list[str] = Field(default_factory=list)
    validation_feedback: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_prompt_products(self) -> "ShadowCompilerInput":
        from ..shadow_task_inputs import (
            shadow_input_projection_digest,
            shadow_phase_task_digest,
        )

        by_phase = {product.phase: product for product in self.prompt_products}
        if len(by_phase) != len(self.prompt_products):
            raise ValueError("Shadow Compiler Prompt Product phases must be unique")
        required = {
            phase.phase
            for phase in self.mechanism.phases
            if phase.task.evaluator == "hook_model"
        }
        if set(by_phase) != required:
            raise ValueError(
                "Shadow Compiler Prompt Products must exactly cover hook_model "
                f"phases: expected {sorted(required)}, got {sorted(by_phase)}"
            )
        for phase in self.mechanism.phases:
            product = by_phase.get(phase.phase)
            if product is None:
                continue
            task = phase.task.model_dump(mode="json")
            if product.task_digest != shadow_phase_task_digest(
                phase=phase.phase,
                task=task,
            ):
                raise ValueError(
                    f"Prompt Product task digest differs at {phase.phase}"
                )
            if product.input_projection_digest != shadow_input_projection_digest(
                phase=phase.phase,
                inputs=[
                    item.model_dump(mode="json")
                    for item in phase.task.inputs
                ],
            ):
                raise ValueError(
                    "Prompt Product input projection digest differs at "
                    f"{phase.phase}"
                )
            if isinstance(phase.task, ShadowDecisionTask):
                if product.response_adapter != "tri_label":
                    raise ValueError(
                        "Shadow decision Task requires tri_label Prompt Product"
                    )
            elif product.response_adapter not in {
                "raw_text",
                "structured_edit",
            }:
                raise ValueError(
                    "Shadow generation Task requires raw_text or "
                    "structured_edit Prompt Product"
                )
        return self


HookFeasibilityStatus = Literal[
    "supported",
    "unstable",
    "unsupported",
    "inconclusive",
]
HookFeasibilityDecision = Literal[
    "feasible",
    "needs_spec_revision",
    "needs_research_revision",
]


class HookFeasibilityPhaseFinding(TeacherPayload):
    """一个 Hook-model phase 在真实 prefix 上的能力判断。"""

    phase: HookPhaseName
    status: HookFeasibilityStatus
    recommended_thinking_mode: Literal["enabled", "disabled"] | None = None
    assessment: str = Field(min_length=1, max_length=700)


class HookFeasibilityReviewerInput(TeacherPayload):
    """Hook Feasibility Reviewer 的冻结机制与描述性 Probe 证据。"""

    mechanism: MechanismSpec
    probe_evidence: dict[str, Any]
    prior_model_experiments: list[dict[str, Any]] = Field(
        default_factory=list
    )


class HookFeasibilityReview(TeacherPayload):
    """目标 Student 模型能否承担冻结 Hook 语义判断的结论。"""

    decision: HookFeasibilityDecision
    phase_findings: list[HookFeasibilityPhaseFinding] = Field(min_length=1)
    assessment: str = Field(min_length=1, max_length=1200)
    compiler_guidance: list[
        Annotated[str, Field(min_length=1, max_length=400)]
    ] = Field(default_factory=list, max_length=4)
    revision_feedback: str | None = Field(default=None, max_length=800)

    @model_validator(mode="after")
    def validate_decision(self) -> "HookFeasibilityReview":
        phases = [finding.phase for finding in self.phase_findings]
        if len(phases) != len(set(phases)):
            raise ValueError(
                "hook feasibility phase_findings must not repeat phases"
            )
        if self.decision == "feasible":
            if any(
                finding.status != "supported"
                for finding in self.phase_findings
            ):
                raise ValueError(
                    "feasible hook review requires every phase to be supported"
                )
            if self.revision_feedback is not None:
                raise ValueError(
                    "feasible hook review must not include revision_feedback"
                )
            return self
        if not self.revision_feedback:
            raise ValueError(
                f"{self.decision} requires revision_feedback"
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
    student_model_experiments: list[dict[str, Any]] = Field(
        default_factory=list
    )
    implementation_constraints: list[str] = Field(default_factory=list)
    validation_feedback: list[str] = Field(default_factory=list)
    conformance_failures: list[dict[str, Any]] = Field(default_factory=list)


class CandidateReviewerInput(TeacherPayload):
    """Candidate Reviewer 的机制目标与确定性门禁摘要。"""

    mechanism: MechanismSpec
    validation_summary: dict[str, Any]
    implementation_summary: str = Field(min_length=1)
    candidate_outcome_digest: dict[str, Any] = Field(default_factory=dict)
    unresolved_risk: str | None = None
    historical_experience: list[str] = Field(default_factory=list)


ConformanceVerdict = Literal[
    "faithful",
    "implementation_mismatch",
    "not_observed",
    "runtime_error",
    "inconclusive",
]
ConformanceFailureLayer = Literal[
    "projection",
    "evaluator",
    "parsing",
    "state",
    "action",
    "integration",
    "ambiguous_spec",
]
ConformanceDecisionLabel = Literal[
    "positive",
    "negative",
    "uncertain",
    "parse_error",
    "unavailable",
]
ConformanceRevisionRoute = Literal[
    "implementation",
    "mechanism",
    "evidence",
]
ConformanceLocalEfficacy = Literal[
    "beneficial",
    "neutral",
    "harmful",
    "inconclusive",
]


class ConformanceReviewerInput(TeacherPayload):
    """Conformance Reviewer 的 Example 级 Candidate 行为审阅任务。"""

    mechanism: MechanismSpec
    trial_refs: list[str] = Field(min_length=1)
    reference_observations: list[dict[str, Any]] = Field(min_length=1)
    example_id: str = Field(min_length=1)
    candidate_trajectory_views: list[dict[str, Any]] = Field(min_length=1)


class ShadowConformanceReviewerInput(TeacherPayload):
    """Shadow Mechanism 的 Example 级 Candidate 行为审阅任务。"""

    mechanism: ShadowMechanismSpec
    trial_refs: list[str] = Field(min_length=1)
    reference_observations: list[dict[str, Any]] = Field(min_length=1)
    example_id: str = Field(min_length=1)
    candidate_trajectory_views: list[dict[str, Any]] = Field(min_length=1)


class ConformanceReview(TeacherPayload):
    """Conformance Reviewer 对一条 Candidate rollout 的语义判断。"""

    verdict: ConformanceVerdict
    observed_phases: list[HookPhaseName] = Field(default_factory=list)
    assessment: str = Field(min_length=1, max_length=1200)
    repair_obligation: str | None = Field(default=None, max_length=500)
    predicate_ref: str | None = Field(default=None, max_length=200)
    expected_label: ConformanceDecisionLabel | None = None
    observed_label: ConformanceDecisionLabel | None = None
    failure_layer: ConformanceFailureLayer | None = None
    decisive_input_summary: str | None = Field(default=None, max_length=500)
    recommended_route: ConformanceRevisionRoute | None = None
    local_efficacy: ConformanceLocalEfficacy
    local_efficacy_assessment: str = Field(min_length=1, max_length=400)
    target_behavior_observed: bool = False

    @model_validator(mode="after")
    def validate_repair_obligation(self) -> "ConformanceReview":
        if len(self.observed_phases) != len(set(self.observed_phases)):
            raise ValueError("observed_phases must not contain duplicates")
        if self.verdict == "faithful":
            if not self.observed_phases:
                raise ValueError(
                    "faithful conformance finding requires an observed phase"
                )
            if self.repair_obligation is not None:
                raise ValueError(
                    "faithful conformance finding must not request repair"
                )
            diagnostics = (
                self.predicate_ref,
                self.expected_label,
                self.observed_label,
                self.failure_layer,
                self.decisive_input_summary,
                self.recommended_route,
            )
            if any(value is not None for value in diagnostics):
                raise ValueError(
                    "faithful conformance finding must not include failure "
                    "diagnostics"
                )
            return self
        if not self.repair_obligation:
            raise ValueError(
                f"{self.verdict} conformance finding requires "
                "repair_obligation"
            )
        if self.failure_layer is None or self.recommended_route is None:
            raise ValueError(
                "non-faithful conformance finding requires failure_layer "
                "and recommended_route"
            )
        if not self.decisive_input_summary:
            raise ValueError(
                "non-faithful conformance finding requires "
                "decisive_input_summary"
            )
        if self.failure_layer == "evaluator":
            if (
                not self.predicate_ref
                or self.expected_label is None
                or self.observed_label is None
            ):
                raise ValueError(
                    "evaluator mismatch requires predicate_ref, "
                    "expected_label, and observed_label"
                )
        if self.failure_layer == "parsing":
            if not self.predicate_ref or self.observed_label != "parse_error":
                raise ValueError(
                    "parsing mismatch requires predicate_ref and "
                    "observed_label=parse_error"
                )
        if self.failure_layer == "ambiguous_spec":
            if not self.predicate_ref:
                raise ValueError(
                    "ambiguous_spec finding requires predicate_ref"
                )
            if self.recommended_route != "mechanism":
                raise ValueError(
                    "ambiguous_spec finding must route to mechanism"
                )
        return self


class ConformanceBatchFinding(ConformanceReview):
    """Example batch 中一条独立 replicate Finding。"""

    replicate_id: str = Field(min_length=1)


class ConformanceReviewBatch(TeacherPayload):
    """Conformance Reviewer 对同一 Example 的有序独立 Findings。"""

    findings: list[ConformanceBatchFinding] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_replicates(self) -> "ConformanceReviewBatch":
        replicate_ids = [item.replicate_id for item in self.findings]
        if len(replicate_ids) != len(set(replicate_ids)):
            raise ValueError("conformance batch must not repeat replicate_id")
        return self


class ConformanceFinding(ConformanceReview):
    """程序附加任务身份后的权威 Conformance Finding。"""

    trial_refs: list[str] = Field(min_length=1)
    candidate_run_ref: str = Field(min_length=1)


ExperienceValidityStatus = Literal[
    "confirmed",
    "failed",
    "unknown",
    "not_applicable",
]
ExperienceDetailCoverage = Literal["complete", "bounded_projection"]
DirectionUpdateTarget = Literal[
    "failure_direction",
    "research_scheme",
    "mechanism_scheme",
]


class ExperienceValidity(TeacherPayload):
    """Causal validity boundaries established by the source adapter."""

    reference: ExperienceValidityStatus
    model_input: ExperienceValidityStatus
    implementation_fidelity: ExperienceValidityStatus
    data_environment: ExperienceValidityStatus


class ExperienceObservation(TeacherPayload):
    """One normalized expected-versus-observed evidence unit."""

    observation_id: int = Field(ge=1)
    subject: str = Field(min_length=1, max_length=300)
    expected: str = Field(min_length=1, max_length=800)
    observed: str = Field(min_length=1, max_length=800)
    comparison: str = Field(min_length=1, max_length=800)
    conditions: str = Field(min_length=1, max_length=600)
    validity: ExperienceValidity
    evidence_structure: str = Field(min_length=1, max_length=800)
    open_checks: list[str] = Field(default_factory=list, max_length=8)


class CapabilityObservation(ExperienceObservation):
    """One model-behavior observation under a program-owned decision scope."""

    decision_scope: str = Field(min_length=1, max_length=1200)


class ExperienceDetailDirectoryEntry(TeacherPayload):
    """One authorized Detail that can resolve a named evidence gap."""

    detail_id: int = Field(ge=1)
    observation_id: int = Field(ge=1)
    resolves: str = Field(min_length=1, max_length=120)
    coverage: ExperienceDetailCoverage
    description: str = Field(min_length=1, max_length=240)


class CapabilitySummarizerInput(TeacherPayload):
    """Capability Pass view over normalized observations and Detail entries."""

    observations: list[CapabilityObservation] = Field(min_length=1)
    detail_directory: list[ExperienceDetailDirectoryEntry] = Field(
        default_factory=list
    )

    @model_validator(mode="after")
    def validate_packet_ids(self) -> "CapabilitySummarizerInput":
        _validate_experience_packet_ids(
            self.observations,
            self.detail_directory,
        )
        return self


class DirectionLayer(TeacherPayload):
    """Stable identity and fixed typed-artifact projection for one layer."""

    ref: str = Field(min_length=1, max_length=240)
    summary: str = Field(min_length=1, max_length=800)


class ResearchDirectionContext(TeacherPayload):
    """Program-maintained Failure, Research, and Mechanism Scheme lineage."""

    failure_direction: DirectionLayer
    research_scheme: DirectionLayer
    mechanism_scheme: DirectionLayer | None = None
    update_target: DirectionUpdateTarget

    @model_validator(mode="after")
    def validate_update_target_exists(self) -> "ResearchDirectionContext":
        if self.update_target == "mechanism_scheme" and self.mechanism_scheme is None:
            raise ValueError(
                "mechanism_scheme update requires a mechanism scheme context"
            )
        return self


class DirectionSummarizerInput(TeacherPayload):
    """Direction Pass view over one stable Research Direction."""

    observations: list[ExperienceObservation] = Field(min_length=1)
    detail_directory: list[ExperienceDetailDirectoryEntry] = Field(
        default_factory=list
    )
    direction_context: ResearchDirectionContext

    @model_validator(mode="after")
    def validate_packet_ids(self) -> "DirectionSummarizerInput":
        _validate_experience_packet_ids(
            self.observations,
            self.detail_directory,
        )
        return self


class CapabilityExperienceProposal(TeacherPayload):
    """One semantic model limitation proposed from direct observations."""

    observed_limitation: str = Field(min_length=1, max_length=600)
    evidence_refs: list[int] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_refs(self) -> "CapabilityExperienceProposal":
        _validate_unique_positive_refs(self.evidence_refs)
        return self


class CapabilityExperienceSummary(TeacherPayload):
    """Zero or more independently supported Capability proposals."""

    items: list[CapabilityExperienceProposal] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_items(self) -> "CapabilityExperienceSummary":
        keys = [
            (item.observed_limitation.casefold(), tuple(item.evidence_refs))
            for item in self.items
        ]
        if len(keys) != len(set(keys)):
            raise ValueError(
                "capability experience summary contains duplicate items"
            )
        return self


class CapabilityExperienceProductItem(TeacherPayload):
    """One program-assembled Capability Experience for later consumption."""

    decision_scope: str = Field(min_length=1, max_length=1200)
    observed_limitation: str = Field(min_length=1, max_length=600)
    evidence_summary: str = Field(min_length=1, max_length=2400)
    evidence_refs: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_refs(self) -> "CapabilityExperienceProductItem":
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError(
                "capability experience evidence_refs must be unique"
            )
        return self


class CapabilityExperienceProduct(TeacherPayload):
    """Program-owned Capability Experience items derived from one Role run."""

    items: list[CapabilityExperienceProductItem] = Field(default_factory=list)


class DirectionDraft(TeacherPayload):
    """One evidence-bounded update to the selected Direction layer."""

    evidence_update: str = Field(min_length=1, max_length=800)
    disposition: str = Field(min_length=1, max_length=400)
    revisit_condition: str = Field(min_length=1, max_length=500)
    applicability: str = Field(min_length=1, max_length=400)
    evidence_refs: list[int] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_refs(self) -> "DirectionDraft":
        _validate_unique_positive_refs(self.evidence_refs)
        return self


class DirectionSummary(TeacherPayload):
    """Zero or one Draft for the Packet's selected Direction layer."""

    items: list[DirectionDraft] = Field(default_factory=list, max_length=1)


def _validate_experience_packet_ids(
    observations: list[ExperienceObservation],
    details: list[ExperienceDetailDirectoryEntry],
) -> None:
    observation_ids = [item.observation_id for item in observations]
    if len(observation_ids) != len(set(observation_ids)):
        raise ValueError("experience observation IDs must be unique")
    detail_ids = [item.detail_id for item in details]
    if len(detail_ids) != len(set(detail_ids)):
        raise ValueError("experience detail IDs must be unique")
    unknown = {
        item.observation_id for item in details
    } - set(observation_ids)
    if unknown:
        raise ValueError(
            f"experience details reference unknown observations: {sorted(unknown)}"
        )


def _validate_unique_positive_refs(refs: list[int]) -> None:
    if any(ref < 1 for ref in refs):
        raise ValueError("experience evidence refs must be positive")
    if len(refs) != len(set(refs)):
        raise ValueError("experience evidence refs must be unique")


@dataclass(frozen=True)
class TeacherRoleDefinition:
    """代码内固定的角色兼容性合同；不兼容变化必须提升 version。"""

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
        version=2,
        input_type=HypothesisResearcherInput,
        output_contract_id="hypothesis_researcher_result",
        output_contract_version=1,
        output_type=HypothesisResearcherResult,
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
        output_contract_version=2,
        output_type=TrialReview,
    ),
    "mechanism_distiller": TeacherRoleDefinition(
        role_id="mechanism_distiller",
        version=1,
        input_type=MechanismDistillerInput,
        output_contract_id="mechanism_distillation",
        output_contract_version=2,
        output_type=MechanismDistillation,
    ),
    "shadow_mechanism_distiller": TeacherRoleDefinition(
        role_id="shadow_mechanism_distiller",
        version=1,
        input_type=MechanismDistillerInput,
        output_contract_id="shadow_distillation_result",
        output_contract_version=1,
        output_type=ShadowDistillationResult,
    ),
    "shadow_prompt_researcher": TeacherRoleDefinition(
        role_id="shadow_prompt_researcher",
        version=1,
        input_type=ShadowPromptResearcherInput,
        output_contract_id="shadow_prompt_research_result",
        output_contract_version=1,
        output_type=ShadowPromptResearchResult,
    ),
    "hook_feasibility_reviewer": TeacherRoleDefinition(
        role_id="hook_feasibility_reviewer",
        version=1,
        input_type=HookFeasibilityReviewerInput,
        output_contract_id="hook_feasibility_review",
        output_contract_version=1,
        output_type=HookFeasibilityReview,
    ),
    "intervention_worker": TeacherRoleDefinition(
        role_id="intervention_worker",
        version=1,
        input_type=InterventionWorkerInput,
        output_contract_id="intervention_worker_result",
        output_contract_version=4,
        output_type=InterventionWorkerResult,
    ),
    "compiler": TeacherRoleDefinition(
        role_id="compiler",
        version=1,
        input_type=CompilerInput,
        output_contract_id="compiler_result",
        output_contract_version=2,
        output_type=CompilerResult,
    ),
    "shadow_compiler": TeacherRoleDefinition(
        role_id="shadow_compiler",
        version=1,
        input_type=ShadowCompilerInput,
        output_contract_id="compiler_result",
        output_contract_version=2,
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
    "conformance_reviewer": TeacherRoleDefinition(
        role_id="conformance_reviewer",
        version=1,
        input_type=ConformanceReviewerInput,
        output_contract_id="conformance_review_batch",
        output_contract_version=5,
        output_type=ConformanceReviewBatch,
    ),
    "shadow_conformance_reviewer": TeacherRoleDefinition(
        role_id="shadow_conformance_reviewer",
        version=1,
        input_type=ShadowConformanceReviewerInput,
        output_contract_id="conformance_review_batch",
        output_contract_version=5,
        output_type=ConformanceReviewBatch,
    ),
    "capability_summarizer": TeacherRoleDefinition(
        role_id="capability_summarizer",
        version=2,
        input_type=CapabilitySummarizerInput,
        output_contract_id="capability_experience_proposal",
        output_contract_version=1,
        output_type=CapabilityExperienceSummary,
    ),
    "direction_summarizer": TeacherRoleDefinition(
        role_id="direction_summarizer",
        version=1,
        input_type=DirectionSummarizerInput,
        output_contract_id="direction_summary",
        output_contract_version=1,
        output_type=DirectionSummary,
    ),
}


def get_teacher_role(role_id: str, version: int) -> TeacherRoleDefinition:
    """按稳定 ID 和版本解析角色定义。"""

    definition = _ROLE_DEFINITIONS.get(role_id)
    if definition is None or definition.version != version:
        raise ValueError(f"unknown Teacher role contract: {role_id}@{version}")
    return definition
