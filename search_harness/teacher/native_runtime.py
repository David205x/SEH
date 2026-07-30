"""直接使用 OpenAI-compatible Chat Completions 的 Teacher runtime。"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from search_harness.framework.tooling import DefinedTool
from search_harness.models import OpenAICompatibleConfig

from .contracts import (
    CandidateReview,
    CompilerResult,
    EvidenceReview,
    FailureDirection,
    InterventionHypothesis,
    InterventionWorkerResult,
    MechanismDistillation,
    TeacherPayload,
    TrialReview,
)
from .loader import load_teacher_agent_spec
from .resources import TeacherResourceConfig, TeacherResources


class NativeChatClient(Protocol):
    """Native runtime 所需的最小异步 OpenAI client 接口。"""

    chat: Any

    async def close(self) -> None:
        """关闭 client 持有的网络资源。"""


@dataclass(frozen=True)
class NativeTeacherToolCall:
    """一次原生 tool call 的可审计结果。"""

    name: str
    call_id: str
    arguments: dict[str, Any]
    content: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class TeacherContinuation:
    """恢复一个已完成角色会话并追加结构化外部反馈。"""

    previous_artifact: dict[str, Any]
    feedback_source: str
    feedback: dict[str, Any]


class NativeChatTeacherRuntime:
    """用显式 provider-native tool loop 执行一个 Teacher 角色。"""

    def __init__(
        self,
        *,
        env_file: Path | None = None,
        max_turns: int = 15,
        client: NativeChatClient | None = None,
        config: OpenAICompatibleConfig | None = None,
    ) -> None:
        if max_turns < 1:
            raise ValueError("Teacher max_turns must be positive")
        if client is not None and config is None:
            raise ValueError("injected NativeChatClient requires explicit config")
        self.env_file = env_file
        self.max_turns = max_turns
        self.client = client
        self.config = config

    async def run(
        self,
        *,
        template_root: Path,
        role_input: dict[str, Any],
        resource_config: TeacherResourceConfig,
        continuation: TeacherContinuation | None = None,
    ) -> dict[str, Any]:
        """执行原生工具循环并返回完整 Teacher artifact。"""

        resources = TeacherResources.from_config(resource_config)
        spec = load_teacher_agent_spec(
            template_root,
            runtime_context=resources,
        )
        validated_input = spec.role.input_type.model_validate(role_input)
        resources.bind_role_input(validated_input)
        user_input = spec.prompt.render_input(
            validated_input,
            resources.model_context(spec.role.role_id),
        )
        session = _prepare_role_session(
            spec_role_id=spec.role.role_id,
            template_root=template_root,
            role_input=validated_input.model_dump(mode="json"),
            resource_config=resource_config.model_dump(mode="json"),
            instructions=spec.prompt.instructions,
            user_input=user_input,
            resources=resources,
            continuation=continuation,
        )
        config = self.config or OpenAICompatibleConfig.from_env(
            env_file=self.env_file,
            prefix="TEACHER",
        )
        client = self.client or AsyncOpenAI(
            api_key=config.api_key or "local",
            base_url=_api_base_url(config.base_url),
            timeout=config.timeout,
        )
        owns_client = self.client is None

        runtime_tools = {
            tool.name: tool for tool in spec.tools.tools
        }
        output_tool_name = f"submit_{spec.role.output_contract_id}"
        tool_specs = [
            _defined_tool_schema(tool) for tool in spec.tools.tools
        ]
        tool_specs.append(
            _output_tool_schema(
                name=output_tool_name,
                output_type=spec.role.output_type,
            )
        )
        messages = session.messages
        tool_calls: list[NativeTeacherToolCall] = []
        request_usage: list[dict[str, Any]] = []
        output: TeacherPayload | None = None

        try:
            for _turn in range(1, self.max_turns + 1):
                response = await client.chat.completions.create(
                    model=config.model_id,
                    messages=deepcopy(messages),
                    tools=tool_specs,
                    tool_choice="auto",
                    parallel_tool_calls=False,
                    temperature=config.temperature,
                    max_tokens=config.max_tokens,
                    extra_body=(
                        {"seed": config.seed}
                        if config.seed is not None
                        else None
                    ),
                )
                request_usage.append(_model_dump(response.usage))
                message = _first_response_message(response)
                assistant_payload = _assistant_message_payload(message)
                messages.append(assistant_payload)
                native_calls = _message_tool_calls(message)

                if not native_calls:
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "No terminal structured result was submitted. "
                                f"Continue the assigned role and call "
                                f"{output_tool_name} when the result is ready."
                            ),
                        }
                    )
                    continue

                submitted_output: TeacherPayload | None = None
                for call in native_calls:
                    name, call_id, arguments_text = _tool_call_fields(call)
                    arguments, parse_error = _parse_tool_arguments(arguments_text)
                    if parse_error is not None:
                        tool_calls.append(
                            NativeTeacherToolCall(
                                name=name,
                                call_id=call_id,
                                arguments={"raw_arguments": arguments_text},
                                content=parse_error,
                                metadata={"error_type": "invalid_json"},
                            )
                        )
                        messages.append(
                            _tool_message(call_id=call_id, content=parse_error)
                        )
                        continue

                    if name == output_tool_name and len(native_calls) > 1:
                        content = (
                            "The terminal submit tool must be called alone. "
                            "Complete any other tools first, then submit in the "
                            "next response."
                        )
                        metadata = {"error_type": "batched_terminal_tool"}
                        candidate_output = None
                    elif name == output_tool_name:
                        candidate_output, content, metadata = _submit_output(
                            output_type=spec.role.output_type,
                            arguments=arguments,
                            resources=resources,
                        )
                    else:
                        candidate_output = None
                        content, metadata = _run_defined_tool(
                            name=name,
                            arguments=arguments,
                            tools=runtime_tools,
                        )

                    tool_calls.append(
                        NativeTeacherToolCall(
                            name=name,
                            call_id=call_id,
                            arguments=arguments,
                            content=content,
                            metadata=metadata,
                        )
                    )
                    messages.append(
                        _tool_message(call_id=call_id, content=content)
                    )
                    if candidate_output is not None:
                        submitted_output = candidate_output

                if submitted_output is not None:
                    output = submitted_output
                    break
        finally:
            if owns_client:
                await client.close()

        if output is None:
            raise RuntimeError(
                f"Teacher role '{spec.role.role_id}' exhausted "
                f"{self.max_turns} turns without valid structured output"
            )

        output_schema = spec.role.output_type.model_json_schema()
        return {
            "schema_version": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "template_root": str(template_root.resolve()),
            "harness_id": spec.manifest.harness_id,
            "role": {
                "id": spec.role.role_id,
                "version": spec.role.version,
            },
            "output_contract": {
                "id": spec.role.output_contract_id,
                "version": spec.role.output_contract_version,
                "schema_digest": _schema_digest(output_schema),
            },
            "runtime": "native_chat",
            "model": config.provenance(),
            "input": validated_input.model_dump(mode="json"),
            "resource_config": resource_config.model_dump(mode="json"),
            "output": output.model_dump(mode="json"),
            "validated_mechanisms": resources.mechanisms.validated_payloads(),
            "resource_artifacts": resources.artifacts(),
            "tool_calls": [asdict(call) for call in tool_calls],
            "usage": _aggregate_usage(request_usage),
            "transcript": messages,
            "role_session": {
                "session_id": session.session_id,
                "revision": session.revision,
                "resource_state": resources.role_session_state(),
                "output_history": [
                    *session.output_history,
                    output.model_dump(mode="json"),
                ],
                "feedback_history": session.feedback_history,
            },
        }

    async def continue_researcher(
        self,
        *,
        previous_artifact: dict[str, Any],
        feedback_source: str,
        feedback: dict[str, Any],
        trial_files: list[Path] | None = None,
    ) -> dict[str, Any]:
        """把 Worker 或 Reviewer 反馈追加到原 Researcher transcript。"""

        role = previous_artifact.get("role")
        if not isinstance(role, dict) or role.get("id") != "hypothesis_researcher":
            raise ValueError(
                "only a Hypothesis Researcher artifact can be continued"
            )
        role_input = previous_artifact.get("input")
        resource_config = previous_artifact.get("resource_config")
        template_root = previous_artifact.get("template_root")
        if not isinstance(role_input, dict):
            raise TypeError("Researcher artifact input must be an object")
        if not isinstance(resource_config, dict):
            raise TypeError(
                "Researcher artifact resource_config must be an object"
            )
        if not isinstance(template_root, str) or not template_root:
            raise TypeError("Researcher artifact template_root must be a string")
        attached_trials = trial_files or []
        continuation_feedback = deepcopy(feedback)
        if attached_trials:
            continuation_feedback["trial_refs"] = [
                path.resolve().parent.name for path in attached_trials
            ]
        return await self.run(
            template_root=Path(template_root),
            role_input=role_input,
            resource_config=_expanded_resource_config(
                resource_config,
                trial_files=attached_trials,
            ),
            continuation=TeacherContinuation(
                previous_artifact=previous_artifact,
                feedback_source=feedback_source,
                feedback=continuation_feedback,
            ),
        )

    async def continue_reviewer(
        self,
        *,
        previous_artifact: dict[str, Any],
        trial_reviews: list[dict[str, Any]],
        aggregate_observations: dict[str, Any],
    ) -> dict[str, Any]:
        """在同一 Reviewer transcript 中追加独立 trial 审阅。"""

        role = previous_artifact.get("role")
        if not isinstance(role, dict) or role.get("id") != "evidence_reviewer":
            raise ValueError(
                "only an Evidence Reviewer artifact can be continued"
            )
        if not trial_reviews:
            raise ValueError("Reviewer continuation requires new trial reviews")
        previous_input = previous_artifact.get("input")
        resource_config = previous_artifact.get("resource_config")
        template_root = previous_artifact.get("template_root")
        previous_output = previous_artifact.get("output")
        if not isinstance(previous_input, dict):
            raise TypeError("Reviewer artifact input must be an object")
        if not isinstance(resource_config, dict):
            raise TypeError(
                "Reviewer artifact resource_config must be an object"
            )
        if not isinstance(template_root, str) or not template_root:
            raise TypeError("Reviewer artifact template_root must be a string")
        if not isinstance(previous_output, dict):
            raise TypeError("Reviewer artifact output must be an object")

        parsed_reviews = [
            TrialReview.model_validate(item).model_dump(mode="json")
            for item in trial_reviews
        ]
        previous_reviews = previous_input.get("trial_reviews")
        if not isinstance(previous_reviews, list):
            raise TypeError(
                "Reviewer artifact trial_reviews must be an array"
            )
        merged_reviews = [
            TrialReview.model_validate(item).model_dump(mode="json")
            for item in [*deepcopy(previous_reviews), *parsed_reviews]
        ]
        refs = [item["trial_ref"] for item in merged_reviews]
        if len(refs) != len(set(refs)):
            raise ValueError(
                "Reviewer continuation contains duplicate trial refs"
            )
        role_input = {
            **deepcopy(previous_input),
            "aggregate_observations": deepcopy(aggregate_observations),
            "trial_reviews": merged_reviews,
            "prior_obligation": previous_output.get("next_obligation"),
        }
        return await self.run(
            template_root=Path(template_root),
            role_input=role_input,
            resource_config=TeacherResourceConfig.model_validate(
                resource_config
            ),
            continuation=TeacherContinuation(
                previous_artifact=previous_artifact,
                feedback_source="trial_reviews",
                feedback={
                    "trial_reviews": parsed_reviews,
                    "aggregate_observations": deepcopy(
                        aggregate_observations
                    ),
                },
            ),
        )


@dataclass
class _PreparedRoleSession:
    session_id: str
    revision: int
    messages: list[dict[str, Any]]
    output_history: list[dict[str, Any]]
    feedback_history: list[dict[str, Any]]


def _expanded_resource_config(
    raw_config: dict[str, Any],
    *,
    trial_files: list[Path],
) -> TeacherResourceConfig:
    """在不改变其他资源的前提下追加显式 trial 文件。"""

    config = TeacherResourceConfig.model_validate(raw_config)
    existing = list(config.trial_files)
    known = {path.resolve() for path in existing}
    for path in trial_files:
        resolved = path.resolve()
        if resolved not in known:
            existing.append(resolved)
            known.add(resolved)
    return TeacherResourceConfig.model_validate(
        {
            **config.model_dump(mode="python"),
            "trial_files": existing,
        }
    )


def _prepare_role_session(
    *,
    spec_role_id: str,
    template_root: Path,
    role_input: dict[str, Any],
    resource_config: dict[str, Any],
    instructions: str,
    user_input: str,
    resources: TeacherResources,
    continuation: TeacherContinuation | None,
) -> _PreparedRoleSession:
    if continuation is None:
        return _PreparedRoleSession(
            session_id=uuid4().hex,
            revision=1,
            messages=[
                {"role": "system", "content": instructions},
                {"role": "user", "content": user_input},
            ],
            output_history=[],
            feedback_history=[],
        )

    artifact = continuation.previous_artifact
    _validate_continuation_artifact(
        artifact,
        spec_role_id=spec_role_id,
        template_root=template_root,
        role_input=role_input,
        resource_config=resource_config,
        instructions=instructions,
    )
    session = artifact["role_session"]
    resources.restore_role_session_state(session["resource_state"])
    feedback_event = {
        "source": continuation.feedback_source,
        "after_revision": session["revision"],
        "payload": deepcopy(continuation.feedback),
    }
    messages = deepcopy(artifact["transcript"])
    messages.append(
        {
            "role": "user",
            "content": _continuation_message(feedback_event),
        }
    )
    return _PreparedRoleSession(
        session_id=session["session_id"],
        revision=session["revision"] + 1,
        messages=messages,
        output_history=deepcopy(session["output_history"]),
        feedback_history=[
            *deepcopy(session["feedback_history"]),
            feedback_event,
        ],
    )


def _validate_continuation_artifact(
    artifact: dict[str, Any],
    *,
    spec_role_id: str,
    template_root: Path,
    role_input: dict[str, Any],
    resource_config: dict[str, Any],
    instructions: str,
) -> None:
    role = artifact.get("role")
    if not isinstance(role, dict) or role.get("id") != spec_role_id:
        raise ValueError("continued artifact role differs from current role")
    if not _continuation_input_matches(
        spec_role_id=spec_role_id,
        previous=artifact.get("input"),
        current=role_input,
    ):
        raise ValueError("continued artifact role input has changed")
    if not _continuation_resources_match(
        previous=artifact.get("resource_config"),
        current=resource_config,
    ):
        raise ValueError("continued artifact resource configuration has changed")
    previous_root = artifact.get("template_root")
    if (
        not isinstance(previous_root, str)
        or Path(previous_root).resolve() != template_root.resolve()
    ):
        raise ValueError("continued artifact template root has changed")
    transcript = artifact.get("transcript")
    if not isinstance(transcript, list) or len(transcript) < 2:
        raise TypeError("continued artifact transcript is invalid")
    first = transcript[0]
    if (
        not isinstance(first, dict)
        or first.get("role") != "system"
        or first.get("content") != instructions
    ):
        raise ValueError(
            "continued transcript system instruction differs from template"
        )
    session = artifact.get("role_session")
    if not isinstance(session, dict):
        raise ValueError("continued artifact has no role_session checkpoint")
    if not isinstance(session.get("session_id"), str):
        raise TypeError("role_session.session_id must be a string")
    if not isinstance(session.get("revision"), int):
        raise TypeError("role_session.revision must be an integer")
    if not isinstance(session.get("resource_state"), dict):
        raise TypeError("role_session.resource_state must be an object")
    if not isinstance(session.get("output_history"), list):
        raise TypeError("role_session.output_history must be a list")
    if not isinstance(session.get("feedback_history"), list):
        raise TypeError("role_session.feedback_history must be a list")


def _continuation_input_matches(
    *,
    spec_role_id: str,
    previous: object,
    current: dict[str, Any],
) -> bool:
    if previous == current:
        return True
    if spec_role_id != "evidence_reviewer":
        return False
    if not isinstance(previous, dict):
        return False
    stable_keys = set(previous) - {
        "aggregate_observations",
        "trial_reviews",
        "prior_obligation",
    }
    if any(previous.get(key) != current.get(key) for key in stable_keys):
        return False
    previous_reviews = previous.get("trial_reviews")
    current_reviews = current.get("trial_reviews")
    if not isinstance(previous_reviews, list) or not isinstance(
        current_reviews,
        list,
    ):
        return False
    return (
        len(previous_reviews) < len(current_reviews)
        and current_reviews[: len(previous_reviews)] == previous_reviews
    )


def _continuation_resources_match(
    *,
    previous: object,
    current: dict[str, Any],
) -> bool:
    if previous == current:
        return True
    if not isinstance(previous, dict):
        return False
    previous_without_trials = {
        key: value for key, value in previous.items() if key != "trial_files"
    }
    current_without_trials = {
        key: value for key, value in current.items() if key != "trial_files"
    }
    if previous_without_trials != current_without_trials:
        return False
    previous_trials = previous.get("trial_files")
    current_trials = current.get("trial_files")
    if not isinstance(previous_trials, list) or not isinstance(
        current_trials,
        list,
    ):
        return False
    previous_paths = {Path(str(path)).resolve() for path in previous_trials}
    current_paths = {Path(str(path)).resolve() for path in current_trials}
    return previous_paths <= current_paths


def _continuation_message(feedback_event: dict[str, Any]) -> str:
    source = feedback_event["source"]
    if source == "intervention_worker":
        instruction = (
            "The assigned intervention could not execute the frozen "
            "hypothesis because of a hypothesis-level capability mismatch. "
            "Revise the hypothesis so it uses supported observable state and "
            "actions."
        )
    elif source == "evidence_reviewer":
        instruction = (
            "Intervention evidence has been reviewed. Preserve supported "
            "parts of the previous hypothesis and respond directly to the "
            "review decision and next obligation. Submit one complete revised "
            "hypothesis."
        )
    elif source == "trial_reviews":
        instruction = (
            "New independent trial reviews for the same frozen hypothesis "
            "are attached. Preserve prior supported findings and update the "
            "global judgment against the accumulated reviews and deterministic "
            "aggregate observations."
        )
    else:
        raise ValueError(
            "unsupported role continuation source: "
            f"{source}"
        )
    return (
        "Continue as the same Teacher role in the existing session.\n"
        f"{instruction}\n\n"
        "Authoritative structured feedback:\n"
        + json.dumps(feedback_event, ensure_ascii=False, indent=2)
    )


def _defined_tool_schema(tool: DefinedTool) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.definition.description,
            "parameters": tool.definition.to_json_schema(),
        },
    }


def _output_tool_schema(
    *,
    name: str,
    output_type: type[TeacherPayload],
) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": (
                "Submit the final validated role result. Call this only after "
                "all necessary evidence and tools have been inspected."
            ),
            "parameters": output_type.model_json_schema(),
        },
    }


def _run_defined_tool(
    *,
    name: str,
    arguments: dict[str, Any],
    tools: dict[str, DefinedTool],
) -> tuple[str, dict[str, Any]]:
    tool = tools.get(name)
    if tool is None:
        return (
            f"Unknown tool '{name}'. Use one of: {sorted(tools)}",
            {"error_type": "unknown_tool"},
        )
    try:
        result = tool.run(arguments)
    except (
        FileNotFoundError,
        KeyError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        return (
            f"Tool execution failed: {type(exc).__name__}: {exc}",
            {
                "error_type": "tool_execution_error",
                "exception_type": type(exc).__name__,
            },
        )
    return result.content, dict(result.metadata)


def _submit_output(
    *,
    output_type: type[TeacherPayload],
    arguments: dict[str, Any],
    resources: TeacherResources,
) -> tuple[TeacherPayload | None, str, dict[str, Any]]:
    try:
        output = output_type.model_validate(arguments)
        _validate_role_result(output, resources)
    except (ValidationError, ValueError, KeyError) as exc:
        content = (
            "Structured output validation failed. Correct the listed fields "
            f"and call the submit tool again:\n{exc}"
        )
        return None, content, {
            "terminal": False,
            "validation_error": True,
        }
    content = json.dumps(output.model_dump(mode="json"), ensure_ascii=False)
    return output, content, {"terminal": True}


def _validate_role_result(
    output: TeacherPayload,
    resources: TeacherResources,
) -> None:
    if isinstance(output, FailureDirection):
        if resources.evaluation is None:
            raise ValueError("Failure Analyst resources are unavailable")
        resources.evaluation.validate_evidence_refs(output.evidence_refs)
    if isinstance(output, InterventionHypothesis):
        resources.validate_hypothesis_research()
    if isinstance(output, EvidenceReview):
        resources.validate_evidence_review(output)
    if isinstance(output, TrialReview):
        if resources.trials is None:
            raise ValueError("Trial Reviewer resources are unavailable")
        resources.trials.validate_trial_review(output)
    if isinstance(output, MechanismDistillation) and output.decision == "distilled":
        if output.mechanism_ref is None:
            raise ValueError("distilled result lacks mechanism_ref")
        resources.mechanisms.resolve(output.mechanism_ref)
    if isinstance(output, InterventionWorkerResult):
        raise ValueError(
            "Intervention Worker must run through "
            "InterventionRoleRuntime so one transcript can span Hook phases"
        )
    if isinstance(output, CompilerResult) and output.decision == "submitted":
        if resources.compiler is None:
            raise ValueError("Compiler resources are unavailable")
        if output.candidate_ref is None:
            raise ValueError("submitted Compiler result lacks candidate_ref")
        resources.compiler.resolve(output.candidate_ref)
    if isinstance(output, CandidateReview):
        if resources.candidate_review is None:
            raise ValueError("Candidate Reviewer resources are unavailable")
        resources.candidate_review.validate_review()


def _first_response_message(response: Any) -> Any:
    choices = getattr(response, "choices", None)
    if not isinstance(choices, list) or not choices:
        raise ValueError("Teacher response has no choices")
    message = getattr(choices[0], "message", None)
    if message is None:
        raise ValueError("Teacher response choice has no message")
    return message


def _message_tool_calls(message: Any) -> list[Any]:
    calls = getattr(message, "tool_calls", None)
    if calls is None and isinstance(message, dict):
        calls = message.get("tool_calls")
    if calls is None:
        return []
    if not isinstance(calls, list):
        raise TypeError("Teacher assistant tool_calls must be a list")
    return calls


def _tool_call_fields(call: Any) -> tuple[str, str, str]:
    if isinstance(call, dict):
        function = call.get("function")
        call_id = call.get("id")
    else:
        function = getattr(call, "function", None)
        call_id = getattr(call, "id", None)
    if isinstance(function, dict):
        name = function.get("name")
        arguments = function.get("arguments")
    else:
        name = getattr(function, "name", None)
        arguments = getattr(function, "arguments", None)
    if not isinstance(name, str) or not name:
        raise ValueError("Teacher tool call has no function name")
    if not isinstance(call_id, str) or not call_id:
        raise ValueError(f"Teacher tool call '{name}' has no call id")
    if not isinstance(arguments, str):
        raise TypeError(f"Teacher tool call '{name}' arguments must be JSON text")
    return name, call_id, arguments


def _parse_tool_arguments(
    raw_arguments: str,
) -> tuple[dict[str, Any], str | None]:
    try:
        arguments = json.loads(raw_arguments)
    except json.JSONDecodeError as exc:
        return {}, (
            "Tool arguments are invalid JSON. Correct them and call the tool "
            f"again: {exc.msg}"
        )
    if not isinstance(arguments, dict):
        return {}, "Tool arguments must be a JSON object."
    return arguments, None


def _assistant_message_payload(message: Any) -> dict[str, Any]:
    payload = _model_dump(message)
    extra = getattr(message, "model_extra", None)
    if isinstance(extra, dict):
        payload.update(
            {
                key: value
                for key, value in extra.items()
                if value is not None and key not in payload
            }
        )
    if not payload:
        payload = {
            "role": "assistant",
            "content": getattr(message, "content", None),
        }
        calls = getattr(message, "tool_calls", None)
        if calls is not None:
            payload["tool_calls"] = [_model_dump(call) for call in calls]
    payload["role"] = "assistant"
    return payload


def _tool_message(*, call_id: str, content: str) -> dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": call_id,
        "content": content,
    }


def _model_dump(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", exclude_none=True)
    if isinstance(value, dict):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        payload = model_dump(mode="json", exclude_none=True)
        if isinstance(payload, dict):
            return payload
    return {}


def _aggregate_usage(items: list[dict[str, Any]]) -> dict[str, Any]:
    input_tokens = sum(
        _integer(item.get("prompt_tokens", item.get("input_tokens", 0)))
        for item in items
    )
    output_tokens = sum(
        _integer(item.get("completion_tokens", item.get("output_tokens", 0)))
        for item in items
    )
    total_tokens = sum(
        _integer(item.get("total_tokens", 0))
        for item in items
    )
    return {
        "requests": len(items),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "calls": items,
    }


def _integer(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _schema_digest(schema: dict[str, Any]) -> str:
    payload = json.dumps(
        schema,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _api_base_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    suffix = "/chat/completions"
    if normalized.endswith(suffix):
        normalized = normalized[: -len(suffix)]
    return normalized
