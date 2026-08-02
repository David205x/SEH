"""Teacher 角色可通过工具访问的只读证据和临时草稿。"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from math import ceil
from pathlib import Path
from statistics import mean
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..intervention.prefix import load_rollout_record

from ..mechanism.capabilities import build_compiler_capability_packet
from ..roles.contracts import (
    CompilerInput,
    DecisionEvaluator,
    EvidenceReview,
    EvidenceReviewerInput,
    FailureAnalystInput,
    HypothesisResearcherInput,
    InterventionWorkerInput,
    MechanismSpec,
    TeacherPayload,
    TrialReview,
    TrialReviewerInput,
)
from .stores import (
    CandidateComparisonStore,
    CandidateReviewResourceConfig,
    CompilerResourceConfig,
    CompilerWorkspaceStore,
    InterventionBranchStore,
    InterventionResourceConfig,
)


class TeacherResourceConfig(BaseModel):
    """一个 standalone Teacher run 的程序侧资源配置。"""

    model_config = ConfigDict(extra="forbid")

    report_dir: Path | None = None
    rollout_file: Path | None = None
    student_template_root: Path | None = None
    trial_files: list[Path] = Field(default_factory=list)
    intervention: InterventionResourceConfig | None = None
    compiler: CompilerResourceConfig | None = None
    candidate_review: CandidateReviewResourceConfig | None = None


@dataclass
class TeacherResources:
    """一次 Teacher run 可见资源的聚合入口。"""

    evaluation: "EvaluationEvidenceStore | None" = None
    trials: "TrialEvidenceStore | None" = None
    mechanisms: "MechanismDraftStore" = field(
        default_factory=lambda: MechanismDraftStore()
    )
    intervention: InterventionBranchStore | None = None
    compiler: CompilerWorkspaceStore | None = None
    candidate_review: CandidateComparisonStore | None = None
    intervention_capabilities_inspected: bool = False
    compiler_capability_packet: dict[str, Any] | None = None
    evidence_review_phases: tuple[str, ...] = ()

    @classmethod
    def from_config(cls, config: TeacherResourceConfig) -> "TeacherResources":
        """加载 request 声明的 UTF-8 资源。"""

        evaluation = None
        if config.report_dir is not None:
            evaluation = EvaluationEvidenceStore.load(
                report_dir=config.report_dir,
                rollout_file=config.rollout_file,
                student_template_root=config.student_template_root,
            )
        elif config.rollout_file is not None or config.student_template_root is not None:
            raise ValueError(
                "rollout_file and student_template_root require report_dir"
            )
        trials = (
            TrialEvidenceStore.load(config.trial_files)
            if config.trial_files
            else None
        )
        intervention = (
            InterventionBranchStore(config.intervention)
            if config.intervention is not None
            else None
        )
        compiler = (
            CompilerWorkspaceStore.load(config.compiler)
            if config.compiler is not None
            else None
        )
        candidate_review = (
            CandidateComparisonStore.load(config.candidate_review)
            if config.candidate_review is not None
            else None
        )
        return cls(
            evaluation=evaluation,
            trials=trials,
            intervention=intervention,
            compiler=compiler,
            candidate_review=candidate_review,
        )

    def bind_role_input(self, role_input: TeacherPayload) -> None:
        """把仅在输入验证后才可确定的资源选择绑定到当前 run。"""

        if isinstance(role_input, FailureAnalystInput):
            if self.evaluation is None:
                raise ValueError("Failure Analyst requires evaluation resources")
            self.evaluation.set_trajectory_read_budget(6)
        if isinstance(role_input, HypothesisResearcherInput):
            if self.evaluation is None:
                raise ValueError(
                    "Hypothesis Researcher requires evaluation resources"
                )
            self.evaluation.restrict_to_evidence_refs(
                role_input.problem_direction.evidence_refs
            )
        if isinstance(role_input, TrialReviewerInput):
            if self.trials is None:
                raise ValueError("Trial Reviewer requires trial resources")
            self.trials.bind_refs([role_input.trial_ref])
        if isinstance(role_input, EvidenceReviewerInput):
            self.evidence_review_phases = tuple(
                directive.phase
                for directive in role_input.hypothesis.phase_plan
            )
        if isinstance(role_input, InterventionWorkerInput):
            if self.intervention is None:
                raise ValueError(
                    "Intervention Worker requires intervention resources"
                )
            self.intervention.bind(role_input)
        if isinstance(role_input, CompilerInput):
            if self.compiler is None:
                raise ValueError("Compiler requires compiler resources")
            packet = build_compiler_capability_packet(
                role_input.mechanism
            )
            self.compiler.bind_capability_packet(packet)
            self.compiler_capability_packet = packet

    def model_context(self, role_id: str) -> dict[str, Any]:
        """返回只适合直接进入 Prompt 的紧凑程序上下文。"""

        if role_id == "failure_analyst":
            if self.evaluation is None:
                raise ValueError("Failure Analyst requires evaluation resources")
            return {
                "evaluation": self.evaluation.failure_analyst_context(),
            }
        if role_id == "hypothesis_researcher":
            if self.evaluation is None:
                raise ValueError(
                    "Hypothesis Researcher requires evaluation resources"
                )
            return {
                "evaluation": (
                    self.evaluation.hypothesis_researcher_context()
                ),
            }
        return {
            "evaluation": (
                self.evaluation.initial_context()
                if self.evaluation is not None
                else None
            ),
            "trials": (
                self.trials.initial_context() if self.trials is not None else None
            ),
            "mechanism_drafts": self.mechanisms.summary(),
            "intervention": (
                self.intervention.initial_context()
                if self.intervention is not None
                else None
            ),
            "compiler": (
                {
                    **self.compiler.initial_context(),
                    "capability_packet": self.compiler_capability_packet,
                }
                if self.compiler is not None
                else None
            ),
            "candidate_review": (
                self.candidate_review.initial_context()
                if self.candidate_review is not None
                else None
            ),
        }

    def artifacts(self) -> dict[str, Any]:
        """返回由角色工具产生、需要随运行结果持久化的程序 artifact。"""

        return {
            "intervention_trial": (
                self.intervention.artifact()
                if self.intervention is not None
                else None
            ),
            "compiler_candidate": (
                self.compiler.artifact()
                if self.compiler is not None
                else None
            ),
        }

    def mark_intervention_capabilities_inspected(self) -> None:
        """记录 Researcher 已读取运行时能力目录。"""

        self.intervention_capabilities_inspected = True

    def validate_hypothesis_research(self) -> None:
        """验证 Researcher 完成受限证据和能力检查后再提交。"""

        if self.evaluation is None:
            raise ValueError("Hypothesis Researcher resources are unavailable")
        self.evaluation.validate_allowed_evidence_inspected()
        if not self.intervention_capabilities_inspected:
            raise ValueError(
                "get_intervention_capabilities must be inspected before "
                "submitting an intervention hypothesis"
            )

    def validate_evidence_review(self, review: EvidenceReview) -> None:
        """校验全局 Reviewer 覆盖冻结假设的全部 phase。"""

        actual = tuple(finding.phase for finding in review.phase_findings)
        if actual != self.evidence_review_phases:
            raise ValueError(
                "Evidence Reviewer phase_findings must follow the frozen "
                f"phase plan: expected={list(self.evidence_review_phases)}, "
                f"actual={list(actual)}"
            )

    def role_session_state(self) -> dict[str, Any]:
        """导出恢复同一角色会话所需的最小程序状态。"""

        return {
            "intervention_capabilities_inspected": (
                self.intervention_capabilities_inspected
            ),
            "evaluation": (
                self.evaluation.role_session_state()
                if self.evaluation is not None
                else None
            ),
            "trials": (
                self.trials.role_session_state()
                if self.trials is not None
                else None
            ),
        }

    def restore_role_session_state(self, state: dict[str, Any]) -> None:
        """恢复经 artifact 持久化且可重新校验的资源访问账本。"""

        capabilities = state.get("intervention_capabilities_inspected")
        if not isinstance(capabilities, bool):
            raise TypeError(
                "role session capability-inspection state must be boolean"
            )
        evaluation_state = state.get("evaluation")
        if self.evaluation is None:
            if evaluation_state is not None:
                raise ValueError(
                    "role session contains unavailable evaluation state"
                )
        else:
            if not isinstance(evaluation_state, dict):
                raise TypeError(
                    "role session evaluation state must be an object"
                )
            self.evaluation.restore_role_session_state(evaluation_state)
        trial_state = state.get("trials")
        if self.trials is None:
            if trial_state is not None:
                raise ValueError(
                    "role session contains unavailable trial state"
                )
        elif trial_state is not None:
            if not isinstance(trial_state, dict):
                raise TypeError(
                    "role session trial state must be an object"
                )
            self.trials.restore_role_session_state(trial_state)
        self.intervention_capabilities_inspected = capabilities


@dataclass(frozen=True)
class EvaluationEvidenceStore:
    """Evaluation report、Student rollout 和 Harness 的只读索引。"""

    report_dir: Path
    rollout_file: Path
    summary: dict[str, Any]
    cases: dict[str, dict[str, Any]]
    rollouts: dict[str, dict[str, dict[str, Any]]]
    student_template_root: Path | None
    harness_manifest: dict[str, Any] | None
    _access_limits: dict[str, Any] = field(default_factory=dict)
    _trajectory_reads: set[tuple[str, str]] = field(default_factory=set)

    @classmethod
    def load(
        cls,
        *,
        report_dir: Path,
        rollout_file: Path | None,
        student_template_root: Path | None,
    ) -> "EvaluationEvidenceStore":
        """从标准 report 目录加载稳定 example/replicate 索引。"""

        root = report_dir.resolve()
        summary = _read_json_object(root / "summary.json")
        cases = {
            _required_string(item, "example_id"): item
            for item in _read_jsonl(root / "per_example.jsonl")
        }
        source = rollout_file
        if source is None:
            source_value = summary.get("source_file")
            if not isinstance(source_value, str) or not source_value.strip():
                raise ValueError("evaluation summary has no source_file")
            source = Path(source_value)
        source = source.resolve()
        rollouts: dict[str, dict[str, dict[str, Any]]] = {}
        for record in _read_jsonl(source):
            example = record.get("example")
            replicate = record.get("replicate")
            if not isinstance(example, dict) or not isinstance(replicate, dict):
                raise ValueError("rollout record lacks example or replicate object")
            example_id = _required_string(example, "example_id")
            replicate_id = _required_string(replicate, "replicate_id")
            rollouts.setdefault(example_id, {})[replicate_id] = record

        template_root = student_template_root.resolve() if student_template_root else None
        manifest = None
        if template_root is not None:
            manifest = _read_json_object(template_root / "harness.json")
        return cls(
            report_dir=root,
            rollout_file=source,
            summary=summary,
            cases=cases,
            rollouts=rollouts,
            student_template_root=template_root,
            harness_manifest=manifest,
        )

    def initial_context(self) -> dict[str, Any]:
        """返回总览，不把案例内容直接塞入初始 Prompt。"""

        manifest = self.harness_manifest or {}
        return {
            "report_dir": str(self.report_dir),
            "rollout_file": str(self.rollout_file),
            "metrics": self.summary.get("metrics"),
            "provenance": self.summary.get("provenance"),
            "case_count": len(self.cases),
            "harness": {
                "harness_id": manifest.get("harness_id"),
                "tool_count": len(manifest.get("tools", []))
                if isinstance(manifest.get("tools"), list)
                else 0,
                "extension_count": len(manifest.get("extensions", []))
                if isinstance(manifest.get("extensions"), list)
                else 0,
            },
        }

    def failure_analyst_context(self) -> dict[str, Any]:
        """返回 Failure Analyst 诊断行为所需的最小总览。"""

        metrics = self.summary.get("metrics")
        metrics = metrics if isinstance(metrics, dict) else {}
        answers = metrics.get("answers")
        answers = answers if isinstance(answers, dict) else {}
        execution = metrics.get("execution")
        execution = execution if isinstance(execution, dict) else {}
        provenance = self.summary.get("provenance")
        provenance = provenance if isinstance(provenance, dict) else {}
        sampling = provenance.get("execution")
        sampling = sampling if isinstance(sampling, dict) else {}
        return {
            "outcomes": {
                key: answers.get(key)
                for key in (
                    "scored_count",
                    "correct_count",
                    "accuracy",
                    "example_count",
                    "stable_failure_count",
                    "unstable_count",
                    "unresolved_example_count",
                )
            }
            | {
                "rollouts_per_example": sampling.get("rollouts_per_example"),
            },
            "execution": {
                key: execution.get(key)
                for key in (
                    "record_count",
                    "completed_rate",
                    "status_counts",
                    "retriever_error_rate",
                    "mean_steps",
                    "mean_tool_calls",
                    "mean_duplicate_queries",
                )
            },
        }

    def hypothesis_researcher_context(self) -> dict[str, Any]:
        """返回 Researcher 设计软干预所需的最小环境摘要。"""

        provenance = self.summary.get("provenance")
        provenance = provenance if isinstance(provenance, dict) else {}
        sampling = provenance.get("execution")
        sampling = sampling if isinstance(sampling, dict) else {}
        manifest = self.harness_manifest or {}
        allowlist = self._trajectory_allowlist()
        return {
            "evidence": {
                "cited_trajectory_count": (
                    len(allowlist) if allowlist is not None else 0
                ),
                "cited_example_count": (
                    len({item[0] for item in allowlist})
                    if allowlist is not None
                    else 0
                ),
                "rollouts_per_example": sampling.get(
                    "rollouts_per_example"
                ),
            },
            "student": {
                "harness_id": manifest.get("harness_id"),
                "tools": _manifest_instance_ids(manifest.get("tools")),
                "extensions": _manifest_instance_ids(
                    manifest.get("extensions")
                ),
            },
        }

    def get_cost_summary(self) -> dict[str, Any]:
        """汇总 replicate 级 token 分布，不把样本规模总量当作成本结论。"""

        executions = list(_replicate_executions(self.cases.values()))
        metrics = (
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "student_total_tokens",
            "hook_total_tokens",
        )
        return {
            "replicate_count": len(executions),
            "metrics": {
                metric: _token_distribution(executions, metric)
                for metric in metrics
            },
        }

    def list_cases(
        self,
        *,
        page: int,
        page_size: int,
        stability: str,
    ) -> dict[str, Any]:
        """分页列出逻辑样本及其稳定性摘要。"""

        selected = [
            case
            for case in self.cases.values()
            if stability == "any" or case.get("stability") == stability
        ]
        selected.sort(key=lambda item: str(item.get("example_id", "")))
        start = (page - 1) * page_size
        end = start + page_size
        items = [
            {
                "example_id": item.get("example_id"),
                "question": item.get("question"),
                "stability": item.get("stability"),
                "success_rate": item.get("success_rate"),
                "answer_consistency": item.get("answer_consistency"),
                "run_status": item.get("run_status"),
                "available_replicates": [
                    replicate.get("replicate_id")
                    for replicate in item.get("replicates", [])
                    if isinstance(replicate, dict)
                ],
            }
            for item in selected[start:end]
        ]
        total_pages = max(1, (len(selected) + page_size - 1) // page_size)
        return {
            "page": page,
            "page_size": page_size,
            "total_items": len(selected),
            "total_pages": total_pages,
            "items": items,
        }

    def list_cases_by_cost(
        self,
        *,
        page: int,
        page_size: int,
        stability: str,
        token_metric: str,
        order: str,
    ) -> dict[str, Any]:
        """按 replicate token 均值排序逻辑样本。"""

        selected = [
            _case_cost_item(case, token_metric)
            for case in self.cases.values()
            if stability == "any" or case.get("stability") == stability
        ]
        if order == "descending":
            selected.sort(
                key=lambda item: (
                    item["mean_tokens"] is not None,
                    item["mean_tokens"] or 0,
                    str(item["example_id"]),
                ),
                reverse=True,
            )
        else:
            selected.sort(
                key=lambda item: (
                    item["mean_tokens"] is None,
                    item["mean_tokens"] or 0,
                    str(item["example_id"]),
                )
            )
        start = (page - 1) * page_size
        end = start + page_size
        total_pages = max(1, (len(selected) + page_size - 1) // page_size)
        return {
            "token_metric": token_metric,
            "order": order,
            "page": page,
            "page_size": page_size,
            "total_items": len(selected),
            "total_pages": total_pages,
            "items": selected[start:end],
        }

    def get_case(self, example_id: str) -> dict[str, Any]:
        """读取一个逻辑样本的完整 evaluation 记录。"""

        allowlist = self._trajectory_allowlist()
        if (
            allowlist is not None
            and example_id not in {item[0] for item in allowlist}
        ):
            raise ValueError(
                "Hypothesis Researcher may inspect only cited examples"
            )
        try:
            return self.cases[example_id]
        except KeyError as exc:
            raise KeyError(f"unknown evaluation example_id: {example_id}") from exc

    def get_trajectory(
        self,
        *,
        example_id: str,
        replicate_id: str,
        view: str = "full",
    ) -> dict[str, Any]:
        """读取一个 example/replicate 的 Student 行为视图或完整轨迹。"""

        reference = (example_id, replicate_id)
        allowlist = self._trajectory_allowlist()
        if allowlist is not None and reference not in allowlist:
            raise ValueError(
                "Hypothesis Researcher may inspect only cited trajectories"
            )
        limit = self._access_limits.get("trajectory_reads")
        if (
            limit is not None
            and reference not in self._trajectory_reads
            and len(self._trajectory_reads) >= limit
        ):
            raise ValueError(
                "Failure Analyst trajectory evidence budget is exhausted. "
                "Submit the diagnosis using the trajectories already inspected."
            )
        try:
            record = self.rollouts[example_id][replicate_id]
        except KeyError as exc:
            raise KeyError(
                f"unknown Student trajectory: {example_id}/{replicate_id}"
            ) from exc
        if view == "full":
            if allowlist is not None:
                raise ValueError(
                    "Hypothesis Researcher may inspect only the behavior view"
                )
            self._trajectory_reads.add(reference)
            return record
        if view == "behavior":
            trajectory = _behavior_trajectory(
                record,
                case=self.cases.get(example_id),
                replicate_id=replicate_id,
            )
            if allowlist is not None:
                trajectory["example"].pop("golden_answer", None)
                trajectory["omitted"].append("golden answer")
            self._trajectory_reads.add(reference)
            return trajectory
        raise ValueError("Student trajectory view must be behavior or full")

    def set_trajectory_read_budget(self, limit: int) -> None:
        """限制当前角色可读取的唯一 Student 轨迹数量。"""

        if limit < 1:
            raise ValueError("trajectory read budget must be positive")
        self._access_limits["trajectory_reads"] = limit

    def restrict_to_evidence_refs(self, evidence_refs: list[str]) -> None:
        """把 Researcher 的证据读取范围冻结为 Analyst 引用集合。"""

        self._access_limits["trajectory_allowlist"] = {
            tuple(reference.split("/", maxsplit=1))
            for reference in evidence_refs
        }

    def _trajectory_allowlist(self) -> set[tuple[str, str]] | None:
        value = self._access_limits.get("trajectory_allowlist")
        return value if isinstance(value, set) else None

    def validate_evidence_refs(self, evidence_refs: list[str]) -> None:
        """验证终态证据引用都对应本次成功读取的完整轨迹 ID。"""

        inspected = {
            f"{example_id}/{replicate_id}"
            for example_id, replicate_id in self._trajectory_reads
        }
        missing = [
            reference
            for reference in evidence_refs
            if reference not in inspected
        ]
        if missing:
            raise ValueError(
                "evidence_refs were not inspected through "
                f"get_student_trajectory: {missing}"
            )

    def validate_allowed_evidence_inspected(self) -> None:
        """验证 Researcher 已读取 Analyst 引用的全部轨迹。"""

        allowlist = self._trajectory_allowlist()
        if allowlist is None:
            raise ValueError(
                "Hypothesis Researcher trajectory allowlist is unavailable"
            )
        missing = sorted(allowlist - self._trajectory_reads)
        if missing:
            references = [
                f"{example_id}/{replicate_id}"
                for example_id, replicate_id in missing
            ]
            raise ValueError(
                "Hypothesis Researcher must inspect every cited trajectory: "
                f"{references}"
            )

    def role_session_state(self) -> dict[str, Any]:
        """导出已经成功读取的轨迹引用。"""

        return {
            "trajectory_reads": [
                f"{example_id}/{replicate_id}"
                for example_id, replicate_id in sorted(self._trajectory_reads)
            ]
        }

    def restore_role_session_state(self, state: dict[str, Any]) -> None:
        """恢复并校验轨迹读取账本没有越过当前引用白名单。"""

        raw_reads = state.get("trajectory_reads")
        if not isinstance(raw_reads, list) or not all(
            isinstance(item, str) for item in raw_reads
        ):
            raise TypeError(
                "role session trajectory_reads must be a string list"
            )
        restored = {
            tuple(reference.split("/", maxsplit=1))
            for reference in raw_reads
        }
        if any(len(reference) != 2 for reference in restored):
            raise ValueError("invalid role session trajectory reference")
        allowlist = self._trajectory_allowlist()
        if allowlist is not None and not restored <= allowlist:
            raise ValueError(
                "role session trajectory reads exceed current evidence refs"
            )
        unknown = [
            f"{example_id}/{replicate_id}"
            for example_id, replicate_id in restored
            if replicate_id not in self.rollouts.get(example_id, {})
        ]
        if unknown:
            raise ValueError(
                f"role session contains unknown trajectory reads: {unknown}"
            )
        self._trajectory_reads.update(restored)

    def get_harness_manifest(self) -> dict[str, Any]:
        """读取当前 Student Harness manifest。"""

        if self.harness_manifest is None:
            raise ValueError("student_template_root was not configured")
        return self.harness_manifest

    def get_harness_component(
        self,
        *,
        category: str,
        component_id: str,
    ) -> dict[str, Any]:
        """读取 manifest 中一个组件的注册信息和入口文件。"""

        if self.student_template_root is None or self.harness_manifest is None:
            raise ValueError("student_template_root was not configured")
        plural = {
            "tool": "tools",
            "prompt": "prompt",
            "extension": "extensions",
        }.get(category)
        if plural is None:
            raise ValueError("category must be tool, prompt, or extension")
        raw_components = self.harness_manifest.get(plural)
        components = [raw_components] if plural == "prompt" else raw_components
        if not isinstance(components, list):
            raise ValueError(f"Harness manifest field '{plural}' is invalid")
        component = next(
            (
                item
                for item in components
                if isinstance(item, dict)
                and item.get("instance_id") == component_id
            ),
            None,
        )
        if component is None:
            raise KeyError(f"unknown Harness component: {category}/{component_id}")
        entrypoint = component.get("entrypoint")
        if not isinstance(entrypoint, str):
            raise ValueError("Harness component entrypoint must be a string")
        module_path = entrypoint.partition(":")[0]
        path = (self.student_template_root / module_path).resolve()
        root = self.student_template_root.resolve()
        if root not in path.parents or not path.is_file():
            raise ValueError(f"invalid Harness component path: {entrypoint}")
        return {
            "registration": component,
            "module_path": module_path,
            "source": path.read_text(encoding="utf-8"),
        }


def _manifest_instance_ids(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        str(item["instance_id"])
        for item in value
        if isinstance(item, dict) and item.get("instance_id")
    ]


def _replicate_executions(
    cases: Iterable[object],
) -> Iterator[dict[str, Any]]:
    for case in cases:
        if not isinstance(case, dict):
            continue
        replicates = case.get("replicates")
        if not isinstance(replicates, list):
            continue
        for replicate in replicates:
            if not isinstance(replicate, dict):
                continue
            execution = replicate.get("execution")
            if isinstance(execution, dict):
                yield execution


def _token_distribution(
    executions: list[dict[str, Any]],
    metric: str,
) -> dict[str, Any]:
    values = [
        value
        for execution in executions
        if isinstance(execution.get("tokens"), dict)
        and isinstance(
            value := execution["tokens"].get(metric),
            (int, float),
        )
    ]
    ordered = sorted(values)
    return {
        "covered_replicates": len(values),
        "coverage_rate": (
            len(values) / len(executions) if executions else None
        ),
        "mean": mean(values) if values else None,
        "p50": _nearest_rank(ordered, 0.5),
        "p95": _nearest_rank(ordered, 0.95),
        "max": max(values) if values else None,
    }


def _nearest_rank(
    ordered: list[int | float],
    quantile: float,
) -> int | float | None:
    if not ordered:
        return None
    return ordered[max(0, ceil(quantile * len(ordered)) - 1)]


def _case_cost_item(
    case: dict[str, Any],
    token_metric: str,
) -> dict[str, Any]:
    replicates = case.get("replicates")
    replicates = replicates if isinstance(replicates, list) else []
    values = []
    for replicate in replicates:
        if not isinstance(replicate, dict):
            continue
        execution = replicate.get("execution")
        execution = execution if isinstance(execution, dict) else {}
        tokens = execution.get("tokens")
        tokens = tokens if isinstance(tokens, dict) else {}
        value = tokens.get(token_metric)
        if isinstance(value, (int, float)):
            values.append(value)
    return {
        "example_id": case.get("example_id"),
        "question": case.get("question"),
        "stability": case.get("stability"),
        "success_rate": case.get("success_rate"),
        "covered_replicates": len(values),
        "replicate_count": len(replicates),
        "mean_tokens": mean(values) if values else None,
        "max_tokens": max(values) if values else None,
    }


@dataclass
class TrialEvidenceStore:
    """允许模型按引用读取 Intervention trial artifact。"""

    trials: dict[str, dict[str, Any]]
    _reads: set[str] = field(default_factory=set)

    @classmethod
    def load(cls, paths: list[Path]) -> "TrialEvidenceStore":
        """加载显式列出的 JSON trial，不扫描目录。"""

        trials: dict[str, dict[str, Any]] = {}
        for path in paths:
            resolved = path.resolve()
            payload = _trial_payload(_read_json_object(resolved))
            trial_ref = resolved.parent.name
            if trial_ref in trials:
                raise ValueError(f"duplicate trial reference: {trial_ref}")
            trials[trial_ref] = payload
        return cls(trials=trials)

    def initial_context(self) -> dict[str, Any]:
        """返回 trial 目录，不直接暴露完整轨迹。"""

        return {
            "trial_count": len(self.trials),
            "trial_refs": sorted(self.trials),
        }

    def list_trials(self) -> dict[str, Any]:
        """列出可读取 trial 的事实目录。"""

        return {
            "trial_count": len(self.trials),
            "items": [
                {
                    "trial_ref": trial_ref,
                    "intent": payload.get("intent"),
                    "worker_result": payload.get("worker_result"),
                    "source": _trial_source_selector(payload),
                    "phase_plan": payload.get("phase_plan"),
                    "activation_counts": payload.get(
                        "activation_counts"
                    ),
                    "phase_effects": payload.get("phase_effects"),
                    "comparison": payload.get("comparison"),
                }
                for trial_ref, payload in sorted(self.trials.items())
            ],
        }

    def get_trial(self, trial_ref: str) -> dict[str, Any]:
        """读取一个 trial 的完整 source/branch 轨迹和事实字段。"""

        try:
            payload = self.trials[trial_ref]
        except KeyError as exc:
            raise KeyError(f"unknown trial reference: {trial_ref}") from exc
        self._reads.add(trial_ref)
        return {
            "trial_ref": trial_ref,
            "intent": payload.get("intent"),
            "worker_result": payload.get("worker_result"),
            "source": {
                "selector": _trial_source_selector(payload),
                "run": _judgment_run(_load_trial_source_run(payload)),
            },
            "action": payload.get("action"),
            "phase_plan": payload.get("phase_plan"),
            "activation_budgets": payload.get("activation_budgets"),
            "activation_counts": payload.get("activation_counts"),
            "context_changes": payload.get("context_changes"),
            "phase_effects": payload.get("phase_effects"),
            "worker_trace": payload.get("worker_trace"),
            "branch_run": _judgment_run(payload.get("branch_run")),
            "run_scopes": {
                "source": "complete original rollout",
                "branch": "continuation from the selected prefix",
            },
            "comparison": payload.get("comparison"),
        }

    def bind_refs(self, trial_refs: list[str]) -> None:
        """确认角色输入与程序显式加载的 trial 集合一致。"""

        requested = set(trial_refs)
        available = set(self.trials)
        if requested != available:
            raise ValueError(
                "Trial Reviewer references must exactly match loaded "
                f"trial files: requested={sorted(requested)}, "
                f"available={sorted(available)}"
            )

    def validate_trial_review(self, review: TrialReview) -> None:
        """确认单条审阅引用正确且完整轨迹已被读取。"""

        self.validate_all_inspected()
        expected = tuple(self.trials)
        if expected != (review.trial_ref,):
            raise ValueError(
                "Trial Reviewer output must reference the loaded trial: "
                f"expected={list(expected)}, actual={review.trial_ref}"
            )

    def validate_all_inspected(self) -> None:
        """确认 Reviewer 在提交前读取了每条完整 trial 轨迹。"""

        missing = sorted(set(self.trials) - self._reads)
        if missing:
            raise ValueError(
                "Trial Reviewer must inspect the full trial through "
                f"get_trial_evidence before submitting: {missing}"
            )

    def role_session_state(self) -> dict[str, Any]:
        """导出 Reviewer 已读取的 trial 引用。"""

        return {"trial_reads": sorted(self._reads)}

    def restore_role_session_state(self, state: dict[str, Any]) -> None:
        """恢复已读 trial 账本，并拒绝当前资源之外的引用。"""

        raw_reads = state.get("trial_reads")
        if not isinstance(raw_reads, list) or not all(
            isinstance(item, str) for item in raw_reads
        ):
            raise TypeError("role session trial_reads must be a string list")
        restored = set(raw_reads)
        unknown = sorted(restored - set(self.trials))
        if unknown:
            raise ValueError(
                f"role session contains unknown trial reads: {unknown}"
            )
        self._reads.update(restored)


def _trial_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """把 Worker run artifact 投影为 Reviewer 使用的 trial 协议。"""

    resource_artifacts = payload.get("resource_artifacts")
    if not isinstance(resource_artifacts, dict):
        return payload
    trial = resource_artifacts.get("intervention_trial")
    if not isinstance(trial, dict):
        return payload
    role_input = payload.get("input")
    role_input = role_input if isinstance(role_input, dict) else {}
    output = payload.get("output")
    output = output if isinstance(output, dict) else {}
    return {
        **trial,
        "intent": role_input.get("trial_objective"),
        "worker_result": {
            key: output.get(key)
            for key in (
                "result_kind",
                "activated_phases",
                "modified_phases",
                "unmet_phases",
            )
            if key in output
        },
    }


def _trial_source_selector(payload: dict[str, Any]) -> dict[str, Any] | None:
    source = payload.get("source")
    if not isinstance(source, dict):
        return None
    return {
        key: value
        for key, value in source.items()
        if key not in {"rollout_file", "source_run"}
    }


def _load_trial_source_run(payload: dict[str, Any]) -> dict[str, Any] | None:
    source = payload.get("source")
    if not isinstance(source, dict):
        return None
    rollout_file = source.get("rollout_file")
    example_id = source.get("example_id")
    replicate_id = source.get("replicate_id")
    if not all(
        isinstance(value, str) and value
        for value in (rollout_file, example_id, replicate_id)
    ):
        return None
    record = load_rollout_record(
        Path(rollout_file),
        example_id,
        replicate_id,
    )
    run = record.get("run")
    return run if isinstance(run, dict) else None


def _judgment_run(run: object) -> dict[str, Any] | None:
    """保留完整 run，仅删除与证据判断无关的模型 usage 元数据。"""

    if not isinstance(run, dict):
        return None
    result = json.loads(json.dumps(run, ensure_ascii=False))
    trace = result.get("trace")
    if not isinstance(trace, list):
        return result
    for event in trace:
        if not isinstance(event, dict) or event.get("event_type") != "model_output":
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        metadata = payload.get("metadata")
        if isinstance(metadata, dict):
            metadata.pop("usage", None)
    return result


_BEHAVIOR_EVENT_TYPES = frozenset(
    {
        "model_output",
        "parsed_output",
        "tool_call",
        "tool_result",
        "tool_error",
        "hook_applied",
        "hook_error",
        "final_answer_candidate",
        "final_deferred",
        "final_answer",
        "invalid_output",
        "invalid_output_feedback",
        "max_steps_reached",
    }
)


def _behavior_trajectory(
    record: dict[str, Any],
    *,
    case: dict[str, Any] | None,
    replicate_id: str,
) -> dict[str, Any]:
    """投影 Student 决策文本与动作，省略重复 model input 和运行元数据。"""

    example = record.get("example")
    example = example if isinstance(example, dict) else {}
    run = record.get("run")
    run = run if isinstance(run, dict) else {}
    metadata = example.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    evaluation = _replicate_evaluation(case, replicate_id)
    events = [
        projected
        for event in run.get("trace", [])
        if isinstance(event, dict)
        and (projected := _project_behavior_event(event)) is not None
    ]
    return {
        "view": "behavior",
        "example": {
            "example_id": example.get("example_id"),
            "question": example.get("question") or run.get("question"),
            "golden_answer": (
                case.get("golden_answer")
                if isinstance(case, dict)
                else example.get("answer")
            ),
            "task_type": metadata.get("type"),
            "difficulty": metadata.get("level"),
            "filter_status": metadata.get("filter_status"),
        },
        "replicate": {
            "replicate_id": replicate_id,
            "evaluation": evaluation,
        },
        "run": {
            "status": run.get("status"),
            "answer": run.get("answer"),
            "error": run.get("error"),
        },
        "events": events,
        "omitted": [
            "repeated model_input messages",
            "provider usage metadata",
            "rollout provenance and filesystem paths",
            "unselected internal trace events",
        ],
    }


def _replicate_evaluation(
    case: dict[str, Any] | None,
    replicate_id: str,
) -> dict[str, Any] | None:
    if not isinstance(case, dict):
        return None
    replicates = case.get("replicates")
    if not isinstance(replicates, list):
        return None
    replicate = next(
        (
            item
            for item in replicates
            if isinstance(item, dict)
            and item.get("replicate_id") == replicate_id
        ),
        None,
    )
    if replicate is None:
        return None
    static = replicate.get("static")
    static = static if isinstance(static, dict) else {}
    teacher = replicate.get("teacher")
    teacher = teacher if isinstance(teacher, dict) else {}
    execution = replicate.get("execution")
    execution = execution if isinstance(execution, dict) else {}
    return {
        "score": replicate.get("score"),
        "score_source": replicate.get("score_source"),
        "predicted_answer": replicate.get("predicted_answer"),
        "run_status": replicate.get("run_status"),
        "runner_error": replicate.get("runner_error"),
        "static_decision": static.get("decision"),
        "static_metrics": static.get("metrics"),
        "teacher_score": teacher.get("score"),
        "teacher_error": teacher.get("error"),
        "execution": {
            key: execution.get(key)
            for key in (
                "steps",
                "model_calls",
                "tool_calls",
                "retriever_errors",
                "duplicate_queries",
            )
        },
    }


def _project_behavior_event(event: dict[str, Any]) -> dict[str, Any] | None:
    event_type = event.get("event_type")
    if event_type not in _BEHAVIOR_EVENT_TYPES:
        return None
    payload = event.get("payload")
    payload = payload if isinstance(payload, dict) else {}
    if event_type == "model_output":
        projected_payload = {"raw_output": payload.get("raw_output")}
        metadata = payload.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        native_reasoning = next(
            (
                metadata[key]
                for key in ("reasoning_content", "reasoning", "thinking")
                if isinstance(metadata.get(key), str) and metadata[key]
            ),
            None,
        )
        if native_reasoning is not None:
            projected_payload["native_reasoning"] = native_reasoning
    else:
        projected_payload = payload
    return {
        "index": event.get("index"),
        "step": event.get("step"),
        "event_type": event_type,
        "payload": projected_payload,
    }


class MechanismDraftStore:
    """一次 Distiller run 内由工具渐进构造的机制草稿。"""

    def __init__(self) -> None:
        self._drafts: dict[str, dict[str, Any]] = {}
        self._validated: dict[str, MechanismSpec] = {}

    def create(
        self,
        *,
        goal: str,
    ) -> str:
        """创建尚未添加 phase rule 的机制草稿。"""

        draft_id = f"mechanism_draft_{len(self._drafts) + 1:03d}"
        self._drafts[draft_id] = {
            "goal": goal,
            "phase_rules": [],
        }
        return draft_id

    def add_phase(
        self,
        *,
        draft_id: str,
        phase: str,
        trigger_condition: str,
        decision_inputs: list[str],
        decision_evaluator: DecisionEvaluator,
        action: str,
        activation_budget: int,
    ) -> None:
        """向草稿追加一个 phase 局部判断、动作和预算。"""

        draft = self._require_draft(draft_id)
        rules = draft["phase_rules"]
        if not isinstance(rules, list):
            raise TypeError("mechanism phase_rules must be a list")
        if any(
            isinstance(rule, dict) and rule.get("phase") == phase
            for rule in rules
        ):
            raise ValueError(f"mechanism phase already exists: {phase}")
        rules.append(
            {
                "phase": phase,
                "trigger_condition": trigger_condition,
                "decision_inputs": list(decision_inputs),
                "decision_evaluator": decision_evaluator,
                "action": action,
                "activation_budget": activation_budget,
            }
        )

    def complete(
        self,
        *,
        draft_id: str,
        behavioral_pseudocode: str,
        state_scope: str,
        fallback: str,
        expected_behavior: str,
        required_capabilities: list[str] | None = None,
        prohibited_behaviors: list[str] | None = None,
        observability: list[str] | None = None,
        known_limits: list[str] | None = None,
    ) -> None:
        """补充动作、状态和回退语义。"""

        draft = self._require_draft(draft_id)
        draft.update(
            {
                "behavioral_pseudocode": behavioral_pseudocode,
                "state_scope": state_scope,
                "fallback": fallback,
                "expected_behavior": expected_behavior,
                "required_capabilities": list(required_capabilities or []),
                "prohibited_behaviors": list(prohibited_behaviors or []),
                "observability": list(observability or []),
                "known_limits": list(known_limits or []),
            }
        )

    def set_constraints(
        self,
        *,
        draft_id: str,
        required_capabilities: list[str],
        prohibited_behaviors: list[str],
        observability: list[str],
        known_limits: list[str],
    ) -> None:
        """补充机制的审计信号与已知能力边界。"""

        draft = self._require_draft(draft_id)
        draft.update(
            {
                "required_capabilities": list(required_capabilities),
                "prohibited_behaviors": list(prohibited_behaviors),
                "observability": list(observability),
                "known_limits": list(known_limits),
            }
        )

    def validate(self, *, draft_id: str, evidence_refs: list[str]) -> str:
        """验证完整草稿并返回稳定的本次运行引用。"""

        draft = dict(self._require_draft(draft_id))
        draft["evidence_refs"] = list(evidence_refs)
        mechanism = MechanismSpec.model_validate(draft)
        mechanism_ref = f"mechanism_{len(self._validated) + 1:03d}"
        self._validated[mechanism_ref] = mechanism
        return mechanism_ref

    def resolve(self, mechanism_ref: str) -> MechanismSpec:
        """解析已经验证的机制引用。"""

        try:
            return self._validated[mechanism_ref]
        except KeyError as exc:
            raise KeyError(f"unknown validated mechanism: {mechanism_ref}") from exc

    def summary(self) -> dict[str, Any]:
        """返回草稿数量，不把草稿内容提前放入 Prompt。"""

        return {
            "draft_count": len(self._drafts),
            "validated_count": len(self._validated),
        }

    def validated_payloads(self) -> dict[str, dict[str, Any]]:
        """返回适合写入运行 artifact 的已验证机制。"""

        return {
            key: value.model_dump(mode="json")
            for key, value in self._validated.items()
        }

    def _require_draft(self, draft_id: str) -> dict[str, Any]:
        try:
            return self._drafts[draft_id]
        except KeyError as exc:
            raise KeyError(f"unknown mechanism draft: {draft_id}") from exc


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"JSON artifact does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON artifact {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise TypeError(f"JSON artifact must contain an object: {path}")
    return payload


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"JSONL artifact does not exist: {path}") from exc
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"invalid JSONL record {path}:{line_number}: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise TypeError(f"JSONL record must be an object: {path}:{line_number}")
        rows.append(payload)
    return rows


def _required_string(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"artifact field '{field}' must be a non-empty string")
    return value
