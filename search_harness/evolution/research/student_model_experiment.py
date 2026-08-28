"""Teacher-directed, descriptive experiments against the Student model profile."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from search_harness.framework import (
    ChatMessage,
    HookModelBackend,
    HookModelRequest,
    ModelInput,
)


_THINKING_MODES = ("enabled", "disabled")
MAX_EXPERIMENT_USER_PROMPT_CHARACTERS = 16000


@dataclass(frozen=True)
class StudentModelExperimentCase:
    """One Teacher-authored input without a program-owned expected answer."""

    case_id: str
    user_prompt: str

    def __post_init__(self) -> None:
        case_id = self.case_id.strip()
        user_prompt = self.user_prompt.strip()
        if not case_id:
            raise ValueError("Student model experiment case_id must not be empty")
        if not user_prompt:
            raise ValueError("Student model experiment user_prompt must not be empty")
        if len(case_id) > 80:
            raise ValueError("Student model experiment case_id exceeds 80 characters")
        if len(user_prompt) > MAX_EXPERIMENT_USER_PROMPT_CHARACTERS:
            raise ValueError(
                "Student model experiment user_prompt exceeds "
                f"{MAX_EXPERIMENT_USER_PROMPT_CHARACTERS} characters"
            )
        object.__setattr__(self, "case_id", case_id)
        object.__setattr__(self, "user_prompt", user_prompt)


def run_student_model_experiment(
    *,
    backend: HookModelBackend,
    experiment_id: str,
    purpose: str,
    system_prompt: str,
    cases: tuple[StudentModelExperimentCase, ...],
    thinking_modes: tuple[str, ...],
    repetitions: int,
) -> dict[str, Any]:
    """Return raw generations and usage without deriving a pass/fail verdict."""

    purpose = purpose.strip()
    system_prompt = system_prompt.strip()
    if not purpose:
        raise ValueError("Student model experiment purpose must not be empty")
    if len(purpose) > 300:
        raise ValueError("Student model experiment purpose exceeds 300 characters")
    if not system_prompt:
        raise ValueError("Student model experiment system_prompt must not be empty")
    if len(system_prompt) > 6000:
        raise ValueError("Student model experiment system_prompt exceeds 6000 characters")
    if not 1 <= len(cases) <= 6:
        raise ValueError("Student model experiment requires one to six cases")
    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("Student model experiment case IDs must be unique")
    if not 1 <= repetitions <= 3:
        raise ValueError("Student model experiment repetitions must be one to three")
    if not thinking_modes or len(thinking_modes) > 2:
        raise ValueError("Student model experiment requires one or two thinking modes")
    if len(thinking_modes) != len(set(thinking_modes)):
        raise ValueError("Student model experiment thinking modes must be unique")
    invalid_modes = [
        mode for mode in thinking_modes if mode not in _THINKING_MODES
    ]
    if invalid_modes:
        raise ValueError(
            "Student model experiment thinking modes must be enabled or disabled"
        )

    observations = []
    for case in cases:
        model_input = ModelInput.from_messages(
            [
                ChatMessage(role="system", content=system_prompt),
                ChatMessage(role="user", content=case.user_prompt),
            ]
        )
        for thinking_mode in thinking_modes:
            for repetition in range(1, repetitions + 1):
                try:
                    response = backend.generate(
                        HookModelRequest(
                            profile="student",
                            purpose=f"experiment:{experiment_id}",
                            model_input=model_input,
                            thinking_mode=thinking_mode,
                        )
                    )
                except Exception as exc:
                    observations.append(
                        {
                            "case_id": case.case_id,
                            "thinking_mode": thinking_mode,
                            "repetition": repetition,
                            "raw_output": None,
                            "metadata": {},
                            "usage": {},
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
                    continue
                metadata = dict(response.metadata)
                usage = metadata.pop("usage", None)
                observations.append(
                    {
                        "case_id": case.case_id,
                        "thinking_mode": thinking_mode,
                        "repetition": repetition,
                        "raw_output": response.raw_output,
                        "metadata": metadata,
                        "usage": dict(usage) if isinstance(usage, dict) else {},
                        "error": None,
                    }
                )
    return {
        "schema_version": 1,
        "experiment_id": experiment_id,
        "experiment_signature": experiment_signature(
            system_prompt=system_prompt,
            cases=cases,
            thinking_modes=thinking_modes,
            repetitions=repetitions,
        ),
        "purpose": purpose,
        "system_prompt": system_prompt,
        "cases": [
            {"case_id": case.case_id, "user_prompt": case.user_prompt}
            for case in cases
        ],
        "thinking_modes": list(thinking_modes),
        "repetitions": repetitions,
        "observations": observations,
    }


def experiment_signature(
    *,
    system_prompt: str,
    cases: tuple[StudentModelExperimentCase, ...],
    thinking_modes: tuple[str, ...],
    repetitions: int,
) -> str:
    """Return a stable cache key for the requests that affect observations."""

    payload = {
        "system_prompt": system_prompt.strip(),
        "cases": [
            {"case_id": case.case_id, "user_prompt": case.user_prompt}
            for case in cases
        ],
        "thinking_modes": list(thinking_modes),
        "repetitions": repetitions,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
