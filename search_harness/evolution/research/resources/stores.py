"""Intervention、Compiler 与 Candidate Review 的受控运行资源。"""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..intervention.bridge import (
    InterventionContext,
)
from ..intervention.prefix import (
    PrefixPromptBuilder,
    build_prefix_timeline,
    load_reconstructed_prefix,
    load_rollout_record,
    resolve_prefix_boundary,
)
from ..intervention.types import (
    InterventionAction,
    PrefixSelector,
)
from search_harness.framework import (
    Agent,
    BaseHook,
    Harness,
    HookPipeline,
    LoopRunner,
    ToolExecutor,
    assemble_harness_components,
)
from search_harness.integrations.openai_compatible import (
    OpenAICompatibleConfig,
    OpenAICompatibleModel,
    ProfiledHookModelBackend,
)
from search_harness.evolution.versioning import (
    CandidateWorkspace,
    HarnessSnapshot,
    HarnessValidator,
)

from ..mechanism.review import review_compiler_candidate
from ..roles.contracts import InterventionWorkerInput
from ..mechanism.hook_api import (
    list_hook_api_symbols,
    query_hook_api_reference,
)
from ..mechanism.hook_authoring import get_hook_authoring_guide


COMPILER_EXACT_QUERY_BUDGET = 12


class InterventionResourceConfig(BaseModel):
    """一个 Worker 单分支试验的运行资源。"""

    model_config = ConfigDict(extra="forbid")

    rollout_file: Path
    student_template_root: Path
    env_file: Path = Path(".env")
    student_max_steps: int = Field(default=20, ge=1)


class CompilerResourceConfig(BaseModel):
    """一个 Compiler 内存候选的 Parent Harness。"""

    model_config = ConfigDict(extra="forbid")

    parent_template_root: Path
    env_file: Path = Path(".env")
    continuation_candidate_file: Path | None = None


class CandidateReviewResourceConfig(BaseModel):
    """Candidate Reviewer 的 incumbent/candidate 配对证据。"""

    model_config = ConfigDict(extra="forbid")

    incumbent_report_dir: Path
    candidate_report_dir: Path
    incumbent_rollout_file: Path | None = None
    candidate_rollout_file: Path | None = None
    incumbent_template_root: Path | None = None
    candidate_template_root: Path | None = None


@dataclass
class InterventionBranchStore:
    """在指定可恢复 prefix 上执行一次 Teacher 选择的 Student 分支。"""

    config: InterventionResourceConfig
    task: InterventionWorkerInput | None = None
    trials: list[dict[str, Any]] = field(default_factory=list)

    def bind(self, task: InterventionWorkerInput) -> None:
        """绑定当前 Worker 的冻结假设和分支选择。"""

        self.task = task
        record = self._record()
        resolve_prefix_boundary(record, task.prefix_id)

    def initial_context(self) -> dict[str, Any]:
        """返回不包含问题答案的运行能力摘要。"""

        return {
            "rollout_file": str(self.config.rollout_file.resolve()),
            "student_template_root": str(self.config.student_template_root.resolve()),
            "student_max_steps": self.config.student_max_steps,
            "student_model_role": "student",
            "single_action_per_trial": True,
        }

    def timeline(self) -> dict[str, Any]:
        """列出当前 example/replicate 的可恢复模型上下文边界。"""

        task = self._task()
        timeline = build_prefix_timeline(self._record())
        return {
            "example_id": task.example_id,
            "replicate_id": task.replicate_id,
            "selected_prefix_id": task.prefix_id,
            "items": timeline,
        }

    def inspect_selected_prefix(self) -> dict[str, Any]:
        """读取选定 prefix 的 Student 可见上下文和活跃 stage。"""

        prefix = self._prefix()
        return {
            "selector": {
                "example_id": prefix.selector.example_id,
                "replicate_id": prefix.selector.replicate_id,
                "step": prefix.selector.step,
                "phase": prefix.selector.phase,
            },
            "question": (
                prefix.example.get("question")
                or prefix.source_run.get("question")
            ),
            "model_input": prefix.model_input.to_dict(),
            "active_stage": _jsonable(prefix.stage_values),
        }

    def run_branch(
        self,
        *,
        action: str,
        content: str | None,
        rationale: str,
    ) -> dict[str, Any]:
        """应用一个动作并调用 Student 从 prefix 继续生成。"""

        task = self._task()
        normalized_content = content.strip() if isinstance(content, str) else None
        selected_action = _intervention_action(
            action=action,
            content=normalized_content,
            rationale=rationale,
        )
        prefix = self._prefix()
        intervention = InterventionContext(prefix)
        intervention.apply_initial(selected_action)

        model_config = OpenAICompatibleConfig.from_env(
            env_file=self.config.env_file,
            prefix="STUDENT",
        )
        model = OpenAICompatibleModel(model_config)
        components = assemble_harness_components(
            self.config.student_template_root,
            env_file=self.config.env_file,
        )
        hooks = _student_hooks(components.extensions)
        hook_model_backend = (
            ProfiledHookModelBackend(
                env_file=self.config.env_file,
                seed=model_config.seed,
            )
            if any(hook.model_profiles for hook in hooks)
            else None
        )
        harness = Harness(
            prompt=PrefixPromptBuilder(intervention.model_input),
            output=components.output,
            tool_executor=ToolExecutor(components.tools.tools),
            lifecycle=HookPipeline(hooks, model_backend=hook_model_backend),
        )
        question = str(
            prefix.example.get("question")
            or prefix.source_run.get("question")
            or ""
        )
        if not question.strip():
            raise ValueError("source rollout question is missing")
        branch = LoopRunner(max_steps=self.config.student_max_steps).run(
            Agent(harness=harness, model=model),
            question,
        ).to_dict()
        artifact = {
            "trial_id": f"trial_{len(self.trials) + 1:03d}",
            "source": {
                "rollout_file": str(self.config.rollout_file.resolve()),
                "example_id": task.example_id,
                "replicate_id": task.replicate_id,
                "prefix_id": task.prefix_id,
                "step": prefix.selector.step,
                "phase": prefix.selector.phase,
                "source_status": prefix.source_run.get("status"),
                "source_answer": prefix.source_run.get("answer"),
            },
            "action": {
                "action": action,
                "content": normalized_content,
                "rationale": rationale.strip(),
            },
            "context_changes": list(intervention.changes),
            "student_model": {
                "role": "student",
                **model_config.provenance(),
            },
            "branch_run": branch,
            "comparison": {
                "source": _run_summary(prefix.source_run),
                "branch": _run_summary(branch),
            },
        }
        self.trials.append(artifact)
        return {
            "trial_id": artifact["trial_id"],
            "action": artifact["action"],
            "comparison": artifact["comparison"],
        }

    def validate_result(
        self,
        *,
        action: str,
        content: str | None,
        rationale: str,
    ) -> None:
        """确认 Worker 最终输出对应实际执行的最新分支。"""

        if not self.trials:
            raise ValueError(
                "Intervention Worker must run one Student branch before submitting"
            )
        expected = self.trials[-1]["action"]
        actual = {
            "action": action,
            "content": content,
            "rationale": rationale,
        }
        if actual != expected:
            raise ValueError(
                "Intervention Worker result does not match the executed branch action"
            )

    def artifact(self) -> dict[str, Any] | None:
        return self.trials[-1] if self.trials else None

    def _task(self) -> InterventionWorkerInput:
        if self.task is None:
            raise RuntimeError("Intervention Worker input is not bound")
        return self.task

    def _record(self) -> dict[str, Any]:
        task = self._task()
        return load_rollout_record(
            self.config.rollout_file,
            task.example_id,
            task.replicate_id,
        )

    def _prefix(self):
        task = self._task()
        boundary = resolve_prefix_boundary(self._record(), task.prefix_id)
        return load_reconstructed_prefix(
            PrefixSelector(
                rollout_file=self.config.rollout_file,
                example_id=task.example_id,
                replicate_id=task.replicate_id,
                step=int(boundary["step"]),
                phase=str(boundary["phase"]),
            )
        )


@dataclass
class CompilerWorkspaceStore:
    """一个只在当前 Compiler run 内存在的内存候选。"""

    config: CompilerResourceConfig
    workspace: CandidateWorkspace
    validator: HarnessValidator = field(default_factory=HarnessValidator)
    last_validation: dict[str, Any] | None = None
    submitted: dict[str, dict[str, Any]] = field(default_factory=dict)
    packet_symbols: frozenset[str] | None = None
    packet_topics: frozenset[str] | None = None
    queried_symbols: set[str] = field(default_factory=set)
    prior_queried_symbols: frozenset[str] = frozenset()
    continuation: dict[str, Any] | None = None

    @classmethod
    def load(cls, config: CompilerResourceConfig) -> "CompilerWorkspaceStore":
        parent = HarnessSnapshot.from_directory(
            config.parent_template_root,
            version_id="parent",
        )
        workspace = CandidateWorkspace(parent)
        continuation = None
        prior_queried_symbols: frozenset[str] = frozenset()
        if config.continuation_candidate_file is not None:
            candidate = _read_json(config.continuation_candidate_file)
            parent_digest = candidate.get("parent_digest")
            if parent_digest != parent.digest:
                raise ValueError(
                    "Compiler continuation parent digest does not match "
                    "the current Accepted Template"
                )
            changed_files = candidate.get("changed_files")
            if not isinstance(changed_files, dict) or not changed_files:
                raise ValueError(
                    "Compiler continuation must contain changed_files"
                )
            with workspace.transaction():
                for path, content in changed_files.items():
                    if not isinstance(path, str):
                        raise TypeError(
                            "Compiler continuation paths must be strings"
                        )
                    if content is None:
                        workspace.delete(path)
                    elif isinstance(content, str):
                        workspace.write_text(path, content)
                    else:
                        raise TypeError(
                            "Compiler continuation file content must be a "
                            "string or null"
                        )
            candidate_digest = candidate.get("candidate_digest")
            if candidate_digest != workspace.digest:
                raise ValueError(
                    "Compiler continuation candidate digest does not match "
                    "its materialized workspace"
                )
            queried = candidate.get("queried_symbols", [])
            if not isinstance(queried, list) or not all(
                isinstance(item, str) and item.strip() for item in queried
            ):
                raise TypeError(
                    "Compiler continuation queried_symbols must be strings"
                )
            prior_queried_symbols = frozenset(queried)
            continuation = {
                "candidate_digest": workspace.digest,
                "changed_paths": [str(path) for path in workspace.changed_paths],
                "summary": candidate.get("summary"),
                "queried_symbols": sorted(prior_queried_symbols),
            }
        return cls(
            config=config,
            workspace=workspace,
            prior_queried_symbols=prior_queried_symbols,
            continuation=continuation,
        )

    def initial_context(self) -> dict[str, Any]:
        manifest = json.loads(self.workspace.read_text("harness.json"))
        policy = json.loads(self.workspace.read_text("evolution.json"))
        continuation_changed_files = None
        if self.continuation is not None:
            continuation_changed_files = {
                str(path): (
                    self.workspace.read_text(path)
                    if self.workspace.exists(path)
                    else None
                )
                for path in self.workspace.changed_paths
            }
        return {
            "parent_template_root": str(self.config.parent_template_root.resolve()),
            "parent_digest": self.workspace.parent.digest,
            "harness_id": manifest.get("harness_id"),
            "file_count": len(self.workspace.parent.files),
            "fixed_components": _fixed_component_ids(manifest, policy),
            "manifest": manifest,
            "evolution_policy": policy,
            "extension_index": _extension_index(
                manifest=manifest,
                policy=policy,
                workspace=self.workspace,
            ),
            "continuation": self.continuation,
            "continuation_changed_files": continuation_changed_files,
            "exact_api_query": {
                "unique_symbol_budget": COMPILER_EXACT_QUERY_BUDGET,
                "scope": (
                    "Runtime Input Topics, exact public symbols, and unknown-query "
                    "suggestions; only successfully resolved symbols absent from the "
                    "capability_packet consume budget"
                ),
            },
        }

    def bind_capability_packet(self, packet: dict[str, Any]) -> None:
        """绑定本次 packet，并初始化受控 exact-query 账本。"""

        contracts = packet.get("contracts")
        if not isinstance(contracts, list):
            raise TypeError("Compiler capability packet contracts must be an array")
        self.packet_symbols = frozenset(_contract_symbols(contracts))
        documents = packet.get("runtime_input_documents", [])
        self.packet_topics = frozenset(
            str(item["runtime_input_id"])
            for item in documents
            if isinstance(item, dict) and item.get("runtime_input_id")
        )
        self.queried_symbols.clear()

    def list_files(self) -> dict[str, Any]:
        files = self.workspace.materialized_files()
        return {
            "revision": self.workspace.revision,
            "items": [
                {"path": str(path), "bytes": len(content)}
                for path, content in sorted(files.items(), key=lambda item: str(item[0]))
            ],
        }

    def read_file(self, path: str) -> dict[str, Any]:
        return {"path": path, "content": self.workspace.read_text(path)}

    def authoring_guide(self, topic: str) -> dict[str, Any]:
        return get_hook_authoring_guide(topic)

    def list_hook_api(
        self,
        *,
        category: str,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        """列出新版 Compiler 可依赖的公开 Hook API。"""

        return list_hook_api_symbols(
            category=category,
            page=page,
            page_size=page_size,
        )

    def query_hook_api(self, symbol: str) -> dict[str, Any]:
        """查询 Runtime Input Topic 或公开 symbol，并为未知项返回建议。"""

        if self.packet_symbols is None:
            raise RuntimeError(
                "Compiler capability packet must be bound before API queries"
            )
        normalized = symbol.strip()
        if not normalized:
            return {"status": "rejected", "reason": "empty_query"}
        result = query_hook_api_reference(normalized)
        if result.get("status") != "resolved":
            return {
                **result,
                "remaining_unique_queries": (
                    COMPILER_EXACT_QUERY_BUDGET - len(self.queried_symbols)
                ),
            }
        if result.get("query_kind") == "runtime_input_topic":
            return {
                **result,
                "source": (
                    "capability_packet"
                    if self.packet_topics is not None
                    and normalized in self.packet_topics
                    else "runtime_input_registry"
                ),
                "remaining_unique_queries": (
                    COMPILER_EXACT_QUERY_BUDGET - len(self.queried_symbols)
                ),
            }
        if normalized in self.packet_symbols:
            return {
                **result,
                "source": "capability_packet",
                "remaining_unique_queries": (
                    COMPILER_EXACT_QUERY_BUDGET - len(self.queried_symbols)
                ),
            }
        if normalized in self.prior_queried_symbols:
            return {
                **result,
                "source": "continuation_query",
                "remaining_unique_queries": (
                    COMPILER_EXACT_QUERY_BUDGET - len(self.queried_symbols)
                ),
            }
        if normalized not in self.queried_symbols:
            if len(self.queried_symbols) >= COMPILER_EXACT_QUERY_BUDGET:
                return {
                    "status": "rejected",
                    "reason": "query_budget_exhausted",
                    "query": normalized,
                    "remaining_unique_queries": 0,
                }
            self.queried_symbols.add(normalized)
        return {
            **result,
            "source": "exact_query",
            "remaining_unique_queries": (
                COMPILER_EXACT_QUERY_BUDGET - len(self.queried_symbols)
            ),
        }

    def write_file(self, *, path: str, content: str) -> dict[str, Any]:
        self.workspace.write_text(path, content)
        self.last_validation = None
        return {
            "revision": self.workspace.revision,
            "changed_paths": [str(item) for item in self.workspace.changed_paths],
        }

    def delete_file(self, *, path: str) -> dict[str, Any]:
        self.workspace.delete(path)
        self.last_validation = None
        return {
            "revision": self.workspace.revision,
            "changed_paths": [str(item) for item in self.workspace.changed_paths],
        }

    def diff(self) -> dict[str, Any]:
        parent = self.workspace.parent.files
        candidate = self.workspace.materialized_files()
        changes = []
        for path in sorted(set(parent) | set(candidate), key=str):
            before = parent.get(path)
            after = candidate.get(path)
            if before == after:
                continue
            changes.append(
                {
                    "path": str(path),
                    "operation": (
                        "add" if before is None else "delete" if after is None else "modify"
                    ),
                    "diff": _text_diff(path, before, after),
                }
            )
        return {
            "revision": self.workspace.revision,
            "candidate_digest": self.workspace.digest,
            "changes": changes,
        }

    def validate(self) -> dict[str, Any]:
        report = self.validator.validate(
            self.workspace,
            env_file=self.config.env_file,
        )
        payload = {
            "passed": report.passed,
            "parent_version": report.parent_version,
            "revision": report.revision,
            "candidate_digest": report.candidate_digest,
            "added_paths": list(report.added_paths),
            "modified_paths": list(report.modified_paths),
            "removed_paths": list(report.removed_paths),
            "errors": list(report.errors),
        }
        self.last_validation = payload
        return payload

    def submit(self, *, summary: str) -> dict[str, Any]:
        if not summary.strip():
            raise ValueError("candidate summary must not be empty")
        validation = self.last_validation
        if validation is None or not validation["passed"]:
            raise ValueError("candidate must pass validation before submission")
        if validation["revision"] != self.workspace.revision:
            raise ValueError("candidate changed after its last validation")
        if not self.workspace.changed_paths:
            raise ValueError("candidate has no changes")
        candidate_ref = f"candidate_{len(self.submitted) + 1:03d}"
        self.submitted[candidate_ref] = {
            "candidate_ref": candidate_ref,
            "summary": summary.strip(),
            "parent_digest": self.workspace.parent.digest,
            "candidate_digest": self.workspace.digest,
            "revision": self.workspace.revision,
            "validation": dict(validation),
            "diff": self.diff(),
            "changed_files": {
                str(path): (
                    self.workspace.read_text(path)
                    if self.workspace.exists(path)
                    else None
                )
                for path in self.workspace.changed_paths
            },
            "queried_symbols": sorted(
                self.prior_queried_symbols | self.queried_symbols
            ),
        }
        return {
            "candidate_ref": candidate_ref,
            "candidate_digest": self.workspace.digest,
            "changed_paths": [str(path) for path in self.workspace.changed_paths],
        }

    def finalize(self, *, summary: str) -> dict[str, Any]:
        """Validate and freeze the exact revision, returning compact model feedback."""

        if not summary.strip():
            raise ValueError("candidate summary must not be empty")
        if (
            self.continuation is not None
            and self.workspace.digest
            == self.continuation["candidate_digest"]
        ):
            return {
                "status": "repair_required",
                "revision": self.workspace.revision,
                "candidate_digest": self.workspace.digest,
                "changed_paths": [
                    str(path) for path in self.workspace.changed_paths
                ],
                "errors": [
                    "The continued Candidate is byte-for-byte identical to "
                    "the rejected revision. Modify the workspace to satisfy "
                    "the supplied feedback, or return a non-submission "
                    "Compiler decision with an exact next_obligation."
                ],
            }
        diff = self.diff()
        review_errors = review_compiler_candidate(self.workspace)
        validation = self.validate()
        changed_paths = [item["path"] for item in diff["changes"]]
        errors = [*review_errors, *validation["errors"]]
        if errors:
            return {
                "status": "repair_required",
                "revision": validation["revision"],
                "candidate_digest": validation["candidate_digest"],
                "changed_paths": changed_paths,
                "errors": errors,
            }
        submitted = self.submit(summary=summary)
        return {
            "status": "submitted",
            "candidate_ref": submitted["candidate_ref"],
            "candidate_digest": submitted["candidate_digest"],
            "changed_paths": submitted["changed_paths"],
            "validation_passed": True,
        }

    def resolve(self, candidate_ref: str) -> dict[str, Any]:
        try:
            return self.submitted[candidate_ref]
        except KeyError as exc:
            raise KeyError(f"unknown submitted candidate: {candidate_ref}") from exc

    def artifact(self) -> dict[str, Any] | None:
        if not self.submitted:
            return None
        return self.submitted[f"candidate_{len(self.submitted):03d}"]


def _contract_symbols(contracts: list[Any]) -> set[str]:
    """递归收集 packet 已公开的顶层和成员符号。"""

    symbols: set[str] = set()
    pending = list(contracts)
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            symbol = value.get("symbol")
            if isinstance(symbol, str) and symbol.strip():
                symbols.add(symbol.strip())
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)
    return symbols


def _query_rejection(symbol: str, reason: str) -> dict[str, Any]:
    """返回不会重新展开契约的紧凑查询拒绝结果。"""

    return {
        "status": "rejected",
        "reason": reason,
        "symbol": symbol,
    }


@dataclass
class CandidateComparisonStore:
    """Incumbent 与 candidate evaluation 的只读配对视图。"""

    config: CandidateReviewResourceConfig
    incumbent_summary: dict[str, Any]
    candidate_summary: dict[str, Any]
    incumbent_cases: dict[str, dict[str, Any]]
    candidate_cases: dict[str, dict[str, Any]]
    incumbent_rollouts: dict[tuple[str, str], dict[str, Any]]
    candidate_rollouts: dict[tuple[str, str], dict[str, Any]]
    inspected_trajectories: set[tuple[str, str]] = field(default_factory=set)

    @classmethod
    def load(
        cls,
        config: CandidateReviewResourceConfig,
    ) -> "CandidateComparisonStore":
        incumbent_summary, incumbent_cases = _load_report(
            config.incumbent_report_dir
        )
        candidate_summary, candidate_cases = _load_report(
            config.candidate_report_dir
        )
        if set(incumbent_cases) != set(candidate_cases):
            raise ValueError(
                "incumbent and candidate reports contain different example IDs"
            )
        incumbent_rollout = _resolve_rollout(
            config.incumbent_rollout_file,
            incumbent_summary,
            config.incumbent_report_dir,
        )
        candidate_rollout = _resolve_rollout(
            config.candidate_rollout_file,
            candidate_summary,
            config.candidate_report_dir,
        )
        return cls(
            config=config,
            incumbent_summary=incumbent_summary,
            candidate_summary=candidate_summary,
            incumbent_cases=incumbent_cases,
            candidate_cases=candidate_cases,
            incumbent_rollouts=_load_rollout_index(incumbent_rollout),
            candidate_rollouts=_load_rollout_index(candidate_rollout),
        )

    def initial_context(self) -> dict[str, Any]:
        changes = self._changes()
        counts = {
            name: sum(1 for item in changes if item["change"] == name)
            for name in ("improved", "regressed", "unchanged")
        }
        return {
            "example_count": len(changes),
            "incumbent_metrics": self.incumbent_summary.get("metrics"),
            "candidate_metrics": self.candidate_summary.get("metrics"),
            "paired_change_counts": counts,
            "harness_diff_available": (
                self.config.incumbent_template_root is not None
                and self.config.candidate_template_root is not None
            ),
        }

    def list_changes(
        self,
        *,
        page: int,
        page_size: int,
        change: str,
    ) -> dict[str, Any]:
        selected = [
            item
            for item in self._changes()
            if change == "any" or item["change"] == change
        ]
        start = (page - 1) * page_size
        return {
            "page": page,
            "page_size": page_size,
            "total_items": len(selected),
            "total_pages": max(1, (len(selected) + page_size - 1) // page_size),
            "items": selected[start : start + page_size],
        }

    def get_case(self, example_id: str) -> dict[str, Any]:
        try:
            incumbent = self.incumbent_cases[example_id]
            candidate = self.candidate_cases[example_id]
        except KeyError as exc:
            raise KeyError(f"unknown comparison example_id: {example_id}") from exc
        return {
            "example_id": example_id,
            "question": incumbent.get("question"),
            "incumbent": _case_projection(incumbent),
            "candidate": _case_projection(candidate),
        }

    def get_paired_trajectory(
        self,
        *,
        example_id: str,
        replicate_id: str,
    ) -> dict[str, Any]:
        key = (example_id, replicate_id)
        try:
            incumbent = self.incumbent_rollouts[key]
            candidate = self.candidate_rollouts[key]
        except KeyError as exc:
            raise KeyError(
                f"unknown paired trajectory: {example_id}/{replicate_id}"
            ) from exc
        self.inspected_trajectories.add(key)
        return {
            "example_id": example_id,
            "replicate_id": replicate_id,
            "incumbent": _trajectory_projection(incumbent),
            "candidate": _trajectory_projection(candidate),
        }

    def validate_review(self) -> None:
        """要求 promotion 建议核查可用的 gain/loss 成对轨迹。"""

        if not self.inspected_trajectories:
            raise ValueError(
                "Candidate Reviewer must inspect at least one paired Student "
                "trajectory before submitting"
            )
        changes = self._changes()
        inspected_examples = {
            example_id for example_id, _ in self.inspected_trajectories
        }
        for change in ("improved", "regressed"):
            available = {
                str(item["example_id"])
                for item in changes
                if item["change"] == change
            }
            if available and not inspected_examples.intersection(available):
                raise ValueError(
                    "Candidate Reviewer must inspect at least one paired "
                    f"{change} Student trajectory before submitting"
                )

    def harness_diff(self) -> dict[str, Any]:
        incumbent_root = self.config.incumbent_template_root
        candidate_root = self.config.candidate_template_root
        if incumbent_root is None or candidate_root is None:
            return {
                "available": False,
                "reason": "candidate Harness roots were not configured",
                "changes": [],
            }
        incumbent = HarnessSnapshot.from_directory(incumbent_root)
        candidate = HarnessSnapshot.from_directory(candidate_root)
        changes = []
        for path in sorted(set(incumbent.files) | set(candidate.files), key=str):
            before = incumbent.files.get(path)
            after = candidate.files.get(path)
            if before == after:
                continue
            changes.append(
                {
                    "path": str(path),
                    "operation": (
                        "add" if before is None else "delete" if after is None else "modify"
                    ),
                    "diff": _text_diff(path, before, after),
                }
            )
        return {
            "available": True,
            "incumbent_digest": incumbent.digest,
            "candidate_digest": candidate.digest,
            "changes": changes,
        }

    def _changes(self) -> list[dict[str, Any]]:
        items = []
        for example_id in sorted(self.incumbent_cases):
            incumbent = self.incumbent_cases[example_id]
            candidate = self.candidate_cases[example_id]
            before = _success_rate(incumbent)
            after = _success_rate(candidate)
            delta = after - before
            change: Literal["improved", "regressed", "unchanged"]
            if delta > 0:
                change = "improved"
            elif delta < 0:
                change = "regressed"
            else:
                change = "unchanged"
            items.append(
                {
                    "example_id": example_id,
                    "question": incumbent.get("question"),
                    "change": change,
                    "incumbent_success_rate": before,
                    "candidate_success_rate": after,
                    "success_rate_delta": delta,
                    "incumbent_status": incumbent.get("run_status"),
                    "candidate_status": candidate.get("run_status"),
                }
            )
        return items


def _intervention_action(
    *,
    action: str,
    content: str | None,
    rationale: str,
) -> InterventionAction:
    if not rationale.strip():
        raise ValueError("intervention rationale must not be empty")
    if action == "no_op":
        if content is not None:
            raise ValueError("no_op must not include content")
        return InterventionAction(
            kind="continue_without_change",
            reason=rationale.strip(),
        )
    if not content:
        raise ValueError(f"{action} requires non-empty content")
    if action in {"append_user_message", "append_system_message"}:
        return InterventionAction(
            kind="append_context_message",
            payload={
                "role": (
                    "user" if action == "append_user_message" else "system"
                ),
                "content": content,
                "persistence": "next_generation",
            },
            reason=rationale.strip(),
        )
    if action == "replace_system_instruction":
        return InterventionAction(
            kind="replace_model_input",
            payload={"system_instruction": content, "user_instruction": ""},
            reason=rationale.strip(),
        )
    if action == "defer_final_answer":
        return InterventionAction(
            kind="replace_stage_value",
            payload={
                "key": "final_decision",
                "value": {"action": "defer", "feedback": content},
            },
            reason=rationale.strip(),
        )
    raise ValueError(f"unsupported intervention action: {action}")


def _run_summary(run: dict[str, Any]) -> dict[str, Any]:
    trace = run.get("trace")
    events = trace if isinstance(trace, list) else []
    return {
        "status": run.get("status"),
        "answer": run.get("answer"),
        "error": run.get("error"),
        "model_calls": sum(
            1 for event in events if event.get("event_type") == "model_output"
        ),
        "tool_calls": sum(
            1 for event in events if event.get("event_type") == "tool_call"
        ),
    }


def _fixed_component_ids(
    manifest: dict[str, Any],
    policy: dict[str, Any],
) -> list[str]:
    items = [
        *manifest.get("tools", []),
        manifest.get("prompt", {}),
        manifest.get("output", {}),
        *manifest.get("extensions", []),
    ]
    policies = policy.get("components", {})
    if not isinstance(policies, dict):
        raise TypeError("evolution.json components must be an object")
    return [
        str(item.get("instance_id"))
        for item in items
        if isinstance(item, dict)
        and policies.get(item.get("instance_id")) == "fixed"
    ]


def _extension_index(
    *,
    manifest: dict[str, Any],
    policy: dict[str, Any],
    workspace: CandidateWorkspace,
) -> list[dict[str, Any]]:
    """Return exact extension registry facts without reading component source."""

    policies = policy.get("components", {})
    if not isinstance(policies, dict):
        raise TypeError("evolution.json components must be an object")
    extensions = manifest.get("extensions", [])
    if not isinstance(extensions, list):
        raise TypeError("harness.json extensions must be an array")
    index = []
    for extension in extensions:
        if not isinstance(extension, dict):
            continue
        instance_id = extension.get("instance_id")
        entrypoint = extension.get("entrypoint")
        source_path = (
            str(entrypoint).split(":", 1)[0]
            if isinstance(entrypoint, str) and entrypoint
            else None
        )
        index.append(
            {
                "instance_id": instance_id,
                "entrypoint": entrypoint,
                "mutability": policies.get(instance_id, "unavailable"),
                "source_bytes": (
                    len(workspace.read_text(source_path).encode("utf-8"))
                    if source_path is not None and workspace.exists(source_path)
                    else None
                ),
            }
        )
    return index


def _student_hooks(extension_bindings: tuple[object, ...]) -> tuple[BaseHook, ...]:
    hooks: list[BaseHook] = []
    for binding in extension_bindings:
        for component in binding.components:
            if not isinstance(component, BaseHook):
                raise TypeError(
                    f"Student extension '{binding.instance_id}' returned a non-Hook"
                )
            hooks.append(component)
    return tuple(hooks)


def _text_diff(
    path: PurePosixPath,
    before: bytes | None,
    after: bytes | None,
) -> str:
    try:
        before_lines = (
            before.decode("utf-8").splitlines(keepends=True)
            if before is not None
            else []
        )
        after_lines = (
            after.decode("utf-8").splitlines(keepends=True)
            if after is not None
            else []
        )
    except UnicodeDecodeError:
        return "<binary content changed>"
    return "".join(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )


def _load_report(
    report_dir: Path,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    root = report_dir.resolve()
    summary = _read_json(root / "summary.json")
    cases = {
        str(item["example_id"]): item
        for item in _read_jsonl(root / "per_example.jsonl")
    }
    return summary, cases


def _resolve_rollout(
    explicit: Path | None,
    summary: dict[str, Any],
    report_dir: Path,
) -> Path:
    if explicit is not None:
        return explicit.resolve()
    source = summary.get("source_file")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("evaluation summary has no source_file")
    path = Path(source)
    if not path.is_absolute():
        path = report_dir.resolve() / path
    return path.resolve()


def _load_rollout_index(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    index = {}
    for record in _read_jsonl(path):
        example = record.get("example")
        replicate = record.get("replicate")
        if not isinstance(example, dict) or not isinstance(replicate, dict):
            raise ValueError("rollout record lacks example or replicate")
        key = (str(example.get("example_id")), str(replicate.get("replicate_id")))
        if key in index:
            raise ValueError(f"duplicate rollout identity: {key}")
        index[key] = record
    return index


def _case_projection(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "success_rate": case.get("success_rate"),
        "stability": case.get("stability"),
        "run_status": case.get("run_status"),
        "execution": case.get("execution"),
        "replicates": [
            {
                "replicate_id": item.get("replicate_id"),
                "score": item.get("score"),
                "run_status": item.get("run_status"),
                "predicted_answer": item.get("predicted_answer"),
                "runner_error": item.get("runner_error"),
                "execution": item.get("execution"),
            }
            for item in case.get("replicates", [])
            if isinstance(item, dict)
        ],
    }


def _trajectory_projection(record: dict[str, Any]) -> dict[str, Any]:
    run = record.get("run")
    if not isinstance(run, dict):
        return {"run": run}
    return {
        "harness": record.get("harness"),
        "provenance": record.get("provenance"),
        "run": {
            "question": run.get("question"),
            "answer": run.get("answer"),
            "status": run.get("status"),
            "error": run.get("error"),
            "trace": run.get("trace"),
        },
    }


def _success_rate(case: dict[str, Any]) -> float:
    value = case.get("success_rate")
    return float(value) if isinstance(value, (int, float)) else 0.0


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"JSON artifact does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON artifact {path}: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise TypeError(f"JSON artifact must contain an object: {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"JSONL artifact does not exist: {path}") from exc
    rows = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"invalid JSONL artifact {path}:{line_number}: {exc.msg}"
            ) from exc
        if not isinstance(value, dict):
            raise TypeError(
                f"JSONL artifact row must be an object: {path}:{line_number}"
            )
        rows.append(value)
    return rows


def _jsonable(value: Any) -> Any:
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _jsonable(value.to_dict())
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
