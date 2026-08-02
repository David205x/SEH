"""直接使用 OpenAI-compatible Chat Completions 的 Role Runner。"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from search_harness.integrations.openai_compatible import (
    OpenAICompatibleClient,
    OpenAICompatibleConfig,
    OpenAICompatibleToolRunner,
)

from .contracts import TeacherPayload, TrialReview
from ..resources.base import TeacherResourceConfig, TeacherResources
from .role_execution import (
    build_role_artifact,
    prepare_role_run,
    validate_role_output,
)
from .sessions import RoleContinuation, RoleSession


class NativeChatRoleRunner:
    """用显式 provider-native tool loop 执行一个 Teacher 角色。"""

    def __init__(
        self,
        *,
        env_file: Path | None = None,
        max_turns: int = 15,
        client: OpenAICompatibleClient | None = None,
        config: OpenAICompatibleConfig | None = None,
    ) -> None:
        if max_turns < 1:
            raise ValueError("Teacher max_turns must be positive")
        if client is not None and config is None:
            raise ValueError(
                "injected OpenAICompatibleClient requires explicit config"
            )
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
        role_id: str,
        role_version: int = 1,
        continuation: RoleContinuation | None = None,
    ) -> dict[str, Any]:
        """执行原生工具循环并返回完整 Teacher artifact。"""

        prepared = prepare_role_run(
            template_root=template_root,
            role_input=role_input,
            resource_config=resource_config,
            role_id=role_id,
            role_version=role_version,
        )
        resources = prepared.resources
        spec = prepared.spec
        session = _prepare_role_session(
            spec_role_id=spec.role.role_id,
            template_root=template_root,
            role_input=prepared.role_input.model_dump(mode="json"),
            resource_config=resource_config.model_dump(mode="json"),
            instructions=spec.prompt.instructions,
            user_input=prepared.rendered_input,
            resources=resources,
            continuation=continuation,
        )
        config = self.config or OpenAICompatibleConfig.from_env(
            env_file=self.env_file,
            prefix="TEACHER",
        )
        output_tool_name = f"submit_{spec.role.output_contract_id}"
        native_result = await OpenAICompatibleToolRunner(
            config=config,
            client=self.client,
        ).run(
            messages=session.messages,
            tools=spec.tools.tools,
            terminal_tool_name=output_tool_name,
            terminal_tool_description=(
                "Submit the final validated role result. Call this only after "
                "all necessary evidence and tools have been inspected."
            ),
            terminal_output_schema=spec.role.output_type.model_json_schema(),
            missing_terminal_message=(
                "No terminal structured result was submitted. Continue the "
                f"assigned role and call {output_tool_name} when the result "
                "is ready."
            ),
            submit_terminal=lambda arguments: _submit_output(
                output_type=spec.role.output_type,
                arguments=arguments,
                resources=resources,
            ),
            max_turns=self.max_turns,
            run_label=f"Teacher role '{spec.role.role_id}'",
        )
        output = native_result.output
        if not isinstance(output, TeacherPayload):
            raise TypeError("native tool runner returned an invalid role output")

        validate_role_output(output, resources)
        return build_role_artifact(
            prepared,
            runtime="native_chat",
            model=config.provenance(),
            output=output,
            tool_calls=[asdict(call) for call in native_result.tool_calls],
            usage=native_result.usage,
            transcript=native_result.transcript,
            runtime_fields={
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
            },
        )

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
            role_id="hypothesis_researcher",
            role_version=_artifact_role_version(previous_artifact),
            role_input=role_input,
            resource_config=_expanded_resource_config(
                resource_config,
                trial_files=attached_trials,
            ),
            continuation=RoleContinuation(
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
            role_id="evidence_reviewer",
            role_version=_artifact_role_version(previous_artifact),
            role_input=role_input,
            resource_config=TeacherResourceConfig.model_validate(
                resource_config
            ),
            continuation=RoleContinuation(
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


def _artifact_role_version(artifact: dict[str, Any]) -> int:
    role = artifact.get("role")
    if not isinstance(role, dict):
        raise TypeError("Teacher artifact role must be an object")
    version = role.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise TypeError("Teacher artifact role version must be a positive integer")
    return version


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
    continuation: RoleContinuation | None,
) -> RoleSession:
    if continuation is None:
        return RoleSession(
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
    restored = RoleSession(
        session_id=session["session_id"],
        revision=session["revision"],
        messages=deepcopy(artifact["transcript"]),
        output_history=deepcopy(session["output_history"]),
        feedback_history=deepcopy(session["feedback_history"]),
    )
    return restored.continued(
        feedback_event=feedback_event,
        feedback_message=_continuation_message(feedback_event),
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


def _submit_output(
    *,
    output_type: type[TeacherPayload],
    arguments: dict[str, Any],
    resources: TeacherResources,
) -> tuple[TeacherPayload | None, str, dict[str, Any]]:
    try:
        output = output_type.model_validate(arguments)
        validate_role_output(output, resources)
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
