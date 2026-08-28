"""Prompt exploration for one frozen stateless Shadow Hook-model task."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from search_harness.framework import (
    ChatMessage,
    ModelInput,
    render_hook_prompt_user_message,
)
from search_harness.integrations.openai_compatible import (
    OpenAICompatibleConfig,
    OpenAICompatibleModel,
    ProfiledHookModelBackend,
)

from .intervention.prefix import (
    load_reconstructed_prefix,
    load_rollout_record,
    resolve_prefix_boundary,
)
from .intervention.types import PrefixSelector, ReconstructedPrefix
from .roles.contracts import (
    ShadowDecisionTask,
    ShadowHookPromptProduct,
    ShadowPromptResearcherInput,
    ShadowPromptResearchResult,
    ShadowPromptResearchSubmission,
    TrialReview,
)
from .shadow_task_inputs import (
    project_shadow_task_inputs,
    shadow_input_projection_digest,
    shadow_phase_task_digest,
)
from .student_model_experiment import (
    StudentModelExperimentCase,
    run_student_model_experiment,
)


_REVIEW_SYSTEM_PROMPT = """You are an independent semantic reviewer for one
Student Hook-model probe.
Independently apply the frozen task to the supplied exact runtime input, then
judge the Student output. The reviewed Trial label is a reference claim, not
proof and not a string-matching rule. Use no fact that is absent from the runtime
input. If the frozen task requires a fact that the projection does not supply, or
if the reference label cannot be independently justified from the projection,
return uncertain. Return supported only when the projection itself supports the
Student output under the frozen boundaries. Do not improve the Prompt or propose
a mechanism change.
Return exactly two lines and no additional text:
DECISION: supported|unsupported|uncertain
ASSESSMENT: one concise factual reason
"""

_PROMPT_FIDELITY_SYSTEM_PROMPT = """You are an independent contract reviewer
for one Student Hook-model Prompt.
Compare the candidate Prompt with the frozen task clause by clause. For a
Decision Task, verify that every positive, negative and uncertain condition keeps
the same label and that no sentence contradicts another boundary. For every Task,
verify that the Prompt uses the declared projected values exactly as supplied.
Reject a Prompt that compensates for a missing value by inventing alternate
semantics, weakens a required condition, adds shortcuts or hidden facts, broadens
applicability, or introduces downstream actions. Clarification is allowed only
when it remains logically equivalent to the frozen task. Return exactly two lines
and no additional text:
DECISION: supported|unsupported|uncertain
ASSESSMENT: one concise factual reason
"""

class ShadowPromptResearchResourceConfig(BaseModel):
    """Program-owned inputs for one bounded Prompt Research run."""

    model_config = ConfigDict(extra="forbid")

    rollout_file: Path
    env_file: Path
    max_cases: int = Field(default=4, ge=1, le=6)
    repetitions: int = Field(default=2, ge=1, le=3)
    thinking_modes: tuple[str, ...] = ("enabled", "disabled")
    reviewer_max_tokens: int = Field(default=700, ge=128, le=2000)

    def model_post_init(self, __context: Any) -> None:
        del __context
        if not self.rollout_file.is_file():
            raise FileNotFoundError(
                f"Prompt Research rollout does not exist: {self.rollout_file}"
            )
        if not self.env_file.is_file():
            raise FileNotFoundError(
                f"Prompt Research env file does not exist: {self.env_file}"
            )
        if not self.thinking_modes or len(self.thinking_modes) > 2:
            raise ValueError(
                "Prompt Research requires one or two thinking modes"
            )
        if len(self.thinking_modes) != len(set(self.thinking_modes)):
            raise ValueError("Prompt Research thinking modes must be unique")
        invalid = set(self.thinking_modes) - {"enabled", "disabled"}
        if invalid:
            raise ValueError(
                "Prompt Research thinking modes must be enabled or disabled"
            )


@dataclass(frozen=True)
class _PromptCase:
    case_id: str
    trial_ref: str
    expected_label: str
    phase_execution: str
    decisive_observation: str
    projection: dict[str, Any]


class ShadowPromptResearchStore:
    """Run Student probes and materialize one reviewed Hook Prompt Product."""

    def __init__(
        self,
        *,
        config: ShadowPromptResearchResourceConfig,
        trial_files: list[Path],
    ) -> None:
        self.config = config
        self._trial_files = [path.resolve() for path in trial_files]
        self._input: ShadowPromptResearcherInput | None = None
        self._cases: list[_PromptCase] = []
        self._probes: dict[str, dict[str, Any]] = {}

    def bind(self, role_input: ShadowPromptResearcherInput) -> None:
        """Freeze one phase and deterministically prepare reviewed cases."""

        self._input = role_input
        self._cases = _build_cases(
            role_input=role_input,
            trial_files=self._trial_files,
            rollout_file=self.config.rollout_file,
            limit=self.config.max_cases,
        )
        if not self._cases:
            raise ValueError(
                "Shadow Prompt Research has no reviewed cases for its phase"
            )

    def model_context(self) -> dict[str, Any]:
        """Return immutable scope and Probe budget without exact case content."""

        role_input = self._require_input()
        phase = role_input.mechanism.phases[0]
        return {
            "phase": role_input.phase,
            "task_digest": shadow_phase_task_digest(
                phase=role_input.phase,
                task=phase.task.model_dump(mode="json"),
            ),
            "input_projection_digest": shadow_input_projection_digest(
                phase=role_input.phase,
                inputs=[
                    item.model_dump(mode="json")
                    for item in phase.task.inputs
                ],
            ),
            "case_count": len(self._cases),
            "thinking_modes": list(self.config.thinking_modes),
            "repetitions": self.config.repetitions,
            "probe_count": len(self._probes),
        }

    def run_probe(self, *, prompt: str) -> dict[str, Any]:
        """Run one candidate Prompt against fixed cases and review every output."""

        prompt = prompt.strip()
        if not prompt:
            raise ValueError("Hook Prompt must not be empty")
        if len(prompt) > 6000:
            raise ValueError("Hook Prompt exceeds 6000 characters")
        role_input = self._require_input()
        phase = role_input.mechanism.phases[0]
        probe_ref = f"shadow_prompt_probe_{len(self._probes) + 1:03d}"
        student_cases = tuple(
            StudentModelExperimentCase(
                case_id=case.case_id,
                user_prompt=_student_user_prompt(case.projection),
            )
            for case in self._cases
        )
        experiment = run_student_model_experiment(
            backend=ProfiledHookModelBackend(
                env_file=self.config.env_file,
                seed=42,
            ),
            experiment_id=probe_ref,
            purpose=(
                "shadow_prompt_research: Evaluate one frozen Hook-model "
                f"task at {role_input.phase}."
            ),
            system_prompt=prompt,
            cases=student_cases,
            thinking_modes=self.config.thinking_modes,
            repetitions=self.config.repetitions,
        )
        references = {case.case_id: case for case in self._cases}
        reviewer = _PromptProbeReviewer(
            env_file=self.config.env_file,
            max_tokens=self.config.reviewer_max_tokens,
        )
        prompt_review = reviewer.review_prompt(
            task=phase.task.model_dump(mode="json"),
            prompt=prompt,
        )
        reviewed_observations = []
        for observation in experiment["observations"]:
            case = references[str(observation["case_id"])]
            sanitized = _sanitize_student_observation(observation)
            review = reviewer.review(
                task=phase.task.model_dump(mode="json"),
                projection=case.projection,
                expected_label=case.expected_label,
                student_output=sanitized.get("raw_output"),
                student_error=sanitized.get("error"),
            )
            reviewed_observations.append({**sanitized, "review": review})
        probe = {
            "schema_version": 1,
            "probe_ref": probe_ref,
            "phase": role_input.phase,
            "task_digest": shadow_phase_task_digest(
                phase=role_input.phase,
                task=phase.task.model_dump(mode="json"),
            ),
            "input_projection_digest": shadow_input_projection_digest(
                phase=role_input.phase,
                inputs=[
                    item.model_dump(mode="json")
                    for item in phase.task.inputs
                ],
            ),
            "prompt": prompt,
            "prompt_digest": _text_digest(prompt),
            "prompt_review": prompt_review,
            "thinking_modes": list(self.config.thinking_modes),
            "repetitions": self.config.repetitions,
            "cases": [
                {
                    "case_id": case.case_id,
                    "trial_ref": case.trial_ref,
                    "expected_label": case.expected_label,
                    "phase_execution": case.phase_execution,
                    "decisive_observation": case.decisive_observation,
                    "projection": case.projection,
                }
                for case in self._cases
            ],
            "observations": reviewed_observations,
            "summary": {
                **_probe_summary(reviewed_observations),
                "prompt_review_tokens": _usage_total(
                    prompt_review.get("usage")
                ),
            },
        }
        self._probes[probe_ref] = probe
        return _probe_model_view(probe)

    def materialize(
        self,
        submission: ShadowPromptResearchSubmission,
    ) -> ShadowPromptResearchResult:
        """Bind model-selected Prompt text to program-owned phase identities."""

        if submission.outcome == "not_feasible":
            if not self._probes:
                raise ValueError(
                    "not_feasible Prompt Research result requires Probe evidence"
                )
            return ShadowPromptResearchResult(
                outcome="not_feasible",
                product=None,
                obligation=submission.obligation,
            )
        probe = self._require_probe(submission.selected_probe_ref)
        if submission.prompt != probe["prompt"]:
            raise ValueError(
                "selected Prompt must exactly match the reviewed probe Prompt"
            )
        if submission.thinking_mode not in probe["thinking_modes"]:
            raise ValueError(
                "selected thinking mode was not run by the selected probe"
            )
        prompt_review = probe.get("prompt_review")
        if (
            not isinstance(prompt_review, dict)
            or prompt_review.get("decision") != "supported"
        ):
            raise ValueError(
                "selected Prompt lacks a supported fidelity review"
            )
        selected_observations = [
            item
            for item in probe["observations"]
            if item.get("thinking_mode") == submission.thinking_mode
        ]
        if not selected_observations or any(
            item.get("review", {}).get("decision") != "supported"
            for item in selected_observations
        ):
            raise ValueError(
                "selected Prompt and thinking mode are not supported on every "
                "reviewed Probe observation"
            )
        role_input = self._require_input()
        phase = role_input.mechanism.phases[0]
        response_adapter = (
            "tri_label"
            if isinstance(phase.task, ShadowDecisionTask)
            else "raw_text"
        )
        product = ShadowHookPromptProduct(
            phase=role_input.phase,
            task_digest=probe["task_digest"],
            input_projection_digest=probe["input_projection_digest"],
            prompt=submission.prompt,
            thinking_mode=submission.thinking_mode,
            response_adapter=response_adapter,
        )
        return ShadowPromptResearchResult(
            outcome="ready",
            product=product,
            obligation=None,
        )

    def artifacts(self) -> dict[str, Any]:
        """Persist full exact Probe evidence outside the active tool view."""

        return {
            "shadow_prompt_probes": list(self._probes.values()),
        }

    def _require_input(self) -> ShadowPromptResearcherInput:
        if self._input is None:
            raise RuntimeError("Shadow Prompt Research input is not bound")
        return self._input

    def _require_probe(self, probe_ref: str | None) -> dict[str, Any]:
        if probe_ref is None:
            raise ValueError("ready Prompt Research result lacks probe ref")
        try:
            return self._probes[probe_ref]
        except KeyError as exc:
            raise KeyError(f"unknown Shadow Prompt probe: {probe_ref}") from exc


class _PromptProbeReviewer:
    """Independent synchronous Teacher judge used inside the Probe tool."""

    def __init__(self, *, env_file: Path, max_tokens: int) -> None:
        config = OpenAICompatibleConfig.from_env(
            env_file=env_file,
            prefix="TEACHER",
        )
        config = replace(
            config,
            max_tokens=max_tokens,
            temperature=0.0,
            seed=42,
        ).with_configured_thinking_mode("disabled")
        self._model = OpenAICompatibleModel(config)

    def review(
        self,
        *,
        task: dict[str, Any],
        projection: dict[str, Any],
        expected_label: str,
        student_output: object,
        student_error: object,
    ) -> dict[str, Any]:
        payload = {
            "frozen_task": task,
            "runtime_input": projection,
            "reviewed_trial_reference": {
                "expected_label": expected_label,
            },
            "student_output": student_output,
            "student_error": student_error,
        }
        try:
            response = self._model.generate(
                ModelInput.from_messages(
                    [
                        ChatMessage(
                            role="system",
                            content=_REVIEW_SYSTEM_PROMPT,
                        ),
                        ChatMessage(
                            role="user",
                            content=json.dumps(
                                payload,
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ),
                        ),
                    ]
                )
            )
        except Exception as exc:
            return {
                "decision": "uncertain",
                "assessment": f"Teacher review failed: {type(exc).__name__}",
                "raw_output": None,
                "usage": {},
                "error": f"{type(exc).__name__}: {exc}",
            }
        decision, assessment = _parse_review(response.raw_output)
        return {
            "decision": decision,
            "assessment": assessment,
            "raw_output": response.raw_output,
            "usage": dict(response.usage),
            "error": None,
        }

    def review_prompt(
        self,
        *,
        task: dict[str, Any],
        prompt: str,
    ) -> dict[str, Any]:
        """Review candidate Prompt fidelity independently of case outcomes."""

        payload = {
            "frozen_task": task,
            "candidate_prompt": prompt,
        }
        return _run_teacher_review(
            model=self._model,
            system_prompt=_PROMPT_FIDELITY_SYSTEM_PROMPT,
            payload=payload,
            failure_prefix="Teacher Prompt review failed",
        )


def _build_cases(
    *,
    role_input: ShadowPromptResearcherInput,
    trial_files: list[Path],
    rollout_file: Path,
    limit: int,
) -> list[_PromptCase]:
    trial_by_ref = {path.parent.name: path for path in trial_files}
    buckets: dict[str, list[_PromptCase]] = {
        "positive": [],
        "negative": [],
        "uncertain": [],
    }
    phase = role_input.mechanism.phases[0]
    task_inputs = [item.model_dump(mode="json") for item in phase.task.inputs]
    for review in role_input.trial_reviews:
        trial_path = trial_by_ref.get(review.trial_ref)
        if trial_path is None:
            raise ValueError(
                "Prompt Research Trial Review references unattached Trial: "
                f"{review.trial_ref}"
            )
        trial = _read_json(trial_path)
        trial_input = _required_object(trial, "input")
        for observation in review.predicate_observations:
            if observation.phase != role_input.phase:
                continue
            prefix = _trial_prefix(
                trial_input=trial_input,
                rollout_file=rollout_file,
                expected_phase=role_input.phase,
            )
            projection = project_shadow_task_inputs(
                phase=role_input.phase,
                inputs=task_inputs,
                get_state=lambda source, current=prefix: _prefix_state_value(
                    current,
                    source,
                ),
            )
            case = _PromptCase(
                case_id=f"{review.trial_ref}_{role_input.phase}",
                trial_ref=review.trial_ref,
                expected_label=observation.predicate_label,
                phase_execution=observation.phase_execution,
                decisive_observation=observation.decisive_observation,
                projection=projection,
            )
            buckets[observation.predicate_label].append(case)
    selected: list[_PromptCase] = []
    while len(selected) < limit:
        added = False
        for label in ("positive", "negative", "uncertain"):
            if buckets[label] and len(selected) < limit:
                selected.append(buckets[label].pop(0))
                added = True
        if not added:
            break
    return selected


def _trial_prefix(
    *,
    trial_input: dict[str, Any],
    rollout_file: Path,
    expected_phase: str,
) -> ReconstructedPrefix:
    example_id = _required_string(trial_input, "example_id")
    replicate_id = _required_string(trial_input, "replicate_id")
    prefix_id = _required_int(trial_input, "prefix_id")
    record = load_rollout_record(rollout_file, example_id, replicate_id)
    boundary = resolve_prefix_boundary(record, prefix_id)
    phase = str(boundary["phase"])
    if phase != expected_phase:
        raise ValueError(
            f"Prompt Research Trial phase mismatch: {phase} != {expected_phase}"
        )
    return load_reconstructed_prefix(
        PrefixSelector(
            rollout_file=rollout_file,
            example_id=example_id,
            replicate_id=replicate_id,
            step=int(boundary["step"]),
            phase=phase,
        )
    )


def _prefix_state_value(prefix: ReconstructedPrefix, source: str) -> Any:
    if source.startswith("stage."):
        name = source.removeprefix("stage.")
        if name not in prefix.stage_values:
            raise KeyError(f"Prompt Research prefix lacks {source}")
        return prefix.stage_values[name]
    if source == "core.question":
        return prefix.example.get("question") or prefix.source_run.get("question")
    if source == "core.step":
        return prefix.selector.step
    if source == "core.status":
        return "running"
    if source == "core.error":
        return None
    if source == "core.max_steps":
        state = prefix.source_run.get("state")
        return state.get("max_steps") if isinstance(state, dict) else None
    if source == "core.model_inputs":
        return [
            event["payload"]
            for event in prefix.retained_trace
            if event.get("event_type") == "model_input"
        ]
    if source == "core.model_outputs":
        return [
            event.get("payload", {}).get("raw_output")
            for event in prefix.retained_trace
            if event.get("event_type") == "model_output"
        ]
    if source == "core.parsed_outputs":
        return [
            event["payload"]
            for event in prefix.retained_trace
            if event.get("event_type") == "parsed_output"
        ]
    if source == "core.tool_interactions":
        return _prefix_tool_interactions(prefix)
    if source == "core.conversation_messages":
        return _prefix_conversation_messages(prefix)
    raise KeyError(f"Prompt Research prefix projector does not support {source}")


def _prefix_tool_interactions(prefix: ReconstructedPrefix) -> list[dict[str, Any]]:
    calls: dict[int, dict[str, Any]] = {}
    interactions = []
    for event in prefix.retained_trace:
        step = int(event.get("step", 0))
        event_type = event.get("event_type")
        payload = event.get("payload")
        payload = payload if isinstance(payload, dict) else {}
        if event_type == "tool_call":
            calls[step] = dict(payload)
        elif event_type == "tool_result" and step in calls:
            interactions.append(
                {
                    "tool_call": calls.pop(step),
                    "tool_result": dict(payload),
                }
            )
    return interactions


def _prefix_conversation_messages(
    prefix: ReconstructedPrefix,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    output_by_step: dict[int, str] = {}
    for event in prefix.retained_trace:
        step = int(event.get("step", 0))
        payload = event.get("payload")
        payload = payload if isinstance(payload, dict) else {}
        if event.get("event_type") == "model_output":
            output_by_step[step] = str(payload.get("raw_output") or "")
        elif event.get("event_type") == "tool_result":
            messages.extend(
                (
                    {"role": "assistant", "content": output_by_step.get(step, "")},
                    {"role": "user", "content": str(payload.get("content") or "")},
                )
            )
        elif event.get("event_type") == "final_deferred":
            messages.extend(
                (
                    {"role": "assistant", "content": output_by_step.get(step, "")},
                    {"role": "user", "content": str(payload.get("feedback") or "")},
                )
            )
    return messages


def _student_user_prompt(projection: dict[str, Any]) -> str:
    return render_hook_prompt_user_message(projection)


def _sanitize_student_observation(value: dict[str, Any]) -> dict[str, Any]:
    metadata = value.get("metadata")
    metadata = dict(metadata) if isinstance(metadata, dict) else {}
    for key in ("reasoning", "reasoning_content", "thinking"):
        metadata.pop(key, None)
    return {
        "case_id": value.get("case_id"),
        "thinking_mode": value.get("thinking_mode"),
        "repetition": value.get("repetition"),
        "raw_output": value.get("raw_output"),
        "metadata": metadata,
        "usage": (
            dict(value["usage"])
            if isinstance(value.get("usage"), dict)
            else {}
        ),
        "error": value.get("error"),
    }


def _run_teacher_review(
    *,
    model: OpenAICompatibleModel,
    system_prompt: str,
    payload: dict[str, Any],
    failure_prefix: str,
) -> dict[str, Any]:
    try:
        response = model.generate(
            ModelInput.from_messages(
                [
                    ChatMessage(role="system", content=system_prompt),
                    ChatMessage(
                        role="user",
                        content=json.dumps(
                            payload,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    ),
                ]
            )
        )
    except Exception as exc:
        return {
            "decision": "uncertain",
            "assessment": f"{failure_prefix}: {type(exc).__name__}",
            "raw_output": None,
            "usage": {},
            "error": f"{type(exc).__name__}: {exc}",
        }
    decision, assessment = _parse_review(response.raw_output)
    return {
        "decision": decision,
        "assessment": assessment,
        "raw_output": response.raw_output,
        "usage": dict(response.usage),
        "error": None,
    }


def _parse_review(value: str) -> tuple[str, str]:
    decision_match = re.search(
        r"(?im)^DECISION:\s*(supported|unsupported|uncertain)\s*$",
        value,
    )
    assessment_match = re.search(
        r"(?im)^ASSESSMENT:\s*(.+)$",
        value,
    )
    if decision_match is None or assessment_match is None:
        return "uncertain", "Teacher review output did not match its line protocol."
    assessment = " ".join(assessment_match.group(1).split())[:700]
    return decision_match.group(1).casefold(), assessment


def _probe_summary(observations: list[dict[str, Any]]) -> dict[str, Any]:
    modes: dict[str, dict[str, int]] = {}
    student_tokens: dict[str, int] = {}
    reviewer_tokens: dict[str, int] = {}
    for item in observations:
        mode = str(item.get("thinking_mode") or "unknown")
        decision = str(item.get("review", {}).get("decision") or "uncertain")
        counts = modes.setdefault(
            mode,
            {"supported": 0, "unsupported": 0, "uncertain": 0},
        )
        counts[decision if decision in counts else "uncertain"] += 1
        student_tokens[mode] = student_tokens.get(mode, 0) + _usage_total(
            item.get("usage")
        )
        reviewer_tokens[mode] = reviewer_tokens.get(mode, 0) + _usage_total(
            item.get("review", {}).get("usage")
        )
    return {
        "review_decisions_by_mode": modes,
        "student_tokens_by_mode": student_tokens,
        "reviewer_tokens_by_mode": reviewer_tokens,
    }


def _probe_model_view(probe: dict[str, Any]) -> dict[str, Any]:
    case_by_id = {
        str(item["case_id"]): item for item in probe["cases"]
    }
    observations = []
    for item in probe["observations"]:
        case = case_by_id[str(item["case_id"])]
        observations.append(
            {
                "case_id": item["case_id"],
                "trial_ref": case["trial_ref"],
                "expected_label": case["expected_label"],
                "decisive_observation": case["decisive_observation"],
                "input_preview": _compact_preview(case["projection"], 3000),
                "thinking_mode": item["thinking_mode"],
                "repetition": item["repetition"],
                "student_output": item["raw_output"],
                "student_error": item["error"],
                "review": {
                    "decision": item["review"]["decision"],
                    "assessment": item["review"]["assessment"],
                    "error": item["review"]["error"],
                },
            }
        )
    return {
        "probe_ref": probe["probe_ref"],
        "prompt_digest": probe["prompt_digest"],
        "phase": probe["phase"],
        "task_digest": probe["task_digest"],
        "input_projection_digest": probe["input_projection_digest"],
        "prompt_review": {
            "decision": probe["prompt_review"]["decision"],
            "assessment": probe["prompt_review"]["assessment"],
            "error": probe["prompt_review"]["error"],
        },
        "summary": probe["summary"],
        "observations": observations,
    }


def _compact_preview(value: Any, limit: int) -> str:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if len(text) <= limit:
        return text
    half = (limit - 32) // 2
    return f"{text[:half]}...[content omitted]...{text[-half:]}"


def _usage_total(value: object) -> int:
    if not isinstance(value, dict):
        return 0
    amount = value.get("total_tokens")
    return amount if isinstance(amount, int) and not isinstance(amount, bool) else 0


def _text_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"JSON artifact must contain an object: {path}")
    return value


def _required_object(value: dict[str, Any], name: str) -> dict[str, Any]:
    item = value.get(name)
    if not isinstance(item, dict):
        raise TypeError(f"{name} must be an object")
    return dict(item)


def _required_string(value: dict[str, Any], name: str) -> str:
    item = value.get(name)
    if not isinstance(item, str) or not item.strip():
        raise TypeError(f"{name} must be a non-empty string")
    return item


def _required_int(value: dict[str, Any], name: str) -> int:
    item = value.get(name)
    if not isinstance(item, int) or isinstance(item, bool) or item < 1:
        raise TypeError(f"{name} must be a positive integer")
    return item
